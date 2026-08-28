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
