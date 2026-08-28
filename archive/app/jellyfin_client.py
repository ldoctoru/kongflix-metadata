import json
import logging
from typing import Callable

import requests
import websocket

logger = logging.getLogger(__name__)


class JellyfinApiError(Exception):
    pass


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session or requests.Session()
        self._ws_app_factory = websocket.WebSocketApp

    def _headers(self) -> dict:
        return {"X-Emby-Token": self.api_key}

    def get_all_items(self) -> list[dict]:
        url = f"{self.base_url}/Items"
        params = {
            "Recursive": True,
            "Fields": "Overview,SeriesName,ParentIndexNumber",
        }
        try:
            response = self.session.get(url, params=params, headers=self._headers(), timeout=30)
        except requests.exceptions.RequestException as error:
            raise JellyfinApiError(str(error)) from error
        if response.status_code != 200:
            raise JellyfinApiError(
                f"GET {url} failed with status {response.status_code}: {response.text}"
            )
        return response.json().get("Items", [])

    def refresh_item(self, item_id: str) -> None:
        url = f"{self.base_url}/Items/{item_id}/Refresh"
        params = {
            "MetadataRefreshMode": "FullRefresh",
            "ImageRefreshMode": "FullRefresh",
            "ReplaceAllMetadata": "false",
            "ReplaceAllImages": "false",
        }
        try:
            response = self.session.post(url, params=params, headers=self._headers(), timeout=30)
        except requests.exceptions.RequestException as error:
            raise JellyfinApiError(str(error)) from error
        if response.status_code not in (200, 204):
            raise JellyfinApiError(
                f"POST {url} failed with status {response.status_code}: {response.text}"
            )

    def listen_for_library_changes(self, on_item_added: Callable[[str], None]) -> None:
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/socket?api_key={self.api_key}"

        def on_message(ws, message):
            data = json.loads(message)
            if data.get("MessageType") != "LibraryChanged":
                return
            items_added = data.get("Data", {}).get("ItemsAdded", [])
            for item_id in items_added:
                on_item_added(item_id)

        def on_error(ws, error):
            logger.error("websocket error: %s", error)

        def on_close(ws, close_status_code, close_msg):
            logger.warning("websocket closed: code=%s msg=%s", close_status_code, close_msg)

        ws_app = self._ws_app_factory(ws_url, on_message=on_message, on_error=on_error, on_close=on_close)
        ws_app.run_forever(reconnect=5)
