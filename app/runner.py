from dataclasses import dataclass, field

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
