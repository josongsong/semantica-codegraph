# ADR: Points-to Analysis Configuration Design

**Status**: Proposed
**Date**: 2025-12-29
**Decision**: L6 PTA를 단일 Stage로 유지, Config로 알고리즘 선택

---

## Context

L6 Points-to Analysis는 현재 여러 알고리즘을 지원:
- **Steensgaard**: O(n·α(n)), 빠르지만 부정확 (unification-based)
- **Andersen**: O(n²), 느리지만 정확 (inclusion-based)
- **Andersen-Lite**: Early cutoff variant
- **Hybrid**: Steensgaard → Andersen sequential refinement

**질문**: 각 알고리즘을 별도 Stage(L6a, L6b, L6c...)로 분리할까?

---

## Decision

✅ **단일 L6 Stage 유지 + PTAMode enum으로 알고리즘 선택**

```rust
pub enum PTAMode {
    /// Steensgaard: O(n·α(n)), union-find based (13,771x faster!)
    Fast,

    /// Andersen: O(n²), inclusion-based with SOTA optimizations
    Precise,

    /// Andersen with early cutoff (Lite variant)
    PreciseLite { max_iterations: usize },

    /// Hybrid: Steensgaard first, then Andersen refinement
    Hybrid,

    /// Auto: Choose based on constraint count
    Auto { threshold: usize },
}
```

---

## Rationale

### 왜 세분화하지 않는가?

#### 1. 실제 사용 패턴
- **99% of users**: Preset 기반 선택 (Fast/Balanced/Thorough)
  - Fast → Steensgaard
  - Balanced → Auto (threshold: 10K)
  - Thorough → Andersen
- **1% of users**: 명시적 알고리즘 선택 (security audit)
- **동시에 여러 PTA 실행**: 거의 없음 (중복, 비효율)

#### 2. Simplicity
- Stage 분리 시 L1-L37 → L1-L50+ (급증)
- 사용자 혼란: "어떤 PTA를 선택해야 하나?"
- Dependency graph 복잡도 증가

#### 3. RFC-CONFIG-SYSTEM 일관성
```rust
// 현재 구조가 Preset 체계와 자연스럽게 일치
impl Preset {
    pub fn pta_config(&self) -> PTAConfig {
        match self {
            Fast => PTAConfig { mode: PTAMode::Fast, .. },
            Balanced => PTAConfig { mode: PTAMode::Auto { threshold: 10000 }, .. },
            Thorough => PTAConfig { mode: PTAMode::Precise, .. },
        }
    }
}
```

#### 4. 확장 가능성
미래에 새 알고리즘(e.g., BDD-based, Demand-driven) 추가 시:
- ✅ `PTAMode::BDD` enum variant 추가만 하면 됨
- ❌ 새 Stage L6e 추가는 과도한 복잡도

---

## Implementation

### 1. PTAMode 확장

```rust
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum PTAMode {
    /// Steensgaard: O(n·α(n))
    /// - 13,771x faster than Andersen
    /// - Less precise (unification = may-alias everything)
    /// - Use case: CI/CD, large codebases, quick feedback
    Fast,

    /// Andersen: O(n²) worst case, O(n) average with SCC+Wave
    /// - SOTA optimizations: SCC collapse, Wave propagation, Sparse bitmap
    /// - More precise (inclusion-based = separate points-to sets)
    /// - Use case: Security audit, critical code paths
    Precise,

    /// Andersen with iteration limit (Lite variant)
    /// - Balance between Fast and Precise
    /// - Early cutoff when max_iterations reached
    /// - Use case: Moderate precision needs
    PreciseLite { max_iterations: usize },

    /// Hybrid: Steensgaard → Andersen refinement
    /// - Phase 1: Steensgaard for initial approximation
    /// - Phase 2: Andersen for refinement
    /// - Use case: Large projects with critical subsets
    Hybrid,

    /// Auto: Dynamic selection based on constraint count
    /// - < threshold: Precise (small enough for accuracy)
    /// - >= threshold: Fast (too large, prioritize speed)
    Auto { threshold: usize },
}
```

### 2. Waterfall Report 개선

**Before**:
```
Stage 6: L6_PointsTo
  Duration: 4ms (1.7% of total)
```

**After** (Option 1: Simple suffix):
```
Stage 6: L6_PointsTo (Steensgaard)
  Duration: 4ms (1.7% of total)
```

**After** (Option 2: Detailed breakdown):
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 6: L6_PointsTo (Steensgaard)                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  Algorithm:      Fast (O(n·α(n)))                                           │
│  Variables:      3,267                                                      │
│  Constraints:    30,446                                                     │
│  Alias Pairs:    3,267                                                      │
│  Duration:       4ms (1.7% of total)                                        │
│  Status:         ✅ SUCCESS                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Config Integration

```rust
// packages/codegraph-ir/src/pipeline/processor/stages/advanced.rs
pub fn run_points_to_analysis(
    nodes: &[Node],
    edges: &[Edge],
    config: &PTAConfig,  // ✅ From ValidatedConfig
) -> Result<PointsToSummary> {
    let mut analyzer = PointsToAnalyzer::new(config.clone());

    // Extract constraints from IR
    let extractor = PTAIRExtractor::new(nodes, edges);
    for constraint in extractor.extract_constraints() {
        analyzer.add_constraint(constraint);
    }

    // Solve with selected algorithm
    let result = analyzer.solve();

    // Log algorithm used (for waterfall report)
    eprintln!("[L6 PTA] Algorithm: {:?}, Duration: {:.2}ms",
              result.stats.mode_used, result.stats.duration_ms);

    Ok(PointsToSummary {
        graph: result.graph,
        stats: result.stats,
    })
}
```

### 4. Preset Definitions

```rust
impl Preset {
    pub fn pta_config(&self) -> PTAConfig {
        match self {
            Self::Fast => PTAConfig {
                mode: PTAMode::Fast,
                field_sensitive: false,
                max_iterations: None,  // Not used for Steensgaard
                auto_threshold: 5000,
                enable_scc: false,     // Steensgaard doesn't use SCC
                enable_wave: false,
                enable_parallel: true,
            },
            Self::Balanced => PTAConfig {
                mode: PTAMode::Auto { threshold: 10000 },
                field_sensitive: true,
                max_iterations: Some(10),  // For Andersen fallback
                auto_threshold: 10000,
                enable_scc: true,
                enable_wave: true,
                enable_parallel: true,
            },
            Self::Thorough => PTAConfig {
                mode: PTAMode::Precise,
                field_sensitive: true,
                max_iterations: Some(50),
                auto_threshold: 100000,
                enable_scc: true,
                enable_wave: true,
                enable_parallel: true,
            },
            Self::Custom => PTAConfig::default(),
        }
    }
}
```

---

## Consequences

### Positive

- ✅ **Simplicity**: 단일 L6 stage, 명확한 선택지
- ✅ **Flexibility**: Config로 세밀한 제어 가능
- ✅ **Consistency**: RFC-CONFIG-SYSTEM과 일관성
- ✅ **Extensibility**: 새 알고리즘 추가 용이
- ✅ **User-friendly**: 90% use case는 Preset만으로 해결

### Negative

- ⚠️ **Waterfall granularity**: L6 내부 알고리즘 선택이 stage별로 분리 안 됨
  - **Mitigation**: Algorithm suffix + detailed metrics in report
- ⚠️ **Dependency graph**: "Taint depends on PTA" 표현 시 어떤 PTA인지 불명확
  - **Mitigation**: Config로 명시 (`taint.use_points_to` + `pta.mode`)

---

## Alternatives Considered

### Alternative 1: Stage 분리 (L6a, L6b, L6c)

```rust
pub enum PTAStage {
    L6a_Steensgaard,
    L6b_Andersen,
    L6c_AndersenLite,
    L6d_Hybrid,
}
```

**Rejected because**:
- Stage 수 급증 (L1-L37 → L1-L50+)
- 사용자 혼란 (어떤 stage를 enable?)
- 동시 실행 거의 없음 (중복)

### Alternative 2: Submodule 구조

```rust
L6_PointsTo/
├── steensgaard (enabled: auto)
├── andersen (enabled: auto)
└── hybrid (enabled: false)
```

**Rejected because**:
- 복잡도 증가 (nested stage control)
- 실질적 이득 없음 (여전히 하나만 실행)

---

## Migration Path

### Phase 1: PTAMode 확장 (Week 1)
- [ ] `PreciseLite { max_iterations }` variant 추가
- [ ] `Auto { threshold }` variant 추가
- [ ] `AnalyzerResult`에 `mode_used: PTAMode` 추가

### Phase 2: Waterfall Report 개선 (Week 2)
- [ ] `L6_PointsTo` → `L6_PointsTo (Steensgaard)` suffix
- [ ] PTA metrics 추가 (variables, constraints, alias pairs)
- [ ] Algorithm complexity 표시 (O(n·α(n)) / O(n²))

### Phase 3: Config 통합 (Week 3)
- [ ] RFC-CONFIG-SYSTEM `PTAConfig` 정의
- [ ] Preset 구현 (Fast/Balanced/Thorough)
- [ ] Validation + cross-stage checks

---

## Examples

### Example 1: CI/CD (Fast)
```rust
let config = PipelineConfig::preset(Preset::Fast).build()?;

// Effective PTA config:
// - mode: Fast (Steensgaard)
// - duration: 4ms for 30K constraints
// - precision: Conservative (may-alias all)
```

### Example 2: Security Audit (Precise)
```rust
let config = PipelineConfig::preset(Preset::Thorough)
    .pta(|c| PTAConfig {
        mode: PTAMode::Precise,
        max_iterations: Some(100),  // Allow more iterations
        ..c
    })
    .build()?;

// Effective PTA config:
// - mode: Precise (Andersen with SCC+Wave)
// - duration: ~10s for 30K constraints
// - precision: High (separate points-to sets)
```

### Example 3: Balanced (Auto)
```rust
let config = PipelineConfig::preset(Preset::Balanced).build()?;

// Effective PTA config:
// - mode: Auto { threshold: 10000 }
// - Small projects (<10K constraints): Precise
// - Large projects (>=10K constraints): Fast
// - Duration: Adaptive
```

### Example 4: Custom (PreciseLite)
```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .pta(|c| PTAConfig {
        mode: PTAMode::PreciseLite { max_iterations: 5 },
        ..c
    })
    .build()?;

// Effective PTA config:
// - mode: PreciseLite (Andersen with early cutoff)
// - duration: ~1s for 30K constraints
// - precision: Medium (better than Fast, faster than Precise)
```

---

## References

- [RFC-CONFIG-SYSTEM.md](./RFC-CONFIG-SYSTEM.md) - Configuration design
- [PTA_VERIFICATION_COMPLETE.md](./PTA_VERIFICATION_COMPLETE.md) - Performance verification
- [ADR-072: Clean Rust-Python Architecture](./adr/ADR-072-clean-rust-python-architecture.md)

---

**Decision**: Approved
**Date**: 2025-12-29
