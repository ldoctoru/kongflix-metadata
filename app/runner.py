import logging
from dataclasses import dataclass, field

from apscheduler.schedulers.blocking import BlockingScheduler

from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.scanner import find_items_missing_metadata


@dataclass(eq=True)
class ScanSummary:
    scanned: int
    flagged: int
    refreshed: int
    failures: list = field(default_factory=list)


def run_once(client: JellyfinClient) -> ScanSummary:
    items = client.get_all_items()
    flagged_items = find_items_missing_metadata(items)

    refreshed = 0
    failures = []

    for item in flagged_items:
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


def run_schedule(client: JellyfinClient, cron_schedule: str) -> None:
    def scan_job():
        summary = run_once(client)
        log_summary(summary)

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
