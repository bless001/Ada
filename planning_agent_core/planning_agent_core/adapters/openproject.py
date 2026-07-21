from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from planning_agent_core.application.openproject_feedback import (
    has_openproject_idempotency_marker,
    markdown_with_idempotency_marker,
    openproject_idempotency_marker,
)
from planning_agent_core.config import settings
from planning_agent_core.ports.openproject import (
    OpenProjectOperationClaim,
    OpenProjectOperationStatus,
    OpenProjectOperationType,
    OpenProjectOutboundStorePort,
)

__all__ = [
    "OpenProjectClient",
    "has_openproject_idempotency_marker",
    "markdown_with_idempotency_marker",
    "openproject_idempotency_marker",
    "resolve_openproject_api_token",
]


def resolve_openproject_api_token(
    *,
    api_key: str | None = None,
    api_token_file: str | None = None,
) -> str:
    if api_token_file and api_token_file.strip():
        token_path = Path(api_token_file)
        if token_path.exists():
            return token_path.read_text(encoding="utf-8").strip()

    if api_key and api_key.strip():
        return api_key.strip()

    return ""


def _api_path_from_href(href: str) -> str:
    parsed = urlparse(href)
    path = parsed.path if parsed.scheme else href
    if path.startswith("/api/v3"):
        path = path.removeprefix("/api/v3")
    return path or "/"


class OpenProjectClient:
    def __init__(
        self,
        *,
        outbound_store: OpenProjectOutboundStorePort | None = None,
        http_client: Any | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_token_file: str | None = None,
        request_timeout_seconds: int | None = None,
    ) -> None:
        self.outbound_store = outbound_store
        self._owns_client = http_client is None
        if http_client is not None:
            self.client = http_client
            return

        token = resolve_openproject_api_token(
            api_key=api_key if api_key is not None else settings.openproject_api_key,
            api_token_file=(
                api_token_file
                if api_token_file is not None
                else settings.openproject_api_token_file
            ),
        )
        self.client = httpx.AsyncClient(
            base_url=f"{(base_url or settings.openproject_base_url).rstrip('/')}/api/v3",
            auth=("apikey", token),
            headers={
                "Accept": "application/hal+json",
                "Content-Type": "application/json",
            },
            timeout=request_timeout_seconds or settings.openproject_request_timeout_seconds,
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    async def create_project(self, identifier: str, name: str, description: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/projects",
            json={
                "identifier": identifier,
                "name": name,
                "description": {"format": "markdown", "raw": description},
            },
        )

    async def list_types(self) -> dict[str, str]:
        data = await self.request("GET", "/types")
        elements = data.get("_embedded", {}).get("elements", [])
        return {e["name"].strip().lower(): e["_links"]["self"]["href"] for e in elements}

    async def get_work_package(self, work_package_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/work_packages/{work_package_id}")

    async def list_work_package_activities(self, work_package_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/work_packages/{work_package_id}/activities")

    async def create_or_update_work_package(
        self,
        *,
        project_id: str,
        external_idempotency_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        store = self._require_outbound_store()
        target_external_id = _work_package_id_from_payload(payload)
        claim = await store.claim_operation(
            idempotency_key=external_idempotency_key,
            operation_type=OpenProjectOperationType.CREATE_OR_UPDATE_WORK_PACKAGE,
            request_payload={"project_id": project_id, "payload": payload},
            target_artifact_type="work_package",
            target_external_id=target_external_id,
        )
        if not claim.should_execute:
            return _skipped_response(claim)

        try:
            if target_external_id:
                response = await self.request(
                    "PATCH",
                    f"/work_packages/{target_external_id}",
                    json=payload,
                )
            else:
                response = await self.request(
                    "POST",
                    f"/projects/{project_id}/work_packages",
                    json=payload,
                )
        except Exception as exc:
            await store.mark_failed(
                idempotency_key=external_idempotency_key,
                error_message=str(exc),
            )
            raise

        await store.mark_succeeded(
            idempotency_key=external_idempotency_key,
            response_payload=response,
        )
        return response

    async def add_comment(
        self,
        *,
        work_package_id: str,
        external_idempotency_key: str,
        markdown: str,
    ) -> dict[str, Any]:
        store = self._require_outbound_store()
        marked_markdown = markdown_with_idempotency_marker(
            markdown,
            external_idempotency_key,
        )
        claim = await store.claim_operation(
            idempotency_key=external_idempotency_key,
            operation_type=OpenProjectOperationType.ADD_COMMENT,
            request_payload={
                "work_package_id": work_package_id,
                "markdown": marked_markdown,
            },
            target_artifact_type="work_package",
            target_external_id=work_package_id,
        )
        if not claim.should_execute:
            return _skipped_response(claim)

        try:
            work_package = await self.get_work_package(work_package_id)
            add_comment_href = (
                work_package.get("_links", {})
                .get("addComment", {})
                .get("href")
            )
            if not add_comment_href:
                raise RuntimeError("The bot cannot add a comment to this work package.")

            response = await self.request(
                "POST",
                _api_path_from_href(add_comment_href),
                json={"comment": {"raw": marked_markdown}},
            )
        except Exception as exc:
            await store.mark_failed(
                idempotency_key=external_idempotency_key,
                error_message=str(exc),
            )
            raise

        await store.mark_succeeded(
            idempotency_key=external_idempotency_key,
            response_payload=response,
        )
        return response

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _require_outbound_store(self) -> OpenProjectOutboundStorePort:
        if self.outbound_store is None:
            raise RuntimeError(
                "OpenProject outbound_store is required for idempotent mutations"
            )
        return self.outbound_store


def _work_package_id_from_payload(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("work_package_id")
    if value is None:
        return None
    return str(value)


def _skipped_response(claim: OpenProjectOperationClaim) -> dict[str, Any]:
    if claim.status == OpenProjectOperationStatus.SUCCEEDED and claim.response_payload is not None:
        return claim.response_payload
    return {
        "idempotency_key": claim.idempotency_key,
        "operation_type": claim.operation_type.value,
        "status": claim.status.value,
        "skipped": True,
        "error_message": claim.error_message,
    }
