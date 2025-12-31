"""
Ports (Interfaces)

Hexagonal Architecture의 핵심 인터페이스 정의
ADR-011 8-Step Pipeline 지원
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from codegraph_runtime.codegen_loop.domain.patch import Patch

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
from codegraph_runtime.codegen_loop.domain.semantic_contract import SemanticContract
from codegraph_runtime.codegen_loop.domain.specs.arch_spec import ArchSpecValidationResult
from codegraph_runtime.codegen_loop.domain.specs.integrity_spec import IntegritySpecValidationResult
from codegraph_runtime.codegen_loop.domain.specs.security_spec import SecuritySpecValidationResult


class LLMPort(ABC):
    """
    LLM 포트 (추상)

    Infrastructure가 구현
    """

    @abstractmethod
    async def generate_patch(
        self,
        task_description: str,
        file_paths: list[str],
        existing_code: dict[str, str],
        feedback: str = "",
    ) -> Patch:
        """
        패치 생성 (Step 3)

        Args:
            task_description: 작업 설명
            file_paths: 대상 파일 경로들
            existing_code: {file_path: code} 매핑
            feedback: 이전 시도 피드백

        Returns:
            생성된 패치 (Multi-file 지원)
        """
        pass


class HCGPort(ABC):
    """
    HCG (Hierarchical Code Graph) 포트

    Infrastructure가 구현
    """

    # ========== Step 1: Scope Selection ==========

    @abstractmethod
    async def query_scope(
        self,
        task_description: str,
        max_files: int = 10,
    ) -> list[str]:
        """
        작업 범위 선택 (HCG Query)

        Args:
            task_description: 작업 설명
            max_files: 최대 파일 수

        Returns:
            관련 파일 경로 리스트
        """
        pass

    # ========== Step 5: Semantic Contract Validation ==========

    @abstractmethod
    async def find_callers(
        self,
        function_fqn: str,
        version: str = "before",
    ) -> list[str]:
        """
        함수 호출자 찾기

        Args:
            function_fqn: 함수 FQN
            version: "before" or "after"

        Returns:
            호출자 FQN 리스트
        """
        pass

    @abstractmethod
    async def extract_contract(
        self,
        function_fqn: str,
        version: str = "before",
    ) -> SemanticContract:
        """
        의미적 계약 추출

        Args:
            function_fqn: 함수 FQN
            version: "before" or "after"

        Returns:
            추출된 계약
        """
        pass

    @abstractmethod
    async def detect_renames(self, patch: Patch) -> dict[str, str]:
        """
        Rename 감지 (implicit)

        Args:
            patch: 적용할 패치

        Returns:
            {old_name: new_name} 매핑
        """
        pass

    # ========== Step 6: HCG Incremental Update ==========

    @abstractmethod
    async def incremental_update(self, patch: Patch) -> bool:
        """
        HCG 증분 업데이트

        Args:
            patch: 적용된 패치

        Returns:
            업데이트 성공 여부
        """
        pass

    # ========== Step 7: GraphSpec Validation ==========

    @abstractmethod
    async def verify_architecture(self, patch: Patch) -> ArchSpecValidationResult:
        """
        아키텍처 규칙 검증

        Args:
            patch: 검증 대상 패치

        Returns:
            검증 결과
        """
        pass

    @abstractmethod
    async def verify_security(self, patch: Patch) -> SecuritySpecValidationResult:
        """
        보안 규칙 검증

        Args:
            patch: 검증 대상 패치

        Returns:
            검증 결과
        """
        pass

    @abstractmethod
    async def verify_integrity(self, patch: Patch) -> IntegritySpecValidationResult:
        """
        무결성 검증 (Resource Leak)

        Args:
            patch: 검증 대상 패치

        Returns:
            검증 결과
        """
        pass


class SandboxPort(ABC):
    """
    Sandbox 실행 포트

    Infrastructure가 구현
    """

    # ========== Step 4: Lint/Build/TypeCheck ==========

    @abstractmethod
    async def validate_syntax(self, code: str, language: str = "python") -> dict:
        """
        문법 검증

        Args:
            code: 검증할 코드
            language: 언어

        Returns:
            검증 결과
            {
                "valid": bool,
                "errors": List[str]
            }
        """
        pass

    @abstractmethod
    async def run_linter(self, patch: Patch) -> dict:
        """
        Linter 실행

        Args:
            patch: 검증할 패치

        Returns:
            린트 결과
            {
                "score": float,  # 0.0~1.0
                "errors": List[str],
                "warnings": List[str]
            }
        """
        pass

    @abstractmethod
    async def run_type_check(self, patch: Patch) -> dict:
        """
        타입 체크 실행

        Args:
            patch: 검증할 패치

        Returns:
            타입 체크 결과
            {
                "valid": bool,
                "errors": List[str]
            }
        """
        pass

    @abstractmethod
    async def build(self, patch: Patch) -> dict:
        """
        빌드 실행

        Args:
            patch: 빌드할 패치

        Returns:
            빌드 결과
            {
                "success": bool,
                "errors": List[str]
            }
        """
        pass

    # ========== Step 8: Test Execution ==========

    @abstractmethod
    async def execute_tests(
        self,
        patch: Patch,
    ) -> dict:
        """
        테스트 실행

        Args:
            patch: 적용할 패치

        Returns:
            테스트 결과
            {
                "pass_rate": float,
                "passed": int,
                "failed": int,
                "errors": List[str],
                "coverage": float
            }
        """
        pass

    # ========== TestGen: Coverage & Flakiness ==========

    @abstractmethod
    async def measure_coverage(
        self,
        test_code: str,
        target_code: str,
    ) -> dict:
        """
        커버리지 측정

        Args:
            test_code: 테스트 코드
            target_code: 대상 코드

        Returns:
            커버리지 결과
            {
                "branch_coverage": float (0.0~1.0),
                "line_coverage": float,
                "condition_coverage": dict,  # {condition_id: {True: bool, False: bool}}
                "uncovered_lines": List[int]
            }
        """
        pass

    @abstractmethod
    async def detect_flakiness(
        self,
        test_code: str,
        iterations: int = 10,
    ) -> dict:
        """
        Flakiness 감지 (ADR-011 Section 12)

        Args:
            test_code: 테스트 코드
            iterations: 반복 횟수 (기본 10회)

        Returns:
            Flakiness 결과
            {
                "flakiness_ratio": float (0.0~1.0),
                "failed_count": int,
                "is_flaky": bool  # ratio > 0.3
            }
        """
        pass


class TestCoveragePort(ABC):
    """
    테스트 커버리지 포트

    TestGen에 특화된 커버리지 분석
    """

    @abstractmethod
    async def measure_branch_coverage(
        self,
        test_code: str,
        target_function: str,
    ) -> float:
        """
        Branch 커버리지 측정

        Args:
            test_code: 테스트 코드
            target_function: 대상 함수 FQN

        Returns:
            커버리지 (0.0 ~ 1.0)
        """
        pass

    @abstractmethod
    async def detect_uncovered_branches(
        self,
        target_function: str,
        existing_tests: list[str],
    ) -> list[dict]:
        """
        미커버 브랜치 탐지

        Args:
            target_function: 대상 함수 FQN
            existing_tests: 기존 테스트 코드

        Returns:
            미커버 브랜치 목록
            [
                {
                    "branch_id": str,
                    "line": int,
                    "condition": str
                }
            ]
        """
        pass


class TestGenPort(ABC):
    """
    테스트 생성 포트

    LLM 기반 테스트 생성
    """

    @abstractmethod
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
            path_description: 테스트 경로 설명
            template: 테스트 템플릿 (pytest, unittest 등)

        Returns:
            생성된 테스트 코드
        """
        pass

    @abstractmethod
    async def synthesize_inputs(
        self,
        param_types: dict[str, str],
    ) -> list[dict]:
        """
        입력 값 합성 (ADR-011 Section 12)

        Args:
            param_types: {param_name: type_str}

        Returns:
            입력 값 목록
            [
                {
                    "param_name": "value",
                    "category": "boundary" | "invalid" | "normal"
                }
            ]
        """
        pass

    @abstractmethod
    async def validate_mock_integrity(
        self,
        test_code: str,
        ir_document: "IRDocument",  # type: ignore
    ) -> dict:
        """
        Mock 무결성 검증 (ADR-011 Section 12)

        Args:
            test_code: 테스트 코드
            ir_document: IR 문서 (signature 검증용)

        Returns:
            검증 결과
            {
                "valid": bool,
                "errors": List[str],  # "Unknown API", "Signature mismatch"
                "warnings": List[str]
            }
        """
        pass
