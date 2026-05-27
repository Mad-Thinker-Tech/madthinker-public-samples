"""SQLite local mirror for catch report rows.

The store owns two things:

* ``catch_reports`` — one row per catch report, keyed by the export ``id``.
* ``sync_state`` — a single-row table holding the opaque cursor so a later
  run can resume exactly where the previous one stopped.

Upserts are keyed on ``id`` so replaying the same row is a no-op, and deletes
are issued for tombstoned rows (``deleted_at`` set).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# The 16 fields of the export row contract. ``id`` is the local primary key.
ROW_FIELDS = (
    "id",
    "report_id",
    "angler_member_id",
    "species",
    "length_inches",
    "river",
    "latitude",
    "longitude",
    "sex",
    "lifecycle_stage",
    "floy_id",
    "pit_id",
    "caught_at",
    "uploaded_at",
    "updated_at",
    "deleted_at",
)


class Store:
    """A SQLite-backed mirror of the export feed."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        columns = ",\n            ".join(
            f"{name} TEXT PRIMARY KEY" if name == "id" else f"{name}"
            for name in ROW_FIELDS
        )
        self._conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS catch_reports (
            {columns}
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cursor TEXT
            );
            """
        )
        self._conn.commit()

    # -- cursor state -----------------------------------------------------
    def get_cursor(self) -> str | None:
        row = self._conn.execute(
            "SELECT cursor FROM sync_state WHERE id = 1"
        ).fetchone()
        return row["cursor"] if row else None

    def set_cursor(self, cursor: str) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_state (id, cursor) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET cursor = excluded.cursor
            """,
            (cursor,),
        )
        self._conn.commit()

    # -- rows -------------------------------------------------------------
    def upsert_row(self, row: dict) -> None:
        values = [row.get(field) for field in ROW_FIELDS]
        placeholders = ", ".join("?" for _ in ROW_FIELDS)
        updates = ", ".join(
            f"{field} = excluded.{field}" for field in ROW_FIELDS if field != "id"
        )
        self._conn.execute(
            f"""
            INSERT INTO catch_reports ({", ".join(ROW_FIELDS)})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {updates}
            """,
            values,
        )
        self._conn.commit()

    def delete_row(self, row_id) -> None:
        self._conn.execute("DELETE FROM catch_reports WHERE id = ?", (row_id,))
        self._conn.commit()

    def get_row(self, row_id) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM catch_reports WHERE id = ?", (row_id,)
        ).fetchone()
        return dict(row) if row else None

    def count_rows(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM catch_reports").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
