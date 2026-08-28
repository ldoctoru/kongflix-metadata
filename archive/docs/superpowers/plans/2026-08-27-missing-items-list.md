# Missing Metadata List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the actual list of movies/series with missing metadata or posters in the web dashboard (title, type, what's missing, and refresh status), reflecting only the most recent scan, without changing scheduled/watch scan behavior.

**Architecture:** The scanner gains a function describing *why* an item is flagged. `run_once` builds a full per-item list alongside its existing aggregate counts. That list is persisted to its own overwrite-only snapshot file (separate from the capped scan-count history) and exposed via a new API route; the dashboard adds a filterable table for it.

**Tech Stack:** Same as the existing app — Python stdlib `json`, Flask, no new dependencies.

## Global Constraints

- The missing-items list reflects only the most recent scan — it is fully overwritten each scan, never appended/accumulated.
- Each entry shows title, type (Jellyfin's `Type` field), and which field(s) are missing (`poster`, `overview`, or both) — not just a count.
- The dashboard shows the entire list with a client-side text filter — no server-side pagination or display cap.
- Storage is `/logs/missing_items.json` (same volume as the existing log/history files) — no new Docker volume.
- If a scan fails before completing (`JellyfinApiError`), the missing-items snapshot is left untouched — never cleared to empty on a failed scan.
- `load_missing_items` must never raise on a missing or corrupt file — degrade to `[]`, matching the existing `load_history` behavior.
- No change to cron scheduling, the lock-guarded concurrency model, or the per-run refresh cap's behavior — this feature only adds visibility into what that existing behavior already does.

---

## File Structure

- `app/scanner.py` — add `describe_missing_reasons(item: dict) -> list[str]`.
- `app/history.py` — add `save_missing_items(path, items) -> None`, `load_missing_items(path) -> list[dict]`.
- `app/runner.py` — modify `run_once` to also return the per-item list; modify `run_scan_and_record` and `run_schedule` to accept and use a `missing_items_path`.
- `app/web.py` — add `GET /api/missing-items`; modify `create_app` and the scan-thread target to accept `missing_items_path`; add a "Missing metadata" section with a search box to the dashboard template.
- `app/main.py` — compute `missing_items_path` alongside the existing `history_path`; thread it into `create_app`/`run_schedule`; unpack `run_once`'s new tuple return in `once` mode.
- `tests/test_scanner.py`, `tests/test_history.py`, `tests/test_runner.py`, `tests/test_state.py`, `tests/test_web.py` — updated/new tests.

---

### Task 1: Scanner — describe missing reasons

**Files:**
- Modify: `app/scanner.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Consumes: nothing new (same `dict`-shaped Jellyfin item as `is_missing_metadata`).
- Produces: `describe_missing_reasons(item: dict) -> list[str]` — a subset of `["poster", "overview"]`, poster checked first.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scanner.py` (the `make_item` helper already defined at the top of this file is reused as-is):

```python
from app.scanner import describe_missing_reasons


def test_describe_missing_reasons_returns_empty_for_complete_item():
    item = make_item()
    assert describe_missing_reasons(item) == []


def test_describe_missing_reasons_flags_poster_only():
    item = make_item(ImageTags={})
    assert describe_missing_reasons(item) == ["poster"]


def test_describe_missing_reasons_flags_overview_only():
    item = make_item(Overview="")
    assert describe_missing_reasons(item) == ["overview"]


def test_describe_missing_reasons_flags_both():
    item = make_item(ImageTags={}, Overview="")
    assert describe_missing_reasons(item) == ["poster", "overview"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scanner.py -v`
Expected: FAIL with `ImportError: cannot import name 'describe_missing_reasons' from 'app.scanner'`.

- [ ] **Step 3: Write minimal implementation**

Add to `app/scanner.py`:

```python
def describe_missing_reasons(item: dict) -> list[str]:
    reasons = []

    image_tags = item.get("ImageTags") or {}
    if not image_tags.get("Primary"):
        reasons.append("poster")

    overview = item.get("Overview") or ""
    if not overview.strip():
        reasons.append("overview")

    return reasons
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS (11 tests total in this file — 7 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add app/scanner.py tests/test_scanner.py
git commit -m "feat: add describe_missing_reasons to scanner"
```

---

### Task 2: History — missing-items snapshot persistence

**Files:**
- Modify: `app/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: nothing new (stdlib `json` only).
- Produces:
  - `save_missing_items(path: str, items: list) -> None` — fully overwrites the file at `path` with `items` (no append, no cap).
  - `load_missing_items(path: str) -> list` — same missing/corrupt-file-degrades-to-`[]` behavior as `load_history`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_history.py`:

```python
from app.history import load_missing_items, save_missing_items


def test_save_missing_items_creates_file(tmp_path):
    path = str(tmp_path / "missing.json")
    save_missing_items(path, [{"id": "1"}])
    assert load_missing_items(path) == [{"id": "1"}]


def test_save_missing_items_overwrites_not_appends(tmp_path):
    path = str(tmp_path / "missing.json")
    save_missing_items(path, [{"id": "1"}])
    save_missing_items(path, [{"id": "2"}])
    assert load_missing_items(path) == [{"id": "2"}]


def test_load_missing_items_returns_empty_list_when_file_missing(tmp_path):
    path = str(tmp_path / "does-not-exist.json")
    assert load_missing_items(path) == []


def test_load_missing_items_returns_empty_list_on_invalid_json(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("not valid json{{{")
    assert load_missing_items(str(path)) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_history.py -v`
Expected: FAIL with `ImportError: cannot import name 'save_missing_items' from 'app.history'`.

- [ ] **Step 3: Write minimal implementation**

Add to `app/history.py` (after the existing `append_history` function):

```python
def save_missing_items(path: str, items: list) -> None:
    with open(path, "w") as f:
        json.dump(items, f)


def load_missing_items(path: str) -> list:
    return load_history(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_history.py -v`
Expected: PASS (9 tests total in this file — 5 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add app/history.py tests/test_history.py
git commit -m "feat: add missing-items snapshot persistence"
```

---

### Task 3: Runner — run_once produces the per-item list

**Files:**
- Modify: `app/runner.py`
- Modify: `tests/test_runner.py`

**Interfaces:**
- Consumes:
  - `describe_missing_reasons(item: dict) -> list[str]` (Task 1)
  - `find_items_missing_metadata(items: list[dict]) -> list[dict]` (existing)
- Produces: `run_once(client: JellyfinClient, max_refreshes_per_run: int = 200) -> tuple[ScanSummary, list[dict]]` — the return type changes from `ScanSummary` alone to a 2-tuple. Each entry in the second element: `{"id": str, "name": str, "type": str, "missing": list[str], "status": "refreshed" | "failed" | "pending"}`.

This task changes an existing function's return type — every caller and every direct test of `run_once` must be updated in this same task, or the test suite will fail with `too many values to unpack`.

- [ ] **Step 1: Update the existing failing tests first**

Replace the four `run_once`-calling tests in `tests/test_runner.py` with these (same test names, updated bodies — replace them in place, don't duplicate):

```python
def test_run_once_refreshes_only_flagged_items():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Complete", "Type": "Movie", "Overview": "ok", "ImageTags": {"Primary": "x"}},
        {"Id": "2", "Name": "Missing Poster", "Type": "Movie", "Overview": "ok", "ImageTags": {}},
        {"Id": "3", "Name": "Missing Overview", "Type": "Series", "Overview": "", "ImageTags": {"Primary": "x"}},
    ]

    summary, missing_items = run_once(client)

    assert summary.scanned == 3
    assert summary.flagged == 2
    assert summary.refreshed == 2
    assert summary.failures == []
    client.refresh_item.assert_any_call("2")
    client.refresh_item.assert_any_call("3")
    assert client.refresh_item.call_count == 2

    assert len(missing_items) == 2
    by_id = {entry["id"]: entry for entry in missing_items}
    assert by_id["2"] == {"id": "2", "name": "Missing Poster", "type": "Movie", "missing": ["poster"], "status": "refreshed"}
    assert by_id["3"] == {"id": "3", "name": "Missing Overview", "type": "Series", "missing": ["overview"], "status": "refreshed"}


def test_run_once_isolates_per_item_failures():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Bad Item", "Type": "Movie", "Overview": "", "ImageTags": {}},
        {"Id": "2", "Name": "Good Item", "Type": "Movie", "Overview": "", "ImageTags": {}},
    ]

    def refresh_side_effect(item_id):
        if item_id == "1":
            raise JellyfinApiError("boom")

    client.refresh_item.side_effect = refresh_side_effect

    summary, missing_items = run_once(client)

    assert summary.scanned == 2
    assert summary.flagged == 2
    assert summary.refreshed == 1
    assert summary.failures == [("Bad Item", "boom")]

    by_id = {entry["id"]: entry for entry in missing_items}
    assert by_id["1"]["status"] == "failed"
    assert by_id["2"]["status"] == "refreshed"


def test_run_once_with_no_missing_items():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Complete", "Type": "Movie", "Overview": "ok", "ImageTags": {"Primary": "x"}},
    ]

    summary, missing_items = run_once(client)

    assert summary == ScanSummary(scanned=1, flagged=0, refreshed=0, failures=[], skipped=0)
    assert missing_items == []


def test_run_once_caps_refreshes_per_run():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Missing 1", "Type": "Movie", "Overview": "", "ImageTags": {}},
        {"Id": "2", "Name": "Missing 2", "Type": "Movie", "Overview": "", "ImageTags": {}},
        {"Id": "3", "Name": "Missing 3", "Type": "Movie", "Overview": "", "ImageTags": {}},
    ]

    summary, missing_items = run_once(client, max_refreshes_per_run=1)

    assert summary.flagged == 3
    assert summary.refreshed == 1
    assert summary.skipped == 2
    assert client.refresh_item.call_count == 1

    statuses = sorted(entry["status"] for entry in missing_items)
    assert statuses == ["pending", "pending", "refreshed"]


def test_run_once_missing_items_failed_count_matches_summary_failures():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Bad Item", "Type": "Movie", "Overview": "", "ImageTags": {}},
        {"Id": "2", "Name": "Good Item", "Type": "Movie", "Overview": "", "ImageTags": {}},
    ]

    def refresh_side_effect(item_id):
        if item_id == "1":
            raise JellyfinApiError("boom")

    client.refresh_item.side_effect = refresh_side_effect

    summary, missing_items = run_once(client)

    failed_count = len([entry for entry in missing_items if entry["status"] == "failed"])
    assert failed_count == len(summary.failures)
```

The last test (`test_run_once_missing_items_failed_count_matches_summary_failures`) is new; the four above it replace the existing bodies of the same-named tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 2, got 1)` on each updated test, since `run_once` still returns a bare `ScanSummary`.

- [ ] **Step 3: Write minimal implementation**

In `app/runner.py`, add the import and replace `run_once`:

```python
from app.scanner import describe_missing_reasons, find_items_missing_metadata
```

(replacing the existing `from app.scanner import find_items_missing_metadata` line)

```python
def run_once(client: JellyfinClient, max_refreshes_per_run: int = 200) -> tuple[ScanSummary, list]:
    items = client.get_all_items()
    flagged_items = find_items_missing_metadata(items)

    items_to_refresh = flagged_items[:max_refreshes_per_run]
    pending_items = flagged_items[max_refreshes_per_run:]
    skipped = len(pending_items)

    refreshed = 0
    failures = []
    missing_items = []

    for item in items_to_refresh:
        reasons = describe_missing_reasons(item)
        try:
            client.refresh_item(item["Id"])
            refreshed += 1
            status = "refreshed"
        except JellyfinApiError as error:
            failures.append((item.get("Name", item["Id"]), str(error)))
            status = "failed"
        missing_items.append({
            "id": item.get("Id"),
            "name": item.get("Name", item.get("Id")),
            "type": item.get("Type", "Unknown"),
            "missing": reasons,
            "status": status,
        })

    for item in pending_items:
        missing_items.append({
            "id": item.get("Id"),
            "name": item.get("Name", item.get("Id")),
            "type": item.get("Type", "Unknown"),
            "missing": describe_missing_reasons(item),
            "status": "pending",
        })

    summary = ScanSummary(
        scanned=len(items),
        flagged=len(flagged_items),
        refreshed=refreshed,
        failures=failures,
        skipped=skipped,
    )
    return summary, missing_items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL still — `run_scan_and_record` and `run_schedule` in this same file call `run_once` and will now break on the changed return type. This is expected at this point; Task 4 fixes those call sites. For this step, confirm specifically that the five tests you just wrote/edited pass:

Run: `pytest tests/test_runner.py -v -k "run_once"`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/test_runner.py
git commit -m "feat: run_once returns per-item missing-metadata list"
```

---

### Task 4: Runner — persist the missing-items snapshot on every scan

**Files:**
- Modify: `app/runner.py`
- Modify: `tests/test_runner.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Consumes:
  - `run_once(client, max_refreshes_per_run) -> tuple[ScanSummary, list]` (Task 3)
  - `save_missing_items(path: str, items: list) -> None` (Task 2)
- Produces:
  - `run_scan_and_record(state, client, max_refreshes_per_run: int, history_path: str, missing_items_path: str) -> None` — new required parameter `missing_items_path`.
  - `run_schedule(client: JellyfinClient, cron_schedule: str, max_refreshes_per_run: int, state, history_path: str, missing_items_path: str) -> None` — new required parameter `missing_items_path`, threaded straight through to `run_scan_and_record`.

- [ ] **Step 1: Update the existing failing tests**

In `tests/test_state.py`, update all three `run_scan_and_record(...)` calls to pass a new `missing_items_path` argument, and add one new test. Replace the whole file's content with:

```python
from unittest.mock import MagicMock, patch

from app.jellyfin_client import JellyfinApiError
from app.runner import ScanSummary, run_scan_and_record
from app.state import AppState


def test_try_start_scan_succeeds_when_idle():
    state = AppState()
    assert state.try_start_scan() is True
    assert state.scanning is True


def test_try_start_scan_fails_when_already_scanning():
    state = AppState()
    state.try_start_scan()
    assert state.try_start_scan() is False


def test_run_scan_and_record_updates_state_and_history(tmp_path):
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    state = AppState()
    state.try_start_scan()

    client = MagicMock()
    client.get_all_items.return_value = []

    run_scan_and_record(state, client, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path)

    assert state.scanning is False
    assert state.last_result["scanned"] == 0
    assert state.last_result["flagged"] == 0
    assert state.last_result["refreshed"] == 0
    assert state.last_result["failures"] == []
    assert state.last_result["skipped"] == 0
    assert state.last_result["timestamp"] == state.last_run_at
    assert state.last_run_at is not None

    from app.history import load_history, load_missing_items
    history = load_history(history_path)
    assert len(history) == 1
    assert history[0]["scanned"] == 0
    assert history[0]["timestamp"] == state.last_run_at
    assert load_missing_items(missing_items_path) == []


def test_run_scan_and_record_writes_missing_items_snapshot(tmp_path):
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    state = AppState()
    state.try_start_scan()

    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Missing Poster", "Type": "Movie", "Overview": "ok", "ImageTags": {}},
    ]

    run_scan_and_record(state, client, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path)

    from app.history import load_missing_items
    snapshot = load_missing_items(missing_items_path)
    assert len(snapshot) == 1
    assert snapshot[0]["id"] == "1"
    assert snapshot[0]["status"] == "refreshed"


def test_run_scan_and_record_leaves_missing_items_untouched_on_error(tmp_path):
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")

    from app.history import save_missing_items, load_missing_items
    save_missing_items(missing_items_path, [{"id": "stale", "status": "pending"}])

    state = AppState()
    state.try_start_scan()

    client = MagicMock()
    client.get_all_items.side_effect = JellyfinApiError("unreachable")

    run_scan_and_record(state, client, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path)

    assert state.scanning is False
    assert state.last_result["error"] == "unreachable"
    assert load_missing_items(missing_items_path) == [{"id": "stale", "status": "pending"}]


def test_run_scan_and_record_clears_scanning_flag_on_error(tmp_path):
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    state = AppState()
    state.try_start_scan()

    client = MagicMock()
    client.get_all_items.side_effect = JellyfinApiError("unreachable")

    run_scan_and_record(state, client, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path)

    assert state.scanning is False
    assert state.last_result["error"] == "unreachable"
    assert state.last_result["timestamp"] == state.last_run_at

    from app.history import load_history
    history = load_history(history_path)
    assert len(history) == 1
    assert history[0]["error"] == "unreachable"
    assert history[0]["timestamp"] == state.last_run_at


def test_run_scan_and_record_releases_lock_on_bookkeeping_error(tmp_path):
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    state = AppState()
    state.try_start_scan()

    client = MagicMock()
    client.get_all_items.return_value = []

    with patch("app.runner.append_history", side_effect=RuntimeError("disk full")):
        try:
            run_scan_and_record(state, client, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path)
        except RuntimeError:
            pass

    assert state.scanning is False
    assert state.try_start_scan() is True
```

In `tests/test_runner.py`, update the two `run_schedule(...)` calls (in `test_run_schedule_skips_scan_when_one_already_in_progress` and `test_run_schedule_runs_scan_via_state_when_idle`) to pass a new `missing_items_path` positional argument — find each `run_schedule(client, "0 3 * * *", 200, state, history_path)` call and change it to `run_schedule(client, "0 3 * * *", 200, state, history_path, str(tmp_path / "missing.json"))`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py tests/test_runner.py -v`
Expected: FAIL — `TypeError: run_scan_and_record() missing 1 required positional argument: 'missing_items_path'` (and similarly for `run_schedule`).

- [ ] **Step 3: Write minimal implementation**

In `app/runner.py`, update the import line for history:

```python
from app.history import append_history, save_missing_items
```

(replacing the existing `from app.history import append_history` line)

Replace `run_scan_and_record`:

```python
def run_scan_and_record(state, client, max_refreshes_per_run: int, history_path: str, missing_items_path: str) -> None:
    try:
        missing_items = None
        try:
            summary, missing_items = run_once(client, max_refreshes_per_run)
            log_summary(summary)
            result = dataclasses.asdict(summary)
        except JellyfinApiError as error:
            result = {"error": str(error)}

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result["timestamp"] = timestamp

        state.last_result = result
        state.last_run_at = timestamp
        append_history(history_path, result)

        if missing_items is not None:
            save_missing_items(missing_items_path, missing_items)
    finally:
        state.scanning = False
        state._lock.release()
```

Replace `run_schedule`'s signature and inner `scan_job`:

```python
def run_schedule(client: JellyfinClient, cron_schedule: str, max_refreshes_per_run: int, state, history_path: str, missing_items_path: str) -> None:
    def scan_job():
        if not state.try_start_scan():
            logger.info("skipping scheduled scan: a scan is already in progress")
            return
        run_scan_and_record(state, client, max_refreshes_per_run, history_path, missing_items_path)

    scan_job()

    scheduler = BlockingScheduler()
    minute, hour, day, month, day_of_week = cron_schedule.split()
    scheduler.add_job(
        scan_job,
        "cron",
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )
    scheduler.start()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py tests/test_runner.py -v`
Expected: PASS (all tests in both files).

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/test_state.py tests/test_runner.py
git commit -m "feat: persist missing-items snapshot on every scan"
```

---

### Task 5: Web — missing-items API route and dashboard table

**Files:**
- Modify: `app/web.py`
- Modify: `tests/test_web.py`

**Interfaces:**
- Consumes:
  - `load_missing_items(path: str) -> list` (Task 2)
  - `run_scan_and_record(state, client, max_refreshes_per_run, history_path, missing_items_path)` (Task 4)
- Produces:
  - `create_app(client, state, max_refreshes_per_run: int, history_path: str, missing_items_path: str) -> Flask` — new required parameter.
  - New route `GET /api/missing-items` returning `load_missing_items(missing_items_path)` as JSON.

- [ ] **Step 1: Update the existing failing tests and add new ones**

Replace `tests/test_web.py`'s `make_test_app` helper and add new tests — replace the entire file content with:

```python
import threading
from unittest.mock import MagicMock, patch

from app.state import AppState
from app.web import create_app


def make_test_app(tmp_path, state=None):
    client = MagicMock()
    client.get_all_items.return_value = []
    state = state or AppState()
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    app = create_app(client, state, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path)
    app.config["TESTING"] = True
    return app, client, state, history_path, missing_items_path


def test_index_returns_200(tmp_path):
    app, _, _, _, _ = make_test_app(tmp_path)
    response = app.test_client().get("/")
    assert response.status_code == 200


def test_status_reflects_app_state(tmp_path):
    state = AppState()
    state.last_result = {"scanned": 3}
    state.last_run_at = "2026-01-01T00:00:00+00:00"
    app, _, _, _, _ = make_test_app(tmp_path, state=state)

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    body = response.get_json()
    assert body["scanning"] is False
    assert body["last_result"] == {"scanned": 3}
    assert body["last_run_at"] == "2026-01-01T00:00:00+00:00"


def test_history_endpoint_returns_persisted_entries(tmp_path):
    from app.history import append_history

    app, _, _, history_path, _ = make_test_app(tmp_path)
    append_history(history_path, {"scanned": 1})
    append_history(history_path, {"scanned": 2})

    response = app.test_client().get("/api/history")

    assert response.status_code == 200
    assert response.get_json() == [{"scanned": 1}, {"scanned": 2}]


def test_missing_items_endpoint_returns_snapshot(tmp_path):
    from app.history import save_missing_items

    app, _, _, _, missing_items_path = make_test_app(tmp_path)
    save_missing_items(missing_items_path, [
        {"id": "1", "name": "The Matrix", "type": "Movie", "missing": ["poster"], "status": "refreshed"},
    ])

    response = app.test_client().get("/api/missing-items")

    assert response.status_code == 200
    assert response.get_json() == [
        {"id": "1", "name": "The Matrix", "type": "Movie", "missing": ["poster"], "status": "refreshed"},
    ]


def test_missing_items_endpoint_returns_empty_list_when_no_snapshot_yet(tmp_path):
    app, _, _, _, _ = make_test_app(tmp_path)

    response = app.test_client().get("/api/missing-items")

    assert response.status_code == 200
    assert response.get_json() == []


@patch("app.web.threading.Thread")
def test_post_scan_starts_scan_when_idle(mock_thread_cls, tmp_path):
    app, client, state, _, _ = make_test_app(tmp_path)
    mock_thread = MagicMock()
    mock_thread_cls.return_value = mock_thread

    response = app.test_client().post("/api/scan")

    assert response.status_code == 202
    assert response.get_json() == {"started": True}
    assert state.scanning is True
    mock_thread.start.assert_called_once()


def test_post_scan_returns_409_when_already_scanning(tmp_path):
    state = AppState()
    state.try_start_scan()
    app, _, _, _, _ = make_test_app(tmp_path, state=state)

    response = app.test_client().post("/api/scan")

    assert response.status_code == 409
    assert response.get_json() == {"error": "scan already in progress"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web.py -v`
Expected: FAIL — `TypeError: create_app() missing 1 required positional argument: 'missing_items_path'`.

- [ ] **Step 3: Write minimal implementation**

In `app/web.py`, update the history import:

```python
from app.history import load_history, load_missing_items
```

(replacing the existing `from app.history import load_history` line)

Update `create_app`'s signature and body:

```python
def create_app(client, state: AppState, max_refreshes_per_run: int, history_path: str, missing_items_path: str) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(INDEX_TEMPLATE)

    @app.route("/api/status")
    def status():
        return jsonify({
            "scanning": state.scanning,
            "last_result": state.last_result,
            "last_run_at": state.last_run_at,
        })

    @app.route("/api/history")
    def history():
        return jsonify(load_history(history_path))

    @app.route("/api/missing-items")
    def missing_items():
        return jsonify(load_missing_items(missing_items_path))

    @app.route("/api/scan", methods=["POST"])
    def scan():
        if not state.try_start_scan():
            return jsonify({"error": "scan already in progress"}), 409
        thread = threading.Thread(
            target=run_scan_and_record,
            args=(state, client, max_refreshes_per_run, history_path, missing_items_path),
            daemon=True,
        )
        thread.start()
        return jsonify({"started": True}), 202

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web.py -v`
Expected: PASS (8 tests total in this file — 6 existing + 2 new).

- [ ] **Step 5: Add the dashboard's "Missing metadata" section**

This step adds UI only — no new routes, no test changes (the existing tests only check response codes/JSON, not HTML content, consistent with how the rest of the dashboard is tested).

In `app/web.py`'s `INDEX_TEMPLATE` string, add this CSS to the `<style>` block, right after the existing `.empty-state { ... }` rule:

```css
  .filter-input {
    width: 100%;
    padding: 0.6rem 0.9rem;
    margin-bottom: 0.9rem;
    background: var(--bg-elev-2);
    border: 1px solid var(--border);
    border-radius: 9px;
    color: var(--text);
    font-size: 0.88rem;
  }
  .filter-input::placeholder { color: var(--text-dim); }
  .filter-input:focus { outline: none; border-color: var(--accent); }
  .type-tag {
    font-size: 0.72rem; color: var(--text-dim); background: rgba(156, 153, 184, 0.12);
    padding: 0.1rem 0.45rem; border-radius: 6px;
  }
  .missing-tag {
    display: inline-block; font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 6px;
    background: rgba(139, 127, 214, 0.15); color: var(--accent); margin-right: 0.3rem;
  }
  .badge.status-refreshed { background: rgba(79, 214, 160, 0.15); color: var(--good); }
  .badge.status-failed { background: rgba(232, 105, 125, 0.15); color: var(--bad); }
  .badge.status-pending { background: rgba(156, 153, 184, 0.15); color: var(--text-dim); }
```

In the HTML body, add this new section right after the closing `</div>` of the `history-card` block and before the closing `</div>` of `.wrap`:

```html
  <div class="section-title" style="margin-top: 1.5rem;">Missing metadata</div>
  <input id="missing-filter" class="filter-input" type="text" placeholder="Filter by title...">
  <div class="card history-card">
    <div class="table-scroll">
      <table id="missing-table">
        <thead>
          <tr><th>Title</th><th>Type</th><th>Missing</th><th>Status</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
    <div id="missing-empty" class="empty-state" style="display:none;">Nothing missing metadata right now.</div>
  </div>
```

In the `<script>` block, add this after the existing `refreshHistory` function definition:

```javascript
  let allMissingItems = [];

  function renderMissingItems() {
    const filterValue = document.getElementById("missing-filter").value.trim().toLowerCase();
    const tbody = document.querySelector("#missing-table tbody");
    const empty = document.getElementById("missing-empty");
    const table = document.getElementById("missing-table");
    tbody.innerHTML = "";

    const filtered = filterValue
      ? allMissingItems.filter((item) => item.name.toLowerCase().includes(filterValue))
      : allMissingItems;

    if (!filtered.length) {
      table.style.display = "none";
      empty.style.display = "block";
      return;
    }
    table.style.display = "table";
    empty.style.display = "none";

    for (const item of filtered) {
      const row = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.textContent = item.name;
      row.appendChild(nameCell);

      const typeCell = document.createElement("td");
      const typeTag = document.createElement("span");
      typeTag.className = "type-tag";
      typeTag.textContent = item.type;
      typeCell.appendChild(typeTag);
      row.appendChild(typeCell);

      const missingCell = document.createElement("td");
      for (const reason of item.missing) {
        const tag = document.createElement("span");
        tag.className = "missing-tag";
        tag.textContent = reason;
        missingCell.appendChild(tag);
      }
      row.appendChild(missingCell);

      const statusCell = document.createElement("td");
      const statusBadge = document.createElement("span");
      statusBadge.className = "badge status-" + item.status;
      statusBadge.textContent = item.status;
      statusCell.appendChild(statusBadge);
      row.appendChild(statusCell);

      tbody.appendChild(row);
    }
  }

  async function refreshMissingItems() {
    const res = await fetch("/api/missing-items");
    allMissingItems = await res.json();
    renderMissingItems();
  }
```

Finally, wire up the filter input and initial/periodic refresh by updating the bottom of the `<script>` block from:

```javascript
  refreshStatus();
  refreshHistory();
  setInterval(refreshStatus, 3000);
  setInterval(refreshHistory, 5000);
```

to:

```javascript
  document.getElementById("missing-filter").addEventListener("input", renderMissingItems);

  refreshStatus();
  refreshHistory();
  refreshMissingItems();
  setInterval(refreshStatus, 3000);
  setInterval(refreshHistory, 5000);
  setInterval(refreshMissingItems, 5000);
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: FAIL at this point is expected for tests outside `tests/test_web.py` that still call `create_app`/`run_schedule` with the old signature (Task 6 fixes `app/main.py`, which is the only other caller). Confirm specifically:

Run: `pytest tests/test_web.py tests/test_scanner.py tests/test_history.py tests/test_runner.py tests/test_state.py -v`
Expected: PASS (all tests in these five files).

- [ ] **Step 7: Commit**

```bash
git add app/web.py tests/test_web.py
git commit -m "feat: add missing-items API route and dashboard table"
```

---

### Task 6: Main — wire missing_items_path through the entrypoint

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes:
  - `run_once(client, max_refreshes_per_run) -> tuple[ScanSummary, list]` (Task 3)
  - `create_app(client, state, max_refreshes_per_run, history_path, missing_items_path) -> Flask` (Task 5)
  - `run_schedule(client, cron_schedule, max_refreshes_per_run, state, history_path, missing_items_path)` (Task 4)
- Produces: `main()`'s `once` mode correctly unpacks `run_once`'s new tuple return; `schedule`/`watch` modes compute and pass `missing_items_path` alongside the existing `history_path`.

- [ ] **Step 1: Update the failing tests**

In `tests/test_main.py`, make these targeted edits (do not rewrite the whole file — these are the only lines affected):

1. In `test_main_once_mode_runs_single_scan_and_returns_zero`, change:
   ```python
   mock_run_once.return_value = MagicMock()
   ```
   to:
   ```python
   mock_run_once.return_value = (MagicMock(), [])
   ```

2. In `test_main_once_mode_does_not_start_web_server`, change:
   ```python
   mock_run_once.return_value = MagicMock()
   ```
   to:
   ```python
   mock_run_once.return_value = (MagicMock(), [])
   ```

3. In `test_main_schedule_mode_calls_run_schedule`, add one line after the existing `assert isinstance(call_args.args[4], str)`:
   ```python
   assert isinstance(call_args.args[5], str)
   assert call_args.args[4] != call_args.args[5]
   ```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `TypeError: cannot unpack non-iterable MagicMock object` for the once-mode tests not yet updated in production code, and `IndexError: tuple index out of range` for the schedule-mode test (only 5 positional args currently passed to `run_schedule`).

- [ ] **Step 3: Write minimal implementation**

In `app/main.py`, update the `once` mode branch:

```python
    if config.run_mode == "once":
        try:
            summary, _missing_items = run_once(client, config.max_refreshes_per_run)
        except JellyfinApiError as error:
            logger.error("could not reach Jellyfin: %s", error)
            return 1
        log_summary(summary)
```

(replacing the existing `summary = run_once(client, config.max_refreshes_per_run)` line and keeping everything else in this branch the same)

Update the `schedule`/`watch` branch to compute and pass `missing_items_path`:

```python
        state = AppState()
        history_path = os.path.join(os.path.dirname(config.log_path) or ".", "scan_history.json")
        missing_items_path = os.path.join(os.path.dirname(config.log_path) or ".", "missing_items.json")
        app = create_app(client, state, config.max_refreshes_per_run, history_path, missing_items_path)
        server_thread = threading.Thread(
            target=lambda: waitress.serve(app, host="0.0.0.0", port=config.web_port),
            daemon=True,
        )
        server_thread.start()

        if config.run_mode == "schedule":
            run_schedule(client, config.cron_schedule, config.max_refreshes_per_run, state, history_path, missing_items_path)
        else:
            run_watch(client)
```

(replacing the existing `history_path = ...` / `app = create_app(...)` / `run_schedule(...)` lines)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (all tests in this file).

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across all files PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: wire missing-items snapshot path through main entrypoint"
```

---

### Task 7: Documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: user-facing description of the new dashboard section.

- [ ] **Step 1: Update `README.md`**

Read the current file first, then update the existing "## Web dashboard" section (add a sentence after the existing paragraph, don't remove anything):

```markdown
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

The dashboard has no authentication — it's intended for use on a
trusted home network, the same as most other Unraid app UIs.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the missing-metadata items list"
```

---

### Task 8: Manual smoke test

**Files:**
- None (manual verification task, no code changes).

**Interfaces:**
- Consumes: the full running system (Tasks 1-7).
- Produces: confidence that the missing-items list renders correctly against a real Jellyfin server.

- [ ] **Step 1: Build and run against a real/test Jellyfin instance**

```bash
docker compose up -d --build
```

- [ ] **Step 2: Trigger a scan and check the new section**

Open `http://<host>:5689/`, click "Scan Now", and once it completes,
confirm the "Missing metadata" section lists real items from the test
library with correct title, type, missing-field tags, and status
badges (refreshed/failed/pending) matching what the logs report.

- [ ] **Step 3: Verify the filter box**

Type part of a known item's title into the filter input. Expected: the
table narrows to matching rows only, case-insensitively, without a
page reload.

- [ ] **Step 4: Verify a failed scan leaves the list untouched**

Temporarily point `JELLYFIN_URL` at an unreachable address and trigger
another scan (or wait for a scheduled tick). Expected: the "Missing
metadata" section still shows the previous scan's real data rather
than going empty, consistent with the error-handling design.

- [ ] **Step 5: Record results**

No commit needed for this task — it's verification only. If any step
surfaces a bug, open a follow-up task/fix and re-run the affected step.
