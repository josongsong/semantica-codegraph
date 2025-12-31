"""
Parse File UseCase

파일 파싱 (L11급 경계 조건 검증 포함)
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger

from ..domain.language_detector import LanguageDetector
from ..domain.models import ASTDocument, Language
from ..domain.ports import ParserPort

logger = get_logger(__name__)


class ParseFileUseCase:
    """
    파일 파싱 UseCase (SOTA급 검증)

    경계 조건 검증:
    - None 입력 체크
    - 파일 존재 여부
    - 파일 타입 검증 (디렉토리 제외)
    - 권한 체크 (Parser에게 위임)
    """

    def __init__(self, parser: ParserPort):
        """
        초기화

        Args:
            parser: AST 파서

        Raises:
            TypeError: parser가 None일 때
        """
        if parser is None:
            raise TypeError("parser cannot be None")

        self.parser = parser

    def execute(self, file_path: Path, language: Language | None = None) -> ASTDocument:
        """
        파일 파싱 실행 (경계 조건 검증 포함)

        Args:
            file_path: 파일 경로
            language: 언어 (None이면 자동 감지)

        Returns:
            AST 문서

        Raises:
            TypeError: file_path가 None이거나 Path가 아닐 때
            FileNotFoundError: 파일이 존재하지 않을 때
            IsADirectoryError: file_path가 디렉토리일 때
            PermissionError: 파일 읽기 권한이 없을 때 (Parser에서 발생)
            ValueError: 파싱 실패 시

        Example:
            >>> parser = TreeSitterParser()
            >>> use_case = ParseFileUseCase(parser=parser)
            >>> result = use_case.execute(Path("main.py"))
        """
        # ===================================================================
        # L11급 경계 조건 검증 (Fail-fast principle)
        # ===================================================================

        # 1. None 체크
        if file_path is None:
            raise TypeError("file_path cannot be None")

        # 2. 타입 체크
        if not isinstance(file_path, Path):
            raise TypeError(f"file_path must be Path, got {type(file_path).__name__}")

        # 3. 파일 존재 체크
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 4. 디렉토리 체크
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
            # Continue with UNKNOWN - parser might handle it

        # ===================================================================
        # 파싱 실행 (예외는 Parser에게 위임)
        # ===================================================================
        try:
            ast_doc = self.parser.parse_file(file_path, language)
            logger.debug("parse_success", file_path=str(file_path), language=language.value)
            return ast_doc

        except PermissionError as e:
            # Re-raise with context
            logger.error("permission_denied", file_path=str(file_path))
            raise PermissionError(f"Permission denied: {file_path}") from e

        except Exception as e:
            # Wrap unexpected errors
            logger.error("parse_failed", file_path=str(file_path), error=str(e))
            raise ValueError(f"Failed to parse {file_path}: {e}") from e

    def _detect_language(self, file_path: Path) -> Language:
        """
        언어 자동 감지 (LanguageDetector 사용)

        Args:
            file_path: 파일 경로

        Returns:
            감지된 언어
        """
        return LanguageDetector.detect(file_path)
