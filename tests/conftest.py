from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    package_root = repo_root / "planning_agent_core"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
