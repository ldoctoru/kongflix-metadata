import logging
import os
import sys
import threading
import time

import waitress

from app.config import ConfigError, load_config
from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.runner import log_summary, run_once, run_schedule, run_watch
from app.state import AppState
from app.web import create_app

logger = logging.getLogger(__name__)


def _setup_logging(log_path: str) -> None:
    handlers = [logging.StreamHandler()]
    try:
        dirname = os.path.dirname(log_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
    except OSError as error:
        print(f"warning: could not set up file logging at {log_path}: {error}", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


def _wait_for_jellyfin(client: JellyfinClient, max_attempts: int = 5, initial_delay: int = 2) -> None:
    delay = initial_delay
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            client.get_all_items()
            return
        except JellyfinApiError as error:
            last_error = error
            logger.warning(
                "could not reach Jellyfin (attempt %d/%d): %s", attempt, max_attempts, error
            )
            if attempt < max_attempts:
                time.sleep(delay)
                delay *= 2
    raise last_error


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
        try:
            summary, _missing_items = run_once(client, config.max_refreshes_per_run)
        except JellyfinApiError as error:
            logger.error("could not reach Jellyfin: %s", error)
            return 1
        log_summary(summary)
    elif config.run_mode in ("schedule", "watch"):
        try:
            _wait_for_jellyfin(client)
        except JellyfinApiError as error:
            logger.error("could not reach Jellyfin: %s", error)
            return 1

        state = AppState()
        history_path = os.path.join(os.path.dirname(config.log_path) or ".", "scan_history.json")
        missing_items_path = os.path.join(os.path.dirname(config.log_path) or ".", "missing_items.json")
        app = create_app(client, state, config.max_refreshes_per_run, history_path, missing_items_path, config.run_mode)
        server_thread = threading.Thread(
            target=lambda: waitress.serve(app, host="0.0.0.0", port=config.web_port),
            daemon=True,
        )
        server_thread.start()

        if config.run_mode == "schedule":
            run_schedule(client, config.cron_schedule, config.max_refreshes_per_run, state, history_path, missing_items_path)
        else:
            run_watch(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
