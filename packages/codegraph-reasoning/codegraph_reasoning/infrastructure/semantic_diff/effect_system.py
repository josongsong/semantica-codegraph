"""
Effect System

함수의 side-effect를 정적으로 추론.
- Local Effect: 소스 코드에서 명시적 effect
- Interprocedural Propagation: Callee → Caller
- Unknown Handling: Pessimistic default
"""

import re
from typing import Literal

from codegraph_engine.code_foundation.domain.models import GraphNode as IRNode
from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind, IRDocument, NodeKind
from codegraph_reasoning.domain.models import EffectSet, EffectType


class LocalEffectAnalyzer:
    """
    Local effect 분석.

    소스 코드에서 명시적으로 드러나는 effect 추출.
    """

    # Effect 감지 패턴
    GLOBAL_KEYWORDS = {"global", "nonlocal"}
    IO_FUNCTIONS = {"print", "open", "write", "read", "input"}
    DB_PATTERNS = [r"\.query\(", r"\.execute\(", r"\.commit\(", r"\.save\(", r"\.delete\("]
    NETWORK_PATTERNS = [r"requests\.", r"urllib\.", r"httpx\.", r"\.get\(", r"\.post\("]
    LOG_PATTERNS = [r"logger\.", r"logging\.", r"log\.", r"\.info\(", r"\.error\("]

    def analyze(self, node: IRNode) -> EffectSet:
        """
        함수의 local effect 분석.

        Returns:
            EffectSet with confidence=1.0 (static analysis)
        """
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            return EffectSet(
                symbol_id=node.id, effects={EffectType.PURE}, idempotent=True, confidence=1.0, source="static"
            )

        effects = set()
        idempotent = True

        # Body 분석
        if node.body:
            for stmt in node.body:
                stmt_effects, stmt_idempotent = self._analyze_statement(stmt)
                effects.update(stmt_effects)
                if not stmt_idempotent:
                    idempotent = False

        # 아무 effect도 없으면 PURE
        if not effects:
            effects.add(EffectType.PURE)

        return EffectSet(symbol_id=node.id, effects=effects, idempotent=idempotent, confidence=1.0, source="static")

    def _analyze_statement(self, stmt: dict) -> tuple[set[EffectType], bool]:
        """
        Statement 분석.

        Returns:
            (effects, idempotent)
        """
        effects = set()
        idempotent = True

        stmt_str = str(stmt)

        # 1. Global mutation 감지
        if self._is_global_mutation(stmt):
            effects.add(EffectType.GLOBAL_MUTATION)
            idempotent = False

        # 2. I/O 연산 감지
        if self._is_io_operation(stmt_str):
            effects.add(EffectType.IO)
            # print는 idempotent, file write는 아님
            if not self._is_idempotent_io(stmt_str):
                idempotent = False

        # 3. DB 연산 감지
        if self._is_db_operation(stmt_str):
            if "query" in stmt_str.lower() or "select" in stmt_str.lower():
                effects.add(EffectType.DB_READ)
            else:
                effects.add(EffectType.DB_WRITE)
                # INSERT/UPDATE는 non-idempotent (기본)
                if not self._is_idempotent_db(stmt_str):
                    idempotent = False

        # 4. Network 연산 감지
        if self._is_network_operation(stmt_str):
            effects.add(EffectType.NETWORK)
            idempotent = False

        # 5. Logging 감지
        if self._is_log_operation(stmt_str):
            effects.add(EffectType.LOG)
            # Logging은 idempotent (같은 로그 여러번 가능)

        return effects, idempotent

    def _is_global_mutation(self, stmt: dict) -> bool:
        """Global 변수 수정 감지"""
        stmt_str = str(stmt)
        return any(kw in stmt_str for kw in self.GLOBAL_KEYWORDS)

    def _is_io_operation(self, stmt_str: str) -> bool:
        """I/O 연산 감지"""
        return any(fn in stmt_str for fn in self.IO_FUNCTIONS)

    def _is_idempotent_io(self, stmt_str: str) -> bool:
        """Idempotent I/O 판별"""
        # print는 idempotent
        if "print(" in stmt_str:
            return True
        # file write는 non-idempotent (append mode)
        if "write(" in stmt_str or "open(" in stmt_str:
            return False
        return True

    def _is_db_operation(self, stmt_str: str) -> bool:
        """DB 연산 감지"""
        return any(re.search(pattern, stmt_str) for pattern in self.DB_PATTERNS)

    def _is_idempotent_db(self, stmt_str: str) -> bool:
        """Idempotent DB 판별"""
        # UPDATE/INSERT with ON CONFLICT는 idempotent
        if "upsert" in stmt_str.lower():
            return True
        # DELETE는 idempotent (같은 조건 재실행 가능)
        if "delete" in stmt_str.lower():
            return True
        return False

    def _is_network_operation(self, stmt_str: str) -> bool:
        """Network 연산 감지"""
        return any(re.search(pattern, stmt_str) for pattern in self.NETWORK_PATTERNS)

    def _is_log_operation(self, stmt_str: str) -> bool:
        """Logging 감지"""
        return any(re.search(pattern, stmt_str) for pattern in self.LOG_PATTERNS)


class TrustedLibraryDB:
    """
    Trusted library effect database.

    주요 라이브러리들의 effect를 사전 정의.
    """

    def __init__(self):
        self.specs: dict[str, EffectSet] = {}
        self._load_builtin_specs()

    def _load_builtin_specs(self):
        """내장 라이브러리 effect 정의"""

        # Python builtin
        self.add("builtins.print", {EffectType.IO}, True, "static")
        self.add("builtins.len", {EffectType.PURE}, True, "static")
        self.add("builtins.sum", {EffectType.PURE}, True, "static")

        # NumPy (pure functions)
        self.add("numpy.array", {EffectType.PURE}, True, "static")
        self.add("numpy.sum", {EffectType.PURE}, True, "static")
        self.add("numpy.dot", {EffectType.PURE}, True, "static")

        # Logging
        self.add("logging.info", {EffectType.LOG}, True, "allowlist")
        self.add("logging.error", {EffectType.LOG}, True, "allowlist")
        self.add("logging.warning", {EffectType.LOG}, True, "allowlist")

        # Redis
        self.add("redis.set", {EffectType.WRITE_STATE}, True, "allowlist")  # Idempotent
        self.add("redis.get", {EffectType.READ_STATE}, True, "allowlist")
        self.add("redis.incr", {EffectType.WRITE_STATE}, False, "allowlist")  # Non-idempotent

        # SQLAlchemy
        self.add("sqlalchemy.query", {EffectType.DB_READ}, True, "allowlist")
        self.add("sqlalchemy.add", {EffectType.DB_WRITE}, False, "allowlist")
        self.add("sqlalchemy.commit", {EffectType.DB_WRITE}, False, "allowlist")

    def add(self, fqn: str, effects: set[EffectType], idempotent: bool, source: Literal["static", "allowlist"]):
        """Library effect 추가"""
        self.specs[fqn] = EffectSet(
            symbol_id=fqn,
            effects=effects,
            idempotent=idempotent,
            confidence=0.95,  # Allowlist는 0.95
            source=source,
        )

    def get(self, fqn: str) -> EffectSet | None:
        """FQN으로 effect 조회"""
        return self.specs.get(fqn)

    def contains(self, fqn: str) -> bool:
        """FQN이 allowlist에 있는지"""
        return fqn in self.specs


# Effect Pattern Database
EFFECT_PATTERNS = [
    {
        "pattern": r".*\.set\(",
        "effects": {EffectType.WRITE_STATE},
        "idempotent": True,
        "confidence": 0.8,
    },
    {
        "pattern": r".*\.append\(",
        "effects": {EffectType.WRITE_STATE},
        "idempotent": False,
        "confidence": 0.8,
    },
    {
        "pattern": r".*\.log\(",
        "effects": {EffectType.LOG},
        "idempotent": True,
        "confidence": 0.7,
    },
    {
        "pattern": r"print\(",
        "effects": {EffectType.IO},
        "idempotent": True,
        "confidence": 0.95,
    },
]


class UnknownEffectHandler:
    """Unknown call 처리 (Pessimistic default)"""

    def __init__(self, allowlist: TrustedLibraryDB):
        self.allowlist = allowlist

    def handle(self, callee_name: str) -> EffectSet:
        """
        Unknown call의 effect 추정.

        우선순위:
        1. Allowlist 확인
        2. Pattern matching
        3. Pessimistic default
        """
        # 1. Allowlist 확인
        if self.allowlist.contains(callee_name):
            effect = self.allowlist.get(callee_name)
            if effect:
                return effect

        # 2. Pattern matching
        for pattern_spec in EFFECT_PATTERNS:
            if re.match(pattern_spec["pattern"], callee_name):
                return EffectSet(
                    symbol_id=callee_name,
                    effects=pattern_spec["effects"],
                    idempotent=pattern_spec["idempotent"],
                    confidence=pattern_spec["confidence"],
                    source="inferred",
                )

        # 3. Pessimistic default
        return EffectSet(
            symbol_id=callee_name,
            effects={EffectType.WRITE_STATE, EffectType.GLOBAL_MUTATION},
            idempotent=False,
            confidence=0.5,
            source="unknown",
        )


class EffectPropagator:
    """Effect 전파 (callee → caller)"""

    def __init__(self, graph: IRDocument):
        self.graph = graph
        self._build_call_graph()

    def _build_call_graph(self):
        """Call graph 구축"""
        self.callees_map: dict[str, set[str]] = {}

        for edge in self.graph.edges:
            if edge.kind == EdgeKind.CALLS:
                caller_id = edge.source_node_id
                callee_id = edge.target_node_id

                if caller_id not in self.callees_map:
                    self.callees_map[caller_id] = set()

                self.callees_map[caller_id].add(callee_id)

    def propagate(
        self,
        node: IRNode,
        local_effect: EffectSet,
        callee_effects: dict[str, EffectSet],
        unknown_handler: UnknownEffectHandler,
    ) -> EffectSet:
        """
        Callee effect를 caller로 전파.

        Effect(f) = LocalEffect(f) ∪ (∪ Effect(callees))
        """
        propagated_effects = set(local_effect.effects)
        min_confidence = local_effect.confidence
        idempotent = local_effect.idempotent

        # Callees 조회
        callees = self.callees_map.get(node.id, set())

        for callee_id in callees:
            if callee_id in callee_effects:
                # Known callee
                callee_effect = callee_effects[callee_id]
                propagated_effects.update(callee_effect.effects)
                min_confidence = min(min_confidence, callee_effect.confidence)

                if not callee_effect.idempotent:
                    idempotent = False
            else:
                # Unknown callee → Pessimistic default
                unknown_effect = unknown_handler.handle(callee_id)
                propagated_effects.update(unknown_effect.effects)
                min_confidence = min(min_confidence, unknown_effect.confidence)
                idempotent = False

        return EffectSet(
            symbol_id=node.id,
            effects=propagated_effects,
            idempotent=idempotent,
            confidence=min_confidence,
            source="inferred",
        )


class EffectAnalyzer:
    """
    Effect 분석 통합.

    Local + Interprocedural propagation.
    """

    def __init__(self, graph: IRDocument):
        self.local_analyzer = LocalEffectAnalyzer()
        self.propagator = EffectPropagator(graph)
        self.allowlist = TrustedLibraryDB()
        self.unknown_handler = UnknownEffectHandler(self.allowlist)

    def analyze_all(self, ir_doc: IRDocument) -> dict[str, EffectSet]:
        """
        모든 함수의 effect 분석.

        Returns:
            symbol_id → EffectSet
        """
        result = {}

        # 1. Local effect 먼저 계산
        local_effects = {}
        for node in ir_doc.nodes:
            if node.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                local_effect = self.local_analyzer.analyze(node)
                local_effects[node.id] = local_effect

        # 2. Interprocedural propagation
        # (Topological order가 이상적이지만 여기서는 간단히 반복)
        for _ in range(3):  # 최대 3번 반복 (대부분 케이스 커버)
            for node in ir_doc.nodes:
                if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
                    continue

                local_effect = local_effects[node.id]
                propagated_effect = self.propagator.propagate(node, local_effect, result, self.unknown_handler)
                result[node.id] = propagated_effect

        return result

    def analyze_single(self, node: IRNode, callee_effects: dict[str, EffectSet]) -> EffectSet:
        """단일 함수의 effect 분석"""
        local_effect = self.local_analyzer.analyze(node)
        return self.propagator.propagate(node, local_effect, callee_effects, self.unknown_handler)
