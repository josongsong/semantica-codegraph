# RFC-028: Critical Analysis Gaps (Cost, Concurrency, Differential)
**Status**: DRAFT
**Priority**: P0 (Critical)
**Timeline**: 6-8주
**Owner**: Static Analysis Team

---

## 1. Executive Summary

현재 Semantica v2는 **Heap/Taint 분석은 Infer급**이지만, **Cost/Concurrency/Differential Analysis가 부재**하여 실용성이 크게 제한됩니다.

### 1.1 RFC-027 연동 (병행 작업)

**본 RFC는 RFC-027과 병행 작업 가능합니다.**

- ✅ **Evidence 스키마 확정 완료** (`src/agent/domain/rfc_specs/evidence.py`)
- ✅ **Claim 스키마 확정 완료** (`src/agent/domain/rfc_specs/claim.py`)
- ✅ **Mapping 테이블 확정** (`src/agent/adapters/rfc/mappings.py`)
- ✅ **병행 작업 시뮬레이션 성공**

**참고 문서**: `_docs/_backlog/RFC-027-028-PARALLEL-WORK-PLAN.md`

### 현재 상황
```
✅ Null Safety:        95% (Infer 근접)
✅ Heap Analysis:      90% (Sep Logic, Bi-abduction)
✅ Taint Analysis:     95% (Interprocedural, context-sensitive)
✅ Semantic Diff:      70% (기본 구현 있음)

⚠️  Cost Analysis:      40% (Core 일부, complexity term/evidence/diff 미완)
⚠️  Concurrency:        30% (Prototype 룰, alias/escape/await 모델 표준화 미완)
⚠️  Differential:       50% (Semantic diff 있음, taint/cost/breaking 종합 diff 미완)
```

### 비즈니스 임팩트

**Without Cost Analysis**:
- ❌ IDE에서 "이 루프는 느림" 실시간 경고 불가
- ❌ PR 리뷰에서 성능 회귀 자동 탐지 불가
- ❌ 대량 데이터 처리 시 timeout 예측 불가

**Without Concurrency Analysis**:
- ❌ Python async 코드의 race condition 탐지 불가
- ❌ FastAPI/Django async view의 공유 변수 접근 경고 불가
- ❌ 프로덕션 data race 사전 방지 불가

**Without Differential Analysis**:
- ❌ PR에서 "Sanitizer 제거됨" 자동 경고 불가
- ❌ "O(n) → O(n²) 회귀" 자동 탐지 불가
- ❌ Breaking change 자동 감지 불가

---

## 2. Architecture Overview

### 2.1 현재 인프라 (재사용 가능)

```
✅ SCCP Engine          — src/contexts/code_foundation/infrastructure/dfg/constant/
✅ SSA Builder          — src/contexts/code_foundation/infrastructure/dfg/ssa/
✅ CFG Builder          — src/contexts/code_foundation/infrastructure/semantic_ir/cfg/
✅ Call Graph           — src/contexts/code_foundation/infrastructure/graphs/
✅ Query Engine         — src/contexts/code_foundation/infrastructure/query/
✅ Semantic Differ      — src/contexts/reasoning_engine/infrastructure/semantic_diff/
✅ Impact Analyzer      — src/contexts/reasoning_engine/infrastructure/impact/
```

**핵심**: 기반은 완벽. 위에 Cost/Concurrency/Differential만 추가하면 됨.

### 2.2 목표 아키텍처

```
┌─────────────────────────────────────────┐
│  New Analysis Layers (RFC-028)         │
│  ┌──────────────────────────────────┐  │
│  │ CostAnalyzer                      │  │ ← 추가
│  │ ConcurrencyAnalyzer              │  │ ← 추가
│  │ DifferentialAnalyzer             │  │ ← 강화
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
              ↓ uses
┌─────────────────────────────────────────┐
│  Existing Infrastructure (Reuse)        │
│  - SCCP, SSA, CFG                       │ ← 재사용
│  - Call Graph, Query Engine             │ ← 재사용
│  - Semantic Differ                      │ ← 확장
└─────────────────────────────────────────┘
```

---

## 3. Common Evidence Schema (필수) ⭐ — LOCKED

**✅ Evidence 스키마 확정 완료** (RFC-027 + RFC-028 통합)

**위치**: `src/agent/domain/rfc_specs/evidence.py` (구현 완료, 테스트 통과)

**모든 Analyzer는 공통 증거 형식을 반환해야 함** (RFC-027 연동)

### 3.1 Base Result Schema (RFC-028 출력 형식)

**팀 A (RFC-028)가 반환할 형식** (팀 B가 이것을 받아서 ResultEnvelope로 변환):

```python
from src.agent.domain.rfc_specs import Evidence, Claim, ConfidenceBasis
from typing import Literal

@dataclass
class AnalysisResult:
    """
    공통 분석 결과 (모든 Analyzer 반환)

    팀 A → 팀 B Interface Contract:
    - verdict: "proven"/"likely"/"heuristic" (문자열)
    - evidence: Evidence 스키마 준수 (팀 공통)
    - 팀 B가 verdict → ConfidenceBasis 변환
    """

    # Verdict (팀 B가 ConfidenceBasis로 변환)
    verdict: Literal["proven", "likely", "heuristic"]
    confidence: float  # 0.0-1.0

    # Evidence (RFC-027 스키마 준수!) ⭐
    evidence: Evidence  # ← src/agent/domain/rfc_specs/evidence.py

    # Explanation (human-readable)
    explanation: str  # 1줄 요약

    # Analysis-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)
```

**변환 흐름**:
```python
# 팀 A: Analysis 결과
result = CostResult(
    verdict="proven",  # ← 문자열
    evidence=Evidence(...)  # ← 스키마 준수
)

# 팀 B: ResultEnvelope로 변환
claim = Claim(
    confidence_basis=VERDICT_TO_CONFIDENCE_BASIS[result.verdict],  # ← 매핑
    ...
)
```

### 3.2 CostEvidence Schema — LOCKED ✅

**✅ 구현 완료**: `src/agent/domain/rfc_specs/evidence.py` → `CostEvidenceBuilder`

**팀 A는 이 Builder를 사용해야 함** (직접 Evidence 생성 금지):

```python
from src.agent.domain.rfc_specs.evidence import CostEvidenceBuilder

# ✅ GOOD: Builder 사용
evidence = CostEvidenceBuilder.build(
    evidence_id="req_001_ev_001",
    location=Location(file_path="utils.py", start_line=10, end_line=20),
    cost_term="n * m",
    loop_bounds=[
        {"loop_id": "loop_1", "bound": "n", "method": "pattern", "confidence": 1.0}
    ],
    hotspots=[{"line": 15, "reason": "nested loop"}],
    provenance=Provenance(engine="CostAnalyzer", version="1.0.0"),
    claim_ids=["pending"]  # ← 팀 B가 나중에 실제 ID로 교체
)

# ❌ BAD: 직접 생성 (validation 우회 가능)
evidence = Evidence(kind=EvidenceKind.COST_TERM, content={...})
```

**Content 구조** (CostEvidenceBuilder가 보장):

```python
@dataclass
class CostEvidence:
    """Cost Analysis 증거 (RFC-LLM-001 호환)"""

    # Loop bounds
    loop_bounds: list[LoopBound]  # [(loop_id, bound_expr, method, confidence)]

    # Cost term (expression tree)
    cost_term: CostTerm  # add(mul(n, m), log(n))

    # Hotspots
    hotspots: list[Hotspot]  # [(block_id, local_term, reason)]

    # Method
    inference_method: Literal["pattern", "sccp", "widening", "heuristic"]

    # Provenance
    provenance: dict = field(default_factory=lambda: {
        "engine": "cost_analyzer",
        "version": "1.0"
    })

@dataclass
class LoopBound:
    """개별 루프 bound 증거"""
    loop_id: str
    bound_expr: str  # "n", "len(arr)", "unknown"
    method: str      # "pattern", "sccp", "heuristic"
    confidence: float
    location: tuple[str, int]  # (file, line)

@dataclass
class CostTerm:
    """복잡도 expression tree"""
    kind: Literal["const", "symbol", "add", "mul", "log", "pow"]
    value: int | str | None = None  # const: 1, symbol: "n"
    children: list[CostTerm] = field(default_factory=list)

    def __str__(self) -> str:
        if self.kind == "const": return str(self.value)
        if self.kind == "symbol": return str(self.value)
        if self.kind == "add": return f"({' + '.join(map(str, self.children))})"
        if self.kind == "mul": return f"({' * '.join(map(str, self.children))})"
        if self.kind == "log": return f"log({self.children[0]})"
        if self.kind == "pow": return f"({self.children[0]}^{self.children[1]})"
```

### 3.3 ConcurrencyEvidence Schema — LOCKED ✅

**✅ 구현 완료**: `src/agent/domain/rfc_specs/evidence.py` → `ConcurrencyEvidenceBuilder`

**팀 A는 이 Builder를 사용해야 함**:

```python
from src.agent.domain.rfc_specs.evidence import ConcurrencyEvidenceBuilder

# ✅ GOOD: Builder 사용
evidence = ConcurrencyEvidenceBuilder.build(
    evidence_id="req_002_ev_001",
    location=Location(...),
    shared_variable={
        "var_id": "v1",
        "var_name": "cache",
        "escape_status": "shared"  # ← 필수 (local/shared/unknown)
    },
    await_cuts=["node_5", "node_10"],
    lock_regions=[
        {"lock_id": "lock_1", "scope": [45, 65], "resolved_alias": True}  # ← resolved_alias 필수!
    ],
    race_witness={"access1": "line_52", "access2": "line_58", "interleaving_path": ["await_55"]},
    provenance=Provenance(engine="RaceDetector", version="1.0.0"),
    claim_ids=["pending"]
)
```

**Content 구조** (ConcurrencyEvidenceBuilder가 보장):

```python
@dataclass
class ConcurrencyEvidence:
    """Concurrency Analysis 증거"""

    # Shared variable identity
    shared_identity: SharedVar  # var_id + escape_status

    # Await cuts (interleaving points)
    await_cuts: list[str]  # [node_id]

    # Lock regions
    lock_regions: list[LockRegion]

    # Race witness (if race detected)
    race_witness: RaceWitness | None

    # Provenance
    provenance: dict = field(default_factory=lambda: {
        "engine": "concurrency_analyzer",
        "version": "1.0"
    })

@dataclass
class SharedVar:
    """공유 변수 identity"""
    var_id: str
    var_name: str
    escape_status: Literal["local", "shared", "unknown"]  # ← 필수!
    location: tuple[str, int]

@dataclass
class LockRegion:
    """Lock 보호 영역"""
    lock_id: str
    lock_primitive: str  # "asyncio.Lock", "threading.Lock"
    scope: tuple[int, int]  # (start_line, end_line)
    resolved_alias: bool  # Alias resolution 성공 여부 ← CRITICAL!

@dataclass
class RaceWitness:
    """Race condition 증거"""
    access1: VarAccess
    access2: VarAccess
    interleaving_path: list[str]  # Await points between
    confidence: float
```

### 3.4 DifferentialEvidence Schema — LOCKED ✅

**✅ 구현 완료**: `src/agent/domain/rfc_specs/evidence.py` → `DifferentialEvidenceBuilder`

**팀 A는 이 Builder를 사용해야 함**:

```python
from src.agent.domain.rfc_specs.evidence import DifferentialEvidenceBuilder

# ✅ GOOD: Builder 사용
evidence = DifferentialEvidenceBuilder.build(
    evidence_id="req_003_ev_001",
    location=Location(...),
    base_snapshot="snap_455",
    pr_snapshot="snap_456",
    scope={
        "changed_functions": ["func1"],
        "impact_closure": ["func2", "func3"],  # ← BFS 확장 필수!
        "total_symbols": 3
    },
    deltas={
        "sanitizer_removed": [("source1", "sink1")],
        "cost_regressions": []
    },
    fingerprints={"before": {"func1": "hash1"}, "after": {"func1": "hash2"}},
    provenance=Provenance(engine="DifferentialAnalyzer", version="1.0.0"),
    claim_ids=["pending"]
)
```

**Content 구조** (DifferentialEvidenceBuilder가 보장):

```python
@dataclass
class DifferentialEvidence:
    """Differential Analysis 증거"""

    # Scope
    base_snapshot: str
    pr_snapshot: str
    scope: DiffScope  # changed + impact_closure

    # Deltas
    deltas: DiffDeltas

    # Before/After fingerprints
    before_fingerprint: dict  # {function: cost_term/path_fingerprint}
    after_fingerprint: dict

    # Provenance
    provenance: dict = field(default_factory=lambda: {
        "engine": "differential_analyzer",
        "version": "1.0"
    })

@dataclass
class DiffScope:
    """Diff 분석 범위 (RFC-LLM-001 호환)"""
    changed_functions: list[str]
    impact_closure: list[str]  # Callers + callees + data deps ← MUST
    total_symbols: int

    # Evidence에 scope 근거 기록
    closure_method: Literal["call_graph", "data_deps", "both"]
    max_depth: int  # BFS depth used

    def to_evidence(self) -> dict:
        """Evidence로 변환"""
        return {
            "changed": len(self.changed_functions),
            "impacted": len(self.impact_closure),
            "total": self.total_symbols,
            "method": self.closure_method,
            "depth": self.max_depth
        }

@dataclass
class DiffDeltas:
    """변경 사항"""
    sanitizer_edges_removed: list[tuple[str, str]]  # (source, sink)
    new_source_to_sink_paths: list[str]
    cost_regressions: list[tuple[str, str, str]]  # (function, before, after)
    breaking_changes: list[str]
```

---

## 4. Phase 1: Cost Analysis (2-3주)

**Real-time (실시간 증분 모드)**:
- IDE에서 코딩 중 "이 루프는 O(n²), 느릴 수 있음" 경고
-  이내 증분 계산

**PR Review (PR 리뷰 모드)**:
- Before: O(n) → After: O(n²) 자동 탐지
- "성능 회귀 위험" 자동 경고

### 3.2 구현 위치

```
src/contexts/code_foundation/infrastructure/analyzers/cost/
├── __init__.py
├── cost_analyzer.py           # Main entry point
├── loop_bound_analyzer.py     # 루프 반복 횟수 추론
├── complexity_calculator.py   # O(n), O(n²) 계산
├── models.py                  # ComplexityClass, CostResult
└── cache.py                   # Function-level cost cache
```

### 3.3 알고리즘

**Step 1: Loop Bound Inference** (Infer-style)
```python
# Pattern matching (Fast path)
for i in range(n):           → Bound(n), confidence=1.0
for i in range(len(arr)):    → Bound(len(arr)), confidence=1.0
while i < n:                 → Bound(n), confidence=0.8 (with widening)

# Symbolic execution (lightweight)
for i in range(start, end):  → Bound(end - start), confidence=0.9

# ⚠️  Unbounded loop (CRITICAL CASE)
while True:                  → Bound(∞), confidence=0.3 (Heuristic: assume O(n))
while condition:             → Bound(unknown), confidence=0.2 (Heuristic: assume O(n))
```

**⚠️  Critical: Unbounded Loop Handling**
- ❌ **BAD**: 추론 실패 시 `Unknown` 리턴 → IDE에서 "분석 불가" 표시
- ✅ **GOOD**: 추론 실패 시 `Heuristic Bound (O(n))` + `confidence: low` 리턴
  - IDE에서 "잠재적 성능 위험 (확신도 낮음)" 표시
  - UX 개선: "모르겠다" 대신 "위험할 수 있다"

**Step 2: Cost Composition**
```python
# Sequential
cost(S1; S2) = cost(S1) + cost(S2)

# Nested loops
for i in range(n):
    for j in range(m):       → O(n * m)
        ...

# Function call
cost(f()) = lookup(f)        # Cached function cost
```

**Step 3: Complexity Classification**
```python
O(1)      : const
O(log n)  : binary search
O(n)      : single loop
O(n log n): merge sort
O(n²)     : nested loop
O(2^n)    : exponential
```

### 3.4 Integration Points

**기존 인프라 재사용**:
```python
class CostAnalyzer:
    def __init__(self,
                 sccp_engine: SCCPEngine,      # ← 재사용
                 ssa_builder: SSABuilder,      # ← 재사용
                 cfg_provider: CFGProvider):   # ← 재사용
        self.sccp = sccp_engine
        self.ssa = ssa_builder
        self.cfg = cfg_provider

    def analyze_function(self, func_fqn: str) -> CostResult:
        # 1. Get CFG (이미 있음)
        cfg = self.cfg.get_cfg(func_fqn)

        # 2. Build SSA (이미 있음)
        ssa = self.ssa.build(cfg)

        # 3. Use SCCP for constant bounds (이미 있음)
        constants = self.sccp.analyze(ssa)

        # 4. Infer loop bounds (NEW)
        bounds = self._infer_loop_bounds(cfg, constants)

        # 5. Calculate complexity (NEW)
        complexity = self._calculate_complexity(cfg, bounds)

        return CostResult(
            function=func_fqn,
            time_complexity=complexity,
            bottlenecks=[...]
        )
```

### 3.5 실시간 증분 최적화

**증분 계산** (기존 `ChunkIncrementalRefresher` 패턴 재사용):
```python
class IncrementalCostAnalyzer:
    def __init__(self, cache: CostCache):
        self._cache = cache

    def analyze_changed(self, func_fqn: str, changed_lines: set[int]) -> CostResult:
        # 1. Check cache
        if not changed_lines and self._cache.has(func_fqn):
            return self._cache.get(func_fqn)

        # 2. Analyze only affected basic blocks (증분)
        affected_blocks = self._get_affected_blocks(func_fqn, changed_lines)

        # 3. Reuse cached costs for unchanged blocks
        ...

        # Target:  per function
```

### 3.6 Escape Analysis (Shared Variable Detection)

**⚠️  CRITICAL**: Shared variable 판정에 escape analysis 필요

```python
# 현재 단순 정의: global/class field만
# 실전 async 케이스:

# 1. Captured mutable closure
def create_worker():
    cache = {}  # ← Shared? (closure capture)

    async def worker(key):
        cache[key] = value  # ← Race 가능!

    return worker

# 2. Module singleton
_global_cache = {}  # ← Obvious shared

# 3. Injected dependency
class Service:
    def __init__(self, cache: Cache):
        self.cache = cache  # ← Shared? (depends on DI)
```

**Required**:
```python
@dataclass
class SharedVar:
    var_id: str
    var_name: str
    escape_status: Literal["local", "shared", "unknown"]  # ← 필수!
    escape_reason: str | None  # "global", "field", "closure", "unknown"

class SharedVarTracker:
    def analyze_escape(self, var: Variable) -> SharedVar:
        # 1. Global → shared
        if var.is_global():
            return SharedVar(..., escape_status="shared", escape_reason="global")

        # 2. Class field → shared
        if var.is_field():
            return SharedVar(..., escape_status="shared", escape_reason="field")

        # 3. Closure capture → shared (if mutable)
        if var.is_captured() and var.is_mutable():
            return SharedVar(..., escape_status="shared", escape_reason="closure")

        # 4. Unknown → conservative
        return SharedVar(..., escape_status="unknown", escape_reason="complex_flow")
```

### 3.7 API Integration

**ReasoningPipeline 통합** (기존 파이프라인 확장):
```python
# src/contexts/reasoning_engine/application/reasoning_pipeline.py

class ReasoningPipeline:
    def __init__(self, ...):
        ...
        # NEW: Cost analyzer
        self.cost_analyzer = CostAnalyzer(...)

    def analyze_performance_regression(self, changes: dict) -> PerformanceReport:
        """NEW: 성능 회귀 분석"""
        regressions = []

        for func, (before, after) in changes.items():
            # Before cost
            cost_before = self.cost_analyzer.analyze(before)

            # After cost
            cost_after = self.cost_analyzer.analyze(after)

            # Compare
            if cost_after.worse_than(cost_before):
                regressions.append(PerformanceRegression(
                    function=func,
                    before=cost_before.complexity,
                    after=cost_after.complexity,
                    severity="HIGH" if cost_after.is_exponential() else "MEDIUM"
                ))

        return PerformanceReport(regressions=regressions)
```

---

## 4. Phase 2: Concurrency Analysis (2-3주)

### 4.1 목표

**Python async (우선순위)**:
- `asyncio.Lock` 없이 shared variable 접근 탐지
- Race condition 경고
- Deadlock 가능성 경고

**Target**:
- FastAPI/Django async views
- `asyncio` 기반 코드
- 실시간  증분

### 4.2 구현 위치

```
src/contexts/code_foundation/infrastructure/analyzers/concurrency/
├── __init__.py
├── race_detector.py           # Race condition 탐지
├── lock_analyzer.py           # Lock acquisition 분석
├── async_analyzer.py          # Python async/await 전용
├── shared_var_tracker.py      # 공유 변수 추적
└── models.py                  # RaceCondition, LockRegion
```

### 4.3 알고리즘 (RacerD-inspired, Lightweight)

**Step 1: Shared Variable Detection**
```python
# Class fields
class Counter:
    def __init__(self):
        self.count = 0  # ← Shared variable

    async def increment(self):
        self.count += 1  # ← Access

# Global variables
cache = {}  # ← Shared

async def get(key):
    return cache[key]  # ← Access
```

**Step 2: Lock Region Detection**
```python
# asyncio.Lock
lock = asyncio.Lock()

async with lock:    # ← Lock acquired
    self.count += 1 # ← Protected
# ← Lock released

# No lock
self.count += 1     # ← Unprotected (RACE!)
```

**Step 3: Await Point Detection**
```python
async def increment(self):
    temp = self.count
    await asyncio.sleep(0)  # ← Interleaving possible!
    self.count = temp + 1   # ← RACE CONDITION
```

**Step 4: Race Detection**
```
Rule: If (multiple writes OR write+read)
      AND at least one has await before
      AND not protected by lock
      → RACE CONDITION
```

### 4.4 Integration Points

**⚠️  CRITICAL DEPENDENCY: Alias Analysis**

Concurrency 분석의 정확도는 **AliasAnalyzer의 must-alias 정확도**에 의존합니다:

```python
# Case: Lock이 함수 인자로 전달
async def increment(self, lock: asyncio.Lock):
    async with lock:        # ← lock 변수
        self.count += 1     # Protected? → Alias analysis 필요

async def worker(self):
    my_lock = asyncio.Lock()
    await self.increment(my_lock)  # lock === my_lock?
```

**Mitigation**:
- Phase 2 시작 **전에** `alias_analyzer.py`의 must-alias 기능 검증
- Parameter aliasing 정확도 측정
- 정확도 낮으면 Conservative (False Positive 허용)

**기존 인프라 재사용**:
```python
class AsyncRaceDetector:
    def __init__(self,
                 call_graph: CallGraph,          # ← 재사용
                 dfg_builder: DFGBuilder,        # ← 재사용
                 alias_analyzer: AliasAnalyzer): # ← 재사용 (CRITICAL!)
        self.call_graph = call_graph
        self.dfg = dfg_builder
        self.alias = alias_analyzer

        # ⚠️  Phase 2 전에 검증 필요
        self._validate_alias_accuracy()

    def analyze_async_function(self, func_fqn: str) -> list[RaceCondition]:
        # 1. Get async call graph (이미 있음)
        async_callees = self._get_async_callees(func_fqn)

        # 2. Find shared variable accesses (DFG 재사용)
        shared_accesses = self._find_shared_accesses(func_fqn)

        # 3. Check lock protection (NEW)
        locks = self._find_lock_regions(func_fqn)

        # 4. Find await points (NEW)
        await_points = self._find_await_points(func_fqn)

        # 5. Detect races (NEW)
        races = []
        for var, accesses in shared_accesses.items():
            if self._has_race(accesses, locks, await_points):
                races.append(RaceCondition(
                    variable=var,
                    accesses=accesses,
                    reason="Unprotected access with await"
                ))

        return races
```

### 4.5 API Integration

**ReasoningPipeline 통합**:
```python
class ReasoningPipeline:
    def __init__(self, ...):
        ...
        # NEW: Concurrency analyzer
        self.concurrency_analyzer = AsyncRaceDetector(...)

    def analyze_concurrency_issues(self) -> ConcurrencyReport:
        """NEW: 동시성 문제 분석"""
        races = []
        deadlocks = []

        # Find all async functions
        async_functions = self._find_async_functions()

        for func in async_functions:
            # Race detection
            func_races = self.concurrency_analyzer.analyze(func)
            races.extend(func_races)

        return ConcurrencyReport(
            race_conditions=races,
            deadlocks=deadlocks
        )
```

---

## 5. Phase 3: Differential Analysis (2주)

### 5.1 목표

**Security Regression**:
- "Sanitizer 제거됨" 자동 탐지
- "Source → Sink 새 경로" 자동 탐지

**Performance Regression** (Cost Analysis 기반):
- "O(n) → O(n²) 회귀" 자동 탐지

**Breaking Change**:
- Return value semantic 변경
- Exception flow 변경

### 5.2 구현 위치

```
src/contexts/reasoning_engine/infrastructure/differential/
├── __init__.py
├── taint_diff_analyzer.py     # Taint before/after 비교
├── cost_diff_analyzer.py      # Cost before/after 비교
├── semantic_diff_enhancer.py  # 기존 semantic_differ 확장
└── models.py                  # DiffResult, Regression
```

### 5.3 알고리즘

**Taint Differential** (NEW):
```python
class TaintDiffAnalyzer:
    def __init__(self,
                 taint_engine: TaintEngine):  # ← 재사용
        self.taint = taint_engine

    def analyze_diff(self,
                     repo_id: str,
                     base_snapshot: str,
                     pr_snapshot: str,
                     changed_functions: list[str]) -> TaintDiffResult:

        # ⚠️  CRITICAL: Scope를 impact_closure로 확장
        # changed_functions만으로는 regression 놓침
        scope = self._compute_diff_scope(changed_functions)
        # scope = changed_set + callers + callees + data deps
        # 0. ⚠️  Compute diff scope (impact_closure) ← CRITICAL
        scope = self._compute_diff_scope(changed_functions)
        # scope = changed_set + callers + callees + data deps (2-3 hops)

        # 1. Run taint on both snapshots (확장된 scope)
        base_vulns = self.taint.analyze(base_snapshot, scope.all_functions)
        pr_vulns = self.taint.analyze(pr_snapshot, scope.all_functions)

        # 2. New vulnerabilities (NEW)
        new_vulns = [v for v in pr_vulns if v not in base_vulns]

        # 3. Fixed vulnerabilities (NEW)
        fixed_vulns = [v for v in base_vulns if v not in pr_vulns]

        # 4. CRITICAL: Sanitizer removed (NEW)
        sanitizer_removed = self._detect_sanitizer_removal(base_vulns, pr_vulns)

        return TaintDiffResult(
            new_vulnerabilities=new_vulns,
            fixed_vulnerabilities=fixed_vulns,
            sanitizer_removed=sanitizer_removed  # ← HIGH severity
        )
```

**Cost Differential** (Cost Analysis 기반):
```python
class CostDiffAnalyzer:
    def __init__(self,
                 cost_analyzer: CostAnalyzer):  # ← Phase 1에서 구현
        self.cost = cost_analyzer

    def analyze_diff(self, before_code: str, after_code: str) -> CostDiffResult:
        # 1. Analyze both (Phase 1 재사용)
        cost_before = self.cost.analyze(before_code)
        cost_after = self.cost.analyze(after_code)

        # 2. Compare (NEW)
        if cost_after.worse_than(cost_before):
            return CostDiffResult(
                regression=True,
                before=cost_before.complexity,
                after=cost_after.complexity,
                message=f"Performance regression: {cost_before} → {cost_after}"
            )

        return CostDiffResult(regression=False)
```

### 5.4 Integration Points

**기존 SemanticDiffer 확장**:
```python
# src/contexts/reasoning_engine/infrastructure/semantic_diff/semantic_differ.py

class SemanticDiffer:
    def __init__(self, ...):
        ...
        # NEW: Specialized diff analyzers
        self.taint_diff = TaintDiffAnalyzer(...)
        self.cost_diff = CostDiffAnalyzer(...)

    def analyze_comprehensive_diff(self,
                                   before: str,
                                   after: str) -> ComprehensiveDiffResult:
        """기존 semantic diff + taint diff + cost diff"""

        # 1. Existing semantic diff (이미 있음)
        semantic = self.analyze_effects(before, after)

        # 2. NEW: Taint diff
        taint = self.taint_diff.analyze_diff(before, after)

        # 3. NEW: Cost diff
        cost = self.cost_diff.analyze_diff(before, after)

        return ComprehensiveDiffResult(
            semantic_changes=semantic,
            security_regressions=taint.new_vulnerabilities,
            sanitizer_removed=taint.sanitizer_removed,  # ← CRITICAL
            performance_regressions=cost.regressions,
            breaking_changes=semantic.breaking_changes
        )
```

---

## 6. Integration Architecture (통합 전략)

### 6.1 Two-Pipeline Pattern

**핵심 구조**: 생성 파이프라인 + 사용 파이프라인

```
┌───────────────────────────────────────────────┐
│ Pipeline 1: Indexing (생성)                   │
│ src/contexts/analysis_indexing/               │
│                                                │
│ 9-Stage Pipeline:                              │
│ 1. Git → 2. Discovery → 3. Parsing            │
│ 4. IR (CFG/DFG/SSA) ⭐                        │
│ 5. Semantic IR → 6. Graph                     │
│ 7. Chunk → 8. RepoMap → 9. Index             │
│                                                │
│ Output: IR, Graph, Chunk, Index               │
└───────────────────────────────────────────────┘
              ↓ produces
┌───────────────────────────────────────────────┐
│ Pipeline 2: Reasoning (사용)                  │
│ src/contexts/reasoning_engine/                │
│                                                │
│ ReasoningPipeline:                             │
│ - analyze_effects()                            │
│ - analyze_impact()                             │
│ - simulate_patch()                             │
│ ✅ - analyze_cost() (NEW)                     │
│ ✅ - analyze_concurrency() (NEW)              │
│ ✅ - analyze_pr_diff() (NEW)                  │
│                                                │
│ Input: IR, Graph (from Pipeline 1)            │
└───────────────────────────────────────────────┘
```

### 6.2 Integration Points (4곳)

#### **Point 1: IRStage (실시간 증분 모드)** ⚡ Real-time

**위치**: `src/contexts/analysis_indexing/infrastructure/stages/ir_stage.py`

**통합 방식**: IR 생성 직후 즉시 분석
```python
class IRStage(BaseStage):
    def __init__(self, ...,
                 cost_analyzer=None,           # ← DI 추가
                 concurrency_analyzer=None):   # ← DI 추가
        super().__init__(...)
        self.cost_analyzer = cost_analyzer
        self.concurrency_analyzer = concurrency_analyzer

    async def execute(self, ctx: StageContext) -> StageContext:
        # 1. IR 생성 (기존)
        ir_docs = {}
        for file in ctx.files:
            ir_doc = self.ir_builder.build(file)
            ir_docs[file] = ir_doc

            # ✅ 2. 생성 직후 즉시 분석 (실시간)
            if ctx.config.enable_realtime_analysis:
                # Cost analysis (per-file, )
                if self.cost_analyzer:
                    cost = self.cost_analyzer.analyze_ir(ir_doc)
                    ctx.analysis_results[f"cost:{file}"] = cost

                # Concurrency (async only, )
                if self.concurrency_analyzer and ir_doc.has_async:
                    races = self.concurrency_analyzer.analyze_ir(ir_doc)
                    ctx.analysis_results[f"race:{file}"] = races

        ctx.ir_docs = ir_docs
        return ctx
```

**용도**: IDE 저장 시 즉시 경고 (파일 단위)
**Target**: 100- per file
**Mode**: Incremental only

---

#### **Point 2: ReasoningPipeline (PR/Audit 모드)** 🔍 Deep Analysis

**위치**: `src/contexts/reasoning_engine/application/reasoning_pipeline.py`

**통합 방식**: 전체 컨텍스트 분석
```python
class ReasoningPipeline:
    def __init__(self,
                 graph: GraphDocument,
                 workspace_root: str | None = None,
                 # ✅ NEW: DI 추가
                 cost_analyzer=None,
                 concurrency_analyzer=None,
                 differential_analyzer=None):

        self.ctx = ReasoningContext(graph=graph)

        # 기존
        self.effect_differ = EffectAnalyzerAdapter()
        self.impact_analyzer = ImpactAnalyzerAdapter(graph, max_depth=5)
        self.slicer = SlicerAdapter(graph)
        self.risk_analyzer = RiskAnalyzerAdapter()

        # ✅ NEW
        self.cost_analyzer = cost_analyzer
        self.concurrency_analyzer = concurrency_analyzer
        self.differential = differential_analyzer

    # ✅ NEW 메서드들
    def analyze_cost(self, functions: list[str]) -> dict[str, CostResult]:
        """Cost 분석 (전체 컨텍스트)"""
        results = {}
        for func in functions:
            # Graph에서 IR 가져오기
            ir_doc = self._get_ir_for_function(func)
            cost = self.cost_analyzer.analyze_ir(ir_doc)
            results[func] = cost
        return results

    def analyze_concurrency(self, async_functions: list[str]) -> ConcurrencyReport:
        """Concurrency 분석"""
        races = []
        for func in async_functions:
            ir_doc = self._get_ir_for_function(func)
            func_races = self.concurrency_analyzer.analyze_ir(ir_doc)
            races.extend(func_races)
        return ConcurrencyReport(races=races)

    def analyze_pr_diff(self,
                        repo_id: str,
                        base_snapshot: str,
                        pr_snapshot: str,
                        changed_functions: list[str]) -> DiffReport:
        """Differential 분석 (PR review)"""

        # 1. Scope 확장 (impact_closure)
        scope = self._compute_impact_closure(changed_functions)

        # 2. Taint diff
        taint_diff = self.differential.analyze_taint_diff(
            repo_id, base_snapshot, pr_snapshot, scope
        )

        # 3. Cost diff (Phase 1 완료 후)
        cost_diff = self.differential.analyze_cost_diff(
            repo_id, base_snapshot, pr_snapshot, scope
        )

        # 4. Breaking change (기존)
        breaking = self.effect_differ.analyze_breaking(...)

        return DiffReport(
            security_regressions=taint_diff.new_vulnerabilities,
            sanitizer_removed=taint_diff.sanitizer_removed,  # CRITICAL
            performance_regressions=cost_diff.regressions,
            breaking_changes=breaking
        )

    def _get_ir_for_function(self, func_fqn: str):
        """Graph에서 IR 추출 (또는 캐시/재생성)"""
        # Graph에 IR이 저장되어 있거나
        # 파일 경로를 찾아서 재파싱
        ...
```

**용도**: PR 리뷰, 전체 감사
**Target**: 2-5초 per PR (10-50 files)
**Mode**: Full + Incremental

---

#### **Point 3: API Routes (HTTP)** 🌐 External

**위치**: `server/api_server/routes/agent.py`

**통합 방식**: HTTP 엔드포인트
```python
# 기존 Mock 제거하고 실제 구현

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_code(request: AnalyzeRequest):
    """코드 분석 (Cost + Concurrency + Taint + Null)"""
    try:
        # 1. Get graph
        foundation = container._foundation
        graph = foundation.graph_store.get_latest_graph(request.repo_path)

        # 2. Create ReasoningPipeline
        pipeline = ReasoningPipeline(
            graph=graph,
            cost_analyzer=foundation.cost_analyzer,
            concurrency_analyzer=foundation.race_detector,
            differential_analyzer=foundation.differential_analyzer
        )

        # 3. Run analyses
        files = request.files or []

        # Cost
        cost_results = pipeline.analyze_cost(files)

        # Concurrency
        concurrency_results = pipeline.analyze_concurrency(files)

        # 4. Convert to issues
        issues = []

        for func, cost in cost_results.items():
            if cost.is_slow():
                issues.append({
                    "severity": cost.severity,
                    "type": "performance",
                    "message": cost.explanation,
                    "verdict": cost.verdict,  # ← proven/likely/heuristic
                    "evidence": cost.evidence.to_dict()
                })

        for race in concurrency_results.races:
            issues.append({
                "severity": "critical",
                "type": "race_condition",
                "message": race.explanation,
                "verdict": race.verdict,
                "evidence": race.evidence.to_dict()
            })

        return AnalyzeResponse(
            summary=f"Found {len(issues)} issues",
            issues=issues,
            recommendations=_generate_recommendations(issues)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ NEW: PR Diff 전용 엔드포인트
@router.post("/analyze/pr-diff", response_model=DiffResponse)
async def analyze_pr_diff(request: PRDiffRequest):
    """PR Differential Analysis"""
    foundation = container._foundation
    graph = foundation.graph_store.get_graph(request.repo_id)

    pipeline = ReasoningPipeline(
        graph=graph,
        differential_analyzer=foundation.differential_analyzer
    )

    diff_report = pipeline.analyze_pr_diff(
        request.repo_id,
        request.base_snapshot,
        request.pr_snapshot,
        request.changed_files
    )

    return DiffResponse(
        security_regressions=diff_report.security_regressions,
        performance_regressions=diff_report.performance_regressions,
        sanitizer_removed=diff_report.sanitizer_removed,  # CRITICAL
        breaking_changes=diff_report.breaking_changes
    )
```

---

#### **Point 4: MCP Server (IDE 통합)** 💡 IDE

**위치**: `server/mcp_server/handlers/`

**통합 방식**: MCP 프로토콜 (VSCode/Cursor)
```python
# server/mcp_server/handlers/analyze_cost.py (신규)

from mcp.server import Server
from src.container import container

mcp = Server("semantica-cost")

@mcp.tool()
async def analyze_function_cost(
    file_path: str,
    function_name: str,
    line_number: int
) -> dict:
    """
    IDE에서 함수 위에 커서 놓으면 즉시 분석

    Target: <
    Trigger: onHover, onSave
    """
    # 1. Get cached IR (빠름)
    foundation = container._foundation
    ir_doc = foundation.ir_cache.get_or_build(file_path)

    # 2. Find function at line
    func = ir_doc.find_function_at_line(line_number)

    # 3. Cost analysis (cached, incremental)
    cost = foundation.cost_analyzer.analyze_function(func.fqn)

    # 4. Return for IDE tooltip
    return {
        "complexity": str(cost.complexity),
        "verdict": cost.verdict,
        "confidence": cost.confidence,
        "message": cost.explanation,
        "hotspots": [
            {"line": h.line, "reason": h.reason}
            for h in cost.evidence.hotspots
        ],
        # IDE tooltip
        "tooltip": f"⚠️  {cost.complexity} (확신도: {cost.confidence:.0%})"
    }

@mcp.tool()
async def check_race_conditions(
    file_path: str
) -> list[dict]:
    """
    파일 저장 시 자동 체크

    Target: <
    Trigger: onSave
    """
    foundation = container._foundation
    ir_doc = foundation.ir_cache.get_or_build(file_path)

    # Async functions only
    if not ir_doc.has_async:
        return []

    races = foundation.race_detector.analyze_file(ir_doc)

    return [
        {
            "line": race.line,
            "variable": race.shared_identity.var_name,
            "severity": "error" if race.verdict == "proven" else "warning",
            "message": race.explanation,
            "evidence": race.evidence.to_dict()
        }
        for race in races
    ]
```

---

### 6.3 Container Integration (DI)

**FoundationContainer에 등록** (핵심):

```python
# src/contexts/code_foundation/infrastructure/di.py

class FoundationContainer:
    def __init__(self, settings, infra_container):
        self.settings = settings
        self._infra = infra_container

    # ============================================================
    # ✅ NEW: Analysis Components (RFC-028)
    # ============================================================

    @cached_property
    def cost_analyzer(self):
        """Cost Analyzer (RFC-028 Phase 1)"""
        from .analyzers.cost import CostAnalyzer

        return CostAnalyzer(
            sccp_engine=self.sccp_engine,
            ssa_builder=self.ssa_builder,
            cfg_provider=self.cfg_provider,
            cache=self._infra.redis  # 캐시 재사용
        )

    @cached_property
    def race_detector(self):
        """Concurrency Analyzer (RFC-028 Phase 2)"""
        from .analyzers.concurrency import AsyncRaceDetector

        return AsyncRaceDetector(
            call_graph=self.call_graph,
            dfg_builder=self.dfg_builder,
            alias_analyzer=self.alias_analyzer,  # ⚠️  Pre-check 필요
            mode="ide"  # Default: IDE mode (FP 최소)
        )

    @cached_property
    def differential_analyzer(self):
        """Differential Analyzer (RFC-028 Phase 3)"""
        from ..reasoning_engine.infrastructure.differential import DifferentialAnalyzer

        return DifferentialAnalyzer(
            taint_engine=self.taint_engine,
            cost_analyzer=self.cost_analyzer,  # Phase 1 완료 후
            semantic_differ=self.semantic_differ,
            impact_analyzer=self.impact_analyzer
        )

    # ============================================================
    # Existing Components (재사용)
    # ============================================================

    @cached_property
    def sccp_engine(self):
        """SCCP Engine (재사용)"""
        from .dfg.constant import ConstantPropagationAnalyzer
        return ConstantPropagationAnalyzer()

    @cached_property
    def alias_analyzer(self):
        """Alias Analyzer (재사용, ⚠️  Phase 2 전 검증)"""
        from .analyzers import AliasAnalyzer
        return AliasAnalyzer()

    # ... 기타 기존 컴포넌트
```

---

### 6.4 Mode-Specific Configuration

**모드별 동작 차이** (중요):

```python
# IDE Mode (실시간, Point 1 + Point 4)
config = AnalysisConfig(
    mode="ide",
    timeout_ms=100,  # Cost
    enable_heuristic=True,
    heuristic_verdict_level="hidden",  # Heuristic는 숨김
    false_positive_tolerance="low"  # FP 최소화
)

# PR Review Mode (Point 2 + Point 3)
config = AnalysisConfig(
    mode="pr",
    timeout_ms=5000,  # 5초
    enable_heuristic=True,
    heuristic_verdict_level="warning",  # Heuristic 경고로 표시
    false_negative_tolerance="low"  # FN 최소화 (보수적)
)

# Audit Mode (Deep, Point 2)
config = AnalysisConfig(
    mode="audit",
    timeout_ms=30000,  # 30초
    enable_full_biabduction=True,
    false_negative_tolerance="zero"  # FN 절대 방지
)
```

**Analyzer에서 사용**:
```python
class AsyncRaceDetector:
    def __init__(self, ..., mode: str = "ide"):
        self.mode = mode

    def analyze_ir(self, ir_doc) -> list[RaceCondition]:
        races = self._detect_races(ir_doc)

        # Mode-specific filtering
        if self.mode == "ide":
            # Heuristic verdict는 숨김
            races = [r for r in races if r.verdict != "heuristic"]
        elif self.mode in ("pr", "audit"):
            # Heuristic도 표시 (보수적)
            pass

        return races
```

---

## 7. Implementation Roadmap (수정)

### Week 1-2: Cost Analysis Foundation
```
Day 1-2:  Loop bound inference (pattern matching - Pythonic patterns)
Day 3:    ⚠️  Unbounded loop handling (Heuristic + confidence)
Day 4-5:  SCCP integration (constant bounds 재사용)
Day 6-7:  Complexity calculator (O(n), O(n²))
Day 8-9:  Cost cache + incremental
Day 10:   Unit tests (특히 unbounded loop cases)
```

### Week 3-4: Cost Analysis Integration (4 Points)
```
Day 11:    FoundationContainer에 cost_analyzer 등록
Day 12:    ✅ Point 1: IRStage 통합 (실시간 모드)
Day 13:    ✅ Point 2: ReasoningPipeline 통합 (PR/Audit 모드)
Day 14:    ✅ Point 3: API Routes 통합 (/agent/analyze)
Day 15:    ✅ Point 4: MCP Server 통합 (IDE)
Day 16:    Cost diff analyzer 구현
Day 17:    Mode-specific config (IDE/PR/Audit)
Day 18:    End-to-end testing + benchmarking
```

### Week 5-6: Concurrency Analysis
```
Day 19:    ⚠️  Pre-check: AliasAnalyzer must-alias 정확도 측정
Day 20-21: Shared variable tracker (+ escape analysis)
Day 22-23: Lock region detector (with alias resolution)
Day 24-25: Await point analyzer (Python async 특화)
Day 26-27: Race detector (RacerD-inspired, lightweight)
Day 28:    ✅ 4-Point Integration (IRStage/Pipeline/API/MCP)
Day 29:    Mode-specific filtering (IDE/PR/Audit)
Day 30:    Testing (FastAPI/Django) + False Positive 튜닝
```

### Week 7-8: Differential Analysis + Integration
```
Day 31-32: Taint diff analyzer (sanitizer removal detection)
Day 33-34: Cost diff analyzer (performance regression)
Day 35-36: Scope 확장 (impact_closure 자동 계산)
Day 37:    SemanticDiffer enhancement
Day 38:    ✅ 4-Point Integration
Day 39:    Mode-specific behavior (PR/Audit)
Day 40:    End-to-end PR testing
Day 41:    MCP Server finalization (IDE tooltips)
Day 42:    Documentation + API docs
```

---

## 7. Success Metrics (Verdict별)

### Cost Analysis (Verdict-based KPI)
- [ ] **Proven** (pattern, sccp):
  - Precision: 95%+
  - Coverage: Simple loops (for, while with constant)
- [ ] **Likely** (widening):
  - Precision: 85%+
  - Coverage: Simple while loops
- [ ] **Heuristic** (unbounded fallback):
  - Warning acceptance rate: 20%+ (개발자가 수용 가능한 비율)
  - Upper bound conservativeness: Actual < Predicted (90%+)
- [ ] **Performance**:
  - Real-time:  per function (incremental)
  - IDE integration: "느린 코드" 실시간 표시

### Concurrency Analysis (Verdict-based KPI)
- [ ] **Proven** (must-alias resolved):
  - Precision: 90%+ (FP 10% 이하)
  - Recall: 85%+
- [ ] **Heuristic** (alias unresolved):
  - IDE 모드: 기본 숨김 (noise 방지)
  - PR/AUDIT 모드: 표시하되 severity 낮춤
- [ ] **Performance**:
  - Real-time:  per async function
  - FastAPI/Django async 지원

### Differential Analysis (Verdict-based KPI)
- [ ] **Sanitizer Removal** (proven):
  - Recall: 100% (놓치면 안 됨)
  - Precision: 95%+
- [ ] **Performance Regression** (proven + likely):
  - Recall: 90%+ (O(n) → O(n²))
  - Precision: 85%+
- [ ] **Breaking Change** (proven):
  - Recall: 85%+
  - Precision: 90%+
- [ ] **Scope Coverage**:
  - Impact closure depth: 2-3 hops (BFS)
  - Coverage: changed + 80%+ of direct callers

---

## 8. API Surface (RFC-LLM-001 Integration)

### 8.1 Internal API (Phase 완료 후)

```python
# Cost Analysis
cost_analyzer.analyze_function("process_data")
→ CostResult(complexity=O(n²), bottlenecks=[...])

# Concurrency Analysis
concurrency_analyzer.analyze_async_function("handle_request")
→ [RaceCondition(variable="cache", ...)]

# Differential Analysis
differential_analyzer.analyze_pr_diff(base_snapshot, pr_snapshot)
→ DiffResult(
    security_regressions=[...],
    performance_regressions=[...],
    sanitizer_removed=[...]  # CRITICAL
)
```

### 8.2 External API (RFC-LLM-001 연동)

```python
# POST /execute with AnalyzeSpec
{
  "intent": "analyze",
  "template_id": "performance_regression",
  "scope": {
    "base_snapshot": "snap_before",
    "pr_snapshot": "snap_after",
    "changed_files": [...]
  }
}

# Response: ResultEnvelope
{
  "claims": [
    {
      "type": "performance_regression",
      "confidence_basis": "proven",  # Cost analysis proof
      "severity": "high",
      "proof_obligation": {
        "before_complexity": "O(n)",
        "after_complexity": "O(n²)",
        "bottleneck_location": "line 42"
      }
    },
    {
      "type": "security_regression",
      "confidence_basis": "proven",  # Taint diff proof
      "severity": "critical",
      "proof_obligation": {
        "sanitizer_removed": "escape() call removed",
        "vulnerable_path": "request → execute"
      }
    }
  ],
  "evidences": [...]
}
```

---

## 9. Testing Strategy

### Unit Tests
```
src/contexts/code_foundation/tests/analyzers/cost/
├── test_loop_bound_inference.py
├── test_complexity_calculator.py
└── test_cost_cache.py

src/contexts/code_foundation/tests/analyzers/concurrency/
├── test_race_detector.py
├── test_lock_analyzer.py
└── test_async_race.py

src/contexts/reasoning_engine/tests/differential/
├── test_taint_diff.py
├── test_cost_diff.py
└── test_sanitizer_removal.py
```

### Integration Tests
```
tests/integration/
├── test_cost_analysis_end_to_end.py
├── test_concurrency_fastapi.py
└── test_pr_diff_analysis.py
```

### Benchmark
```
benchmark/_external_benchmark/
├── cost_analysis_benchmark.py    # Infer와 비교
├── concurrency_benchmark.py      # RacerD와 비교
└── diff_analysis_benchmark.py    # Manual review와 비교
```

---

## 10. Dependencies & Risks

### Dependencies

| Component | Status | Must-Check Before Use |
|-----------|--------|----------------------|
| SCCP Engine | ✅ Ready | None |
| SSA Builder | ✅ Ready | None |
| CFG Builder | ✅ Ready | None |
| Call Graph | ✅ Ready | None |
| Taint Engine | ✅ Ready | None |
| Semantic Differ | ✅ Ready | None |
| **Alias Analyzer** | ⚠️  Exists | **Phase 2 전 must-alias 정확도 측정 필수** |
| Impact Analyzer | ✅ Ready | Scope expansion용 재사용 |
| Escape Analysis | ❌ Needed | Concurrency에서 구현 필요 |

### Risks & Mitigations

1. **Cost Analysis: Unbounded Loop** (High) ⭐ CRITICAL
   - **Risk**: `while True:`, 복잡한 재귀 → Bound 추론 실패
   - ❌ **BAD Mitigation**: "Unknown" 리턴 → IDE에서 "분석 불가"
   - ✅ **GOOD Mitigation**: Heuristic Bound (O(n)) + `confidence: 0.2-0.3`
   - **Rationale**: IDE UX 관점에서 "모르겠다" < "위험할 수 있다" (actionable)
   - **Fallback**: Conservative O(n²) 가정 + Warning

2. **Concurrency: Context Sensitivity** (High) ⭐ CRITICAL
   - **Risk**: Lock이 함수 인자로 전달 → Alias 분석 실패 → False Positive
   - **Pre-check**: Phase 2 시작 전 `alias_analyzer.py` must-alias 정확도 측정
   - **Mitigation**: Must-alias 실패 시 Conservative (Protected로 간주)
   - **Fallback**: Lock pattern 화이트리스트 (예: `self._lock` 필드만)

3. **Differential 노이즈** (Low)
   - **Risk**: 사소한 변경에도 과도한 경고
   - **Mitigation**: Severity-based filtering (CRITICAL만 기본 표시)
   - **Fallback**: User feedback loop (false alarm 학습)

---

## 11. Best Practices & Critical Checkpoints

### 🏆 Best Highlights (신의 한 수)

**A. Cost Analysis: Loop Bound Inference**
- Pattern matching으로 Pythonic 패턴 (`range(n)`, `len(arr)`) 추론
- SCCP 상수 재사용 (SMT Solver 안 써도 됨)
- **Why Good**: 실시간성() 보장 + 가성비 최고

**B. Concurrency: Await Point Detection**
- Python async 특성: `await` 지점에서만 컨텍스트 스위칭
- 모든 명령어 검사 X, await 전후만 체크
- **Why Good**: False Positive 획기적 감소

**C. Differential: Sanitizer Removal Detection**
- 단순 취약점 개수 비교 X
- "방어막(Sanitizer)이 사라졌는가?" 체크
- **Why Good**: 보안 팀 God Feature

### ⚠️ Critical Checkpoints (구현 시 주의사항)

**Checkpoint 1: Cost Analysis - Unbounded Loop Handling**

**Risk**: `while True:`, 복잡한 재귀 → Bound 추론 실패
```python
# 추론 어려운 케이스
while True:
    if complex_condition():
        break

def recursive_func(n):
    if random_condition():
        return recursive_func(n - 1)
```

**❌ BAD Approach**:
```python
return CostResult(complexity=ComplexityClass.UNKNOWN)
# → IDE: "분석 불가(복잡함)" (not actionable)
```

**✅ GOOD Approach**:
```python
return CostResult(
    complexity=ComplexityClass.LINEAR,  # Heuristic: O(n) 가정
    confidence=0.2,  # Low confidence
    explanation="추론 실패, 보수적으로 O(n) 가정"
)
# → IDE: "잠재적 성능 위험 (확신도 낮음)" (actionable)
```

**Implementation**:
```python
# src/contexts/code_foundation/infrastructure/analyzers/cost/loop_bound_analyzer.py

def _infer_loop_bound(self, loop: LoopNode) -> BoundResult:
    # 1. Pattern matching (Fast path) → proven
    if loop.is_for_range():
        return BoundResult(
            bound=loop.range_arg(),
            verdict="proven",
            confidence=1.0,
            method="pattern",
            evidence=CostEvidence(
                loop_bounds=[LoopBound(
                    loop_id=loop.id,
                    bound_expr=str(loop.range_arg()),
                    method="pattern",
                    confidence=1.0,
                    location=(loop.file, loop.line)
                )],
                cost_term=CostTerm("symbol", value=str(loop.range_arg())),
                hotspots=[],
                inference_method="pattern"
            )
        )

    # 2. SCCP constant (Fast path) → proven
    if loop.condition_is_constant():
        const = self.sccp.get_constant(loop.limit_var)
        return BoundResult(
            bound=const,
            verdict="proven",
            confidence=0.95,
            method="sccp",
            evidence=CostEvidence(...)
        )

    # 3. Widening (Medium path) → likely
    if loop.is_simple_while():
        return BoundResult(
            bound=Symbolic("n"),
            verdict="likely",
            confidence=0.8,
            method="widening",
            evidence=CostEvidence(...)
        )

    # 4. ⚠️  FALLBACK: Unbounded → heuristic + upper_bound_hint
    # ❌ BAD: return BoundResult(bound=Symbolic("n"), confidence=0.2)
    # ✅ GOOD: UNKNOWN + conservative upper bound
    return BoundResult(
        bound=Unknown(),
        verdict="heuristic",
        confidence=0.2,
        method="heuristic",
        upper_bound_hint="O(n²)",  # Conservative (worst-case)
        warning="Unbounded loop: worst-case O(n²) assumed",
        evidence=CostEvidence(
            loop_bounds=[LoopBound(
                loop_id=loop.id,
                bound_expr="unknown",
                method="heuristic",
                confidence=0.2,
                location=(loop.file, loop.line)
            )],
            cost_term=CostTerm("unknown"),
            hotspots=[],
            inference_method="heuristic"
        ),
        explanation="Unknown termination: 보수적 O(n²) 경고"
    )
```

**UX Mapping** (IDE):
```python
if result.verdict == "proven":
    show_warning(severity="HIGH", color="red")
elif result.verdict == "likely":
    show_warning(severity="MEDIUM", color="yellow")
elif result.verdict == "heuristic":
    show_hint(severity="INFO", color="blue",
              message=f"상한 미확정: worst-case {result.upper_bound_hint}")
```

**Checkpoint 2: Concurrency - Context Sensitivity (Alias 의존성)**

**Risk**: Lock 객체가 함수 인자로 전달 → Alias 실패 → False Positive

```python
async def process(self, lock: asyncio.Lock):
    async with lock:        # ← lock 변수
        self.count += 1     # Protected?

async def worker(self):
    my_lock = asyncio.Lock()
    await self.process(my_lock)  # lock === my_lock? (Must-alias needed)
```

**Pre-check Required** (Phase 2 시작 전):
```python
# Verify alias_analyzer.py accuracy
def test_must_alias_accuracy():
    """
    Must-alias 정확도 측정

    Target: 90%+ for parameter aliasing
    """
    test_cases = [
        ("lock === my_lock", True),   # Parameter passing
        ("self._lock === lock", False), # Field vs parameter
        ...
    ]

    for case, expected in test_cases:
        result = alias_analyzer.must_alias(case.lhs, case.rhs)
        assert result == expected
```

**Mitigation** (Alias 정확도 낮을 시) — **모드별 Verdict 조정**:
```python
class AsyncRaceDetector:
    def __init__(self, ..., mode: Literal["ide", "pr", "audit"]):
        self.mode = mode

    def _is_protected_by_lock(self, access: VarAccess, locks: list[Lock]) -> ProtectionResult:
        for lock in locks:
            # Must-alias check (CRITICAL)
            if self.alias.must_alias(access.in_scope, lock.scope):
                return ProtectionResult(
                    protected=True,
                    verdict="proven",
                    confidence=0.95
                )

        # ⚠️  Alias 실패 시 — Mode-specific policy
        if self.alias.resolve_failed(access.in_scope, locks):
            if self.mode == "ide":
                # IDE: False Positive 줄이기 → verdict 낮춤
                return ProtectionResult(
                    protected=True,  # 보호된 것으로 간주 (경고 숨김)
                    verdict="heuristic",
                    confidence=0.3,
                    explanation="Alias 미해결: IDE 모드에서 경고 숨김"
                )
            else:  # pr, audit
                # PR/AUDIT: False Negative 방지 → 보수적
                return ProtectionResult(
                    protected=False,  # 보호 안 된 것으로 간주
                    verdict="heuristic",
                    confidence=0.4,
                    explanation="Alias 미해결: 보수적으로 unprotected 판정",
                    evidence=ConcurrencyEvidence(
                        shared_identity=...,
                        lock_regions=[
                            LockRegion(
                                ...,
                                resolved_alias=False  # ← Evidence에 기록!
                            )
                        ]
                    )
                )

        return ProtectionResult(protected=False, verdict="proven", confidence=0.95)
```

**핵심**: 결론(protected=True/False)을 바꾸지 말고, **verdict를 조정**해서 모드별 처리

---

## 12. Conclusion

### Why This Matters
1. **Cost Analysis**: IDE 실시간 성능 경고 → 개발자 생산성 ↑
2. **Concurrency**: Python async 안전성 → 프로덕션 버그 ↓
3. **Differential**: PR 자동 리뷰 → 보안/성능 회귀 조기 발견

### Timeline Summary
- **Week 1-2**: Cost Analysis 구현
- **Week 3-4**: Cost 4-Point Integration (IRStage, Pipeline, API, MCP)
- **Week 5-6**: Concurrency (alias pre-check + 4-Point Integration)
- **Week 7-8**: Differential (scope 확장 + 4-Point Integration)
- **Total**: 6-8주

### Critical Success Factors
1. ⚠️  **Unbounded loop**: UNKNOWN + upper_bound_hint (not O(n) 고정)
2. ⚠️  **Alias accuracy**: Phase 2 전 must-alias 정확도 측정 필수
3. ⚠️  **Mode separation**: IDE(FP 최소) vs PR/Audit(FN 최소)
4. ✅ **4-Point Integration**: IRStage, ReasoningPipeline, API, MCP
5. ✅ **Incremental**: 기존 캐싱 인프라 재사용
6. ✅ **Low Hanging Fruit**: Cost Analysis부터 (쉽고 효과 큼)

### Integration Checklist (각 Phase마다)
- [ ] **Point 1**: IRStage (실시간 증분,  목표)
- [ ] **Point 2**: ReasoningPipeline (PR/Audit, 2-5초 목표)
- [ ] **Point 3**: API Routes (HTTP, Mock 제거)
- [ ] **Point 4**: MCP Server (IDE tooltip, < 목표)

### Next Steps
1. **Day 1**: FoundationContainer에 DI 준비
2. **Week 1-2**: Cost Analysis 구현
3. **Day 11**: ⚠️  4-Point Integration 시작
4. **Day 19**: ⚠️  Alias pre-check (Concurrency 전)
5. **Week 7**: Differential 4-Point Integration

---

---

## 14. RFC-027 Integration Status

### ✅ Evidence 스키마 확정 완료 (Phase 0)

**파일**:
- `src/agent/domain/rfc_specs/evidence.py` (구현 완료)
- `src/agent/domain/rfc_specs/claim.py` (구현 완료)
- `src/agent/adapters/rfc/mappings.py` (매핑 테이블)
- `tests/agent/domain/rfc_specs/test_evidence.py` (통과)

**병행 작업**: ✅ **가능** (시뮬레이션 성공)

**Sync Points**: Week 2, 4, 8 (총 3회)

**참고**: `_docs/_backlog/RFC-027-028-PARALLEL-WORK-PLAN.md`

---

**RFC-028 — READY FOR IMPLEMENTATION**
**Review Feedback: INCORPORATED (Unbounded Loop, Alias Dependency)**
**RFC-027 Integration: COMPLETE (Evidence Schema Locked)**
