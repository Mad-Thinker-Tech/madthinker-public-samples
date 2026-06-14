"""Tests for the signed-photo-URL downloader.

The HTTP transport is mocked, so these run with no network: the FakeSession's
``photos`` map serves each signed URL.
"""

from pathlib import Path

from madthinker_export.photos import download_row_photos
from tests.conftest import FakeResponse, FakeSession


def row_with_photos(row_id="r1"):
    return {
        "id": row_id,
        "photo_url": f"https://signed.example/{row_id}.jpg?token=x",
        "head_photo_url": f"https://signed.example/{row_id}-head.jpg?token=y",
        "photo_urls_expire_at": "2024-01-01T01:00:00Z",
    }


def test_downloads_both_photos_to_disk(tmp_path):
    row = row_with_photos("r1")
    session = FakeSession(
        [],
        photos={
            row["photo_url"]: FakeResponse(200, content=b"BODY"),
            row["head_photo_url"]: FakeResponse(200, content=b"HEAD"),
        },
    )

    paths = download_row_photos(row, tmp_path, session)

    assert Path(paths["photo_path"]).read_bytes() == b"BODY"
    assert Path(paths["head_photo_path"]).read_bytes() == b"HEAD"


def test_null_photo_fields_are_skipped(tmp_path):
    row = {
        "id": "r1",
        "photo_url": None,
        "head_photo_url": None,
        "photo_urls_expire_at": None,
    }
    session = FakeSession([])

    paths = download_row_photos(row, tmp_path, session)

    assert paths == {"photo_path": None, "head_photo_path": None}
    assert list(Path(tmp_path).iterdir()) == []  # nothing written
    assert session.calls == []  # nothing fetched


def test_failed_download_warns_and_continues(tmp_path, capsys):
    row = row_with_photos("r1")
    session = FakeSession(
        [],
        photos={
            row["photo_url"]: FakeResponse(403, {"error": "expired"}),
            row["head_photo_url"]: FakeResponse(200, content=b"HEAD"),
        },
    )

    paths = download_row_photos(row, tmp_path, session)

    assert paths["photo_path"] is None  # the failed one stays unset
    assert Path(paths["head_photo_path"]).read_bytes() == b"HEAD"  # the other still lands
    out = capsys.readouterr().out
    assert "r1" in out and "photo_url" in out  # a warning was emitted


def test_only_head_photo_present(tmp_path):
    row = {
        "id": "r2",
        "photo_url": None,
        "head_photo_url": "https://signed.example/r2-head.png?token=z",
        "photo_urls_expire_at": "2024-01-01T01:00:00Z",
    }
    session = FakeSession(
        [], photos={row["head_photo_url"]: FakeResponse(200, content=b"PNGDATA")}
    )

    paths = download_row_photos(row, tmp_path, session)

    assert paths["photo_path"] is None
    head = Path(paths["head_photo_path"])
    assert head.read_bytes() == b"PNGDATA"
    assert head.suffix == ".png"  # extension derived from the URL
