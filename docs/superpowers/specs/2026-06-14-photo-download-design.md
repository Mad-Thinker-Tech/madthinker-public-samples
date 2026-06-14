# Photo download for the Catch Reports Export reference consumer

**Date:** 2026-06-14
**Status:** Approved

## Goal

A conservation community pulls the catch-reports feed to mirror the data **and the
accompanying photos**. The current sample mirrors the data but ignores photos
entirely. Add the simplest, cleanest way for a customer to also pull photos —
without adding abstraction the sample doesn't need.

## Non-goals (deliberately trimmed for simplicity)

- No typed model classes — keep the existing dict-based row handling.
- No separate "SDK iterator" helper — the sync loop is the iteration.
- No pluggable store / Protocol — SQLite stays the one and only store, cursor
  included.
- Do not store the raw signed URLs — they expire in 1 hour, so a saved URL is
  misleading. Store local file paths instead.

## Design

### Switch: one optional setting

`MT_EXPORT_PHOTO_DIR` (env var, optional).

- Unset → data-only sync, identical to today's behavior.
- Set → during the same `python -m madthinker_export sync` run, each row's photos
  download to that folder **in the same loop pass**, before the signed URLs
  expire.

The headline command does not change. Photos are opt-in via one folder path.

### New module: `photos.py`

`download_row_photos(row, photo_dir, session) -> dict[str, str | None]`

- Downloads `photo_url` → `<id>.jpg`, `head_photo_url` → `<id>.head.jpg` in
  `photo_dir`. Extension derived from the URL path when present, else `.jpg`.
- Rows with `null` photo fields are skipped cleanly (returns `None` paths).
- A single failed download (e.g. expired URL, network error) prints a warning
  and continues — best-effort. It does not abort the sync.
- Returns `{"photo_path": ..., "head_photo_path": ...}` (either may be `None`).

### `store.py`

Add three columns to `catch_reports`:

- `photo_urls_expire_at` — copied from the row (when the URLs were valid until).
- `photo_path` — local file once `photo_url` is downloaded, else `NULL`.
- `head_photo_path` — local file once `head_photo_url` is downloaded, else `NULL`.

`ROW_FIELDS` stays the 16-field export contract used to read row values; the new
columns are mirror-local metadata written alongside the upsert. The raw signed
URL fields (`photo_url`, `head_photo_url`) are **not** stored.

### `sync.py`

When a photo directory is provided, after deciding to upsert a row, call
`download_row_photos` and persist the returned local paths plus
`photo_urls_expire_at`. Count downloaded photos in `SyncResult`. When no photo
directory is provided, behavior is unchanged.

### `config.py` / `__main__.py`

- `Config` gains optional `photo_dir: str | None`, read from `MT_EXPORT_PHOTO_DIR`.
- The CLI wires `photo_dir` into the sync call and reports photos downloaded in
  the completion summary.

## Tests

- Row with photos: files written to disk, paths recorded in the mirror.
- Row with **null photo fields**: skipped cleanly, paths `NULL` (required case).
- Failed/expired download: warning emitted, sync continues, row still upserted.
- Existing data-only tests continue to pass unchanged (photo_dir unset).

## Docs

- `README.md`: document `MT_EXPORT_PHOTO_DIR`, the photo columns, and best-effort
  download behavior.
- `CLAUDE.md`: add `photos.py` to the package file list and note the photo
  columns are part of the now-fixed surface.
