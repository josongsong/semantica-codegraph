"""
Taint Analysis Ports

Taint 분석 파이프라인의 인터페이스 정의.

이 파일은 Taint 분석에서 사용되는 핵심 계약을 정의합니다:
1. AtomMatcher의 입출력 계약 (🔥 HCG/FQN 기반 매칭)
2. TaintAnalysisService의 결과 타입
3. AtomIndexer의 계약
4. IR → Taint 레이어 간 데이터 흐름

Hexagonal Architecture:
- Domain Layer: 이 파일 (Port/Protocol 정의)
- Infrastructure Layer: TypeAwareAtomMatcher, AtomIndexer, TaintAnalysisService
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.taint.atoms import AtomSpec
    from codegraph_engine.code_foundation.domain.taint.models import DetectedAtoms
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression


# =============================================================================
# Expression → Taint Matcher 인터페이스 계약
# =============================================================================


class TaintExpressionContract(TypedDict, total=False):
    """
    Taint Matcher가 Expression에서 기대하는 attrs 필드.

    🔥 핵심: TypeAwareAtomMatcher.match_call()이 동작하려면
    Expression.attrs가 이 계약을 만족해야 합니다.

    필수 필드:
        - callee_name: 함수/메서드 이름 (예: "execute", "request.args.get")

    HCG/FQN 매칭에 필요한 필드:
        - receiver_type: LSP에서 반환한 타입 (예: "(variable) conn: Connection")
        - lsp_type: LSP 원본 타입 문자열

    Flow 분석에 필요한 필드:
        - arg_expr_ids: 인자 Expression ID 리스트

    이 계약이 지켜지지 않으면:
        - callee_name 없음 → 매칭 실패, 빈 결과 반환
        - receiver_type 없음 → call-only 매칭으로 fallback (정확도 저하)
    """

    # 🔥 필수 (없으면 매칭 불가)
    callee_name: str

    # 🔥 HCG/FQN 매칭에 중요 (없으면 정확도 저하)
    receiver_type: str  # "(variable) conn: Connection" 형식
    lsp_type: str  # LSP 원본 타입

    # Flow 분석용
    arg_expr_ids: list[str]


# =============================================================================
# AtomIndexer 인터페이스
# =============================================================================


@runtime_checkable
class AtomIndexerPort(Protocol):
    """
    AtomIndexer 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/taint/matching/atom_indexer.py

    책임:
    1. Atom 스펙을 (base_type, call) 쌍으로 인덱싱
    2. O(1) 조회 제공
    3. FQN 기반 매칭 지원

    사용 패턴:
        indexer = AtomIndexer()
        indexer.build_index(atoms)
        matches = indexer.find_by_fqn("sqlite3.Connection.execute")
    """

    def build_index(self, atoms: list["AtomSpec"]) -> None:
        """
        Atom 인덱스 빌드.

        Args:
            atoms: AtomSpec 리스트

        Raises:
            ValueError: atoms가 비어있는 경우
            TypeError: atoms에 AtomSpec이 아닌 요소가 있는 경우

        Contract:
            - 인덱스 키: (base_type, call) 튜플
            - base_type이 있는 atom은 (base_type, call)과 (None, call) 둘 다 인덱싱
            - 이후 find_by_* 메서드 호출 가능
        """
        ...

    def find_by_call(
        self,
        base_type: str | None,
        call_name: str,
    ) -> list["AtomSpec"]:
        """
        (type, call) 쌍으로 Atom 조회.

        Args:
            base_type: 타입 FQN (예: "sqlite3.Connection") 또는 None
            call_name: 메서드/함수 이름 (예: "execute")

        Returns:
            매칭되는 AtomSpec 리스트

        Raises:
            RuntimeError: 인덱스가 빌드되지 않은 경우
            ValueError: call_name이 비어있는 경우

        Performance:
            O(1) average, O(k) where k = matches
        """
        ...

    def find_by_fqn(self, fqn: str) -> list["AtomSpec"]:
        """
        🔥 HCG 기반: FQN으로 Atom 조회.

        FQN 형식: "{module}.{class}.{method}"
        예: "sqlite3.Connection.execute"

        매칭 전략 (우선순위):
            1. Exact match: (sqlite3.Connection, execute)
            2. Call-only match: (None, execute)
            3. Suffix match: (Connection, execute)

        Args:
            fqn: Fully Qualified Name

        Returns:
            매칭되는 AtomSpec 리스트 (중복 제거됨)

        Raises:
            RuntimeError: 인덱스가 빌드되지 않은 경우
        """
        ...

    def find_by_type(self, base_type: str) -> list["AtomSpec"]:
        """
        타입으로만 Atom 조회.

        Args:
            base_type: 타입 FQN

        Returns:
            해당 타입의 모든 Atom
        """
        ...

    def is_built(self) -> bool:
        """인덱스 빌드 여부 확인."""
        ...

    def get_stats(self) -> dict[str, int]:
        """인덱스 통계 반환."""
        ...


# =============================================================================
# MatchResult 계약
# =============================================================================


@dataclass
class MatchResultContract:
    """
    AtomMatcher.match_call()의 결과.

    하나의 Expression이 하나의 AtomSpec과 매칭될 때의 결과.
    """

    # 매칭 성공 여부
    matched: bool = True

    # 매칭 신뢰도 (0.0 ~ 1.0)
    confidence: float = 1.0

    # 매칭 방법
    match_method: str = "unknown"  # "fqn", "type_aware", "call_only", "fallback"

    # 매칭된 rule 인덱스
    matched_rule_index: int = 0

    # 제약조건 검증 결과
    constraints_satisfied: bool = True

    # 추가 메타데이터
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# TypeAwareAtomMatcher 인터페이스
# =============================================================================


@runtime_checkable
class TypeAwareAtomMatcherPort(Protocol):
    """
    TypeAwareAtomMatcher 인터페이스.

    구현체: src/contexts/code_foundation/infrastructure/taint/matching/type_aware_matcher.py

    🔥 핵심 책임:
    1. Expression을 AtomSpec과 매칭
    2. HCG/LSP 타입 정보 활용 (receiver_type → FQN)
    3. 제약조건 검증

    매칭 전략 (우선순위):
        1. FQN 매칭: receiver_type 정규화 → "{type}.{method}" FQN 생성 → find_by_fqn
        2. Type-aware 매칭: find_by_call(normalized_type, method)
        3. Call-only 매칭: find_by_call(None, callee_name)

    사용 패턴:
        matcher = TypeAwareAtomMatcher(indexer, validator)
        matches = matcher.match_call(call_expr, ir_doc)
        for atom, result in matches:
            if atom.kind == "sink":
                # 취약점 후보
    """

    def match_call(
        self,
        call_expr: "Expression",
        ir_doc: Any,
    ) -> list[tuple["AtomSpec", MatchResultContract]]:
        """
        CALL Expression을 Atom과 매칭.

        Args:
            call_expr: CALL 타입 Expression
            ir_doc: IR 문서 (TypeInfo 조회, DFG alias 해석에 사용)

        Returns:
            (AtomSpec, MatchResult) 튜플 리스트

        Pre-conditions:
            - call_expr.kind == ExprKind.CALL
            - call_expr.attrs["callee_name"] 존재 (🔥 필수)
            - call_expr.attrs["receiver_type"] 존재 (선택, 있으면 정확도 향상)

        Post-conditions:
            - 매칭된 각 AtomSpec은 유효한 match_rules 보유
            - MatchResult.confidence > 0

        Contract:
            - callee_name 없으면 빈 리스트 반환 + warning 로그
            - receiver_type 없으면 call-only 매칭으로 fallback
        """
        ...

    def match_all(
        self,
        ir_doc: Any,
        atoms: list["AtomSpec"],
    ) -> "DetectedAtoms":
        """
        IR 문서의 모든 Expression을 Atom과 매칭.

        Args:
            ir_doc: IR 문서
            atoms: AtomSpec 리스트

        Returns:
            DetectedAtoms (sources, sinks, sanitizers, propagators)

        Contract:
            - ir_doc.get_all_expressions() 호출 가능해야 함
            - 각 CALL Expression에 대해 match_call() 수행
            - 결과를 kind별로 분류 (source, sink, sanitizer, propagator)
        """
        ...

    def _normalize_receiver_type(self, receiver_type: str) -> str | None:
        """
        🔥 HCG/LSP 기반: receiver_type 정규화.

        LSP 형식 → FQN 변환:
            "(variable) conn: Connection" → "sqlite3.Connection"
            "(module) requests" → "requests"
            "Connection" → "sqlite3.Connection" (known types)

        Args:
            receiver_type: LSP에서 반환한 타입 문자열

        Returns:
            정규화된 FQN 또는 None

        Contract:
            - None 반환 시 FQN 매칭 불가 → call-only fallback
        """
        ...


# =============================================================================
# TaintAnalysisService 결과 타입
# =============================================================================


@dataclass
class SimpleVulnerabilityContract:
    """
    탐지된 취약점 정보.
    """

    policy_id: str  # 정책 ID (예: "sql-injection")
    source_atom_id: str  # 소스 Atom ID
    sink_atom_id: str  # 싱크 Atom ID
    source_location: str  # 소스 위치 (예: "file.py:10")
    sink_location: str  # 싱크 위치
    confidence: float  # 신뢰도 (0.0 ~ 1.0)
    severity: str  # "high", "medium", "low"
    path_length: int  # 경로 길이
    is_sanitized: bool = False  # sanitizer 통과 여부


class TaintAnalysisResultContract(TypedDict):
    """
    TaintAnalysisService.analyze()의 반환 타입.

    🔥 기존 문제: dict[str, Any] → 키가 뭔지 알 수 없음
    해결: TypedDict로 정확한 키와 타입 명시
    """

    # 탐지된 취약점 리스트
    vulnerabilities: list[SimpleVulnerabilityContract]

    # 탐지된 Atom들 (sources, sinks, sanitizers, propagators)
    detected_atoms: "DetectedAtoms"

    # 실행된 정책 ID 리스트
    policies_executed: list[str]

    # 실행 통계
    execution_stats: dict[str, int]


class TaintAnalysisResultPartial(TypedDict, total=False):
    """TaintAnalysisResult의 선택적 필드."""

    # 경로 정보 (optional)
    paths: list[dict[str, Any]]

    # 에러 정보
    errors: list[str]

    # 경고 정보
    warnings: list[str]


# =============================================================================
# TaintAnalysisService 인터페이스
# =============================================================================


@runtime_checkable
class TaintAnalysisServicePort(Protocol):
    """
    TaintAnalysisService 인터페이스.

    구현체: src/contexts/code_foundation/application/taint_analysis_service.py

    책임:
    1. IR 문서에서 source/sink/sanitizer 탐지
    2. 정책 기반 취약점 분석
    3. 결과 집계 및 반환

    의존성:
        - AtomRepositoryPort: Atom 로드
        - PolicyRepositoryPort: Policy 로드
        - AtomMatcherPort: Expression ↔ Atom 매칭
        - ConstraintValidatorPort: 제약조건 검증
        - PolicyCompilerPort: 정책 컴파일
    """

    def analyze(
        self,
        ir_doc: Any,
        control_config_path: Any | None = None,
        lang: str = "python",
    ) -> TaintAnalysisResultContract:
        """
        IR 문서 분석.

        Args:
            ir_doc: IR 문서 (IRDocumentWithSemanticPort 만족 필요)
            control_config_path: 제어 설정 파일 경로 (optional)
            lang: 언어 (기본: "python")

        Returns:
            TaintAnalysisResultContract

        Pre-conditions:
            - ir_doc.get_all_expressions() 사용 가능
            - ir_doc.dfg_snapshot 사용 가능 (optional, 있으면 정확도 향상)

        Contract:
            - 반환된 vulnerabilities는 각 SimpleVulnerabilityContract 만족
            - detected_atoms.sources, sinks 등은 유효한 DetectedSource, DetectedSink
        """
        ...


# =============================================================================
# FQN Normalizer 인터페이스
# =============================================================================


@runtime_checkable
class FQNNormalizerPort(Protocol):
    """
    FQN (Fully Qualified Name) 정규화 인터페이스.

    책임:
    1. LSP 타입 문자열 → FQN 변환
    2. 짧은 타입명 → 알려진 모듈 매핑
    3. 타입 문자열 정규화 (Optional[str] → str | None)

    사용 위치:
        - TypeAwareAtomMatcher._normalize_receiver_type()
        - AtomIndexer (future: wildcard 매칭)
    """

    def normalize_lsp_type(self, lsp_type: str) -> str | None:
        """
        LSP 타입 문자열을 FQN으로 변환.

        예:
            "(variable) conn: Connection" → "sqlite3.Connection"
            "(module) requests" → "requests"

        Args:
            lsp_type: LSP에서 반환한 타입 문자열

        Returns:
            정규화된 FQN 또는 None
        """
        ...

    def resolve_short_type(self, short_type: str) -> str:
        """
        짧은 타입명을 FQN으로 변환.

        예:
            "Connection" → "sqlite3.Connection"
            "Cursor" → "sqlite3.Cursor"
            "Request" → "flask.Request"

        Args:
            short_type: 짧은 타입명

        Returns:
            FQN (매핑 없으면 원본 반환)
        """
        ...

    def normalize_python_type(self, type_str: str) -> str:
        """
        Python 타입 문자열 정규화.

        예:
            "Optional[str]" → "str | None"
            "List[int]" → "list[int]"
            "Dict[str, Any]" → "dict[str, Any]"

        Args:
            type_str: 원본 타입 문자열

        Returns:
            정규화된 타입 문자열
        """
        ...


# =============================================================================
# Known Types Registry (FQN 해석용)
# =============================================================================


KNOWN_TYPE_MAPPINGS: dict[str, str] = {
    # sqlite3
    "Connection": "sqlite3.Connection",
    "Cursor": "sqlite3.Cursor",
    # Flask
    "Request": "flask.Request",
    "Response": "flask.Response",
    # Django
    "HttpRequest": "django.http.HttpRequest",
    "HttpResponse": "django.http.HttpResponse",
    "QuerySet": "django.db.models.QuerySet",
    # subprocess
    "Popen": "subprocess.Popen",
    "CompletedProcess": "subprocess.CompletedProcess",
    # psycopg2
    "connection": "psycopg2.extensions.connection",
    "cursor": "psycopg2.extensions.cursor",
    # pymysql
    # "Connection": "pymysql.connections.Connection",  # sqlite3와 충돌
    # requests
    "Session": "requests.Session",
    # lxml
    "Element": "lxml.etree.Element",
    "_Element": "lxml.etree._Element",
    # xml
    "ElementTree": "xml.etree.ElementTree.ElementTree",
}
"""
알려진 짧은 타입명 → FQN 매핑.

이 매핑은 Pyright가 짧은 타입명만 반환할 때 사용됩니다.
예: "Connection" → "sqlite3.Connection"

⚠️ 주의:
- 동일한 짧은 이름이 여러 모듈에 있을 수 있음 (예: Connection)
- 이 경우 import 문을 확인하거나 context 기반 해석 필요
"""


# =============================================================================
# Constraint Validation 확장
# =============================================================================


class ConstraintValidatorExtendedPort(Protocol):
    """
    ConstraintValidator 확장 인터페이스.

    RFC-030에서 추가된 SCCP, Dominator 통합을 포함.
    """

    def validate(self, node: Any, constraints: dict) -> bool:
        """기본 제약조건 검증."""
        ...

    def validate_arg_constraint(
        self,
        call_expr: "Expression",
        constraint: dict,
        ir_doc: Any,
    ) -> bool:
        """
        인자 제약조건 검증.

        Args:
            call_expr: CALL Expression
            constraint: {arg_index: 0, arg_type: "tainted"} 등
            ir_doc: IR 문서

        Returns:
            제약조건 만족 여부
        """
        ...

    def set_sccp_result(self, sccp_result: Any) -> None:
        """RFC-030: SCCP 결과 설정 (상수 전파)."""
        ...

    def set_dominator_tree(self, dom_tree: Any) -> None:
        """RFC-030: Dominator tree 설정 (guard 검증)."""
        ...

    def set_ir_document(self, ir_doc: Any) -> None:
        """RFC-030: IR 문서 설정."""
        ...
