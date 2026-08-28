# Exclude Item Types From Scanning — Design

## Purpose

Fix a real false-positive class discovered via user report and root-cause
analysis: items like Season folders (and similarly, BoxSets/collection
folders and music library items) get flagged as "missing metadata" on
every scan even though the gap is either not real (Jellyfin's UI shows a
parent-inherited poster, masking that the Season item's own `ImageTags`
is empty) or not fixable (most metadata providers never supply
season-level overviews). Every scan re-flags these items, calls refresh,
Jellyfin correctly finds nothing new to add, and the cycle repeats
forever — the exact "same results every scan" symptom reported.

## Approach

Let the user configure a list of Jellyfin item `Type` values to exclude
entirely from scanning, applied at the Jellyfin API query level (via
Jellyfin's native `ExcludeItemTypes` parameter on `/Items`) rather than
fetched-then-filtered client-side — faster for large libraries, and
`scanned` counts in the dashboard stay meaningful (excluded items were
never counted as part of the library scan at all, consistent with them
never having been eligible for "missing metadata" in the first place).

## Components

- `app/config.py`
  - New `Config` field `exclude_item_types: list[str]`, loaded from env
    var `EXCLUDE_ITEM_TYPES` (comma-separated string, whitespace around
    each entry stripped, empty entries dropped). Default when the env
    var is unset:
    `"Season,BoxSet,CollectionFolder,Audio,MusicAlbum,MusicArtist"`.
    Setting the env var to an empty string (`EXCLUDE_ITEM_TYPES=`)
    disables exclusion entirely (scans every item type, matching
    today's behavior before this feature).

- `app/jellyfin_client.py`
  - `get_all_items(self, exclude_item_types: list[str] | None = None) -> list[dict]`
    — when `exclude_item_types` is a non-empty list, adds
    `"ExcludeItemTypes": ",".join(exclude_item_types)` to the existing
    request params dict (alongside `Recursive`/`Fields`). When `None` or
    empty, the parameter is omitted entirely (no behavior change from
    today).

- `app/runner.py`
  - `run_once(client, max_refreshes_per_run: int = 200, exclude_item_types: list[str] | None = None) -> tuple[ScanSummary, list]`
    — passes `exclude_item_types` straight through to
    `client.get_all_items(exclude_item_types)`; no other logic changes,
    since exclusion now happens entirely at the Jellyfin API layer.
  - `run_schedule(client, cron_schedule, max_refreshes_per_run, state, history_path, missing_items_path, exclude_item_types=None)`
    — threads the list through to the `run_once` call inside `scan_job`.

- `app/main.py`
  - `once` mode: passes `config.exclude_item_types` into its `run_once(...)` call.
  - `schedule`/`watch` modes: passes `config.exclude_item_types` into the
    `run_schedule(...)` call. `watch` mode is unaffected otherwise — it
    reacts to explicitly newly-added items via websocket, not a scan, so
    an excluded-type item added while watching still gets a single
    refresh call (harmless; this fix targets the repeating-forever scan
    problem specifically, not per-item watch behavior).

## Data flow

`EXCLUDE_ITEM_TYPES` env var → `Config.exclude_item_types` (parsed list)
→ threaded through `run_once`/`run_schedule` → `client.get_all_items`
adds `ExcludeItemTypes` to the Jellyfin API request → Jellyfin never
returns those items in the first place → they never appear in
`scanned`/`flagged` counts or the missing-items list.

## Error handling

- No new error conditions. An invalid/unknown type name in the list is
  harmless — Jellyfin's `ExcludeItemTypes` parameter simply excludes
  types it recognizes and ignores unrecognized strings, so a typo just
  means that particular exclusion doesn't take effect (silently),
  consistent with how Jellyfin's own API behaves for this parameter.

## Testing

- `tests/test_config.py`: default `exclude_item_types` list matches the
  documented default; a custom comma-separated value parses correctly
  (including stripping whitespace and dropping empty entries from
  trailing/double commas); an empty string produces an empty list.
- `tests/test_jellyfin_client.py`: `get_all_items` includes
  `ExcludeItemTypes` in the request params when a non-empty list is
  passed; omits it entirely when `None` or `[]` is passed (existing
  tests calling `get_all_items()` with no argument must continue to
  pass unmodified, confirming the parameter is optional with a
  backward-compatible default).
- `tests/test_runner.py`: `run_once` forwards `exclude_item_types` to
  `client.get_all_items`.

## Out of scope

- Any change to `watch` mode's per-item refresh behavior.
- Per-library-folder exclusion (only item `Type`, not specific Jellyfin
  library/collection names) — out of scope for this fix.
- Retroactively re-evaluating items already in a persisted
  `missing_items.json` snapshot — the next scan naturally drops excluded
  types from the list once this feature is deployed and configured.
