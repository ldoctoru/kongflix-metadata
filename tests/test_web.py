import threading
from unittest.mock import MagicMock, patch

from app.state import AppState
from app.web import create_app


def make_test_app(tmp_path, state=None, run_mode="schedule"):
    client = MagicMock()
    client.get_all_items.return_value = []
    state = state or AppState()
    history_path = str(tmp_path / "history.json")
    missing_items_path = str(tmp_path / "missing.json")
    app = create_app(client, state, max_refreshes_per_run=200, history_path=history_path, missing_items_path=missing_items_path, run_mode=run_mode)
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
    assert body["run_mode"] == "schedule"


def test_status_reflects_watch_run_mode(tmp_path):
    app, _, _, _, _ = make_test_app(tmp_path, run_mode="watch")

    response = app.test_client().get("/api/status")

    assert response.get_json()["run_mode"] == "watch"


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


def test_index_template_has_no_broken_js_string_escapes(tmp_path):
    app, _, _, _, _ = make_test_app(tmp_path)
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)
    # A Python \' escape inside the JS-containing template string collapses to a
    # bare apostrophe once rendered, leaving a single-quoted JS string literal
    # that an apostrophe in "what's shown" would terminate early -- a syntax
    # error that breaks the entire inline <script>. Note that the plain text
    # "what's shown" appears in the rendered HTML either way (it's part of the
    # dialog copy); what distinguishes broken from fixed is which quote
    # character wraps the confirm() string, so we check that directly rather
    # than the substring alone.
    assert "confirm('Clear the missing-metadata list?" not in html
    assert 'confirm("Clear the missing-metadata list?' in html
