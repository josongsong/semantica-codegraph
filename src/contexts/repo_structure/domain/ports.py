"""
Repo Structure Domain Ports
"""

from pathlib import Path
from typing import Protocol

from .models import RepoMap


class RepoMapStorePort(Protocol):
    """RepoMap 저장소 포트"""

    async def save(self, repomap: RepoMap) -> None: ...

    async def load(self, repo_id: str) -> RepoMap | None: ...


class RepoMapBuilderPort(Protocol):
    """RepoMap 빌더 포트"""

    async def build(self, repo_path: Path, repo_id: str) -> RepoMap: ...
