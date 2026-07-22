from __future__ import annotations

import importlib
from pathlib import Path


CORE_MODULES = [
    "planning_agent_core.main",
    "planning_agent_core.models",
    "planning_agent_core.schemas",
    "planning_agent_core.api.events",
    "planning_agent_core.application.project_orchestrator",
    "planning_agent_core.skills",
    "planning_agent_core.skills.context_capsule",
    "planning_agent_core.skills.implementation_status_classification",
    "planning_agent_core.skills.neo4j_projection",
    "planning_agent_core.skills.openproject_projection",
    "planning_agent_core.skills.plan_validation",
    "planning_agent_core.skills.repository_inspection",
    "planning_agent_core.skills.requirement_extraction",
    "planning_agent_core.skills.weaviate_projection",
    "planning_agent_core.workflow.graph",
    "planning_agent_core.workflow.persistence_setup",
    "planning_agent_core.workflow.runner",
    "planning_agent_core.workflow.state",
    "planning_agent_core.ports.executions",
    "planning_agent_core.persistence.executions",
    "planning_agent_core.adapters.command_runner",
    "planning_agent_core.adapters.lsp",
    "planning_agent_core.adapters.neo4j_store",
    "planning_agent_core.adapters.repository_analysis",
    "planning_agent_core.adapters.repository_filesystem",
    "planning_agent_core.adapters.tree_sitter_analysis",
    "planning_agent_core.adapters.weaviate_store",
    "planning_agent_core.api.repositories",
    "planning_agent_core.domain.code_analysis",
    "planning_agent_core.domain.coding",
    "planning_agent_core.domain.repositories",
    "planning_agent_core.ports.coding_attempts",
    "planning_agent_core.ports.repository_analysis",
    "planning_agent_core.persistence.coding_attempts",
    "planning_agent_core.persistence.agent_platform",
    "planning_agent_core.services.coding_service",
    "planning_agent_core.services.agent_platform_service",
    "planning_agent_core.services.repository_analysis_service",
    "planning_agent_core.services.repository_projection_service",
    "planning_agent_core.services.repository_write_tracker",
    "planning_agent_core.agent_platform",
    "planning_agent_core.agent_platform.adapters",
    "planning_agent_core.agent_platform.agents.base",
    "planning_agent_core.agent_platform.agents.planning",
    "planning_agent_core.agent_platform.agents.coding",
    "planning_agent_core.agent_platform.agents.verification",
    "planning_agent_core.agent_platform.config",
    "planning_agent_core.agent_platform.factory",
    "planning_agent_core.agent_platform.orchestration",
    "planning_agent_core.agent_platform.runtime",
]


def test_planning_agent_core_modules_import(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root / "planning_agent_core"))

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://coding_agent:change-me@localhost:5432/coding_agent",
    )
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("LLM_MODEL", "local-coding-model")
    monkeypatch.setenv("LLM_API_KEY", "local-not-secret")
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "http://localhost:8081")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "placeholder-key")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "change-me")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")

    for module_name in CORE_MODULES:
        importlib.import_module(module_name)
