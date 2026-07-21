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
from planning_agent_core.application.openproject_mapping import OpenProjectResourceCatalog
from planning_agent_core.application.openproject_reconciliation import (
    detect_human_edit_summary,
)
from planning_agent_core.config import settings
from planning_agent_core.ports.openproject import (
    OpenProjectOperationClaim,
    OpenProjectOperationStatus,
    OpenProjectOperationType,
    OpenProjectOutboundStorePort,
    OpenProjectReconciliationStorePort,
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
        reconciliation_store: OpenProjectReconciliationStorePort | None = None,
        http_client: Any | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_token_file: str | None = None,
        request_timeout_seconds: int | None = None,
    ) -> None:
        self.outbound_store = outbound_store
        self.reconciliation_store = reconciliation_store
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
        return _hal_elements_by_name(data)

    async def list_statuses(self) -> dict[str, str]:
        data = await self.request("GET", "/statuses")
        return _hal_elements_by_name(data)

    async def list_priorities(self) -> dict[str, str]:
        data = await self.request("GET", "/priorities")
        return _hal_elements_by_name(data)

    async def load_resource_catalog(self) -> OpenProjectResourceCatalog:
        return OpenProjectResourceCatalog(
            type_hrefs=await self.list_types(),
            status_hrefs=await self.list_statuses(),
            priority_hrefs=await self.list_priorities(),
        )

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
                before_payload = await self.get_work_package(target_external_id)
                before_activities_payload = await self.list_work_package_activities(
                    target_external_id
                )
                await self._record_reconciliation_snapshot(
                    outbound_idempotency_key=external_idempotency_key,
                    operation_type=OpenProjectOperationType.CREATE_OR_UPDATE_WORK_PACKAGE,
                    target_artifact_type="work_package",
                    target_external_id=target_external_id,
                    before_payload=before_payload,
                    before_activities_payload=before_activities_payload,
                    agent_payload=payload,
                )
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
            await self._record_reconciliation_snapshot(
                outbound_idempotency_key=external_idempotency_key,
                operation_type=OpenProjectOperationType.ADD_COMMENT,
                target_artifact_type="work_package",
                target_external_id=work_package_id,
                before_payload=work_package,
                agent_payload={
                    "comment": {
                        "raw": marked_markdown,
                    }
                },
            )
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

    async def _record_reconciliation_snapshot(
        self,
        *,
        outbound_idempotency_key: str,
        operation_type: OpenProjectOperationType,
        target_artifact_type: str,
        target_external_id: str,
        before_payload: dict[str, Any],
        agent_payload: dict[str, Any],
        before_activities_payload: dict[str, Any] | None = None,
    ) -> None:
        if self.reconciliation_store is None:
            return
        await self.reconciliation_store.record_snapshot(
            outbound_idempotency_key=outbound_idempotency_key,
            operation_type=operation_type,
            target_artifact_type=target_artifact_type,
            target_external_id=target_external_id,
            before_payload=before_payload,
            before_activities_payload=before_activities_payload,
            agent_payload=agent_payload,
            detected_human_edits=detect_human_edit_summary(
                before_payload=before_payload,
                agent_payload=agent_payload,
            ),
        )


def _work_package_id_from_payload(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("work_package_id")
    if value is None:
        return None
    return str(value)


def _hal_elements_by_name(data: dict[str, Any]) -> dict[str, str]:
    elements = data.get("_embedded", {}).get("elements", [])
    return {
        item["name"].strip(): item["_links"]["self"]["href"]
        for item in elements
        if item.get("name") and item.get("_links", {}).get("self", {}).get("href")
    }


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
