"""
Reasoning Ports (Interfaces)

Port = Adapter가 구현해야 하는 계약(Contract)
"""

from typing import Protocol


class IComplexityAnalyzer(Protocol):
    """
    복잡도 분석 Port

    구현체:
    - RadonComplexityAnalyzer (Radon 라이브러리)
    - ASTComplexityAnalyzer (AST 기반)
    """

    def analyze_cyclomatic(self, code: str) -> float:
        """
        Cyclomatic Complexity 계산

        Args:
            code: 소스 코드

        Returns:
            복잡도 점수 (0.0+)
        """
        ...

    def analyze_cognitive(self, code: str) -> float:
        """
        Cognitive Complexity 계산

        Args:
            code: 소스 코드

        Returns:
            인지 복잡도 (0.0+)
        """
        ...

    def count_impact_nodes(self, file_path: str) -> int:
        """
        CFG 영향 노드 수 계산

        Args:
            file_path: 파일 경로

        Returns:
            영향받는 노드 수
        """
        ...


class IRiskAssessor(Protocol):
    """
    위험도 평가 Port

    구현체:
    - HistoricalRiskAssessor (경험 기반)
    - StaticRiskAssessor (정적 분석)
    """

    def assess_regression_risk(self, problem_description: str, file_paths: list[str]) -> float:
        """
        Regression 위험도 평가

        Args:
            problem_description: 문제 설명
            file_paths: 변경 대상 파일들

        Returns:
            위험도 점수 (0.0 ~ 1.0)
        """
        ...

    def check_security_sink(self, code: str) -> bool:
        """
        보안 sink 접근 여부 확인

        Args:
            code: 소스 코드

        Returns:
            True if touches security sink
        """
        ...

    def check_test_failure(self, file_paths: list[str]) -> bool:
        """
        최근 테스트 실패 여부 확인

        Args:
            file_paths: 파일 경로들

        Returns:
            True if recent test failure
        """
        ...


class IGraphAnalyzer(Protocol):
    """
    그래프 분석 Port

    구현체:
    - MemgraphAnalyzer (Memgraph 기반)
    - NetworkXAnalyzer (NetworkX 기반)
    - SimpleGraphAnalyzer (로컬 AST)
    """

    def analyze_graph_impact(self, file_changes: dict[str, str]):
        """
        Graph Impact 분석

        Args:
            file_changes: {file_path: new_content}

        Returns:
            GraphImpact (Domain Model)
        """
        ...

    def calculate_impact_radius(self, changed_files: list[str]) -> int:
        """
        영향 반경 계산 (BFS)

        Args:
            changed_files: 변경된 파일들

        Returns:
            영향받는 노드 수
        """
        ...

    def analyze_execution_trace(self, before_code: str, after_code: str):
        """
        실행 추적 분석

        Args:
            before_code: 변경 전 코드
            after_code: 변경 후 코드

        Returns:
            ExecutionTrace (Domain Model)
        """
        ...


class IToTExecutor(Protocol):
    """
    Tree-of-Thought 실행 Port

    구현체:
    - LangGraphToTExecutor (LangGraph 기반, SOTA)
    - SimpleToTExecutor (단순 병렬)
    """

    async def generate_strategies(self, problem: str, context: dict, count: int = 3) -> list:
        """
        LLM으로 전략 생성

        Args:
            problem: 문제 설명
            context: 컨텍스트 (파일, 코드 등)
            count: 생성할 전략 수

        Returns:
            CodeStrategy 리스트
        """
        ...

    async def execute_strategy(self, strategy, timeout: int = 60):
        """
        Sandbox에서 전략 실행

        Args:
            strategy: CodeStrategy
            timeout: 실행 타임아웃 (초)

        Returns:
            ExecutionResult
        """
        ...


class ILATSExecutor(IToTExecutor, Protocol):
    """
    LATS Executor Port (IToTExecutor 확장)

    구현체:
    - LATSExecutor (v9)

    LATS 전용 메서드:
    - generate_next_thoughts: 다음 단계 생성
    - evaluate_thought: 중간 평가
    - generate_complete_strategy: Thought 경로 → 전략
    """

    # IToTExecutor 메서드 (하위 호환)
    async def generate_strategies(self, problem: str, context: dict, count: int = 3) -> list:
        """전략 생성 (하위 호환)"""
        ...

    async def execute_strategy(self, strategy, timeout: int = 60):
        """전략 실행 (하위 호환)"""
        ...

    # LATS 전용 메서드
    async def generate_next_thoughts(
        self,
        current_state: str,
        problem: str,
        context: dict,
        k: int = 3,
    ) -> list[str]:
        """
        다음 step 생성 (LLM)

        Args:
            current_state: 현재 Thought
            problem: 문제
            context: 컨텍스트
            k: 생성할 개수

        Returns:
            다음 Thought들
        """
        ...

    async def evaluate_thought(
        self,
        partial_thought: str,
    ) -> float:
        """
        중간 평가 (0.0 ~ 1.0)

        Args:
            partial_thought: 평가할 Thought

        Returns:
            평가 점수
        """
        ...

    async def generate_complete_strategy(
        self,
        thought_path: list[str],
        problem: str,
        context: dict,
    ):
        """
        Thought 경로 → 완전한 전략

        Args:
            thought_path: Root부터의 Thought 경로
            problem: 문제
            context: 컨텍스트

        Returns:
            CodeStrategy
        """
        ...


class ISandboxExecutor(Protocol):
    """
    Sandbox 실행 Port (Code Domain)

    구현체:
    - DockerSandbox (Docker 기반)
    - LocalSandbox (로컬 프로세스)
    """

    async def execute_code(self, file_changes: dict[str, str], timeout: int = 60):
        """
        코드 실행 및 평가

        Args:
            file_changes: {path: content}
            timeout: 타임아웃

        Returns:
            ExecutionResult
        """
        ...

    def cleanup(self):
        """Sandbox 정리"""
        ...
