from app.scanner import is_missing_metadata, find_items_missing_metadata, describe_missing_reasons


def make_item(**overrides):
    item = {
        "Id": "item-1",
        "Name": "Some Movie",
        "Overview": "A great movie about things.",
        "ImageTags": {"Primary": "abc123"},
    }
    item.update(overrides)
    return item


def test_complete_item_is_not_missing():
    item = make_item()
    assert is_missing_metadata(item) is False


def test_missing_poster_is_flagged():
    item = make_item(ImageTags={})
    assert is_missing_metadata(item) is True


def test_missing_image_tags_key_entirely_is_flagged():
    item = make_item()
    del item["ImageTags"]
    assert is_missing_metadata(item) is True


def test_missing_overview_key_is_flagged():
    item = make_item()
    del item["Overview"]
    assert is_missing_metadata(item) is True


def test_empty_overview_string_is_flagged():
    item = make_item(Overview="")
    assert is_missing_metadata(item) is True


def test_whitespace_only_overview_is_flagged():
    item = make_item(Overview="   ")
    assert is_missing_metadata(item) is True


def test_find_items_missing_metadata_filters_list():
    complete = make_item(Id="complete-1")
    missing_poster = make_item(Id="missing-poster-1", ImageTags={})
    missing_overview = make_item(Id="missing-overview-1", Overview="")

    result = find_items_missing_metadata([complete, missing_poster, missing_overview])

    result_ids = {item["Id"] for item in result}
    assert result_ids == {"missing-poster-1", "missing-overview-1"}


def test_describe_missing_reasons_returns_empty_for_complete_item():
    item = make_item()
    assert describe_missing_reasons(item) == []


def test_describe_missing_reasons_flags_poster_only():
    item = make_item(ImageTags={})
    assert describe_missing_reasons(item) == ["poster"]


def test_describe_missing_reasons_flags_overview_only():
    item = make_item(Overview="")
    assert describe_missing_reasons(item) == ["overview"]


def test_describe_missing_reasons_flags_both():
    item = make_item(ImageTags={}, Overview="")
    assert describe_missing_reasons(item) == ["poster", "overview"]
