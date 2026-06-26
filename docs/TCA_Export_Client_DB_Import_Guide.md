# MadThinker Export - Client Database Import Guide

How to set up a consumer database to mirror MadThinker catch reports, and a
ready-to-use prompt for generating the import mechanism in a client's repo.

Companion to `TCA_Export_SDK_API_Reference.md` (the API contract). Read that
first - this guide is about the *receiving* side.

---

## What you are building

A small, repeatable pipeline:

```
MadThinker export endpoint  --(SDK pull loop)-->  your import job  -->  your database
                                                       |
                                              saves a cursor so the
                                              next run only pulls changes
```

You need three things in your database:

1. A **mirror table** that matches the export row shape (primary key = `id`).
2. A **sync-state table** holding the single cursor string between runs.
3. An **import job** that runs the SDK loop: pull a page, upsert/delete each row,
   save the cursor, repeat while `has_more`.

---

## 1. Target schema (Postgres / Supabase)

The `catch_reports` column definitions are the source of truth in
**[TCA_Export_Reference.md — Paste-ready mirror schema](TCA_Export_Reference.md#paste-ready-mirror-schema)**,
which has a ready-to-run Postgres `catch_reports` table (and a SQLite variant).
Create that table, then add the two helpers this guide uses:

```sql
-- Single-row cursor store for incremental sync.
create table if not exists sync_state (
  key   text primary key,
  value text
);
```

This guide differs from the canonical schema in two optional ways, if you prefer:

- Add a local `imported_at timestamptz not null default now()` bookkeeping
  column to `catch_reports`.
- Model photos as a **separate table** instead of the inline `photo_path` /
  `head_photo_path` columns. Either way, never store the API's signed
  `photo_url` — it expires in ~1 hour.

```sql
-- Optional alternative to inline photo path columns.
create table if not exists catch_report_photos (
  catch_report_id uuid references catch_reports(id) on delete cascade,
  kind            text check (kind in ('body','head')),
  storage_path    text,                   -- path in YOUR storage
  downloaded_at   timestamptz not null default now(),
  primary key (catch_report_id, kind)
);
```

---

## 2. Upsert and delete

The column lists below must match your schema; if they ever drift, reconcile
against [TCA_Export_Reference.md](TCA_Export_Reference.md#the-exported-table--every-field).
For each row in a page:

```sql
-- Live row (deleted_at is null): upsert by id.
insert into catch_reports (
  id, report_id, angler_member_id, species, length_inches, fork_length_inches,
  girth_inches, river, latitude, longitude, sex, lifecycle_stage, marks,
  hatchery, floy_id, pit_id, scale_envelope_id, fin_envelope_id,
  caught_at, uploaded_at, updated_at, deleted_at
) values (
  :id, :report_id, :angler_member_id, :species, :length_inches, :fork_length_inches,
  :girth_inches, :river, :latitude, :longitude, :sex, :lifecycle_stage, :marks,
  :hatchery, :floy_id, :pit_id, :scale_envelope_id, :fin_envelope_id,
  :caught_at, :uploaded_at, :updated_at, :deleted_at
)
on conflict (id) do update set
  report_id        = excluded.report_id,
  angler_member_id = excluded.angler_member_id,
  species          = excluded.species,
  length_inches    = excluded.length_inches,
  fork_length_inches = excluded.fork_length_inches,
  girth_inches     = excluded.girth_inches,
  river            = excluded.river,
  latitude         = excluded.latitude,
  longitude        = excluded.longitude,
  sex              = excluded.sex,
  lifecycle_stage  = excluded.lifecycle_stage,
  marks            = excluded.marks,
  hatchery         = excluded.hatchery,
  floy_id          = excluded.floy_id,
  pit_id           = excluded.pit_id,
  scale_envelope_id = excluded.scale_envelope_id,
  fin_envelope_id  = excluded.fin_envelope_id,
  caught_at        = excluded.caught_at,
  uploaded_at      = excluded.uploaded_at,
  updated_at       = excluded.updated_at,
  deleted_at       = excluded.deleted_at,
  imported_at      = now();

-- Tombstoned row (deleted_at is set): hard-delete...
delete from catch_reports where id = :id;
-- ...or soft-delete instead, if you prefer to keep history:
-- update catch_reports set deleted_at = :deleted_at, imported_at = now() where id = :id;
```

## 3. Cursor handling

```sql
-- read
select value from sync_state where key = 'export_cursor';

-- write (after each successful page)
insert into sync_state (key, value) values ('export_cursor', :cursor)
on conflict (key) do update set value = excluded.value;
```

First run: there is no cursor, so call with `since=1970-01-01T00:00:00Z`. Every
run after that: call with the saved cursor.

## 4. Photos

If you need the images, download `photo_url` / `head_photo_url` **inside the same
loop iteration that returned the row** (they expire in ~1 hour), store the bytes
in your own storage, and record the path in `catch_report_photos`. Do not persist
the signed URL. If a URL has already expired, re-pull the row to get a fresh one.

## 5. Scheduling

Run the import job every 15 minutes to hourly (cron, a Supabase scheduled
function, an AWS EventBridge timer, etc.). Within a single run, keep calling while
`has_more` is `true` so a backfill completes in one pass.

---

## Example prompt - generate the import mechanism in a client repo

Paste the block below into a coding-agent session (e.g. Claude Code) whose working
directory is the client's repo. It assumes the MadThinker SDK is available (as a
dependency, a vendored copy, or this repo's `TCA_Export_SDK_API_Reference.md`
checked in alongside). Adjust the two bracketed lines for the client's stack.

---

> You are setting up a **consumer pipeline** that mirrors MadThinker catch reports
> into this repo's database. The MadThinker SDK / API reference is available here:
> **[point to it: the `madthinker_export` package, or `docs/TCA_Export_SDK_API_Reference.md`]**.
> The target database is **[name it: e.g. a Supabase Postgres project / a local SQLite sample]**.
>
> Read the API reference first and treat it as the contract - do not invent fields
> or parameters. Then build the following, using test-driven development, and verify
> before claiming anything works.
>
> **Deliverables:**
> 1. A **schema migration** creating: a `catch_reports` mirror table whose columns
>    match the 22 data fields of the export row (`id` is the primary key), a
>    `sync_state` key/value table for the cursor, and - only if photos are in scope -
>    a `catch_report_photos` table recording locally-stored image paths. Do NOT add
>    columns for the signed photo URLs; they are ephemeral.
> 2. An **import job** that runs the export loop exactly as specified in the
>    reference: read saved cursor (first run uses `since=1970-01-01T00:00:00Z`,
>    later runs use the saved `cursor`); for each row, upsert by `id` when
>    `deleted_at` is null and delete/soft-delete by `id` when it is set; save
>    `next_cursor` after each page; continue while `has_more` is true. Use the SDK's
>    client for the HTTP + cursor if available; otherwise implement the call against
>    the contract.
> 3. **Photo handling** (if in scope): download `photo_url` / `head_photo_url`
>    within the same iteration that returned the row (the URLs expire in ~1 hour),
>    store the bytes in this project's storage, and record the path. Never persist
>    the signed URL.
> 4. **Idempotent + crash-safe behavior:** re-running applies the same row as a
>    no-op change; a crash mid-run resumes from the last saved cursor with no data
>    loss. Respect the error rules: 401/400 are caller faults (clear message, exit
>    non-zero, no retry); 429 backs off (server allows 60 req/min); 5xx retries with
>    exponential backoff + jitter against the same cursor.
> 5. **Tests** with the HTTP boundary mocked (run with no key and no network):
>    pagination follows `next_cursor` and stops on `has_more=false` with no row
>    overlap; a tombstoned row deletes the local copy; the cursor persists and a
>    second run resumes from it; an upsert applied twice leaves one updated row;
>    401/400/429/5xx map to the right handling.
> 6. A short **README** section: required env vars (`MT_EXPORT_API_URL`,
>    `MT_EXPORT_API_KEY` - the key is delivered out-of-band and kept secret), how to
>    run the import once, and how to schedule it.
>
> **Constraints:** secrets come only from the environment, never hardcoded or
> committed. Match this repo's existing language, framework, and migration tooling.
> Keep dependencies minimal. Seed a small **sample database** so a reviewer can run
> the importer end-to-end against a real key and see rows land, then run the tests
> green.

---

## Notes for whoever you hand this to

- The API key and endpoint URL are delivered separately and are secret. They go in
  the environment (`MT_EXPORT_API_KEY`, `MT_EXPORT_API_URL`), never in the repo.
- The mirror's primary key is MadThinker's `id`. That is what makes upserts and
  delete-propagation work.
- Start with a backfill (`since=1970-01-01T00:00:00Z`) into the sample database to
  confirm the whole loop, then switch to the saved-cursor cadence.
