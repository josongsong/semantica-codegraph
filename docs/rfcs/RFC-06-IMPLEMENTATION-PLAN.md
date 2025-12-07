# RFC-06 v6 Implementation Plan

**Version:** 1.0  
**Created:** 2025-12-05  
**Owner:** Semantica Core Team  
**Estimated Duration:** 16 weeks (4 months)

---

## Executive Summary

Semantica v6는 기존의 **검색 엔진**에서 **추론 엔진(Reasoning Engine)**으로 진화합니다.

**핵심 가치:**
- LLM Agent가 코드를 **시뮬레이션**하고 **영향도를 예측**할 수 있음
- RAG 토큰 비용 **50% 감소** (Program Slice)
- Hallucination **40% 감소** (Speculative Execution)
- Breaking Change **자동 감지** (Semantic Diff)

---

## Phase 0: Foundation (Week 1-2)

### Goals
- v6 전용 context 생성
- 벤치마크 인프라 구축
- 기존 v5 인프라 재사용 확인

### Deliverables

#### 1. 디렉토리 구조 생성
```
src/contexts/reasoning_engine/
├── __init__.py
├── di.py
├── domain/
│   ├── __init__.py
│   ├── models.py          # ImpactHash, SemanticDiff, SliceResult
│   └── ports.py           # ReasoningEnginePort, SlicerPort
├── infrastructure/
│   ├── impact/
│   │   ├── __init__.py
│   │   ├── symbol_hasher.py     # SignatureHash, BodyHash, ImpactHash
│   │   ├── bloom_filter.py      # Saturation detection
│   │   └── impact_propagator.py # Graph-based propagation
│   ├── speculative/
│   │   ├── __init__.py
│   │   ├── cow_graph.py         # Copy-on-Write Graph
│   │   ├── overlay_manager.py   # Patch stack (LIFO)
│   │   └── error_snapshot.py    # Error Graph handling
│   ├── semantic_diff/
│   │   ├── __init__.py
│   │   ├── differ.py            # Semantic change detection
│   │   └── effect_system.py     # Effect types + propagation
│   ├── slicer/
│   │   ├── __init__.py
│   │   ├── pdg_builder.py       # CFG + DFG → PDG
│   │   ├── slicer.py            # Backward/Forward slice
│   │   ├── budget_manager.py    # Token budget
│   │   └── context_optimizer.py # LLM-friendly output
│   └── cross_lang/              # Phase 4 (Optional)
└── usecase/
    ├── __init__.py
    ├── compute_impact.py
    ├── preview_patch.py
    ├── detect_semantic_change.py
    └── slice_for_llm.py
```

#### 2. 벤치마크 세트 구축
```
benchmark/v6_reasoning/
├── __init__.py
├── impact_accuracy_bench.py      # Impact vs Full rebuild
├── speculative_memory_bench.py   # Memory overhead
├── semantic_diff_accuracy_bench.py # Ground truth 대비
├── slice_quality_bench.py        # Token usage + 정확도
└── golden_set/
    ├── impact_cases.json         # 30개 시나리오
    ├── semantic_changes.json     # 50개 시나리오
    └── slice_cases.json          # 40개 시나리오
```

#### 3. v5 인프라 재사용 확인
- ✅ `code_foundation/infrastructure/graph/impact_analyzer.py` → 기반 활용
- ✅ `code_foundation/infrastructure/semantic_ir/` → CFG/DFG 재사용
- ✅ `analysis_indexing/infrastructure/scope_expander.py` → 영향 전파 로직 참고

### Success Criteria
- [ ] 디렉토리 구조 생성 완료
- [ ] 벤치마크 golden set 30개 이상 수집
- [ ] v5 코드 재사용 가능 확인 (import 테스트)

### Time Budget: 2 weeks

---

## Phase 1: Impact & Semantic Diff (Week 3-6)

### Goals
- Symbol-level Hash 시스템 구축
- Graph 기반 영향 전파
- **Effect System 구현** (RFC-06-EFFECT)
- Semantic Change Detection
- **Storage Layer 구축** (RFC-06-STORAGE)
- **Observability 기반 구축** (RFC-06-OBS)

### 1.1 Symbol Hash System

#### File: `infrastructure/impact/symbol_hasher.py`

```python
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

@dataclass
class SymbolHash:
    """Salsa-style symbol-level hashing"""
    symbol_id: str
    signature_hash: str  # 이름, 파라미터, 반환 타입
    body_hash: str       # 함수 내부 AST
    impact_hash: str     # Signature + callees' signatures
    
    @classmethod
    def compute(cls, node: IRNode, callees: list[IRNode]) -> "SymbolHash":
        """Hash 계산"""
        sig_hash = cls._hash_signature(node)
        body_hash = cls._hash_body(node)
        
        # ImpactHash = H(SignatureHash + callees' SignatureHash)
        callee_sigs = [cls._hash_signature(c) for c in callees]
        impact_hash = sha256(
            (sig_hash + "".join(sorted(callee_sigs))).encode()
        ).hexdigest()
        
        return cls(
            symbol_id=node.id,
            signature_hash=sig_hash,
            body_hash=body_hash,
            impact_hash=impact_hash
        )
    
    @staticmethod
    def _hash_signature(node: IRNode) -> str:
        """Signature 요소만 해싱 (whitespace 무시)"""
        components = [
            node.name,
            "|".join(sorted(p.type_annotation or "Any" for p in node.params)),
            node.return_type or "None",
        ]
        return sha256("|".join(components).encode()).hexdigest()
    
    @staticmethod
    def _hash_body(node: IRNode) -> str:
        """Body AST 해싱 (정규화된 형태)"""
        # AST 순회하며 구조 해싱 (변수명/포맷 무관)
        pass

@dataclass
class ImpactType:
    """변경 영향도 분류"""
    level: Literal["NO_IMPACT", "IR_LOCAL", "SIGNATURE_CHANGE", "STRUCTURAL_CHANGE"]
    affected_symbols: list[str]
    reason: str

class ImpactClassifier:
    """Hash 비교 기반 영향도 분류"""
    
    def classify(self, old: SymbolHash, new: SymbolHash) -> ImpactType:
        """Hash 비교로 영향도 결정"""
        if old.signature_hash != new.signature_hash:
            return ImpactType(
                level="SIGNATURE_CHANGE",
                affected_symbols=[new.symbol_id],
                reason="Signature changed"
            )
        
        if old.body_hash != new.body_hash:
            return ImpactType(
                level="IR_LOCAL",
                affected_symbols=[new.symbol_id],
                reason="Body changed, signature unchanged"
            )
        
        return ImpactType(
            level="NO_IMPACT",
            affected_symbols=[],
            reason="No change"
        )
```

#### File: `infrastructure/impact/bloom_filter.py`

```python
from bitarray import bitarray
import mmh3

class SaturationAwareBloomFilter:
    """Saturation detection 포함 Bloom Filter"""
    
    def __init__(self, expected_items: int = 10000, fp_rate: float = 0.01):
        self.size = self._optimal_size(expected_items, fp_rate)
        self.hash_count = self._optimal_hash_count(self.size, expected_items)
        self.bits = bitarray(self.size)
        self.bits.setall(0)
        
        self.added_count = 0
        self.query_count = 0
        self.positive_count = 0
    
    def add(self, item: str):
        """Item 추가"""
        for i in range(self.hash_count):
            index = mmh3.hash(item, i) % self.size
            self.bits[index] = 1
        self.added_count += 1
    
    def contains(self, item: str) -> bool:
        """Item 포함 여부 (FP 가능)"""
        self.query_count += 1
        result = all(
            self.bits[mmh3.hash(item, i) % self.size]
            for i in range(self.hash_count)
        )
        if result:
            self.positive_count += 1
        return result
    
    def check_saturation(self) -> tuple[bool, float]:
        """Saturation 감지"""
        if self.query_count < 100:
            return False, 0.0
        
        fp_ratio = self.positive_count / self.query_count
        is_saturated = fp_ratio > 0.3  # 30% 임계값
        
        return is_saturated, fp_ratio
    
    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        """최적 비트 배열 크기"""
        import math
        return int(-(n * math.log(p)) / (math.log(2) ** 2))
    
    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        """최적 해시 함수 개수"""
        import math
        return max(1, int((m / n) * math.log(2)))
```

#### File: `infrastructure/impact/impact_propagator.py`

```python
from collections import deque
from typing import Set, Dict

class GraphBasedImpactPropagator:
    """Call/Import Graph 기반 영향 전파"""
    
    def propagate(
        self,
        changed_symbols: Set[str],
        impact_types: Dict[str, ImpactType],
        graph: GraphDocument,
        max_depth: int = 5
    ) -> Set[str]:
        """영향 받는 심볼 집합 계산"""
        
        affected = set(changed_symbols)
        queue = deque([(sym, 0) for sym in changed_symbols])
        
        while queue:
            symbol_id, depth = queue.popleft()
            
            if depth >= max_depth:
                continue
            
            impact = impact_types.get(symbol_id)
            if not impact:
                continue
            
            # SIGNATURE_CHANGE만 caller로 전파
            if impact.level == "SIGNATURE_CHANGE":
                callers = self._find_callers(symbol_id, graph)
                for caller in callers:
                    if caller not in affected:
                        affected.add(caller)
                        queue.append((caller, depth + 1))
            
            # STRUCTURAL_CHANGE는 importer로 전파
            if impact.level == "STRUCTURAL_CHANGE":
                importers = self._find_importers(symbol_id, graph)
                for importer in importers:
                    if importer not in affected:
                        affected.add(importer)
                        queue.append((importer, depth + 1))
        
        return affected
    
    def _find_callers(self, symbol_id: str, graph: GraphDocument) -> list[str]:
        """Reverse CALLS edge"""
        return [
            edge.source_node_id
            for edge in graph.edges
            if edge.kind == "CALLS" and edge.target_node_id == symbol_id
        ]
    
    def _find_importers(self, symbol_id: str, graph: GraphDocument) -> list[str]:
        """Reverse IMPORTS edge"""
        return [
            edge.source_node_id
            for edge in graph.edges
            if edge.kind == "IMPORTS" and edge.target_node_id == symbol_id
        ]
```

### 1.2 Semantic Change Detection

#### File: `infrastructure/semantic_diff/effect_system.py`

```python
from enum import Enum
from dataclasses import dataclass

class EffectType(str, Enum):
    """Effect 분류"""
    PURE = "pure"
    READ_STATE = "read_state"
    WRITE_STATE = "write_state"
    GLOBAL_MUTATION = "global_mutation"
    IO = "io"
    DB = "db"
    NETWORK = "network"
    UNKNOWN_EFFECT = "unknown_effect"

@dataclass
class EffectSet:
    """함수의 effect 집합"""
    symbol_id: str
    local_effects: set[EffectType]
    propagated_effects: set[EffectType]
    
    @property
    def total_effects(self) -> set[EffectType]:
        return self.local_effects | self.propagated_effects
    
    def is_pure(self) -> bool:
        return self.total_effects == {EffectType.PURE}

class EffectAnalyzer:
    """Effect 추론 엔진"""
    
    def analyze_function(
        self,
        node: IRNode,
        graph: GraphDocument,
        callee_effects: dict[str, EffectSet]
    ) -> EffectSet:
        """함수의 effect 계산"""
        
        local_effects = self._analyze_local_effects(node)
        
        # Callee effect propagation
        propagated = set()
        for edge in graph.edges:
            if edge.kind == "CALLS" and edge.source_node_id == node.id:
                callee_id = edge.target_node_id
                
                # Unknown call → 보수적 정책
                if callee_id not in callee_effects:
                    propagated.add(EffectType.WRITE_STATE)
                    propagated.add(EffectType.GLOBAL_MUTATION)
                else:
                    propagated.update(callee_effects[callee_id].total_effects)
        
        return EffectSet(
            symbol_id=node.id,
            local_effects=local_effects,
            propagated_effects=propagated
        )
    
    def _analyze_local_effects(self, node: IRNode) -> set[EffectType]:
        """Local effect 감지"""
        effects = set()
        
        # AST 순회하며 effect 감지
        for stmt in node.body:
            if self._is_io_operation(stmt):
                effects.add(EffectType.IO)
            elif self._is_global_mutation(stmt):
                effects.add(EffectType.GLOBAL_MUTATION)
            # ... 더 많은 휴리스틱
        
        return effects or {EffectType.PURE}
    
    def _is_io_operation(self, stmt) -> bool:
        """IO 감지 (print, open, write 등)"""
        pass
    
    def _is_global_mutation(self, stmt) -> bool:
        """Global 변수 수정 감지"""
        pass
```

#### File: `infrastructure/semantic_diff/differ.py`

```python
@dataclass
class SemanticDiff:
    """의미적 변화 감지 결과"""
    signature_changes: list[str]
    call_graph_changes: dict[str, list[str]]  # added/removed calls
    effect_changes: dict[str, tuple[EffectSet, EffectSet]]  # old → new
    reachable_set_changes: dict[str, set[str]]
    
    is_pure_refactoring: bool
    confidence: float
    reason: str

class SemanticDiffer:
    """동작 변화 vs 리팩토링 구분"""
    
    def __init__(self, effect_analyzer: EffectAnalyzer):
        self.effect_analyzer = effect_analyzer
    
    def detect_behavior_change(
        self,
        old_ir: IRDocument,
        new_ir: IRDocument,
        old_graph: GraphDocument,
        new_graph: GraphDocument
    ) -> SemanticDiff:
        """의미적 변화 감지"""
        
        # 1. Signature 변화
        sig_changes = self._compare_signatures(old_ir, new_ir)
        
        # 2. Call graph 변화
        call_changes = self._compare_call_edges(old_graph, new_graph)
        
        # 3. Effect 변화
        old_effects = self._compute_effects(old_ir, old_graph)
        new_effects = self._compute_effects(new_ir, new_graph)
        effect_changes = self._compare_effects(old_effects, new_effects)
        
        # 4. Reachable set 변화 (특정 엔트리포인트 기준)
        reachable_changes = self._compare_reachable_sets(old_graph, new_graph)
        
        # 5. 순수 리팩토링 판정
        is_refactoring = (
            len(sig_changes) == 0 and
            len(effect_changes) == 0 and
            self._is_minimal_call_change(call_changes)
        )
        
        confidence = self._calculate_confidence(
            sig_changes, call_changes, effect_changes
        )
        
        return SemanticDiff(
            signature_changes=sig_changes,
            call_graph_changes=call_changes,
            effect_changes=effect_changes,
            reachable_set_changes=reachable_changes,
            is_pure_refactoring=is_refactoring,
            confidence=confidence,
            reason=self._explain_changes(sig_changes, effect_changes)
        )
    
    def _compare_call_edges(
        self,
        old_graph: GraphDocument,
        new_graph: GraphDocument
    ) -> dict[str, list[str]]:
        """Call graph diff"""
        old_calls = {
            (e.source_node_id, e.target_node_id)
            for e in old_graph.edges if e.kind == "CALLS"
        }
        new_calls = {
            (e.source_node_id, e.target_node_id)
            for e in new_graph.edges if e.kind == "CALLS"
        }
        
        return {
            "added": list(new_calls - old_calls),
            "removed": list(old_calls - new_calls)
        }
    
    def _compare_effects(
        self,
        old: dict[str, EffectSet],
        new: dict[str, EffectSet]
    ) -> dict[str, tuple[EffectSet, EffectSet]]:
        """Effect 변화"""
        changes = {}
        for symbol_id in old.keys() & new.keys():
            old_effect = old[symbol_id]
            new_effect = new[symbol_id]
            if old_effect.total_effects != new_effect.total_effects:
                changes[symbol_id] = (old_effect, new_effect)
        return changes
```

### Success Criteria (Phase 1)
- [ ] Symbol Hash가 full rebuild와 100% 동치성 검증
- [ ] Bloom Filter saturation 감지 동작 확인
- [ ] Semantic Diff가 ground truth 대비 85%+ 정확도
- [ ] Effect System이 30개 케이스에서 올바른 effect 추론

### Time Budget: 4 weeks

---

## Phase 2: Speculative Core (Week 7-10)

### Goals
- Copy-on-Write Graph 구현
- Patch Stack (LIFO) 관리
- Error Graph Snapshot

### 2.1 CoW Graph

#### File: `infrastructure/speculative/cow_graph.py`

```python
from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy

@dataclass
class DeltaLayer:
    """변경된 nodes/edges만 관리"""
    patch_id: str
    added_nodes: dict[str, GraphNode] = field(default_factory=dict)
    removed_node_ids: set[str] = field(default_factory=set)
    added_edges: list[GraphEdge] = field(default_factory=list)
    removed_edge_ids: set[str] = field(default_factory=set)
    
    def apply_to_view(self, base: GraphDocument) -> GraphDocument:
        """Base + delta로 view 생성"""
        view_nodes = {n.id: n for n in base.nodes if n.id not in self.removed_node_ids}
        view_nodes.update(self.added_nodes)
        
        view_edges = [
            e for e in base.edges
            if e.id not in self.removed_edge_ids
        ]
        view_edges.extend(self.added_edges)
        
        return GraphDocument(
            repo_id=base.repo_id,
            snapshot_id=f"{base.snapshot_id}+{self.patch_id}",
            nodes=list(view_nodes.values()),
            edges=view_edges
        )

class CowGraphStore:
    """Immutable base + delta overlay"""
    
    def __init__(self, base: GraphDocument):
        self.base = base  # immutable
        self.overlays: dict[str, DeltaLayer] = {}
    
    def create_overlay(self, patch_id: str) -> DeltaLayer:
        """새 overlay 생성"""
        delta = DeltaLayer(patch_id=patch_id)
        self.overlays[patch_id] = delta
        return delta
    
    def get_view(self, patch_id: str) -> GraphDocument:
        """Base + delta 뷰 생성"""
        if patch_id not in self.overlays:
            return self.base
        
        delta = self.overlays[patch_id]
        return delta.apply_to_view(self.base)
    
    def commit_overlay(self, patch_id: str) -> GraphDocument:
        """Overlay를 새 base로 승격"""
        view = self.get_view(patch_id)
        self.base = view
        del self.overlays[patch_id]
        return self.base
    
    def rollback_overlay(self, patch_id: str):
        """Overlay 삭제 (LIFO만 지원)"""
        if patch_id in self.overlays:
            del self.overlays[patch_id]
```

### 2.2 Overlay Manager (LIFO Patch Stack)

#### File: `infrastructure/speculative/overlay_manager.py`

```python
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

@dataclass
class PatchMetadata:
    """패치 메타데이터"""
    patch_id: str
    description: str
    timestamp: float
    files_changed: list[str]
    symbols_changed: list[str]

class OverlayManager:
    """Patch Stack (LIFO) 관리"""
    
    def __init__(self, cow_store: CowGraphStore, max_overlays: int = 10):
        self.cow_store = cow_store
        self.max_overlays = max_overlays
        self.patch_stack: OrderedDict[str, PatchMetadata] = OrderedDict()
    
    def apply_patch(
        self,
        patch: str,
        description: str
    ) -> tuple[str, Optional[GraphDocument]]:
        """패치 적용 (새 overlay 생성)"""
        import time
        import uuid
        
        patch_id = f"patch_{uuid.uuid4().hex[:8]}"
        
        # LRU eviction
        if len(self.patch_stack) >= self.max_overlays:
            oldest_id = next(iter(self.patch_stack))
            self._evict_overlay(oldest_id)
        
        # 1. Overlay 생성
        delta = self.cow_store.create_overlay(patch_id)
        
        # 2. Patch 적용
        try:
            files_changed, symbols_changed = self._apply_patch_to_delta(
                patch, delta
            )
            
            # 3. 메타데이터 저장
            self.patch_stack[patch_id] = PatchMetadata(
                patch_id=patch_id,
                description=description,
                timestamp=time.time(),
                files_changed=files_changed,
                symbols_changed=symbols_changed
            )
            
            # 4. View 반환
            view = self.cow_store.get_view(patch_id)
            return patch_id, view
            
        except Exception as e:
            # Error snapshot
            return patch_id, self._create_error_snapshot(patch_id, e)
    
    def rollback_patch(self, patch_id: str) -> bool:
        """패치 롤백 (LIFO만 지원)"""
        if patch_id not in self.patch_stack:
            return False
        
        # LIFO 체크
        if patch_id != list(self.patch_stack.keys())[-1]:
            # Non-LIFO rollback → 재적용 필요
            return self._rebuild_without_patch(patch_id)
        
        # LIFO rollback
        self.cow_store.rollback_overlay(patch_id)
        del self.patch_stack[patch_id]
        return True
    
    def _rebuild_without_patch(self, target_patch_id: str) -> bool:
        """Non-LIFO rollback: 패치 재적용"""
        # Cost: O(k) where k = patches after target
        remaining_patches = [
            (pid, meta) for pid, meta in self.patch_stack.items()
            if pid != target_patch_id
        ]
        
        # 모든 overlay 제거
        self.cow_store.overlays.clear()
        self.patch_stack.clear()
        
        # 재적용
        for pid, meta in remaining_patches:
            # ... 패치 재적용
            pass
        
        return True
    
    def _apply_patch_to_delta(
        self,
        patch: str,
        delta: DeltaLayer
    ) -> tuple[list[str], list[str]]:
        """실제 패치 적용 로직"""
        # 1. 패치 파싱
        # 2. 변경된 파일 IR 재생성
        # 3. delta에 추가/삭제 기록
        pass
    
    def _create_error_snapshot(self, patch_id: str, error: Exception):
        """에러 스냅샷 생성"""
        from .error_snapshot import ErrorGraphSnapshot
        return ErrorGraphSnapshot(
            patch_id=patch_id,
            error_type=type(error).__name__,
            error_message=str(error),
            partial_graph=None  # 부분 성공 시 partial graph
        )
    
    def _evict_overlay(self, patch_id: str):
        """LRU eviction"""
        self.cow_store.rollback_overlay(patch_id)
        del self.patch_stack[patch_id]
```

### 2.3 Error Graph Snapshot

#### File: `infrastructure/speculative/error_snapshot.py`

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ErrorGraphSnapshot:
    """Speculative 실패 시 에러 스냅샷"""
    patch_id: str
    error_type: str  # "SyntaxError" | "TypeError" | "IRGenerationError"
    error_message: str
    partial_graph: Optional[GraphDocument]
    
    def to_llm_feedback(self) -> str:
        """LLM에게 전달할 피드백"""
        return f"""
패치 적용 실패 (patch_id: {self.patch_id})

에러 타입: {self.error_type}
에러 메시지: {self.error_message}

제안:
1. Syntax 에러인 경우 → 패치 재작성 필요
2. Type 에러인 경우 → 타입 어노테이션 확인
3. IR 생성 실패 → 파일 구조 확인
"""
```

### Success Criteria (Phase 2)
- [ ] CoW Graph 메모리 오버헤드 < 2x base
- [ ] Overlay 생성 latency < 100ms
- [ ] LIFO rollback 정상 동작
- [ ] Non-LIFO rollback O(k) 비용 검증
- [ ] Error snapshot이 LLM에게 유용한 피드백 제공

### Time Budget: 4 weeks

---

## Phase 3: Reasoning Engine (Week 11-16)

### Goals
- Program Slice (Backward + Forward)
- PDG Builder (CFG + DFG → PDG)
- LLM Context Optimizer

### 3.1 PDG Builder

#### File: `infrastructure/slicer/pdg_builder.py`

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class PdgEdge:
    """Program Dependence Graph edge"""
    source_id: str
    target_id: str
    kind: Literal["control", "data"]
    label: str  # "TRUE_BRANCH" | "READ x" | "WRITE y"

@dataclass
class ProgramDependenceGraph:
    """PDG = CFG + DFG"""
    function_id: str
    nodes: list[str]  # Block IDs or Variable IDs
    edges: list[PdgEdge]
    
    def get_dependencies(self, node_id: str, kind: str = "both") -> list[str]:
        """의존성 조회"""
        deps = []
        for edge in self.edges:
            if edge.target_id == node_id:
                if kind == "both" or edge.kind == kind:
                    deps.append(edge.source_id)
        return deps

class PdgBuilder:
    """CFG + DFG → PDG"""
    
    def build_pdg(
        self,
        cfg: ControlFlowGraph,
        dfg: DfgSnapshot
    ) -> ProgramDependenceGraph:
        """PDG 생성"""
        
        pdg_edges = []
        
        # 1. Control Dependency (CFG 기반)
        pdg_edges.extend(self._extract_control_deps(cfg))
        
        # 2. Data Dependency (DFG 기반)
        pdg_edges.extend(self._extract_data_deps(dfg))
        
        return ProgramDependenceGraph(
            function_id=cfg.function_node_id,
            nodes=self._collect_all_nodes(cfg, dfg),
            edges=pdg_edges
        )
    
    def _extract_control_deps(self, cfg: ControlFlowGraph) -> list[PdgEdge]:
        """Control dependency 추출"""
        control_edges = []
        
        for edge in cfg.edges:
            if edge.kind in ("TRUE_BRANCH", "FALSE_BRANCH", "LOOP_BACK"):
                control_edges.append(PdgEdge(
                    source_id=edge.source_block_id,
                    target_id=edge.target_block_id,
                    kind="control",
                    label=edge.kind
                ))
        
        return control_edges
    
    def _extract_data_deps(self, dfg: DfgSnapshot) -> list[PdgEdge]:
        """Data dependency 추출"""
        data_edges = []
        
        for edge in dfg.edges:
            data_edges.append(PdgEdge(
                source_id=edge.from_variable_id,
                target_id=edge.to_variable_id,
                kind="data",
                label=edge.kind  # "alias" | "assign" | "return_value"
            ))
        
        return data_edges
    
    def _collect_all_nodes(
        self,
        cfg: ControlFlowGraph,
        dfg: DfgSnapshot
    ) -> list[str]:
        """PDG 노드 수집 (Block + Variable)"""
        nodes = set()
        
        # Blocks from CFG
        nodes.update(b.id for b in cfg.blocks)
        
        # Variables from DFG
        nodes.update(v.id for v in dfg.variables)
        
        return list(nodes)
```

### 3.2 Program Slicer

#### File: `infrastructure/slicer/slicer.py`

```python
from collections import deque
from dataclasses import dataclass

@dataclass
class SliceResult:
    """Slice 결과"""
    target_variable: str
    slice_nodes: list[str]  # Block IDs, Variable IDs
    code_fragments: list[tuple[str, int, int]]  # (file, start_line, end_line)
    control_context: list[str]  # Control 의존성 설명
    total_tokens: int
    
    def to_llm_context(self) -> str:
        """LLM-friendly 컨텍스트"""
        pass

class ProgramSlicer:
    """Weiser slicing 알고리즘"""
    
    def __init__(self, pdg_builder: PdgBuilder):
        self.pdg_builder = pdg_builder
    
    def backward_slice(
        self,
        pdg: ProgramDependenceGraph,
        target_var: str,
        max_depth: int = 10
    ) -> SliceResult:
        """이 변수의 값이 어떻게 형성되었는지 추적"""
        
        visited = set()
        slice_nodes = []
        
        queue = deque([(target_var, 0)])
        
        while queue:
            node_id, depth = queue.popleft()
            
            if depth > max_depth or node_id in visited:
                continue
            
            visited.add(node_id)
            slice_nodes.append(node_id)
            
            # Data + Control dependencies
            deps = pdg.get_dependencies(node_id, kind="both")
            for dep in deps:
                queue.append((dep, depth + 1))
        
        # LLM-friendly 코드 추출
        code_fragments, control_ctx = self._extract_code_fragments(
            slice_nodes, pdg
        )
        
        return SliceResult(
            target_variable=target_var,
            slice_nodes=slice_nodes,
            code_fragments=code_fragments,
            control_context=control_ctx,
            total_tokens=self._estimate_tokens(code_fragments)
        )
    
    def forward_slice(
        self,
        pdg: ProgramDependenceGraph,
        source_var: str,
        max_depth: int = 10
    ) -> SliceResult:
        """이 변수가 영향을 미치는 후속 코드"""
        # Backward와 반대 방향
        pass
    
    def _extract_code_fragments(
        self,
        slice_nodes: list[str],
        pdg: ProgramDependenceGraph
    ) -> tuple[list[tuple[str, int, int]], list[str]]:
        """최소 코드 + Control context"""
        # 1. Slice nodes → IR nodes 매핑
        # 2. Span 정보로 코드 조각 추출
        # 3. Control dependency → 설명 문자열 생성
        pass
    
    def _estimate_tokens(self, fragments: list) -> int:
        """토큰 수 추정"""
        # 간단한 휴리스틱: chars / 4
        total_chars = sum(
            len(code) for code, _, _ in fragments
        )
        return total_chars // 4
```

### 3.3 Budget Manager

#### File: `infrastructure/slicer/budget_manager.py`

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class BudgetConfig:
    """Token budget 설정"""
    max_tokens: int = 8000
    min_tokens: int = 500
    summarization_threshold: int = 200  # 함수 크기
    
@dataclass
class RelevanceScore:
    """Node 중요도"""
    node_id: str
    score: float
    reason: Literal["distance", "effect", "recentness", "hotspot"]

class BudgetManager:
    """Token budget 관리"""
    
    def __init__(self, config: BudgetConfig):
        self.config = config
    
    def apply_budget(
        self,
        slice_result: SliceResult,
        relevance_scores: list[RelevanceScore]
    ) -> SliceResult:
        """Budget 초과 시 pruning"""
        
        if slice_result.total_tokens <= self.config.max_tokens:
            return slice_result
        
        # 1. Relevance score 정렬
        sorted_nodes = sorted(
            relevance_scores,
            key=lambda x: x.score,
            reverse=True
        )
        
        # 2. Top-k nodes 선택 (budget 내)
        selected_nodes = []
        current_tokens = 0
        
        for score in sorted_nodes:
            node_tokens = self._estimate_node_tokens(score.node_id)
            
            if current_tokens + node_tokens > self.config.max_tokens:
                break
            
            selected_nodes.append(score.node_id)
            current_tokens += node_tokens
        
        # 3. Filtered slice 생성
        return self._filter_slice(slice_result, selected_nodes)
    
    def compute_relevance(
        self,
        slice_nodes: list[str],
        pdg: ProgramDependenceGraph,
        target_var: str
    ) -> list[RelevanceScore]:
        """Relevance score 계산"""
        scores = []
        
        for node_id in slice_nodes:
            # 거리 기반
            distance = self._pdg_distance(target_var, node_id, pdg)
            
            # Effect 기반 (IO/DB 연산 우선)
            effect_boost = self._has_important_effect(node_id)
            
            # Recentness (최근 수정된 코드 우선)
            recency_boost = self._recency_score(node_id)
            
            total_score = (1.0 / (distance + 1)) + effect_boost + recency_boost
            
            scores.append(RelevanceScore(
                node_id=node_id,
                score=total_score,
                reason="distance" if distance < 3 else "effect"
            ))
        
        return scores
    
    def _has_important_effect(self, node_id: str) -> float:
        """중요한 effect 감지 (IO, DB 등)"""
        # Effect system과 연동
        pass
```

### 3.4 Context Optimizer (LLM-friendly output)

#### File: `infrastructure/slicer/context_optimizer.py`

```python
from dataclasses import dataclass

@dataclass
class OptimizedContext:
    """LLM에게 전달할 최적화된 컨텍스트"""
    summary: str
    essential_code: str
    control_flow_explanation: str
    variable_history: str
    total_tokens: int

class ContextOptimizer:
    """Minimum Viable Context 생성"""
    
    def optimize_for_llm(
        self,
        slice_result: SliceResult,
        ir_docs: dict[str, IRDocument]
    ) -> OptimizedContext:
        """LLM-friendly 컨텍스트 생성"""
        
        # 1. Syntax integrity 보장
        code_blocks = self._ensure_syntax_integrity(
            slice_result.code_fragments,
            ir_docs
        )
        
        # 2. Import 최소화
        essential_imports = self._extract_essential_imports(code_blocks)
        
        # 3. Summary 생성 (큰 함수는 signature만)
        summary = self._generate_summary(code_blocks)
        
        # 4. Control flow 설명
        control_explanation = self._explain_control_flow(
            slice_result.control_context
        )
        
        # 5. Variable history 추적
        var_history = self._trace_variable_history(slice_result)
        
        # 6. 최종 조합
        essential_code = self._assemble_code(
            essential_imports,
            code_blocks
        )
        
        return OptimizedContext(
            summary=summary,
            essential_code=essential_code,
            control_flow_explanation=control_explanation,
            variable_history=var_history,
            total_tokens=self._count_tokens(essential_code + control_explanation)
        )
    
    def _ensure_syntax_integrity(
        self,
        fragments: list[tuple[str, int, int]],
        ir_docs: dict[str, IRDocument]
    ) -> list[str]:
        """Syntax integrity 보장"""
        
        complete_blocks = []
        
        for file_path, start_line, end_line in fragments:
            # 1. IR에서 해당 노드 찾기
            node = self._find_node_by_span(file_path, start_line, end_line, ir_docs)
            
            if not node:
                continue
            
            # 2. 완전한 블록 추출
            if node.kind in ("FUNCTION", "METHOD"):
                # Signature + body 전체 (또는 summary)
                if self._is_too_large(node):
                    complete_blocks.append(self._summarize_function(node))
                else:
                    complete_blocks.append(self._extract_full_function(node))
            
            elif node.kind == "CLASS":
                # Class signature + 관련 메서드만
                complete_blocks.append(self._extract_class_partial(node))
        
        return complete_blocks
    
    def _is_too_large(self, node: IRNode, threshold: int = 200) -> bool:
        """함수가 너무 큰지 확인"""
        if not node.span:
            return False
        return (node.span.end_line - node.span.start_line) > threshold
    
    def _summarize_function(self, node: IRNode) -> str:
        """큰 함수는 signature + docstring만"""
        return f"""
def {node.name}({self._format_params(node.params)}) -> {node.return_type or 'None'}:
    \"\"\"
    {node.docstring or '(no docstring)'}
    \"\"\"
    # ... (function body omitted, {self._count_lines(node)} lines)
"""
    
    def _explain_control_flow(self, control_ctx: list[str]) -> str:
        """Control dependency 설명"""
        if not control_ctx:
            return "No special control flow."
        
        return "Control flow:\n" + "\n".join(
            f"- {ctx}" for ctx in control_ctx
        )
    
    def _trace_variable_history(self, slice_result: SliceResult) -> str:
        """Variable 생성 경로 추적"""
        # DFG edge를 따라가며 "x는 y로부터 계산됨" 형태로 설명
        pass
```

### Success Criteria (Phase 3)
- [ ] PDG Builder가 CFG/DFG 올바르게 결합
- [ ] Backward/Forward slice 정확도 90%+
- [ ] Token budget 준수율 100%
- [ ] Syntax integrity 100% (incomplete fragment 없음)
- [ ] Agent 답변 정확도 +30% (baseline 대비)

### Time Budget: 6 weeks

---

## Phase 4 (Optional): Cross-Language (Week 17+)

### Goals
- Boundary-first 전략
- Schema normalization
- Cross-language edge 생성

**우선순위:** Low (MSA 고객 확보 후 시작)

**구현 전략:**
1. OpenAPI/gRPC spec parser 구현
2. Boundary node 생성
3. 각 언어 그래프에서 boundary 연결점 찾기
4. Cross-language edge 추가

**예상 기간:** 6개월+

---

## Testing Strategy

### 1. Unit Tests
```
tests/v6/
├── test_symbol_hasher.py          # Hash 계산 정확도
├── test_bloom_filter.py           # Saturation detection
├── test_impact_propagator.py     # Graph 기반 전파
├── test_effect_analyzer.py        # Effect 추론
├── test_semantic_differ.py        # 동작 변화 감지
├── test_cow_graph.py              # CoW 메모리, 동치성
├── test_overlay_manager.py        # LIFO rollback
├── test_pdg_builder.py            # CFG+DFG 결합
├── test_slicer.py                 # Slice 정확도
└── test_context_optimizer.py      # Syntax integrity
```

### 2. Integration Tests
```
tests/v6/integration/
├── test_end_to_end_impact.py      # 전체 파이프라인
├── test_speculative_agent.py      # Agent 통합
├── test_slice_for_llm.py          # LLM 컨텍스트
└── test_performance_regression.py # 성능 회귀
```

### 3. Benchmark Suite
```
benchmark/v6_reasoning/
├── impact_accuracy_bench.py       # Full rebuild 동치성
├── speculative_memory_bench.py    # 메모리 오버헤드
├── semantic_diff_accuracy_bench.py # Ground truth 정확도
└── slice_quality_bench.py         # Token 사용 + 정확도
```

---

## Success Metrics (Overall)

| Metric | Baseline (v5) | Target (v6) | Measured By |
|--------|--------------|-------------|-------------|
| Incremental Rebuild Speed | 192x | 300x+ | impact_accuracy_bench.py |
| RAG Token Usage | 100% | 50% | slice_quality_bench.py |
| LLM Hallucination Rate | baseline | -40% | Agent evaluation |
| Patch Safety Score | N/A | 95% | Speculative preview accuracy |
| Breaking Change Detection | N/A | 90% | semantic_diff_accuracy_bench.py |
| Memory Overhead (Speculative) | N/A | < 2x | speculative_memory_bench.py |

---

## Risk Mitigation

### Risk 1: Speculative Execution 메모리 폭발
**Mitigation:**
- Max 10 overlays (LRU eviction)
- 메모리 사용량 모니터링
- 임계값 초과 시 자동 eviction

### Risk 2: Semantic Diff False Positive
**Mitigation:**
- Conservative 전략 (의심스러우면 behavior change)
- Confidence score 제공
- Ground truth 기반 지속적 개선

### Risk 3: Program Slice 정확도
**Mitigation:**
- Golden set 40개 이상 수집
- PDG 정확도 먼저 검증
- Slice 결과를 사람이 review

### Risk 4: v5 유지보수 부담
**Mitigation:**
- v6를 별도 context로 격리
- v5 코드 최대한 재사용
- v6는 v5 위에 thin layer

---

## Deliverables Summary

### Phase 0 (Week 1-2)
- [x] 디렉토리 구조
- [x] 벤치마크 golden set 30+
- [x] v5 재사용 확인

### Phase 1 (Week 3-6)
- [x] Symbol Hash System
- [x] Bloom Filter + Saturation
- [x] Impact Propagator
- [x] Effect System
- [x] Semantic Differ

### Phase 2 (Week 7-10)
- [x] CoW Graph
- [x] Overlay Manager (LIFO)
- [x] Error Snapshot

### Phase 3 (Week 11-16)
- [x] PDG Builder
- [x] Program Slicer
- [x] Budget Manager
- [x] Context Optimizer

### Phase 4 (Optional, Week 17+)
- [ ] Cross-Language (MSA 고객 확보 후)

---

## Next Steps

1. **RFC 승인** (이번 주)
2. **Golden Set 수집** (1주)
3. **Phase 0 시작** (2주)
4. **Weekly 체크인** (매주 금요일)

---

**End of Implementation Plan**

