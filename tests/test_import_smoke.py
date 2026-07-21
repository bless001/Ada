from __future__ import annotations

import importlib
from pathlib import Path


CORE_MODULES = [
    "planning_agent_core.main",
    "planning_agent_core.models",
    "planning_agent_core.schemas",
    "planning_agent_core.skills",
    "planning_agent_core.workflow.graph",
    "planning_agent_core.workflow.runner",
    "planning_agent_core.workflow.state",
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
