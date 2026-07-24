from __future__ import annotations

from pydantic import Field

from planning_agent_core.agent_platform.config.models import AgentConfig


class VerificationAgentConfig(AgentConfig):
    agent_type: str = "verification"
    checkpoint_namespace: str = "verification"
    approval_required: bool = False
    independent_workspace: bool = True
    require_diff_for_pass: bool = True
    require_test_command_for_pass: bool = False
    require_test_evidence_for_source_changes: bool = False
    warning_terms: list[str] = Field(default_factory=lambda: ["todo", "fixme", "temporary", "hack"])
    sensitive_path_patterns: list[str] = Field(
        default_factory=lambda: [
            "auth",
            "security",
            "permission",
            "migration",
            "config",
            ".env",
            "docker-compose",
        ]
    )
    large_change_line_threshold: int = Field(default=500, ge=1)
    large_change_file_threshold: int = Field(default=20, ge=1)
    warn_on_sensitive_changes: bool = False
    warn_on_missing_rollback: bool = False
    security_review_enabled: bool = True
