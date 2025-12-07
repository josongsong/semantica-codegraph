"""
Index Repository Command

리포지토리 인덱싱 명령 (CQRS Command)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexRepositoryCommand:
    """리포지토리 인덱싱 명령"""

    repo_id: str
    mode: str  # "full" or "incremental"
    file_paths: list[str]
    snapshot_id: str | None = None
