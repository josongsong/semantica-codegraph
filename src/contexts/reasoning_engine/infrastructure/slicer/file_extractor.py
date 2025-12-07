"""
File Code Extractor - 실제 파일에서 코드 추출

PDGNode의 file_path + line 정보로 실제 소스 코드 추출
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from .exceptions import FileExtractionError

logger = logging.getLogger(__name__)


@dataclass
class SourceCode:
    """실제 소스 코드"""

    file_path: str
    start_line: int
    end_line: int
    code: str
    language: str = "python"


class FileCodeExtractor:
    """
    실제 파일에서 코드 추출

    PDGNode.statement (IR) 대신 실제 소스 파일에서 코드 추출
    """

    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self._file_cache = {}  # {file_path: lines}

    def extract(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> SourceCode | None:
        """
        실제 파일에서 코드 추출

        Args:
            file_path: 파일 경로
            start_line: 시작 라인 (0-based)
            end_line: 끝 라인 (0-based, inclusive)

        Returns:
            SourceCode 또는 None (파일 없으면)

        Raises:
            FileExtractionError: If extraction fails critically
        """
        try:
            logger.debug(f"Extracting code: {file_path}:{start_line}-{end_line}")

            # 상대 경로 처리
            if self.workspace_root:
                full_path = self.workspace_root / file_path
            else:
                full_path = Path(file_path)

            # 파일이 없으면 None (not an error, just missing)
            if not full_path.exists():
                logger.warning(f"File not found: {full_path}")
                return None

            # 캐시 확인
            if str(full_path) not in self._file_cache:
                try:
                    with open(full_path, encoding="utf-8") as f:
                        self._file_cache[str(full_path)] = f.readlines()
                except UnicodeDecodeError as e:
                    logger.error(f"Unicode decode error: {full_path}")
                    raise FileExtractionError(f"Cannot decode {file_path}: {e}") from e
                except OSError:
                    logger.error(f"IO error: {full_path}")
                    return None  # IO errors are soft failures

            lines = self._file_cache[str(full_path)]

            # 라인 범위 확인
            if start_line < 0 or end_line >= len(lines):
                logger.warning(f"Line range out of bounds: {start_line}-{end_line}, file has {len(lines)} lines")
                # 범위 조정
                start_line = max(0, start_line)
                end_line = min(len(lines) - 1, end_line)

            # 코드 추출
            code_lines = lines[start_line : end_line + 1]
            code = "".join(code_lines)

            # 언어 추론
            language = self._infer_language(file_path)

            logger.debug(f"Extracted {len(code)} chars from {file_path}")

            return SourceCode(
                file_path=str(file_path),
                start_line=start_line,
                end_line=end_line,
                code=code,
                language=language,
            )

        except FileExtractionError:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error extracting code: {e}")
            raise FileExtractionError(f"Failed to extract code from {file_path}: {e}") from e

    def extract_with_context(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        context_lines: int = 2,
    ) -> SourceCode | None:
        """
        컨텍스트 포함해서 추출

        Args:
            file_path: 파일 경로
            start_line: 시작 라인
            end_line: 끝 라인
            context_lines: 앞뒤로 포함할 라인 수

        Returns:
            SourceCode with context
        """
        # 범위 확장
        extended_start = max(0, start_line - context_lines)
        extended_end = end_line + context_lines

        return self.extract(file_path, extended_start, extended_end)

    def _infer_language(self, file_path: str) -> str:
        """파일 확장자로 언어 추론"""
        suffix = Path(file_path).suffix.lower()

        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
        }

        return lang_map.get(suffix, "unknown")

    def clear_cache(self):
        """캐시 초기화"""
        self._file_cache.clear()
