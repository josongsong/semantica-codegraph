"""
TestGenAdapter - LLM 기반 테스트 생성

TestGenPort 구현
"""

import ast
from typing import TYPE_CHECKING

from codegraph_runtime.codegen_loop.application.ports import LLMPort, TestGenPort

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument


class TestGenAdapter(TestGenPort):
    """
    LLM 기반 테스트 생성

    ADR-011 명세:
    - Input synthesis (boundary, invalid)
    - Mock integrity 검증
    - pytest 템플릿 사용

    Hexagonal Architecture:
    - LLMPort에 위임
    """

    def __init__(self, llm: LLMPort):
        """
        초기화

        Args:
            llm: LLM 포트
        """
        self.llm = llm

    async def generate_test(
        self,
        target_function: str,
        path_description: str,
        template: str = "pytest",
    ) -> str:
        """
        테스트 생성

        Args:
            target_function: 대상 함수 FQN
            path_description: 경로 설명
            template: 템플릿

        Returns:
            생성된 테스트 코드
        """
        # LLM 프롬프트 구성
        prompt = self._build_prompt(target_function, path_description, template)

        # LLM 호출 (generate_patch 재사용)
        # Note: LLMPort에 generate_test 메서드 추가 권장
        patch = await self.llm.generate_patch(
            task_description=prompt,
            file_paths=[],
            existing_code={},
        )

        # Patch에서 test 코드 추출
        if patch.files:
            return patch.files[0].new_content or ""

        # Fallback: 템플릿 기반 기본 테스트
        return self._generate_template_test(target_function)

    async def synthesize_inputs(
        self,
        param_types: dict[str, str],
    ) -> list[dict]:
        """
        입력 값 합성

        ADR-011 Section 12:
        - Boundary values
        - Invalid values
        - Normal values

        Args:
            param_types: {param_name: type_str}

        Returns:
            입력 값 목록
        """
        inputs = []

        for param_name, type_str in param_types.items():
            # Boundary values
            if "int" in type_str.lower():
                inputs.extend(
                    [
                        {param_name: -1, "category": "boundary"},
                        {param_name: 0, "category": "boundary"},
                        {param_name: 1, "category": "boundary"},
                    ]
                )
            elif "str" in type_str.lower():
                inputs.extend(
                    [
                        {param_name: "", "category": "boundary"},
                        {param_name: "x", "category": "normal"},
                        {param_name: "x" * 1000, "category": "boundary"},
                    ]
                )
            elif "list" in type_str.lower():
                inputs.extend(
                    [
                        {param_name: [], "category": "boundary"},
                        {param_name: [1], "category": "normal"},
                        {param_name: [1, 2, 3], "category": "normal"},
                    ]
                )

            # Invalid values
            inputs.append({param_name: None, "category": "invalid"})

        return inputs[:10]  # 최대 10개

    async def validate_mock_integrity(
        self,
        test_code: str,
        ir_document: "IRDocument",  # type: ignore
    ) -> dict:
        """
        Mock 무결성 검증

        ADR-011 Section 12:
        - 존재하지 않는 API 체크
        - Signature 불일치 체크

        Args:
            test_code: 테스트 코드
            ir_document: IR 문서

        Returns:
            검증 결과
        """
        errors = []
        warnings = []

        # AST로 mock 호출 찾기
        try:
            tree = ast.parse(test_code)
        except SyntaxError as e:
            return {"valid": False, "errors": [f"Syntax error: {e}"], "warnings": []}

        # mock.patch, MagicMock 등 찾기
        mock_targets = self._extract_mock_targets(tree)

        for target_info in mock_targets:
            target = target_info["name"]
            mock_args_count = target_info.get("args_count", 0)

            # IR에서 target 찾기
            nodes = ir_document.find_nodes_by_name(target.split(".")[-1])
            if not nodes:
                errors.append(f"Unknown API: {target}")
                continue

            # Signature 검증
            node = nodes[0]

            # Check if node has signature info
            if hasattr(node, "attrs") and "signature" in node.attrs:
                sig_str = node.attrs["signature"]
                # Parse parameter count from signature string
                # e.g., "(x: int, y: str) -> bool" → 2 params
                param_count = self._count_params_from_signature(sig_str)

                if param_count >= 0 and mock_args_count != param_count:
                    errors.append(f"Signature mismatch: {target} expects {param_count} args, got {mock_args_count}")
            else:
                # No signature info - warning only
                warnings.append(f"No signature info for {target}, skipping validation")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def _count_params_from_signature(self, sig_str: str) -> int:
        """
        Signature 문자열에서 파라미터 개수 추출

        Args:
            sig_str: e.g., "(x: int, y: str) -> bool"

        Returns:
            파라미터 개수 (-1 if parse failed)
        """
        try:
            # Extract params between first ( and )
            start = sig_str.find("(")
            end = sig_str.find(")")

            if start == -1 or end == -1:
                return -1

            params_str = sig_str[start + 1 : end].strip()

            if not params_str:
                return 0  # No params

            # Count commas + 1 (simple heuristic)
            # Handle: "self, x, y" or "x: int, y: str"
            params = [p.strip() for p in params_str.split(",") if p.strip()]

            # Filter out 'self', 'cls', '*args', '**kwargs'
            params = [
                p
                for p in params
                if not p.startswith("self")
                and not p.startswith("cls")
                and not p.startswith("*args")
                and not p.startswith("**kwargs")
            ]

            return len(params)

        except Exception:
            return -1  # Parse failed

    def _build_prompt(
        self,
        target_function: str,
        path_description: str,
        template: str,
    ) -> str:
        """LLM 프롬프트 생성"""
        return f"""Generate a {template} test for function: {target_function}

Test scenario: {path_description}

Requirements:
- Use pytest framework
- Include boundary values (0, -1, 1, empty, None)
- Include error cases (exceptions)
- Use @pytest.mark.parametrize for multiple inputs
- Follow AAA pattern (Arrange, Act, Assert)

Generate ONLY the test code, no explanations.
"""

    def _generate_template_test(self, target_function: str) -> str:
        """템플릿 기반 기본 테스트"""
        func_name = target_function.split(".")[-1]
        return f'''import pytest

def test_{func_name}_base():
    """Base test case"""
    # Arrange
    input_value = 1

    # Act
    result = {func_name}(input_value)

    # Assert
    assert result is not None


@pytest.mark.parametrize("input_value,expected", [
    (0, 0),
    (1, 2),
    (-1, -1),
])
def test_{func_name}_parametrized(input_value, expected):
    """Parametrized test"""
    result = {func_name}(input_value)
    assert result == expected


def test_{func_name}_error():
    """Error case test"""
    with pytest.raises(Exception):
        {func_name}(None)
'''

    def _extract_mock_targets(self, tree: ast.AST) -> list[dict]:
        """
        AST에서 mock 대상 추출

        Args:
            tree: AST

        Returns:
            [{"name": str, "args_count": int}, ...]
        """
        targets = []

        for node in ast.walk(tree):
            # mock.patch("target")
            if isinstance(node, ast.Call):
                if hasattr(node.func, "attr") and node.func.attr == "patch":  # type: ignore
                    if node.args and isinstance(node.args[0], ast.Constant):
                        target_name = node.args[0].value
                        targets.append({"name": target_name, "args_count": 0})

                # MagicMock() or Mock()
                elif hasattr(node.func, "id") and node.func.id in ["MagicMock", "Mock"]:  # type: ignore
                    # Mock object creation - no specific target
                    pass

        return targets
