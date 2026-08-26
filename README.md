# Kongflix Metadata

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

## Configuration reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `JELLYFIN_URL` | yes | — | Base URL of the Jellyfin server |
| `JELLYFIN_API_KEY` | yes | — | API key from Jellyfin Dashboard → API Keys |
| `RUN_MODE` | no | `schedule` | `schedule` \| `once` \| `watch` |
| `CRON_SCHEDULE` | no | `0 3 * * *` | Cron expression, used only in `schedule` mode |
| `LOG_PATH` | no | `/logs/metadata-updater.log` | Path to the summary log file inside the container |

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
