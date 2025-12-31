"""
CASCADE 컴포넌트 Port 정의 (Hexagonal Architecture)

RFC-060: SOTA Agent Code Editing
- IFuzzyPatcher: Smart Fuzzy Patching
- IReproductionEngine: TDD Reproduction-First
- IProcessManager: Sandbox Process Management
- IGraphPruner: PageRank-based Context Pruning
- ICascadeOrchestrator: Full TDD Cycle Orchestration
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


# ============================================================================
# Domain Models (Value Objects)
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


@dataclass(frozen=True)
class DiffAnchor:
    """Diff 앵커 포인트 (Immutable Value Object)"""

    line_number: int
    content: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]

    def signature(self) -> str:
        """앵커의 고유 시그니처 생성"""
        return f"{self.content.strip()}::{len(self.context_before)}"


@dataclass(frozen=True)
class PatchResult:
    """패치 적용 결과 (Immutable Value Object)"""

    status: PatchStatus
    applied_lines: tuple[int, ...]
    conflicts: tuple[str, ...]
    fuzzy_matches: tuple[tuple[int, float], ...]  # (line_number, confidence)

    def is_success(self) -> bool:
        return self.status in (PatchStatus.SUCCESS, PatchStatus.FUZZY_APPLIED)

    def confidence_score(self) -> float:
        """퍼지 매칭 신뢰도 평균"""
        if not self.fuzzy_matches:
            return 1.0 if self.status == PatchStatus.SUCCESS else 0.0
        return sum(c for _, c in self.fuzzy_matches) / len(self.fuzzy_matches)


@dataclass(frozen=True)
class ReproductionScript:
    """재현 스크립트 (Immutable Value Object)"""

    script_path: str
    content: str
    issue_description: str
    expected_failure_pattern: str  # 예상 실패 패턴 (regex)

    def should_fail(self) -> bool:
        """스크립트가 실패해야 하는가 (버그 재현)"""
        return True


@dataclass(frozen=True)
class ReproductionResult:
    """재현 결과 (Immutable Value Object)"""

    status: ReproductionStatus
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float

    def is_bug_reproduced(self) -> bool:
        """버그가 재현되었는가"""
        return self.status == ReproductionStatus.FAIL_CONFIRMED


@dataclass(frozen=True)
class ProcessInfo:
    """프로세스 정보 (Immutable Value Object)"""

    pid: int
    name: str
    status: ProcessStatus
    ports: tuple[int, ...]
    cpu_percent: float
    memory_mb: float

    def is_zombie(self) -> bool:
        return self.status == ProcessStatus.ZOMBIE

    def should_kill(self) -> bool:
        """강제 종료 대상인가"""
        return self.is_zombie() or self.cpu_percent > 90


@dataclass(frozen=True)
class GraphNode:
    """Graph RAG 노드 (Immutable Value Object)"""

    node_id: str
    content: str
    node_type: str  # function, class, module
    pagerank_score: float
    call_depth: int

    def should_include_body(self) -> bool:
        """본문을 포함해야 하는가 (PageRank 기반)"""
        # Top 20% 노드는 본문 포함, 나머지는 시그니처만
        return self.pagerank_score > 0.8 or self.call_depth <= 2


@dataclass(frozen=True)
class PrunedContext:
    """토큰 최적화된 컨텍스트 (Immutable Value Object)"""

    full_nodes: tuple[GraphNode, ...]  # 본문 포함
    signature_only_nodes: tuple[GraphNode, ...]  # 시그니처만
    total_tokens: int
    compression_ratio: float

    def is_within_budget(self, max_tokens: int) -> bool:
        return self.total_tokens <= max_tokens


# ============================================================================
# Ports (Interfaces) - Dependency Inversion Principle
# ============================================================================


class IFuzzyPatcher(Protocol):
    """Smart Fuzzy Patcher Port

    책임:
    - git apply 시도
    - 실패 시 fuzzy matching fallback
    - 앵커 포인트 탐색
    """

    async def apply_patch(
        self,
        file_path: str,
        diff: str,
        fallback_to_fuzzy: bool = True,
    ) -> PatchResult:
        """패치 적용 (git apply 실패 시 fuzzy matching)"""
        ...

    async def find_anchors(
        self,
        file_content: str,
        target_block: str,
    ) -> list[DiffAnchor]:
        """변경 대상 블록의 앵커 포인트 탐색"""
        ...

    async def fuzzy_match(
        self,
        anchor: DiffAnchor,
        file_content: str,
        threshold: float = 0.8,
    ) -> int | None:
        """Fuzzy matching으로 앵커 위치 찾기"""
        ...


class IReproductionEngine(Protocol):
    """Reproduction-First Strategy Port

    TDD 사이클의 핵심:
    1. 버그 재현 스크립트 생성
    2. 실패 확인 (버그 존재 증명)
    3. 수정 후 성공 확인
    """

    async def generate_reproduction_script(
        self,
        issue_description: str,
        context_files: list[str],
        tech_stack: dict[str, str],
    ) -> ReproductionScript:
        """버그 재현 스크립트 생성"""
        ...

    async def verify_failure(
        self,
        script: ReproductionScript,
    ) -> ReproductionResult:
        """스크립트 실행 및 실패 확인"""
        ...

    async def verify_fix(
        self,
        script: ReproductionScript,
        after_changes: bool = True,
    ) -> ReproductionResult:
        """수정 후 스크립트 성공 확인"""
        ...


class IProcessManager(Protocol):
    """Sandbox Process Manager Port

    Zombie Process Killer:
    - 샌드박스 프로세스 모니터링
    - 좀비 프로세스 정리
    - 포트 정리
    """

    async def scan_processes(
        self,
        sandbox_id: str,
    ) -> list[ProcessInfo]:
        """샌드박스 내 프로세스 스캔"""
        ...

    async def kill_zombies(
        self,
        sandbox_id: str,
        force: bool = False,
    ) -> list[int]:
        """좀비 프로세스 강제 종료"""
        ...

    async def cleanup_ports(
        self,
        sandbox_id: str,
        port_range: tuple[int, int] = (8000, 9000),
    ) -> list[int]:
        """점유된 포트 정리"""
        ...


class IGraphPruner(Protocol):
    """Graph RAG PageRank Pruner Port

    토큰 예산 내에서 최적의 컨텍스트 선택:
    - PageRank로 중요도 계산
    - 상위 노드는 본문 포함
    - 나머지는 시그니처만
    """

    async def calculate_pagerank(
        self,
        nodes: list[GraphNode],
        edges: list[tuple[str, str]],
        damping: float = 0.85,
    ) -> dict[str, float]:
        """PageRank 계산"""
        ...

    async def prune_context(
        self,
        nodes: list[GraphNode],
        max_tokens: int = 8000,
        top_k_full: int = 20,
    ) -> PrunedContext:
        """토큰 예산 내에서 컨텍스트 최적화"""
        ...

    async def estimate_tokens(
        self,
        content: str,
    ) -> int:
        """토큰 수 추정"""
        ...


class ICascadeOrchestrator(Protocol):
    """CASCADE 전체 오케스트레이션 Port

    Autonomous Mode의 핵심 컨트롤러:
    1. Localization (SBFL)
    2. Reproduction Script 생성
    3. Static Gate (Ruff + Pyright)
    4. Patch + Verify
    5. Impact Test Selection
    6. Patch Minimization
    """

    async def execute_tdd_cycle(
        self,
        issue_description: str,
        context_files: list[str],
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """TDD 사이클 실행 (Reproduction-First)"""
        ...

    async def optimize_context(
        self,
        repo_path: str,
        query: str,
        max_tokens: int = 8000,
    ) -> PrunedContext:
        """Graph RAG 기반 컨텍스트 최적화"""
        ...
