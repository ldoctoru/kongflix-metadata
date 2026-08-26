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
