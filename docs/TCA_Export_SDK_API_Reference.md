# MadThinker Catch Reports Export - API Reference

External-facing reference for the MadThinker Catch Reports Export endpoint. This
is the stable contract the SDK implements and that any consumer (e.g. The
Conservation Angler) integrates against. Language-agnostic; the SDK is one
reference implementation of the loop described here.

---

## Model

A **pull** API. MadThinker never pushes to you. Your system calls one endpoint on
a schedule (every 15 minutes to hourly is typical) and stores the returned rows
in your own database.

Each response includes an opaque **cursor**. You save it and pass it back on the
next call, so you never miss a row and never receive a duplicate. The cursor only
advances when you successfully process a response, which makes retries safe.

---

## What you receive out-of-band

Two values are delivered to you through a secure channel (not in this document):

1. **API key** - a secret string shaped like `tca_live_a1b2c3d4...`. Treat it like
   a password. Never commit it; load it from an environment variable or secret store.
2. **Endpoint URL** - the exact URL to call.

The current production endpoint is:

```
https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export
```

The SDK reads both from the environment so neither is hardcoded:

| Env var             | Value                                    |
| ------------------- | ---------------------------------------- |
| `MT_EXPORT_API_URL` | the endpoint URL above                   |
| `MT_EXPORT_API_KEY` | your `tca_live_...` key                  |

The key is sent in the `x-tca-api-key` request header. There is no Supabase JWT
and no `apikey` header involved - the API key alone authenticates you.

---

## Request

```
GET <MT_EXPORT_API_URL>
```

### Headers

```
x-tca-api-key: <your API key>
```

### Query parameters

| Parameter | When                 | Description                                                                                                                  | Example                       |
| --------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| `since`   | First-ever call only | ISO 8601 timestamp. Returns rows updated at/after this time. Use `1970-01-01T00:00:00Z` on the very first call to backfill. | `2026-05-19T00:00:00Z`        |
| `cursor`  | All later calls      | Opaque string from the previous response's `next_cursor`. Pass it back exactly. Takes precedence over `since`.              | `eyJ0cyI6IjIwMjYtMDUtMTk...`  |
| `limit`   | Optional             | Max rows per call. Default `1000`, max `5000`.                                                                              | `1000`                        |

Rule of thumb: pass `since` exactly once (the first call ever), and `cursor` on
every call after that.

---

## Response (200)

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

### Envelope fields

| Field            | Type    | Notes                                                                                          |
| ---------------- | ------- | ---------------------------------------------------------------------------------------------- |
| `rows`           | array   | The page of catch reports. Empty array when nothing has changed.                               |
| `next_cursor`    | string  | Always present, even on an empty final page. Save it and reuse it on the next call.            |
| `has_more`       | boolean | `true` when more rows are waiting. It is `true` exactly when `returned_count == limit`.        |
| `returned_count` | integer | Number of rows in `rows`.                                                                       |

### Row fields (25)

The complete field list — names, types, nullability, and meaning (including
`fork_length_inches`, `girth_inches`, `marks`, `hatchery`, `scale_envelope_id`,
and `fin_envelope_id`) — lives in one place, the source of truth:

➡️ **[TCA_Export_Reference.md — The exported table](TCA_Export_Reference.md#the-exported-table--every-field).**

The sample response above shows the shape; that page defines every field.

---

## The integration loop

This is the whole integration. Run it on a schedule.

1. Read your saved cursor. If you have none, this is your first run.
2. Call the endpoint:
   - First run: `since=1970-01-01T00:00:00Z`.
   - Otherwise: `cursor=<your saved cursor>`.
3. For each row in `rows`:
   - `deleted_at` is `null` -> **upsert** by `id`.
   - `deleted_at` is set -> **delete** (or soft-delete) by `id`.
   - If the row has photos and you want the images, **download the bytes now** (the
     signed URLs expire in ~1 hour).
4. Save `next_cursor`, replacing your previous value.
5. If `has_more` is `true`, go back to step 2 immediately with the new cursor.
   Otherwise you are caught up until the next scheduled run.

---

## Errors

All error bodies are shaped `{ "error": "..." }`.

| Status | Meaning                                              | What to do                                                                 |
| ------ | --------------------------------------------------- | ------------------------------------------------------------------------- |
| `401`  | Missing / wrong / revoked API key                   | Check the `x-tca-api-key` header. Caller fault - do not retry.            |
| `400`  | Bad `since`, bad `cursor`, or `limit` out of range  | Fix the parameter (body explains which). Caller fault - do not retry.     |
| `429`  | Rate limited (default 60 requests/minute)           | Back off and retry.                                                       |
| `5xx`  | Server error on MadThinker's side                   | Retry with the **same** cursor (it only advances on success) - safe.      |

---

## Operational notes

- **Idempotent.** Re-calling with the same cursor returns the same rows. Only the
  signed photo URLs and `photo_urls_expire_at` are regenerated each call; the
  underlying data is identical.
- **Photo URLs are ephemeral.** Do not persist `photo_url` / `head_photo_url` as a
  source of truth - they expire in ~1 hour. Download the image bytes during the
  same sync iteration and store them in your own storage. If a URL has expired,
  re-pull the row (same `since`/`cursor`) to get a fresh one.
- **Backfill.** Your first run (`since=1970-01-01T00:00:00Z`) pulls all history -
  expect several pages; follow `has_more` until it is `false`.
- **No data loss on crash.** Restart from the last saved cursor; nothing is lost.
- **Deletes propagate through the same feed** via `deleted_at` (always `null` in
  Phase 1, but handle it now to stay forward-compatible).

---

## Quick smoke test

Verify your key before writing code:

```bash
curl -H "x-tca-api-key: $MT_EXPORT_API_KEY" \
  "$MT_EXPORT_API_URL?since=1970-01-01T00:00:00Z&limit=10"
```

You should get JSON with up to 10 rows.

---

## Questions / key rotation

Contact Mark Alcazar (mark@madthinkertech.com).
