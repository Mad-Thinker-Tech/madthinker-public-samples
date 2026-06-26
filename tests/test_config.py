"""Tests for environment-driven configuration."""

import pytest

from madthinker_export.config import Config, ConfigError

URL = "https://example.supabase.co/functions/v1/tca-catch-reports-export"


def base_env(**overrides):
    env = {"MT_EXPORT_API_URL": URL, "MT_EXPORT_API_KEY": "secret"}
    env.update(overrides)
    return env


def test_reads_url_and_key():
    cfg = Config.from_env(base_env())
    assert cfg.api_url == URL
    assert cfg.api_key == "secret"


def test_missing_url_raises_with_var_name():
    with pytest.raises(ConfigError) as exc:
        Config.from_env({"MT_EXPORT_API_KEY": "secret"})
    assert "MT_EXPORT_API_URL" in str(exc.value)


def test_missing_key_raises_with_var_name():
    with pytest.raises(ConfigError) as exc:
        Config.from_env({"MT_EXPORT_API_URL": URL})
    assert "MT_EXPORT_API_KEY" in str(exc.value)


def test_default_db_path():
    assert Config.from_env(base_env()).db_path == "catch_reports.db"


def test_custom_db_path():
    cfg = Config.from_env(base_env(MT_EXPORT_DB_PATH="/tmp/mine.db"))
    assert cfg.db_path == "/tmp/mine.db"


def test_default_limit_is_1000():
    assert Config.from_env(base_env()).limit == 1000


def test_custom_limit_parsed_as_int():
    assert Config.from_env(base_env(MT_EXPORT_LIMIT="500")).limit == 500


def test_non_integer_limit_raises():
    with pytest.raises(ConfigError):
        Config.from_env(base_env(MT_EXPORT_LIMIT="lots"))


def test_out_of_range_limit_raises():
    with pytest.raises(ConfigError):
        Config.from_env(base_env(MT_EXPORT_LIMIT="9999"))


def test_default_photo_dir_is_photos():
    # Photos are opt-out: an unset MT_EXPORT_PHOTO_DIR downloads to ./photos.
    assert Config.from_env(base_env()).photo_dir == "photos"


def test_custom_photo_dir():
    cfg = Config.from_env(base_env(MT_EXPORT_PHOTO_DIR="/tmp/pics"))
    assert cfg.photo_dir == "/tmp/pics"


def test_blank_photo_dir_disables_photos():
    # An explicitly blank value opts out of photo download entirely.
    assert Config.from_env(base_env(MT_EXPORT_PHOTO_DIR="")).photo_dir is None
