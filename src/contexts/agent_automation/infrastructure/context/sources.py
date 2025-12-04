"""Context Sources - 컨텍스트 소스 수집."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.models import CodeGraph

logger = get_logger(__name__)


@dataclass
class ContextFile:
    """컨텍스트 파일.

    Attributes:
        file_path: 파일 경로
        content: 파일 내용
        source_type: 소스 타입 (related, test, doc, url)
        relevance_score: 관련도 점수 (0.0-1.0)
        metadata: 추가 메타데이터
    """

    file_path: str
    content: str
    source_type: str
    relevance_score: float = 1.0
    metadata: dict | None = None


class ContextSources:
    """컨텍스트 소스 수집기.

    CodeGraph, 테스트 파일, 문서 등에서 관련 파일을 추출합니다.
    """

    def __init__(self, project_root: Path):
        """
        Args:
            project_root: 프로젝트 루트 디렉토리
        """
        self.project_root = Path(project_root)

    async def get_related_files(
        self,
        target_files: list[str],
        code_graph: "CodeGraph | None" = None,
        max_depth: int = 2,
    ) -> list[ContextFile]:
        """관련 파일 추출 (CodeGraph 기반).

        Args:
            target_files: 타겟 파일 경로 리스트
            code_graph: CodeGraph 인스턴스
            max_depth: 최대 탐색 깊이

        Returns:
            ContextFile 리스트
        """
        related = []

        if not code_graph:
            logger.warning("CodeGraph not provided, skipping related files")
            return related

        # CodeGraph 기반 관련 파일 추출
        related_file_set = set()

        for target_file in target_files:
            # 1. Import/Export 관계
            imported_by = self._get_imported_by(code_graph, target_file)
            related_file_set.update(imported_by)

            # 2. Call graph (caller/callee)
            callers = self._get_callers(code_graph, target_file, max_depth)
            related_file_set.update(callers)

            # 3. Inheritance hierarchy
            subclasses = self._get_subclasses(code_graph, target_file)
            related_file_set.update(subclasses)

        # ContextFile로 변환
        for file_path in related_file_set:
            full_path = self.project_root / file_path
            if full_path.exists():
                content = full_path.read_text()
                related.append(
                    ContextFile(
                        file_path=file_path,
                        content=content,
                        source_type="related",
                        relevance_score=0.8,
                    )
                )

        logger.info(f"Found {len(related)} related files from CodeGraph")
        return related

    def _get_imported_by(self, code_graph: "CodeGraph", file_path: str) -> set[str]:
        """파일을 import하는 파일들 조회."""
        # 간단한 구현: nodes에서 import 관계 찾기
        imported_by = set()

        if hasattr(code_graph, "nodes"):
            for node in code_graph.nodes:
                if hasattr(node, "imports") and file_path in node.imports:
                    if node.file_path and node.file_path != file_path:
                        imported_by.add(node.file_path)

        return imported_by

    def _get_callers(self, code_graph: "CodeGraph", file_path: str, max_depth: int) -> set[str]:
        """함수를 호출하는 파일들 조회 (call graph)."""
        callers = set()

        # 간단한 구현: 1-hop caller만 (향후 확장 가능)
        if hasattr(code_graph, "edges"):
            for edge in code_graph.edges:
                if hasattr(edge, "target_file") and edge.target_file == file_path:
                    if hasattr(edge, "source_file") and edge.source_file != file_path:
                        callers.add(edge.source_file)

        return callers

    def _get_subclasses(self, code_graph: "CodeGraph", file_path: str) -> set[str]:
        """클래스를 상속하는 파일들 조회."""
        subclasses = set()

        # 간단한 구현: inheritance edge 찾기
        if hasattr(code_graph, "edges"):
            for edge in code_graph.edges:
                if (
                    hasattr(edge, "edge_type")
                    and edge.edge_type == "inherits"
                    and hasattr(edge, "target_file")
                    and edge.target_file == file_path
                ):
                    if hasattr(edge, "source_file") and edge.source_file != file_path:
                        subclasses.add(edge.source_file)

        return subclasses

    async def get_test_files(self, target_files: list[str]) -> list[ContextFile]:
        """테스트 파일 추출.

        Args:
            target_files: 타겟 파일 경로 리스트

        Returns:
            ContextFile 리스트
        """
        test_files = []

        for file_path in target_files:
            path = Path(file_path)

            # src/module.py -> tests/test_module.py
            if "src/" in str(path):
                rel_path = path.relative_to(self.project_root / "src")
                test_path = self.project_root / "tests" / f"test_{rel_path.name}"

                if test_path.exists():
                    content = test_path.read_text()
                    test_files.append(
                        ContextFile(
                            file_path=str(test_path.relative_to(self.project_root)),
                            content=content,
                            source_type="test",
                            relevance_score=0.9,
                        )
                    )

        logger.info(f"Found {len(test_files)} test files")
        return test_files

    async def get_doc_files(self, target_files: list[str]) -> list[ContextFile]:
        """문서 파일 추출.

        Args:
            target_files: 타겟 파일 경로 리스트

        Returns:
            ContextFile 리스트
        """
        doc_files = []

        # README, CHANGELOG 등 프로젝트 문서
        doc_patterns = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md"]

        for pattern in doc_patterns:
            doc_path = self.project_root / pattern
            if doc_path.exists():
                content = doc_path.read_text()
                doc_files.append(
                    ContextFile(
                        file_path=pattern,
                        content=content,
                        source_type="doc",
                        relevance_score=0.5,
                    )
                )

        logger.info(f"Found {len(doc_files)} doc files")
        return doc_files

    async def scrape_urls(self, urls: list[str]) -> list[ContextFile]:
        """URL 스크래핑 (선택적).

        Args:
            urls: URL 리스트

        Returns:
            ContextFile 리스트
        """
        # TODO: httpx를 사용하여 URL 스크래핑
        # 지금은 스킵
        logger.info(f"URL scraping not implemented (urls={len(urls)})")
        return []
