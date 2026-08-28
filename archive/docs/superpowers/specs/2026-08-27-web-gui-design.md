# Web GUI — Design

## Purpose

Add a small web dashboard to the existing Jellyfin metadata updater
container so the user can see the result of the last few scans and
trigger a manual scan on demand, without needing to read `docker logs`.

## Approach

The GUI is a Flask app served from inside the *same* container and image
as the existing scanner — no second container, no second image, no
change to the Unraid install story beyond adding one port. It only starts
in `schedule` and `watch` run modes, since `once` mode is a one-shot
invocation that exits immediately and would have nothing to serve.

The web server runs on a background daemon thread; the existing
scheduler (`BlockingScheduler.start()`) or watch loop
(`listen_for_library_changes`) continues to run, blocking, on the main
thread exactly as it does today. No change to that control flow.

## Components

- `app/history.py`
  - `load_history(path: str) -> list[dict]` — reads the JSON array at
    `path`; returns `[]` if the file doesn't exist or is invalid JSON.
  - `append_history(path: str, entry: dict, max_entries: int = 20) -> None`
    — appends `entry` to the array at `path`, keeping only the most
    recent `max_entries` (drops oldest first), then writes it back.
  - Storage location: `/logs/scan_history.json` — the same volume
    already mounted for the log file, so history survives container
    restarts without a new volume.

- `app/state.py`
  - `AppState` — holds `scanning: bool`, `last_result: dict | None`,
    `last_run_at: str | None` (ISO timestamp), and a `threading.Lock`.
  - `run_scan_and_record(state: AppState, client, max_refreshes_per_run: int, history_path: str) -> None`
    — acquires the lock (non-blocking; if already held, does nothing —
    caller is responsible for checking `state.scanning` first and
    rejecting the request), sets `state.scanning = True`, calls
    `run_once(client, max_refreshes_per_run)`, calls `log_summary`,
    converts the `ScanSummary` to a plain dict, sets
    `state.last_result`/`state.last_run_at`, appends the dict (plus a
    timestamp) to the history file via `append_history`, then sets
    `state.scanning = False` in a `finally` block so a crash mid-scan
    doesn't leave the UI stuck showing "scanning" forever.

- `app/web.py`
  - `create_app(client, state: AppState, max_refreshes_per_run: int, history_path: str) -> Flask` —
    factory function (keeps the app testable without needing a running
    server or real Jellyfin connection).
  - `GET /` — renders a single HTML page (inline template, no separate
    static-asset build step): current status (idle / scanning), the
    most recent scan's summary (scanned/flagged/refreshed/skipped/failed
    counts, last run time), a "Scan Now" button, and a table of the last
    20 history entries. Auto-refreshes via a short `<script>` polling
    `/api/status` every 5 seconds while a scan is in progress.
  - `GET /api/status` — JSON: `{"scanning": bool, "last_result": dict | null, "last_run_at": str | null}`.
  - `GET /api/history` — JSON: list of the persisted history entries.
  - `POST /api/scan` — if `state.scanning` is already `True`, returns
    HTTP 409 with `{"error": "scan already in progress"}`; otherwise
    starts `run_scan_and_record` on a new background thread and returns
    HTTP 202 with `{"started": true}`.

- `app/main.py`
  - For `run_mode in ("schedule", "watch")`: after the existing
    `_wait_for_jellyfin` connectivity check succeeds, start
    `waitress.serve(app, host="0.0.0.0", port=config.web_port)` on a
    `threading.Thread(daemon=True)` before calling `run_schedule`/`run_watch`
    (which continue to block the main thread as today).
  - `run_mode == "once"`: unchanged, no web server.

- `app/config.py`
  - New `Config` field `web_port: int`, loaded from env var `WEB_PORT`,
    default `5689`. Validated as a positive integer in the range
    1-65535; invalid values raise `ConfigError`.

## Data flow

Scheduled cron tick, or a `POST /api/scan` from the dashboard, both
funnel through the same `run_scan_and_record` — there is exactly one
code path that performs a scan and records its result, so the GUI's
"Scan Now" button can never observe different behavior than the
scheduled scan.

```
cron tick ─┐
           ├─► run_scan_and_record ─► run_once ─► ScanSummary
POST /api/scan ─┘                         │
                                           ├─► AppState (in-memory, polled by GUI)
                                           └─► scan_history.json (persisted, survives restart)
```

## Error handling

- If `run_once` itself raises (e.g. `JellyfinApiError` from a Jellyfin
  that went unreachable mid-scan), `run_scan_and_record` catches it,
  records a history entry with an `"error"` field and the exception
  message instead of scan counts, sets `scanning = False` in `finally`,
  and logs the error — the GUI surfaces the failed entry instead of the
  container crashing or the UI hanging on "scanning" forever.
- `POST /api/scan` while a scan is already running never starts a
  second concurrent scan (checked-then-acquire pattern, see `AppState`
  above) — returns 409 instead.
- `load_history` never raises on a missing or corrupt history file — it
  degrades to an empty list, so a fresh install or a manually-edited
  file doesn't crash the dashboard.

## Testing

- `tests/test_history.py`: load returns `[]` for missing/invalid file;
  append adds an entry; append caps at `max_entries`, dropping oldest.
- `tests/test_state.py`: `run_scan_and_record` updates `last_result`/
  `last_run_at` and calls `append_history`; a scan that raises still
  clears `scanning` via `finally` and records an error entry.
- `tests/test_web.py`: using Flask's `test_client()` (no real server
  bound to a port) — `GET /` returns 200; `GET /api/status` reflects
  `AppState`; `GET /api/history` reflects the history file's contents
  (via a mocked/temp-file `history_path`); `POST /api/scan` returns 202
  and starts a scan when idle, returns 409 when `state.scanning` is
  already `True`.

## Packaging

- `requirements.txt`: add `Flask` and `waitress` (production WSGI
  server — avoids running Flask's own development server, which warns
  against production use).
- `Dockerfile`: add `EXPOSE 5689`.
- `docker-compose.yml`: add `ports: ["5689:5689"]`.
- `.env.example` / README configuration table: document `WEB_PORT`
  (default `5689`).
- `unraid-template.xml`: add a `WebUI` field
  (`http://[IP]:[PORT:5689]/`) and a `Config Type="Port"` entry mapping
  container port 5689.

## Out of scope

- Authentication (per explicit decision — relies on trusted LAN/Unraid
  network, consistent with most other Unraid app UIs).
- Editing configuration (`JELLYFIN_URL`, `RUN_MODE`, cron schedule, etc.)
  from the UI — still env-var/restart driven.
- Real-time push updates (WebSockets/SSE) — the dashboard polls
  `/api/status` on a plain interval, which is sufficient for a
  single-user homelab tool with infrequent scans.
