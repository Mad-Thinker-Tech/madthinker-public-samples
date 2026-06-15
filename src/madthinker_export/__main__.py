"""Command-line entry point: ``python -m madthinker_export sync``.

Reads configuration from the environment, runs the sync loop against the live
endpoint, and mirrors rows into a local SQLite file. Exit codes:

* ``0`` — sync completed.
* ``1`` — a runtime error (auth, bad request, or exhausted transient retries).
* ``2`` — misconfiguration (missing/invalid environment variables).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable

from .client import ExportClient, ExportError
from .config import DEFAULT_DB_PATH, Config, ConfigError
from .store import Store
from .sync import sync

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 2

# How many of the most recent rows ``show`` prints.
SHOW_LIMIT = 20


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="madthinker_export",
        description="Mirror MadThinker catch reports into a local SQLite file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Pull new/changed rows since the last run.")
    sub.add_parser("show", help="Print the catch reports in the local mirror.")
    return parser


def main(
    argv: list[str] | None = None,
    env: dict | None = None,
    session=None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    env = os.environ if env is None else env
    args = _build_parser().parse_args(argv)

    # `show` only reads the local mirror, so it needs no API URL or key.
    if args.command == "show":
        return _run_show(env.get("MT_EXPORT_DB_PATH") or DEFAULT_DB_PATH)

    try:
        config = Config.from_env(env)
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return EXIT_CONFIG_ERROR

    if args.command == "sync":
        return _run_sync(config, session=session, sleep=sleep)

    return EXIT_OK  # pragma: no cover - argparse guarantees a known command


def _run_sync(config: Config, *, session, sleep: Callable[[float], None]) -> int:
    client = ExportClient(
        config.api_url,
        config.api_key,
        limit=config.limit,
        session=session,
        sleep=sleep,
    )
    store = Store(config.db_path)
    try:
        result = sync(client, store, photo_dir=config.photo_dir)
    except ExportError as exc:
        print(f"Sync failed: {exc}")
        return EXIT_RUNTIME_ERROR
    finally:
        store.close()

    photos = ""
    if config.photo_dir:
        photos = f" {result.photos} photo(s) saved to {config.photo_dir}."
    print(
        f"Sync complete: {result.pages} page(s), "
        f"{result.upserts} upserted, {result.deletes} deleted.{photos} "
        f"Mirror at {config.db_path}."
    )
    return EXIT_OK


# Columns shown by `show`: (row key, header, width).
_SHOW_COLUMNS = (
    ("caught_at", "CAUGHT AT", 20),
    ("species", "SPECIES", 16),
    ("length_inches", "LENGTH", 7),
    ("river", "RIVER", 18),
    ("photo", "PHOTO", 5),
)


def _run_show(db_path: str) -> int:
    if not os.path.exists(db_path):
        print(f"No mirror found at {db_path}. Run a sync first (run.cmd).")
        return EXIT_OK

    store = Store(db_path)
    try:
        total = store.count_rows()
        rows = store.recent_rows(limit=SHOW_LIMIT)
    finally:
        store.close()

    if total == 0:
        print(f"No catch reports in {db_path} yet. Run a sync first (run.cmd).")
        return EXIT_OK

    print(f"{total} catch report(s) in {db_path}. Showing the {len(rows)} most recent:")
    print()
    print("  ".join(header.ljust(w) for _, header, w in _SHOW_COLUMNS))
    print("  ".join("-" * w for _, _, w in _SHOW_COLUMNS))
    for row in rows:
        print("  ".join(_cell(row, key).ljust(w)[:w] for key, _, w in _SHOW_COLUMNS))
    return EXIT_OK


def _cell(row: dict, key: str) -> str:
    if key == "photo":
        return "yes" if row.get("photo_path") or row.get("head_photo_path") else "-"
    value = row.get(key)
    return "-" if value is None else str(value)


if __name__ == "__main__":
    sys.exit(main())
