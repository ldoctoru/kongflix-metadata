# Kongflix Metadata (Archived)

> **This project has been archived.** It's superseded by the native
> Jellyfin plugin in [`../plugin/`](../plugin/) — see the
> [top-level README](../README.md) for details. This Docker/Python
> tool is kept here for reference and is no longer maintained.

A small Docker service that scans a Jellyfin server for items missing a
poster image or an overview/plot description, and triggers Jellyfin's own
metadata refresh for those items so its configured providers (TMDb, TVDB,
etc.) can fill in the gaps.

It does not call any external metadata provider itself — it only detects
gaps and asks Jellyfin to re-fetch.

## Setup

1. In Jellyfin, go to **Dashboard → API Keys** and create a new API key.
2. Copy `.env.example` to `.env` and fill in `JELLYFIN_URL` and
   `JELLYFIN_API_KEY`.
3. Build and run:

   ```bash
   docker compose up -d --build
   ```

4. Check logs:

   ```bash
   docker compose logs -f
   ```

   Or read the log file directly at `./logs/metadata-updater.log`.

## Run modes

Set `RUN_MODE` in `.env`:

- `schedule` (default) — scans on a cron schedule (`CRON_SCHEDULE`, default
  `0 3 * * *`), runs once immediately at startup, then on schedule.
- `once` — runs a single scan and exits. Useful for a manual check:

  ```bash
  docker compose run --rm -e RUN_MODE=once kongflix-metadata
  ```

- `watch` — stays running and listens for Jellyfin's `LibraryChanged`
  events, refreshing newly added items as they arrive.

## What counts as "missing metadata"

An item is flagged if it has **no poster image** or **no overview/plot
text**. Genres, external provider IDs, and other fields are not checked.

## Web dashboard

In `schedule` and `watch` modes, a small web dashboard is served on
`WEB_PORT` (default `5689`) — e.g. `http://<host>:5689/`. It shows the
result of the last 20 scans and has a "Scan Now" button to trigger a
manual scan on demand. It also lists every item flagged in the most
recent scan — title, type, what's missing (poster/overview), and
whether it was refreshed, failed, or is still pending (beyond the
per-run cap) — with a text box to filter by title. `once` mode does
not start the dashboard, since the container exits immediately after a
single scan.

Each failed or pending item also has a "Retry" button to re-attempt
just that one item's refresh without running a full scan — the result
is saved immediately, so it persists across page reloads.

A "Clear List" button resets the displayed list (and its persisted
snapshot) on demand, without waiting for or triggering a scan — useful
if the list is stale and you don't want to run a full rescan right
away. In `watch` mode, a hint reminds you that the list only updates
on a full scan (a scheduled tick, in `schedule` mode, or a manual
"Scan Now" click) — `watch` mode itself only reacts to newly added
items and never re-scans the existing library on its own.

The dashboard has no authentication — it's intended for use on a
trusted home network, the same as most other Unraid app UIs.

## Configuration reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `JELLYFIN_URL` | yes | — | Base URL of the Jellyfin server |
| `JELLYFIN_API_KEY` | yes | — | API key from Jellyfin Dashboard → API Keys |
| `RUN_MODE` | no | `schedule` | `schedule` \| `once` \| `watch` |
| `CRON_SCHEDULE` | no | `0 3 * * *` | Cron expression, used only in `schedule` mode |
| `LOG_PATH` | no | `/logs/metadata-updater.log` | Path to the summary log file inside the container |
| `MAX_REFRESHES_PER_RUN` | no | `200` | Caps how many items get a refresh triggered per scan run |
| `WEB_PORT` | no | `5689` | Port the web dashboard listens on (schedule/watch modes only) |

## Unraid

An Unraid Community Applications template is included at
[`unraid-template.xml`](unraid-template.xml), with an icon at
[`icon.svg`](icon.svg). To install manually in Unraid (Docker tab → Add
Container → Template repositories), point Unraid at:

```
https://raw.githubusercontent.com/ldoctoru/kongflix-metadata/main/unraid-template.xml
```

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
