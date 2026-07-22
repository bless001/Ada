from __future__ import annotations

from planning_agent_core.ports.openproject import OpenProjectPort


class WorkPackageGateway(OpenProjectPort):
    """Platform-facing OpenProject gateway for work package synchronization."""


__all__ = ["WorkPackageGateway"]
