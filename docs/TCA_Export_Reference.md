# MadThinker Catch Reports Export — Reference

**The one place for the exported table schema and how the API works.** If you
read one document, read this one. The other docs go deeper on specific topics
and link back here for the field list.

---

## How the API works (the whole model, in one page)

It is a **pull** API. MadThinker never pushes to you. Your job is a loop:

1. **You call one endpoint** on a schedule (every 15 min to hourly). MadThinker
   returns a **page** of catch-report rows.
2. **Each response carries a `cursor`** (`next_cursor`). You save it and pass it
   back on the next call, so you only ever get new/changed rows — never a
   duplicate, never a gap.
3. **First call only:** you have no cursor yet, so you ask for everything with
   `since=1970-01-01T00:00:00Z`. Every call after that uses the saved cursor.
4. **For each row:** if `deleted_at` is empty, **upsert** it into your table
   (keyed on `id`); if `deleted_at` is set, **delete** it (it was removed
   upstream).
5. **If `has_more` is true**, call again immediately with the new cursor to get
   the next page. Otherwise you are caught up until the next scheduled run.

Two things that trip people up:

- **Photos are time-limited.** A row may include **signed photo URLs** that stop
  working **~1 hour** after the response. If you want the images, download them
  **in the same loop pass** that returned the row — see
  [Photos](#photos-the-important-part) below.
- **The cursor only advances on success.** So if a call fails, you safely retry
  with the *same* cursor and lose nothing.

### Auth and endpoint

Two values are delivered to you out-of-band (keep the key secret):

| What         | How it is used                                              |
| ------------ | ----------------------------------------------------------- |
| API key      | Sent in the `x-tca-api-key` request header.                 |
| Endpoint URL | The exact URL you `GET`. Production endpoint is below.       |

```
GET https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export
x-tca-api-key: <your key>
```

Query parameters: `since` (first call only), `cursor` (every later call), and
optional `limit` (default 1000, max 5000).

---

## The exported table — every field

This is the complete row shape the endpoint returns: **25 fields**. The three
fields people most often look for — **`girth_inches`, `scale_envelope_id`,
`fin_envelope_id`** — are in the *Measurements* and *Tags & samples* groups
below.

> **Null vs. never-null:** `marks` and `hatchery` are always `true`/`false`
> (they default to `false` upstream). Everything else marked `null?` = yes may
> be absent.

### Identity

| Field              | Type           | Null? | Meaning                                                  |
| ------------------ | -------------- | :---: | -------------------------------------------------------- |
| `id`               | string (uuid)  |  no   | MadThinker's id for the catch report. **Your primary key.** |
| `report_id`        | string (uuid)  |  no   | Client-supplied report id (idempotency key on upload).   |
| `angler_member_id` | string         |  yes  | The angler's member number.                              |

### Measurements

| Field                | Type           | Null? | Meaning                                            |
| -------------------- | -------------- | :---: | -------------------------------------------------- |
| `species`            | string         |  no   | e.g. `Steelhead`, `Atlantic Salmon`.               |
| `length_inches`      | number         |  yes  | Measured length.                                   |
| `fork_length_inches` | number         |  yes  | Manually entered fork length. `null` = not measured. |
| `girth_inches`       | number         |  yes  | **Final confirmed girth.** `null` = not measured.  |

### Location

| Field       | Type   | Null? | Meaning   |
| ----------- | ------ | :---: | --------- |
| `river`     | string |  yes  | River name. |
| `latitude`  | number |  yes  |           |
| `longitude` | number |  yes  |           |

### Biology & research flags

| Field             | Type    | Null? | Meaning                                        |
| ----------------- | ------- | :---: | ---------------------------------------------- |
| `sex`             | string  |  yes  |                                                |
| `lifecycle_stage` | string  |  yes  |                                                |
| `marks`           | boolean |  no   | Researcher flag. Always `true`/`false`.        |
| `hatchery`        | boolean |  no   | Researcher flag. Always `true`/`false`.        |

### Tags & samples

| Field               | Type   | Null? | Meaning                                                       |
| ------------------- | ------ | :---: | ------------------------------------------------------------- |
| `floy_id`           | string |  yes  | Physical Floy tag id.                                         |
| `pit_id`            | string |  yes  | Physical PIT tag id.                                          |
| `scale_envelope_id` | string |  yes  | **Scanned barcode of the scale sample envelope.**            |
| `fin_envelope_id`   | string |  yes  | **Scanned barcode of the fin sample envelope ("fin clip").** |

### Timestamps & lifecycle

| Field         | Type             | Null? | Meaning                                                       |
| ------------- | ---------------- | :---: | ------------------------------------------------------------- |
| `caught_at`   | string (ISO8601) |  no   | When the fish was caught.                                    |
| `uploaded_at` | string (ISO8601) |  no   | When the report reached MadThinker.                          |
| `updated_at`  | string (ISO8601) |  no   | Last change upstream. Drives the cursor ordering.           |
| `deleted_at`  | string (ISO8601) |  yes  | If set, the row was deleted upstream — delete it on your side. |

### Photos (the important part)

| Field                  | Type           | Null? | Meaning                                                            |
| ---------------------- | -------------- | :---: | ----------------------------------------------------------------- |
| `photo_url`            | string         |  yes  | **Signed, time-limited** download URL for the catch photo.        |
| `head_photo_url`       | string         |  yes  | **Signed, time-limited** download URL for the head photo.         |
| `photo_urls_expire_at` | string (ISO8601) |  yes  | When both URLs above stop working (~1 hour after the response).   |

**Do not store `photo_url` / `head_photo_url`.** They expire in ~1 hour, so a
saved URL is worthless. Instead, download the image bytes during the same loop
pass and store *where you put the file*. See the column note below.

---

## Two kinds of columns: response fields vs. your mirror

The 25 fields above are what the **API returns**. What you **store** is almost
the same, with one swap for photos:

- **23 fields you copy straight in** — everything except the two signed URLs
  (you keep `photo_urls_expire_at`).
- **2 signed URL fields you do *not* store** (`photo_url`, `head_photo_url`).
  You use them to download the images, then discard them.
- **2 local columns you add** (`photo_path`, `head_photo_path`) — where *you*
  saved each image, or `NULL` if there was no photo or the download was skipped.

So your mirror table has **25 columns**, just a different 25: the two signed URLs
are replaced by the two local paths.

---

## Paste-ready mirror schema

### Postgres / Supabase

```sql
create table if not exists catch_reports (
  id                  uuid primary key,   -- MadThinker's id = your PK
  report_id           uuid,
  angler_member_id    text,
  species             text,
  length_inches       numeric,
  fork_length_inches  numeric,            -- manually entered fork length
  girth_inches        double precision,   -- final confirmed girth
  river               text,
  latitude            double precision,
  longitude           double precision,
  sex                 text,
  lifecycle_stage     text,
  marks               boolean,            -- never null upstream
  hatchery            boolean,            -- never null upstream
  floy_id             text,
  pit_id              text,
  scale_envelope_id   text,               -- scale sample envelope barcode
  fin_envelope_id     text,               -- fin sample envelope barcode
  caught_at           timestamptz,
  uploaded_at         timestamptz,
  updated_at          timestamptz,
  deleted_at          timestamptz,        -- non-null = deleted upstream
  photo_urls_expire_at timestamptz,       -- when the signed URLs expired
  -- Local-only: where YOU stored each downloaded image (never the signed URL):
  photo_path          text,
  head_photo_path     text
);
```

### SQLite (the local sample uses this)

```sql
CREATE TABLE IF NOT EXISTS catch_reports (
  id                   TEXT PRIMARY KEY,
  report_id            TEXT,
  angler_member_id     TEXT,
  species              TEXT,
  length_inches        REAL,
  fork_length_inches   REAL,
  girth_inches         REAL,
  river                TEXT,
  latitude             REAL,
  longitude            REAL,
  sex                  TEXT,
  lifecycle_stage      TEXT,
  marks                INTEGER,           -- SQLite stores booleans as 1/0
  hatchery             INTEGER,
  floy_id              TEXT,
  pit_id               TEXT,
  scale_envelope_id    TEXT,
  fin_envelope_id      TEXT,
  caught_at            TEXT,
  uploaded_at          TEXT,
  updated_at           TEXT,
  deleted_at           TEXT,
  photo_urls_expire_at TEXT,
  photo_path           TEXT,
  head_photo_path      TEXT
);
```

You also need a one-row **cursor store** so a later run resumes where the last
one stopped (`sync_state(key, value)` or equivalent). See the
[Import Guide](TCA_Export_Client_DB_Import_Guide.md).

---

## Errors

| Status | Meaning                              | What to do                                  |
| ------ | ------------------------------------ | ------------------------------------------- |
| `401`  | Missing / wrong / revoked API key    | Fix the `x-tca-api-key` header. Do not retry. |
| `400`  | Bad `since` / `cursor` / `limit`     | Fix the parameter. Do not retry.            |
| `429`  | Rate limited (60 req/min)            | Back off and retry.                         |
| `5xx`  | Server error upstream                | Retry with the **same** cursor — safe.      |

---

## Go deeper

- **[SDK / API Reference](TCA_Export_SDK_API_Reference.md)** — the precise
  protocol contract: headers, query parameters, the response envelope, paging,
  and error bodies.
- **[Catch Reports Export API](TCA_Catch_Reports_Export_API.md)** — a narrated
  walkthrough with a complete, runnable Python example.
- **[Client Database Import Guide](TCA_Export_Client_DB_Import_Guide.md)** — how
  to mirror the feed into your own Postgres/Supabase database, cursor handling,
  and scheduling.

The **field list and schema on this page are the source of truth.** If another
doc disagrees, this page wins — please file an issue.
