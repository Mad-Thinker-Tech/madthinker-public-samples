"""Tests for the command-line entry point and its exit codes."""

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
