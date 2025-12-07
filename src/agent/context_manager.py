"""
Context Manager

LLM에게 제공할 Context를 스마트하게 선택/관리합니다.

기능:
- 관련 코드 파일 자동 탐색
- Import dependency 분석
- 테스트 파일 자동 발견
- Context 크기 최적화
"""

import ast
import re
from pathlib import Path
from typing import Any


class ContextManager:
    """
    Context 선택 및 관리.

    LLM이 코드를 생성할 때 필요한 최소한의 관련 Context만 제공.
    """

    def __init__(self, repo_root: str = "."):
        """
        Args:
            repo_root: Repository 루트 경로
        """
        self.repo_root = Path(repo_root)

    async def select_context(
        self, task_description: str, initial_files: list[str], max_tokens: int = 8000
    ) -> dict[str, Any]:
        """
        Task에 필요한 Context를 선택.

        Args:
            task_description: Task 설명
            initial_files: 초기 파일 리스트
            max_tokens: 최대 토큰 수 (대략)

        Returns:
            Context dict (files, dependencies, tests)
        """
        context = {
            "files": {},  # {file_path: content}
            "dependencies": [],  # 의존 파일들
            "tests": [],  # 테스트 파일들
            "related_symbols": [],  # 관련 심볼들
        }

        # 1. 초기 파일 읽기
        for file_path in initial_files:
            content = await self._read_file(file_path)
            if content:
                context["files"][file_path] = content

        # 2. Import dependency 분석
        for file_path in list(context["files"].keys()):
            deps = await self._find_dependencies(file_path)
            context["dependencies"].extend(deps)

        # 3. 테스트 파일 찾기
        for file_path in initial_files:
            test_file = await self._find_test_file(file_path)
            if test_file:
                context["tests"].append(test_file)

                # 테스트 내용도 포함
                test_content = await self._read_file(test_file)
                if test_content:
                    context["files"][test_file] = test_content

        # 4. 관련 심볼 추출
        for file_path, content in context["files"].items():
            symbols = await self._extract_symbols(content)
            context["related_symbols"].extend(symbols)

        # 5. Context 크기 최적화
        context = await self._optimize_context(context, max_tokens)

        return context

    async def _read_file(self, file_path: str) -> str | None:
        """파일 읽기"""
        try:
            path = self.repo_root / file_path
            if path.exists():
                return path.read_text()
        except Exception:
            pass
        return None

    async def _find_dependencies(self, file_path: str) -> list[str]:
        """Import dependency 분석"""
        content = await self._read_file(file_path)
        if not content:
            return []

        deps = []

        # Python import 분석
        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        deps.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        deps.append(node.module)

        except Exception:
            # Fallback: regex
            import_pattern = r"^(?:from|import)\s+(\S+)"
            for line in content.splitlines():
                match = re.match(import_pattern, line.strip())
                if match:
                    deps.append(match.group(1))

        # Local file로 변환 (예: "utils" → "utils.py")
        local_deps = []
        for dep in deps:
            # Relative import는 건너뜀
            if dep.startswith("."):
                continue

            # Local file 추정
            dep_path = self.repo_root / f"{dep.replace('.', '/')}.py"
            if dep_path.exists():
                local_deps.append(str(dep_path.relative_to(self.repo_root)))

        return local_deps

    async def _find_test_file(self, file_path: str) -> str | None:
        """테스트 파일 찾기"""
        path = Path(file_path)

        # 1. test_{name}.py 패턴
        test_name = f"test_{path.stem}.py"
        test_path = path.parent / test_name

        if test_path.exists():
            return str(test_path)

        # 2. {name}_test.py 패턴
        test_name = f"{path.stem}_test.py"
        test_path = path.parent / test_name

        if test_path.exists():
            return str(test_path)

        # 3. tests/ 디렉토리
        test_dir = path.parent / "tests"
        if test_dir.exists():
            for test_file in test_dir.glob(f"*{path.stem}*.py"):
                return str(test_file)

        return None

    async def _extract_symbols(self, content: str) -> list[dict]:
        """코드에서 심볼(함수, 클래스) 추출"""
        symbols = []

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    symbols.append(
                        {
                            "type": "function",
                            "name": node.name,
                            "line": node.lineno,
                        }
                    )
                elif isinstance(node, ast.ClassDef):
                    symbols.append(
                        {
                            "type": "class",
                            "name": node.name,
                            "line": node.lineno,
                        }
                    )

        except Exception:
            # Fallback: regex
            func_pattern = r"^def\s+(\w+)"
            class_pattern = r"^class\s+(\w+)"

            for i, line in enumerate(content.splitlines(), 1):
                func_match = re.match(func_pattern, line.strip())
                if func_match:
                    symbols.append(
                        {
                            "type": "function",
                            "name": func_match.group(1),
                            "line": i,
                        }
                    )

                class_match = re.match(class_pattern, line.strip())
                if class_match:
                    symbols.append(
                        {
                            "type": "class",
                            "name": class_match.group(1),
                            "line": i,
                        }
                    )

        return symbols

    async def _optimize_context(self, context: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        """Context 크기 최적화 (토큰 제한)"""
        # 간단한 휴리스틱: 1 token ≈ 4 chars
        max_chars = max_tokens * 4

        # 파일 내용 총 크기 계산
        total_chars = sum(len(content) for content in context["files"].values())

        if total_chars <= max_chars:
            return context  # 충분히 작음

        # 크기 초과 시 우선순위 적용
        # 1. 초기 파일은 전체 포함
        # 2. 테스트 파일 우선
        # 3. 나머지는 요약 또는 제거

        optimized_files = {}
        remaining_chars = max_chars

        # 초기 파일 (테스트 제외)
        for file_path, content in context["files"].items():
            if file_path not in context["tests"]:
                if len(content) <= remaining_chars:
                    optimized_files[file_path] = content
                    remaining_chars -= len(content)
                else:
                    # 요약 (처음 1000자 + ... + 마지막 1000자)
                    summary = content[:1000] + "\n\n... (truncated) ...\n\n" + content[-1000:]
                    optimized_files[file_path] = summary
                    remaining_chars -= len(summary)

        # 테스트 파일
        for test_file in context["tests"]:
            if test_file in context["files"]:
                content = context["files"][test_file]
                if len(content) <= remaining_chars:
                    optimized_files[test_file] = content
                    remaining_chars -= len(content)

        context["files"] = optimized_files

        return context

    def format_context_for_llm(self, context: dict[str, Any]) -> str:
        """LLM에게 제공할 Context를 포맷팅"""
        formatted = []

        # 1. 파일 내용
        for file_path, content in context["files"].items():
            formatted.append(f"### {file_path}")
            formatted.append("```python")
            formatted.append(content)
            formatted.append("```")
            formatted.append("")

        # 2. 관련 심볼
        if context["related_symbols"]:
            formatted.append("### Related Symbols")
            for symbol in context["related_symbols"][:10]:  # 최대 10개
                formatted.append(f"- {symbol['type']} `{symbol['name']}` (line {symbol['line']})")
            formatted.append("")

        # 3. 테스트 파일
        if context["tests"]:
            formatted.append("### Test Files")
            for test in context["tests"]:
                formatted.append(f"- {test}")
            formatted.append("")

        return "\n".join(formatted)
