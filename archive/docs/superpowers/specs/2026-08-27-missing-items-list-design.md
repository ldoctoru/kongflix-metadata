# Missing Metadata List — Design

## Purpose

Show the actual list of movies/series (and other library items) with
missing metadata or posters in the web dashboard, not just aggregate
counts, while keeping the existing scheduled/watch scan behavior
completely unchanged.

## Approach

The scanner already has a boolean predicate for "is this item missing
metadata" (`is_missing_metadata`); this feature adds a companion
function describing *why* an item is flagged (missing poster,
overview, or both), and has the scan runner build a full per-item list
alongside the existing aggregate counts. That list reflects only the
most recent scan (per explicit decision) and is stored separately from
the capped 20-entry scan-count history, so that file stays small
regardless of library size. The existing scheduled/manual scan
mechanism, cron handling, and lock-guarded concurrency are untouched —
this is purely additive to what gets recorded and displayed after a
scan runs.

## Components

- `app/scanner.py`
  - `describe_missing_reasons(item: dict) -> list[str]` — returns a
    subset of `["poster", "overview"]` depending on which field(s) are
    missing on the item. `is_missing_metadata` is unchanged in
    signature and behavior; internally it can be expressed as
    `bool(describe_missing_reasons(item))` but this is an
    implementation detail, not a required refactor.

- `app/runner.py`
  - `run_once` builds a new `missing_items: list[dict]` alongside the
    existing `ScanSummary`, one entry per **flagged** item (not only
    the ones actually refreshed this round). Each entry:
    ```python
    {
        "id": str,
        "name": str,
        "type": str,        # Jellyfin's "Type" field, e.g. "Movie", "Series", "Episode"
        "missing": list[str],  # from describe_missing_reasons, e.g. ["poster"]
        "status": str,       # "refreshed" | "failed" | "pending"
    }
    ```
    - `"refreshed"` — within the per-run cap, `refresh_item` succeeded.
    - `"failed"` — within the per-run cap, `refresh_item` raised
      `JellyfinApiError` (mirrors today's `ScanSummary.failures` list;
      the two remain in sync since they're built from the same loop).
    - `"pending"` — beyond `max_refreshes_per_run`, not attempted this
      round (mirrors today's `ScanSummary.skipped` count).
  - `run_once`'s return type changes from `ScanSummary` to a small
    wrapper — a `(ScanSummary, list[dict])` tuple is sufficient; no new
    dataclass is required since nothing else needs to construct or
    compare this pairing.
  - `run_scan_and_record` appends the `ScanSummary`-derived dict to
    `scan_history.json` exactly as today (unchanged shape, so existing
    history entries and the 20-entry cap logic are untouched), and
    separately calls `save_missing_items(missing_items_path, missing_items)`
    to overwrite the current snapshot.

- `app/history.py`
  - `save_missing_items(path: str, items: list[dict]) -> None` —
    overwrites the file at `path` with `items` (no append, no cap —
    every call fully replaces the snapshot).
  - `load_missing_items(path: str) -> list[dict]` — same
    missing/corrupt-file-degrades-to-`[]` behavior as the existing
    `load_history`. (Both can share the same underlying read helper if
    convenient; `load_history` is not renamed or changed.)
  - Snapshot file location: `/logs/missing_items.json` — same volume
    as the existing log file and scan history, so it survives
    container restarts without a new volume.

- `app/web.py`
  - New route `GET /api/missing-items` — returns the current snapshot
    via `load_missing_items`.
  - Dashboard gets a new "Missing metadata" section below the existing
    stat cards: a text input that filters the rendered rows by title
    (client-side, case-insensitive substring match — no new backend
    endpoint or query params needed), and a table with columns Title,
    Type, Missing, Status. Status renders as a small badge (e.g. green
    "Refreshed", red "Failed", gray "Pending"), consistent with the
    existing badge styling used in the scan-history table.

## Data flow

Scan runs (scheduled cron tick or manual "Scan Now" — same
lock-guarded `run_scan_and_record` path as today) → `run_once` returns
both the aggregate `ScanSummary` and the new `missing_items` list →
`run_scan_and_record` appends the summary to `scan_history.json`
(unchanged) and overwrites `missing_items.json` with the new list →
the dashboard's existing polling loop adds a fetch to
`/api/missing-items` and re-renders the filterable table alongside the
status/history sections it already polls.

## Error handling

If a scan fails before completing (e.g. `JellyfinApiError` from
`get_all_items`), `missing_items.json` is left untouched — there is no
new list to report, and showing the last successful scan's real data
beats clearing it to an empty table. `load_missing_items` never raises
on a missing or corrupt file, matching `load_history`'s existing
behavior, so a fresh install shows an empty list rather than an error.

## Testing

- `tests/test_scanner.py`: `describe_missing_reasons` returns `[]` for
  a complete item, `["poster"]`, `["overview"]`, and
  `["poster", "overview"]` for the respective missing-field
  combinations.
- `tests/test_runner.py`: `run_once`'s `missing_items` list marks a
  successfully refreshed item `"refreshed"`, a failed refresh
  `"failed"`, and an item beyond the cap `"pending"` — and that the
  `ScanSummary` counts and the `missing_items` list stay consistent
  (e.g. `len([i for i in missing_items if i["status"] == "failed"])
  == len(summary.failures)`).
- `tests/test_history.py`: `save_missing_items`/`load_missing_items`
  round-trip; a second `save_missing_items` call fully replaces the
  prior contents (no accumulation); corrupt/missing file degrades to
  `[]`.
- `tests/test_web.py`: `GET /api/missing-items` reflects the contents
  of the snapshot file (via a mocked/temp-file path, consistent with
  how `/api/history` is already tested).

## Out of scope

- Cumulative/persistent tracking across scans (explicit decision —
  most-recent-scan-only).
- Server-side pagination or a display cap on the missing-items list
  (explicit decision — show everything, filter client-side).
- Any change to scan scheduling, cron handling, or the per-run refresh
  cap's *behavior* — this feature only adds visibility into what that
  existing behavior already does.
