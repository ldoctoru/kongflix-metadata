# Clear Missing-Items List + Watch-Mode Hint — Design

## Purpose

Address a real usability gap surfaced by a user running `RUN_MODE=watch`:
the "Missing metadata" list only ever reflects the results of the last
*full scan* (a scheduled tick, or a manual "Scan Now" click) — `watch`
mode itself only reacts to newly-added Jellyfin items via websocket and
never re-scans the whole library, so the list can sit stale indefinitely
if the user relies on watch mode alone. This is not a data-corruption bug
(the list already correctly reflects only the most recent full scan, per
existing design) — it's a missing affordance: no way to manually clear a
stale list, and no explanation of why it isn't updating in watch mode.

## Approach

Two additive changes, no change to scan/watch mode behavior itself:

1. A "Clear List" button that empties the missing-items list on demand
   (both the persisted snapshot and the browser view), for when a user
   wants to reset a stale display without waiting for/triggering a scan.
2. A contextual hint shown only in `watch` mode, explaining that the list
   only updates on a full scan and pointing at "Scan Now" as the fix.

## Components

- `app/web.py`
  - New route `POST /api/clear-missing-items`: calls
    `save_missing_items(missing_items_path, [])`, returns
    `{"cleared": true}` with HTTP 200. No interaction with the scan lock
    (mirrors `retry_item`'s independence — this never touches
    `AppState.try_start_scan`), but reuses the same `_missing_items_lock`
    from `app/runner.py` to stay consistent with the read-modify-write
    protection already in place for that file (this is a full overwrite,
    but taking the lock avoids a rare interleaving where a scan's
    concurrent write and a clear could otherwise race in unspecified
    ways).
  - `create_app(...)`'s existing parameters are unchanged — no new
    constructor argument needed, since `missing_items_path` is already
    passed in.
  - Dashboard: a "Clear List" button next to the existing filter input
    in the "Missing metadata" section. Clicking it shows a native
    `confirm()` dialog ("Clear the missing-metadata list? This does not
    affect Jellyfin — it just resets what's shown here until the next
    scan."); on confirm, calls the new endpoint, then sets
    `allMissingItems = []` and re-renders (same in-place-update pattern
    already used elsewhere, no full page reload).
  - A `run_mode` value needs to reach the frontend to show the watch-mode
    hint conditionally. `GET /api/status` gains one new field:
    `"run_mode"` (the `Config.run_mode` value, threaded into `create_app`
    as a new parameter). The dashboard shows a small hint line under the
    "Missing metadata" section title only when `run_mode === "watch"`:
    *"Watch mode only reacts to newly added items — click 'Scan Now' to
    refresh this list."*

- `app/main.py` — pass `config.run_mode` into `create_app(...)` as the
  new parameter.

## Data flow

Click "Clear List" → confirm dialog → `POST /api/clear-missing-items` →
`save_missing_items(path, [])` (lock-protected) → response →
`allMissingItems = []` → re-render shows the existing empty state
("Nothing missing metadata right now.").

Page load / status poll → `GET /api/status` includes `run_mode` →
dashboard shows/hides the watch-mode hint based on that value — no
polling needed beyond the existing status refresh, since `run_mode`
never changes at runtime (it's fixed at container start).

## Error handling

- Clearing is idempotent — clearing an already-empty list is a no-op
  overwrite, not an error.
- No interaction with the scan lock — clearing works regardless of
  whether a scan is in progress (a scan finishing afterward will simply
  repopulate the list with fresh data, same as it always does).

## Testing

- `tests/test_web.py`: `POST /api/clear-missing-items` empties an
  existing snapshot and returns `{"cleared": true}`; `GET /api/status`
  includes the `run_mode` field with the value passed to `create_app`.

## Out of scope

- Changing watch mode to also perform periodic full scans (a real
  alternative fix, but a bigger behavioral change to an existing,
  intentionally-scoped mode — the user asked for a manual clear +
  explanation, not a mode redesign).
- Any change to scheduled/manual scan behavior, the scan lock, or the
  existing "most recent scan only" snapshot semantics.
