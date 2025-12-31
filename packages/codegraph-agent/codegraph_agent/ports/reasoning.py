"""
Reasoning Ports (Interfaces)

RFC-060: SOTA Agent Code Editing
- 복잡도 분석
- 위험도 평가
- 그래프 분석
- ToT/LATS 실행
"""

from typing import Any, Protocol


class IComplexityAnalyzer(Protocol):
    """
    복잡도 분석 Port

    구현체:
    - RadonComplexityAnalyzer (Radon 라이브러리)
    - ASTComplexityAnalyzer (AST 기반)
    """

    def analyze_cyclomatic(self, code: str) -> float:
        """Cyclomatic Complexity 계산"""
        ...

    def analyze_cognitive(self, code: str) -> float:
        """Cognitive Complexity 계산"""
        ...

    def count_impact_nodes(self, file_path: str) -> int:
        """CFG 영향 노드 수 계산"""
        ...


class IRiskAssessor(Protocol):
    """
    위험도 평가 Port

    구현체:
    - HistoricalRiskAssessor (경험 기반)
    - StaticRiskAssessor (정적 분석)
    """

    def assess_regression_risk(
        self,
        problem_description: str,
        file_paths: list[str],
    ) -> float:
        """Regression 위험도 평가 (0.0 ~ 1.0)"""
        ...

    def check_security_sink(self, code: str) -> bool:
        """보안 sink 접근 여부 확인"""
        ...

    def check_test_failure(self, file_paths: list[str]) -> bool:
        """최근 테스트 실패 여부 확인"""
        ...


class IGraphAnalyzer(Protocol):
    """
    그래프 분석 Port

    구현체:
    - MemgraphAnalyzer (Memgraph 기반)
    - NetworkXAnalyzer (NetworkX 기반)
    - SimpleGraphAnalyzer (로컬 AST)
    """

    def analyze_graph_impact(
        self,
        file_changes: dict[str, str],
    ) -> Any:
        """Graph Impact 분석"""
        ...

    def calculate_impact_radius(
        self,
        changed_files: list[str],
    ) -> int:
        """영향 반경 계산 (BFS)"""
        ...

    def analyze_execution_trace(
        self,
        before_code: str,
        after_code: str,
    ) -> Any:
        """실행 추적 분석"""
        ...


class IToTExecutor(Protocol):
    """
    Tree-of-Thought 실행 Port

    구현체:
    - LangGraphToTExecutor (LangGraph 기반, SOTA)
    - SimpleToTExecutor (단순 병렬)
    """

    async def generate_strategies(
        self,
        problem: str,
        context: dict[str, Any],
        count: int = 3,
    ) -> list[Any]:
        """LLM으로 전략 생성"""
        ...

    async def execute_strategy(
        self,
        strategy: Any,
        timeout: int = 60,
    ) -> Any:
        """Sandbox에서 전략 실행"""
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

    async def generate_next_thoughts(
        self,
        current_state: str,
        problem: str,
        context: dict[str, Any],
        k: int = 3,
    ) -> list[str]:
        """다음 step 생성 (LLM)"""
        ...

    async def evaluate_thought(
        self,
        partial_thought: str,
    ) -> float:
        """중간 평가 (0.0 ~ 1.0)"""
        ...

    async def generate_complete_strategy(
        self,
        thought_path: list[str],
        problem: str,
        context: dict[str, Any],
    ) -> Any:
        """Thought 경로 → 완전한 전략"""
        ...


class ISandboxExecutor(Protocol):
    """
    Sandbox 실행 Port

    구현체:
    - DockerSandbox (Docker 기반)
    - LocalSandbox (로컬 프로세스)
    """

    async def execute_code(
        self,
        file_changes: dict[str, str],
        timeout: int = 60,
    ) -> Any:
        """코드 실행 및 평가"""
        ...

    def cleanup(self) -> None:
        """Sandbox 정리"""
        ...
