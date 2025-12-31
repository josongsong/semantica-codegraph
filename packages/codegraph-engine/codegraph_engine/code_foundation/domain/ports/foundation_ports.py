"""
Code Foundation Domain Ports

코드 분석 파이프라인의 포트 인터페이스

Hexagonal Architecture:
- Domain Layer defines Ports (interfaces)
- Infrastructure Layer implements Adapters
- Domain depends on Ports (abstractions), not concrete implementations
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ..models import ASTDocument, Chunk, IRDocument, Language
from ..semantic_ir.mode import SemanticIrBuildMode

# GraphDocument은 infrastructure에 있음 (TYPE_CHECKING으로만 사용)
if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
else:
    GraphDocument = Any  # Runtime fallback

if TYPE_CHECKING:
    from ..query.results import PathResult
    from ..taint.atoms import AtomSpec
    from ..taint.compiled_policy import CompiledPolicy
    from ..taint.control import ControlConfig
    from ..taint.models import DetectedAtoms
    from ..taint.policy import Policy


class ParserPort(Protocol):
    """AST 파서 포트"""

    def parse_file(self, file_path: Path, language: Language) -> ASTDocument:
        """파일을 파싱하여 AST 생성"""
        ...

    def parse_code(self, code: str, language: Language) -> ASTDocument:
        """코드를 파싱하여 AST 생성"""
        ...


class IRGeneratorPort(Protocol):
    """IR 생성기 포트"""

    def generate(self, ast_doc: ASTDocument) -> IRDocument:
        """AST로부터 IR 생성"""
        ...


class GraphBuilderPort(Protocol):
    """그래프 빌더 포트"""

    def build(self, ir_doc: IRDocument) -> GraphDocument:
        """IR로부터 그래프 생성"""
        ...


class ChunkerPort(Protocol):
    """청커 포트"""

    def chunk(self, ir_doc: IRDocument, source_code: str) -> list[Chunk]:
        """IR로부터 청크 생성"""
        ...


class ChunkStorePort(Protocol):
    """청크 저장소 포트"""

    async def save_chunks(self, chunks: list[Chunk], repo_id: str) -> None:
        """청크 저장"""
        ...

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """청크 조회"""
        ...

    async def get_chunks_by_file(self, file_path: str, repo_id: str) -> list[Chunk]:
        """파일의 모든 청크 조회"""
        ...

    async def delete_chunks(self, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        ...


# ============================================================
# Taint Analysis Ports
# ============================================================


class AtomRepositoryPort(Protocol):
    """
    Port for loading atom specifications.

    Implemented by YAMLAtomRepository (infrastructure).
    """

    def load_atoms(self, path: str | None = None) -> list["AtomSpec"]:
        """
        Load atom specifications.

        Args:
            path: Optional path to atom definitions

        Returns:
            List of atom specifications
        """
        ...


class PolicyRepositoryPort(Protocol):
    """
    Port for loading policy definitions.

    Implemented by YAMLPolicyRepository (infrastructure).
    """

    def load_policies(self, path: str | None = None) -> list["Policy"]:
        """
        Load policy definitions.

        Args:
            path: Optional path to policy definitions

        Returns:
            List of policies
        """
        ...


class ControlParserPort(Protocol):
    """
    Port for parsing control configuration.

    Implemented by TOMLControlParser (infrastructure).
    """

    def parse(self, path: str) -> "ControlConfig":
        """
        Parse control configuration file.

        Args:
            path: Path to control config (TOML)

        Returns:
            ControlConfig instance

        Raises:
            FileNotFoundError: If path does not exist
            ValueError: If TOML is invalid
        """
        ...

    def parse_or_default(self, path: "Path") -> "ControlConfig":
        """
        Parse control configuration or return default if not found.

        Args:
            path: Path to control config (TOML)

        Returns:
            ControlConfig instance (default if file not found)

        Note:
            Does not raise FileNotFoundError - returns default config instead.
        """
        ...


class AtomMatcherPort(Protocol):
    """
    Port for type-aware atom matching.

    Implemented by TypeAwareAtomMatcher (infrastructure).

    Thread-Safety: Implementation must be thread-safe for read operations.
    Performance: O(N * M) where N = expressions, M = atoms (optimized to O(N) with indexing).
    """

    def match_all(self, ir_doc: Any, atoms: list["AtomSpec"]) -> "DetectedAtoms":
        """
        Match all atoms in IR document.

        Args:
            ir_doc: IR document to analyze (must have get_all_expressions method)
            atoms: Atom specifications (can be empty list)

        Returns:
            DetectedAtoms with all matches (sources, sinks, sanitizers)

        Raises:
            ValueError: If ir_doc is None or invalid format
            RuntimeError: If matching fails due to internal error

        Performance:
            - O(N * M) naive, O(N) with atom indexing
            - Memory: O(M) for index + O(K) for results where K = matches

        Thread-Safety:
            - Safe for concurrent calls with different ir_doc
            - Not safe if atoms list is mutated during execution

        Example:
            ```python
            detected = matcher.match_all(ir_document, atom_specs)
            assert detected.count_sources() >= 0
            assert detected.count_sinks() >= 0
            ```
        """
        ...

    def match_call(self, call_expr: Any, ir_doc: Any) -> list[tuple["AtomSpec", Any]]:
        """
        Match a single call expression to atoms.

        Args:
            call_expr: Call expression from IR (Expression with kind=CALL)
            ir_doc: IR document for context

        Returns:
            List of (AtomSpec, MatchResult) tuples

        Raises:
            ValueError: If call_expr is not CALL kind

        Note:
            Lower-level API for matching individual expressions.
            Use match_all() for bulk matching.
        """
        ...


class PolicyCompilerPort(Protocol):
    """
    Port for policy compilation.

    Implemented by PolicyCompiler (infrastructure).
    """

    def compile(self, policy: "Policy", atoms: list["AtomSpec"]) -> "CompiledPolicy":
        """
        Compile policy grammar → Q.DSL.

        Args:
            policy: Policy to compile
            atoms: Available atoms

        Returns:
            Compiled policy with query
        """
        ...


class QueryEnginePort(Protocol):
    """
    Port for query execution.

    Implemented by QueryEngineAdapter (infrastructure).

    Thread-Safety: Implementation should handle concurrent queries safely.
    Performance: O(V + E) for BFS/DFS, may be exponential for all-paths.
    Rate Limiting: Max 10 concurrent queries per client, 100 queries/min.
    """

    def execute_flow_query(
        self,
        compiled_policy: "CompiledPolicy",
        max_paths: int,
        max_depth: int,
        timeout_seconds: float = 60.0,
    ) -> list["PathResult"]:
        """
        Execute compiled flow query.

        Args:
            compiled_policy: Compiled policy with FlowExpr
            max_paths: Max number of paths (must be > 0, recommended < 1000)
            max_depth: Max traversal depth (must be > 0, recommended < 100)
            timeout_seconds: Max execution time in seconds (default: 60.0)

        Returns:
            List of paths from sources to sinks (may be empty)
            Paths are sorted by confidence (highest first)

        Raises:
            ValueError: If max_paths <= 0 or max_depth <= 0 or timeout <= 0
            ValueError: If compiled_policy is invalid or None
            ValueError: If max_paths > 10000 or max_depth > 100 (safety limits)
            RuntimeError: If query execution fails (graph corruption)
            TimeoutError: If query exceeds timeout_seconds

        Performance:
            - Small graph (< 1K nodes): < 100ms
            - Medium graph (< 10K nodes): < 1s
            - Large graph (< 100K nodes): < 10s
            - Best case: O(V + E) single path BFS
            - Worst case: O(V^max_depth) all paths enumeration
            - Memory: O(max_paths * max_depth) for results

        Constraints:
            - max_paths: [1, 10000] hard limit
            - max_depth: [1, 100] hard limit
            - timeout_seconds: [0.1, 300.0] recommended range

        Thread-Safety:
            - Safe for concurrent reads on same graph
            - Not safe if graph is being modified
            - Each thread gets independent PathResult objects

        Rate Limiting:
            - Max 10 concurrent queries per client
            - Max 100 queries per minute per client
            - Implementation should enforce via decorator/middleware

        Observability:
            - Logs: query execution time, paths found, nodes visited
            - Metrics: execution_time_ms, paths_found, timeout_occurred
            - Trace: For debugging complex queries

        Example:
            ```python
            paths = engine.execute_flow_query(
                compiled_policy=policy,
                max_paths=100,
                max_depth=20,
                timeout_seconds=30.0
            )
            assert all(len(p.nodes) <= max_depth for p in paths)
            assert len(paths) <= max_paths
            ```
        """
        ...


class ConstraintValidatorPort(Protocol):
    """
    Port for constraint validation.

    Implemented by ConstraintValidator (infrastructure).

    Thread-Safety: Must be thread-safe (stateless validation).
    Performance: O(N * C) where N = path length, C = constraint count.
    """

    def validate_path(self, path: "PathResult", constraints: dict) -> bool:
        """
        Validate path against constraints.

        Args:
            path: Path to validate (must not be None)
            constraints: Constraint specifications (can be empty dict)
                Valid keys: max_length, min_confidence, require_sanitizer
                Example: {"max_length": 50, "min_confidence": 0.7}

        Returns:
            True if path satisfies ALL constraints, False otherwise
            Returns True if constraints dict is empty (no constraints)

        Raises:
            ValueError: If path is None
            KeyError: If constraint key is unknown/unsupported
            TypeError: If constraint value has wrong type

        Performance:
            - O(1) for simple constraints (max_length, min_confidence)
            - O(N) for path-based constraints where N = path length
            - Should complete in < 1ms per path

        Validation Rules:
            - max_length: path.length <= value
            - min_confidence: path.confidence >= value
            - require_sanitizer: path must contain sanitizer node
            - All constraints must pass (AND logic)

        Thread-Safety:
            - Must be stateless and thread-safe
            - No mutation of path or constraints

        Example:
            ```python
            valid = validator.validate_path(
                path=path_result,
                constraints={
                    "max_length": 50,
                    "min_confidence": 0.8
                }
            )
            assert isinstance(valid, bool)
            ```

        Note:
            Unknown constraint keys should raise KeyError, not silently ignore.
            This prevents typos in constraint specifications.
        """
        ...

    # =========================================================================
    # RFC-030 Phase 2/3: Optional SCCP + Dominator Integration
    # =========================================================================

    def set_sccp_result(self, sccp_result: Any) -> None:
        """
        RFC-030: Set SCCP result for constant evaluation.

        Args:
            sccp_result: Result from ConstantPropagationAnalyzer
        """
        ...

    def set_dominator_tree(self, dom_tree: Any) -> None:
        """
        RFC-030: Set Dominator tree for guard validation.

        Args:
            dom_tree: Dominator tree from SSA construction
        """
        ...

    def set_ir_document(self, ir_doc: Any) -> None:
        """
        RFC-030: Set IR document for context.

        Args:
            ir_doc: IR document being analyzed
        """
        ...

    def is_guard_protected(self, sink_block_id: str, variable: str) -> bool:
        """
        RFC-030: Check if variable is protected by a guard at sink location.

        Uses Dominator analysis to validate that a guard check dominates
        the sink block, ensuring all paths to sink pass through the guard.

        Args:
            sink_block_id: CFG block ID of the sink
            variable: Variable name to check for guard protection

        Returns:
            True if variable is protected by a valid guard
            False if no guard or guard doesn't dominate sink

        Example:
            ```python
            # Code pattern that creates valid guard:
            # if not is_valid(user_input):
            #     return  # exit on fail
            # sink(user_input)  # guarded

            is_protected = validator.is_guard_protected(
                sink_block_id="block_5",
                variable="user_input"
            )
            ```
        """
        ...


# =============================================================================
# Cross-Layer Interface Contracts (추가)
# =============================================================================
# 아래 포트들은 레이어 간 인터페이스를 명확히 정의합니다.
# 자세한 정의는 각 전문 ports 파일 참조:
# - semantic_ir_ports.py: SemanticIRBuilder, ExpressionBuilder, DfgBuilder
# - expression_ports.py: Expression.attrs 타입 정의
# - taint_ports.py: AtomIndexer, TypeAwareAtomMatcher, TaintAnalysisService


class LayeredIRBuilderPort(Protocol):
    """
    LayeredIRBuilder 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py

    전체 IR 생성 파이프라인을 조율합니다:
    1. 파일 파싱 → ASTDocument
    2. IR 생성 → IRDocument (nodes, edges)
    3. Semantic IR 추가 → types, signatures, CFG, DFG, expressions
    4. 인덱스 빌드 (🔥 자동)

    사용 예:
        builder = LayeredIRBuilder(project_root=Path("."))
        ir_docs, global_ctx, *_ = await builder.build_full(files=[path])
        # ir_docs의 인덱스는 자동으로 빌드됨
    """

    async def build_full(
        self,
        files: list[Any],
        enable_semantic_ir: bool = True,
        semantic_mode: SemanticIrBuildMode = SemanticIrBuildMode.FULL,
        enable_advanced_analysis: bool = False,
        enable_lsp_enrichment: bool = True,
        enable_cross_file: bool = True,
        enable_retrieval_index: bool = True,
        collect_diagnostics: bool = True,
        analyze_packages: bool = True,
    ) -> tuple[dict[str, Any], Any, Any, Any, Any]:
        """
        전체 IR 빌드.

        Args:
            files: 분석 대상 파일 경로 리스트
            enable_semantic_ir: Semantic IR 생성 여부
            semantic_mode: SemanticIrBuildMode (QUICK, PR, FULL)
            enable_advanced_analysis: 고급 분석 (interprocedural) 여부
            enable_lsp_enrichment: Pyright/LSP 타입 정보 추가 여부
            enable_cross_file: 파일 간 참조 분석 여부
            enable_retrieval_index: 검색 인덱스 생성 여부
            collect_diagnostics: 진단 정보 수집 여부
            analyze_packages: 패키지 의존성 분석 여부

        Returns:
            (
                dict[str, IRDocument],  # 파일별 IR 문서
                GlobalContext,           # 전역 심볼 테이블
                RetrievalOptimizedIndex, # 검색 인덱스
                DiagnosticIndex | None,  # 진단 정보
                PackageIndex | None      # 패키지 의존성
            )

        Contract:
            - 반환된 각 IRDocument는 build_indexes() 완료 상태여야 함
            - enable_lsp_enrichment=True 시, Expression.attrs["receiver_type"] 설정됨
            - enable_semantic_ir=True 시, expressions, dfg_snapshot 포함

        Post-conditions:
            - 모든 IRDocument.ensure_indexes() 호출 불필요 (이미 완료)
            - QueryEngine 생성 시 즉시 사용 가능
        """
        ...


class GlobalContextPort(Protocol):
    """
    GlobalContext 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/ir/global_context.py

    파일 간 심볼 테이블을 관리합니다.
    """

    def get_symbol(self, fqn: str) -> Any | None:
        """FQN으로 심볼 조회."""
        ...

    def get_all_symbols(self) -> dict[str, Any]:
        """모든 심볼 반환."""
        ...

    def add_symbol(self, fqn: str, symbol: Any) -> None:
        """심볼 추가."""
        ...
