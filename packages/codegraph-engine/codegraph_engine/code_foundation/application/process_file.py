"""
Process File UseCase

파일 전체 처리 (AST → IR → Graph → Chunks)
L11급 경계 조건 검증 + 명시적 예외 처리
"""

from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

from ..domain.language_detector import LanguageDetector
from ..domain.models import Chunk, IRDocument, Language
from ..domain.ports import ChunkerPort, GraphBuilderPort, IRGeneratorPort, ParserPort
from ..infrastructure.graph.models import GraphDocument

logger = get_logger(__name__)


def _get_ir_node_count(ir_doc: Any) -> int:
    """Get node count from IRDocument (supports both Infrastructure and Domain)"""
    if hasattr(ir_doc, "nodes"):
        return len(ir_doc.nodes)
    # DEPRECATED: Domain IRDocument uses 'symbols'
    return len(getattr(ir_doc, "symbols", []))


def _get_graph_node_count(graph_doc: Any) -> int:
    """Get node count from GraphDocument (supports both formats)"""
    if hasattr(graph_doc, "graph_nodes"):
        return len(graph_doc.graph_nodes)
    return len(getattr(graph_doc, "nodes", {}))


def _get_graph_edge_count(graph_doc: Any) -> int:
    """Get edge count from GraphDocument (supports both formats)"""
    if hasattr(graph_doc, "graph_edges"):
        return len(graph_doc.graph_edges)
    return len(getattr(graph_doc, "edges", []))


class ProcessFileUseCase:
    """
    파일 전체 처리 UseCase (SOTA급 검증)

    4단계 파이프라인:
    1. AST 파싱
    2. IR 생성
    3. 그래프 빌드
    4. 청킹

    각 단계에서 명시적 예외 처리 및 로깅
    """

    def __init__(
        self,
        parser: ParserPort,
        ir_generator: IRGeneratorPort,
        graph_builder: GraphBuilderPort,
        chunker: ChunkerPort,
    ):
        """
        초기화

        Args:
            parser: AST 파서
            ir_generator: IR 생성기
            graph_builder: 그래프 빌더
            chunker: 청커

        Raises:
            TypeError: 필수 의존성이 None일 때
        """
        if parser is None:
            raise TypeError("parser cannot be None")
        if ir_generator is None:
            raise TypeError("ir_generator cannot be None")
        if graph_builder is None:
            raise TypeError("graph_builder cannot be None")
        if chunker is None:
            raise TypeError("chunker cannot be None")

        self.parser = parser
        self.ir_generator = ir_generator
        self.graph_builder = graph_builder
        self.chunker = chunker

    def execute(
        self, file_path: Path, language: Language | None = None
    ) -> tuple[IRDocument, GraphDocument, list[Chunk]]:
        """
        파일 전체 처리 실행 (경계 조건 검증 + 명시적 예외 처리)

        Args:
            file_path: 파일 경로
            language: 언어 (None이면 자동 감지)

        Returns:
            (IR 문서, 그래프 문서, 청크 리스트)

        Raises:
            TypeError: file_path가 None이거나 Path가 아닐 때
            FileNotFoundError: 파일이 존재하지 않을 때
            IsADirectoryError: file_path가 디렉토리일 때
            ValueError: 처리 중 오류 발생 시 (어느 단계에서 실패했는지 명시)

        Example:
            >>> use_case = ProcessFileUseCase(parser, ir_gen, graph_builder, chunker)
            >>> ir_doc, graph_doc, chunks = use_case.execute(Path("main.py"))
        """
        # ===================================================================
        # L11급 경계 조건 검증
        # ===================================================================
        if file_path is None:
            raise TypeError("file_path cannot be None")

        if not isinstance(file_path, Path):
            raise TypeError(f"file_path must be Path, got {type(file_path).__name__}")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            if file_path.is_dir():
                raise IsADirectoryError(f"Expected file, got directory: {file_path}")
            else:
                raise ValueError(f"Not a regular file: {file_path}")

        # ===================================================================
        # 언어 자동 감지
        # ===================================================================
        if language is None:
            language = self._detect_language(file_path)

        if language == Language.UNKNOWN:
            logger.warning(
                "unknown_language_detected",
                file_path=str(file_path),
                extension=file_path.suffix,
            )

        logger.info("process_file_start", file_path=str(file_path), language=language.value)

        # ===================================================================
        # Stage 1: AST 파싱
        # ===================================================================
        try:
            logger.debug("[1/4] Parsing AST", file_path=str(file_path))
            ast_doc = self.parser.parse_file(file_path, language)
            logger.debug(
                "✅ [1/4] AST parsed",
                file_path=str(file_path),
                source_lines=ast_doc.source_code.count("\n") + 1,
            )

        except Exception as e:
            logger.error("❌ [1/4] AST parsing failed", file_path=str(file_path), error=str(e))
            raise ValueError(f"AST parsing failed for {file_path}: {e}") from e

        # ===================================================================
        # Stage 2: IR 생성
        # ===================================================================
        try:
            logger.debug("[2/4] Generating IR")
            ir_doc = self.ir_generator.generate(ast_doc)
            node_count = _get_ir_node_count(ir_doc)
            logger.debug("✅ [2/4] IR generated", nodes=node_count)

        except Exception as e:
            logger.error("❌ [2/4] IR generation failed", file_path=str(file_path), error=str(e))
            raise ValueError(f"IR generation failed for {file_path}: {e}") from e

        # ===================================================================
        # Stage 3: 그래프 빌드
        # ===================================================================
        try:
            logger.debug("[3/4] Building graph")
            graph_doc = self.graph_builder.build(ir_doc)
            node_count = _get_graph_node_count(graph_doc)
            edge_count = _get_graph_edge_count(graph_doc)
            logger.debug("✅ [3/4] Graph built", nodes=node_count, edges=edge_count)

        except Exception as e:
            logger.error("❌ [3/4] Graph building failed", file_path=str(file_path), error=str(e))
            raise ValueError(f"Graph building failed for {file_path}: {e}") from e

        # ===================================================================
        # Stage 4: 청킹
        # ===================================================================
        try:
            logger.debug("[4/4] Chunking")
            chunks = self.chunker.chunk(ir_doc, ast_doc.source_code)
            logger.debug("✅ [4/4] Chunked", chunks=len(chunks))

        except Exception as e:
            logger.error("❌ [4/4] Chunking failed", file_path=str(file_path), error=str(e))
            raise ValueError(f"Chunking failed for {file_path}: {e}") from e

        # ===================================================================
        # Complete
        # ===================================================================
        logger.info(
            "✅ Process complete",
            file_path=str(file_path),
            ir_nodes=_get_ir_node_count(ir_doc),
            graph_nodes=_get_graph_node_count(graph_doc),
            chunks=len(chunks),
        )

        return ir_doc, graph_doc, chunks

    def _detect_language(self, file_path: Path) -> Language:
        """
        언어 자동 감지 (LanguageDetector 사용)

        Args:
            file_path: 파일 경로

        Returns:
            감지된 언어
        """
        return LanguageDetector.detect(file_path)
