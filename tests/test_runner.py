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
