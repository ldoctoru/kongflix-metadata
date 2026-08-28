# Clear Missing-Items List + Watch-Mode Hint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Clear List" button that empties the missing-metadata list on demand, and a contextual hint in `watch` mode explaining that the list only updates on a full scan.

**Architecture:** A new `POST /api/clear-missing-items` route overwrites the snapshot with an empty list (lock-protected, reusing the existing `_missing_items_lock`). `GET /api/status` gains a `run_mode` field so the dashboard can conditionally show the watch-mode hint. Both are additive — no change to scan/watch behavior.

**Tech Stack:** Same as the existing app — Python stdlib, Flask, no new dependencies.

## Global Constraints

- Clearing never touches the scan lock (`AppState.try_start_scan`) — it works regardless of whether a scan is in progress.
- Clearing reuses `app.runner._missing_items_lock` (the same lock already protecting `missing_items.json` reads/writes) rather than introducing a second lock.
- The watch-mode hint is shown only when `run_mode === "watch"` — never in `schedule` or `once` (though `once` mode never starts the dashboard at all, so this is moot for that mode in practice).
- No change to scheduled/manual scan behavior, the scan lock, or the "most recent scan only" snapshot semantics.

---

## File Structure

- `app/web.py` — add `POST /api/clear-missing-items` route; add `run_mode` to `create_app`'s signature and to the `/api/status` JSON response; add a "Clear List" button + confirm dialog + watch-mode hint to the dashboard template.
- `app/main.py` — pass `config.run_mode` into `create_app(...)`.
- `README.md` — document both additions.
- `tests/test_web.py` — update `make_test_app` helper to accept/pass `run_mode`; add new tests.

---

### Task 1: Backend — clear-missing-items route and run_mode in status

**Files:**
- Modify: `app/web.py`
- Modify: `app/main.py`
- Modify: `tests/test_web.py`

**Interfaces:**
- Consumes:
  - `app.runner._missing_items_lock` (existing `threading.Lock()` instance)
  - `app.history.save_missing_items(path: str, items: list) -> None` (existing)
- Produces:
  - `create_app(client, state, max_refreshes_per_run: int, history_path: str, missing_items_path: str, run_mode: str) -> Flask` — signature gains a required `run_mode` parameter (last position).
  - `GET /api/status` response gains a `"run_mode"` key.
  - New route `POST /api/clear-missing-items` — always returns `{"cleared": true}` with HTTP 200 (idempotent; clearing an empty list is a no-op).

- [ ] **Step 1: Update the existing failing tests and add new ones**

Replace `tests/test_web.py`'s `make_test_app` helper and add new tests — read the current full file first (it has 9 existing tests), then apply these changes:

Change the helper:

```python
def make_test_app(tmp_path, state=None, run_mode="schedule"):
    client = MagicMock()
    client.get_all_items.return_value = []
    state = state or AppState()
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    app = create_app(client, state, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path, run_mode=run_mode)
    app.config["TESTING"] = True
    return app, client, state, history_path, missing_items_path
```

Update `test_status_reflects_app_state` to also assert the new field — find this existing test and add one line to its body, right after the existing `assert body["last_run_at"] == "2026-01-01T00:00:00+00:00"` line:

```python
    assert body["run_mode"] == "schedule"
```

Add new tests (anywhere in the file, e.g. near the other `/api/missing-items` tests):

```python
def test_status_reflects_watch_run_mode(tmp_path):
    app, _, _, _, _ = make_test_app(tmp_path, run_mode="watch")

    response = app.test_client().get("/api/status")

    assert response.get_json()["run_mode"] == "watch"


def test_clear_missing_items_empties_the_snapshot(tmp_path):
    from app.history import load_missing_items, save_missing_items

    app, _, _, _, missing_items_path = make_test_app(tmp_path)
    save_missing_items(missing_items_path, [
        {"id": "1", "name": "Some Movie", "type": "Movie", "series": None, "season": None, "missing": ["poster"], "status": "failed"},
    ])

    response = app.test_client().post("/api/clear-missing-items")

    assert response.status_code == 200
    assert response.get_json() == {"cleared": True}
    assert load_missing_items(missing_items_path) == []


def test_clear_missing_items_is_idempotent_on_empty_list(tmp_path):
    app, _, _, _, missing_items_path = make_test_app(tmp_path)

    response = app.test_client().post("/api/clear-missing-items")

    assert response.status_code == 200
    assert response.get_json() == {"cleared": True}

    from app.history import load_missing_items
    assert load_missing_items(missing_items_path) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web.py -v`
Expected: FAIL — `TypeError: create_app() missing 1 required positional argument: 'run_mode'` (all tests using `make_test_app` now fail, since the helper passes `run_mode=run_mode` to a `create_app` that doesn't accept it yet).

- [ ] **Step 3: Write minimal implementation**

In `app/web.py`, update the history import:

```python
from app.history import load_history, load_missing_items, save_missing_items
```

(replacing the existing `from app.history import load_history, load_missing_items` line)

Update the runner import:

```python
from app.runner import _missing_items_lock, retry_item, run_scan_and_record
```

(replacing the existing `from app.runner import retry_item, run_scan_and_record` line)

Update `create_app`'s signature:

```python
def create_app(client, state: AppState, max_refreshes_per_run: int, history_path: str, missing_items_path: str, run_mode: str) -> Flask:
```

Update the `/api/status` route body:

```python
    @app.route("/api/status")
    def status():
        return jsonify({
            "scanning": state.scanning,
            "last_result": state.last_result,
            "last_run_at": state.last_run_at,
            "run_mode": run_mode,
        })
```

Add the new route, after the existing `/api/retry-item/<item_id>` route and before `return app`:

```python
    @app.route("/api/clear-missing-items", methods=["POST"])
    def clear_missing_items():
        with _missing_items_lock:
            save_missing_items(missing_items_path, [])
        return jsonify({"cleared": True})
```

In `app/main.py`, update the `create_app(...)` call:

```python
        app = create_app(client, state, config.max_refreshes_per_run, history_path, missing_items_path, config.run_mode)
```

(replacing the existing `app = create_app(client, state, config.max_refreshes_per_run, history_path, missing_items_path)` line)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web.py -v`
Expected: PASS (13 tests total in this file — 9 existing + 4 new).

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across all files PASS.

- [ ] **Step 6: Commit**

```bash
git add app/web.py app/main.py tests/test_web.py
git commit -m "feat: add clear-missing-items route and run_mode to status"
```

---

### Task 2: Dashboard — Clear List button and watch-mode hint

**Files:**
- Modify: `app/web.py` (template only — no route changes)
- Modify: `README.md`

**Interfaces:**
- Consumes: `POST /api/clear-missing-items`, `GET /api/status`'s `run_mode` field (Task 1)
- Produces: no new backend interfaces — UI only.

- [ ] **Step 1: Add CSS for the Clear List button and the hint text**

In `app/web.py`'s `INDEX_TEMPLATE` `<style>` block, add this after the existing `.retry-btn:disabled { opacity: 0.5; cursor: not-allowed; }` rule:

```css
  .missing-actions {
    display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.9rem;
  }
  .missing-actions .filter-input { margin-bottom: 0; flex: 1; }
  .clear-btn {
    background: var(--bg-elev-2); border: 1px solid var(--border); color: var(--bad);
    padding: 0.6rem 0.9rem; border-radius: 9px; font-size: 0.85rem; cursor: pointer;
    white-space: nowrap;
  }
  .clear-btn:hover { background: rgba(232, 105, 125, 0.12); }
  .watch-hint {
    color: var(--text-dim); font-size: 0.82rem; margin: -0.4rem 0 0.9rem 0.1rem;
  }
```

- [ ] **Step 2: Restructure the filter row and add the hint line**

Find this existing block in `app/web.py`'s HTML body:

```html
  <div class="section-title" style="margin-top: 1.5rem;">Missing metadata</div>
  <input id="missing-filter" class="filter-input" type="text" placeholder="Filter by title...">
```

Replace it with:

```html
  <div class="section-title" style="margin-top: 1.5rem;">Missing metadata</div>
  <div id="watch-hint" class="watch-hint" style="display:none;">Watch mode only reacts to newly added items — click "Scan Now" to refresh this list.</div>
  <div class="missing-actions">
    <input id="missing-filter" class="filter-input" type="text" placeholder="Filter by title...">
    <button id="clear-list-btn" class="clear-btn" onclick="clearMissingList()">Clear List</button>
  </div>
```

- [ ] **Step 3: Show/hide the watch-mode hint based on run_mode**

In `app/web.py`'s `refreshStatus()` function, find the line that reads `scanning = !!data.scanning;` near the top of the function body, and add this right after it:

```javascript
    document.getElementById("watch-hint").style.display = data.run_mode === "watch" ? "block" : "none";
```

- [ ] **Step 4: Add the `clearMissingList` JS function**

In `app/web.py`'s `<script>` block, add this function right after `retryItem(...)`'s closing brace (before `async function refreshMissingItems()`):

```javascript
  async function clearMissingList() {
    if (!confirm('Clear the missing-metadata list? This does not affect Jellyfin — it just resets what\'s shown here until the next scan.')) {
      return;
    }

    const res = await fetch("/api/clear-missing-items", { method: "POST" });
    if (!res.ok) {
      showToast("Could not clear the list");
      return;
    }

    allMissingItems = [];
    currentMissingPage = 1;
    renderMissingItems();
    showToast("List cleared");
  }
```

- [ ] **Step 5: Manually verify the full suite still passes**

Run: `pytest -v`
Expected: All tests PASS (this step is template-only JS/CSS/HTML with no route or Python logic changes, so the existing suite is unaffected — no new Python tests are needed for this task, consistent with how the rest of the dashboard's client-side rendering is untested by design).

- [ ] **Step 6: Update `README.md`**

Read the current file first, then update the existing "## Web dashboard" section (add these sentences after the existing paragraph about the missing-items list and Retry button, don't remove anything):

```markdown
A "Clear List" button resets the displayed list (and its persisted
snapshot) on demand, without waiting for or triggering a scan — useful
if the list is stale and you don't want to run a full rescan right
away. In `watch` mode, a hint reminds you that the list only updates
on a full scan (a scheduled tick, in `schedule` mode, or a manual
"Scan Now" click) — `watch` mode itself only reacts to newly added
items and never re-scans the existing library on its own.
```

- [ ] **Step 7: Commit**

```bash
git add app/web.py README.md
git commit -m "feat: add Clear List button and watch-mode hint to dashboard"
```

---

### Task 3: Manual smoke test

**Files:**
- None (manual verification task, no code changes).

**Interfaces:**
- Consumes: the full running system (Tasks 1-2).
- Produces: confidence that clearing works end-to-end and the hint shows correctly.

- [ ] **Step 1: Build and run against a real/test Jellyfin instance**

```bash
docker compose up -d --build
```

- [ ] **Step 2: Verify Clear List**

Trigger a scan so the missing-items list has entries. Click "Clear
List", confirm the dialog. Expected: the table immediately shows the
empty state, and reloading the page also shows it empty (confirming
the snapshot file was actually cleared, not just the in-browser view).

- [ ] **Step 3: Verify the watch-mode hint**

Set `RUN_MODE=watch` and restart the container. Expected: the hint
line appears under "Missing metadata" explaining that the list only
updates on a full scan. Switch back to `RUN_MODE=schedule` (or
`RUN_MODE=once`, though `once` never starts the dashboard) and
restart; expected: the hint no longer appears.

- [ ] **Step 4: Verify a scan after clearing repopulates the list normally**

After clearing, click "Scan Now" (or wait for the next scheduled
tick). Expected: the list repopulates with the scan's real results,
unaffected by the earlier clear.

- [ ] **Step 5: Record results**

No commit needed for this task — it's verification only. If any step
surfaces a bug, open a follow-up task/fix and re-run the affected step.
