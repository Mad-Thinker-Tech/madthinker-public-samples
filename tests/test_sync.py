"""Tests for the sync loop wiring client + store together.

These drive the real client and real SQLite store, mocking only the HTTP
transport, so they exercise the full sync behaviour end to end.
"""

from pathlib import Path

from madthinker_export.client import ExportClient
from madthinker_export.store import Store
from madthinker_export.sync import EPOCH, sync
from tests.conftest import FakeResponse, FakeSession

URL = "https://example.supabase.co/functions/v1/tca-catch-reports-export"
KEY = "secret"


def page(rows, next_cursor, has_more):
    return FakeResponse(
        200,
        {
            "rows": rows,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "returned_count": len(rows),
        },
    )


def live(row_id, **extra):
    row = {"id": row_id, "report_id": f"RPT-{row_id}", "deleted_at": None}
    row.update(extra)
    return row


def tombstone(row_id):
    return {"id": row_id, "deleted_at": "2024-05-01T00:00:00Z"}


def build(scripted, db_path):
    session = FakeSession(scripted)
    client = ExportClient(URL, KEY, session=session, sleep=lambda _s: None)
    store = Store(db_path)
    return client, store, session


def test_pagination_follows_cursor_until_has_more_false(tmp_path):
    client, store, session = build(
        [
            page([live("r1"), live("r2")], "c1", True),
            page([live("r3")], "c2", False),
        ],
        tmp_path / "m.db",
    )
    result = sync(client, store)

    assert store.count_rows() == 3  # all rows, no overlap
    assert store.get_cursor() == "c2"
    assert result.pages == 2
    # first call uses since, second resumes from the first page's cursor
    assert session.calls[0]["params"]["since"] == EPOCH
    assert "cursor" not in session.calls[0]["params"]
    assert session.calls[1]["params"]["cursor"] == "c1"


def test_first_run_sends_epoch_since(tmp_path):
    client, store, session = build(
        [page([live("r1")], "c1", False)], tmp_path / "m.db"
    )
    sync(client, store)
    assert session.calls[0]["params"]["since"] == EPOCH


def test_tombstone_deletes_live_upserts(tmp_path):
    client, store, _ = build(
        [
            page([live("r1"), live("r2")], "c1", True),
            page([tombstone("r1")], "c2", False),
        ],
        tmp_path / "m.db",
    )
    result = sync(client, store)

    assert store.get_row("r1") is None
    assert store.get_row("r2") is not None
    assert store.count_rows() == 1
    assert result.upserts == 2
    assert result.deletes == 1


def test_second_run_resumes_from_saved_cursor(tmp_path):
    db = tmp_path / "m.db"
    client1, store1, _ = build([page([live("r1")], "c1", False)], db)
    sync(client1, store1)
    store1.close()

    # Second run: a fresh store reads the persisted cursor.
    client2, store2, session2 = build([page([live("r2")], "c2", False)], db)
    sync(client2, store2)

    assert session2.calls[0]["params"]["cursor"] == "c1"
    assert "since" not in session2.calls[0]["params"]
    assert store2.get_cursor() == "c2"
    assert store2.count_rows() == 2


def test_upsert_is_idempotent_across_runs(tmp_path):
    db = tmp_path / "m.db"
    client1, store1, _ = build(
        [page([live("r1", species="steelhead")], "c1", False)], db
    )
    sync(client1, store1)
    store1.close()

    client2, store2, _ = build(
        [page([live("r1", species="coho")], "c2", False)], db
    )
    sync(client2, store2)

    assert store2.count_rows() == 1
    assert store2.get_row("r1")["species"] == "coho"


def test_no_photo_download_when_photo_dir_unset(tmp_path):
    photo_url = "https://signed.example/r1.jpg?t=1"
    rows = [live("r1", photo_url=photo_url, head_photo_url=None)]
    session = FakeSession(
        [page(rows, "c1", False)],
        photos={photo_url: FakeResponse(200, content=b"IMG")},
    )
    client = ExportClient(URL, KEY, session=session, sleep=lambda _s: None)
    store = Store(tmp_path / "m.db")

    result = sync(client, store)  # no photo_dir

    assert store.get_row("r1")["photo_path"] is None
    assert result.photos == 0
    # the signed URL was never fetched
    assert all(call["url"] != photo_url for call in session.calls)


def test_downloads_photos_when_photo_dir_set(tmp_path):
    photo_url = "https://signed.example/r1.jpg?t=1"
    rows = [
        live(
            "r1",
            photo_url=photo_url,
            head_photo_url=None,
            photo_urls_expire_at="2024-01-01T01:00:00Z",
        )
    ]
    session = FakeSession(
        [page(rows, "c1", False)],
        photos={photo_url: FakeResponse(200, content=b"IMG")},
    )
    client = ExportClient(URL, KEY, session=session, sleep=lambda _s: None)
    store = Store(tmp_path / "m.db")

    result = sync(client, store, photo_dir=tmp_path / "pics")

    saved = store.get_row("r1")
    assert Path(saved["photo_path"]).read_bytes() == b"IMG"
    assert saved["head_photo_path"] is None
    assert saved["photo_urls_expire_at"] == "2024-01-01T01:00:00Z"
    assert result.photos == 1


def test_tombstoned_rows_skip_photo_download(tmp_path):
    session = FakeSession([page([tombstone("r1")], "c1", False)])
    client = ExportClient(URL, KEY, session=session, sleep=lambda _s: None)
    store = Store(tmp_path / "m.db")

    result = sync(client, store, photo_dir=tmp_path / "pics")

    assert result.deletes == 1
    assert result.photos == 0
