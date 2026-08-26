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
        max_refreshes_per_run=200,
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


def test_invalid_cron_schedule_raises():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "CRON_SCHEDULE": "0 3 * *",
    }
    with pytest.raises(ConfigError):
        load_config(env)


def test_default_max_refreshes_per_run_is_200():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
    }
    config = load_config(env)

    assert config.max_refreshes_per_run == 200


def test_max_refreshes_per_run_can_be_overridden():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "MAX_REFRESHES_PER_RUN": "50",
    }
    config = load_config(env)

    assert config.max_refreshes_per_run == 50


def test_invalid_max_refreshes_per_run_raises():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "MAX_REFRESHES_PER_RUN": "not-a-number",
    }
    with pytest.raises(ConfigError):
        load_config(env)


def test_zero_max_refreshes_per_run_raises():
    env = {
        "JELLYFIN_URL": "http://jellyfin.local:8096",
        "JELLYFIN_API_KEY": "secret-key",
        "MAX_REFRESHES_PER_RUN": "0",
    }
    with pytest.raises(ConfigError):
        load_config(env)
