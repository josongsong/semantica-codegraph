"""
VerificationSnapshot Factory (RFC-SEM-022)

결정적(Deterministic) 실행을 위한 스냅샷 자동 생성.

SOTA Features:
- 룰셋/정책 해시 자동 계산
- Git revision 자동 추출
- 인덱스 스냅샷 ID 연동
- 캐싱으로 중복 계산 방지

Architecture:
- Port/Adapter Pattern
- Immutable Snapshots
- Content-addressable (Hash-based)
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts import VerificationSnapshot

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.chunk.store_protocol import ChunkStoreProtocol

logger = get_logger(__name__)

# Engine version (Semantic Versioning)
ENGINE_VERSION = "2.5.0"


# ============================================================
# Ports (Hexagonal Architecture)
# ============================================================


class RulesetLoaderPort(Protocol):
    """룰셋 로더 포트."""

    async def load_ruleset(self, path: str) -> str:
        """룰셋 내용 로드."""
        ...

    async def load_policies(self, path: str) -> str:
        """정책 내용 로드."""
        ...


class IndexSnapshotPort(Protocol):
    """인덱스 스냅샷 포트."""

    async def get_snapshot_id(self, workspace_id: str) -> str:
        """현재 인덱스 스냅샷 ID 조회."""
        ...


class GitResolverPort(Protocol):
    """Git Resolver 포트."""

    async def get_revision(self, repo_path: str) -> str:
        """현재 Git revision (commit SHA) 조회."""
        ...


# ============================================================
# Adapters (Infrastructure)
# ============================================================


class FileSystemRulesetLoader:
    """파일시스템 기반 룰셋 로더."""

    def __init__(self, base_path: Path | None = None):
        self._base_path = base_path or Path.cwd()

    async def load_ruleset(self, path: str) -> str:
        """룰셋 디렉토리의 모든 YAML 파일 내용 연결."""
        ruleset_path = self._base_path / path
        contents = []

        if ruleset_path.exists():
            for yaml_file in sorted(ruleset_path.glob("**/*.yaml")):
                try:
                    contents.append(yaml_file.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"Failed to read {yaml_file}: {e}")

        return "\n---\n".join(contents) if contents else ""

    async def load_policies(self, path: str) -> str:
        """정책 디렉토리의 모든 YAML 파일 내용 연결."""
        return await self.load_ruleset(path)


class ChunkStoreIndexSnapshot:
    """ChunkStore 기반 인덱스 스냅샷."""

    def __init__(self, chunk_store: ChunkStoreProtocol | None = None):
        self._chunk_store = chunk_store

    async def get_snapshot_id(self, workspace_id: str) -> str:
        """
        인덱스 스냅샷 ID 생성.

        ChunkStore가 있으면 실제 스냅샷 ID,
        없으면 workspace_id 기반 ID 반환.
        """
        if self._chunk_store is None:
            # Fallback: workspace 기반 ID
            return f"index_{workspace_id[:12]}"

        try:
            # ChunkStore에서 메타데이터 조회
            if hasattr(self._chunk_store, "get_snapshot_id"):
                return await self._chunk_store.get_snapshot_id(workspace_id)

            # Fallback: 청크 수 기반 해시
            if hasattr(self._chunk_store, "count"):
                count = await self._chunk_store.count(workspace_id)
                return f"index_v{count:08d}"

        except Exception as e:
            logger.warning(f"Failed to get snapshot ID: {e}")

        return f"index_{workspace_id[:12]}"


class GitRevisionResolver:
    """Git revision 리졸버."""

    def __init__(self, repo_path: Path | None = None):
        self._repo_path = repo_path or Path.cwd()
        self._cache: dict[str, str] = {}

    async def get_revision(self, repo_path: str | None = None) -> str:
        """
        현재 Git HEAD commit SHA 조회.

        캐싱으로 반복 호출 최적화.
        """
        target_path = Path(repo_path) if repo_path else self._repo_path

        # 캐시 확인
        cache_key = str(target_path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # git rev-parse HEAD 실행
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "rev-parse", "HEAD"],
                cwd=target_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                revision = result.stdout.strip()
                self._cache[cache_key] = revision
                return revision

        except subprocess.TimeoutExpired:
            logger.warning("Git rev-parse timed out")
        except FileNotFoundError:
            logger.warning("Git not found")
        except Exception as e:
            logger.warning(f"Failed to get git revision: {e}")

        # Fallback: 타임스탬프 기반
        import time

        fallback = f"unknown_{int(time.time())}"
        self._cache[cache_key] = fallback
        return fallback


# ============================================================
# Domain Service: SnapshotFactory
# ============================================================


@dataclass
class SnapshotFactoryConfig:
    """SnapshotFactory 설정."""

    engine_version: str = ENGINE_VERSION
    ruleset_path: str = "cwe/catalog"
    policies_path: str = "cwe/catalog/policies"
    enable_caching: bool = True
    cache_ttl_seconds: int = 300  # 5분


class SnapshotFactory:
    """
    VerificationSnapshot 자동 생성 Factory.

    RFC-SEM-022 Section 3: Determinism Contract
    - 동일 engine_version
    - 동일 ruleset_hash / policies_hash
    - 동일 index_snapshot_id
    - 동일 repo_revision
    → 동일 결과 보장

    SOTA Features:
    - Content-addressable hashing
    - Lazy loading with caching
    - Parallel async operations
    - Fallback strategies
    """

    def __init__(
        self,
        config: SnapshotFactoryConfig | None = None,
        ruleset_loader: RulesetLoaderPort | None = None,
        index_snapshot: IndexSnapshotPort | None = None,
        git_resolver: GitResolverPort | None = None,
    ):
        """
        Initialize factory with optional adapters.

        Args:
            config: Factory 설정
            ruleset_loader: 룰셋 로더 (default: FileSystem)
            index_snapshot: 인덱스 스냅샷 (default: ChunkStore)
            git_resolver: Git 리졸버 (default: subprocess)
        """
        self._config = config or SnapshotFactoryConfig()
        self._ruleset_loader = ruleset_loader or FileSystemRulesetLoader()
        self._index_snapshot = index_snapshot or ChunkStoreIndexSnapshot()
        self._git_resolver = git_resolver or GitRevisionResolver()

        # Cache for computed hashes
        self._hash_cache: dict[str, tuple[str, float]] = {}

    @property
    def engine_version(self) -> str:
        """현재 엔진 버전."""
        return self._config.engine_version

    async def create(
        self,
        repo_id: str,
        workspace_id: str,
        ruleset_path: str | None = None,
        policies_path: str | None = None,
    ) -> VerificationSnapshot:
        """
        결정적 실행 스냅샷 자동 생성.

        Parallel execution으로 성능 최적화:
        1. Ruleset hash (async)
        2. Policies hash (async)
        3. Index snapshot ID (async)
        4. Git revision (async)

        Args:
            repo_id: 저장소 ID
            workspace_id: 워크스페이스 ID
            ruleset_path: 룰셋 경로 (optional)
            policies_path: 정책 경로 (optional)

        Returns:
            VerificationSnapshot (immutable)
        """
        ruleset_path = ruleset_path or self._config.ruleset_path
        policies_path = policies_path or self._config.policies_path

        # Parallel async execution
        ruleset_task = self._get_ruleset_hash(ruleset_path)
        policies_task = self._get_policies_hash(policies_path)
        index_task = self._index_snapshot.get_snapshot_id(workspace_id)
        revision_task = self._git_resolver.get_revision(None)

        results = await asyncio.gather(
            ruleset_task,
            policies_task,
            index_task,
            revision_task,
            return_exceptions=True,
        )

        # Handle results with fallbacks
        ruleset_hash = results[0] if not isinstance(results[0], Exception) else "sha256:unknown"
        policies_hash = results[1] if not isinstance(results[1], Exception) else "sha256:unknown"
        index_id = results[2] if not isinstance(results[2], Exception) else f"index_{workspace_id[:12]}"
        repo_revision = results[3] if not isinstance(results[3], Exception) else "unknown"

        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Snapshot component {i} failed: {result}")

        return VerificationSnapshot(
            engine_version=self._config.engine_version,
            ruleset_hash=ruleset_hash,
            policies_hash=policies_hash,
            index_snapshot_id=index_id,
            repo_revision=repo_revision,
        )

    async def create_minimal(self, workspace_id: str) -> VerificationSnapshot:
        """
        최소 스냅샷 생성 (빠른 실행용).

        룰셋/정책 해시 계산 생략.
        """
        index_id = await self._index_snapshot.get_snapshot_id(workspace_id)
        repo_revision = await self._git_resolver.get_revision(None)

        return VerificationSnapshot(
            engine_version=self._config.engine_version,
            ruleset_hash="sha256:minimal",
            policies_hash="sha256:minimal",
            index_snapshot_id=index_id,
            repo_revision=repo_revision,
        )

    async def _get_ruleset_hash(self, path: str) -> str:
        """룰셋 해시 계산 (캐시 적용)."""
        cache_key = f"ruleset:{path}"

        if self._config.enable_caching and cache_key in self._hash_cache:
            cached_hash, timestamp = self._hash_cache[cache_key]
            import time

            if time.time() - timestamp < self._config.cache_ttl_seconds:
                return cached_hash

        content = await self._ruleset_loader.load_ruleset(path)
        hash_value = self._compute_hash(content)

        if self._config.enable_caching:
            import time

            self._hash_cache[cache_key] = (hash_value, time.time())

        return hash_value

    async def _get_policies_hash(self, path: str) -> str:
        """정책 해시 계산 (캐시 적용)."""
        cache_key = f"policies:{path}"

        if self._config.enable_caching and cache_key in self._hash_cache:
            cached_hash, timestamp = self._hash_cache[cache_key]
            import time

            if time.time() - timestamp < self._config.cache_ttl_seconds:
                return cached_hash

        content = await self._ruleset_loader.load_policies(path)
        hash_value = self._compute_hash(content)

        if self._config.enable_caching:
            import time

            self._hash_cache[cache_key] = (hash_value, time.time())

        return hash_value

    @staticmethod
    def _compute_hash(content: str) -> str:
        """SHA256 해시 계산."""
        if not content:
            return "sha256:empty"

        hash_bytes = hashlib.sha256(content.encode("utf-8")).digest()
        return f"sha256:{hash_bytes.hex()[:12]}"

    def clear_cache(self) -> None:
        """해시 캐시 초기화."""
        self._hash_cache.clear()


# ============================================================
# Factory Functions
# ============================================================


@lru_cache(maxsize=1)
def get_snapshot_factory() -> SnapshotFactory:
    """
    Singleton SnapshotFactory 인스턴스.

    Container에서 호출됨.
    """
    return SnapshotFactory()


async def create_snapshot(
    repo_id: str,
    workspace_id: str,
    ruleset_path: str | None = None,
    policies_path: str | None = None,
) -> VerificationSnapshot:
    """
    VerificationSnapshot 생성 헬퍼.

    Usage:
        snapshot = await create_snapshot("repo1", "ws_001")
    """
    factory = get_snapshot_factory()
    return await factory.create(repo_id, workspace_id, ruleset_path, policies_path)
