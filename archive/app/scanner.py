def describe_missing_reasons(item: dict) -> list[str]:
    reasons = []

    image_tags = item.get("ImageTags") or {}
    if not image_tags.get("Primary"):
        reasons.append("poster")

    overview = item.get("Overview") or ""
    if not overview.strip():
        reasons.append("overview")

    return reasons


def is_missing_metadata(item: dict) -> bool:
    return bool(describe_missing_reasons(item))


def find_items_missing_metadata(items: list[dict]) -> list[dict]:
    return [item for item in items if is_missing_metadata(item)]
