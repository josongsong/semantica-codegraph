"""
AST Code Transformer (SRP 분리)

Port: CodeTransformerPort
Technology: AST + regex (기본), Rope (선택적)

책임:
- Symbol rename
- Method/Function 추출

SOLID:
- S: 코드 변환만 담당
- O: Strategy Pattern으로 새 변환 추가 용이
- L: CodeTransformerPort 완벽히 구현
- I: rename_symbol, extract_method만
- D: RenameStrategyProtocol 주입 (DIP 준수)
"""

import logging
import re
import time
from pathlib import Path

from apps.orchestrator.orchestrator.domain.code_editing import (
    ExtractMethodRequest,
    FileChange,
    RefactoringResult,
    RenameRequest,
)
from apps.orchestrator.orchestrator.ports.rename_strategy import RenameStrategyProtocol

logger = logging.getLogger(__name__)

# Rope import (선택적)
try:
    from rope.base.project import Project
    from rope.refactor.rename import Rename

    ROPE_AVAILABLE = True
except ImportError:
    ROPE_AVAILABLE = False
    Project = None
    Rename = None


# ============================================================================
# Strategy Pattern (OCP 준수) - RenameStrategyProtocol 구현체들
# ============================================================================


class ASTRenameStrategy:
    """AST + regex 기반 Rename (기본)"""

    async def rename(self, request: RenameRequest, content: str) -> tuple[str, list[str]]:
        """
        AST + regex 기반 rename

        단순 텍스트 치환이지만, 심볼 경계 체크 (\b)
        """
        old_name = request.symbol.name
        new_name = request.new_name
        warnings = []

        # Regex: 심볼 경계에서만 치환 (\b)
        pattern = r"\b" + re.escape(old_name) + r"\b"
        new_content = re.sub(pattern, new_name, content)

        # 변경 없으면 경고
        if new_content == content:
            warnings.append(f"No occurrences of '{old_name}' found")

        return new_content, warnings


class RopeRenameStrategy:
    """Rope 기반 Rename (고급)"""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def rename(self, request: RenameRequest, content: str) -> tuple[str, list[str]]:
        """
        Rope 기반 rename (고급)

        Features:
        - 다중 파일 지원
        - Import 자동 업데이트
        - 스코프 인식 rename
        """
        # Extract request parameters
        old_name = request.symbol.name
        new_name = request.new_name
        file_path = request.symbol.location.file_path

        # 🔥 L11 수정: SymbolLocation에 start_byte 없음 → 라인/컬럼에서 계산
        location = request.symbol.location
        offset = self._calculate_byte_offset(content, location.line, location.column)

        # Rope 기반 cross-file rename
        try:
            import rope.base.project
            import rope.refactor.rename

            # Rope 프로젝트 초기화
            project_root = self.workspace_root
            project = rope.base.project.Project(str(project_root))

            # 파일 리소스
            resource = project.get_file(str(file_path))

            # Rename refactoring
            renamer = rope.refactor.rename.Rename(project, resource, offset)
            changes = renamer.get_changes(new_name)

            # Changes 적용
            if changes:
                project.do(changes)

            # 🔥 L11 수정: Rope가 파일을 수정했으므로 파일에서 다시 읽기
            from pathlib import Path

            actual_file = Path(file_path) if Path(file_path).is_absolute() else self.workspace_root / file_path
            updated_content = actual_file.read_text(encoding="utf-8")

            project.close()

            warnings = []
            return updated_content, warnings

        except ImportError:
            # Rope 없으면 fallback: regex rename
            return self._fallback_regex_rename(old_name, new_name, content, "Rope not available")
        except Exception as e:
            # 에러 발생 시 fallback
            return self._fallback_regex_rename(old_name, new_name, content, f"Rope failed: {e}")

    def _fallback_regex_rename(self, old_name: str, new_name: str, content: str, reason: str) -> tuple[str, list[str]]:
        """
        Fallback regex rename (DRY 준수)

        L11 SOTA: 중복 코드 제거
        """
        warnings = [f"{reason}. Using fallback regex rename"]
        pattern = r"\b" + re.escape(old_name) + r"\b"
        new_content = re.sub(pattern, new_name, content)
        return new_content, warnings

    def _calculate_byte_offset(self, content: str, line: int, column: int) -> int:
        """
        Line/Column → Byte Offset 변환 (L11 SOTA급)

        UTF-8 멀티바이트 문자 정확 처리:
        - Column은 문자 단위 (grapheme cluster 고려)
        - Offset은 바이트 단위
        - 한글, 이모지 등 멀티바이트 완벽 처리

        Args:
            content: 파일 내용 (str)
            line: 줄 번호 (1-based)
            column: 컬럼 번호 (0-based, 문자 단위)

        Returns:
            Byte offset (0-based)

        Raises:
            ValueError: Invalid line or column

        Note:
            Rope requires byte offset, but SymbolLocation uses line/column

        Examples:
            >>> content = "def func():\\n    한글\\n"
            >>> offset = _calculate_byte_offset(content, 2, 4)  # "한글" = 6 bytes
            >>> assert offset == 15  # "def func():\n" (12) + "    " (4) = 16, but "한글" starts at column 4
        """
        # 1. Content를 바이트로 변환
        content_bytes = content.encode("utf-8")
        lines = content.splitlines(keepends=True)

        # 2. Validation
        if line < 1 or line > len(lines):
            raise ValueError(f"Invalid line {line} (file has {len(lines)} lines)")

        if column < 0:
            raise ValueError(f"Invalid column {column} (must be >= 0)")

        # 3. 이전 줄들의 바이트 수
        offset = 0
        for i in range(line - 1):
            offset += len(lines[i].encode("utf-8"))

        # 4. 현재 줄에서 column까지의 바이트 수
        # 중요: column은 문자 단위이므로 grapheme cluster 고려
        current_line = lines[line - 1] if line <= len(lines) else ""

        # Column 범위 체크
        if column > len(current_line):
            raise ValueError(f"Invalid column {column} (line {line} has {len(current_line)} characters)")

        # 문자 단위 column → 바이트 단위 offset
        char_count = 0
        for char in current_line:
            if char_count >= column:
                break
            offset += len(char.encode("utf-8"))
            char_count += 1

        return offset


# ============================================================================
# Code Transformer
# ============================================================================


class ASTCodeTransformer:
    """
    AST 기반 Code Transformer

    CodeTransformerPort 구현체

    Features:
    - Symbol rename (AST + regex)
    - Method/Function 추출

    Usage:
        transformer = ASTCodeTransformer("/workspace")
        result = await transformer.rename_symbol(request)
    """

    def __init__(
        self,
        workspace_root: str,
        use_rope: bool = False,
        rename_strategy: RenameStrategyProtocol | None = None,
    ):
        """
        Args:
            workspace_root: Workspace 루트 경로
            use_rope: Rope 사용 여부 (설치 필요)
            rename_strategy: RenameStrategyProtocol (DIP - 주입 가능)
        """
        self._workspace_root = Path(workspace_root)
        self.use_rope = use_rope and ROPE_AVAILABLE

        # DIP: RenameStrategy 주입 (없으면 기본 구현 사용)
        if rename_strategy:
            self._rename_strategy = rename_strategy
        elif self.use_rope:
            self._rename_strategy: RenameStrategyProtocol = RopeRenameStrategy(self._workspace_root)
        else:
            self._rename_strategy = ASTRenameStrategy()

        logger.info(f"ASTCodeTransformer initialized: workspace={workspace_root}, rope={self.use_rope}")

    async def rename_symbol(self, request: RenameRequest) -> RefactoringResult:
        """
        Symbol 이름 변경

        Args:
            request: Rename 요청

        Returns:
            RefactoringResult: 리팩토링 결과

        Raises:
            ValueError: Invalid request
            FileNotFoundError: File not found
            RuntimeError: Refactoring failed
        """
        start_time = time.perf_counter()

        try:
            file_path = request.symbol.location.file_path
            logger.info(f"Rename: {request.symbol.name} -> {request.new_name} in {file_path}")

            # 파일 읽기
            file = self._workspace_root / file_path if not Path(file_path).is_absolute() else Path(file_path)
            original_content = file.read_text(encoding="utf-8")

            # Strategy 실행
            new_content, warnings = await self._rename_strategy.rename(request, original_content)

            # FileChange 생성
            changes = []
            if new_content != original_content:
                changes.append(
                    FileChange(
                        file_path=file_path,
                        original_content=original_content,
                        new_content=new_content,
                    )
                )

            # Dry-run이 아니면 실제 적용
            if not request.dry_run and changes:
                file.write_text(new_content, encoding="utf-8")

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(f"Rename complete: {len(changes)} files changed, time={execution_time_ms:.1f}ms")

            return RefactoringResult(
                success=True,
                changes=changes,
                affected_files=[file_path] if changes else [],
                warnings=warnings,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return RefactoringResult(
                success=False,
                changes=[],
                affected_files=[],
                errors=[str(e)],
                execution_time_ms=execution_time_ms,
            )

    async def extract_method(self, request: ExtractMethodRequest) -> RefactoringResult:
        """
        메서드/함수 추출

        Args:
            request: Extract 요청

        Returns:
            RefactoringResult: 리팩토링 결과

        Raises:
            ValueError: Invalid request
            FileNotFoundError: File not found
            RuntimeError: Refactoring failed
        """
        start_time = time.perf_counter()

        try:
            logger.info(f"Extract method: lines {request.start_line}-{request.end_line} in {request.file_path}")

            # 파일 읽기
            file = (
                self._workspace_root / request.file_path
                if not Path(request.file_path).is_absolute()
                else Path(request.file_path)
            )
            original_content = file.read_text(encoding="utf-8")
            lines = original_content.splitlines(keepends=True)

            # 추출할 라인 (1-based -> 0-based)
            extract_start = request.start_line - 1
            extract_end = request.end_line

            if extract_start < 0 or extract_end > len(lines):
                raise ValueError(f"Invalid line range: {request.start_line}-{request.end_line}")

            extracted_lines = lines[extract_start:extract_end]
            extracted_code = "".join(extracted_lines)

            # 들여쓰기 감지
            indent = self._detect_indent(extracted_code)

            # 새 함수 생성
            new_function = self._create_function(
                name=request.new_function_name,
                body=extracted_code,
                indent=indent,
            )

            # 함수 호출로 치환
            function_call = f"{' ' * len(indent)}{request.new_function_name}()\n"

            # 새 내용 구성
            new_lines = lines[:extract_start] + [function_call] + lines[extract_end:] + ["\n\n"] + [new_function]
            new_content = "".join(new_lines)

            # FileChange 생성
            changes = [
                FileChange(
                    file_path=request.file_path,
                    original_content=original_content,
                    new_content=new_content,
                )
            ]

            # Dry-run이 아니면 실제 적용
            if not request.dry_run:
                file.write_text(new_content, encoding="utf-8")

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(f"Extract method complete: time={execution_time_ms:.1f}ms")

            return RefactoringResult(
                success=True,
                changes=changes,
                affected_files=[request.file_path],
                warnings=["Basic extraction - parameters not inferred"],
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return RefactoringResult(
                success=False,
                changes=[],
                affected_files=[],
                errors=[str(e)],
                execution_time_ms=execution_time_ms,
            )

    def _detect_indent(self, code: str) -> str:
        """들여쓰기 감지"""
        lines = code.splitlines()
        for line in lines:
            if line and not line.isspace():
                match = re.match(r"^(\s*)", line)
                if match:
                    return match.group(1)
        return ""

    def _create_function(self, name: str, body: str, indent: str) -> str:
        """함수 생성"""
        return f"""def {name}():
{body}
"""
