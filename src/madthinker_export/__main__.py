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
from .config import Config, ConfigError
from .store import Store
from .sync import sync

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="madthinker_export",
        description="Mirror MadThinker catch reports into a local SQLite file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Pull new/changed rows since the last run.")
    return parser


def main(
    argv: list[str] | None = None,
    env: dict | None = None,
    session=None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    env = os.environ if env is None else env
    args = _build_parser().parse_args(argv)

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
        result = sync(client, store)
    except ExportError as exc:
        print(f"Sync failed: {exc}")
        return EXIT_RUNTIME_ERROR
    finally:
        store.close()

    print(
        f"Sync complete: {result.pages} page(s), "
        f"{result.upserts} upserted, {result.deletes} deleted. "
        f"Mirror at {config.db_path}."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
