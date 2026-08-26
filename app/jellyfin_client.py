import requests


class JellyfinApiError(Exception):
    pass


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {"X-Emby-Token": self.api_key}

    def get_all_items(self) -> list[dict]:
        url = f"{self.base_url}/Items"
        params = {
            "Recursive": True,
            "Fields": "Overview",
        }
        response = self.session.get(url, params=params, headers=self._headers(), timeout=30)
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
        response = self.session.post(url, params=params, headers=self._headers(), timeout=30)
        if response.status_code not in (200, 204):
            raise JellyfinApiError(
                f"POST {url} failed with status {response.status_code}: {response.text}"
            )
