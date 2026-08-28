import json
import os


def load_history(path: str) -> list[dict]:
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return data


def append_history(path: str, entry: dict, max_entries: int = 20) -> None:
    entries = load_history(path)
    entries.append(entry)
    entries = entries[-max_entries:]
    with open(path, "w") as f:
        json.dump(entries, f)


def save_missing_items(path: str, items: list) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(items, f)
    os.replace(tmp_path, path)


def load_missing_items(path: str) -> list:
    return load_history(path)
