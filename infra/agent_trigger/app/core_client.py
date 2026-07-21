from typing import Any

import httpx


class CoreOrchestrationClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def orchestrate_event(self, event_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/v1/events/{event_id}/orchestrate"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url)
            response.raise_for_status()
            return response.json()
