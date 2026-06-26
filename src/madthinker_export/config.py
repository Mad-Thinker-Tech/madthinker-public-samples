"""Configuration read from the environment.

Two variables are required and delivered out-of-band:

* ``MT_EXPORT_API_URL`` — the export endpoint URL.
* ``MT_EXPORT_API_KEY`` — the API key sent in the ``x-tca-api-key`` header.

Three are optional:

* ``MT_EXPORT_DB_PATH``  — local SQLite mirror path (default ``catch_reports.db``).
* ``MT_EXPORT_LIMIT``    — page size, 1..5000 (default 1000).
* ``MT_EXPORT_PHOTO_DIR``— folder for downloaded photos. Photos are opt-out:
  unset downloads to ``photos``; set it to a path to choose the folder, or to an
  empty string to skip photo download entirely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .client import DEFAULT_LIMIT, MAX_LIMIT

DEFAULT_DB_PATH = "catch_reports.db"
DEFAULT_PHOTO_DIR = "photos"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    api_url: str
    api_key: str
    db_path: str = DEFAULT_DB_PATH
    limit: int = DEFAULT_LIMIT
    photo_dir: str | None = None

    @classmethod
    def from_env(cls, env: dict | None = None) -> Config:
        env = os.environ if env is None else env

        api_url = env.get("MT_EXPORT_API_URL")
        if not api_url:
            raise ConfigError(
                "MT_EXPORT_API_URL is not set. Point it at the export endpoint, e.g. "
                "https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export"
            )

        api_key = env.get("MT_EXPORT_API_KEY")
        if not api_key:
            raise ConfigError(
                "MT_EXPORT_API_KEY is not set. It holds the value sent in the "
                "x-tca-api-key header and is delivered out-of-band."
            )

        db_path = env.get("MT_EXPORT_DB_PATH") or DEFAULT_DB_PATH

        raw_limit = env.get("MT_EXPORT_LIMIT")
        if raw_limit is None or raw_limit == "":
            limit = DEFAULT_LIMIT
        else:
            try:
                limit = int(raw_limit)
            except ValueError as exc:
                raise ConfigError(
                    f"MT_EXPORT_LIMIT must be an integer, got {raw_limit!r}"
                ) from exc
            if not 1 <= limit <= MAX_LIMIT:
                raise ConfigError(
                    f"MT_EXPORT_LIMIT must be between 1 and {MAX_LIMIT}, got {limit}"
                )

        # Photos are opt-out: unset downloads to DEFAULT_PHOTO_DIR; an explicit
        # empty string disables download; any other value is the target folder.
        raw_photo_dir = env.get("MT_EXPORT_PHOTO_DIR")
        if raw_photo_dir is None:
            photo_dir = DEFAULT_PHOTO_DIR
        else:
            photo_dir = raw_photo_dir or None

        return cls(
            api_url=api_url,
            api_key=api_key,
            db_path=db_path,
            limit=limit,
            photo_dir=photo_dir,
        )
