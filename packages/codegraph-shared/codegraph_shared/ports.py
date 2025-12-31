"""
Foundation Layer Ports

Foundation 계층의 인덱스 포트 인터페이스
각 인덱스 타입(Lexical, Vector, Symbol 등)의 추상 인터페이스 정의

Note:
- API Layer 포트는 src/api/ports.py 참조
- 도메인별 포트는 각 context의 domain/ports.py 참조
"""

from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable

# ============================================================
# Common Types (shared across layers)
# ============================================================
# NOTE: IndexDocument, SearchHit는 multi_index.infrastructure.common.documents에서
# 정의된 Pydantic 모델을 사용합니다. 아래는 하위 호환성을 위한 re-export입니다.

from codegraph_engine.multi_index.infrastructure.common.documents import (
    IndexDocument,
    SearchHit,
)

# ============================================================
# Foundation Layer Ports (Index Layer)
# ============================================================


@runtime_checkable
class LexicalIndexPort(Protocol):
    """
    Lexical Search Port (Tantivy-based).

    Provides file-based text/identifier/regex search.
    """

    @abstractmethod
    async def reindex_repo(self, repo_id: str, snapshot_id: str) -> None:
        """
        Full repository reindex.

        Args:
            repo_id: Repository identifier
            snapshot_id: Git commit hash or snapshot identifier
        """
        ...

    @abstractmethod
    async def reindex_paths(self, repo_id: str, snapshot_id: str, paths: list[str]) -> None:
        """
        Partial reindex for specific files/paths.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            paths: List of file paths to reindex
        """
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Search with lexical query.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query (text/regex/identifier)
            limit: Maximum results

        Returns:
            List of SearchHit with source="lexical"
        """
        ...

    @abstractmethod
    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Delete repository index"""
        ...


@runtime_checkable
class VectorIndexPort(Protocol):
    """
    Vector Search Port (Qdrant-based).

    Provides semantic/embedding-based search.
    """

    @abstractmethod
    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Full index creation.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances
        """
        ...

    @abstractmethod
    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Incremental upsert.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        ...

    @abstractmethod
    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete documents by ID.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        ...

    @abstractmethod
    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
        chunk_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        """
        Semantic search.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            limit: Maximum results
            chunk_ids: Optional list of chunk IDs to filter (DB-level filtering)

        Returns:
            List of SearchHit with source="vector"
        """
        ...


@runtime_checkable
class SymbolIndexPort(Protocol):
    """
    Symbol Search Port (Kuzu Graph-based).

    Provides go-to-definition, find-references, call graph queries.
    """

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Symbol search (go-to-def, find-refs).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Symbol name or pattern
            limit: Maximum results

        Returns:
            List of SearchHit with source="symbol"
        """
        ...

    @abstractmethod
    async def index_graph(self, repo_id: str, snapshot_id: str, graph_doc: Any) -> None:
        """
        Index graph document.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            graph_doc: GraphDocument instance
        """
        ...

    @abstractmethod
    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get symbols that call this symbol (returns dict for flexibility)"""
        ...

    @abstractmethod
    async def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get symbols called by this symbol (returns dict for flexibility)"""
        ...

    @abstractmethod
    async def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """
        Get node by ID.

        Args:
            node_id: Node/symbol identifier

        Returns:
            Node data as dict or None if not found
        """
        ...

    @abstractmethod
    async def get_references(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get all nodes that reference this symbol.

        Args:
            symbol_id: Symbol identifier

        Returns:
            List of nodes that reference this symbol
        """
        ...


@runtime_checkable
class FuzzyIndexPort(Protocol):
    """
    Fuzzy Search Port (PostgreSQL pg_trgm-based).

    Handles typos and incomplete queries.
    """

    @abstractmethod
    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """Index documents for fuzzy search."""
        ...

    @abstractmethod
    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """Upsert documents for fuzzy search."""
        ...

    @abstractmethod
    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """Delete documents by ID."""
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Fuzzy search for identifiers/symbols.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Partial or misspelled identifier
            limit: Maximum results

        Returns:
            List of SearchHit with source="fuzzy"
        """
        ...


@runtime_checkable
class DomainMetaIndexPort(Protocol):
    """
    Domain Metadata Search Port (README/ADR/Docs).

    Searches documentation and architectural decision records.
    """

    @abstractmethod
    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """Index domain documents (README, ADR, API specs)"""
        ...

    @abstractmethod
    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """Upsert domain documents."""
        ...

    @abstractmethod
    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """Delete documents by ID."""
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Search domain documents.

        Returns:
            List of SearchHit with source="domain"
        """
        ...


@runtime_checkable
class RuntimeIndexPort(Protocol):
    """
    Runtime Trace Index Port (Phase 3).

    Provides hot path and error-based search.
    """

    @abstractmethod
    def index_traces(self, repo_id: str, snapshot_id: str, traces: list[dict[str, Any]]) -> None:
        """Index runtime traces from OpenTelemetry"""
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Search based on runtime metrics.

        Returns:
            List of SearchHit with source="runtime"
        """
        ...


@runtime_checkable
class RepoMapPort(Protocol):
    """
    RepoMap Query Port.

    Provides read-only access to RepoMap snapshots for Retriever/Index layers.

    Usage:
        repomap_port = PostgresRepoMapStore(...)
        nodes = repomap_port.get_topk_by_importance(repo_id, snapshot_id, k=100)
        subtree = repomap_port.get_subtree(node_id)
    """

    @abstractmethod
    def get_snapshot(self, repo_id: str, snapshot_id: str) -> Any | None:  # RepoMapSnapshot
        """
        Get complete RepoMap snapshot.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/commit identifier

        Returns:
            RepoMapSnapshot or None if not found
        """
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> Any | None:  # RepoMapNode
        """
        Get single RepoMap node by ID.

        Args:
            node_id: RepoMap node ID

        Returns:
            RepoMapNode or None if not found
        """
        ...

    @abstractmethod
    def get_topk_by_importance(self, repo_id: str, snapshot_id: str, k: int = 100) -> list[Any]:  # list[RepoMapNode]
        """
        Get top K nodes sorted by importance score.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            k: Number of top nodes to return

        Returns:
            List of RepoMapNode sorted by importance (descending)
        """
        ...

    @abstractmethod
    def get_subtree(self, node_id: str) -> list[Any]:  # list[RepoMapNode]
        """
        Get node and all descendants.

        Args:
            node_id: RepoMap node ID (format: repomap:{repo_id}:{snapshot_id}:{kind}:{path})
                    Contains repo_id and snapshot_id embedded in the ID.

        Returns:
            List of RepoMapNode (root + all children recursively)
        """
        ...

    @abstractmethod
    def get_nodes_by_path(self, repo_id: str, snapshot_id: str, path: str) -> list[Any]:  # list[RepoMapNode]
        """
        Get all nodes matching a file/directory path.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            path: File or directory path

        Returns:
            List of RepoMapNode matching the path
        """
        ...

    @abstractmethod
    def get_nodes_by_fqn(self, repo_id: str, snapshot_id: str, fqn: str) -> list[Any]:  # list[RepoMapNode]
        """
        Get all nodes matching a fully qualified name.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            fqn: Fully qualified name

        Returns:
            List of RepoMapNode matching the FQN
        """
        ...


# ============================================================
# Agent Execution Layer Ports (v7 SOTA Agent)
# ============================================================
# Agent 실행을 위한 핵심 포트
# Port/Adapter 패턴으로 OSS vendor lock-in 방지


@runtime_checkable
class IWorkflowEngine(Protocol):
    """
    Workflow Orchestration Port.

    LangGraph, Temporal, Prefect 등 workflow engine 추상화.
    Business logic은 WorkflowStep에 있고, Engine은 orchestration만 담당.
    """

    @abstractmethod
    async def execute(
        self,
        steps: list[Any],
        initial_state: Any,
        config: dict[str, Any] | None = None,
    ) -> Any:
        """
        Workflow 실행.

        Args:
            steps: WorkflowStep 리스트 (Analyze→Plan→Generate→Critic→Test→Heal)
            initial_state: 초기 상태
            config: Engine별 설정 (max_iterations, early_exit 조건 등)

        Returns:
            WorkflowResult (최종 상태 + 메타데이터)
        """
        ...

    @abstractmethod
    def add_step(self, step: Any, name: str) -> None:
        """
        WorkflowStep 등록.

        Args:
            step: WorkflowStep 인스턴스
            name: Step 이름 (node ID로 사용)
        """
        ...


@runtime_checkable
class ISandboxExecutor(Protocol):
    """
    Sandbox 실행 Port.

    E2B, Firecracker, Docker, K8s 등 sandbox 실행 환경 추상화.
    보안 격리 + 리소스 제한.
    """

    @abstractmethod
    async def create_sandbox(self, config: dict[str, Any]) -> Any:
        """
        Sandbox 생성.

        Args:
            config: Sandbox 설정
                - template: "python" | "node" | "base"
                - timeout: 초 단위 타임아웃
                - env_vars: 환경 변수 (secret 포함)
                - resource_limits: CPU/Memory/Disk 제한

        Returns:
            SandboxHandle (sandbox ID + 메타데이터)
        """
        ...

    @abstractmethod
    async def execute_code(self, handle: Any, code: str, language: str = "python") -> Any:
        """
        코드 실행.

        Args:
            handle: create_sandbox로 생성한 핸들
            code: 실행할 코드
            language: 언어 ("python" | "node" | "bash")

        Returns:
            ExecutionResult (stdout, stderr, exit_code, execution_time)
        """
        ...

    @abstractmethod
    async def destroy_sandbox(self, handle: Any) -> None:
        """Sandbox 정리 (리소스 해제)"""
        ...


@runtime_checkable
class ILLMProvider(Protocol):
    """
    LLM 호출 Port.

    LiteLLM, LangChain, 자체 구현 등 LLM provider 추상화.
    Multi-model routing + fallback + cost tracking.
    """

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]], model_tier: str = "medium", **kwargs: Any) -> str:
        """
        텍스트 완성.

        Args:
            messages: OpenAI format 메시지 리스트
            model_tier: "fast" | "medium" | "strong"
                - fast: Haiku, GPT-3.5 등 (latency 우선)
                - medium: Sonnet, GPT-4o 등 (균형)
                - strong: Opus, o1 등 (품질 우선)
            **kwargs: temperature, max_tokens 등

        Returns:
            완성된 텍스트
        """
        ...

    @abstractmethod
    async def complete_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: type,  # Pydantic BaseModel
        model_tier: str = "medium",
        **kwargs: Any,
    ) -> Any:
        """
        구조화된 출력 (Pydantic schema 기반).

        Args:
            messages: 메시지 리스트
            schema: Pydantic BaseModel 클래스
            model_tier: 모델 등급

        Returns:
            schema 인스턴스 (파싱 보장)
        """
        ...

    @abstractmethod
    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """
        텍스트 임베딩 생성.

        Args:
            text: 임베딩할 텍스트
            model: 임베딩 모델

        Returns:
            임베딩 벡터
        """
        ...


@runtime_checkable
class IGuardrailValidator(Protocol):
    """
    Guardrail 검증 Port.

    Guardrails AI, Pydantic Validator, 자체 규칙 등 검증 엔진 추상화.
    정책 계층: global → org → repo → local
    """

    @abstractmethod
    async def validate(
        self,
        data: Any,  # CodeChange, CodeChanges 등
        policies: list[dict[str, Any]],
        level: str = "repo",  # "global" | "org" | "repo" | "local"
    ) -> Any:
        """
        데이터 검증.

        Args:
            data: 검증할 데이터 (CodeChange, 생성된 코드 등)
            policies: 적용할 정책 리스트
                - DetectSecrets: API key, token 유출 방지
                - CheckLOCLimit: LOC 제한
                - CheckFileLimit: 파일 개수 제한
                - DetectPII: PII 유출 방지
            level: 정책 적용 레벨

        Returns:
            ValidationResult (valid, errors, warnings)
        """
        ...


@runtime_checkable
class IVCSApplier(Protocol):
    """
    VCS 적용 Port.

    GitPython, libgit2, go-git 등 VCS 라이브러리 추상화.
    Branch 생성 + Commit + PR + Conflict resolution.
    """

    @abstractmethod
    async def apply_changes(
        self,
        changes: list[Any],
        branch_name: str,
        commit_message: str | None = None,  # CodeChange 리스트
    ) -> Any:
        """
        변경사항 적용 (branch 생성 + commit).

        Args:
            changes: CodeChange 리스트
            branch_name: 생성할 브랜치 이름
            commit_message: 커밋 메시지 (None이면 자동 생성)

        Returns:
            CommitResult (commit_sha, branch_name, changed_files)
        """
        ...

    @abstractmethod
    async def create_pr(self, branch_name: str, title: str, body: str, base_branch: str = "main") -> Any:
        """
        PR 생성.

        Args:
            branch_name: PR 소스 브랜치
            title: PR 제목
            body: PR 본문
            base_branch: PR 타겟 브랜치

        Returns:
            PRResult (pr_number, pr_url)
        """
        ...

    @abstractmethod
    async def resolve_conflict(
        self,
        conflict: Any,
        strategy: str = "llm",  # "llm" | "ours" | "theirs"
    ) -> Any:
        """
        Merge conflict 해결.

        Args:
            conflict: MergeConflict 정보
            strategy: 해결 전략

        Returns:
            ConflictResolution (resolved, resolution_code)
        """
        ...


@runtime_checkable
class IMetricsCollector(Protocol):
    """
    메트릭 수집 Port.

    Prometheus, DataDog, CloudWatch 등 메트릭 백엔드 추상화.
    Counter, Gauge, Histogram 지원.
    """

    @abstractmethod
    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Counter 메트릭 기록 (단조 증가).

        Args:
            name: 메트릭 이름 (예: "requests_total")
            value: 증가값 (기본 1.0)
            labels: 라벨 (예: {"status": "200"})
        """
        ...

    @abstractmethod
    def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Gauge 메트릭 기록 (현재 값).

        Args:
            name: 메트릭 이름 (예: "active_agents")
            value: 현재 값
            labels: 라벨
        """
        ...

    @abstractmethod
    def record_histogram(
        self,
        name: str,
        value: float,
    ) -> None:
        """
        Histogram 메트릭 기록 (분포).

        Args:
            name: 메트릭 이름 (예: "latency_ms")
            value: 관측값
        """
        ...

    @abstractmethod
    def get_all_metrics(self) -> dict[str, Any]:
        """모든 메트릭 반환 (디버깅/익스포트용)"""
        ...


@runtime_checkable
class IHealthChecker(Protocol):
    """
    Health Check Port.

    시스템 컴포넌트 상태 확인 추상화.
    DB, Redis, LLM API 등 헬스 체크.
    """

    @abstractmethod
    async def check_health(self) -> dict[str, bool]:
        """
        전체 시스템 헬스 체크.

        Returns:
            {"postgres": True, "redis": True, "llm_api": False}
        """
        ...

    @abstractmethod
    async def check_component(self, component: str) -> bool:
        """
        특정 컴포넌트 헬스 체크.

        Args:
            component: "postgres" | "redis" | "qdrant" | "memgraph" | "llm_api"

        Returns:
            True if healthy
        """
        ...


@runtime_checkable
class IVisualValidator(Protocol):
    """
    Visual 검증 Port.

    Playwright, Selenium, Puppeteer 등 브라우저 자동화 추상화.
    Screenshot + Vision Model 기반 UI 검증.
    """

    @abstractmethod
    async def capture_screenshot(
        self, url: str, selector: str | None = None, viewport: dict[str, int] | None = None
    ) -> Any:
        """
        스크린샷 캡처.

        Args:
            url: 캡처할 URL
            selector: CSS selector (특정 요소만 캡처)
            viewport: {"width": 1920, "height": 1080}

        Returns:
            Screenshot (bytes, metadata)
        """
        ...

    @abstractmethod
    async def compare_screenshots(self, before: Any, after: Any, use_vision_model: bool = True) -> Any:
        """
        스크린샷 비교.

        Args:
            before: 변경 전 스크린샷
            after: 변경 후 스크린샷
            use_vision_model: Vision Model (GPT-4o) 사용 여부

        Returns:
            VisualDiff (has_difference, diff_description, diff_score)
        """
        ...


# ============================================================
# API/Server Layer Ports
# ============================================================
# Note: API Layer 포트는 apps/api/shared/ports.py에 정의되어 있습니다.
# (ContextPort, EnginePort, GraphPort, IndexingPort, LLMPort, SearchPort)
# 필요한 경우 해당 파일에서 직접 import하세요.

# ============================================================================
# Agent Service Protocols (v7)
# ============================================================================


@runtime_checkable
class IAnalyzeService(Protocol):
    """
    Task 분석 서비스 인터페이스.

    Task의 복잡도, 영향 범위 등을 분석합니다.
    """

    @abstractmethod
    async def analyze_task(self, task: Any) -> dict[str, Any]:
        """
        Task를 분석합니다.

        Args:
            task: 분석할 Task

        Returns:
            분석 결과 (summary, impacted_files, complexity_score 등)
        """
        ...


@runtime_checkable
class IPlanService(Protocol):
    """
    수정 계획 생성 서비스 인터페이스.

    Task와 분석 결과를 바탕으로 수정 계획을 생성합니다.
    """

    @abstractmethod
    async def plan_changes(self, task: Any, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        수정 계획을 생성합니다.

        Args:
            task: 대상 Task
            analysis: 분석 결과

        Returns:
            수정 계획 (steps, files, approach 등)
        """
        ...


@runtime_checkable
class IGenerateService(Protocol):
    """
    코드 생성 서비스 인터페이스.

    계획에 따라 실제 코드 변경을 생성합니다.
    """

    @abstractmethod
    async def generate_code(self, task: Any, plan: dict[str, Any] | None) -> list[Any]:
        """
        코드 변경을 생성합니다.

        Args:
            task: 대상 Task
            plan: 수정 계획

        Returns:
            CodeChange 리스트
        """
        ...


@runtime_checkable
class ICriticService(Protocol):
    """
    코드 검토 서비스 인터페이스.

    생성된 코드를 검토하여 문제점을 찾습니다.
    """

    @abstractmethod
    async def review_code(self, changes: list[Any]) -> list[str]:
        """
        코드를 검토합니다.

        Args:
            changes: 검토할 코드 변경

        Returns:
            발견된 문제 리스트 (빈 리스트면 승인)
        """
        ...


@runtime_checkable
class ITestService(Protocol):
    """
    테스트 실행 서비스 인터페이스.

    코드 변경에 대한 테스트를 실행합니다.
    """

    @abstractmethod
    async def run_tests(self, changes: list[Any]) -> list[Any]:
        """
        테스트를 실행합니다.

        Args:
            changes: 테스트할 코드 변경

        Returns:
            ExecutionResult 리스트
        """
        ...


@runtime_checkable
class IHealService(Protocol):
    """
    자동 수정 서비스 인터페이스.

    테스트 실패나 문제점을 자동으로 수정합니다.
    """

    @abstractmethod
    async def suggest_fix(self, errors: list[str], changes: list[Any]) -> list[Any]:
        """
        수정 제안을 생성합니다.

        Args:
            errors: 발견된 에러
            changes: 원본 코드 변경

        Returns:
            수정된 CodeChange 리스트
        """
        ...


# ============================================================================
# Router & Retrieval Ports
# ============================================================================


@runtime_checkable
class IQueryAnalyzer(Protocol):
    """
    Query 복잡도 분석 인터페이스.

    Query의 특성을 분석하여 적절한 검색 전략 결정을 지원합니다.
    """

    @abstractmethod
    def analyze(self, query: str) -> Any:
        """
        Query를 분석합니다.

        Args:
            query: 검색 쿼리

        Returns:
            QueryComplexity 객체 (complexity_level, specificity_score 등)
        """
        ...


@runtime_checkable
class ITopKSelector(Protocol):
    """
    동적 Top-K 선택 인터페이스.

    Query 복잡도와 intent에 따라 최적의 k 값을 선택합니다.
    """

    @abstractmethod
    def select_k(self, query: str, intent: str | None = None) -> int:
        """
        Query에 대한 최적 k 값을 선택합니다.

        Args:
            query: 검색 쿼리
            intent: Query intent (symbol/flow/concept/code 등)

        Returns:
            적절한 k 값
        """
        ...


@runtime_checkable
class IBudgetSelector(Protocol):
    """
    Budget-aware Top-K 선택 인터페이스.

    Latency budget을 고려한 k 값 선택을 지원합니다.
    """

    @abstractmethod
    def select_with_budget(self, query: str, intent: str | None = None) -> int:
        """
        Budget을 고려하여 k 값을 선택합니다.

        Args:
            query: 검색 쿼리
            intent: Query intent

        Returns:
            Budget 내에서 최적의 k 값
        """
        ...
