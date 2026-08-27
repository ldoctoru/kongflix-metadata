import json

from app.history import append_history, load_history, load_missing_items, save_missing_items


def test_load_history_returns_empty_list_when_file_missing(tmp_path):
    path = str(tmp_path / "does-not-exist.json")
    assert load_history(path) == []


def test_load_history_returns_empty_list_on_invalid_json(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("not valid json{{{")
    assert load_history(str(path)) == []


def test_append_history_creates_file_with_one_entry(tmp_path):
    path = str(tmp_path / "history.json")
    append_history(path, {"scanned": 5})
    assert load_history(path) == [{"scanned": 5}]


def test_append_history_appends_to_existing_entries(tmp_path):
    path = str(tmp_path / "history.json")
    append_history(path, {"scanned": 1})
    append_history(path, {"scanned": 2})
    assert load_history(path) == [{"scanned": 1}, {"scanned": 2}]


def test_append_history_caps_at_max_entries_dropping_oldest(tmp_path):
    path = str(tmp_path / "history.json")
    for i in range(5):
        append_history(path, {"scanned": i}, max_entries=3)
    assert load_history(path) == [{"scanned": 2}, {"scanned": 3}, {"scanned": 4}]


def test_save_missing_items_creates_file(tmp_path):
    path = str(tmp_path / "missing.json")
    save_missing_items(path, [{"id": "1"}])
    assert load_missing_items(path) == [{"id": "1"}]


def test_save_missing_items_overwrites_not_appends(tmp_path):
    path = str(tmp_path / "missing.json")
    save_missing_items(path, [{"id": "1"}])
    save_missing_items(path, [{"id": "2"}])
    assert load_missing_items(path) == [{"id": "2"}]


def test_load_missing_items_returns_empty_list_when_file_missing(tmp_path):
    path = str(tmp_path / "does-not-exist.json")
    assert load_missing_items(path) == []


def test_load_missing_items_returns_empty_list_on_invalid_json(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("not valid json{{{")
    assert load_missing_items(str(path)) == []
