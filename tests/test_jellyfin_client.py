import json
from unittest.mock import MagicMock

import pytest

from app.jellyfin_client import JellyfinClient, JellyfinApiError


def make_client(session):
    return JellyfinClient(base_url="http://jellyfin.local:8096", api_key="test-key", session=session)


def test_get_all_items_calls_correct_endpoint_and_returns_items():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"Items": [{"Id": "1"}, {"Id": "2"}]}
    session.get.return_value = response

    client = make_client(session)
    items = client.get_all_items()

    assert items == [{"Id": "1"}, {"Id": "2"}]
    session.get.assert_called_once()
    call_args = session.get.call_args
    assert call_args.args[0] == "http://jellyfin.local:8096/Items"
    assert call_args.kwargs["params"]["Recursive"] is True
    assert call_args.kwargs["headers"]["X-Emby-Token"] == "test-key"


def test_get_all_items_raises_on_error_status():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 500
    response.text = "server error"
    session.get.return_value = response

    client = make_client(session)

    with pytest.raises(JellyfinApiError):
        client.get_all_items()


def test_refresh_item_calls_correct_endpoint_with_params():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 204
    session.post.return_value = response

    client = make_client(session)
    client.refresh_item("item-123")

    session.post.assert_called_once()
    call_args = session.post.call_args
    assert call_args.args[0] == "http://jellyfin.local:8096/Items/item-123/Refresh"
    params = call_args.kwargs["params"]
    assert params["MetadataRefreshMode"] == "FullRefresh"
    assert params["ImageRefreshMode"] == "FullRefresh"
    assert params["ReplaceAllMetadata"] == "false"
    assert params["ReplaceAllImages"] == "false"
    assert call_args.kwargs["headers"]["X-Emby-Token"] == "test-key"


def test_refresh_item_raises_on_error_status():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 404
    response.text = "not found"
    session.post.return_value = response

    client = make_client(session)

    with pytest.raises(JellyfinApiError):
        client.refresh_item("missing-item")


def test_listen_for_library_changes_invokes_callback_for_added_items():
    session = MagicMock()
    client = make_client(session)

    received = []
    fake_ws_app = MagicMock()

    def fake_ws_app_factory(url, on_message, on_error, on_close):
        fake_ws_app.on_message = on_message
        return fake_ws_app

    client._ws_app_factory = fake_ws_app_factory

    client.listen_for_library_changes(lambda item_id: received.append(item_id))

    message = json.dumps({
        "MessageType": "LibraryChanged",
        "Data": {"ItemsAdded": ["item-a", "item-b"], "ItemsUpdated": []},
    })
    fake_ws_app.on_message(fake_ws_app, message)

    assert received == ["item-a", "item-b"]
    fake_ws_app.run_forever.assert_called_once()


def test_listen_for_library_changes_ignores_other_message_types():
    session = MagicMock()
    client = make_client(session)

    received = []
    fake_ws_app = MagicMock()

    def fake_ws_app_factory(url, on_message, on_error, on_close):
        fake_ws_app.on_message = on_message
        return fake_ws_app

    client._ws_app_factory = fake_ws_app_factory

    client.listen_for_library_changes(lambda item_id: received.append(item_id))

    message = json.dumps({"MessageType": "SessionsStart", "Data": {}})
    fake_ws_app.on_message(fake_ws_app, message)

    assert received == []
