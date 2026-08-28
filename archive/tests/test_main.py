import logging
from unittest.mock import ANY, patch, MagicMock

from app.jellyfin_client import JellyfinApiError
from app.main import main
from app.state import AppState


@patch("app.main.run_once")
@patch("app.main.log_summary")
@patch("app.main.JellyfinClient")
def test_main_once_mode_runs_single_scan_and_returns_zero(mock_client_cls, mock_log_summary, mock_run_once):
    mock_client_cls.return_value = MagicMock()
    mock_run_once.return_value = (MagicMock(), [])

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


@patch("app.main.waitress")
@patch("app.main.run_schedule")
@patch("app.main.JellyfinClient")
def test_main_schedule_mode_calls_run_schedule(mock_client_cls, mock_run_schedule, mock_waitress):
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
    mock_run_schedule.assert_called_once()
    call_args = mock_run_schedule.call_args
    assert call_args.args[0] == mock_client_cls.return_value
    assert call_args.args[1] == "0 3 * * *"
    assert call_args.args[2] == 200
    assert isinstance(call_args.args[3], AppState)
    assert isinstance(call_args.args[4], str)
    assert isinstance(call_args.args[5], str)
    assert call_args.args[4] != call_args.args[5]


@patch("app.main.waitress")
@patch("app.main.run_watch")
@patch("app.main.JellyfinClient")
def test_main_watch_mode_calls_run_watch(mock_client_cls, mock_run_watch, mock_waitress):
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


@patch("app.main.waitress")
@patch("app.main.run_schedule")
@patch("app.main.JellyfinClient")
def test_main_schedule_mode_starts_web_server_thread(mock_client_cls, mock_run_schedule, mock_waitress):
    mock_client_cls.return_value = MagicMock()

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "schedule",
        "CRON_SCHEDULE": "0 3 * * *",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
        "WEB_PORT": "5689",
    }

    exit_code = main(env)

    assert exit_code == 0

    import time as time_module

    deadline = time_module.time() + 1.0
    while not mock_waitress.serve.called and time_module.time() < deadline:
        time_module.sleep(0.01)

    assert mock_waitress.serve.called
    call_args = mock_waitress.serve.call_args
    assert call_args.kwargs["host"] == "0.0.0.0"
    assert call_args.kwargs["port"] == 5689


@patch("app.main.run_once")
@patch("app.main.log_summary")
@patch("app.main.waitress")
@patch("app.main.JellyfinClient")
def test_main_once_mode_does_not_start_web_server(mock_client_cls, mock_waitress, mock_log_summary, mock_run_once):
    mock_client_cls.return_value = MagicMock()
    mock_run_once.return_value = (MagicMock(), [])

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "once",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 0
    mock_waitress.serve.assert_not_called()


@patch("app.main.run_once")
@patch("app.main.JellyfinClient")
def test_main_once_mode_returns_one_on_jellyfin_api_error(mock_client_cls, mock_run_once):
    mock_client_cls.return_value = MagicMock()
    mock_run_once.side_effect = JellyfinApiError("connection refused")

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "once",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 1


@patch("app.main.time.sleep")
@patch("app.main.run_schedule")
@patch("app.main.JellyfinClient")
def test_main_schedule_mode_returns_one_when_jellyfin_unreachable(
    mock_client_cls, mock_run_schedule, mock_sleep
):
    mock_client = MagicMock()
    mock_client.get_all_items.side_effect = JellyfinApiError("connection refused")
    mock_client_cls.return_value = mock_client

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "schedule",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 1
    mock_run_schedule.assert_not_called()
    assert mock_sleep.called


@patch("app.main.time.sleep")
@patch("app.main.run_watch")
@patch("app.main.JellyfinClient")
def test_main_watch_mode_returns_one_when_jellyfin_unreachable(
    mock_client_cls, mock_run_watch, mock_sleep
):
    mock_client = MagicMock()
    mock_client.get_all_items.side_effect = JellyfinApiError("connection refused")
    mock_client_cls.return_value = mock_client

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "watch",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 1
    mock_run_watch.assert_not_called()
    assert mock_sleep.called


@patch("app.main.time.sleep")
@patch("app.main.waitress")
@patch("app.main.run_schedule")
@patch("app.main.JellyfinClient")
def test_main_schedule_mode_proceeds_when_jellyfin_reachable(
    mock_client_cls, mock_run_schedule, mock_waitress, mock_sleep
):
    mock_client = MagicMock()
    mock_client.get_all_items.return_value = []
    mock_client_cls.return_value = mock_client

    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "RUN_MODE": "schedule",
        "LOG_PATH": "/tmp/test-metadata-updater.log",
    }

    exit_code = main(env)

    assert exit_code == 0
    mock_run_schedule.assert_called_once()
    mock_sleep.assert_not_called()
