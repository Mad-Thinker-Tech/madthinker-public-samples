"""Tests for the SQLite local mirror store."""

from madthinker_export.store import Store


def _row(row_id="r1", **overrides):
    base = {
        "id": row_id,
        "report_id": "RPT-1",
        "angler_member_id": "M-1",
        "species": "steelhead",
        "length_inches": 30.5,
        "river": "Deschutes",
        "latitude": 45.0,
        "longitude": -121.0,
        "sex": "F",
        "lifecycle_stage": "adult",
        "floy_id": "FLOY-1",
        "pit_id": "PIT-1",
        "caught_at": "2024-01-01T00:00:00Z",
        "uploaded_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-03T00:00:00Z",
        "deleted_at": None,
    }
    base.update(overrides)
    return base


def test_cursor_starts_as_none(tmp_path):
    store = Store(tmp_path / "mirror.db")
    assert store.get_cursor() is None


def test_set_and_get_cursor(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.set_cursor("cursor-abc")
    assert store.get_cursor() == "cursor-abc"


def test_set_cursor_replaces_previous(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.set_cursor("cursor-1")
    store.set_cursor("cursor-2")
    assert store.get_cursor() == "cursor-2"


def test_cursor_persists_across_reopen(tmp_path):
    db = tmp_path / "mirror.db"
    Store(db).set_cursor("cursor-persisted")
    assert Store(db).get_cursor() == "cursor-persisted"


def test_upsert_inserts_row(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1", species="chinook"))
    got = store.get_row("r1")
    assert got["species"] == "chinook"
    assert got["length_inches"] == 30.5
    assert store.count_rows() == 1


def test_upsert_is_idempotent(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1"))
    store.upsert_row(_row("r1"))
    assert store.count_rows() == 1


def test_upsert_updates_existing_row(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1", species="steelhead"))
    store.upsert_row(_row("r1", species="coho"))
    assert store.get_row("r1")["species"] == "coho"
    assert store.count_rows() == 1


def test_delete_removes_row(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1"))
    store.delete_row("r1")
    assert store.get_row("r1") is None
    assert store.count_rows() == 0


def test_delete_missing_row_is_noop(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.delete_row("does-not-exist")
    assert store.count_rows() == 0


def test_upsert_records_photo_metadata(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(
        _row("r1", photo_urls_expire_at="2024-01-01T01:00:00Z"),
        photo_path="/photos/r1.jpg",
        head_photo_path="/photos/r1.head.jpg",
    )
    got = store.get_row("r1")
    assert got["photo_urls_expire_at"] == "2024-01-01T01:00:00Z"
    assert got["photo_path"] == "/photos/r1.jpg"
    assert got["head_photo_path"] == "/photos/r1.head.jpg"


def test_upsert_without_photos_leaves_paths_null(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1"))
    got = store.get_row("r1")
    assert got["photo_path"] is None
    assert got["head_photo_path"] is None
    assert got["photo_urls_expire_at"] is None


def test_reupsert_refreshes_photo_paths(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1"), photo_path="/photos/old.jpg")
    store.upsert_row(_row("r1"), photo_path="/photos/new.jpg")
    assert store.get_row("r1")["photo_path"] == "/photos/new.jpg"
    assert store.count_rows() == 1


def test_recent_rows_most_recent_first_and_capped(tmp_path):
    store = Store(tmp_path / "mirror.db")
    store.upsert_row(_row("r1", caught_at="2024-01-01T00:00:00Z"))
    store.upsert_row(_row("r2", caught_at="2024-03-01T00:00:00Z"))
    store.upsert_row(_row("r3", caught_at="2024-02-01T00:00:00Z"))
    rows = store.recent_rows(limit=2)
    assert [r["id"] for r in rows] == ["r2", "r3"]


def test_recent_rows_empty_store(tmp_path):
    store = Store(tmp_path / "mirror.db")
    assert store.recent_rows(limit=10) == []
