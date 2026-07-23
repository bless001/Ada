from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.agent_platform.orchestration.contracts import (
    AgentExecutionRequest,
)
from planning_agent_core.agent_platform.orchestration.flow import (
    AgentFlowResult,
    AgentFlowStatus,
)
from planning_agent_core.agent_platform.orchestration.flow_persistence import (
    AgentFlowApproval,
    AgentFlowNotFoundError,
    AgentFlowVersionConflictError,
    PersistedAgentFlow,
    begin_resume_snapshot,
    close_flow_snapshot,
    complete_run_snapshot,
    reserve_flow_snapshot,
)
from planning_agent_core.models import AgentPlatformFlowRecord


class SqlAlchemyAgentFlowStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def reserve(
        self,
        execution: AgentExecutionRequest,
    ) -> PersistedAgentFlow:
        snapshot = reserve_flow_snapshot(execution)
        record = AgentPlatformFlowRecord(id=snapshot.flow_id)
        _write_snapshot(record, snapshot)
        self.db.add(record)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise AgentFlowVersionConflictError(
                f"Agent flow already exists for workflow: {execution.workflow_id}"
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
        return snapshot

    async def begin_resume(
        self,
        *,
        flow_id: UUID,
        execution: AgentExecutionRequest,
        expected_version: int,
        approval: AgentFlowApproval | None = None,
    ) -> PersistedAgentFlow:
        try:
            record = await self._lock(flow_id)
            current = _read_snapshot(record)
            _check_version(current, expected_version)
            snapshot = begin_resume_snapshot(
                current,
                execution,
                approval=approval,
            )
            _write_snapshot(record, snapshot)
            await self.db.commit()
            return snapshot
        except Exception:
            await self.db.rollback()
            raise

    async def complete_run(
        self,
        *,
        flow_id: UUID,
        result: AgentFlowResult,
        expected_version: int,
    ) -> PersistedAgentFlow:
        try:
            record = await self._lock(flow_id)
            current = _read_snapshot(record)
            _check_version(current, expected_version)
            snapshot = complete_run_snapshot(current, result)
            _write_snapshot(record, snapshot)
            await self.db.commit()
            return snapshot
        except Exception:
            await self.db.rollback()
            raise

    async def close(
        self,
        *,
        flow_id: UUID,
        status: AgentFlowStatus,
        reason: str,
        expected_version: int,
        approval: AgentFlowApproval,
    ) -> PersistedAgentFlow:
        try:
            record = await self._lock(flow_id)
            current = _read_snapshot(record)
            _check_version(current, expected_version)
            snapshot = close_flow_snapshot(
                current,
                status=status,
                reason=reason,
                approval=approval,
            )
            _write_snapshot(record, snapshot)
            await self.db.commit()
            return snapshot
        except Exception:
            await self.db.rollback()
            raise

    async def get(self, flow_id: UUID) -> PersistedAgentFlow | None:
        record = await self.db.get(AgentPlatformFlowRecord, flow_id)
        return _read_snapshot(record) if record is not None else None

    async def _lock(self, flow_id: UUID) -> AgentPlatformFlowRecord:
        record = await self.db.scalar(
            select(AgentPlatformFlowRecord)
            .where(AgentPlatformFlowRecord.id == flow_id)
            .with_for_update()
        )
        if record is None:
            raise AgentFlowNotFoundError(f"Agent flow not found: {flow_id}")
        return record


def _read_snapshot(record: AgentPlatformFlowRecord) -> PersistedAgentFlow:
    return PersistedAgentFlow.model_validate(record.flow_json)


def _write_snapshot(
    record: AgentPlatformFlowRecord,
    snapshot: PersistedAgentFlow,
) -> None:
    pending_execution = snapshot.pending_execution_payload or {}
    pending_request = pending_execution.get("request", {})
    current_step = snapshot.steps[-1] if snapshot.steps else None
    pending_route = snapshot.pending_route
    latest_approval = snapshot.approvals[-1] if snapshot.approvals else None

    record.workflow_id = snapshot.workflow_id
    record.project_key = snapshot.project_id
    record.task_key = snapshot.task_id
    record.status = snapshot.status.value
    record.version = snapshot.version
    record.step_count = snapshot.step_count
    record.current_agent_type = pending_execution.get("agent_type") or (
        current_step.agent_type if current_step else None
    )
    current_execution_id = pending_request.get("execution_id")
    record.current_execution_id = (
        UUID(str(current_execution_id))
        if current_execution_id
        else current_step.execution_id
        if current_step
        else None
    )
    record.pending_action = pending_route.next_action.value if pending_route is not None else None
    record.pending_agent_type = pending_route.next_agent_type if pending_route is not None else None
    record.requires_approval = (
        pending_route.requires_approval if pending_route is not None else False
    )
    record.correlation_id = snapshot.correlation_id
    record.resume_count = snapshot.resume_count
    record.last_approval_decision = (
        latest_approval.decision.value if latest_approval is not None else None
    )
    record.flow_json = snapshot.model_dump(mode="json")
    record.created_at = snapshot.created_at
    record.updated_at = snapshot.updated_at


def _check_version(current: PersistedAgentFlow, expected_version: int) -> None:
    if current.version != expected_version:
        raise AgentFlowVersionConflictError(
            f"Agent flow version conflict: expected {expected_version}, found {current.version}"
        )
