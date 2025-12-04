"""Auto Context Builder - 자동 컨텍스트 구성."""

from pathlib import Path
from typing import TYPE_CHECKING

from src.contexts.agent_automation.infrastructure.context.ranker import ContextRanker
from src.contexts.agent_automation.infrastructure.context.sources import ContextFile, ContextSources
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.models import CodeGraph

logger = get_logger(__name__)


class AutoContextBuilder:
    """자동 컨텍스트 빌더.

    타겟 파일 기반으로 관련 파일을 자동으로 수집하고,
    토큰 제한에 맞게 컨텍스트를 구성합니다.
    """

    def __init__(
        self,
        project_root: Path,
        max_tokens: int = 100000,
        include_tests: bool = True,
        include_docs: bool = True,
        include_urls: bool = False,
    ):
        """
        Args:
            project_root: 프로젝트 루트 디렉토리
            max_tokens: 최대 토큰 수
            include_tests: 테스트 파일 포함 여부
            include_docs: 문서 파일 포함 여부
            include_urls: URL 스크래핑 포함 여부
        """
        self.project_root = Path(project_root)
        self.include_tests = include_tests
        self.include_docs = include_docs
        self.include_urls = include_urls

        # 컴포넌트 초기화
        self.sources = ContextSources(project_root)
        self.ranker = ContextRanker(max_tokens=max_tokens)

    async def build_context(
        self,
        target_files: list[str],
        code_graph: "CodeGraph | None" = None,
        urls: list[str] | None = None,
    ) -> list[ContextFile]:
        """컨텍스트 구성.

        Args:
            target_files: 타겟 파일 경로 리스트
            code_graph: CodeGraph 인스턴스 (옵션)
            urls: 추가 URL 리스트 (옵션)

        Returns:
            ContextFile 리스트 (정렬 및 제한됨)
        """
        logger.info(
            f"Building context for {len(target_files)} target files",
            extra={"target_files": target_files},
        )

        all_files: list[ContextFile] = []

        # 1. 타겟 파일 자체 추가
        for file_path in target_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                content = full_path.read_text()
                all_files.append(
                    ContextFile(
                        file_path=file_path,
                        content=content,
                        source_type="target",
                        relevance_score=1.0,
                    )
                )

        # 2. CodeGraph 기반 관련 파일
        related_files = await self.sources.get_related_files(
            target_files,
            code_graph=code_graph,
        )
        all_files.extend(related_files)

        # 3. 테스트 파일
        if self.include_tests:
            test_files = await self.sources.get_test_files(target_files)
            all_files.extend(test_files)

        # 4. 문서 파일
        if self.include_docs:
            doc_files = await self.sources.get_doc_files(target_files)
            all_files.extend(doc_files)

        # 5. URL 스크래핑 (선택적)
        if self.include_urls and urls:
            url_files = await self.sources.scrape_urls(urls)
            all_files.extend(url_files)

        # 6. 랭킹 및 제한
        ranked_files = self.ranker.rank_and_limit(all_files, target_files)

        logger.info(
            f"Context built: {len(ranked_files)} files",
            extra={
                "total_collected": len(all_files),
                "final_count": len(ranked_files),
            },
        )

        return ranked_files

    def format_context(self, files: list[ContextFile]) -> str:
        """컨텍스트를 프롬프트 문자열로 포맷팅.

        Args:
            files: ContextFile 리스트

        Returns:
            포맷팅된 컨텍스트 문자열
        """
        lines = []
        lines.append("# Context Files\n")

        for file in files:
            lines.append(f"## {file.file_path} ({file.source_type})\n")
            lines.append("```")
            lines.append(file.content)
            lines.append("```\n")

        return "\n".join(lines)
