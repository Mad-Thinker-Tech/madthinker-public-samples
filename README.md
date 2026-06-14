# MadThinker Catch Reports Export — reference consumer

A small, runnable example showing the **correct** way to integrate with the
MadThinker Catch Reports Export API. Clone it, point it at your API key and
endpoint URL, and it builds and maintains a local mirror of catch reports in a
SQLite file.

It is deliberately minimal (`requests` + the Python standard library) and is
meant to read as the canonical integration: opaque cursor handling, idempotent
upserts, tombstone deletes, and retry/backoff on transient errors.

## How it works (pull model)

You poll the export endpoint; it never pushes to you. Each call returns a page
of rows and an **opaque cursor**. You save the cursor and pass it back on the
next call to get only what changed since. The cursor — not a timestamp — is the
source of truth for "where I am," so the mirror stays consistent across runs.

The sync loop:

1. Read the saved cursor from SQLite. None means this is the first run.
2. First run calls with `since=1970-01-01T00:00:00Z`; every later call uses the
   saved cursor (cursor wins over `since`).
3. For each row: `deleted_at` null → upsert by `id`; otherwise delete by `id`
   (tombstone). When photo download is enabled, a live row's signed photo URLs
   are fetched in this same iteration (see [Photos](#photos)).
4. Save the returned `next_cursor`, replacing the previous one.
5. If `has_more` is true, fetch the next page immediately; otherwise stop.

## Prerequisites

The only thing you must install yourself is **Python**. Everything else is
either bundled with Python or installed automatically in [Setup](#setup).

| Dependency | Version | How to get it |
| ---------- | ------- | ------------- |
| **Python** | 3.10 or newer | Install if you don't have it (see below), then verify with `python --version`. |
| **pip** and **venv** | bundled | Ship with Python 3.10+. On Debian/Ubuntu, install via `sudo apt install python3-venv python3-pip`. |
| **SQLite** | bundled | **Nothing to install.** Python's standard library includes the `sqlite3` module and a built-in SQLite engine; the mirror file is created for you. |
| **`requests`** | ≥ 2.28 | The one third-party library. Installed automatically by `pip install -e .` below. |
| **git** | any | Only needed to clone the repo (or download the ZIP from GitHub instead). |

Installing Python 3.10+:

- **Windows:** download from <https://www.python.org/downloads/> and tick
  **"Add python.exe to PATH"** in the installer, or run
  `winget install Python.Python.3.12`.
- **macOS:** `brew install python@3.12`, or the installer from python.org.
- **Linux (Debian/Ubuntu):** `sudo apt install python3 python3-venv python3-pip`.

Verify before continuing (must print 3.10 or higher):

```bash
python --version      # if that's not found, try: python3 --version
```

## Setup

Create an isolated environment and install the package (this also pulls in
`requests`):

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

## Configure

Two environment variables are required; they are **delivered out-of-band — keep
the key secret and never commit it.**

| Variable             | Purpose                                                                 |
| -------------------- | ----------------------------------------------------------------------- |
| `MT_EXPORT_API_URL`  | Export endpoint, e.g. `https://<project>.supabase.co/functions/v1/tca-catch-reports-export` |
| `MT_EXPORT_API_KEY`  | The API key. Sent verbatim in the `x-tca-api-key` request header.       |

Optional:

| Variable            | Default             | Purpose                          |
| ------------------- | ------------------- | -------------------------------- |
| `MT_EXPORT_DB_PATH`   | `catch_reports.db`  | Path to the local SQLite mirror. |
| `MT_EXPORT_LIMIT`     | `1000`              | Page size (1–5000).              |
| `MT_EXPORT_PHOTO_DIR` | _(unset)_           | Folder for downloaded photos. Unset → data only; set → download photos during sync. See [Photos](#photos). |

```bash
export MT_EXPORT_API_URL="https://<project>.supabase.co/functions/v1/tca-catch-reports-export"
export MT_EXPORT_API_KEY="your-key-here"
```

## Run

```bash
python -m madthinker_export sync
```

This writes a SQLite file (`catch_reports.db` by default) containing a
`catch_reports` table and a `sync_state` table holding the cursor. Run it again
later and it resumes from the saved cursor, pulling only new and changed rows.

Exit codes: `0` success, `1` runtime error (auth, bad request, or exhausted
transient retries), `2` misconfiguration.

## Photos

Each row may carry two **signed** photo URLs (`photo_url`, `head_photo_url`)
that expire **one hour** after the response. To also mirror the images, point
`MT_EXPORT_PHOTO_DIR` at a folder:

```bash
export MT_EXPORT_PHOTO_DIR="./photos"
python -m madthinker_export sync
```

The same `sync` run then downloads each live row's photos **in the same
iteration that produced the URLs**, before they expire, writing
`<id>.jpg` and `<id>.head.jpg` (extension derived from the URL). The mirror
records, per row:

- `photo_urls_expire_at` — when the signed URLs were valid until,
- `photo_path` / `head_photo_path` — the local files, or `NULL` if the row had
  no photo or the download was skipped.

The raw signed URLs are **not** stored — they expire, so a saved URL would be
misleading; the local paths are the durable reference.

Download is **best-effort**: a single failed image fetch (e.g. an already-expired
URL) prints a warning and the sync continues. Because a row only reappears in the
feed when it changes, an image missed this way is re-fetched the next time that
row is exported. Leave `MT_EXPORT_PHOTO_DIR` unset for data-only syncs.

## Errors and retries

| Status | Meaning                          | Behavior                                   |
| ------ | -------------------------------- | ------------------------------------------ |
| 401    | Missing/wrong/revoked key        | Caller's fault. Clear message, exit, no retry. |
| 400    | Invalid `cursor`/`since`/`limit` | Caller's fault. Clear message, exit, no retry. |
| 429    | Rate limit (server allows 60/min)| Transient. Exponential backoff + jitter, retry. |
| 5xx / connection error | Server / network         | Transient. Bounded retry (~4) with backoff, then exit nonzero with the last error. |

## Develop and test

The unit tests mock the HTTP boundary, so they run with **no API key and no
network**:

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
