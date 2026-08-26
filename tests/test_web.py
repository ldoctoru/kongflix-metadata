import threading
from unittest.mock import MagicMock, patch

from app.state import AppState
from app.web import create_app


def make_test_app(tmp_path, state=None):
    client = MagicMock()
    client.get_all_items.return_value = []
    state = state or AppState()
    history_path = str(tmp_path / "history.json")
    app = create_app(client, state, max_refreshes_per_run=200, history_path=history_path)
    app.config["TESTING"] = True
    return app, client, state, history_path


def test_index_returns_200(tmp_path):
    app, _, _, _ = make_test_app(tmp_path)
    response = app.test_client().get("/")
    assert response.status_code == 200


def test_status_reflects_app_state(tmp_path):
    state = AppState()
    state.last_result = {"scanned": 3}
    state.last_run_at = "2026-01-01T00:00:00+00:00"
    app, _, _, _ = make_test_app(tmp_path, state=state)

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    body = response.get_json()
    assert body["scanning"] is False
    assert body["last_result"] == {"scanned": 3}
    assert body["last_run_at"] == "2026-01-01T00:00:00+00:00"


def test_history_endpoint_returns_persisted_entries(tmp_path):
    from app.history import append_history

    app, _, _, history_path = make_test_app(tmp_path)
    append_history(history_path, {"scanned": 1})
    append_history(history_path, {"scanned": 2})

    response = app.test_client().get("/api/history")

    assert response.status_code == 200
    assert response.get_json() == [{"scanned": 1}, {"scanned": 2}]


@patch("app.web.threading.Thread")
def test_post_scan_starts_scan_when_idle(mock_thread_cls, tmp_path):
    app, client, state, _ = make_test_app(tmp_path)
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
    app, _, _, _ = make_test_app(tmp_path, state=state)

    response = app.test_client().post("/api/scan")

    assert response.status_code == 409
    assert response.get_json() == {"error": "scan already in progress"}
