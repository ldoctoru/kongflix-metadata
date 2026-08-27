import dataclasses
import datetime
import logging
from dataclasses import dataclass, field

from apscheduler.schedulers.blocking import BlockingScheduler

from app.history import append_history, save_missing_items
from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.scanner import describe_missing_reasons, find_items_missing_metadata


@dataclass(eq=True)
class ScanSummary:
    scanned: int
    flagged: int
    refreshed: int
    failures: list = field(default_factory=list)
    skipped: int = 0


def run_once(client: JellyfinClient, max_refreshes_per_run: int = 200) -> tuple[ScanSummary, list]:
    items = client.get_all_items()
    flagged_items = find_items_missing_metadata(items)

    items_to_refresh = flagged_items[:max_refreshes_per_run]
    pending_items = flagged_items[max_refreshes_per_run:]
    skipped = len(pending_items)

    refreshed = 0
    failures = []
    missing_items = []

    for item in items_to_refresh:
        reasons = describe_missing_reasons(item)
        try:
            client.refresh_item(item["Id"])
            refreshed += 1
            status = "refreshed"
        except JellyfinApiError as error:
            failures.append((item.get("Name", item["Id"]), str(error)))
            status = "failed"
        missing_items.append({
            "id": item.get("Id"),
            "name": item.get("Name", item.get("Id")),
            "type": item.get("Type", "Unknown"),
            "missing": reasons,
            "status": status,
        })

    for item in pending_items:
        missing_items.append({
            "id": item.get("Id"),
            "name": item.get("Name", item.get("Id")),
            "type": item.get("Type", "Unknown"),
            "missing": describe_missing_reasons(item),
            "status": "pending",
        })

    summary = ScanSummary(
        scanned=len(items),
        flagged=len(flagged_items),
        refreshed=refreshed,
        failures=failures,
        skipped=skipped,
    )
    return summary, missing_items


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


def run_scan_and_record(state, client, max_refreshes_per_run: int, history_path: str, missing_items_path: str) -> None:
    try:
        missing_items = None
        try:
            summary, missing_items = run_once(client, max_refreshes_per_run)
            log_summary(summary)
            result = dataclasses.asdict(summary)
        except JellyfinApiError as error:
            result = {"error": str(error)}

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result["timestamp"] = timestamp

        state.last_result = result
        state.last_run_at = timestamp
        append_history(history_path, result)

        if missing_items is not None:
            save_missing_items(missing_items_path, missing_items)
    finally:
        state.scanning = False
        state._lock.release()


def run_schedule(client: JellyfinClient, cron_schedule: str, max_refreshes_per_run: int, state, history_path: str, missing_items_path: str) -> None:
    def scan_job():
        if not state.try_start_scan():
            logger.info("skipping scheduled scan: a scan is already in progress")
            return
        run_scan_and_record(state, client, max_refreshes_per_run, history_path, missing_items_path)

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
