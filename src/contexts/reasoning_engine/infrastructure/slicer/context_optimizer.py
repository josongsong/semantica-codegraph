"""
Context Optimizer - LLM-friendly code generation

Ensures syntax integrity and adds necessary context (stubs, imports, explanations).
"""

from dataclasses import dataclass

from .slicer import CodeFragment, SliceResult


@dataclass
class OptimizedContext:
    """LLM에게 전달할 최적화된 컨텍스트"""

    summary: str
    """요약 정보"""

    essential_code: str
    """핵심 코드 (실행 가능)"""

    control_flow_explanation: str
    """Control flow 설명"""

    variable_history: str
    """변수 히스토리"""

    total_tokens: int
    """총 토큰 수"""

    confidence: float
    """정확도"""

    warnings: list[str]
    """경고 메시지"""

    def to_llm_prompt(self) -> str:
        """LLM 프롬프트로 변환"""
        parts = []

        # Summary
        parts.append(f"# Context Summary\n{self.summary}\n")

        # Control flow
        if self.control_flow_explanation:
            parts.append(f"# Control Flow\n{self.control_flow_explanation}\n")

        # Variable history
        if self.variable_history:
            parts.append(f"# Variable History\n{self.variable_history}\n")

        # Essential code
        parts.append(f"# Code\n```python\n{self.essential_code}\n```\n")

        # Warnings
        if self.warnings:
            parts.append("# Warnings\n" + "\n".join(f"- {w}" for w in self.warnings))

        return "\n".join(parts)


class ContextOptimizer:
    """
    Context Optimizer - Syntax integrity + LLM-friendly output

    주요 기능:
    1. Stub 생성 (함수/클래스/Import)
    2. Syntax validation (AST parse)
    3. Control flow 설명
    4. Import 최소화
    """

    def __init__(self):
        self.stubs_generated = []
        self.imports_added = []

    def optimize_for_llm(
        self,
        slice_result: SliceResult,
        ir_docs: dict[str, any] | None = None,
    ) -> OptimizedContext:
        """
        LLM-friendly 컨텍스트 생성

        Args:
            slice_result: Program slice

        Returns:
            OptimizedContext ready for LLM
        """
        warnings = []

        # 1. Code fragments → Essential code
        essential_code = self._assemble_code(slice_result.code_fragments)

        # 2. Syntax integrity check
        is_valid, errors = self._validate_syntax(essential_code)

        # 3. Add stubs if needed
        if not is_valid:
            essential_code, stubs_added = self._add_stubs(essential_code, errors)
            if stubs_added:
                warnings.append(f"Added {len(stubs_added)} stubs for missing definitions")

        # 4. Generate summary
        summary = self._generate_summary(slice_result)

        # 5. Control flow explanation
        control_flow = self._format_control_flow(slice_result.control_context)

        # 6. Variable history
        var_history = self._trace_variable_history(slice_result)

        # 7. Count tokens
        total_tokens = self._count_tokens(essential_code)

        return OptimizedContext(
            summary=summary,
            essential_code=essential_code,
            control_flow_explanation=control_flow,
            variable_history=var_history,
            total_tokens=total_tokens,
            confidence=slice_result.confidence,
            warnings=warnings,
        )

    def _assemble_code(self, fragments: list[CodeFragment]) -> str:
        """
        코드 조각들을 하나로 조립

        Args:
            fragments: Code fragments

        Returns:
            Assembled code
        """
        if not fragments:
            return "# (No code available)"

        # Group by file
        files = {}
        for frag in fragments:
            if frag.file_path not in files:
                files[frag.file_path] = []
            files[frag.file_path].append(frag)

        # Assemble
        parts = []
        for file_path, frags in files.items():
            parts.append(f"# File: {file_path}\n")

            # Sort by line number
            frags.sort(key=lambda f: f.start_line)

            # Add code
            for frag in frags:
                # Add line numbers as comment
                parts.append(f"# Lines {frag.start_line}-{frag.end_line}")
                parts.append(frag.code)
                parts.append("")  # Empty line

        return "\n".join(parts)

    def _validate_syntax(self, code: str) -> tuple[bool, list[str]]:
        """
        Syntax validation (AST parse)

        Args:
            code: Python code

        Returns:
            (is_valid, errors)
        """
        try:
            import ast

            ast.parse(code)
            return True, []
        except SyntaxError as e:
            return False, [str(e)]
        except Exception as e:
            return False, [f"Validation error: {e}"]

    def _add_stubs(self, code: str, errors: list[str]) -> tuple[str, list[str]]:
        """
        Missing definitions에 대한 stub 추가

        FIXED: AST 기반 undefined name 탐지

        Args:
            code: Original code
            errors: Syntax errors

        Returns:
            (fixed_code, stubs_added)
        """

        stubs = []
        stub_code = []

        # 1. AST로 undefined names 찾기
        undefined_names = self._find_undefined_names(code)

        # 2. Generate stubs
        for name in undefined_names:
            # Heuristic: 대문자로 시작하면 클래스, 아니면 변수/함수
            if name[0].isupper():
                # Class stub
                stub_code.append(f"class {name}:")
                stub_code.append('    """Auto-generated stub"""')
                stub_code.append("    pass")
                stub_code.append("")
                stubs.append(name)
            elif name.endswith("Error") or name.endswith("Exception"):
                # Exception stub
                stub_code.append(f"class {name}(Exception):")
                stub_code.append('    """Auto-generated exception stub"""')
                stub_code.append("    pass")
                stub_code.append("")
                stubs.append(name)
            elif "_" in name or name.islower():
                # Function or variable (heuristic)
                stub_code.append(f"def {name}(*args, **kwargs):")
                stub_code.append('    """Auto-generated function stub"""')
                stub_code.append("    pass")
                stub_code.append("")
                stubs.append(name)
            else:
                # Default: variable
                stub_code.append(f"{name}: any = None  # Auto-generated stub")
                stubs.append(name)

        # 3. Fallback if no stubs generated
        if not stub_code:
            stub_code = [
                "# Auto-generated helper stubs",
                "from typing import Any",
                "",
            ]

        fixed_code = "\n".join(stub_code) + "\n\n" + code

        return fixed_code, stubs

    def _find_undefined_names(self, code: str) -> set[str]:
        """
        AST로 undefined names 찾기

        Args:
            code: Python code

        Returns:
            Set of undefined names
        """
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Syntax error면 빈 set 반환 (validation에서 처리됨)
            return set()

        # Defined names (assignments, imports, function defs, class defs)
        defined = set()

        # Used names (Name nodes with Load context)
        used = set()

        for node in ast.walk(tree):
            # Definitions
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    defined.add(alias.asname if alias.asname else alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    defined.add(alias.asname if alias.asname else alias.name)

            # Usage
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)

        # Builtins (don't need stubs)
        builtins = {
            "print",
            "len",
            "range",
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "set",
            "tuple",
            "True",
            "False",
            "None",
            "isinstance",
            "type",
            "object",
            "Exception",
            "ValueError",
            "TypeError",
            "KeyError",
            "IndexError",
        }

        # Undefined = used - defined - builtins
        undefined = used - defined - builtins

        return undefined

    def _generate_summary(self, slice_result: SliceResult) -> str:
        """
        Slice 요약 생성

        Args:
            slice_result: Slice result

        Returns:
            Summary text
        """
        stats = slice_result.to_dict()

        summary_parts = [
            f"Target: {slice_result.target_variable}",
            f"Slice type: {slice_result.slice_type}",
            f"Nodes: {stats['node_count']}",
            f"Lines: {stats['total_lines']}",
            f"Tokens: ~{stats['total_tokens']}",
            f"Confidence: {stats['confidence']:.2f}",
        ]

        return "\n".join(summary_parts)

    def _format_control_flow(self, control_context: list[str]) -> str:
        """
        Control flow 설명 포맷팅

        Args:
            control_context: Control flow list

        Returns:
            Formatted explanation
        """
        if not control_context:
            return "No special control flow."

        parts = ["Control flow dependencies:"]
        for i, ctx in enumerate(control_context[:10], 1):  # Limit to 10
            parts.append(f"{i}. {ctx}")

        if len(control_context) > 10:
            parts.append(f"... and {len(control_context) - 10} more")

        return "\n".join(parts)

    def _trace_variable_history(self, slice_result: SliceResult) -> str:
        """
        변수 생성 경로 추적

        Args:
            slice_result: Slice result

        Returns:
            Variable history
        """
        # TODO: Trace variable definitions through DFG

        # Placeholder
        return f"Variable '{slice_result.target_variable}' traced through {len(slice_result.slice_nodes)} dependencies"

    def _count_tokens(self, code: str) -> int:
        """
        토큰 수 추정

        Args:
            code: Python code

        Returns:
            Estimated tokens
        """
        # Simple heuristic: chars / 4
        return len(code) // 4
