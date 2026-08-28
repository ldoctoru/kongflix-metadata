# Jellyfin Metadata Updater — Design

## Purpose

A Dockerized service that scans a Jellyfin library for items missing metadata
(poster image or overview text) and triggers Jellyfin's own metadata refresh
for just those items, so the user doesn't have to manually hunt for
incomplete entries.

## Approach

The service talks only to the Jellyfin REST API — it does not call external
metadata providers (TMDb, TVDB, etc.) directly. Instead it detects gaps and
asks Jellyfin to re-fetch metadata using whatever providers Jellyfin is
already configured with. This avoids needing separate API keys and keeps the
app's logic simple and provider-agnostic.

## Components

- `app/jellyfin_client.py` — thin wrapper over the Jellyfin REST API:
  authentication via API key header, listing items (`GET /Items`,
  recursive, across all library types), triggering a refresh
  (`POST /Items/{Id}/Refresh`), and a WebSocket listener for
  `LibraryChanged` events (`/socket`).
- `app/scanner.py` — missing-metadata detection: an item is flagged if it has
  no `ImageTags.Primary` (poster) OR an empty/missing `Overview`. Works
  uniformly across Movies, Series, Episodes, Music, and any other library
  type returned by Jellyfin.
- `app/main.py` — entrypoint. Reads configuration from environment variables
  and dispatches to one of three runners: `schedule`, `once`, `watch`.
- `Dockerfile` — `python:slim` base image with minimal dependencies
  (`requests`, `apscheduler`, `websocket-client`).
- `docker-compose.yml` — example service definition with environment
  variables and a volume mount for logs.
- `.env.example` — documents required/optional environment variables.

## Run modes

Controlled by `RUN_MODE`:

- **`schedule`** (default) — runs the scan on a cron schedule (`CRON_SCHEDULE`,
  default `0 3 * * *`) using an in-container scheduler. No host cron needed.
- **`once`** — runs a single scan pass and exits. Intended for
  `docker run --rm` / manual invocation.
- **`watch`** — opens a WebSocket connection to Jellyfin and reacts to
  `LibraryChanged` events, scanning/refreshing newly added items as they
  arrive.

## Configuration (environment variables)

| Variable | Required | Default | Description |
|---|---|---|---|
| `JELLYFIN_URL` | yes | — | Base URL of the Jellyfin server |
| `JELLYFIN_API_KEY` | yes | — | API key generated in Jellyfin dashboard |
| `RUN_MODE` | no | `schedule` | `schedule` \| `once` \| `watch` |
| `CRON_SCHEDULE` | no | `0 3 * * *` | Cron expression, used only in `schedule` mode |
| `LOG_PATH` | no | `/logs/metadata-updater.log` | Path to the summary log file |

## Missing-metadata criteria

An item is considered to need a refresh if **either**:
- it has no primary image (`ImageTags.Primary` absent), **or**
- its `Overview` field is empty or missing.

This intentionally excludes secondary gaps (genres, external provider IDs)
to avoid re-triggering refreshes on items that are legitimately sparse but
otherwise fine.

## Refresh call

For each flagged item:

```
POST /Items/{Id}/Refresh
    ?MetadataRefreshMode=FullRefresh
    &ImageRefreshMode=FullRefresh
    &ReplaceAllMetadata=false
    &ReplaceAllImages=false
```

This asks Jellyfin to re-query its configured providers for that item,
without blowing away metadata/images that already exist and are fine.

## Error handling

- **Per-item failures** (API error, timeout, unexpected response shape) are
  logged and the scan continues with the next item — one bad item never
  aborts a run.
- **Connection failure to Jellyfin at startup**: fails fast with a clear log
  message and non-zero exit in `once` mode; retries with exponential backoff
  in `schedule` and `watch` modes (since those are expected to run
  unattended long-term).

## Logging

Each run (scheduled tick, manual `once` run, or watch-triggered refresh)
writes a summary to both stdout (visible via `docker logs`) and a log file
at `LOG_PATH` (mounted to a host volume via `docker-compose.yml`). A summary
includes: items scanned, items flagged, refreshes triggered, and any
failures with their item names/IDs.

## Testing

- Unit tests for the missing-metadata predicate in `scanner.py`, using
  mocked Jellyfin item JSON fixtures (poster present/absent, overview
  present/absent/whitespace-only).
- Unit tests for `jellyfin_client.py` request construction (correct
  endpoint, headers, query params) using mocked HTTP responses.
- Manual smoke test against a real or test Jellyfin instance to validate the
  refresh call actually triggers Jellyfin's provider re-fetch, and that the
  WebSocket listener correctly picks up `LibraryChanged` events.

## Out of scope

- Direct calls to external metadata providers (TMDb, TVDB, Fanart.tv, etc.)
- Webhook/external notifications (log file only, per user preference)
- A web UI — this is a headless background service
