# TCA Catch Reports Export API

This document describes how TCA can pull catch report data from Mad Thinker on a recurring schedule.

---

## Overview

Mad Thinker exposes a single REST endpoint that returns catch reports relevant to TCA. Your system calls this endpoint on a schedule (hourly, every 15 minutes, whatever fits) and stores the rows in your Supabase database.

Each call returns rows that have been created or updated since the last time you called. You hand back a "cursor" value on each call, which tells our system where you left off, so you never miss rows and never get duplicates.

This is a pull model. Mad Thinker does not push to you. You decide the cadence.

---

## What you need from Mad Thinker

Before you can call the API, Mark will send you two things:

1. **API key** (a random string, looks like `tca_live_a1b2c3d4...`). Keep this secret. Treat it like a password.
2. **Endpoint URL** (the exact URL to call).

Both will be delivered through a secure channel.

---

## Endpoint

```
GET https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export
```

### Required headers

```
x-tca-api-key: <your API key>
```

### Query parameters

| Parameter | Required         | Description                                                                                                                                                       | Example                      |
| --------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `since`   | First call only  | ISO 8601 timestamp. Returns rows updated at or after this time. Use `1970-01-01T00:00:00Z` on the very first call to backfill everything.                         | `2026-05-19T00:00:00Z`       |
| `cursor`  | Subsequent calls | An opaque string returned by the previous response in `next_cursor`. Pass this back exactly as received. When you pass `cursor`, you do not need to pass `since`. | `eyJ0cyI6IjIwMjYtMDUtMTk...` |
| `limit`   | Optional         | Max rows to return per call. Default 1000, max 5000.                                                                                                              | `1000`                       |

You will pass `since` only on the very first call ever. After that, you always pass `cursor` from the previous response.

---

## Response shape

```json
{
  "rows": [
    {
      "id": "9f2a...",
      "report_id": "550e8400-...",
      "angler_member_id": "mtsip6385a",
      "species": "Steelhead",
      "length_inches": 24,
      "fork_length_inches": 22.5,
      "girth_inches": 12,
      "river": "Smith River",
      "latitude": 45.5231,
      "longitude": -122.6765,
      "sex": "male",
      "lifecycle_stage": "adult",
      "marks": false,
      "hatchery": false,
      "floy_id": null,
      "pit_id": null,
      "scale_envelope_id": null,
      "fin_envelope_id": null,
      "caught_at": "2026-05-18T14:32:00Z",
      "uploaded_at": "2026-05-18T14:45:12Z",
      "updated_at": "2026-05-18T14:45:12Z",
      "deleted_at": null,
      "photo_url": "https://...supabase.co/storage/v1/object/sign/catch-photos/...?token=...",
      "head_photo_url": null,
      "photo_urls_expire_at": "2026-05-18T15:45:12Z"
    }
  ],
  "next_cursor": "eyJ0cyI6IjIwMjYtMDUtMTk...",
  "has_more": false,
  "returned_count": 1
}
```

### Field notes

For the **complete field list** — every row field with its type, nullability,
and meaning (including `girth_inches`, `scale_envelope_id`, and
`fin_envelope_id`) — see the source of truth:
**[TCA_Export_Reference.md — The exported table](TCA_Export_Reference.md#the-exported-table--every-field).**

A few envelope/behavior notes specific to this walkthrough:

- **`id`**: Unique ID for the catch report on Mad Thinker's side. Use this as your primary key on your end.
- **`deleted_at`**: If populated, this row was deleted on Mad Thinker's side. You should delete it (or mark it deleted) in your database. If `null`, the row is live.
- **`has_more`**: If `true`, there are more rows waiting. Call again immediately with the new `cursor` (no need to wait for your next scheduled run).
- **`next_cursor`**: Pass this back on your next call. Always.
- **`photo_url`** / **`head_photo_url`**: Time-limited signed URLs that **expire 1 hour after the response** — download the image bytes in the same loop iteration in which you pull the row, then store the file path (never the URL).

---

## How to integrate (the loop)

This is the entire integration. Run this on a schedule (cron, supabase scheduled function, AWS Lambda on a timer, etc.).

1. Read your saved cursor from your database. If no cursor yet, this is your first run.
2. Call the endpoint.
   - First run: pass `since=1970-01-01T00:00:00Z`.
   - Subsequent runs: pass `cursor=<your saved cursor>`.
3. For each row in the response:
   - If `deleted_at` is `null`: upsert (insert or update) into your table, matching on `id`.
   - If `deleted_at` is set: delete (or soft-delete) from your table, matching on `id`.
4. Save `next_cursor` to your database, replacing the previous value.
5. If `has_more` is `true`, go back to step 2 immediately (using the new cursor). Otherwise, you're done until the next scheduled run.

---

## Sample code (Python)

This is a complete working example. Drop your API key in, run it, and it will pull all catch reports into a local SQLite file. Adapt it to write to your Supabase instance.

> The table below mirrors the exported row shape. If the fields ever look out of
> date, [TCA_Export_Reference.md](TCA_Export_Reference.md#the-exported-table--every-field)
> is the source of truth — reconcile against it.

```python
import os
import time
import sqlite3
import requests

API_URL = "https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export"
API_KEY = os.environ["TCA_API_KEY"]  # set this in your environment

# Local store for the cursor and the data. Replace with your Supabase logic.
db = sqlite3.connect("tca_catch_reports.db")
db.execute("""
    CREATE TABLE IF NOT EXISTS catch_reports (
        id TEXT PRIMARY KEY,
        report_id TEXT,
        angler_member_id TEXT,
        species TEXT,
        length_inches INTEGER,
        fork_length_inches REAL,
        girth_inches REAL,
        river TEXT,
        latitude REAL,
        longitude REAL,
        sex TEXT,
        lifecycle_stage TEXT,
        marks INTEGER,
        hatchery INTEGER,
        floy_id TEXT,
        pit_id TEXT,
        scale_envelope_id TEXT,
        fin_envelope_id TEXT,
        caught_at TEXT,
        uploaded_at TEXT,
        updated_at TEXT,
        deleted_at TEXT
    )
""")
db.execute("CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT)")
db.commit()


def get_cursor():
    row = db.execute("SELECT value FROM sync_state WHERE key = 'cursor'").fetchone()
    return row[0] if row else None


def save_cursor(cursor):
    db.execute(
        "INSERT INTO sync_state (key, value) VALUES ('cursor', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (cursor,),
    )
    db.commit()


def apply_row(row):
    if row.get("deleted_at"):
        db.execute("DELETE FROM catch_reports WHERE id = ?", (row["id"],))
    else:
        db.execute("""
            INSERT INTO catch_reports VALUES (
                :id, :report_id, :angler_member_id, :species, :length_inches,
                :fork_length_inches, :girth_inches,
                :river, :latitude, :longitude, :sex, :lifecycle_stage,
                :marks, :hatchery,
                :floy_id, :pit_id, :scale_envelope_id, :fin_envelope_id, :caught_at,
                :uploaded_at, :updated_at, :deleted_at
            )
            ON CONFLICT(id) DO UPDATE SET
                species = excluded.species,
                length_inches = excluded.length_inches,
                fork_length_inches = excluded.fork_length_inches,
                girth_inches = excluded.girth_inches,
                river = excluded.river,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                sex = excluded.sex,
                lifecycle_stage = excluded.lifecycle_stage,
                marks = excluded.marks,
                hatchery = excluded.hatchery,
                floy_id = excluded.floy_id,
                pit_id = excluded.pit_id,
                scale_envelope_id = excluded.scale_envelope_id,
                fin_envelope_id = excluded.fin_envelope_id,
                updated_at = excluded.updated_at,
                deleted_at = excluded.deleted_at
        """, row)


def sync():
    cursor = get_cursor()
    params = {"cursor": cursor} if cursor else {"since": "1970-01-01T00:00:00Z"}
    headers = {"x-tca-api-key": API_KEY}

    while True:
        response = requests.get(API_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        for row in data["rows"]:
            apply_row(row)

        save_cursor(data["next_cursor"])
        db.commit()

        print(f"Pulled {data['returned_count']} rows. has_more={data['has_more']}")

        if not data["has_more"]:
            break

        # If more data is waiting, immediately continue with the new cursor.
        params = {"cursor": data["next_cursor"]}


if __name__ == "__main__":
    sync()
```

Run on a schedule with cron, AWS EventBridge, a Supabase scheduled function, or your scheduler of choice. Suggested cadence: every 15 minutes to hourly. Lower is fine.

---

## Quick smoke test (curl)

Before writing any code, verify your API key works:

```bash
curl -H "x-tca-api-key: YOUR_KEY_HERE" \
  "https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export?since=1970-01-01T00:00:00Z&limit=10"
```

You should get back JSON with up to 10 rows.

---

## Error responses

| HTTP status | Meaning                                                                  | What to do                                                                                                     |
| ----------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `401`       | Missing or invalid API key                                               | Check your `x-tca-api-key` header. Contact Mark if the key was rotated.                                        |
| `400`       | Bad request (invalid `since` format, bad `cursor`, `limit` out of range) | Check your parameters. Body will describe the issue.                                                           |
| `429`       | Rate limited                                                             | Wait and retry. Default rate limit is 60 requests per minute.                                                  |
| `5xx`       | Server error on Mad Thinker's side                                       | Retry with the same cursor. The cursor only advances when you save a successful response, so retries are safe. |

All error responses include a JSON body like:

```json
{ "error": "Invalid since parameter. Must be ISO 8601 timestamp." }
```

---

## Operational notes

- **Idempotent**: Re-running the same call with the same cursor returns the same catch-report rows. The `photo_url`, `head_photo_url`, and `photo_urls_expire_at` fields are regenerated on every call (new signed URLs, new expiry) — the underlying data is identical, only the time-limited URLs differ.
- **No data loss on failure**: If your job crashes mid-run, restart with the last saved cursor. Nothing is lost.
- **Backfill**: Your first run with `since=1970-01-01T00:00:00Z` pulls everything. Expect this to take several calls if there's a lot of history (each call returns up to 5000 rows, `has_more` flag tells you when you're caught up).
- **Deletes**: Watch the `deleted_at` field. Mad Thinker deletes propagate through the same feed.

---

## Questions

Contact Mark Alcazar (mark@madthinkertech.com) with any questions, or to request a key rotation.
