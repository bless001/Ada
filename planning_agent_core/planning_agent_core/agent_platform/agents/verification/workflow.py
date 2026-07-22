from __future__ import annotations

from planning_agent_core.agent_platform.agents.verification.config import VerificationAgentConfig


VERIFICATION_WORKFLOW_STEPS: tuple[str, ...] = (
    "load_task_acceptance_criteria",
    "load_coding_result",
    "inspect_repository_diff",
    "run_relevant_tests",
    "evaluate_acceptance_criteria",
    "review_regression_risk",
    "return_verdict",
)


def build_verification_agent_workflow(config: VerificationAgentConfig) -> tuple[str, ...]:
    return VERIFICATION_WORKFLOW_STEPS
