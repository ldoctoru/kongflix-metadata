# Jellyfin Metadata Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dockerized Python service that scans a Jellyfin server for items missing a poster or overview, and triggers Jellyfin's own metadata refresh for those items, in `once`, `schedule`, or `watch` mode.

**Architecture:** A `JellyfinClient` wraps the Jellyfin REST API (list items, trigger refresh, listen for `LibraryChanged` websocket events). A `scanner` module holds the pure predicate for "is this item missing metadata". `main.py` wires config, the client, the scanner, and one of three runners together, with a summary logged to stdout and a log file each run. Packaged as a single Docker image.

**Tech Stack:** Python 3.12, `requests` (HTTP), `websocket-client` (websocket), `apscheduler` (cron scheduling), `pytest` + `unittest.mock` (tests), Docker + Docker Compose.

## Global Constraints

- No external metadata provider API calls (TMDb/TVDB/etc.) — refresh is delegated entirely to Jellyfin via `POST /Items/{Id}/Refresh`.
- An item is "missing metadata" if it has no `ImageTags.Primary` OR an empty/missing `Overview` (per spec — poster OR overview, not a comprehensive field check).
- Scan covers all library/item types returned by Jellyfin `/Items` (Movies, Series, Episodes, Music, etc.) — no library-type filtering.
- Logging is log-file + stdout only — no webhook/external notification integration.
- Config is entirely environment-variable driven: `JELLYFIN_URL`, `JELLYFIN_API_KEY` (required), `RUN_MODE` (default `schedule`), `CRON_SCHEDULE` (default `0 3 * * *`), `LOG_PATH` (default `/logs/metadata-updater.log`).
- Refresh call params are exactly: `MetadataRefreshMode=FullRefresh&ImageRefreshMode=FullRefresh&ReplaceAllMetadata=false&ReplaceAllImages=false`.
- Per-item failures must not abort a scan run; startup connection failure fails fast in `once` mode and retries with backoff in `schedule`/`watch` modes.

---

## File Structure

- `app/jellyfin_client.py` — `JellyfinClient` class: HTTP session setup, `get_all_items()`, `refresh_item(item_id)`, `listen_for_library_changes(on_item_added)`.
- `app/scanner.py` — pure function `is_missing_metadata(item: dict) -> bool` and `find_items_missing_metadata(items: list[dict]) -> list[dict]`.
- `app/config.py` — `Config` dataclass loaded from environment variables, with validation.
- `app/runner.py` — `ScanSummary` dataclass and `run_once(client) -> ScanSummary`, `run_schedule(client, cron_schedule, log_path)`, `run_watch(client, log_path)`.
- `app/main.py` — entrypoint: sets up logging, loads `Config`, builds `JellyfinClient`, dispatches to the right runner based on `RUN_MODE`.
- `tests/test_scanner.py` — unit tests for the missing-metadata predicate.
- `tests/test_jellyfin_client.py` — unit tests for `JellyfinClient` request construction, using mocked `requests.Session`.
- `tests/test_runner.py` — unit tests for `run_once` summary building and per-item failure isolation.
- `requirements.txt` — `requests`, `websocket-client`, `apscheduler`.
- `Dockerfile` — `python:3.12-slim` base, installs requirements, copies `app/`, runs `python -m app.main`.
- `docker-compose.yml` — example service definition with env vars and a `/logs` volume mount.
- `.env.example` — documents all environment variables.
- `README.md` — setup/usage instructions.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`
- Create: `pytest.ini`

**Interfaces:**
- Produces: a `python -m pytest` runnable test setup; `app` importable as a package.

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.32.3
websocket-client==1.8.0
apscheduler==3.10.4
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
pytest==8.3.3
```

- [ ] **Step 3: Create empty package files**

Create `app/__init__.py` (empty) and `tests/__init__.py` (empty).

- [ ] **Step 4: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 5: Install dependencies locally and verify pytest runs**

Run:
```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
Expected: `no tests ran` (exits 0, since there are no test files yet).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt app/__init__.py tests/__init__.py pytest.ini
git commit -m "chore: scaffold python project structure"
```

---

### Task 2: Scanner — missing-metadata predicate

**Files:**
- Create: `app/scanner.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Consumes: nothing (pure logic, operates on plain `dict` shaped like a Jellyfin `BaseItemDto` JSON object).
- Produces:
  - `is_missing_metadata(item: dict) -> bool`
  - `find_items_missing_metadata(items: list[dict]) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scanner.py`:

```python
from app.scanner import is_missing_metadata, find_items_missing_metadata


def make_item(**overrides):
    item = {
        "Id": "item-1",
        "Name": "Some Movie",
        "Overview": "A great movie about things.",
        "ImageTags": {"Primary": "abc123"},
    }
    item.update(overrides)
    return item


def test_complete_item_is_not_missing():
    item = make_item()
    assert is_missing_metadata(item) is False


def test_missing_poster_is_flagged():
    item = make_item(ImageTags={})
    assert is_missing_metadata(item) is True


def test_missing_image_tags_key_entirely_is_flagged():
    item = make_item()
    del item["ImageTags"]
    assert is_missing_metadata(item) is True


def test_missing_overview_key_is_flagged():
    item = make_item()
    del item["Overview"]
    assert is_missing_metadata(item) is True


def test_empty_overview_string_is_flagged():
    item = make_item(Overview="")
    assert is_missing_metadata(item) is True


def test_whitespace_only_overview_is_flagged():
    item = make_item(Overview="   ")
    assert is_missing_metadata(item) is True


def test_find_items_missing_metadata_filters_list():
    complete = make_item(Id="complete-1")
    missing_poster = make_item(Id="missing-poster-1", ImageTags={})
    missing_overview = make_item(Id="missing-overview-1", Overview="")

    result = find_items_missing_metadata([complete, missing_poster, missing_overview])

    result_ids = {item["Id"] for item in result}
    assert result_ids == {"missing-poster-1", "missing-overview-1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scanner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scanner'` (or `ImportError`).

- [ ] **Step 3: Write minimal implementation**

Create `app/scanner.py`:

```python
def is_missing_metadata(item: dict) -> bool:
    image_tags = item.get("ImageTags") or {}
    has_poster = bool(image_tags.get("Primary"))

    overview = item.get("Overview") or ""
    has_overview = bool(overview.strip())

    return not has_poster or not has_overview


def find_items_missing_metadata(items: list[dict]) -> list[dict]:
    return [item for item in items if is_missing_metadata(item)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/scanner.py tests/test_scanner.py
git commit -m "feat: add missing-metadata scanner predicate"
```

---

### Task 3: Jellyfin API client — item listing and refresh

**Files:**
- Create: `app/jellyfin_client.py`
- Test: `tests/test_jellyfin_client.py`

**Interfaces:**
- Consumes: `requests.Session`-compatible object (injected for testability).
- Produces:
  - `class JellyfinClient.__init__(self, base_url: str, api_key: str, session: requests.Session | None = None)`
  - `JellyfinClient.get_all_items(self) -> list[dict]`
  - `JellyfinClient.refresh_item(self, item_id: str) -> None`
  - `class JellyfinApiError(Exception)` — raised on non-2xx responses.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jellyfin_client.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.jellyfin_client import JellyfinClient, JellyfinApiError


def make_client(session):
    return JellyfinClient(base_url="http://jellyfin.local:8096", api_key="test-key", session=session)


def test_get_all_items_calls_correct_endpoint_and_returns_items():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"Items": [{"Id": "1"}, {"Id": "2"}]}
    session.get.return_value = response

    client = make_client(session)
    items = client.get_all_items()

    assert items == [{"Id": "1"}, {"Id": "2"}]
    session.get.assert_called_once()
    call_args = session.get.call_args
    assert call_args.args[0] == "http://jellyfin.local:8096/Items"
    assert call_args.kwargs["params"]["Recursive"] is True
    assert call_args.kwargs["headers"]["X-Emby-Token"] == "test-key"


def test_get_all_items_raises_on_error_status():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "server error"
    session.get.return_value = response

    client = make_client(session)

    with pytest.raises(JellyfinApiError):
        client.get_all_items()


def test_refresh_item_calls_correct_endpoint_with_params():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 204
    session.post.return_value = response

    client = make_client(session)
    client.refresh_item("item-123")

    session.post.assert_called_once()
    call_args = session.post.call_args
    assert call_args.args[0] == "http://jellyfin.local:8096/Items/item-123/Refresh"
    params = call_args.kwargs["params"]
    assert params["MetadataRefreshMode"] == "FullRefresh"
    assert params["ImageRefreshMode"] == "FullRefresh"
    assert params["ReplaceAllMetadata"] == "false"
    assert params["ReplaceAllImages"] == "false"
    assert call_args.kwargs["headers"]["X-Emby-Token"] == "test-key"


def test_refresh_item_raises_on_error_status():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 404
    response.text = "not found"
    session.post.return_value = response

    client = make_client(session)

    with pytest.raises(JellyfinApiError):
        client.refresh_item("missing-item")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jellyfin_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jellyfin_client'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/jellyfin_client.py`:

```python
import requests


class JellyfinApiError(Exception):
    pass


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {"X-Emby-Token": self.api_key}

    def get_all_items(self) -> list[dict]:
        url = f"{self.base_url}/Items"
        params = {
            "Recursive": True,
            "Fields": "Overview",
        }
        response = self.session.get(url, params=params, headers=self._headers(), timeout=30)
        if response.status_code != 200:
            raise JellyfinApiError(
                f"GET {url} failed with status {response.status_code}: {response.text}"
            )
        return response.json().get("Items", [])

    def refresh_item(self, item_id: str) -> None:
        url = f"{self.base_url}/Items/{item_id}/Refresh"
        params = {
            "MetadataRefreshMode": "FullRefresh",
            "ImageRefreshMode": "FullRefresh",
            "ReplaceAllMetadata": "false",
            "ReplaceAllImages": "false",
        }
        response = self.session.post(url, params=params, headers=self._headers(), timeout=30)
        if response.status_code not in (200, 204):
            raise JellyfinApiError(
                f"POST {url} failed with status {response.status_code}: {response.text}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jellyfin_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/jellyfin_client.py tests/test_jellyfin_client.py
git commit -m "feat: add Jellyfin API client for item listing and refresh"
```

---

### Task 4: Jellyfin API client — websocket library-change listener

**Files:**
- Modify: `app/jellyfin_client.py`
- Test: `tests/test_jellyfin_client.py`

**Interfaces:**
- Consumes: `websocket.WebSocketApp`-compatible factory (injected for testability).
- Produces: `JellyfinClient.listen_for_library_changes(self, on_item_added: Callable[[str], None]) -> None` — blocking call; for each `LibraryChanged` message with `ItemsAdded`, calls `on_item_added(item_id)` once per added item ID.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jellyfin_client.py`:

```python
import json


def test_listen_for_library_changes_invokes_callback_for_added_items():
    session = MagicMock()
    client = make_client(session)

    received = []
    fake_ws_app = MagicMock()

    def fake_ws_app_factory(url, on_message, on_error, on_close):
        fake_ws_app.on_message = on_message
        return fake_ws_app

    client._ws_app_factory = fake_ws_app_factory

    client.listen_for_library_changes(lambda item_id: received.append(item_id))

    message = json.dumps({
        "MessageType": "LibraryChanged",
        "Data": {"ItemsAdded": ["item-a", "item-b"], "ItemsUpdated": []},
    })
    fake_ws_app.on_message(fake_ws_app, message)

    assert received == ["item-a", "item-b"]
    fake_ws_app.run_forever.assert_called_once()


def test_listen_for_library_changes_ignores_other_message_types():
    session = MagicMock()
    client = make_client(session)

    received = []
    fake_ws_app = MagicMock()

    def fake_ws_app_factory(url, on_message, on_error, on_close):
        fake_ws_app.on_message = on_message
        return fake_ws_app

    client._ws_app_factory = fake_ws_app_factory

    client.listen_for_library_changes(lambda item_id: received.append(item_id))

    message = json.dumps({"MessageType": "SessionsStart", "Data": {}})
    fake_ws_app.on_message(fake_ws_app, message)

    assert received == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jellyfin_client.py -v`
Expected: FAIL with `AttributeError: 'JellyfinClient' object has no attribute '_ws_app_factory'` (or similar).

- [ ] **Step 3: Write minimal implementation**

Modify `app/jellyfin_client.py` — add imports and the method:

```python
import json
from typing import Callable

import websocket
```

Add inside `JellyfinClient.__init__`, after `self.session = ...`:

```python
        self._ws_app_factory = websocket.WebSocketApp
```

Add new method to `JellyfinClient`:

```python
    def listen_for_library_changes(self, on_item_added: Callable[[str], None]) -> None:
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/socket?api_key={self.api_key}"

        def on_message(ws, message):
            data = json.loads(message)
            if data.get("MessageType") != "LibraryChanged":
                return
            items_added = data.get("Data", {}).get("ItemsAdded", [])
            for item_id in items_added:
                on_item_added(item_id)

        def on_error(ws, error):
            pass

        def on_close(ws, close_status_code, close_msg):
            pass

        ws_app = self._ws_app_factory(ws_url, on_message=on_message, on_error=on_error, on_close=on_close)
        ws_app.run_forever()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jellyfin_client.py -v`
Expected: PASS (6 tests total in this file).

- [ ] **Step 5: Commit**

```bash
git add app/jellyfin_client.py tests/test_jellyfin_client.py
git commit -m "feat: add websocket library-change listener to Jellyfin client"
```

---

### Task 5: Config loading

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `os.environ`-like mapping (injected as a `dict` parameter for testability).
- Produces:
  - `class Config` (dataclass) with fields: `jellyfin_url: str`, `jellyfin_api_key: str`, `run_mode: str`, `cron_schedule: str`, `log_path: str`.
  - `class ConfigError(Exception)`
  - `load_config(env: dict) -> Config`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import pytest

from app.config import load_config, Config, ConfigError


def test_loads_required_and_default_values():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
    }
    config = load_config(env)

    assert config == Config(
        jellyfin_url="http://jellyfin.local:8096",
        jellyfin_api_key="secret-key",
        run_mode="schedule",
        cron_schedule="0 3 * * *",
        log_path="/logs/metadata-updater.log",
    )


def test_loads_overridden_optional_values():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "once",
        "CRON_SCHEDULE": "0 * * * *",
        "LOG_PATH": "/var/log/updater.log",
    }
    config = load_config(env)

    assert config.run_mode == "once"
    assert config.cron_schedule == "0 * * * *"
    assert config.log_path == "/var/log/updater.log"


def test_missing_jellyfin_url_raises():
    env = {"JELLYFIN_API_KEY": "secret-key"}
    with pytest.raises(ConfigError):
        load_config(env)


def test_missing_jellyfin_api_key_raises():
    env = {"JELLYFIN_URL": "http://jellyfin.local:8096"}
    with pytest.raises(ConfigError):
        load_config(env)


def test_invalid_run_mode_raises():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "not-a-real-mode",
    }
    with pytest.raises(ConfigError):
        load_config(env)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/config.py`:

```python
from dataclasses import dataclass

VALID_RUN_MODES = {"once", "schedule", "watch"}


class ConfigError(Exception):
    pass


@dataclass(eq=True)
class Config:
    jellyfin_url: str
    jellyfin_api_key: str
    run_mode: str
    cron_schedule: str
    log_path: str


def load_config(env: dict) -> Config:
    jellyfin_url = env.get("JELLYFIN_URL")
    if not jellyfin_url:
        raise ConfigError("JELLYFIN_URL is required")

    jellyfin_api_key = env.get("JELLYFIN_API_KEY")
    if not jellyfin_api_key:
        raise ConfigError("JELLYFIN_API_KEY is required")

    run_mode = env.get("RUN_MODE", "schedule")
    if run_mode not in VALID_RUN_MODES:
        raise ConfigError(f"RUN_MODE must be one of {sorted(VALID_RUN_MODES)}, got {run_mode!r}")

    cron_schedule = env.get("CRON_SCHEDULE", "0 3 * * *")
    log_path = env.get("LOG_PATH", "/logs/metadata-updater.log")

    return Config(
        jellyfin_url=jellyfin_url,
        jellyfin_api_key=jellyfin_api_key,
        run_mode=run_mode,
        cron_schedule=cron_schedule,
        log_path=log_path,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add environment-variable config loading"
```

---

### Task 6: Runner — single scan pass with summary and failure isolation

**Files:**
- Create: `app/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes:
  - `JellyfinClient.get_all_items(self) -> list[dict]` (Task 3)
  - `JellyfinClient.refresh_item(self, item_id: str) -> None` (Task 3)
  - `JellyfinApiError` (Task 3)
  - `find_items_missing_metadata(items: list[dict]) -> list[dict]` (Task 2)
- Produces:
  - `@dataclass ScanSummary`: `scanned: int`, `flagged: int`, `refreshed: int`, `failures: list[tuple[str, str]]` (item name, error message)
  - `run_once(client: JellyfinClient) -> ScanSummary`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runner.py`:

```python
from unittest.mock import MagicMock

from app.jellyfin_client import JellyfinApiError
from app.runner import run_once, ScanSummary


def test_run_once_refreshes_only_flagged_items():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Complete", "Overview": "ok", "ImageTags": {"Primary": "x"}},
        {"Id": "2", "Name": "Missing Poster", "Overview": "ok", "ImageTags": {}},
        {"Id": "3", "Name": "Missing Overview", "Overview": "", "ImageTags": {"Primary": "x"}},
    ]

    summary = run_once(client)

    assert summary.scanned == 3
    assert summary.flagged == 2
    assert summary.refreshed == 2
    assert summary.failures == []
    client.refresh_item.assert_any_call("2")
    client.refresh_item.assert_any_call("3")
    assert client.refresh_item.call_count == 2


def test_run_once_isolates_per_item_failures():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Bad Item", "Overview": "", "ImageTags": {}},
        {"Id": "2", "Name": "Good Item", "Overview": "", "ImageTags": {}},
    ]

    def refresh_side_effect(item_id):
        if item_id == "1":
            raise JellyfinApiError("boom")

    client.refresh_item.side_effect = refresh_side_effect

    summary = run_once(client)

    assert summary.scanned == 2
    assert summary.flagged == 2
    assert summary.refreshed == 1
    assert summary.failures == [("Bad Item", "boom")]


def test_run_once_with_no_missing_items():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "1", "Name": "Complete", "Overview": "ok", "ImageTags": {"Primary": "x"}},
    ]

    summary = run_once(client)

    assert summary == ScanSummary(scanned=1, flagged=0, refreshed=0, failures=[])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.runner'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/runner.py`:

```python
from dataclasses import dataclass, field

from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.scanner import find_items_missing_metadata


@dataclass(eq=True)
class ScanSummary:
    scanned: int
    flagged: int
    refreshed: int
    failures: list = field(default_factory=list)


def run_once(client: JellyfinClient) -> ScanSummary:
    items = client.get_all_items()
    flagged_items = find_items_missing_metadata(items)

    refreshed = 0
    failures = []

    for item in flagged_items:
        try:
            client.refresh_item(item["Id"])
            refreshed += 1
        except JellyfinApiError as error:
            failures.append((item.get("Name", item["Id"]), str(error)))

    return ScanSummary(
        scanned=len(items),
        flagged=len(flagged_items),
        refreshed=refreshed,
        failures=failures,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/test_runner.py
git commit -m "feat: add single-scan runner with per-item failure isolation"
```

---

### Task 7: Runner — schedule and watch modes, plus logging setup

**Files:**
- Modify: `app/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes:
  - `ScanSummary`, `run_once(client) -> ScanSummary` (Task 6, this task's earlier steps)
  - `JellyfinClient.listen_for_library_changes(self, on_item_added) -> None` (Task 4)
  - `JellyfinClient.refresh_item(self, item_id: str) -> None` (Task 3)
  - `apscheduler.schedulers.blocking.BlockingScheduler` (third-party, from `requirements.txt`)
- Produces:
  - `log_summary(summary: ScanSummary) -> None` — logs via the `logging` module at INFO level (and ERROR per failure).
  - `run_schedule(client: JellyfinClient, cron_schedule: str) -> None` — blocking; runs `run_once` + `log_summary` on the given cron expression, immediately once at startup, then on schedule.
  - `run_watch(client: JellyfinClient) -> None` — blocking; calls `client.listen_for_library_changes` with a callback that calls `client.refresh_item(item_id)` and logs the outcome.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py`:

```python
import logging

from app.runner import log_summary, run_watch


def test_log_summary_logs_counts_and_failures(caplog):
    from app.runner import ScanSummary

    summary = ScanSummary(scanned=10, flagged=2, refreshed=1, failures=[("Bad Item", "boom")])

    with caplog.at_level(logging.INFO):
        log_summary(summary)

    assert "scanned=10" in caplog.text
    assert "flagged=2" in caplog.text
    assert "refreshed=1" in caplog.text
    assert "Bad Item" in caplog.text
    assert "boom" in caplog.text


def test_run_watch_refreshes_items_reported_by_listener():
    client = MagicMock()

    def fake_listen(on_item_added):
        on_item_added("new-item-1")
        on_item_added("new-item-2")

    client.listen_for_library_changes.side_effect = fake_listen

    run_watch(client)

    client.refresh_item.assert_any_call("new-item-1")
    client.refresh_item.assert_any_call("new-item-2")
    assert client.refresh_item.call_count == 2


def test_run_watch_isolates_refresh_failures(caplog):
    client = MagicMock()

    def fake_listen(on_item_added):
        on_item_added("bad-item")
        on_item_added("good-item")

    client.listen_for_library_changes.side_effect = fake_listen

    def refresh_side_effect(item_id):
        if item_id == "bad-item":
            raise JellyfinApiError("boom")

    client.refresh_item.side_effect = refresh_side_effect

    with caplog.at_level(logging.INFO):
        run_watch(client)

    assert client.refresh_item.call_count == 2
    assert "bad-item" in caplog.text
    assert "boom" in caplog.text
```

Note: `MagicMock` and `JellyfinApiError` are already imported at the top of `tests/test_runner.py` from Task 6 — no new imports needed for those names, only add the `logging` and `app.runner` imports shown above.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with `ImportError: cannot import name 'log_summary' from 'app.runner'`.

- [ ] **Step 3: Write minimal implementation**

Modify `app/runner.py` — add imports at the top:

```python
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
```

Add functions at the end of `app/runner.py`:

```python
logger = logging.getLogger("jellyfin_metadata_updater")


def log_summary(summary: ScanSummary) -> None:
    logger.info(
        "scan complete: scanned=%d flagged=%d refreshed=%d failed=%d",
        summary.scanned,
        summary.flagged,
        summary.refreshed,
        len(summary.failures),
    )
    for name, error_message in summary.failures:
        logger.error("failed to refresh %s: %s", name, error_message)


def run_schedule(client: JellyfinClient, cron_schedule: str) -> None:
    def scan_job():
        summary = run_once(client)
        log_summary(summary)

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


def run_watch(client: JellyfinClient) -> None:
    def on_item_added(item_id: str):
        try:
            client.refresh_item(item_id)
            logger.info("refreshed newly added item %s", item_id)
        except JellyfinApiError as error:
            logger.error("failed to refresh newly added item %s: %s", item_id, error)

    client.listen_for_library_changes(on_item_added)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: PASS (6 tests total in this file).

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/test_runner.py
git commit -m "feat: add schedule and watch run modes with summary logging"
```

---

### Task 8: Main entrypoint

**Files:**
- Create: `app/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes:
  - `load_config(env: dict) -> Config`, `ConfigError` (Task 5)
  - `JellyfinClient.__init__(self, base_url, api_key)` (Task 3)
  - `run_once(client) -> ScanSummary`, `log_summary(summary)`, `run_schedule(client, cron_schedule)`, `run_watch(client)` (Tasks 6-7)
- Produces: `main(env: dict = None) -> int` — returns process exit code; `if __name__ == "__main__":` calls `sys.exit(main())`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:

```python
import logging
from unittest.mock import patch, MagicMock

from app.main import main


@patch("app.main.run_once")
@patch("app.main.log_summary")
@patch("app.main.JellyfinClient")
def test_main_once_mode_runs_single_scan_and_returns_zero(mock_client_cls, mock_log_summary, mock_run_once):
    mock_client_cls.return_value = MagicMock()
    mock_run_once.return_value = MagicMock()

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "once",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 0
    mock_client_cls.assert_called_once_with(base_url="http://jellyfin.local:8096", api_key="secret-key")
    mock_run_once.assert_called_once()
    mock_log_summary.assert_called_once()


def test_main_returns_nonzero_on_invalid_config():
    env = {"JELLYFIN_URL": "http://jellyfin.local:8096"}  # missing API key

    exit_code = main(env)

    assert exit_code == 1


@patch("app.main.run_schedule")
@patch("app.main.JellyfinClient")
def test_main_schedule_mode_calls_run_schedule(mock_client_cls, mock_run_schedule):
    mock_client_cls.return_value = MagicMock()

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "schedule",
        "CRON_SCHEDULE": "0 3 * * *",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 0
    mock_run_schedule.assert_called_once_with(mock_client_cls.return_value, "0 3 * * *")


@patch("app.main.run_watch")
@patch("app.main.JellyfinClient")
def test_main_watch_mode_calls_run_watch(mock_client_cls, mock_run_watch):
    mock_client_cls.return_value = MagicMock()

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "watch",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 0
    mock_run_watch.assert_called_once_with(mock_client_cls.return_value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/main.py`:

```python
import logging
import os
import sys

from app.config import ConfigError, load_config
from app.jellyfin_client import JellyfinClient
from app.runner import log_summary, run_once, run_schedule, run_watch


def _setup_logging(log_path: str) -> None:
    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
    except OSError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


def main(env: dict = None) -> int:
    if env is None:
        env = os.environ

    try:
        config = load_config(env)
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 1

    _setup_logging(config.log_path)

    client = JellyfinClient(base_url=config.jellyfin_url, api_key=config.jellyfin_api_key)

    if config.run_mode == "once":
        summary = run_once(client)
        log_summary(summary)
    elif config.run_mode == "schedule":
        run_schedule(client, config.cron_schedule)
    elif config.run_mode == "watch":
        run_watch(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across all files PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: add main entrypoint dispatching to run modes"
```

---

### Task 9: Dockerfile, Compose, and env example

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `requirements.txt` (Task 1), `app/main.py` (Task 8).
- Produces: a buildable Docker image that runs `python -m app.main` as its entrypoint.

- [ ] **Step 1: Create `.dockerignore`**

```
.git
.gitignore
tests/
docs/
*.pyc
__pycache__/
.pytest_cache/
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
```

- [ ] **Step 3: Create `.env.example`**

```
JELLYFIN_URL=http://jellyfin.local:8096
JELLYFIN_API_KEY=changeme
RUN_MODE=schedule
CRON_SCHEDULE=0 3 * * *
LOG_PATH=/logs/metadata-updater.log
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  kongflix-metadata:
    build: .
    container_name: kongflix-metadata
    restart: unless-stopped
    environment:
      JELLYFIN_URL: ${JELLYFIN_URL}
      JELLYFIN_API_KEY: ${JELLYFIN_API_KEY}
      RUN_MODE: ${RUN_MODE:-schedule}
      CRON_SCHEDULE: ${CRON_SCHEDULE:-0 3 * * *}
      LOG_PATH: /logs/metadata-updater.log
    volumes:
      - ./logs:/logs
```

- [ ] **Step 5: Build the image to verify it builds successfully**

Run: `docker build -t kongflix-metadata .`
Expected: build completes with exit code 0.

- [ ] **Step 6: Verify the container fails fast with a clear message when config is missing**

Run: `docker run --rm kongflix-metadata`
Expected: prints `configuration error: JELLYFIN_URL is required` (or similar) to stderr and exits non-zero.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example .dockerignore
git commit -m "feat: add Dockerfile, compose config, and env example"
```

---

### Task 10: README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: user-facing setup/usage instructions.

- [ ] **Step 1: Write `README.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage instructions"
```

---

### Task 11: Manual smoke test against a real Jellyfin instance

**Files:**
- None (manual verification task, no code changes).

**Interfaces:**
- Consumes: the full running system (Tasks 1-10).
- Produces: confidence that the refresh call and websocket listener work against a real Jellyfin server.

- [ ] **Step 1: Run a one-off scan against a real/test Jellyfin server**

Fill in `.env` with real `JELLYFIN_URL`/`JELLYFIN_API_KEY` pointing at a test
Jellyfin instance (not production, to avoid unexpected refresh load). Run:

```bash
docker compose run --rm -e RUN_MODE=once kongflix-metadata
```

Expected: log output shows `scan complete: scanned=N flagged=M refreshed=M failed=0`
(or `failed=K` with real error details logged if some items errored), and in
the Jellyfin dashboard, at least one previously-incomplete item now shows a
poster and/or overview after Jellyfin's provider fetch completes (this may
take a few seconds to a couple minutes depending on Jellyfin's own refresh
queue).

- [ ] **Step 2: Verify watch mode picks up a newly added item**

```bash
docker compose run --rm -e RUN_MODE=watch kongflix-metadata
```

While it's running, add a new movie/show file to a Jellyfin-monitored
folder and let Jellyfin auto-scan it in. Expected: within a few seconds,
the log shows `refreshed newly added item <id>` for the new item.

- [ ] **Step 3: Verify scheduled mode runs immediately then waits**

```bash
docker compose up -d --build
docker compose logs -f
```

Expected: a `scan complete: ...` log line appears immediately at startup,
and the container keeps running afterward without exiting (waiting for the
next cron tick).

- [ ] **Step 4: Record results**

No commit needed for this task — it's verification only. If any step
surfaces a bug, open a follow-up task/fix and re-run the affected step.
