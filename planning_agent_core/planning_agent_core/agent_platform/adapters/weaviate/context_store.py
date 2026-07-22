from __future__ import annotations

from planning_agent_core.ports.vector_store import VectorStorePort


class SemanticContextStore(VectorStorePort):
    """Platform-facing semantic context store interface for Weaviate-backed retrieval."""


__all__ = ["SemanticContextStore"]
