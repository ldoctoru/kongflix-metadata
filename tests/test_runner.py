import logging
from unittest.mock import MagicMock, patch

from app.jellyfin_client import JellyfinApiError
from app.runner import run_once, run_schedule, ScanSummary
from app.runner import log_summary, run_watch
from app.state import AppState


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


@patch("app.runner.BlockingScheduler")
def test_run_schedule_skips_scan_when_one_already_in_progress(mock_scheduler_cls, tmp_path):
    history_path = str(tmp_path / "history.json")
    state = AppState()
    state.try_start_scan()  # simulate a scan already in progress (lock held)

    client = MagicMock()

    with patch("app.runner.run_once") as mock_run_once:
        run_schedule(client, "0 3 * * *", 200, state, history_path, str(tmp_path / "missing.json"))

    mock_run_once.assert_not_called()
    mock_scheduler_cls.return_value.start.assert_called_once()


@patch("app.runner.BlockingScheduler")
def test_run_schedule_runs_scan_via_state_when_idle(mock_scheduler_cls, tmp_path):
    history_path = str(tmp_path / "history.json")
    state = AppState()

    client = MagicMock()
    client.get_all_items.return_value = []

    run_schedule(client, "0 3 * * *", 200, state, history_path, str(tmp_path / "missing.json"))

    assert state.last_result["scanned"] == 0
    assert state.last_result["flagged"] == 0
    assert state.last_result["refreshed"] == 0
    assert state.last_result["failures"] == []
    assert state.last_result["skipped"] == 0
    assert state.last_result["timestamp"] == state.last_run_at
    assert state.scanning is False

    from app.history import load_history
    history = load_history(history_path)
    assert len(history) == 1


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
