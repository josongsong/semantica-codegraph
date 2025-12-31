"""
Semantic IR Ports

SemanticIRBuilder 및 관련 컴포넌트의 인터페이스 정의.

이 파일은 IR 생성 파이프라인의 핵심 계약을 정의합니다:
1. SemanticIRBuilder의 입출력 인터페이스
2. ExpressionBuilder의 계약
3. DfgBuilder의 계약
4. 레이어 간 데이터 흐름 명시

Hexagonal Architecture:
- Domain Layer: 이 파일 (Port/Protocol 정의)
- Infrastructure Layer: 실제 구현체 (SemanticBuilder, ExpressionBuilder 등)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock, BasicFlowGraph
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
        ControlFlowBlock,
        ControlFlowEdge,
        ControlFlowGraph,
    )
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.types.models import TypeEntity


# =============================================================================
# SemanticIrSnapshot: SemanticIRBuilder 출력 계약
# =============================================================================


@dataclass
class SemanticIrSnapshotContract:
    """
    SemanticIRBuilder가 반환해야 하는 데이터 구조.

    이 계약은 LayeredIRBuilder가 SemanticBuilder.build_full()의 반환값에서
    기대하는 모든 필드를 명시합니다.

    Usage:
        snapshot = semantic_builder.build_full(ir_doc, source_map, mode="full")
        assert isinstance(snapshot, SemanticIrSnapshotContract)

    필수 필드:
        - types: 타입 엔티티 (클래스, 제네릭 등)
        - signatures: 함수 시그니처
        - cfg_graphs, cfg_blocks, cfg_edges: Control Flow Graph
        - bfg_graphs, bfg_blocks: Basic Flow Graph (DFG 구축용)
        - dfg_snapshot: Data Flow Graph
        - expressions: Expression IR (Taint 분석 핵심)
    """

    # Type information
    types: list["TypeEntity"] = field(default_factory=list)

    # Function signatures
    signatures: list["SignatureEntity"] = field(default_factory=list)

    # Control Flow Graph
    cfg_graphs: list["ControlFlowGraph"] = field(default_factory=list)
    cfg_blocks: list["ControlFlowBlock"] = field(default_factory=list)
    cfg_edges: list["ControlFlowEdge"] = field(default_factory=list)

    # Basic Flow Graph (for DFG construction)
    bfg_graphs: list["BasicFlowGraph"] = field(default_factory=list)
    bfg_blocks: list["BasicFlowBlock"] = field(default_factory=list)

    # Data Flow Graph
    dfg_snapshot: "DfgSnapshot | None" = None

    # Expression IR (🔥 Taint Analysis 핵심)
    expressions: list["Expression"] = field(default_factory=list)

    # Semantic Index (optional)
    semantic_index: Any = None


@runtime_checkable
class SemanticIRBuilderPort(Protocol):
    """
    SemanticIRBuilder 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/semantic_ir/builder.py

    이 포트는 IR 문서에 semantic 정보(타입, CFG, DFG, Expression)를 추가합니다.
    """

    def build_full(
        self,
        ir_doc: "IRDocument",
        source_map: dict[str, tuple[Any, Any]],
        mode: str = "full",
    ) -> SemanticIrSnapshotContract:
        """
        IR 문서에 semantic 정보를 추가.

        Args:
            ir_doc: 기본 IR 문서 (노드, 엣지 포함)
            source_map: {file_path: (SourceFile, AstTree)} 매핑
            mode: "full" | "quick" | "minimal"

        Returns:
            SemanticIrSnapshotContract - 모든 semantic 정보 포함

        Raises:
            ValueError: ir_doc가 None이거나 유효하지 않은 경우
            RuntimeError: 빌드 중 내부 오류 발생

        Contract:
            - 반환된 snapshot.expressions는 비어있지 않아야 함 (mode="full" 시)
            - 각 Expression은 유효한 span을 가져야 함
            - dfg_snapshot은 expressions와 일관성이 있어야 함
        """
        ...


# =============================================================================
# ExpressionBuilder: Expression 생성 계약
# =============================================================================


class ExpressionBuilderConfig(TypedDict, total=False):
    """ExpressionBuilder 설정."""

    external_analyzer: Any  # PyrightExternalAnalyzer or None
    project_root: Path | None
    max_ast_cache_size: int
    enable_type_enrichment: bool  # receiver_type 추가 여부


@runtime_checkable
class ExpressionBuilderPort(Protocol):
    """
    ExpressionBuilder 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/semantic_ir/expression/builder.py

    🔥 핵심 책임:
    1. AST → Expression IR 변환
    2. Pyright로부터 타입 정보 획득
    3. Expression.attrs에 receiver_type, callee_name 등 설정

    이 포트의 출력은 TypeAwareAtomMatcher의 입력이 됩니다.
    """

    def build(
        self,
        ir_doc: "IRDocument",
        bfg_blocks: list["BasicFlowBlock"],
        source_map: dict[str, tuple[Any, Any]],
    ) -> list["Expression"]:
        """
        IR 문서와 BFG로부터 Expression IR 생성.

        Args:
            ir_doc: IR 문서
            bfg_blocks: Basic Flow Graph 블록들
            source_map: {file_path: (SourceFile, AstTree)}

        Returns:
            Expression 리스트

        Contract:
            - 각 Expression.attrs는 ExpressionAttrsContract를 만족해야 함
            - CALL 타입 Expression은 반드시 callee_name을 가져야 함
            - Pyright 활성화 시, receiver_type이 설정되어야 함

        Raises:
            ValueError: ir_doc가 None인 경우
        """
        ...


# =============================================================================
# DfgBuilder: DFG 생성 계약
# =============================================================================


@runtime_checkable
class DfgBuilderPort(Protocol):
    """
    DfgBuilder 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/dfg/builder.py

    책임:
    1. Expression IR → DFG 변환
    2. Variable Entity 생성
    3. Data flow edge 구축
    """

    def build_full(
        self,
        ir_doc: "IRDocument",
        bfg_blocks: list["BasicFlowBlock"],
        expressions: list["Expression"],
    ) -> "DfgSnapshot":
        """
        DFG 스냅샷 생성.

        Args:
            ir_doc: IR 문서
            bfg_blocks: BFG 블록들
            expressions: Expression IR (🔥 reads_vars, defines_var가 채워져 있어야 함)

        Returns:
            DfgSnapshot

        Contract:
            - expressions의 reads_vars, defines_var가 이미 채워져 있어야 함
            - 반환된 DfgSnapshot.variables는 expressions 기반이어야 함
            - DfgSnapshot.edges는 variable 간 data flow를 나타냄

        Pre-condition:
            - Expression.reads_vars: 해당 expression이 읽는 variable IDs
            - Expression.defines_var: 해당 expression이 정의하는 variable ID
        """
        ...


# =============================================================================
# InterproceduralDataFlowBuilder: 함수 간 데이터 흐름 계약
# =============================================================================


@runtime_checkable
class InterproceduralBuilderPort(Protocol):
    """
    InterproceduralDataFlowBuilder 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/ir/interprocedural_builder.py

    책임:
    1. 함수 호출 관계 분석
    2. 파라미터 → 인자 데이터 흐름 연결
    3. k-CFA context 설정
    """

    def build(
        self,
        ir_doc: "IRDocument",
        expressions: list["Expression"],
        dfg_snapshot: "DfgSnapshot",
    ) -> "DfgSnapshot":
        """
        Interprocedural 데이터 흐름 추가.

        Args:
            ir_doc: IR 문서
            expressions: Expression IR (CALL 포함)
            dfg_snapshot: 기존 intraprocedural DFG

        Returns:
            확장된 DfgSnapshot (interprocedural edges 추가)

        Contract:
            - 함수 호출(CALL Expression)마다 callee 해석 시도
            - 해석 성공 시 arg → param data flow edge 추가
            - VariableEntity.context 필드에 k-CFA context 설정
        """
        ...


# =============================================================================
# SourceMap: 소스 코드 매핑 계약
# =============================================================================


class SourceMapEntry(TypedDict):
    """소스 맵 엔트리."""

    source_file: Any  # SourceFile
    ast_tree: Any  # AstTree


SourceMapContract = dict[str, SourceMapEntry]
"""
source_map 계약.

형식: {file_path: {"source_file": SourceFile, "ast_tree": AstTree}}

LayeredIRBuilder에서 생성되어 SemanticBuilder, ExpressionBuilder로 전달됩니다.
"""


# =============================================================================
# TypeInfo Resolution: 타입 정보 해석 계약
# =============================================================================


class TypeInfoContract(TypedDict, total=False):
    """
    TypeInfo 계약.

    Pyright LSP에서 반환되는 타입 정보의 표준 형식.
    """

    symbol_name: str
    file_path: str
    line: int
    column: int
    inferred_type: str | None  # 🔥 "sqlite3.Connection" 등
    declared_type: str | None
    is_builtin: bool
    definition_file: str | None
    definition_line: int | None
    definition_fqn: str | None  # 🔥 Fully Qualified Name


@runtime_checkable
class TypeResolverPort(Protocol):
    """
    타입 해석 인터페이스.

    Pyright LSP 래퍼나 다른 타입 분석기를 위한 추상화.
    """

    def get_type_at(self, file_path: str, line: int, column: int) -> TypeInfoContract | None:
        """
        특정 위치의 타입 정보 획득.

        Args:
            file_path: 파일 경로
            line: 라인 번호 (1-based)
            column: 컬럼 번호 (0-based)

        Returns:
            TypeInfoContract or None
        """
        ...

    def normalize_type(self, type_str: str) -> str:
        """
        타입 문자열 정규화.

        예:
            "Optional[str]" → "str | None"
            "(variable) x: int" → "int"
            "Connection" → "sqlite3.Connection" (known types)

        Args:
            type_str: 원본 타입 문자열

        Returns:
            정규화된 타입 문자열
        """
        ...


# =============================================================================
# IRDocument 확장 요구사항
# =============================================================================


@runtime_checkable
class IRDocumentWithSemanticPort(Protocol):
    """
    Semantic IR가 추가된 IRDocument 인터페이스.

    LayeredIRBuilder.build_full() 완료 후 IRDocument가 만족해야 하는 계약.
    """

    # 기본 IR
    @property
    def nodes(self) -> list[Any]: ...

    @property
    def edges(self) -> list[Any]: ...

    # Semantic IR (🔥 필수)
    @property
    def expressions(self) -> list["Expression"]:
        """Expression IR - Taint 분석 핵심."""
        ...

    @property
    def dfg_snapshot(self) -> "DfgSnapshot | None":
        """DFG 스냅샷."""
        ...

    @property
    def cfgs(self) -> list["ControlFlowGraph"]:
        """CFG 리스트."""
        ...

    @property
    def types(self) -> list["TypeEntity"]:
        """타입 엔티티."""
        ...

    # Index 관련
    def build_indexes(self) -> None:
        """
        인덱스 빌드 (QueryEngine 사용 전 필수).

        이 메서드는 LayeredIRBuilder.build_full() 완료 후
        자동으로 호출되어야 합니다.
        """
        ...

    def ensure_indexes(self) -> None:
        """인덱스가 빌드되지 않았으면 빌드."""
        ...

    # Expression 조회
    def get_all_expressions(self) -> list["Expression"]:
        """모든 Expression 반환."""
        ...

    def find_expression_by_id(self, expr_id: str) -> "Expression | None":
        """ID로 Expression 조회."""
        ...
