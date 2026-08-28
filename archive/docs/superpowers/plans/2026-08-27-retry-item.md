# Per-Item Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user retry a single failed/pending item from the dashboard's "Missing metadata" table, without triggering a full library rescan.

**Architecture:** A new `retry_item` function in `app/runner.py` re-attempts `client.refresh_item` for one item, updates that item's status in the persisted `missing_items.json` snapshot, and returns the updated entry. A new Flask route exposes it; the dashboard adds a "Retry" button on failed/pending rows that calls the route and patches just that row in place.

**Tech Stack:** Same as the existing app — Python stdlib, Flask, no new dependencies.

## Global Constraints

- `retry_item` is independent of the scan lock (`AppState.try_start_scan`) — it never acquires or checks it, so a retry can run concurrently with an in-progress scheduled/manual scan.
- A retry's result (`"refreshed"` or `"failed"`) is persisted to `missing_items.json`, not just shown live in the browser.
- The "Retry" button appears only on rows with `status` `"failed"` or `"pending"` — never on `"refreshed"` rows.
- A retry never triggers a full rescan and never touches `scan_history.json` or `ScanSummary` counts — it is not a scan.
- An item not found in the current snapshot returns HTTP 404, not an error that crashes the page.

---

## File Structure

- `app/runner.py` — add `retry_item(client, missing_items_path, item_id) -> dict | None`.
- `app/web.py` — add `POST /api/retry-item/<item_id>` route; add a "Retry" button + JS handler to the dashboard template.
- `README.md` — document the Retry button.
- `tests/test_runner.py`, `tests/test_web.py` — new tests.

---

### Task 1: Runner — retry_item function

**Files:**
- Modify: `app/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes:
  - `app.history.load_missing_items(path: str) -> list` (existing)
  - `app.history.save_missing_items(path: str, items: list) -> None` (existing)
  - `app.jellyfin_client.JellyfinClient.refresh_item(item_id: str) -> None`, `JellyfinApiError` (existing)
- Produces: `retry_item(client: JellyfinClient, missing_items_path: str, item_id: str) -> dict | None` — returns the updated entry dict on success (whether the underlying refresh succeeded or failed — both are "successful retry attempts"), or `None` if `item_id` isn't present in the current snapshot (in which case `refresh_item` is never called and the file is never written).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py`:

```python
from app.history import load_missing_items, save_missing_items
from app.runner import retry_item


def test_retry_item_marks_success_and_persists(tmp_path):
    missing_items_path = str(tmp_path / "missing.json")
    save_missing_items(missing_items_path, [
        {"id": "1", "name": "Bad Item", "type": "Movie", "series": None, "season": None, "missing": ["poster"], "status": "failed"},
        {"id": "2", "name": "Other Item", "type": "Movie", "series": None, "season": None, "missing": ["overview"], "status": "pending"},
    ])
    client = MagicMock()

    result = retry_item(client, missing_items_path, "1")

    assert result["id"] == "1"
    assert result["status"] == "refreshed"
    client.refresh_item.assert_called_once_with("1")

    snapshot = load_missing_items(missing_items_path)
    by_id = {entry["id"]: entry for entry in snapshot}
    assert by_id["1"]["status"] == "refreshed"
    assert by_id["2"]["status"] == "pending"


def test_retry_item_marks_failure_and_persists(tmp_path):
    missing_items_path = str(tmp_path / "missing.json")
    save_missing_items(missing_items_path, [
        {"id": "1", "name": "Bad Item", "type": "Movie", "series": None, "season": None, "missing": ["poster"], "status": "pending"},
    ])
    client = MagicMock()
    client.refresh_item.side_effect = JellyfinApiError("still broken")

    result = retry_item(client, missing_items_path, "1")

    assert result["status"] == "failed"
    assert result["error"] == "still broken"

    snapshot = load_missing_items(missing_items_path)
    assert snapshot[0]["status"] == "failed"
    assert snapshot[0]["error"] == "still broken"


def test_retry_item_returns_none_for_unknown_id(tmp_path):
    missing_items_path = str(tmp_path / "missing.json")
    save_missing_items(missing_items_path, [
        {"id": "1", "name": "Bad Item", "type": "Movie", "series": None, "season": None, "missing": ["poster"], "status": "failed"},
    ])
    client = MagicMock()

    result = retry_item(client, missing_items_path, "does-not-exist")

    assert result is None
    client.refresh_item.assert_not_called()

    snapshot = load_missing_items(missing_items_path)
    assert snapshot[0]["status"] == "failed"
```

Note: `MagicMock` and `JellyfinApiError` are already imported at the top of `tests/test_runner.py` from earlier tasks — only the `load_missing_items`/`save_missing_items`/`retry_item` imports shown above are new.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py -v -k retry_item`
Expected: FAIL with `ImportError: cannot import name 'retry_item' from 'app.runner'`.

- [ ] **Step 3: Write minimal implementation**

Add to `app/runner.py` (after `run_watch`, at the end of the file):

```python
def retry_item(client: JellyfinClient, missing_items_path: str, item_id: str) -> dict | None:
    items = load_missing_items(missing_items_path)

    target = None
    for entry in items:
        if entry.get("id") == item_id:
            target = entry
            break

    if target is None:
        return None

    try:
        client.refresh_item(item_id)
        target["status"] = "refreshed"
        target.pop("error", None)
    except JellyfinApiError as error:
        target["status"] = "failed"
        target["error"] = str(error)

    save_missing_items(missing_items_path, items)
    return target
```

Update the import line at the top of `app/runner.py`:

```python
from app.history import append_history, load_missing_items, save_missing_items
```

(replacing the existing `from app.history import append_history, save_missing_items` line)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v -k retry_item`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across all files PASS.

- [ ] **Step 6: Commit**

```bash
git add app/runner.py tests/test_runner.py
git commit -m "feat: add retry_item for single-item metadata refresh retry"
```

---

### Task 2: Web — retry-item API route

**Files:**
- Modify: `app/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `retry_item(client, missing_items_path, item_id) -> dict | None` (Task 1)
- Produces: `POST /api/retry-item/<item_id>` — HTTP 200 with the updated entry JSON on success (whether the underlying refresh succeeded or failed — see Task 1), HTTP 404 with `{"error": "item not found"}` when `item_id` isn't in the current snapshot.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_web.py`:

```python
def test_retry_item_returns_updated_entry(tmp_path):
    from app.history import save_missing_items

    app, client, _, _, missing_items_path = make_test_app(tmp_path)
    save_missing_items(missing_items_path, [
        {"id": "1", "name": "Bad Item", "type": "Movie", "series": None, "season": None, "missing": ["poster"], "status": "failed"},
    ])

    response = app.test_client().post("/api/retry-item/1")

    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == "1"
    assert body["status"] == "refreshed"
    client.refresh_item.assert_called_once_with("1")


def test_retry_item_returns_404_for_unknown_id(tmp_path):
    app, _, _, _, _ = make_test_app(tmp_path)

    response = app.test_client().post("/api/retry-item/does-not-exist")

    assert response.status_code == 404
    assert response.get_json() == {"error": "item not found"}
```

Note: this uses the existing `make_test_app(tmp_path)` helper already defined at the top of `tests/test_web.py` — no changes needed to that helper, since it already returns `(app, client, state, history_path, missing_items_path)` and the `client` mock returned is the same `MagicMock` wired into `create_app`, so `client.refresh_item` calls made by the route are observable on it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web.py -v -k retry_item`
Expected: FAIL with `404 Not Found` (no such route registered yet) or similar — both new tests fail since the route doesn't exist.

- [ ] **Step 3: Write minimal implementation**

In `app/web.py`, update the runner import:

```python
from app.runner import retry_item, run_scan_and_record
```

(replacing the existing `from app.runner import run_scan_and_record` line)

Add the new route inside `create_app`, after the existing `/api/scan` route and before `return app`:

```python
    @app.route("/api/retry-item/<item_id>", methods=["POST"])
    def retry(item_id):
        result = retry_item(client, missing_items_path, item_id)
        if result is None:
            return jsonify({"error": "item not found"}), 404
        return jsonify(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web.py -v -k retry_item`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across all files PASS.

- [ ] **Step 6: Commit**

```bash
git add app/web.py tests/test_web.py
git commit -m "feat: add retry-item API route"
```

---

### Task 3: Dashboard — Retry button and documentation

**Files:**
- Modify: `app/web.py` (template only — no route changes)
- Modify: `README.md`

**Interfaces:**
- Consumes: `POST /api/retry-item/<item_id>` (Task 2)
- Produces: no new backend interfaces — UI only.

- [ ] **Step 1: Add CSS for the retry button**

In `app/web.py`'s `INDEX_TEMPLATE` `<style>` block, add this after the existing `.page-info { color: var(--text-dim); font-size: 0.82rem; }` rule:

```css
  .retry-btn {
    background: var(--bg-elev-2); border: 1px solid var(--border); color: var(--accent);
    padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.72rem; cursor: pointer;
    margin-left: 0.5rem;
  }
  .retry-btn:hover { background: var(--accent-soft); }
  .retry-btn:disabled { opacity: 0.5; cursor: not-allowed; }
```

- [ ] **Step 2: Add the Retry button to each eligible row**

In `app/web.py`'s `renderMissingItems()` function, find the block that builds `statusCell`:

```javascript
      const statusCell = document.createElement("td");
      const statusBadge = document.createElement("span");
      statusBadge.className = "badge status-" + item.status;
      statusBadge.textContent = item.status;
      statusCell.appendChild(statusBadge);
      row.appendChild(statusCell);
```

Replace it with:

```javascript
      const statusCell = document.createElement("td");
      const statusBadge = document.createElement("span");
      statusBadge.className = "badge status-" + item.status;
      statusBadge.textContent = item.status;
      statusCell.appendChild(statusBadge);

      if (item.status === "failed" || item.status === "pending") {
        const retryBtn = document.createElement("button");
        retryBtn.className = "retry-btn";
        retryBtn.textContent = "Retry";
        retryBtn.onclick = () => retryItem(item.id, retryBtn);
        statusCell.appendChild(retryBtn);
      }

      row.appendChild(statusCell);
```

- [ ] **Step 3: Add the `retryItem` JS function**

In `app/web.py`'s `<script>` block, add this function right after `renderMissingItems()`'s closing brace (before `async function refreshMissingItems()`):

```javascript
  async function retryItem(itemId, buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "Retrying…";

    const res = await fetch("/api/retry-item/" + encodeURIComponent(itemId), { method: "POST" });

    if (res.status === 404) {
      showToast("Item not found — try refreshing the page");
      return;
    }
    if (!res.ok) {
      showToast("Retry failed to start");
      buttonEl.disabled = false;
      buttonEl.textContent = "Retry";
      return;
    }

    const updated = await res.json();
    const index = allMissingItems.findIndex((entry) => entry.id === updated.id);
    if (index !== -1) {
      allMissingItems[index] = updated;
    }
    showToast(updated.status === "refreshed" ? "Refreshed successfully" : "Retry failed again");
    renderMissingItems();
  }
```

Note: `showToast` is already defined earlier in the same `<script>` block (used by `triggerScan()`) — no need to redefine it.

- [ ] **Step 4: Manually verify the full suite still passes**

Run: `pytest -v`
Expected: All tests PASS (this step is template-only JS/CSS with no route or Python logic changes, so the existing suite should be unaffected — no new Python tests are needed for this task, consistent with how the rest of the dashboard's client-side rendering is untested by design).

- [ ] **Step 5: Update `README.md`**

Read the current file first, then update the existing "## Web dashboard" section (add a sentence after the existing paragraph about the missing-items list, don't remove anything):

```markdown
Each failed or pending item also has a "Retry" button to re-attempt
just that one item's refresh without running a full scan — the result
is saved immediately, so it persists across page reloads.
```

- [ ] **Step 6: Commit**

```bash
git add app/web.py README.md
git commit -m "feat: add per-item Retry button to the missing-metadata table"
```

---

### Task 4: Manual smoke test

**Files:**
- None (manual verification task, no code changes).

**Interfaces:**
- Consumes: the full running system (Tasks 1-3).
- Produces: confidence that retry works end-to-end against a real Jellyfin server.

- [ ] **Step 1: Build and run against a real/test Jellyfin instance**

```bash
docker compose up -d --build
```

- [ ] **Step 2: Trigger a scan, then retry a failed or pending item**

Open the dashboard, click "Scan Now", wait for it to complete. If any
item shows "failed" or "pending", click its "Retry" button. Expected:
button shows "Retrying…", then the row's status badge updates
in place (no full page reload, no full table re-render disrupting
scroll position/filter), and a toast confirms the outcome.

- [ ] **Step 3: Verify persistence across reload**

Reload the page. Expected: the retried item's updated status is still
shown (read from `missing_items.json`, not reverted to the pre-retry
state).

- [ ] **Step 4: Verify a retry during an active scan doesn't block either**

Trigger "Scan Now", and while it's running, click "Retry" on a
visible failed/pending item. Expected: both complete independently —
the retry doesn't wait for the scan, and the scan isn't blocked by the
retry.

- [ ] **Step 5: Record results**

No commit needed for this task — it's verification only. If any step
surfaces a bug, open a follow-up task/fix and re-run the affected step.
