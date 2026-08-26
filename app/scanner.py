def is_missing_metadata(item: dict) -> bool:
    image_tags = item.get("ImageTags") or {}
    has_poster = bool(image_tags.get("Primary"))

    overview = item.get("Overview") or ""
    has_overview = bool(overview.strip())

    return not has_poster or not has_overview


def find_items_missing_metadata(items: list[dict]) -> list[dict]:
    return [item for item in items if is_missing_metadata(item)]
