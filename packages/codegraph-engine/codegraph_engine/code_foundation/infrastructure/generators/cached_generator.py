"""
Cached IR Generator

파싱 결과(IRDocument)를 3-tier 캐싱하여 반복 파싱 방지.

캐시 키: (repo_id, file_path, content_hash)
- content_hash로 파일 내용 변경 감지
- 동일 파일은 재파싱하지 않음

L1: In-Memory LRU (~0.1ms)
L2: Redis (~1-2ms, shared across instances)
L3: Re-parse (~10-100ms)
"""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
from codegraph_engine.code_foundation.infrastructure.parsing.source_file import SourceFile
from codegraph_shared.infra.cache.three_tier_cache import L3DatabaseLoader, ThreeTierCache

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator

logger = get_logger(__name__)


def compute_content_hash(content: str) -> str:
    """
    파일 내용의 해시 계산.

    Args:
        content: 파일 내용

    Returns:
        SHA256 해시 (16자리)
    """
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class IRGeneratorLoader(L3DatabaseLoader[IRDocument]):
    """IR Generator용 L3 로더 (실제로는 파싱 수행)"""

    def __init__(self, generator: "IRGenerator", repo_id: str):
        """
        Args:
            generator: 실제 IR Generator
            repo_id: Repository ID
        """
        self.generator = generator
        self.repo_id = repo_id

    async def load(self, key: str) -> IRDocument | None:
        """
        파일을 파싱하여 IRDocument 생성.

        Args:
            key: "file_path:content_hash:snapshot_id"

        Returns:
            IRDocument or None
        """
        try:
            parts = key.split(":", 2)
            if len(parts) != 3:
                logger.error("invalid_ir_cache_key", key=key)
                return None

            file_path, content_hash, snapshot_id = parts

            # 파일 읽기
            file_path_obj = Path(file_path)
            content = file_path_obj.read_text()

            # 언어 감지
            language = "python"  # 기본값 (향후 확장 가능)
            if file_path_obj.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                language = "typescript"

            # SourceFile 생성
            source = SourceFile(file_path=file_path, content=content, language=language)

            # 파일 파싱 (sync 메서드를 executor에서 실행)
            import asyncio

            loop = asyncio.get_event_loop()
            ir_doc = await loop.run_in_executor(None, self.generator.generate, source, snapshot_id)

            logger.debug(
                "ir_generated", file_path=file_path, node_count=len(ir_doc.nodes), edge_count=len(ir_doc.edges)
            )

            return ir_doc

        except Exception as e:
            logger.error("ir_generation_failed", key=key, error=str(e), exc_info=True)
            return None

    async def save(self, key: str, value: IRDocument) -> None:
        """Save는 필요 없음 (파싱 결과는 캐시만)"""
        pass

    async def delete(self, key: str) -> None:
        """Delete는 필요 없음"""
        pass


class CachedIRGenerator:
    """
    3-tier 캐싱이 적용된 IR Generator.

    파싱 결과를 캐싱하여 성능 향상:
    - 동일 파일을 여러 번 파싱하지 않음
    - content_hash로 파일 변경 감지
    - Redis로 인스턴스 간 캐시 공유

    성능:
    - L1 hit: ~0.1ms (vs 10-100ms 파싱)
    - L2 hit: ~1-2ms
    - Expected hit rate: 60-80% (동일 파일 반복 조회 시)

    Usage:
        generator = _PythonIRGenerator(repo_id="my-repo")
        cached_gen = CachedIRGenerator(
            generator=generator,
            redis_client=redis,
            l1_maxsize=500
        )

        # 첫 조회: 파싱 수행 (~50ms)
        ir_doc1 = cached_gen.generate("src/main.py", snapshot_id="abc123")

        # 두 번째 조회: 캐시 히트 (~0.1ms)
        ir_doc2 = cached_gen.generate("src/main.py", snapshot_id="abc123")
    """

    def __init__(
        self,
        generator: "IRGenerator",
        redis_client: Any | None = None,
        l1_maxsize: int = 500,
        ttl: int = 600,  # 10분
    ):
        """
        Args:
            generator: 실제 IR Generator
            redis_client: Redis 클라이언트 (optional)
            l1_maxsize: L1 최대 크기
            ttl: TTL (초)
        """
        self.generator = generator
        self.repo_id = getattr(generator, "repo_id", "unknown")

        self._cache = ThreeTierCache[IRDocument](
            l1_maxsize=l1_maxsize,
            l2_redis=redis_client,
            l3_loader=IRGeneratorLoader(generator, self.repo_id),
            ttl=ttl,
            namespace=f"ir:{self.repo_id}",
        )

    def generate(self, source: SourceFile | str | Path, snapshot_id: str) -> IRDocument:
        """
        IRDocument 생성 (캐싱 적용).

        Args:
            source: SourceFile 또는 파일 경로
            snapshot_id: Snapshot ID

        Returns:
            IRDocument
        """
        import asyncio

        # SourceFile로 변환 및 content 읽기
        if isinstance(source, str | Path):
            file_path_obj = Path(source)
            if not file_path_obj.exists():
                logger.error("ir_file_not_found", file_path=str(source))
                raise FileNotFoundError(f"File not found: {source}")

            content = file_path_obj.read_text()

            # 언어 감지
            language = "python"
            if file_path_obj.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                language = "typescript"

            source = SourceFile(file_path=str(file_path_obj), content=content, language=language)
        else:
            content = source.content

        content_hash = compute_content_hash(content)

        # 캐시 키: "file_path:content_hash:snapshot_id"
        cache_key = f"{source.file_path}:{content_hash}:{snapshot_id}"

        # 캐시 조회
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        ir_doc = loop.run_until_complete(self._cache.get(cache_key))

        if ir_doc is None:
            # Cache miss - 직접 파싱
            logger.warning("ir_cache_miss_unexpected", file_path=source.file_path)
            ir_doc = self.generator.generate(source, snapshot_id)

        return ir_doc

    async def generate_async(self, source: SourceFile | str | Path, snapshot_id: str) -> IRDocument:
        """
        IRDocument 생성 (async).

        Args:
            source: SourceFile 또는 파일 경로
            snapshot_id: Snapshot ID

        Returns:
            IRDocument
        """
        # SourceFile로 변환 및 content 읽기
        if isinstance(source, str | Path):
            file_path_obj = Path(source)
            content = file_path_obj.read_text()

            language = "python"
            if file_path_obj.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                language = "typescript"

            source = SourceFile(file_path=str(file_path_obj), content=content, language=language)
        else:
            content = source.content

        content_hash = compute_content_hash(content)

        cache_key = f"{source.file_path}:{content_hash}:{snapshot_id}"

        ir_doc = await self._cache.get(cache_key)
        if ir_doc is None:
            # Cache miss - 직접 파싱
            logger.warning("ir_cache_miss", file_path=source.file_path)
            ir_doc = self.generator.generate(source, snapshot_id)

        return ir_doc

    async def invalidate_file(self, file_path: str | Path) -> None:
        """
        파일 관련 캐시 무효화.

        Args:
            file_path: 파일 경로
        """
        # 파일 경로로 시작하는 모든 키 무효화
        file_path_str = str(file_path)
        pattern = f"{file_path_str}:*"
        count = await self._cache.invalidate_pattern(pattern)
        logger.debug("ir_cache_invalidated", file_path=file_path_str, keys_invalidated=count)

    async def invalidate_repo(self, repo_id: str) -> None:
        """레포지토리 전체 캐시 무효화"""
        self._cache._l1.clear()
        if self._cache._l2:
            await self._cache._l2.clear_namespace()

    def stats(self) -> dict:
        """캐시 통계 조회"""
        return self._cache.stats()
