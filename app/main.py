import logging
import os
import sys

from app.config import ConfigError, load_config
from app.jellyfin_client import JellyfinClient
from app.runner import log_summary, run_once, run_schedule, run_watch


def _setup_logging(log_path: str) -> None:
    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
    except OSError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


def main(env: dict = None) -> int:
    if env is None:
        env = os.environ

    try:
        config = load_config(env)
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 1

    _setup_logging(config.log_path)

    client = JellyfinClient(base_url=config.jellyfin_url, api_key=config.jellyfin_api_key)

    if config.run_mode == "once":
        summary = run_once(client)
        log_summary(summary)
    elif config.run_mode == "schedule":
        run_schedule(client, config.cron_schedule)
    elif config.run_mode == "watch":
        run_watch(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
