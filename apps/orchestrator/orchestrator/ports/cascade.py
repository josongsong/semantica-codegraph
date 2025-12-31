"""
CASCADE 컴포넌트 Port 정의 (Hexagonal Architecture)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

# ============================================================================
# Domain Models (Business Logic 포함)
# ============================================================================


class PatchStatus(Enum):
    """패치 적용 상태"""

    SUCCESS = "success"
    FUZZY_APPLIED = "fuzzy_applied"
    FAILED = "failed"
    CONFLICT = "conflict"


class ReproductionStatus(Enum):
    """재현 스크립트 상태"""

    FAIL_CONFIRMED = "fail_confirmed"  # 버그 재현 성공 (기대)
    PASS_UNEXPECTED = "pass_unexpected"  # 이미 통과 (작업 불필요)
    ERROR = "error"


class ProcessStatus(Enum):
    """프로세스 상태"""

    RUNNING = "running"
    ZOMBIE = "zombie"
    KILLED = "killed"


@dataclass
class DiffAnchor:
    """Diff 앵커 포인트"""

    line_number: int
    content: str
    context_before: list[str]
    context_after: list[str]

    def signature(self) -> str:
        """앵커의 고유 시그니처 생성"""
        return f"{self.content.strip()}::{len(self.context_before)}"


@dataclass
class PatchResult:
    """패치 적용 결과"""

    status: PatchStatus
    applied_lines: list[int]
    conflicts: list[str]
    fuzzy_matches: dict[int, float]  # line_number -> confidence

    def is_success(self) -> bool:
        return self.status in (PatchStatus.SUCCESS, PatchStatus.FUZZY_APPLIED)

    def confidence_score(self) -> float:
        """퍼지 매칭 신뢰도 평균"""
        if not self.fuzzy_matches:
            return 1.0 if self.status == PatchStatus.SUCCESS else 0.0
        return sum(self.fuzzy_matches.values()) / len(self.fuzzy_matches)


@dataclass
class ReproductionScript:
    """재현 스크립트"""

    script_path: str
    content: str
    issue_description: str
    expected_failure_pattern: str  # 예상 실패 패턴 (regex)

    def should_fail(self) -> bool:
        """스크립트가 실패해야 하는가 (버그 재현)"""
        return True


@dataclass
class ReproductionResult:
    """재현 결과"""

    status: ReproductionStatus
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float

    def is_bug_reproduced(self) -> bool:
        """버그가 재현되었는가"""
        return self.status == ReproductionStatus.FAIL_CONFIRMED


@dataclass
class ProcessInfo:
    """프로세스 정보"""

    pid: int
    name: str
    status: ProcessStatus
    ports: list[int]
    cpu_percent: float
    memory_mb: float

    def is_zombie(self) -> bool:
        return self.status == ProcessStatus.ZOMBIE

    def should_kill(self) -> bool:
        """강제 종료 대상인가"""
        return self.is_zombie() or self.cpu_percent > 90


@dataclass
class GraphNode:
    """Graph RAG 노드"""

    node_id: str
    content: str
    node_type: str  # function, class, module
    pagerank_score: float
    call_depth: int

    def should_include_body(self) -> bool:
        """본문을 포함해야 하는가 (PageRank 기반)"""
        # Top 20% 노드는 본문 포함, 나머지는 시그니처만
        return self.pagerank_score > 0.8 or self.call_depth <= 2


@dataclass
class PrunedContext:
    """토큰 최적화된 컨텍스트"""

    full_nodes: list[GraphNode]  # 본문 포함
    signature_only_nodes: list[GraphNode]  # 시그니처만
    total_tokens: int
    compression_ratio: float

    def is_within_budget(self, max_tokens: int) -> bool:
        return self.total_tokens <= max_tokens


# ============================================================================
# Ports (Interfaces)
# ============================================================================


class IFuzzyPatcher(Protocol):
    """Smart Fuzzy Patcher Port"""

    async def apply_patch(self, file_path: str, diff: str, fallback_to_fuzzy: bool = True) -> PatchResult:
        """
        패치 적용 (git apply 실패 시 fuzzy matching)

        Args:
            file_path: 대상 파일 경로
            diff: Unified Diff 문자열
            fallback_to_fuzzy: git apply 실패 시 fuzzy 사용 여부

        Returns:
            PatchResult: 적용 결과
        """
        ...

    async def find_anchors(self, file_content: str, target_block: str) -> list[DiffAnchor]:
        """
        변경 대상 블록의 앵커 포인트 탐색

        Args:
            file_content: 파일 내용
            target_block: 찾을 코드 블록

        Returns:
            List[DiffAnchor]: 발견된 앵커들
        """
        ...

    async def fuzzy_match(self, anchor: DiffAnchor, file_content: str, threshold: float = 0.8) -> int | None:
        """
        Fuzzy matching으로 앵커 위치 찾기

        Args:
            anchor: 찾을 앵커
            file_content: 파일 내용
            threshold: 최소 신뢰도 (0.0 ~ 1.0)

        Returns:
            Optional[int]: 매칭된 라인 번호 (없으면 None)
        """
        ...


class IReproductionEngine(Protocol):
    """Reproduction-First Strategy Port"""

    async def generate_reproduction_script(
        self, issue_description: str, context_files: list[str], tech_stack: dict[str, str]
    ) -> ReproductionScript:
        """
        버그 재현 스크립트 생성

        Args:
            issue_description: 이슈 설명
            context_files: 관련 파일 목록
            tech_stack: 기술 스택 (e.g., {"test_framework": "pytest"})

        Returns:
            ReproductionScript: 생성된 스크립트
        """
        ...

    async def verify_failure(self, script: ReproductionScript) -> ReproductionResult:
        """
        스크립트 실행 및 실패 확인

        Args:
            script: 재현 스크립트

        Returns:
            ReproductionResult: 실행 결과
        """
        ...

    async def verify_fix(self, script: ReproductionScript, after_changes: bool = True) -> ReproductionResult:
        """
        수정 후 스크립트 성공 확인

        Args:
            script: 재현 스크립트
            after_changes: 변경 적용 후인지 여부

        Returns:
            ReproductionResult: 실행 결과
        """
        ...


class IProcessManager(Protocol):
    """Zombie Process Killer Port"""

    async def scan_processes(self, sandbox_id: str) -> list[ProcessInfo]:
        """
        샌드박스 내 프로세스 스캔

        Args:
            sandbox_id: 샌드박스 ID

        Returns:
            List[ProcessInfo]: 프로세스 목록
        """
        ...

    async def kill_zombies(self, sandbox_id: str, force: bool = False) -> list[int]:
        """
        좀비 프로세스 강제 종료

        Args:
            sandbox_id: 샌드박스 ID
            force: SIGKILL 사용 여부 (기본 SIGTERM)

        Returns:
            List[int]: 종료된 PID 목록
        """
        ...

    async def cleanup_ports(self, sandbox_id: str, port_range: tuple[int, int] = (8000, 9000)) -> list[int]:
        """
        점유된 포트 정리

        Args:
            sandbox_id: 샌드박스 ID
            port_range: 정리 대상 포트 범위

        Returns:
            List[int]: 정리된 포트 목록
        """
        ...


class IGraphPruner(Protocol):
    """Graph RAG PageRank Pruner Port"""

    async def calculate_pagerank(
        self, nodes: list[GraphNode], edges: list[tuple[str, str]], damping: float = 0.85
    ) -> dict[str, float]:
        """
        PageRank 계산

        Args:
            nodes: 노드 목록
            edges: 엣지 목록 (from_id, to_id)
            damping: Damping factor

        Returns:
            Dict[str, float]: node_id -> pagerank_score
        """
        ...

    async def prune_context(
        self, nodes: list[GraphNode], max_tokens: int = 8000, top_k_full: int = 20
    ) -> PrunedContext:
        """
        토큰 예산 내에서 컨텍스트 최적화

        Args:
            nodes: 노드 목록 (PageRank 계산 완료)
            max_tokens: 최대 토큰 수
            top_k_full: 본문 포함할 상위 K개 노드

        Returns:
            PrunedContext: 최적화된 컨텍스트
        """
        ...

    async def estimate_tokens(self, content: str) -> int:
        """
        토큰 수 추정

        Args:
            content: 텍스트 내용

        Returns:
            int: 예상 토큰 수
        """
        ...


# ============================================================================
# Composite Port (CASCADE Orchestrator)
# ============================================================================


class ICascadeOrchestrator(Protocol):
    """CASCADE 전체 오케스트레이션 Port"""

    async def execute_tdd_cycle(
        self, issue_description: str, context_files: list[str], max_retries: int = 3
    ) -> dict[str, Any]:
        """
        TDD 사이클 실행 (Reproduction-First)

        1. Reproduction Script 생성
        2. Verify Failure (버그 재현)
        3. Code 수정 (Fuzzy Patch 사용)
        4. Verify Pass (수정 확인)

        Args:
            issue_description: 이슈 설명
            context_files: 관련 파일 목록
            max_retries: 최대 재시도 횟수

        Returns:
            Dict: 실행 결과
        """
        ...

    async def optimize_context(self, repo_path: str, query: str, max_tokens: int = 8000) -> PrunedContext:
        """
        Graph RAG 기반 컨텍스트 최적화

        Args:
            repo_path: 레포지토리 경로
            query: 쿼리
            max_tokens: 최대 토큰 수

        Returns:
            PrunedContext: 최적화된 컨텍스트
        """
        ...
