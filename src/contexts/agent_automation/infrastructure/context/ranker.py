"""Context Ranker - 컨텍스트 랭킹 및 크기 조절."""

from src.contexts.agent_automation.infrastructure.context.sources import ContextFile
from src.infra.observability import get_logger

logger = get_logger(__name__)


class ContextRanker:
    """컨텍스트 랭커.

    수집된 컨텍스트 파일을 관련도 순으로 정렬하고,
    토큰 제한에 맞게 조절합니다.
    """

    def __init__(self, max_tokens: int = 100000):
        """
        Args:
            max_tokens: 최대 토큰 수
        """
        self.max_tokens = max_tokens

    def rank_and_limit(
        self,
        files: list[ContextFile],
        target_files: list[str],
    ) -> list[ContextFile]:
        """컨텍스트 파일 랭킹 및 제한.

        Args:
            files: ContextFile 리스트
            target_files: 타겟 파일 (우선순위 높음)

        Returns:
            정렬 및 제한된 ContextFile 리스트
        """
        # 1. 타겟 파일 우선
        target_set = set(target_files)
        targets = [f for f in files if f.file_path in target_set]
        others = [f for f in files if f.file_path not in target_set]

        # 2. 관련도 순 정렬
        others_sorted = sorted(others, key=lambda f: f.relevance_score, reverse=True)

        # 3. 타겟 + 관련 파일
        ranked = targets + others_sorted

        # 4. 토큰 제한
        limited = self._limit_by_tokens(ranked)

        logger.info(
            f"Ranked {len(files)} files -> {len(limited)} files (within token limit)",
            extra={
                "original_count": len(files),
                "limited_count": len(limited),
                "max_tokens": self.max_tokens,
            },
        )

        return limited

    def _limit_by_tokens(self, files: list[ContextFile]) -> list[ContextFile]:
        """토큰 제한으로 파일 필터링.

        Args:
            files: ContextFile 리스트

        Returns:
            제한된 ContextFile 리스트
        """
        limited = []
        total_tokens = 0

        for file in files:
            # 간단한 토큰 추정 (1 token ≈ 4 chars)
            file_tokens = len(file.content) // 4

            if total_tokens + file_tokens > self.max_tokens:
                logger.warning(
                    f"Token limit reached: {total_tokens}/{self.max_tokens}",
                    extra={"files_included": len(limited)},
                )
                break

            limited.append(file)
            total_tokens += file_tokens

        return limited
