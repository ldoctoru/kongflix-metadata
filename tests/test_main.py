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
