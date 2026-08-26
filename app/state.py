import dataclasses
import datetime
import threading

from app.history import append_history
from app.jellyfin_client import JellyfinApiError
from app.runner import log_summary, run_once


class AppState:
    def __init__(self):
        self.scanning = False
        self.last_result = None
        self.last_run_at = None
        self._lock = threading.Lock()

    def try_start_scan(self) -> bool:
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return False
        self.scanning = True
        return True


def run_scan_and_record(state: AppState, client, max_refreshes_per_run: int, history_path: str) -> None:
    try:
        summary = run_once(client, max_refreshes_per_run)
        log_summary(summary)
        result = dataclasses.asdict(summary)
    except JellyfinApiError as error:
        result = {"error": str(error)}

    state.last_result = result
    state.last_run_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    append_history(history_path, result)

    state.scanning = False
    state._lock.release()
