"""
Parse File UseCase

파일 파싱
"""

from pathlib import Path

from ..domain.models import ASTDocument, Language
from ..domain.ports import ParserPort


class ParseFileUseCase:
    """파일 파싱 UseCase"""

    def __init__(self, parser: ParserPort):
        """
        초기화

        Args:
            parser: AST 파서
        """
        self.parser = parser

    def execute(self, file_path: Path, language: Language | None = None) -> ASTDocument:
        """
        파일 파싱 실행

        Args:
            file_path: 파일 경로
            language: 언어 (None이면 자동 감지)

        Returns:
            AST 문서
        """
        # 언어 자동 감지
        if language is None:
            language = self._detect_language(file_path)

        # 파싱 실행
        ast_doc = self.parser.parse_file(file_path, language)

        return ast_doc

    def _detect_language(self, file_path: Path) -> Language:
        """언어 자동 감지"""
        ext = file_path.suffix.lower()

        mapping = {
            ".py": Language.PYTHON,
            ".js": Language.JAVASCRIPT,
            ".jsx": Language.JAVASCRIPT,
            ".ts": Language.TYPESCRIPT,
            ".tsx": Language.TYPESCRIPT,
            ".go": Language.GO,
            ".rs": Language.RUST,
            ".java": Language.JAVA,
            ".cpp": Language.CPP,
            ".cc": Language.CPP,
            ".cxx": Language.CPP,
        }

        return mapping.get(ext, Language.UNKNOWN)
