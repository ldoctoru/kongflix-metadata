# Per-Item Retry — Design

## Purpose

Let the user retry a single failed or pending item directly from the
dashboard's "Missing metadata" table, without needing to trigger a
full library rescan.

## Approach

Add a `POST /api/retry-item/<item_id>` route that re-attempts the
refresh for exactly one item, updates that item's `status` in the
persisted `missing_items.json` snapshot, and returns the new status to
the browser — which patches just that row's badge in place. This is
independent of the scan lock (`AppState.try_start_scan`): it's a
lightweight, single-item operation that doesn't touch scan history or
counts, so it's safe to run even while a scheduled/manual scan is in
progress.

## Components

- `app/runner.py`
  - `retry_item(client: JellyfinClient, missing_items_path: str, item_id: str) -> dict | None`
    — loads the current snapshot via `load_missing_items`, finds the
    entry whose `"id"` matches `item_id`. If none is found, returns
    `None` (item not in the current snapshot — e.g. a newer scan
    already replaced it). Otherwise calls `client.refresh_item(item_id)`;
    on success sets that entry's `"status"` to `"refreshed"`; on
    `JellyfinApiError`, sets `"status"` to `"failed"` and adds an
    `"error"` key with the error message. Writes the full updated list
    back via `save_missing_items(missing_items_path, items)`, and
    returns the updated entry dict.

- `app/web.py`
  - New route `POST /api/retry-item/<item_id>`: calls
    `retry_item(client, missing_items_path, item_id)`. Returns the
    updated entry as JSON with HTTP 200 if found, or
    `{"error": "item not found"}` with HTTP 404 if `retry_item`
    returned `None`.
  - Dashboard: a "Retry" button appears only on rows whose `status` is
    `"failed"` or `"pending"` (not on `"refreshed"` rows). Clicking it
    calls the new endpoint, then finds and replaces the matching entry
    in the in-memory `allMissingItems` array by `id`, and calls
    `renderMissingItems()` again — preserving the current filter text
    and page number, since neither of those change as a side effect of
    a single-item retry.

## Data flow

Click "Retry" → `POST /api/retry-item/<id>` → `retry_item` calls
`client.refresh_item(id)` → updates and persists the one matching
entry in `missing_items.json` → response returns the updated entry →
browser splices the updated entry into `allMissingItems` → the table
re-renders (same page/filter state) with the new status badge; the
Retry button disappears from that row once its status is `"refreshed"`.

## Error handling

- Item not present in the current snapshot (stale page after a newer
  scan ran, or the id was mistyped) → 404; the browser shows a toast
  ("Item not found — try refreshing the page") and leaves the row
  untouched rather than crashing the render.
- `refresh_item` raising `JellyfinApiError` is an **expected** outcome
  here, not a server error — the entry's status becomes `"failed"`
  (persisted) and the response is still HTTP 200, since the retry
  attempt itself completed successfully even though the underlying
  refresh did not.
- No interaction with `AppState`'s scan lock — a retry runs
  concurrently with any in-progress scheduled/manual scan without
  blocking either, and without appearing in scan history (this is not
  a scan, it's a single-item action).

## Testing

- `tests/test_runner.py`: `retry_item` sets `"refreshed"` on a
  successful `client.refresh_item` call and persists it via
  `save_missing_items`; sets `"failed"` plus an `"error"` message on
  `JellyfinApiError`; returns `None` for an `item_id` not present in
  the current snapshot, without calling `refresh_item` or writing any
  file in that case.
- `tests/test_web.py`: `POST /api/retry-item/<id>` returns 200 with
  the updated entry for a known id; returns 404 with
  `{"error": "item not found"}` for an unknown id.

## Out of scope

- Retrying multiple items in one request (bulk retry) — one item per
  call, matching the existing "Scan Now" (full scan) vs. this
  (single-item) split.
- Any change to the scan lock, scan history, or scheduled/watch scan
  behavior.
