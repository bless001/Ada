from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RepositorySnapshot:
    repository_key: str
    commit_sha: str | None
    dirty: bool


class RepositoryPort(Protocol):
    def resolve_path(self, *, repository_key: str, relative_path: str) -> str:
        ...

    async def read_text(self, *, repository_key: str, relative_path: str) -> str:
        ...

    async def snapshot(self, *, repository_key: str) -> RepositorySnapshot:
        ...

    async def diff(self, *, repository_key: str) -> str:
        ...
