"""The sync loop: pull pages, mirror rows, persist the cursor.

The loop is the canonical integration:

1. Read the saved cursor. ``None`` means this is the first run.
2. First run calls with ``since=1970-01-01T00:00:00Z``; every later call uses
   the saved/returned ``cursor`` (cursor wins over since).
3. For each row: ``deleted_at`` null -> upsert by id; otherwise delete by id.
   When ``photo_dir`` is given, a live row's signed photo URLs are downloaded
   in this same iteration (before they expire) and the local paths stored.
4. Save ``next_cursor``, replacing the previous one.
5. If ``has_more`` is true, immediately fetch again with the new cursor;
   otherwise stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .client import ExportClient
from .photos import download_row_photos
from .store import Store

# The first-ever call asks for everything since the Unix epoch.
EPOCH = "1970-01-01T00:00:00Z"


@dataclass
class SyncResult:
    pages: int = 0
    upserts: int = 0
    deletes: int = 0
    photos: int = 0
    final_cursor: str | None = None


def sync(
    client: ExportClient,
    store: Store,
    *,
    photo_dir: str | Path | None = None,
) -> SyncResult:
    result = SyncResult()
    cursor = store.get_cursor()
    use_since = cursor is None

    while True:
        if use_since:
            page = client.fetch(since=EPOCH)
            use_since = False
        else:
            page = client.fetch(cursor=cursor)

        for row in page["rows"]:
            if row.get("deleted_at"):
                store.delete_row(row["id"])
                result.deletes += 1
            else:
                paths = {}
                if photo_dir is not None:
                    paths = download_row_photos(row, photo_dir, client.session)
                    result.photos += sum(p is not None for p in paths.values())
                store.upsert_row(row, **paths)
                result.upserts += 1

        cursor = page["next_cursor"]
        store.set_cursor(cursor)
        result.pages += 1
        result.final_cursor = cursor

        if not page["has_more"]:
            break

    return result
