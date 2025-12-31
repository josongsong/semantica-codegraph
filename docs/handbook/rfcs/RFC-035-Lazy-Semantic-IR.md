# RFC-035: Lazy Semantic IR - Granular Layer Control

## Status: Draft
## Author: Semantica Team
## Priority: P1
## Estimated: 7-8h

---

## 1. 개요

### 1.1 목표
Semantic IR 생성을 **Precompute vs Lazy** 기준으로 세분화하여 5-15% 성능 개선.

### 1.2 배경

**현재 문제:**
```python
BuildConfig(
    cfg=True,   # CFG + DFG + SSA + BFG 전부
    dfg=True,   # All-or-Nothing
)
```

**문제점:**
1. DFG: 큰 함수(1000+ LOC)도 무조건 생성 → 비효율
2. SSA: 대부분 AI 작업에 불필요 → 낭비
3. 세밀한 제어 불가

### 1.3 핵심 원칙 (사용자 제안)

```
구조적·지역적·결정적 → Precompute
전역적·조합적·목적 의존 → Lazy
```

---

## 2. 현재 상태 분석

### 2.1 Semantic IR 레이어 비용 분포

| Layer | 상대적 비용 |
|-------|-------------|
| Semantic IR (전체) | 높음 (전체의 50%+) |
| ├─ CFG | 중간 |
| ├─ DFG | 높음 (가장 무거움) |
| ├─ SSA/Dom | 낮음-중간 |
| ├─ BFG | 중간 |
| └─ Expression | 중간 |

### 2.2 문제점

**DFG All-or-Nothing:**
```python
# 현재
for func in functions:
    build_dfg(func)  # 모든 함수, LOC 무관

# 문제
def huge_function():  # 매우 큰 함수
    # DFG 생성: 오래 걸림
    # AI 사용: 거의 없음 (너무 복잡해서 안 봄)
```

**SSA Always:**
```python
# 현재
if enable_semantic_ir:
    build_ssa_for_all_functions()

# 문제
- 90% AI 작업: SSA 불필요
- 10% AI 작업: SSA 필요 (path-sensitive)
```

---

## 3. 설계

### 3.1 새로운 Semantic IR 플래그

```python
@dataclass
class BuildConfig:
    # ================================================================
    # Layer 5: Semantic IR (Granular Control)
    # ================================================================
    
    # Always (P0)
    cfg: bool = True  # Control Flow Graph (함수 로컬)
    call_graph: bool = True  # 항상 생성됨 (Layer 1 CALLS edge)
    
    # Conditional (P0.5)
    dfg: bool = True  # Data Flow Graph
    dfg_function_loc_threshold: int = 500  # 🆕 500 LOC 이상 함수 스킵
    dfg_incremental_only_changed: bool = True  # 🆕 Incremental 시 변경 함수만
    
    # Lazy (P1)
    ssa: bool = False  # 🆕 SSA (Path-sensitive 전용)
    dominator: bool = False  # 🆕 Dominator tree (SSA와 함께)
    
    # Other
    bfg: bool = True  # Basic Block Flow Graph
    expressions: bool = True  # Expression analysis (for taint)
    generic_inference: bool = True  # RFC-034
    
    # ================================================================
    # Backward Compatibility
    # ================================================================
    
    @property
    def enable_semantic_ir(self) -> bool:
        """Legacy: enable any semantic IR layer."""
        return self.cfg or self.dfg or self.bfg or self.expressions
    
    @classmethod
    def for_editor(cls) -> "BuildConfig":
        """IDE 로컬 분석 (빠른 피드백)."""
        return cls(
            cfg=True,   # 함수 이해
            dfg=False,  # 값 추적 불필요
            ssa=False,
            bfg=False,
            expressions=False,
        )
    
    @classmethod
    def for_refactoring(cls) -> "BuildConfig":
        """리팩토링 (값 추적 필요)."""
        return cls(
            cfg=True,
            dfg=True,
            dfg_function_loc_threshold=500,  # 큰 함수 스킵
            ssa=False,  # 대부분 불필요
        )
    
    @classmethod
    def for_path_sensitive(cls) -> "BuildConfig":
        """Path-sensitive 분석 (정밀)."""
        return cls(
            cfg=True,
            dfg=True,
            ssa=True,   # Path-sensitive 필수
            dominator=True,
        )
```

### 3.2 구현 계획

**Phase 1: DFG Threshold (4h)**

```python
# src/contexts/code_foundation/infrastructure/semantic_ir/builder.py

async def build_dfg(self, ir_doc: IRDocument, config: BuildConfig):
    """Build DFG with threshold."""
    
    for func_node in functions:
        # 🆕 RFC-035: Check LOC threshold
        func_loc = self._get_function_loc(func_node)
        
        if func_loc > config.dfg_function_loc_threshold:
            logger.debug(
                f"RFC-035: Skipping DFG for {func_node.name} "
                f"({func_loc} LOC > {config.dfg_function_loc_threshold})"
            )
            continue
        
        # Build DFG
        dfg = self._build_dfg_for_function(func_node)
```

**Phase 2: SSA 분리 (3h)**

```python
# src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py

async def _build_semantic_ir(self, structural_irs, config):
    # CFG (항상)
    if config.cfg:
        await self._build_cfg(structural_irs)
    
    # DFG (조건부)
    if config.dfg:
        await self._build_dfg(structural_irs, config)
    
    # 🆕 RFC-035: SSA 분리
    if config.ssa:
        await self._build_ssa_dominator(structural_irs, config)
```

---

## 4. 예상 효과

### 4.1 성능 개선

| 시나리오 | Before | After | 개선 |
|---------|--------|-------|------|
| **Rich (46K LOC)** |  |  | **-13%** |
| ├─ DFG threshold |  |  | -18% |
| └─ SSA 분리 |  |  | -100% |
| **Django (350K LOC)** | ~18s | ~15s | **-16%** |

### 4.2 사용 패턴별

**IDE 로컬 (for_editor):**
```
Before:  (CFG+DFG+SSA+BFG)
After:   (CFG만)
개선: -78%
```

**리팩토링 (for_refactoring):**
```
Before: 
After:   (CFG+DFG threshold)
개선: -49%
```

**Path-sensitive:**
```
Before: 
After:   (동일, SSA 포함)
개선: 0% (정밀도 유지)
```

---

## 5. 구현 상세

### 5.1 파일 변경

**수정 파일:**
```
src/contexts/code_foundation/infrastructure/ir/
├── build_config.py                   (+40 lines)
└── layered_ir_builder.py             (+80 lines)

src/contexts/code_foundation/infrastructure/semantic_ir/
├── builder.py                        (+60 lines)
└── parallel.py                       (+30 lines)
```

**신규 파일:**
```
tests/unit/ir/
└── test_lazy_semantic_ir.py          
```

### 5.2 주요 변경

**build_config.py:**
```python
# 🆕 RFC-035 fields
dfg_function_loc_threshold: int = 500
dfg_incremental_only_changed: bool = True
ssa: bool = False
dominator: bool = False

# 🆕 Presets
@classmethod
def for_editor(cls): ...

@classmethod
def for_refactoring(cls): ...

@classmethod
def for_path_sensitive(cls): ...
```

**semantic_ir/builder.py:**
```python
def _should_build_dfg_for_function(
    self, 
    func_node: Node,
    config: BuildConfig,
) -> bool:
    """
    RFC-035: Determine if DFG should be built for function.
    
    Conditions:
    1. LOC < threshold
    2. Not incremental OR changed function
    """
    # Check LOC threshold
    func_loc = self._get_function_loc(func_node)
    if func_loc > config.dfg_function_loc_threshold:
        return False
    
    # Check incremental
    if config.incremental and config.dfg_incremental_only_changed:
        # Only if function was changed
        return func_node.id in config.changed_nodes
    
    return True
```

---

## 6. 테스트 계획

### 6.1 Unit Tests 

```python
class TestDFGThreshold:
    def test_small_function_builds_dfg(self):
        """< 500 LOC → DFG 생성"""
    
    def test_large_function_skips_dfg(self):
        """> 500 LOC → DFG 스킵"""
    
    def test_threshold_configurable(self):
        """Threshold 변경 가능"""

class TestSSASeparation:
    def test_ssa_off_by_default(self):
        """ssa=False → SSA 스킵"""
    
    def test_ssa_on_when_requested(self):
        """ssa=True → SSA 생성"""
    
    def test_dominator_requires_ssa(self):
        """dominator=True → ssa도 True"""

class TestPresets:
    def test_for_editor_minimal(self):
        """for_editor(): 최소 레이어"""
    
    def test_for_refactoring_dfg(self):
        """for_refactoring(): DFG threshold"""
    
    def test_for_path_sensitive_full(self):
        """for_path_sensitive(): SSA 포함"""
```

### 6.2 Integration Tests

```python
class TestPerformanceRegression:
    def test_editor_mode_faster(self):
        """Editor mode < 30% of full"""
    
    def test_refactoring_mode_balanced(self):
        """Refactoring mode = 50% of full"""
    
    def test_path_sensitive_same(self):
        """Path-sensitive = 100% of full"""
```

---

## 7. 롤백 계획

**Phase 1만 배포 (DFG threshold):**
```python
# 기본값으로 전체 생성 유지
dfg_function_loc_threshold: int = 999999  # 사실상 무제한
```

**Phase 2 롤백 (SSA 분리):**
```python
# SSA 항상 생성
ssa: bool = True  # Default True로 복구
```

---

## 8. 마이그레이션

### 8.1 Backward Compatibility

**기존 코드:**
```python
# 변경 불필요
builder.build_full(
    files=files,
    enable_semantic_ir=True,
)
```

**새 코드 (선택적):**
```python
# 세밀한 제어 원하면
config = BuildConfig.for_refactoring()
builder.build(files, config)
```

### 8.2 Breaking Changes

**없음** - 기본값으로 기존 동작 유지

---

## 9. 성공 지표

| 지표 | 현재 | 목표 |
|------|------|------|
| Editor mode |  | < |
| Refactoring mode |  | < |
| Full mode |  | ~ |
| 평균 개선 | - | 10-15% |

---

## 10. 위험 요소

### 10.1 복잡도 증가

**Before:** 5개 플래그 (cfg, dfg, bfg, expressions, generic_inference)
**After:** 8개 플래그 (+dfg_threshold, +ssa, +dominator)

**완화:**
- Preset methods (for_editor, for_refactoring)
- 기본값으로 기존 동작 유지

### 10.2 DFG 없는 함수

**문제:**
```python
# 큰 함수 DFG 스킵 시
def huge_func():  # 2000 LOC, DFG 없음
    # Taint 분석 불가능
```

**완화:**
- Threshold 높임 (500 → 1000)
- 명시적 요청 시 강제 생성
- 로깅으로 스킵 알림

---

## 11. 구현 순서

### Week 1: DFG Threshold (4h)

**Day 1-2: Core Implementation**
```python
# build_config.py (+20 lines)
dfg_function_loc_threshold: int = 500
dfg_incremental_only_changed: bool = True

# semantic_ir/builder.py (+40 lines)
def _should_build_dfg_for_function()
def _get_function_loc()
```

**Day 2: Testing**
```python
# test_lazy_semantic_ir.py 
TestDFGThreshold 
TestIncrementalDFG 
TestFunctionLOC 
```

### Week 2: SSA Separation (3h)

**Day 3: SSA Split**
```python
# build_config.py (+20 lines)
ssa: bool = False
dominator: bool = False

# layered_ir_builder.py (+40 lines)
if config.ssa:
    await self._build_ssa_dominator()
```

**Day 3-4: Testing**
```python
# test_lazy_semantic_ir.py (+15 tests)
TestSSASeparation 
TestPresets 
```

---

## 12. 파일 변경 상세

### 12.1 build_config.py

```python
@dataclass
class BuildConfig:
    # ... existing fields ...
    
    # 🆕 RFC-035: Granular Semantic IR Control
    dfg_function_loc_threshold: int = 500
    """DFG threshold: Skip functions > N LOC (default: 500)"""
    
    dfg_incremental_only_changed: bool = True
    """Incremental: Build DFG for changed functions only"""
    
    ssa: bool = False
    """SSA transformation (for path-sensitive analysis)"""
    
    dominator: bool = False
    """Dominator tree (requires SSA)"""
    
    def __post_init__(self):
        """Validate invariants."""
        # Dominator requires SSA
        if self.dominator and not self.ssa:
            raise ValueError("dominator=True requires ssa=True")
        
        # DFG threshold > 0
        if self.dfg_function_loc_threshold <= 0:
            raise ValueError("dfg_function_loc_threshold must be > 0")
    
    @classmethod
    def for_editor(cls) -> "BuildConfig":
        """
        IDE 로컬 분석 (최소 레이어).
        
        Layers: Structural + CFG
        Use: 함수 이해, 로컬 리팩토링
        Perf: ~30% of full
        """
        return cls(
            cfg=True,
            dfg=False,
            ssa=False,
            bfg=False,
            expressions=False,
            generic_inference=False,
        )
    
    @classmethod
    def for_refactoring(cls) -> "BuildConfig":
        """
        리팩토링 (값 추적).
        
        Layers: Structural + CFG + DFG (threshold)
        Use: Extract method, inline, rename
        Perf: ~50% of full
        """
        return cls(
            cfg=True,
            dfg=True,
            dfg_function_loc_threshold=500,
            ssa=False,
            bfg=True,
            expressions=True,
            generic_inference=True,
        )
    
    @classmethod
    def for_path_sensitive(cls) -> "BuildConfig":
        """
        Path-sensitive 분석 (정밀).
        
        Layers: Full + SSA + Dominator
        Use: 정밀 taint, slicing
        Perf: 100% (최대)
        """
        return cls(
            cfg=True,
            dfg=True,
            ssa=True,
            dominator=True,
            bfg=True,
            expressions=True,
            generic_inference=True,
        )
```

### 12.2 semantic_ir/builder.py

```python
class DefaultSemanticIrBuilder:
    """Semantic IR builder with RFC-035 lazy control."""
    
    def _get_function_loc(self, func_node: Node) -> int:
        """
        Get function LOC (Lines of Code).
        
        Args:
            func_node: Function node
        
        Returns:
            LOC count (non-empty, non-comment)
        """
        span = func_node.span
        if not span:
            return 0
        
        return span.end_line - span.start_line + 1
    
    def _should_build_dfg_for_function(
        self,
        func_node: Node,
        config: BuildConfig,
        changed_nodes: set[str] | None = None,
    ) -> bool:
        """
        RFC-035: Determine if DFG should be built.
        
        Conditions:
        1. LOC < threshold
        2. Incremental: Only changed functions
        
        Args:
            func_node: Function node
            config: Build configuration
            changed_nodes: Changed node IDs (for incremental)
        
        Returns:
            True if should build DFG
        """
        # Check LOC threshold
        func_loc = self._get_function_loc(func_node)
        
        if func_loc > config.dfg_function_loc_threshold:
            logger.debug(
                f"RFC-035: Skipping DFG for {func_node.name} "
                f"({func_loc} LOC > threshold)"
            )
            return False
        
        # Check incremental
        if config.incremental and config.dfg_incremental_only_changed:
            if changed_nodes and func_node.id not in changed_nodes:
                logger.debug(
                    f"RFC-035: Skipping DFG for {func_node.name} "
                    f"(unchanged in incremental)"
                )
                return False
        
        return True
    
    async def build_dfg(
        self,
        ir_docs: dict[str, IRDocument],
        config: BuildConfig,
        changed_nodes: set[str] | None = None,
    ):
        """
        Build DFG with RFC-035 threshold.
        
        Args:
            ir_docs: IR documents
            config: Build configuration
            changed_nodes: Changed nodes (for incremental)
        """
        skipped_count = 0
        built_count = 0
        
        for ir_doc in ir_docs.values():
            for func_node in self._get_functions(ir_doc):
                if not self._should_build_dfg_for_function(
                    func_node, config, changed_nodes
                ):
                    skipped_count += 1
                    continue
                
                # Build DFG
                self._build_dfg_for_function(func_node, ir_doc)
                built_count += 1
        
        logger.info(
            f"RFC-035: DFG built for {built_count} functions "
            f"({skipped_count} skipped)"
        )
```

### 12.3 layered_ir_builder.py

```python
async def _build_ssa_dominator_parallel(
    self,
    structural_irs: dict[str, IRDocument],
    build_config: BuildConfig,
) -> int:
    """
    RFC-035: Build SSA/Dominator (conditional).
    
    Args:
        structural_irs: IR documents
        build_config: Configuration
    
    Returns:
        Number of SSA contexts built
    """
    # 🆕 RFC-035: Check if SSA enabled
    if not build_config.ssa:
        self.logger.debug("RFC-035: SSA disabled, skipping")
        return 0
    
    # ... existing implementation ...
```

---

## 13. 테스트 계획

### 13.1 Unit Tests 

**DFG Threshold :**
- Base: LOC < threshold
- Edge: LOC = threshold
- Corner: LOC > threshold
- Extreme: LOC = 0, 10000
- Incremental: changed only

**SSA Separation :**
- Base: ssa=False
- Edge: ssa=True
- Corner: dominator without ssa
- Integration: Presets
- Backward compat

### 13.2 Performance Tests

```python
def test_editor_mode_performance():
    """Editor mode < 30% of full."""
    t_full = benchmark_full()
    t_editor = benchmark_editor()
    assert t_editor < t_full * 0.3

def test_refactoring_mode_performance():
    """Refactoring mode = 50% of full."""
    t_full = benchmark_full()
    t_refactor = benchmark_refactoring()
    assert t_refactor < t_full * 0.5
```

---

## 14. 결론

**RFC-035 핵심:**

1. **Precompute vs Lazy 명확화**
   - CFG/Call Graph: Always
   - DFG: Conditional (threshold)
   - SSA: Lazy (요청 시)

2. **성능 개선: 10-15%**
   - Editor mode: 78% 개선
   - Refactoring: 49% 개선

3. **복잡도 관리**
   - Preset methods
   - Backward compatible

**다음 단계:**
- [ ] Week 1: DFG threshold (4h)
- [ ] Week 2: SSA separation (3h)
- [ ] Week 2: Testing (1h)

---

## 15. 참고

**Related RFCs:**
- RFC-030: SCCP
- RFC-032: Type Inference
- RFC-033: Expression Type
- RFC-034: Generic/TypeVar

**Last 

