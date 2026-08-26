import dataclasses
import datetime
import logging
from dataclasses import dataclass, field

from apscheduler.schedulers.blocking import BlockingScheduler

from app.history import append_history
from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.scanner import find_items_missing_metadata


@dataclass(eq=True)
class ScanSummary:
    scanned: int
    flagged: int
    refreshed: int
    failures: list = field(default_factory=list)
    skipped: int = 0


def run_once(client: JellyfinClient, max_refreshes_per_run: int = 200) -> ScanSummary:
    items = client.get_all_items()
    flagged_items = find_items_missing_metadata(items)

    items_to_refresh = flagged_items[:max_refreshes_per_run]
    skipped = max(0, len(flagged_items) - max_refreshes_per_run)

    refreshed = 0
    failures = []

    for item in items_to_refresh:
        try:
            client.refresh_item(item["Id"])
            refreshed += 1
        except JellyfinApiError as error:
            failures.append((item.get("Name", item["Id"]), str(error)))

    return ScanSummary(
        scanned=len(items),
        flagged=len(flagged_items),
        refreshed=refreshed,
        failures=failures,
        skipped=skipped,
    )


logger = logging.getLogger("jellyfin_metadata_updater")


def log_summary(summary: ScanSummary) -> None:
    logger.info(
        "scan complete: scanned=%d flagged=%d refreshed=%d failed=%d",
        summary.scanned,
        summary.flagged,
        summary.refreshed,
        len(summary.failures),
    )
    for name, error_message in summary.failures:
        logger.error("failed to refresh %s: %s", name, error_message)
    if summary.skipped > 0:
        logger.info("scan skipped=%d items this round (per-run refresh cap reached)", summary.skipped)


def run_scan_and_record(state, client, max_refreshes_per_run: int, history_path: str) -> None:
    try:
        try:
            summary = run_once(client, max_refreshes_per_run)
            log_summary(summary)
            result = dataclasses.asdict(summary)
        except JellyfinApiError as error:
            result = {"error": str(error)}

        state.last_result = result
        state.last_run_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        append_history(history_path, result)
    finally:
        state.scanning = False
        state._lock.release()


def run_schedule(client: JellyfinClient, cron_schedule: str, max_refreshes_per_run: int, state, history_path: str) -> None:
    def scan_job():
        if not state.try_start_scan():
            logger.info("skipping scheduled scan: a scan is already in progress")
            return
        run_scan_and_record(state, client, max_refreshes_per_run, history_path)

    scan_job()

    scheduler = BlockingScheduler()
    minute, hour, day, month, day_of_week = cron_schedule.split()
    scheduler.add_job(
        scan_job,
        "cron",
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )
    scheduler.start()


def run_watch(client: JellyfinClient) -> None:
    def on_item_added(item_id: str):
        try:
            client.refresh_item(item_id)
            logger.info("refreshed newly added item %s", item_id)
        except JellyfinApiError as error:
            logger.error("failed to refresh newly added item %s: %s", item_id, error)

    client.listen_for_library_changes(on_item_added)
