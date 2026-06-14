"""Download a row's signed photo URLs to local disk.

Each export row may carry ``photo_url`` and ``head_photo_url`` — signed URLs
that expire one hour after the response. They must therefore be downloaded in
the *same* iteration that produced them; after expiry the row has to be
re-pulled for fresh URLs.

Download is best-effort: a row with no photos is skipped, and a single failed
download is reported and skipped rather than aborting the sync. The caller
persists the returned local paths alongside the row.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEFAULT_TIMEOUT = 30

# (row field holding the signed URL, returned path key, filename suffix).
_TARGETS = (
    ("photo_url", "photo_path", ""),
    ("head_photo_url", "head_photo_path", ".head"),
)


def _guess_ext(url: str) -> str:
    """Best-effort image extension from the URL path; default ``.jpg``."""
    path = unquote(urlsplit(url).path)
    ext = os.path.splitext(path)[1]
    return ext if ext else ".jpg"


def download_row_photos(
    row: dict,
    photo_dir: str | Path,
    session,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, str | None]:
    """Download ``row``'s photos into ``photo_dir``.

    Returns ``{"photo_path": ..., "head_photo_path": ...}`` with local file
    paths for any photo that downloaded, and ``None`` for fields that were
    absent or failed.
    """
    paths: dict[str, str | None] = {"photo_path": None, "head_photo_path": None}
    photo_dir = Path(photo_dir)

    for url_field, path_field, suffix in _TARGETS:
        url = row.get(url_field)
        if not url:
            continue
        dest = photo_dir / f"{row['id']}{suffix}{_guess_ext(url)}"
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            photo_dir.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(response.content)
        except Exception as exc:  # best-effort: warn and keep going
            print(f"Warning: failed to download {url_field} for row {row['id']}: {exc}")
            continue
        paths[path_field] = str(dest)

    return paths
