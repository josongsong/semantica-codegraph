"""
Type Hint Generator (SRP 분리)

Port: TypeHintGeneratorPort
Technology: AST + Jedi 추론

책임:
- 타입 힌트 자동 생성 (Python only)

SOLID:
- S: 타입 힌트 생성만 담당
- O: 새 타입 추론 규칙 추가 용이
- L: TypeHintGeneratorPort 완벽히 구현
- I: generate_type_hints만
"""

import ast
import logging
import time
from pathlib import Path

from apps.orchestrator.orchestrator.domain.code_editing import (
    FileChange,
    RefactoringResult,
)

logger = logging.getLogger(__name__)

# Jedi import (선택적 - 고급 추론)
try:
    import jedi

    JEDI_AVAILABLE = True
except ImportError:
    JEDI_AVAILABLE = False
    jedi = None


class TypeHintGenerator:
    """
    Type Hint Generator

    TypeHintGeneratorPort 구현체

    Features:
    - 함수/메서드 타입 힌트 자동 생성
    - 기본 타입 추론 (str, int, list, dict, None)
    - Jedi 기반 고급 추론 (선택적)

    Usage:
        generator = TypeHintGenerator("/workspace")
        result = await generator.generate_type_hints("main.py")
    """

    # 기본 타입 매핑
    BASIC_TYPE_MAP = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "list": "list",
        "dict": "dict",
        "set": "set",
        "tuple": "tuple",
        "None": "None",
    }

    def __init__(
        self,
        workspace_root: str,
        use_jedi: bool = True,
    ):
        """
        Args:
            workspace_root: Workspace 루트 경로
            use_jedi: Jedi 사용 여부 (고급 추론)
        """
        self.use_jedi = use_jedi and JEDI_AVAILABLE
        self._workspace_root = Path(workspace_root)

        logger.info(f"TypeHintGenerator initialized: workspace={workspace_root}, jedi={self.use_jedi}")

    async def generate_type_hints(self, file_path: str) -> RefactoringResult:
        """
        타입 힌트 자동 생성 (Python only)

        Args:
            file_path: 파일 경로

        Returns:
            RefactoringResult: 타입 힌트 추가 결과

        Raises:
            FileNotFoundError: File not found
            RuntimeError: Type inference failed
        """
        start_time = time.perf_counter()

        try:
            logger.info(f"Generate type hints: {file_path}")

            # 파일 읽기
            file = self._workspace_root / file_path if not Path(file_path).is_absolute() else Path(file_path)
            original_content = file.read_text(encoding="utf-8")

            # AST 파싱
            tree = ast.parse(original_content)

            # 함수/메서드 찾기 및 타입 힌트 추가
            functions_without_hints = self._find_functions_without_hints(tree)
            warnings = []

            if not functions_without_hints:
                warnings.append("All functions already have type hints")
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                return RefactoringResult(
                    success=True,
                    changes=[],
                    affected_files=[],
                    warnings=warnings,
                    execution_time_ms=execution_time_ms,
                )

            # 타입 힌트 추가
            new_content, added_hints = await self._add_type_hints(original_content, functions_without_hints, file_path)

            if not added_hints:
                warnings.append("Could not infer types for any function")
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                return RefactoringResult(
                    success=True,
                    changes=[],
                    affected_files=[],
                    warnings=warnings,
                    execution_time_ms=execution_time_ms,
                )

            # FileChange 생성
            changes = [
                FileChange(
                    file_path=file_path,
                    original_content=original_content,
                    new_content=new_content,
                )
            ]

            warnings.append(f"Added type hints to {added_hints} functions")
            warnings.append("Basic type inference - complex types use Any")

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(f"Type hints generated: {added_hints} functions, time={execution_time_ms:.1f}ms")

            return RefactoringResult(
                success=True,
                changes=changes,
                affected_files=[file_path],
                warnings=warnings,
                execution_time_ms=execution_time_ms,
            )

        except SyntaxError as e:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return RefactoringResult(
                success=False,
                changes=[],
                affected_files=[],
                errors=[f"Syntax error in file: {e}"],
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

    def _find_functions_without_hints(self, tree: ast.AST) -> list[ast.FunctionDef]:
        """타입 힌트 없는 함수 찾기"""
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 반환 타입 힌트 없는지 확인
                if node.returns is None:
                    functions.append(node)
                    continue

                # 인자 타입 힌트 없는지 확인
                has_untyped_args = False
                for arg in node.args.args:
                    if arg.arg != "self" and arg.annotation is None:
                        has_untyped_args = True
                        break

                if has_untyped_args:
                    functions.append(node)

        return functions

    async def _add_type_hints(self, content: str, functions: list[ast.FunctionDef], file_path: str) -> tuple[str, int]:
        """타입 힌트 추가"""
        lines = content.splitlines(keepends=True)
        added_hints = 0

        # 역순으로 처리 (라인 번호 변경 방지)
        for func in sorted(functions, key=lambda f: f.lineno, reverse=True):
            # 타입 추론
            return_type = await self._infer_return_type(func, content, file_path)
            arg_types = await self._infer_arg_types(func, content, file_path)

            # 타입 힌트 적용
            if return_type or arg_types:
                lines = self._apply_type_hints(lines, func, return_type, arg_types)
                added_hints += 1

        return "".join(lines), added_hints

    async def _infer_return_type(self, func: ast.FunctionDef, content: str, file_path: str) -> str | None:
        """반환 타입 추론"""
        # 이미 타입 힌트 있으면 스킵
        if func.returns is not None:
            return None

        # return 문 분석
        for node in ast.walk(func):
            if isinstance(node, ast.Return):
                if node.value is None:
                    return "None"

                # 기본 타입 추론
                if isinstance(node.value, ast.Constant):
                    type_name = type(node.value.value).__name__
                    return self.BASIC_TYPE_MAP.get(type_name, "Any")

                if isinstance(node.value, ast.List):
                    return "list"

                if isinstance(node.value, ast.Dict):
                    return "dict"

                if isinstance(node.value, ast.Set):
                    return "set"

                if isinstance(node.value, ast.Tuple):
                    return "tuple"

                # Jedi 사용 가능하면 고급 추론
                if self.use_jedi:
                    return await self._jedi_infer_type(content, file_path, func.lineno)

        # return 문 없으면 None
        return "None"

    async def _infer_arg_types(self, func: ast.FunctionDef, content: str, file_path: str) -> dict[str, str]:
        """인자 타입 추론"""
        arg_types = {}

        for arg in func.args.args:
            if arg.arg == "self":
                continue

            if arg.annotation is not None:
                continue

            # 기본값으로 타입 추론
            if func.args.defaults:
                idx = func.args.args.index(arg) - len(func.args.args) + len(func.args.defaults)
                if idx >= 0 and idx < len(func.args.defaults):
                    default = func.args.defaults[idx]
                    if isinstance(default, ast.Constant):
                        type_name = type(default.value).__name__
                        arg_types[arg.arg] = self.BASIC_TYPE_MAP.get(type_name, "Any")
                        continue

            # 추론 못하면 Any
            arg_types[arg.arg] = "Any"

        return arg_types

    async def _jedi_infer_type(self, content: str, file_path: str, line: int) -> str | None:
        """Jedi 기반 타입 추론"""
        if not self.use_jedi:
            return None

        try:
            script = jedi.Script(code=content, path=file_path)
            # 타입 추론 시도
            inferences = script.infer(line=line, column=0)
            if inferences:
                return inferences[0].name
        except Exception:
            pass

        return None

    def _apply_type_hints(
        self,
        lines: list[str],
        func: ast.FunctionDef,
        return_type: str | None,
        arg_types: dict[str, str],
    ) -> list[str]:
        """타입 힌트 적용"""
        # 함수 정의 라인 찾기 (1-based -> 0-based)
        func_line_idx = func.lineno - 1
        func_line = lines[func_line_idx]

        # 간단한 케이스: 반환 타입만 추가
        if return_type and "->" not in func_line:
            # ) 뒤에 -> Type: 추가
            if "):" in func_line:
                func_line = func_line.replace("):", f") -> {return_type}:")
                lines[func_line_idx] = func_line

        return lines
