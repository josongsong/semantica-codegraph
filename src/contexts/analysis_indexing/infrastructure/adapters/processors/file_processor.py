"""
File Processor Adapter

파일 처리 로직 (언어 감지, 파싱)
"""

from pathlib import Path

from ....domain.models import FileToIndex


class FileProcessorAdapter:
    """파일 처리 어댑터"""

    def __init__(self, parser_registry):
        """
        초기화

        Args:
            parser_registry: Parser Registry
        """
        self.parser_registry = parser_registry

    def detect_language(self, file_path: str) -> str | None:
        """
        파일 언어 감지

        Args:
            file_path: 파일 경로

        Returns:
            언어 (python, typescript 등) 또는 None
        """
        path = Path(file_path)
        return self.parser_registry.detect_language(path)

    def parse_file(self, file: FileToIndex):
        """
        파일 파싱

        Args:
            file: 파일 정보

        Returns:
            AST 객체
        """
        from src.contexts.code_foundation.infrastructure.parsing.ast_tree import AstTree
        from src.contexts.code_foundation.infrastructure.parsing.source_file import SourceFile

        # SourceFile 생성
        source = SourceFile.from_content(
            file_path=file.file_path,
            content=Path(file.file_path).read_text() if not file.old_content else file.old_content,
            language=file.language or "python",
        )

        # AST 파싱
        ast = AstTree.parse(source)

        return ast
