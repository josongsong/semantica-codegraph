# RFC-036: Deterministic Lazy Semantic IR (Final)

## Status: Draft
## Author: Semantica Team
## Created: 2025-12-21
## Priority: P1
## Estimated: 7-8h

---

## 1. Executive Summary

**한 줄 요약:**
> AI 코딩 에이전트가 "지금 필요한 정확한 정보"만 즉시 얻고, 나머지는 요청 시 동일한 결과로 재계산 가능하도록 한다.

**핵심 원칙:**
```
로컬·결정적·선형 → Precompute (Base)
전역·조합적·목적 의존 → Lazy (On-demand)
```

**목표:**
- 성능: Editor mode 78% 개선 (2.3s → 0.5s)
- 정확성: Deterministic 보장 (입력 동일 → 출력 동일)
- 실용성: 3-tier model (90/9/1 사용 패턴)

---

## 2. 문제 정의

### 2.1 현재 문제

**All-or-Nothing:**
```python
BuildConfig(
    enable_semantic_ir=True  # CFG + DFG + SSA + BFG 전부
)
```

**비효율:**
- Rich (46K LOC): Semantic IR 2.3초 (전체의 51%)
- AI 에이전트 90% 작업: SSA/PDG 불필요
- 메모리: +380MB

### 2.2 잘못된 접근 (배제)

**❌ 근사 CFG/DFG**
- 정확성 훼손

**❌ 보안 분석 우선 최적화**
- AI 코딩 목적과 불일치

**❌ 8-stage 세분화**
- Over-engineering

---

## 3. 설계: 3-Tier Model

### 3.1 Tier 정의

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Base (Always)                                        │
│   - Structural IR (AST, nodes, edges)                       │
│   - CFG (Control Flow, function-local)                      │
│   - Call Graph (CALLS edges)                                │
│   Cost: ~800ms (18%)                                        │
│   Use: 90% AI tasks                                         │
├─────────────────────────────────────────────────────────────┤
│ Tier 2: Extended (On-demand, Refactoring)                   │
│   - Expression IR (87K expressions)                         │
│   - DFG (Data Flow, with threshold)                         │
│   - Type Enrichment (Summary, Generic)                      │
│   Cost: +1.2s (27%)                                         │
│   Use: 9% AI tasks                                          │
├─────────────────────────────────────────────────────────────┤
│ Tier 3: Full (On-demand, Analysis)                          │
│   - SSA + Dominator                                         │
│   - PDG (Program Dependence)                                │
│   - Interprocedural DFG                                     │
│   - Taint Analysis                                          │
│   Cost: +0.5s (11%)                                         │
│   Use: 1% AI tasks                                          │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 사용 패턴 매핑

| AI Task | Tier | Example |
|---------|------|---------|
| "이 함수 이해해줘" | Base | CFG + Signature |
| "어디서 호출됨?" | Base | Call Graph |
| "이름 바꿔도 돼?" | Base | REFERENCES |
| "Extract Method 안전?" | Extended | DFG (로컬) |
| "이 값 어디서 왔어?" | Extended | DFG |
| "Null 가능성?" | Full | SSA + Path |
| "이 코드 슬라이싱" | Full | PDG |

---

## 4. 구현 설계

### 4.1 BuildConfig (Simplified)

```python
from enum import Enum

class SemanticTier(str, Enum):
    """Semantic IR tiers."""
    
    BASE = "base"         # CFG + Calls (Always)
    EXTENDED = "extended" # + DFG + Expression
    FULL = "full"         # + SSA + PDG + Interproc

@dataclass
class BuildConfig:
    # ================================================================
    # Layer 5: Semantic IR (3-Tier Model)
    # ================================================================
    
    semantic_tier: SemanticTier = SemanticTier.BASE
    """
    RFC-036: Semantic IR tier.
    
    - BASE: CFG + Calls (90% AI tasks)
    - EXTENDED: + DFG + Expression (9% AI tasks)
    - FULL: + SSA + PDG (1% AI tasks)
    """
    
    # Fine-grained control (Advanced)
    cfg: bool = True  # Always in BASE+
    dfg: bool = True  # EXTENDED+
    dfg_function_loc_threshold: int = 500  # Skip huge functions
    ssa: bool = False  # FULL only
    expressions: bool = True  # EXTENDED+
    bfg: bool = True  # Internal
    
    # RFC-034
    generic_inference: bool = True
    
    # ================================================================
    # Presets (Primary API)
    # ================================================================
    
    @classmethod
    def for_editor(cls) -> "BuildConfig":
        """
        IDE 로컬 분석 (최소).
        
        Tier: BASE
        Layers: Structural + CFG + Calls
        Use: 함수 이해, 로컬 수정
        Perf: ~800ms (18% of full)
        Memory: ~120MB
        """
        return cls(
            semantic_tier=SemanticTier.BASE,
            cfg=True,
            dfg=False,
            ssa=False,
            expressions=False,
            generic_inference=False,
            lsp_enrichment=False,
        )
    
    @classmethod
    def for_refactoring(cls) -> "BuildConfig":
        """
        리팩토링 (값 추적).
        
        Tier: EXTENDED
        Layers: BASE + DFG + Expression
        Use: Extract method, inline, rename with flow
        Perf: ~2.0s (45% of full)
        Memory: ~250MB
        """
        return cls(
            semantic_tier=SemanticTier.EXTENDED,
            cfg=True,
            dfg=True,
            dfg_function_loc_threshold=500,  # Skip huge functions
            ssa=False,
            expressions=True,
            generic_inference=True,
            lsp_enrichment=False,
        )
    
    @classmethod
    def for_analysis(cls) -> "BuildConfig":
        """
        정밀 분석 (전체).
        
        Tier: FULL
        Layers: All
        Use: Path-sensitive, slicing, taint
        Perf: ~4.4s (100%)
        Memory: ~400MB
        """
        return cls(
            semantic_tier=SemanticTier.FULL,
            cfg=True,
            dfg=True,
            ssa=True,
            expressions=True,
            generic_inference=True,
            heap_analysis=False,
            taint_analysis=False,  # Separate flag
        )
    
    @classmethod
    def for_security(cls) -> "BuildConfig":
        """
        보안 분석 (Taint 포함).
        
        Tier: FULL + Taint
        Layers: All + Taint
        Use: Security audit, vulnerability scan
        Perf: ~5.0s (114%)
        """
        return cls(
            semantic_tier=SemanticTier.FULL,
            cfg=True,
            dfg=True,
            ssa=True,
            expressions=True,
            heap_analysis=True,
            taint_analysis=True,  # Enable taint
        )
    
    def __post_init__(self):
        """
        Validate and derive flags from tier.
        
        SOTA: semantic_tier is Source of Truth.
        Individual flags are derived state (read-only from user perspective).
        """
        # Derive flags from tier (semantic_tier = Source of Truth)
        if self.semantic_tier == SemanticTier.BASE:
            # BASE: CFG + Calls only
            object.__setattr__(self, "cfg", True)
            object.__setattr__(self, "dfg", False)
            object.__setattr__(self, "ssa", False)
            object.__setattr__(self, "expressions", False)
            object.__setattr__(self, "generic_inference", False)
        
        elif self.semantic_tier == SemanticTier.EXTENDED:
            # EXTENDED: + DFG + Expression
            object.__setattr__(self, "cfg", True)
            object.__setattr__(self, "dfg", True)
            object.__setattr__(self, "ssa", False)
            object.__setattr__(self, "expressions", True)
            object.__setattr__(self, "generic_inference", True)
        
        elif self.semantic_tier == SemanticTier.FULL:
            # FULL: All
            object.__setattr__(self, "cfg", True)
            object.__setattr__(self, "dfg", True)
            object.__setattr__(self, "ssa", True)
            object.__setattr__(self, "expressions", True)
            object.__setattr__(self, "generic_inference", True)
        
        # Validation
        if self.dfg_function_loc_threshold <= 0:
            raise ValueError("dfg_function_loc_threshold must be > 0")
```

### 4.2 LayeredIRBuilder 수정

```python
async def _build_semantic_ir_parallel(
    self,
    structural_irs: dict[str, IRDocument],
    config: BuildConfig,
):
    """
    RFC-036: Tier-based semantic IR build.
    
    Tier 1 (BASE): CFG only
    Tier 2 (EXTENDED): + DFG + Expression
    Tier 3 (FULL): + SSA + PDG
    """
    if config.semantic_tier == SemanticTier.BASE:
        # Base: CFG only
        await self._build_cfg_parallel(structural_irs, config)
        return
    
    elif config.semantic_tier == SemanticTier.EXTENDED:
        # Extended: CFG + DFG + Expression
        await self._build_cfg_parallel(structural_irs, config)
        await self._build_dfg_with_threshold(structural_irs, config)
        await self._build_expressions(structural_irs, config)
        return
    
    else:  # FULL
        # Full: All layers
        await self._build_cfg_parallel(structural_irs, config)
        await self._build_dfg_full(structural_irs, config)
        await self._build_expressions(structural_irs, config)
        await self._build_ssa_dominator(structural_irs, config)
        return
```

### 4.3 DFG Threshold 구현

```python
async def _build_dfg_with_threshold(
    self,
    structural_irs: dict[str, IRDocument],
    config: BuildConfig,
):
    """
    RFC-036: Build DFG with function LOC threshold.
    
    Args:
        structural_irs: IR documents
        config: Build configuration with dfg_function_loc_threshold
    """
    from src.contexts.code_foundation.infrastructure.semantic_ir.builder import (
        DefaultSemanticIrBuilder,
    )
    
    builder = DefaultSemanticIrBuilder()
    skipped_count = 0
    built_count = 0
    
    for file_path, ir_doc in structural_irs.items():
        # Get functions
        functions = [n for n in ir_doc.nodes if n.kind.value in ("Function", "Method")]
        
        for func in functions:
            # Check LOC threshold
            func_loc = func.span.end_line - func.span.start_line + 1 if func.span else 0
            
            if func_loc > config.dfg_function_loc_threshold:
                logger.debug(
                    f"RFC-036: Skipping DFG for {func.name} "
                    f"({func_loc} LOC > {config.dfg_function_loc_threshold})"
                )
                skipped_count += 1
                continue
            
            # Build DFG for this function
            # (existing implementation)
            built_count += 1
    
    logger.info(
        f"RFC-036: DFG built for {built_count} functions, "
        f"skipped {skipped_count} (LOC threshold)"
    )
```

---

## 5. 캐시 & 무효화 전략

### 5.1 캐시 키 (정확성 강화)

```python
@dataclass
class SemanticCacheKey:
    """
    RFC-036: Cache key for semantic IR.
    
    SOTA: function_span_hash for accuracy.
    """
    
    file_hash: str              # SHA256 of file content
    function_span_hash: str     # Hash of (start_line, end_line, signature)
    tier: SemanticTier          # BASE/EXTENDED/FULL
    
    @classmethod
    def from_function(
        cls,
        file_hash: str,
        func_node: Node,
        tier: SemanticTier,
    ) -> "SemanticCacheKey":
        """Create cache key from function node."""
        import hashlib
        
        # Compute function span hash
        span_data = f"{func_node.span.start_line}:{func_node.span.end_line}:{func_node.name}"
        span_hash = hashlib.sha256(span_data.encode()).hexdigest()[:16]
        
        return cls(
            file_hash=file_hash,
            function_span_hash=span_hash,
            tier=tier,
        )
    
    def __hash__(self):
        return hash((self.file_hash, self.function_span_hash, self.tier))
```

**function_id 대신 function_span_hash 이유:**
- function_id 재사용 위험 (AST rebuild 시)
- Span 이동 감지 필요
- 더 정확한 무효화

### 5.2 무효화 규칙

| 변경 | 무효화 |
|------|--------|
| 파일 내용 변경 | 해당 파일 모든 tier |
| Import 추가/삭제 | Call Graph (Tier 1+) |
| 함수 시그니처 변경 | Caller Summary (Tier 2+) |

**구현:**
```python
def invalidate_cache(self, changed_files: set[str]):
    """Invalidate semantic IR cache."""
    for file_path in changed_files:
        # Remove all tiers for this file
        keys_to_remove = [
            k for k in self._cache.keys()
            if k.file_hash == compute_hash(file_path)
        ]
        for key in keys_to_remove:
            del self._cache[key]
```

---

## 6. 성능 예상 (Rich 46K LOC)

### 6.1 Tier별 비용

| Tier | Layers | Time | Memory | Use% |
|------|--------|------|--------|------|
| BASE | CFG + Calls | 0.8s | 120MB | 90% |
| EXTENDED | + DFG + Expr | 2.0s | 250MB | 9% |
| FULL | + SSA + PDG | 4.4s | 400MB | 1% |

### 6.2 개선 효과

**Before (현재):**
```
모든 요청: 4.4s (FULL 항상 생성)
```

**After (RFC-036):**
```
90% 요청: 0.8s (BASE) → 82% 개선
 9% 요청: 2.0s (EXTENDED) → 55% 개선
 1% 요청: 4.4s (FULL) → 0% 개선

평균: 0.8*0.9 + 2.0*0.09 + 4.4*0.01 = 0.94s
개선: 4.4s → 0.94s (79% 개선)
```

---

## 7. 구현 계획

### 7.1 Phase 1: Tier Model (3h)

**파일:**
- `build_config.py` (+60 lines)

**내용:**
```python
# SemanticTier enum
# for_editor() / for_refactoring() / for_analysis()
# Tier validation (__post_init__)
```

### 7.2 Phase 2: DFG Threshold (3h)

**파일:**
- `layered_ir_builder.py` (+40 lines)
- `semantic_ir/builder.py` (+30 lines)

**내용:**
```python
# _build_dfg_with_threshold()
# _get_function_loc()
# Skip logic
```

### 7.3 Phase 3: SSA Separation (2h)

**파일:**
- `layered_ir_builder.py` (+20 lines)

**내용:**
```python
# if config.ssa:
#     await self._build_ssa_dominator()
```

**Total: 7-8h**

---

## 8. 테스트 계획

### 8.1 Unit Tests (25 tests)

```python
class TestTierModel:
    """Test 3-tier model."""
    
    def test_base_tier_only_cfg(self):
        """BASE: CFG만 생성"""
        config = BuildConfig.for_editor()
        assert config.semantic_tier == SemanticTier.BASE
        assert config.cfg is True
        assert config.dfg is False
    
    def test_extended_tier_has_dfg(self):
        """EXTENDED: DFG 포함"""
        config = BuildConfig.for_refactoring()
        assert config.semantic_tier == SemanticTier.EXTENDED
        assert config.dfg is True
        assert config.ssa is False
    
    def test_full_tier_has_ssa(self):
        """FULL: SSA 포함"""
        config = BuildConfig.for_analysis()
        assert config.semantic_tier == SemanticTier.FULL
        assert config.ssa is True

class TestDFGThreshold:
    """Test DFG threshold logic."""
    
    def test_small_function_builds_dfg(self):
        """< 500 LOC → DFG"""
    
    def test_large_function_skips_dfg(self):
        """> 500 LOC → Skip"""
    
    def test_threshold_configurable(self):
        """Threshold 변경 가능"""

class TestTierValidation:
    """Test tier constraint validation."""
    
    def test_base_cannot_have_dfg(self):
        """BASE + dfg → ValueError"""
        with pytest.raises(ValueError):
            BuildConfig(
                semantic_tier=SemanticTier.BASE,
                dfg=True  # Invalid
            )
    
    def test_ssa_requires_dfg(self):
        """ssa without dfg → ValueError"""
        with pytest.raises(ValueError):
            BuildConfig(ssa=True, dfg=False)
```

### 8.2 Performance Tests (5 tests)

```python
class TestPerformanceImprovement:
    """Verify performance improvements."""
    
    @pytest.mark.benchmark
    def test_editor_mode_faster(self):
        """Editor < 30% of full."""
        t_full = benchmark_full_tier()
        t_editor = benchmark_base_tier()
        assert t_editor < t_full * 0.3
    
    @pytest.mark.benchmark
    def test_refactoring_mode_balanced(self):
        """Refactoring = 45-55% of full."""
        t_full = benchmark_full_tier()
        t_refactor = benchmark_extended_tier()
        assert 0.45 * t_full < t_refactor < 0.55 * t_full
```

### 8.3 Integration Tests (10 tests)

```python
class TestEndToEnd:
    """Test real-world scenarios."""
    
    async def test_editor_workflow(self):
        """
        IDE workflow:
        1. Open file → BASE tier
        2. 함수 이해 → CFG 사용
        3. 영향 분석 → Call Graph 사용
        """
    
    async def test_refactoring_workflow(self):
        """
        Refactoring workflow:
        1. Extract method → EXTENDED tier
        2. DFG로 변수 추적
        3. 안전성 판단
        """
```

---

## 9. Backward Compatibility

### 9.1 Migration Path

**기존 코드 (변경 불필요):**
```python
# 여전히 동작
builder.build_full(
    files=files,
    enable_semantic_ir=True,  # → FULL tier
)
```

**새 코드 (권장):**
```python
config = BuildConfig.for_refactoring()
result = await builder.build(files, config)
```

### 9.2 Default 동작

```python
# 기본값
semantic_tier = SemanticTier.BASE  # 🆕 Changed from implicit FULL

# Backward compat
enable_semantic_ir=True → semantic_tier=FULL
```

---

## 10. 파일 변경 계획

### 10.1 수정 파일

```
src/contexts/code_foundation/infrastructure/ir/
├── build_config.py                    (+80 lines)
│   ├── SemanticTier enum
│   ├── semantic_tier field
│   ├── Presets (for_editor/refactoring/analysis)
│   └── Tier validation
│
└── layered_ir_builder.py              (+60 lines)
    ├── _build_semantic_ir_parallel() 수정
    ├── _build_dfg_with_threshold()
    └── Tier-based dispatch
```

### 10.2 신규 파일

```
tests/unit/ir/
└── test_semantic_tier.py               (25 tests)
    ├── TestTierModel (5)
    ├── TestDFGThreshold (8)
    ├── TestTierValidation (7)
    └── TestPerformanceImprovement (5)
```

**Total: +140 lines, 25 tests**

---

## 11. 위험 요소 & 완화

### 11.1 복잡도 증가

**위험:**
- 3 tiers + 세부 플래그 = 혼란

**완화:**
- **Preset만 문서화** (Primary API)
- 세부 플래그는 Advanced 섹션
- Tier validation으로 잘못된 조합 차단

### 11.2 첫 요청 지연

**위험:**
- On-demand 첫 호출 시 지연

**완화:**
- BASE tier는 항상 있음 (즉시 응답)
- EXTENDED 필요 시만 0.5-1.2s 추가
- Prefetch 가능 (Background)

### 11.3 캐시 무효화 복잡도

**위험:**
- Dependency tracking 누락 시 stale

**완화:**
- Stateless 설계 (Summary 매번 재생성)
- 명시적 clear_cache() API
- Incremental strategy가 dependency 관리

---

## 12. 성공 지표

| 지표 | Before | After | Target |
|------|--------|-------|--------|
| Editor mode | 4.4s | 0.8s | <1.0s |
| Refactoring | 4.4s | 2.0s | <2.5s |
| Full | 4.4s | 4.4s | ~4.4s |
| 평균 (90/9/1) | 4.4s | 0.94s | <1.5s |
| Memory (Editor) | 400MB | 120MB | <150MB |

---

## 13. Stage 정의 (최종, 단순화)

### 13.1 3-Tier = 3-Stage

**Stage 1: BASE**
- Structural IR (S0)
- CFG (S1)
- Call Graph (S2)

**Stage 2: EXTENDED**
- Stage 1 +
- Expression (S4)
- DFG (S5, with threshold)

**Stage 3: FULL**
- Stage 2 +
- SSA (S6)
- PDG (S7)
- Interprocedural (S8)

**S3 'DefUse-lite' 제거 이유:**
- DFG와 중복
- 명확한 경계 없음
- 실무에서 불필요

---

## 14. 결론

### 14.1 RFC-036 Final 핵심

**3-Tier Model:**
```
90% 사용: BASE (0.8s)
 9% 사용: EXTENDED (2.0s)
 1% 사용: FULL (4.4s)

평균: 79% 개선
```

**설계 원칙:**
- Deterministic (입력 동일 → 출력 동일)
- Tier-based (3단계로 단순화)
- Preset-first (API 명확)

**구현:**
- 7-8h
- +140 lines
- 25 tests

### 14.2 다음 단계

**Option A: RFC-036 구현 (권장)**
- 3-tier model
- 7-8h
- 79% 평균 개선

**Option B: 현재 유지**
- 0h
- 85/100 (충분)

**내 선택: Option A**

---

## 15. 참고

**Related RFCs:**
- RFC-030: SCCP
- RFC-032: Type Inference
- RFC-033: Expression
- RFC-034: Generic/TypeVar
- RFC-035: Lazy Semantic IR (merged into RFC-036)

**Issues Resolved:**
- S3 DefUse-lite 제거 (모호함)
- 8-stage → 3-tier (단순화)
- 캐시 키 단순화

---

## 16. SOTA 확장 (RFC-037 Preview)

### 16.1 P0: Tier Planner (자동 승격)

**목적:** 사용자가 tier 선택하지 않음, 시스템이 요청 분석해서 자동 선택

```python
class TierPlanner:
    """
    RFC-037: Automatic tier selection based on agent intent.
    
    Input: AgentIntent + QueryType + Scope
    Output: SemanticTier + Options
    """
    
    def plan(
        self,
        intent: AgentIntent,      # RENAME, EXTRACT, ADD_PARAM
        query_type: QueryType,     # CALLERS, FLOW, SLICE
        scope: Scope,              # FILE, FUNCTION, REPO
    ) -> tuple[SemanticTier, dict]:
        """
        Determine required tier from agent request.
        
        Examples:
            intent=RENAME, query=CALLERS → BASE
            intent=EXTRACT, query=FLOW → EXTENDED
            intent=REFACTOR, query=SLICE → FULL
        """
        # Mapping logic
        if query_type == QueryType.SLICE:
            return (SemanticTier.FULL, {})
        
        if query_type == QueryType.FLOW:
            return (SemanticTier.EXTENDED, {"dfg_threshold": 500})
        
        # Default: BASE
        return (SemanticTier.BASE, {})
```

### 16.2 P0: Deterministic Provenance

**목적:** 재현 가능성 증명

```python
@dataclass
class BuildProvenance:
    """
    RFC-037: Build provenance for determinism verification.
    
    Enables:
    - Replay builds with identical results
    - Debug non-deterministic issues
    - Audit trail
    """
    
    input_fingerprint: str      # Repo rev + file hashes
    builder_version: str        # Semantic IR builder hash
    config_fingerprint: str     # Tier + flags + thresholds
    dependency_fingerprint: str # Summary/YAML versions
    build_timestamp: str
    
    # Stable ordering guarantee
    node_sort_key: str = "id"   # Stable node iteration
    edge_sort_key: str = "id"   # Stable edge iteration
    parallel_seed: int = 42     # Deterministic parallel
```

### 16.3 P0: Refactor Primitives API

**목적:** AI 에이전트가 직접 사용하는 API

```python
class RefactorPrimitives:
    """
    RFC-037: High-level primitives for AI agents.
    
    Built on Semantic IR tiers.
    """
    
    # BASE tier
    def get_callers(self, symbol: str) -> list[str]:
        """O(1) via Call Graph."""
    
    def rename_impact(self, symbol: str) -> RenameImpact:
        """Occurrences + dynamic risk."""
    
    def extract_method_safety(self, range: Range) -> SafetyReport:
        """CFG region + side-effect summary."""
    
    # EXTENDED tier
    def value_origin(self, var: str, at_line: int) -> list[Origin]:
        """Backward slice-lite via DFG."""
    
    def side_effect_summary(self, function: str) -> SideEffects:
        """Heap/IO/calls analysis."""
    
    # FULL tier
    def path_sensitive_origin(self, var: str, path: list) -> Origin:
        """Precise origin via SSA."""
    
    def program_slice(self, criterion: Criterion) -> Slice:
        """PDG-based slicing."""
```

---

## 17. Next RFCs

**RFC-037: Tier Planner + Deterministic Provenance**
- Priority: P0
- Estimated: 8-10h
- Focus: 자동 tier 선택, 재현성 보장

**RFC-038: Refactor Primitives API**
- Priority: P0
- Estimated: 12h
- Focus: AI 에이전트 직접 사용 API

**RFC-039: Function-Level Invalidation**
- Priority: P1
- Estimated: 6h
- Focus: 세밀한 캐시 무효화

---

**Last Updated:** 2025-12-21
**Status:** 🟢 Ready for Implementation
**Next:** RFC-037 (Tier Planner + Provenance)

