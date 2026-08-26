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
    max_refreshes_per_run: int


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
    cron_fields = cron_schedule.split()
    if len(cron_fields) != 5:
        raise ConfigError(
            f"CRON_SCHEDULE must have exactly 5 space-separated fields, got {cron_schedule!r}"
        )

    log_path = env.get("LOG_PATH", "/logs/metadata-updater.log")

    max_refreshes_per_run_raw = env.get("MAX_REFRESHES_PER_RUN", "200")
    try:
        max_refreshes_per_run = int(max_refreshes_per_run_raw)
    except (TypeError, ValueError):
        raise ConfigError(
            f"MAX_REFRESHES_PER_RUN must be a positive integer, got {max_refreshes_per_run_raw!r}"
        )
    if max_refreshes_per_run <= 0:
        raise ConfigError(
            f"MAX_REFRESHES_PER_RUN must be a positive integer, got {max_refreshes_per_run_raw!r}"
        )

    return Config(
        jellyfin_url=jellyfin_url,
        jellyfin_api_key=jellyfin_api_key,
        run_mode=run_mode,
        cron_schedule=cron_schedule,
        log_path=log_path,
        max_refreshes_per_run=max_refreshes_per_run,
    )
