"""
Indexing Modes

인덱싱 모드별 설정 및 동작을 정의합니다.
"""

from enum import Enum


class IndexingMode(str, Enum):
    """인덱싱 모드"""

    # Core modes
    FAST = "fast"  # AST + IR + Basic chunks (no embedding)
    BALANCED = "balanced"  # + Semantic IR + Graph + Embedding (priority queue)
    DEEP = "deep"  # + Full embedding + RepoMap + Domain
    BOOTSTRAP = "bootstrap"  # Initial full indexing
    REPAIR = "repair"  # Consistency repair + orphan cleanup

    # Background jobs (Phase 2+)
    EMBEDDING_REFRESH = "embedding_refresh"  # 오래된 embedding 재생성
    REPOMAP_REBUILD = "repomap_rebuild"  # RepoMap 재계산


class IndexingTrigger(str, Enum):
    """인덱싱 트리거 타입"""

    MANUAL = "manual"  # CLI/API 직접 호출
    GIT_COMMIT = "git_commit"  # Git commit hook
    GIT_CHECKOUT = "git_checkout"  # Branch checkout
    GIT_PULL = "git_pull"  # Git pull
    FS_EVENT = "fs_event"  # File system watcher
    IDE_SAVE = "ide_save"  # IDE overlay save
    SCHEDULED = "scheduled"  # Cron/scheduled job
    PR_EVENT = "pr_event"  # PR opened/updated
