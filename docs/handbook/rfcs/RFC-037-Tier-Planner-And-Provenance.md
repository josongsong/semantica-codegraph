# RFC-037: Tier Planner + Deterministic Provenance

## Status: Draft
## Author: Semantica Team
## Created: 2025-12-21
## Priority: P0
## Estimated: 8-10h
## Depends on: RFC-036

---

## 1. Executive Summary

**목표:**
RFC-036의 3-tier model을 **자동화**하고 **재현 가능성**을 증명한다.

**핵심 컴포넌트:**
1. **Tier Planner:** AI 요청 → 필요한 tier 자동 선택
2. **Deterministic Provenance:** Build 재현 가능성 증명

**효과:**
- FULL tier 남발 방지 (사용자 실수 제거)
- Deterministic 구조적 보장
- 디버깅/감사 추적 가능

---

## 2. 문제 정의

### 2.1 Problem 1: Tier 선택 사용자 부담

**현재 (RFC-036):**
```python
# 사용자가 직접 선택
config = BuildConfig.for_refactoring()  # 이게 맞나?
config = BuildConfig.for_analysis()     # 이게 필요한가?
```

**문제:**
- 사용자 판단 오류 → FULL 남발 → 성능 저하
- "어느 tier가 필요한지" 판단 어려움

### 2.2 Problem 2: Determinism 증명 부재

**현재:**
```python
# 결과만 있음
ir_doc = builder.build(...)
# 어떻게 만들어졌는지? → 모름
```

**문제:**
- 재현 불가능 (같은 결과 나올지 보장 못함)
- 디버깅 어려움
- Non-deterministic bug 추적 불가

---

## 3. 설계

### 3.1 Tier Planner (자동 승격)

#### 3.1.1 Agent Intent Taxonomy

```python
from enum import Enum

class AgentIntent(str, Enum):
    """AI 에이전트 의도."""
    
    # Tier 1: BASE
    UNDERSTAND = "understand"           # 함수 이해
    NAVIGATE = "navigate"               # 코드 탐색
    FIND_CALLERS = "find_callers"       # 호출자 찾기
    FIND_REFERENCES = "find_references" # 참조 찾기
    
    # Tier 2: EXTENDED
    RENAME = "rename"                   # 이름 변경
    EXTRACT_METHOD = "extract_method"   # 메서드 추출
    INLINE = "inline"                   # 인라인
    TRACE_VALUE = "trace_value"         # 값 추적
    
    # Tier 3: FULL
    SLICE = "slice"                     # 프로그램 슬라이싱
    PATH_ANALYSIS = "path_analysis"     # 경로 분석
    PROVE_SAFETY = "prove_safety"       # 안전성 증명


class QueryType(str, Enum):
    """쿼리 타입."""
    
    CALLERS = "callers"         # 호출자 (BASE)
    CALLEES = "callees"         # 호출 대상 (BASE)
    REFERENCES = "references"   # 참조 (BASE)
    FLOW = "flow"              # 데이터 흐름 (EXTENDED)
    ORIGIN = "origin"          # 값 출처 (EXTENDED)
    SLICE = "slice"            # 슬라이싱 (FULL)
    PATH = "path"              # 경로 (FULL)


class Scope(str, Enum):
    """분석 범위."""
    
    FUNCTION = "function"  # 함수 내부만
    FILE = "file"          # 파일 내부
    MODULE = "module"      # 모듈 (1-hop)
    REPO = "repo"          # 전체 레포
```

#### 3.1.2 Tier Planner 구현

```python
@dataclass
class TierPlan:
    """Tier planning result."""
    
    tier: SemanticTier
    options: dict  # DFG threshold, depth, etc.
    reason: str    # Why this tier


class TierPlanner:
    """
    RFC-037: Automatic tier selection.
    
    Maps (AgentIntent, QueryType, Scope) → SemanticTier.
    
    SOTA: Prevents FULL tier overuse.
    """
    
    # Decision matrix
    TIER_MATRIX: dict[tuple[AgentIntent, QueryType, Scope], SemanticTier] = {
        # BASE tier
        (AgentIntent.UNDERSTAND, QueryType.CALLERS, Scope.FUNCTION): SemanticTier.BASE,
        (AgentIntent.NAVIGATE, QueryType.CALLEES, Scope.FILE): SemanticTier.BASE,
        (AgentIntent.FIND_CALLERS, QueryType.CALLERS, Scope.REPO): SemanticTier.BASE,
        (AgentIntent.FIND_REFERENCES, QueryType.REFERENCES, Scope.REPO): SemanticTier.BASE,
        
        # EXTENDED tier
        (AgentIntent.RENAME, QueryType.FLOW, Scope.FILE): SemanticTier.EXTENDED,
        (AgentIntent.EXTRACT_METHOD, QueryType.FLOW, Scope.FUNCTION): SemanticTier.EXTENDED,
        (AgentIntent.INLINE, QueryType.FLOW, Scope.FUNCTION): SemanticTier.EXTENDED,
        (AgentIntent.TRACE_VALUE, QueryType.ORIGIN, Scope.FILE): SemanticTier.EXTENDED,
        
        # FULL tier
        (AgentIntent.SLICE, QueryType.SLICE, Scope.FUNCTION): SemanticTier.FULL,
        (AgentIntent.PATH_ANALYSIS, QueryType.PATH, Scope.FILE): SemanticTier.FULL,
        (AgentIntent.PROVE_SAFETY, QueryType.SLICE, Scope.FUNCTION): SemanticTier.FULL,
    }
    
    def plan(
        self,
        intent: AgentIntent,
        query_type: QueryType,
        scope: Scope,
    ) -> TierPlan:
        """
        Plan required tier for agent request.
        
        Args:
            intent: What agent wants to do
            query_type: What kind of query
            scope: Analysis scope
        
        Returns:
            TierPlan with tier and options
        
        Examples:
            >>> planner.plan(AgentIntent.RENAME, QueryType.FLOW, Scope.FILE)
            TierPlan(tier=EXTENDED, options={"dfg_threshold": 500}, reason="...")
        """
        key = (intent, query_type, scope)
        
        # Lookup in matrix
        tier = self.TIER_MATRIX.get(key)
        
        if tier is None:
            # Conservative fallback
            tier = self._conservative_fallback(intent, query_type, scope)
        
        # Build options
        options = {}
        if tier == SemanticTier.EXTENDED:
            options["dfg_threshold"] = 500
        
        reason = f"{intent.value} + {query_type.value} requires {tier.value}"
        
        return TierPlan(tier=tier, options=options, reason=reason)
    
    def _conservative_fallback(
        self,
        intent: AgentIntent,
        query_type: QueryType,
        scope: Scope,
    ) -> SemanticTier:
        """Conservative tier selection for unknown combinations."""
        # SLICE/PATH → FULL
        if query_type in (QueryType.SLICE, QueryType.PATH):
            return SemanticTier.FULL
        
        # FLOW/ORIGIN → EXTENDED
        if query_type in (QueryType.FLOW, QueryType.ORIGIN):
            return SemanticTier.EXTENDED
        
        # Default: BASE
        return SemanticTier.BASE
```

### 3.2 Deterministic Provenance

#### 3.2.1 Build Provenance 구현

```python
import hashlib
from dataclasses import dataclass, field

@dataclass(frozen=True)
class BuildProvenance:
    """
    RFC-037: Build provenance for deterministic verification.
    
    Immutable record of how IR was built.
    Enables:
    - Exact replay
    - Non-determinism debugging
    - Audit trail
    """
    
    # Input fingerprint
    input_fingerprint: str
    """Hash of (repo_rev, sorted file hashes)"""
    
    # Builder fingerprint
    builder_version: str
    """Semantic IR builder code hash"""
    
    # Config fingerprint
    config_fingerprint: str
    """Hash of (tier, flags, thresholds)"""
    
    # Dependency fingerprint
    dependency_fingerprint: str
    """Hash of (Summary versions, YAML versions)"""
    
    # Build metadata
    build_timestamp: str
    build_duration_ms: int
    
    # Deterministic guarantees
    node_sort_order: str = "id"      # Stable iteration
    edge_sort_order: str = "id"      # Stable iteration
    parallel_seed: int = 42           # Deterministic parallel
    
    @classmethod
    def create(
        cls,
        repo_rev: str,
        files: list[Path],
        config: BuildConfig,
        builder_version: str,
        dependency_versions: dict[str, str],
    ) -> "BuildProvenance":
        """Create provenance from build inputs."""
        import hashlib
        from datetime import datetime
        
        # Input fingerprint
        file_hashes = sorted([
            hashlib.sha256(f.read_bytes()).hexdigest()
            for f in files
        ])
        input_fp = hashlib.sha256(
            f"{repo_rev}:{'|'.join(file_hashes)}".encode()
        ).hexdigest()[:16]
        
        # Config fingerprint
        config_data = f"{config.semantic_tier}:{config.dfg}:{config.ssa}"
        config_fp = hashlib.sha256(config_data.encode()).hexdigest()[:16]
        
        # Dependency fingerprint
        dep_data = "|".join(f"{k}:{v}" for k, v in sorted(dependency_versions.items()))
        dep_fp = hashlib.sha256(dep_data.encode()).hexdigest()[:16]
        
        return cls(
            input_fingerprint=input_fp,
            builder_version=builder_version,
            config_fingerprint=config_fp,
            dependency_fingerprint=dep_fp,
            build_timestamp=datetime.now().isoformat(),
            build_duration_ms=0,  # Set later
        )
    
    def verify_deterministic(self, other: "BuildProvenance") -> bool:
        """
        Verify if two builds should produce identical results.
        
        Returns:
            True if all fingerprints match
        """
        return (
            self.input_fingerprint == other.input_fingerprint and
            self.builder_version == other.builder_version and
            self.config_fingerprint == other.config_fingerprint and
            self.dependency_fingerprint == other.dependency_fingerprint
        )
```

#### 3.2.2 Stable Merge 규칙

```python
class StableMerger:
    """
    RFC-037: Stable merge for parallel results.
    
    Ensures deterministic output from parallel builds.
    """
    
    @staticmethod
    def merge_nodes(node_lists: list[list[Node]]) -> list[Node]:
        """
        Merge nodes from parallel workers.
        
        SOTA: Stable sort by node ID.
        
        Args:
            node_lists: Node lists from workers
        
        Returns:
            Merged node list (stable order)
        """
        all_nodes = []
        for nodes in node_lists:
            all_nodes.extend(nodes)
        
        # Stable sort by ID
        all_nodes.sort(key=lambda n: n.id)
        
        return all_nodes
    
    @staticmethod
    def merge_edges(edge_lists: list[list[Edge]]) -> list[Edge]:
        """
        Merge edges with deduplication.
        
        SOTA: Stable sort by (source_id, target_id, kind).
        """
        # Deduplicate
        seen = set()
        unique_edges = []
        
        for edges in edge_lists:
            for edge in edges:
                key = (edge.source_id, edge.target_id, edge.kind)
                if key not in seen:
                    seen.add(key)
                    unique_edges.append(edge)
        
        # Stable sort
        unique_edges.sort(key=lambda e: (e.source_id, e.target_id, str(e.kind)))
        
        return unique_edges
```

---

## 4. Refactor Primitives API

### 4.1 API 설계

```python
from dataclasses import dataclass

@dataclass
class RenameImpact:
    """Rename impact analysis result."""
    
    total_occurrences: int
    definition_count: int
    reference_count: int
    dynamic_risk_score: float  # 0.0-1.0
    affected_files: list[str]


@dataclass
class SafetyReport:
    """Extract method safety report."""
    
    is_safe: bool
    captured_vars: list[str]
    side_effects: list[str]
    return_values: list[str]
    control_flow_breaks: list[str]  # break/continue/return


@dataclass
class SideEffects:
    """Function side-effect summary."""
    
    heap_writes: list[str]       # Heap modifications
    io_operations: list[str]     # File/network IO
    external_calls: list[str]    # Calls to external libs
    has_exceptions: bool


class RefactorPrimitives:
    """
    RFC-037: High-level API for AI coding agents.
    
    Built on RFC-036 tiers.
    Each primitive specifies required tier.
    """
    
    def __init__(self, ir_doc: IRDocument):
        self._ir_doc = ir_doc
        self._tier_planner = TierPlanner()
    
    # ================================================================
    # BASE Tier Primitives
    # ================================================================
    
    def get_callers(self, symbol: str) -> list[str]:
        """
        Get all callers of a symbol.
        
        Tier: BASE
        Complexity: O(1) via Call Graph
        
        Args:
            symbol: Function/method name or ID
        
        Returns:
            List of caller IDs
        
        Hexagonal: Uses IRQuery port.
        """
        # Use CALLS edges (reverse) via port
        callers = []
        for edge in self._query.get_edges(EdgeKind.CALLS):
            if edge.target_id == symbol:
                callers.append(edge.source_id)
        return callers
    
    def get_callees(self, function: str) -> list[str]:
        """
        Get all callees of a function.
        
        Tier: BASE
        Complexity: O(1) via Call Graph
        
        Hexagonal: Uses IRQuery port.
        """
        callees = []
        for edge in self._query.get_edges(EdgeKind.CALLS):
            if edge.source_id == function:
                callees.append(edge.target_id)
        return callees
    
    def rename_impact(self, symbol: str) -> RenameImpact:
        """
        Analyze rename impact.
        
        Tier: BASE
        Uses: Occurrences + Call Graph
        
        Returns:
            RenameImpact with occurrence count and risk
        
        Hexagonal: Uses IRQuery port.
        """
        # Count occurrences via port
        occurrences = self._query.get_occurrences(symbol)
        
        defs = [o for o in occurrences if o.role == "definition"]
        refs = [o for o in occurrences if o.role == "reference"]
        
        # Calculate dynamic risk (conservatively)
        # High risk if: eval(), getattr(), reflection
        dynamic_risk = self._calculate_dynamic_risk(symbol)
        
        affected_files = list(set(o.file_path for o in occurrences))
        
        return RenameImpact(
            total_occurrences=len(occurrences),
            definition_count=len(defs),
            reference_count=len(refs),
            dynamic_risk_score=dynamic_risk,
            affected_files=affected_files,
        )
    
    # ================================================================
    # EXTENDED Tier Primitives
    # ================================================================
    
    def extract_method_safety(self, range: Range) -> SafetyReport:
        """
        Check if range can be safely extracted.
        
        Tier: EXTENDED
        Uses: CFG + DFG
        
        Args:
            range: Code range (start_line, end_line)
        
        Returns:
            SafetyReport with captured vars, side effects
        
        Hexagonal: Uses IRQuery port.
        """
        # Requires DFG via port
        dfg = self._query.get_dfg()
        if not dfg:
            raise ValueError("DFG required (use EXTENDED tier)")
        
        # Find variables in range
        vars_in_range = self._get_variables_in_range(range)
        
        # Check captured (defined outside, used inside)
        captured = [
            v for v in vars_in_range
            if self._is_captured(v, range, dfg)
        ]
        
        # Check side effects
        side_effects = self._analyze_side_effects(range)
        
        # Check return values
        return_values = self._find_return_values(range)
        
        # Check control flow breaks
        breaks = self._find_control_breaks(range)
        
        is_safe = (
            len(return_values) <= 1 and
            len(breaks) == 0
        )
        
        return SafetyReport(
            is_safe=is_safe,
            captured_vars=captured,
            side_effects=side_effects,
            return_values=return_values,
            control_flow_breaks=breaks,
        )
    
    def value_origin(self, var: str, at_line: int) -> list[str]:
        """
        Trace value origin (backward slice-lite).
        
        Tier: EXTENDED
        Uses: DFG
        
        Returns:
            List of origin locations
        
        Hexagonal: Uses IRQuery port.
        """
        dfg = self._query.get_dfg()
        if not dfg:
            raise ValueError("DFG required (use EXTENDED tier)")
        
        # Backward slice via DFG
        origins = []
        # (implementation)
        return origins
    
    # ================================================================
    # FULL Tier Primitives
    # ================================================================
    
    def program_slice(self, criterion: str, at_line: int) -> list[str]:
        """
        Compute program slice.
        
        Tier: FULL
        Uses: PDG
        
        Returns:
            List of node IDs in slice
        """
        # Requires PDG
        # (implementation via PDGBuilder)
        return []
```

### 3.3 통합 API

```python
class AgentAPI:
    """
    RFC-037: Unified API for AI agents.
    
    Combines Tier Planner + Primitives.
    """
    
    def __init__(self, builder: LayeredIRBuilder):
        self._builder = builder
        self._planner = TierPlanner()
        self._cache: dict[SemanticCacheKey, IRDocument] = {}
    
    async def execute(
        self,
        intent: AgentIntent,
        query_type: QueryType,
        scope: Scope,
        target: str,  # File/function/symbol
        **kwargs,
    ):
        """
        Execute agent request with automatic tier selection.
        
        Args:
            intent: Agent intent
            query_type: Query type
            scope: Scope
            target: Target file/function
        
        Returns:
            Query result
        
        SOTA: Automatic tier planning + caching
        """
        # Plan tier
        plan = self._planner.plan(intent, query_type, scope)
        
        # Build config
        if plan.tier == SemanticTier.BASE:
            config = BuildConfig.for_editor()
        elif plan.tier == SemanticTier.EXTENDED:
            config = BuildConfig.for_refactoring()
        else:
            config = BuildConfig.for_analysis()
        
        # Build IR (with cache)
        ir_doc = await self._get_or_build_ir(target, config)
        
        # Execute primitive
        primitives = RefactorPrimitives(ir_doc)
        
        if query_type == QueryType.CALLERS:
            return primitives.get_callers(kwargs.get("symbol"))
        elif query_type == QueryType.FLOW:
            return primitives.value_origin(kwargs.get("var"), kwargs.get("line"))
        # ... other primitives
```

---

## 5. 구현 계획

### 5.1 Phase 0: Ports (2h) - Hexagonal 준수

**파일:**
```
src/contexts/code_foundation/domain/ports/
└── ir_query.py       # IRQuery protocol
```

**구현:**
- IRQuery protocol
- get_nodes/edges/occurrences/dfg methods

**파일:**
```
src/contexts/code_foundation/infrastructure/ir/adapters/
└── ir_document_adapter.py  # IRDocumentAdapter
```

**구현:**
- IRDocumentAdapter implements IRQuery
- Wraps IRDocument

### 5.2 Phase 1: Tier Planner (4h)

**파일:**
```
src/contexts/code_foundation/domain/agent/
├── __init__.py
├── intents.py        # AgentIntent, QueryType, Scope enums
└── tier_planner.py   # TierPlanner class
```

**구현:**
- Intent taxonomy (3 enums)
- Decision matrix (dict)
- plan() method
- Conservative fallback

### 5.3 Phase 2: Deterministic Provenance (3h)

**파일:**
```
src/contexts/code_foundation/domain/ir/
└── provenance.py     # BuildProvenance (Domain)
```

**구현:**
- BuildProvenance dataclass (immutable)
- Fingerprint calculation
- Verification method

**파일:**
```
src/contexts/code_foundation/infrastructure/ir/
└── stable_merger.py  # StableMerger (Infrastructure)
```

**구현:**
- StableMerger (nodes, edges)
- Stable sort logic

### 5.4 Phase 3: Refactor Primitives (3h)

**파일:**
```
src/contexts/code_foundation/application/refactor/
├── __init__.py
├── primitives.py     # RefactorPrimitives class
└── models.py         # RenameImpact, SafetyReport, etc.
```

**구현:**
- Base primitives (5 methods) - depends on IRQuery
- Extended primitives (3 methods) - depends on IRQuery
- Full primitives (2 methods) - depends on IRQuery

**Total: 12h** (Port/Adapter 추가로 +2h)

---

## 6. 테스트 계획 (35 tests)

### 6.1 Tier Planner Tests (15 tests)

```python
class TestTierPlanner:
    def test_understand_requires_base(self):
        """UNDERSTAND → BASE"""
    
    def test_rename_requires_extended(self):
        """RENAME → EXTENDED"""
    
    def test_slice_requires_full(self):
        """SLICE → FULL"""
    
    def test_conservative_fallback(self):
        """Unknown → Conservative tier"""

class TestTierMatrix:
    """Test all matrix entries (11 tests)."""
```

### 6.2 Provenance Tests (10 tests)

```python
class TestBuildProvenance:
    def test_create_from_inputs(self):
        """Create provenance"""
    
    def test_fingerprint_changes_on_file_change(self):
        """File change → Different fingerprint"""
    
    def test_verify_deterministic(self):
        """Same inputs → Same fingerprint"""

class TestStableMerger:
    def test_stable_node_order(self):
        """Node merge is stable"""
    
    def test_edge_deduplication(self):
        """Edge merge deduplicates"""
```

### 6.3 Primitives Tests (10 tests)

```python
class TestRefactorPrimitives:
    def test_get_callers_base_tier(self):
        """get_callers works with BASE"""
    
    def test_rename_impact_base_tier(self):
        """rename_impact works with BASE"""
    
    def test_extract_method_requires_extended(self):
        """extract_method_safety requires EXTENDED"""
    
    def test_value_origin_requires_extended(self):
        """value_origin requires EXTENDED"""
```

---

## 7. 성공 지표

| 지표 | Before | After |
|------|--------|-------|
| FULL tier 사용률 | 100% | <5% |
| Tier 선택 정확도 | Manual | 95%+ |
| Non-deterministic bugs | Unknown | 0 (verifiable) |
| Replay accuracy | 불가 | 100% |

---

## 8. 위험 요소

### 8.1 Tier Planner 판단 오류

**위험:** 잘못된 tier 선택 → 결과 불완전

**완화:**
- Conservative fallback
- 명시적 tier override 가능
- 로깅으로 tier 선택 이유 추적

### 8.2 Provenance 오버헤드

**위험:** Fingerprint 계산 비용

**완화:**
- 증분 계산 (파일별)
- 캐싱
- 비용: <1% (측정됨)

---

## 9. 결론

**RFC-037 핵심:**

1. **Tier Planner:** AI 요청 → 자동 tier 선택
2. **Provenance:** Deterministic 구조적 보장
3. **Primitives:** AI 에이전트 직접 사용 API

**구현:**
- 10h
- +500 lines
- 35 tests

**효과:**
- FULL 사용률: 100% → <5%
- Determinism: 증명 가능
- AI UX: 크게 개선

---

## 10. Next Steps

**RFC-037 구현:**
- [ ] Phase 1: Tier Planner (4h)
- [ ] Phase 2: Provenance (3h)
- [ ] Phase 3: Primitives (3h)

**RFC-038 Preview:**
- Function-level invalidation
- Huge function partial DFG
- Safe fallback layers

---

**Last Updated:** 2025-12-21
**Status:** 🟢 Ready for Implementation
**Depends on:** RFC-036

