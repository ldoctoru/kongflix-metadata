import threading


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
