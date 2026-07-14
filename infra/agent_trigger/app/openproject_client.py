from typing import Any

import httpx


class OpenProjectClient:
    def __init__(self, base_url: str, api_token: str, host_header: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.host_header = host_header

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/hal+json",
            "Content-Type": "application/json",
        }

        if self.host_header:
            headers["Host"] = self.host_header

        return headers

    def _auth(self):
        return ("apikey", self.api_token)

    def get_work_package(self, work_package_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v3/work_packages/{work_package_id}"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=self._headers(), auth=self._auth())
            response.raise_for_status()
            return response.json()

    def list_work_package_activities(self, work_package_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v3/work_packages/{work_package_id}/activities"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=self._headers(), auth=self._auth())
            response.raise_for_status()
            return response.json()

    def add_comment(self, work_package: dict[str, Any], comment_markdown: str) -> None:
        add_comment_link = (
            work_package.get("_links", {})
            .get("addComment", {})
            .get("href")
        )

        if not add_comment_link:
            raise RuntimeError("The bot cannot add a comment to this work package.")

        url = f"{self.base_url}{add_comment_link}"
        payload = {"comment": {"raw": comment_markdown}}

        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                url,
                headers=self._headers(),
                auth=self._auth(),
                json=payload,
            )
            response.raise_for_status()