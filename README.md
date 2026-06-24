# MadThinker Catch Reports Export — reference consumer

A small, runnable example showing the **correct** way to integrate with the
MadThinker Catch Reports Export API. Clone it, point it at your API key and
endpoint URL, and it builds and maintains a local mirror of catch reports in a
SQLite file.

It is deliberately minimal (`requests` + the Python standard library) and is
meant to read as the canonical integration: opaque cursor handling, idempotent
upserts, tombstone deletes, and retry/backoff on transient errors.

## Quick start (Windows)

If you just want to pull the data, this is the whole thing — three steps, no
prior Python knowledge needed:

1. **Get the code.** Download this repository as a ZIP from GitHub (green
   **Code** button → **Download ZIP**) and unzip it, or clone it with git.
2. **Run setup.** Open the unzipped folder, then from a command prompt in that
   folder run:

   ```
   config.cmd
   ```

   It checks for Python (and tells you how to install it if it's missing), sets
   everything up, and asks you to paste the API key we emailed you.
3. **Run it.**

   ```
   run.cmd
   ```

   This pulls every catch report into `catch_reports.db` and saves photos into
   the `photos` folder. Run `run.cmd` again any time to fetch what's changed.

To browse what you've pulled at any time, run:

```
showdata.cmd
```

It prints a summary of the catch reports in your local database (no API key
needed — it only reads the file `run.cmd` created).

## Quick start (macOS / Linux)

The same three steps, using the shell scripts instead of the `.cmd` files:

1. **Get the code** — download and unzip the repo, or clone it.
2. **Run setup** from a Terminal in that folder:

   ```bash
   ./config.sh
   ```

   It checks for Python (telling you how to install it if missing), sets
   everything up, and asks you to paste the API key we emailed you.
3. **Run it**, then browse what you pulled:

   ```bash
   ./run.sh
   ./showdata.sh
   ```

If a script won't start, mark them executable once with
`chmod +x config.sh run.sh showdata.sh`.

That's it. The rest of this README is reference detail and the manual commands
the scripts wrap.

## Documentation

Deeper references live in [`docs/`](docs/):

- [**Catch Reports Export API**](docs/TCA_Catch_Reports_Export_API.md) —
  consumer-facing overview of the pull model: endpoint, query parameters, and
  response shape. Start here for the big picture.
- [**SDK / API Reference**](docs/TCA_Export_SDK_API_Reference.md) — the stable,
  language-agnostic endpoint contract this sample implements (headers,
  parameters, errors, paging).
- [**Client Database Import Guide**](docs/TCA_Export_Client_DB_Import_Guide.md) —
  how to mirror the feed into your own Postgres/Supabase database, including a
  target schema and the import-job loop.

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
| `MT_EXPORT_API_URL`  | Export endpoint, e.g. `https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export` |
| `MT_EXPORT_API_KEY`  | The API key. Sent verbatim in the `x-tca-api-key` request header.       |

Optional:

| Variable            | Default             | Purpose                          |
| ------------------- | ------------------- | -------------------------------- |
| `MT_EXPORT_DB_PATH`   | `catch_reports.db`  | Path to the local SQLite mirror. |
| `MT_EXPORT_LIMIT`     | `1000`              | Page size (1–5000).              |
| `MT_EXPORT_PHOTO_DIR` | _(unset)_           | Folder for downloaded photos. Unset → data only; set → download photos during sync. See [Photos](#photos). |

```bash
export MT_EXPORT_API_URL="https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export"
export MT_EXPORT_API_KEY="your-key-here"
```

## Run

```bash
python -m madthinker_export sync
```

This writes a SQLite file (`catch_reports.db` by default) containing a
`catch_reports` table and a `sync_state` table holding the cursor. Run it again
later and it resumes from the saved cursor, pulling only new and changed rows.

To print the catch reports already in the mirror (the cross-platform equivalent
of `showdata.cmd`):

```bash
python -m madthinker_export show
```

Exit codes: `0` success, `1` runtime error (auth, bad request, or exhausted
transient retries), `2` misconfiguration.

## Troubleshooting the connection

If a call fails — especially with a **404 Not Found** — the cause is almost
always a wrong `MT_EXPORT_API_URL`, not the key. Run the probe to find out for
certain:

```bash
python -m madthinker_export probe
```

It runs two checks against the configured URL:

1. **Static** — compares your URL to the canonical endpoint and points out any
   host/path mismatch. Needs no key and no network.
2. **Live** — one request, with the status code localising the fault:

   | Result                | Meaning                                             |
   | --------------------- | --------------------------------------------------- |
   | `URL WRONG` (404)     | No function at this URL — fix `MT_EXPORT_API_URL`.   |
   | `URL RIGHT, KEY WRONG` (401) | Endpoint reached; key missing or invalid.    |
   | `URL RIGHT` (400)     | Endpoint reached; check the request parameters.     |
   | `FULLY VALIDATED` (200) | URL and key both good, response contract matches. |

The probe works even without `MT_EXPORT_API_KEY` set: a correct URL returns
`401` and a wrong URL returns `404`, so the result still tells you whether the
URL is right. Exit codes match the table — `0` only when fully validated.

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
