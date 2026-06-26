"""Tests for the command-line entry point and its exit codes."""

import os

from madthinker_export.__main__ import main
from madthinker_export.store import Store
from tests.conftest import FakeResponse, FakeSession

URL = "https://example.supabase.co/functions/v1/tca-catch-reports-export"


NO_SLEEP = lambda _seconds: None  # noqa: E731 - keep retry tests instant


def env_for(tmp_path, **overrides):
    env = {
        "MT_EXPORT_API_URL": URL,
        "MT_EXPORT_API_KEY": "secret",
        "MT_EXPORT_DB_PATH": str(tmp_path / "m.db"),
    }
    env.update(overrides)
    return env


def one_page(rows):
    return FakeResponse(
        200,
        {"rows": rows, "next_cursor": "c1", "has_more": False, "returned_count": len(rows)},
    )


def test_sync_mirrors_rows_and_returns_zero(tmp_path):
    env = env_for(tmp_path)
    session = FakeSession([one_page([{"id": "r1", "deleted_at": None}])])

    code = main(["sync"], env=env, session=session, sleep=NO_SLEEP)

    assert code == 0
    assert Store(env["MT_EXPORT_DB_PATH"]).count_rows() == 1


def test_missing_config_returns_nonzero(tmp_path, capsys):
    env = {"MT_EXPORT_API_URL": URL}  # no key
    code = main(["sync"], env=env, session=FakeSession([]), sleep=NO_SLEEP)
    assert code != 0
    assert "MT_EXPORT_API_KEY" in capsys.readouterr().out


def test_auth_error_returns_nonzero(tmp_path, capsys):
    session = FakeSession([FakeResponse(401, {"error": "Unauthorized"})])
    code = main(["sync"], env=env_for(tmp_path), session=session, sleep=NO_SLEEP)
    assert code != 0
    assert "Unauthorized" in capsys.readouterr().out


def test_bad_request_returns_nonzero(tmp_path):
    session = FakeSession([FakeResponse(400, {"error": "Invalid cursor."})])
    code = main(["sync"], env=env_for(tmp_path), session=session, sleep=NO_SLEEP)
    assert code != 0


def test_server_error_exhaustion_returns_nonzero(tmp_path):
    session = FakeSession([FakeResponse(500, {"error": "Internal server error"})] * 10)
    code = main(["sync"], env=env_for(tmp_path), session=session, sleep=NO_SLEEP)
    assert code != 0


def test_show_lists_reports(tmp_path, capsys):
    db = str(tmp_path / "m.db")
    store = Store(db)
    store.upsert_row(
        {
            "id": "r1",
            "species": "chinook",
            "river": "Deschutes",
            "length_inches": 30.5,
            "caught_at": "2024-05-01T12:00:00Z",
            "deleted_at": None,
        }
    )
    store.close()

    code = main(["show"], env={"MT_EXPORT_DB_PATH": db})

    out = capsys.readouterr().out
    assert code == 0
    assert "chinook" in out
    assert "Deschutes" in out
    assert "1" in out  # the count


def test_show_no_database_is_friendly_and_creates_nothing(tmp_path, capsys):
    db = str(tmp_path / "missing.db")
    code = main(["show"], env={"MT_EXPORT_DB_PATH": db})
    out = capsys.readouterr().out
    assert code == 0
    assert "run" in out.lower()  # tells them to sync first
    assert not os.path.exists(db)  # show must not create an empty db


def test_show_empty_database(tmp_path, capsys):
    db = str(tmp_path / "empty.db")
    Store(db).close()  # creates schema, no rows
    code = main(["show"], env={"MT_EXPORT_DB_PATH": db})
    out = capsys.readouterr().out
    assert code == 0
    assert "no catch reports" in out.lower()


def test_show_needs_no_api_key(tmp_path):
    # show works with only a db path — no URL/key configured
    db = str(tmp_path / "m.db")
    Store(db).close()
    assert main(["show"], env={"MT_EXPORT_DB_PATH": db}) == 0


def test_probe_validates_and_returns_zero(tmp_path):
    from madthinker_export.probe import CANONICAL

    env = {"MT_EXPORT_API_URL": CANONICAL, "MT_EXPORT_API_KEY": "k"}
    code = main(["probe"], env=env, session=FakeSession([one_page([])]))
    assert code == 0


def test_probe_wrong_url_returns_runtime_error(capsys):
    env = {
        "MT_EXPORT_API_URL": "https://wrong.supabase.co/functions/v1/catch-reports-export",
        "MT_EXPORT_API_KEY": "k",
    }
    code = main(["probe"], env=env, session=FakeSession([FakeResponse(404, {"message": "no"})]))
    assert code == 1
    assert "STATIC CHECK: FAIL" in capsys.readouterr().out


def test_probe_needs_no_api_key(capsys):
    from madthinker_export.probe import CANONICAL

    env = {"MT_EXPORT_API_URL": CANONICAL}  # no key
    session = FakeSession([FakeResponse(401, {"error": "Unauthorized"})])
    code = main(["probe"], env=env, session=session)
    assert code == 1  # not fully validated, but did not crash on the missing key
    assert "URL RIGHT" in capsys.readouterr().out


def test_probe_missing_url_is_config_error(capsys):
    code = main(["probe"], env={}, session=FakeSession([]))
    assert code == 2
    assert "MT_EXPORT_API_URL" in capsys.readouterr().out


def test_sync_downloads_photos_when_dir_configured(tmp_path, capsys):
    photo_url = "https://signed.example/r1.jpg?t=1"
    photo_dir = tmp_path / "pics"
    env = env_for(tmp_path, MT_EXPORT_PHOTO_DIR=str(photo_dir))
    rows = [{"id": "r1", "deleted_at": None, "photo_url": photo_url, "head_photo_url": None}]
    session = FakeSession(
        [one_page(rows)], photos={photo_url: FakeResponse(200, content=b"IMG")}
    )

    code = main(["sync"], env=env, session=session, sleep=NO_SLEEP)

    assert code == 0
    assert (photo_dir / "r1.jpg").read_bytes() == b"IMG"
    assert "1 photo" in capsys.readouterr().out  # reported in the summary
