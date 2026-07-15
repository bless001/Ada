from typing import Any
import httpx

from planning_agent_core.config import settings


class OpenProjectClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=f"{settings.openproject_base_url.rstrip('/')}/api/v3",
            auth=("apikey", settings.openproject_api_key),
            headers={"Content-Type": "application/json"},
            timeout=60,
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> dict:
        response = await self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    async def create_project(self, identifier: str, name: str, description: str) -> dict:
        return await self.request("POST", "/projects", json={"identifier": identifier, "name": name, "description": {"format": "markdown", "raw": description}})

    async def list_types(self) -> dict[str, str]:
        data = await self.request("GET", "/types")
        elements = data.get("_embedded", {}).get("elements", [])
        return {e["name"].strip().lower(): e["_links"]["self"]["href"] for e in elements}

    async def close(self) -> None:
        await self.client.aclose()
