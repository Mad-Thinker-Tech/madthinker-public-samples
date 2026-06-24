# CLAUDE.md

Reference consumer for the MadThinker Catch Reports Export API. Standalone, public-facing example.

- Package: `src/madthinker_export/` — `config` (env), `client` (HTTP + retries), `store` (SQLite), `photos` (signed-URL download), `sync` (loop), `probe` (endpoint diagnostic), `__main__` (CLI).
- Runtime dep is `requests` only; SQLite via stdlib; `pytest` + `ruff` for dev. Python 3.10+.
- TDD: write the failing test first. Unit tests mock the HTTP boundary (see `tests/conftest.py`) and run with no key/network.
- Run tests: `pytest -q`. Lint: `ruff check .`.
- Live run: set `MT_EXPORT_API_URL` + `MT_EXPORT_API_KEY`, then `python -m madthinker_export sync`.
- Photos: set `MT_EXPORT_PHOTO_DIR` to also download signed photo URLs during sync (best-effort, in the same iteration before they expire). The mirror stores `photo_urls_expire_at` + local `photo_path`/`head_photo_path`, never the raw signed URLs.
- API contract and sync loop are fixed — see `README.md` and `client.py`/`sync.py` docstrings before changing behavior.
- CLI commands: `python -m madthinker_export sync` (pull), `show` (print the local mirror; reads only the DB path, no API key required), and `probe` (diagnose `MT_EXPORT_API_URL`: a static check vs the canonical endpoint plus one live GET — 404 means the URL is wrong, 401 means the URL is right but the key is not, 200 means fully validated; tolerates a missing key, no retries).
- Onboarding wrappers (repo root): `config.env` (shared, non-secret settings — committed), `config.env.local` (holds the API key — git-ignored, not tracked; `config.cmd` recreates it on fresh clones), `config.cmd` (Windows setup: checks Python, builds the venv, installs, writes the key into `config.env.local`), `run.cmd` (Windows: loads config, runs sync), `showdata.cmd` (Windows: prints the catch reports in the local mirror). macOS/Linux equivalents are `config.sh`/`run.sh`/`showdata.sh` (same behavior; venv at `.venv/bin/python`; keep them committed with the executable bit). The three-step community flow is download → config → run, with showdata to view the data.
- The API key never goes in a tracked file. `config.env.local` is git-ignored; keep it that way.
- Keep it minimal: do not add tooling, frameworks, or scaffolding beyond the listed files (the Python package files plus the `config.env`/`config.env.local`/`config.cmd`/`run.cmd` wrappers).
