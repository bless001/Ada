from __future__ import annotations

from typing import Any, Protocol


class OpenProjectPort(Protocol):
    async def get_work_package(self, work_package_id: str) -> dict[str, Any]:
        ...

    async def list_work_package_activities(self, work_package_id: str) -> dict[str, Any]:
        ...

    async def create_or_update_work_package(
        self,
        *,
        project_id: str,
        external_idempotency_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    async def add_comment(
        self,
        *,
        work_package_id: str,
        external_idempotency_key: str,
        markdown: str,
    ) -> dict[str, Any]:
        ...
