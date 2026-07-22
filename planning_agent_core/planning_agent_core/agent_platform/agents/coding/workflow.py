from __future__ import annotations

from planning_agent_core.agent_platform.agents.coding.config import CodingAgentConfig


CODING_WORKFLOW_STEPS: tuple[str, ...] = (
    "load_task_context",
    "inspect_repository",
    "policy_check",
    "apply_patch",
    "run_quality_checks",
    "capture_evidence",
    "decide_retry_or_handoff",
)


def build_coding_agent_workflow(config: CodingAgentConfig) -> tuple[str, ...]:
    return CODING_WORKFLOW_STEPS
