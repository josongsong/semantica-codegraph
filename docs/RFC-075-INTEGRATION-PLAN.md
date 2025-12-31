# RFC-075: SOTA 갭 해소 통합 계획 (Integration Plan)
**Status**: Draft
**Author**: Integration Team
**Created**: 2025-12-29
**Updated**: 2025-12-29
**Related**: [RFC-074-SOTA-GAP-ROADMAP.md](RFC-SOTA-GAP-ROADMAP.md), [SOTA_GAP_ANALYSIS_FINAL.md](SOTA_GAP_ANALYSIS_FINAL.md)

---

## 📋 요약 (Executive Summary)

본 RFC는 RFC-074에서 제안된 SOTA 갭 해소 로드맵을 **현재 레포지토리 구조에 통합**하는 구체적 실행 계획입니다.

**목표**:
- RFC-074의 Phase 1-3 작업을 현재 Rust 파이프라인에 통합
- 기존 Benchmark 시스템 (RFC-002)과 Ground Truth 기반 검증 자동화
- Configuration 시스템과의 매끄러운 통합 (향후 RFC-001 기반)
- 점진적 배포 전략 (feature flag, A/B testing)

**핵심 원칙**:
1. **No Breaking Changes**: 기존 L1-L16 stage 호환성 유지
2. **Incremental Rollout**: Feature flag로 점진적 활성화
3. **Benchmark-driven Development**: 모든 변경사항은 Ground Truth로 검증
4. **SSOT (Single Source of Truth)**: Rust 구현 = 유일한 진실

---

## 🔍 현재 레포지토리 상황 (As-Is)

### 1. 최근 작업 내역 (2주간)

```bash
# 주요 커밋
524d77c2 - SQLite ChunkStore 구현 완료 (comprehensive testing)
160680a7 - L1-L37 전체 StageId enum + dependency graph 완성
5cdb5d97 - Python 145개 파일 삭제, 100% Rust 마이그레이션
a2c32c48 - Pipeline orchestrator unwrap() 제거 (에러 처리 강화)
```

**시사점**:
- ✅ **Rust-only 아키텍처 확립**: Python 레거시 제거 완료
- ✅ **파이프라인 구조 완성**: L1-L37 stage 정의 완료 (구현은 L1-L16)
- ✅ **프로덕션 준비도 향상**: unwrap() 제거, 에러 처리 강화
- 🎯 **다음 단계**: 미구현 stage (L17+) 구현 필요

### 2. Benchmark 시스템 (RFC-002) ✅ 구축 완료

**구현 현황**:
```rust
// packages/codegraph-ir/src/benchmark/
├── config.rs              // BenchmarkConfig + Tolerance
├── ground_truth.rs        // GroundTruth + GroundTruthStore
├── validator.rs           // Ground Truth validation
├── runner.rs              // BenchmarkRunner
├── result.rs              // BenchmarkResult + BenchmarkDiff
├── repository.rs          // Repository (small/medium/large)
└── report/                // JSON, Markdown, Terminal, HTML

// 기존 벤치마크 레포지토리
tools/benchmark/repo-test/
├── small/typer/           // ~5K LOC
├── medium/              // (미구성)
└── large/pydantic/        // ~50K LOC
```

**핵심 기능**:
1. **Ground Truth 관리**:
   - `GroundTruth::from_results()`: 3회 실행 평균으로 baseline 생성
   - `GroundTruthStore`: JSON 파일 기반 저장 (`target/benchmark_results/ground_truth/`)
   - Tolerance: duration ±5%, memory ±10%, count exact match

2. **자동 Regression 탐지**:
   - `GroundTruthValidator::validate()`: 실행 결과 vs baseline 비교
   - `Severity`: Critical (20%+), Warning (10-20%), Info (5-10%)
   - `ValidationResult`: Pass/Fail with detailed violations

3. **Multi-repo 지원**:
   - `Repository::from_path()`: 자동 언어/카테고리 탐지
   - `RepoCategory`: Small (<10K), Medium (10-100K), Large (100K+)

**시사점**:
- ✅ **Ground Truth 시스템 완비**: 새로운 분석 추가 시 즉시 검증 가능
- ✅ **자동화된 Regression 탐지**: CI/CD 통합 준비 완료
- 🎯 **작업 필요**: Medium-size 레포지토리 추가, Juliet/OWASP Benchmark 통합

### 3. Configuration 시스템 (현재 상태)

**구현 현황**:
```rust
// packages/codegraph-ir/src/pipeline/end_to_end_config.rs
pub struct E2EPipelineConfig {
    pub stages: StageControl,     // L1-L37 individual toggles
    pub cache_config: CacheConfig,
    pub parallel_config: ParallelConfig,
    // ... (200 LOC)
}

pub struct StageControl {
    pub enable_ir_build: bool,           // L1
    pub enable_chunking: bool,           // L2
    pub enable_taint: bool,              // L14
    pub enable_points_to: bool,          // L10
    pub enable_concurrency_analysis: bool, // L18
    // ... 총 37개 stage flags
}

// packages/codegraph-ir/src/benchmark/config.rs
pub struct BenchmarkConfig {
    pub pipeline_config: PipelineConfig,  // ← 이건 뭐지? (단순 버전)
    pub benchmark_opts: BenchmarkOptions,
}
```

**문제점**:
1. **Config 파편화**:
   - `PipelineConfig` (단순 버전, 6개 필드)
   - `E2EPipelineConfig` (완전 버전, 37개 stage)
   - **불일치**: `BenchmarkConfig`가 단순 버전 사용 중

2. **RFC-001 미구현**:
   - Preset 시스템 없음 (Fast/Balanced/Thorough)
   - Stage override builder 없음
   - YAML 로딩 없음 (`serde_yaml` dependency만 추가됨)

**시사점**:
- ⚠️ **Config 시스템 개선 필요**: RFC-001 구현 or E2EPipelineConfig 활용
- 🎯 **우선순위**: 새로운 분석 stage를 추가하기 전에 Config 통합 필요

### 4. Pipeline 구조 (L1-L37)

**구현 현황** (실제 코드 확인):
```rust
// packages/codegraph-ir/src/pipeline/end_to_end_config.rs - StageControl
pub struct StageControl {
    // ✅ 구현됨 (L1-L16)
    pub enable_ir_build: bool,             // L1
    pub enable_chunking: bool,             // L2
    pub enable_lexical: bool,              // L2.5
    pub enable_cross_file: bool,           // L3
    pub enable_flow_graph: bool,           // L4
    pub enable_types: bool,                // L5
    pub enable_data_flow: bool,            // L6
    pub enable_ssa: bool,                  // L7
    pub enable_symbols: bool,              // L8
    pub enable_occurrences: bool,          // L9
    pub enable_clone_detection: bool,      // L10
    pub enable_points_to: bool,            // L10 (PTA)
    pub enable_pdg: bool,                  // L11
    pub enable_heap_analysis: bool,        // L12
    pub enable_effect_analysis: bool,      // L13
    pub enable_slicing: bool,              // L13
    pub enable_taint: bool,                // L14
    pub enable_cost_analysis: bool,        // L15
    pub enable_repomap: bool,              // L16

    // ❌ 미구현 (L17-L37) - RFC-074에서 구현 예정
    // L17: Escape Analysis
    // L18: Concurrency (일부 구현)
    // L19: Typestate Analysis
    // L20: Differential Analysis
    // L21: SMT Verification (일부 구현)
    // ...
    pub enable_smt_verification: bool,     // L21 (placeholder)
    pub enable_concurrency_analysis: bool, // L18 (placeholder)
    pub enable_git_history: bool,          // L33
    pub enable_query_engine: bool,         // L37
}
```

**시사점**:
- ✅ **Stage 슬롯 확보**: L17-L37 flag 정의 완료 (구현만 하면 됨)
- ✅ **Dependency graph 완성**: `StageDAG` 구현 (160680a7 커밋)
- 🎯 **작업 필요**: RFC-074의 새로운 분석을 L17+ 슬롯에 배치

---

## 🎯 통합 전략 (To-Be)

### Phase 1: Config 시스템 통합 (1-2주)

**목표**: RFC-001 구현 or E2EPipelineConfig 단순화

#### Option A: E2EPipelineConfig 활용 (권장)

```rust
// 현재 E2EPipelineConfig를 BenchmarkConfig에 통합
pub struct BenchmarkConfig {
    pub pipeline_config: E2EPipelineConfig,  // ← 변경
    pub benchmark_opts: BenchmarkOptions,
}

impl BenchmarkConfig {
    /// Create with preset-like pattern
    pub fn fast() -> Self {
        Self {
            pipeline_config: E2EPipelineConfig {
                stages: StageControl {
                    // Fast preset: 기본 분석만
                    enable_ir_build: true,
                    enable_chunking: true,
                    enable_lexical: true,
                    enable_cross_file: false,  // 비활성화
                    enable_taint: false,       // 비활성화
                    enable_points_to: false,   // 비활성화
                    // ...
                },
                parallel_config: ParallelConfig {
                    num_workers: Some(num_cpus::get()),
                    // ...
                },
                // ...
            },
            benchmark_opts: BenchmarkOptions::default(),
        }
    }

    pub fn balanced() -> Self { /* ... */ }
    pub fn thorough() -> Self { /* ... */ }

    /// Stage override builder
    pub fn with_stage(mut self, stage: &str, enabled: bool) -> Self {
        match stage {
            "taint" => self.pipeline_config.stages.enable_taint = enabled,
            "escape" => self.pipeline_config.stages.enable_escape = enabled,
            // ...
            _ => panic!("Unknown stage: {}", stage),
        }
        self
    }
}
```

**장점**:
- ✅ 기존 E2EPipelineConfig 재사용 (중복 제거)
- ✅ 37개 stage 모두 제어 가능
- ✅ RFC-001 구현 없이도 즉시 사용 가능

**단점**:
- ⚠️ YAML 로딩 미지원 (수동 구현 필요)
- ⚠️ Stage override가 match 문 (타입 안전성 낮음)

#### Option B: RFC-001 완전 구현 (이상적이지만 시간 소요)

```rust
// RFC-001 명세대로 구현
pub struct PipelineConfig {
    preset: Preset,
    overrides: HashMap<String, Value>,
    // ...
}

impl PipelineConfig {
    pub fn preset(preset: Preset) -> PipelineConfigBuilder { /* ... */ }
    pub fn from_yaml(path: &str) -> Result<Self> { /* ... */ }
}

pub struct PipelineConfigBuilder {
    // ...
    pub fn taint(self, f: impl FnOnce(TaintConfigBuilder)) -> Self { /* ... */ }
    pub fn build(self) -> ValidatedConfig { /* ... */ }
}
```

**장점**:
- ✅ RFC-001 명세 준수 (장기적 아키텍처)
- ✅ YAML 지원, 타입 안전성, 컴파일 타임 검증

**단점**:
- ❌ 구현 비용 높음 (2-3주)
- ❌ RFC-074 작업 지연

**결론**: **Option A 채택** (빠른 진행), RFC-001은 별도 RFC로 추후 구현

#### 작업 계획 (1-2주)

1. **Week 1**:
   - [ ] `BenchmarkConfig` → `E2EPipelineConfig` 마이그레이션
   - [ ] Preset 메서드 추가 (`fast()`, `balanced()`, `thorough()`)
   - [ ] Stage override builder 구현
   - [ ] 기존 테스트 수정

2. **Week 2**:
   - [ ] 모든 benchmark 예제 업데이트
   - [ ] Documentation 업데이트
   - [ ] Backward compatibility 검증

**산출물**:
- [ ] `packages/codegraph-ir/src/benchmark/config.rs` 업데이트 (200 LOC)
- [ ] Migration guide: `docs/CONFIG_MIGRATION.md`

---

### Phase 2: Ground Truth Test Set 구성 (2-3주)

**목표**: RFC-074의 각 분석 기법별 Ground Truth 벤치마크 레포지토리 추가

#### 2.1. Security Bugs (Taint, Differential, Typestate)

**Juliet Test Suite** (NIST):
```bash
tools/benchmark/repo-test/security/
├── juliet/
│   ├── CWE-78/  # Command Injection (Taint)
│   ├── CWE-89/  # SQL Injection (Taint)
│   ├── CWE-190/ # Integer Overflow (SMT)
│   ├── CWE-366/ # Race Condition (Escape + Concurrency)
│   └── CWE-476/ # NULL Pointer Dereference (PTA)
└── ground_truth/
    ├── CWE-78_Balanced.json  # Expected: 85%+ recall
    └── ...
```

**Ground Truth 생성**:
```bash
# Step 1: 수동 라벨링 (Juliet은 이미 라벨링됨)
# CWE-78: 200 test cases (100 TP, 100 TN)

# Step 2: Baseline 실행
cargo run --bin bench-codegraph -- \
  --repo tools/benchmark/repo-test/security/juliet/CWE-78 \
  --preset balanced \
  --establish-ground-truth "Initial CWE-78 baseline"

# Output: target/benchmark_results/ground_truth/juliet_CWE-78_Balanced.json
{
  "expected": {
    "taint_flows": 85,      // 85% recall expected
    "false_positives": 10,  // 10% FP rate
    "duration_sec": 2.5,
    // ...
  }
}

# Step 3: 새 구현 테스트
cargo run --bin bench-codegraph -- \
  --repo tools/benchmark/repo-test/security/juliet/CWE-78 \
  --preset balanced \
  --validate  # Auto-compare against ground truth
```

#### 2.2. Concurrency Bugs (Escape Analysis)

**DaCapo Benchmark**:
```bash
tools/benchmark/repo-test/concurrency/
├── dacapo/
│   ├── avrora/   # Multi-threaded simulation (Race detection)
│   ├── lusearch/ # Concurrent indexing (Escape analysis)
│   └── ...
└── ground_truth/
    └── dacapo_avrora_Balanced.json
```

**Expected Metrics**:
```json
{
  "expected": {
    "race_conditions_detected": 12,
    "false_positives": 2,  // ← RFC-074 Phase 1 목표: 60% → 20%
    "escape_analysis_precision": 0.85
  }
}
```

#### 2.3. Correctness Bugs (Typestate, Resource Leak)

**DroidBench** (Android resource leak):
```bash
tools/benchmark/repo-test/correctness/
├── droidbench/
│   ├── ResourceLeak/
│   ├── FileHandleLeak/
│   └── ...
└── ground_truth/
    └── droidbench_ResourceLeak_Balanced.json
```

#### 2.4. Symbolic Execution (암호학적 버그)

**Custom Test Suite** (KLEE 기반):
```bash
tools/benchmark/repo-test/symbolic/
├── crypto/
│   ├── constant_time_compare.c  # Timing channel
│   ├── hash_collision.c          # Input validation bypass
│   └── integer_overflow.c        # Edge cases
└── ground_truth/
    └── crypto_suite_Balanced.json
```

#### 작업 계획 (2-3주)

1. **Week 1**:
   - [ ] Juliet CWE-78, 89, 190, 366 다운로드 및 정리
   - [ ] Ground Truth 생성 스크립트 작성
   - [ ] Baseline 실행 (현재 구현)

2. **Week 2**:
   - [ ] DaCapo, DroidBench 추가
   - [ ] Ground Truth 검증 (수동 확인)
   - [ ] Expected metrics 설정

3. **Week 3**:
   - [ ] Custom Symbolic Execution test suite 작성
   - [ ] 모든 Ground Truth JSON 파일 생성
   - [ ] CI/CD 통합 (`just benchmark-validate`)

**산출물**:
- [ ] `tools/benchmark/repo-test/` 구조 확립 (6개 카테고리)
- [ ] Ground Truth JSON 파일 생성 (30-50개)
- [ ] `docs/BENCHMARK_GROUND_TRUTH.md` (Ground Truth 관리 가이드)

---

### Phase 3: Pipeline 통합 전략 (RFC-074 Phase 1 기준)

**목표**: RFC-074의 P0 갭 3개를 현재 파이프라인에 통합

#### 3.1. Escape Analysis 통합 (L17)

**Pipeline 배치**:
```rust
// packages/codegraph-ir/src/pipeline/end_to_end_config.rs
pub struct StageControl {
    // ...
    /// L17: Escape Analysis - Track object escaping to heap/threads
    /// Dependencies: L6 (DFG), L10 (CallGraph)
    pub enable_escape_analysis: bool,
    // ...
}

// packages/codegraph-ir/src/pipeline/processor/stages/advanced.rs
impl StageProcessor {
    pub fn run_escape_analysis(&self, ir: &IRDocument, dfg: &DataFlowGraph) -> Result<EscapeGraph> {
        let analyzer = EscapeAnalyzer::new(
            ir.call_graph.clone(),
            dfg.clone(),
        );
        analyzer.analyze()
    }
}
```

**의존성 그래프**:
```
L6 (DFG) ──┐
           ├─→ L17 (Escape Analysis) ──→ L18 (Concurrency)
L10 (CG) ──┘
```

**Feature Flag**:
```rust
// Cargo.toml
[features]
escape-analysis = []  # Enable L17 Escape Analysis

// 조건부 컴파일
#[cfg(feature = "escape-analysis")]
pub fn run_escape_analysis(...) -> Result<EscapeGraph> { /* ... */ }

#[cfg(not(feature = "escape-analysis"))]
pub fn run_escape_analysis(...) -> Result<EscapeGraph> {
    Ok(EscapeGraph::empty())  // Stub
}
```

**통합 절차**:
1. **Week 1**: `packages/codegraph-ir/src/features/escape_analysis/` 구현
2. **Week 2**: `StageProcessor` 통합, feature flag 추가
3. **Week 3**: Concurrency 분석에 escape info 활용, Benchmark 검증

**Benchmark 검증**:
```bash
# Step 1: Escape Analysis 활성화
cargo run --bin bench-codegraph -- \
  --repo tools/benchmark/repo-test/concurrency/dacapo/avrora \
  --preset balanced \
  --features escape-analysis \
  --validate

# Expected: FP rate 60% → 20% (-67%)
```

#### 3.2. Differential Taint Analysis 통합 (L20)

**Pipeline 배치**:
```rust
pub struct StageControl {
    // ...
    /// L20: Differential Analysis - Detect security regressions
    /// Dependencies: L14 (Taint), Git history
    pub enable_differential_analysis: bool,
    // ...
}
```

**의존성 그래프**:
```
L14 (Taint, old) ──┐
                   ├─→ L20 (Differential) ──→ Security Regression Report
L14 (Taint, new) ──┘
```

**Git Integration**:
```rust
// packages/codegraph-ir/src/features/differential/
pub struct DifferentialTaintAnalyzer {
    old_commit: String,
    new_commit: String,
}

impl DifferentialTaintAnalyzer {
    pub fn analyze(&self) -> Result<Vec<TaintRegression>> {
        // 1. Checkout old commit, run taint
        let old_taint = self.run_taint_on_commit(&self.old_commit)?;

        // 2. Checkout new commit, run taint
        let new_taint = self.run_taint_on_commit(&self.new_commit)?;

        // 3. Semantic diff
        self.detect_regressions(&old_taint, &new_taint)
    }
}
```

**CI/CD 통합**:
```yaml
# .github/workflows/differential-analysis.yml
name: Differential Taint Analysis

on:
  pull_request:

jobs:
  differential:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # HEAD + HEAD~1

      - name: Run Differential Analysis
        run: |
          cargo run --bin bench-codegraph -- \
            --differential \
            --old-commit HEAD~1 \
            --new-commit HEAD \
            --fail-on-regression
```

**통합 절차**:
1. **Week 1-2**: `SemanticDiffer` 구현 (function matching, CFG diff)
2. **Week 3-4**: `TaintRegression` 탐지 로직
3. **Week 5-6**: CI/CD 통합, GitHub Action 작성

**Benchmark 검증**:
```bash
# OWASP Top 10 regression scenarios
tools/benchmark/repo-test/security/owasp_regression/
├── scenario_01_sanitizer_removed/
│   ├── before.py
│   └── after.py   # Sanitizer 제거
└── ground_truth/
    └── scenario_01_Balanced.json  # Expected: 탐지됨
```

#### 3.3. Path-Sensitive Analysis 완성 (L14 업그레이드)

**현재 구현** (65-70%):
```rust
// packages/codegraph-ir/src/features/taint_analysis/infrastructure/path_sensitive.rs
pub struct PathSensitiveTaintAnalyzer {
    dfg: Option<DataFlowGraph>,  // ← 이미 있음!
    // ...
}

// 문제: Stub 구현
fn extract_branch_condition(&self, node_id: &str) -> Result<String, String> {
    Ok(format!("condition_{}", node_id))  // ← Placeholder!
}
```

**업그레이드 계획**:
```rust
// DFG 통합
fn extract_branch_condition(&self, node_id: &str) -> Result<PathCondition, String> {
    let dfg = self.dfg.as_ref().ok_or("DFG not available")?;

    // DFG에서 실제 조건 추출
    let def_use = dfg.get_def_use(node_id)?;
    match def_use.kind {
        DefUseKind::BinaryOp { op, lhs, rhs } => {
            Ok(PathCondition::Comparison {
                var: lhs.clone(),
                op: op.clone(),
                value: rhs.clone(),
                negated: false,
            })
        }
        // ...
    }
}

// Infeasible path pruning
fn is_path_feasible(&self, conditions: &[PathCondition]) -> bool {
    for (i, c1) in conditions.iter().enumerate() {
        for c2 in &conditions[i+1..] {
            if self.is_contradictory(c1, c2) {
                return false;  // x > 10 and x < 5
            }
        }
    }
    true
}
```

**통합 절차**:
1. **Week 1-2**: DFG 통합, `extract_branch_condition` 구현
2. **Week 3**: Infeasible path pruning
3. **Week 4**: Z3 통합 (optional, feature flag)

**Benchmark 검증**:
```bash
# OWASP Benchmark path-sensitive cases
cargo run --bin bench-codegraph -- \
  --repo tools/benchmark/repo-test/security/owasp \
  --preset balanced \
  --validate

# Expected: Precision 75% → 85%
```

#### 3.4. 통합 타임라인 (13주)

| Week | 작업 | 산출물 | Benchmark |
|------|------|--------|-----------|
| 1-3 | Escape Analysis | 450 LOC + 10 tests | Concurrency FP -67% |
| 4-9 | Differential Taint | 750 LOC + CI/CD | Security regression 85% |
| 10-13 | Path-sensitive 완성 | +141 LOC + 12 tests | Taint precision +10% |

---

### Phase 4: Benchmark 시스템과 통합

**목표**: RFC-074의 모든 변경사항을 Ground Truth로 자동 검증

#### 4.1. Benchmark Runner 확장

**현재 구현**:
```rust
// packages/codegraph-ir/src/benchmark/runner.rs
pub struct BenchmarkRunner {
    config: BenchmarkConfig,
    repo: Repository,
}

impl BenchmarkRunner {
    pub fn run(&self) -> BenchmarkResult2<BenchmarkReport> {
        // 1. Warmup runs
        // 2. Measured runs
        // 3. Ground Truth validation
        // 4. Report generation
    }
}
```

**확장 계획**:
```rust
pub struct BenchmarkRunner {
    config: BenchmarkConfig,
    repo: Repository,
    custom_validators: Vec<Box<dyn CustomValidator>>,  // ← 추가
}

pub trait CustomValidator {
    fn name(&self) -> &str;
    fn validate(&self, result: &BenchmarkResult) -> ValidationResult;
}

// Escape Analysis 전용 validator
pub struct EscapeAnalysisValidator {
    expected_fp_rate: f64,
}

impl CustomValidator for EscapeAnalysisValidator {
    fn validate(&self, result: &BenchmarkResult) -> ValidationResult {
        let actual_fp = result.concurrency_summary.false_positives as f64
            / result.concurrency_summary.total_checks as f64;

        if actual_fp > self.expected_fp_rate * 1.1 {
            ValidationResult::fail(
                "Escape Analysis FP rate regression",
                Severity::Critical,
            )
        } else {
            ValidationResult::pass()
        }
    }
}
```

**사용 예시**:
```rust
let runner = BenchmarkRunner::new(config, repo)
    .add_validator(Box::new(EscapeAnalysisValidator {
        expected_fp_rate: 0.20,  // RFC-074 목표
    }))
    .add_validator(Box::new(TaintPrecisionValidator {
        expected_precision: 0.85,
    }));

let report = runner.run()?;
```

#### 4.2. Ground Truth 자동 업데이트

**현재**: 수동으로 `--establish-ground-truth` 실행

**개선**:
```rust
// Auto-update when improvement detected
impl GroundTruthStore {
    pub fn auto_update_if_better(
        &self,
        id: &str,
        new_result: &BenchmarkResult,
    ) -> BenchmarkResult2<bool> {
        let old_gt = self.load(id)?;

        // Check if new result is significantly better
        if self.is_better(&new_result, &old_gt.expected) {
            let new_gt = GroundTruth::from_results(
                old_gt.repo_id,
                old_gt.config_name,
                &[new_result.clone()],
                "Auto-update: performance improvement".to_string(),
            );
            self.save(&new_gt)?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn is_better(&self, new: &BenchmarkResult, old: &ExpectedMetrics) -> bool {
        // 10% faster AND same accuracy
        new.duration.as_secs_f64() < old.duration_sec * 0.9
            && new.total_nodes == old.total_nodes  // Deterministic match
    }
}
```

#### 4.3. CI/CD 통합

**GitHub Actions Workflow**:
```yaml
# .github/workflows/benchmark-regression.yml
name: Benchmark Regression Test

on:
  pull_request:
  push:
    branches: [main, feature/*]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Rust
        uses: actions-rs/toolchain@v1

      - name: Run Benchmarks
        run: |
          cargo run --bin bench-codegraph -- \
            --all-repos \
            --preset balanced \
            --validate \
            --fail-on-regression

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-report
          path: target/benchmark_results/latest_report.md
```

**PR Comment Integration**:
```yaml
      - name: Comment PR with Results
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('target/benchmark_results/latest_report.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '## Benchmark Results\n\n' + report
            });
```

---

## 📊 통합 마일스톤

### Q1 2025 (Phase 1: Quick Wins)

| Milestone | 기간 | 산출물 | 검증 |
|-----------|------|--------|------|
| **M1: Config 통합** | W1-2 | `BenchmarkConfig` 업데이트 | All tests pass |
| **M2: Ground Truth 구성** | W3-5 | Juliet/DaCapo/DroidBench 추가 | 30+ GT files |
| **M3: Escape Analysis** | W6-8 | L17 구현 + 통합 | Concurrency FP -67% |
| **M4: Differential Taint** | W9-14 | L20 구현 + CI/CD | Security regression 85% |
| **M5: Path-sensitive 완성** | W15-18 | L14 업그레이드 | Taint precision +10% |

### Q2 2025 (Phase 2: Foundation)

| Milestone | 기간 | 산출물 | 검증 |
|-----------|------|--------|------|
| **M6: Flow-sensitive PTA** | W19-24 | L10 업그레이드 | Must-alias +15-20% |
| **M7: Symbolic Execution** | W25-40 | L21 완성 | Crypto bugs 70% |
| **M8: Typestate** | W41-48 | L19 구현 | Resource leak 80% |

### Q3-Q4 2025 (Phase 3: Advanced)

- P2 갭 해소 (Context-sensitive Heap, Demand-driven, etc.)
- SOTA 95% 수준 달성

---

## 🔧 개발 워크플로우

### 새로운 분석 기법 추가 (Escape Analysis 예시)

#### Step 1: Feature 구현 (Rust)

```bash
# 1. 브랜치 생성
git checkout -b feature/L17-escape-analysis

# 2. 디렉토리 구조 생성
mkdir -p packages/codegraph-ir/src/features/escape_analysis/{domain,infrastructure,tests}

# 3. 구현
# - domain/escape_graph.rs (150 LOC)
# - infrastructure/analyzer.rs (300 LOC)
# - tests/integration_tests.rs (10 tests)
```

#### Step 2: Pipeline 통합

```rust
// packages/codegraph-ir/src/pipeline/end_to_end_config.rs
pub struct StageControl {
    /// L17: Escape Analysis
    #[cfg(feature = "escape-analysis")]
    pub enable_escape_analysis: bool,
}

// packages/codegraph-ir/src/pipeline/processor/stages/advanced.rs
impl StageProcessor {
    #[cfg(feature = "escape-analysis")]
    pub fn run_escape_analysis(&self, ...) -> Result<EscapeGraph> {
        // ...
    }
}
```

#### Step 3: Ground Truth 생성

```bash
# 1. Baseline 실행
cargo run --bin bench-codegraph -- \
  --repo tools/benchmark/repo-test/concurrency/dacapo/avrora \
  --preset balanced \
  --features escape-analysis \
  --establish-ground-truth "Initial L17 Escape Analysis baseline"

# Output: target/benchmark_results/ground_truth/dacapo_avrora_Balanced.json
```

#### Step 4: Benchmark 검증

```bash
# 2. Validation 실행
cargo run --bin bench-codegraph -- \
  --repo tools/benchmark/repo-test/concurrency/dacapo/avrora \
  --preset balanced \
  --features escape-analysis \
  --validate

# Expected output:
# ✅ PASS: Concurrency FP rate 20% (expected: 20%, actual: 18%)
# ✅ PASS: Duration 5.2s (expected: 5.0s ±5%, tolerance: 4.75-5.25s)
```

#### Step 5: CI/CD 검증

```bash
# 3. PR 생성
git add .
git commit -m "feat(L17): Implement Escape Analysis"
git push origin feature/L17-escape-analysis

# 4. GitHub Actions 자동 실행
# - Benchmark regression test
# - Ground Truth validation
# - PR comment with results
```

#### Step 6: Code Review

**Checklist**:
- [ ] Ground Truth validation PASS
- [ ] No performance regression (duration ±5%)
- [ ] Test coverage 80%+
- [ ] Documentation 작성 (`docs/ESCAPE_ANALYSIS_DESIGN.md`)
- [ ] Feature flag 추가 (`escape-analysis`)

---

## 📝 산출물 (Deliverables)

### Q1 2025 (Phase 1)

| 문서 | 내용 | 상태 |
|------|------|------|
| `docs/CONFIG_MIGRATION.md` | Config 시스템 마이그레이션 가이드 | ⏳ Pending |
| `docs/BENCHMARK_GROUND_TRUTH.md` | Ground Truth 관리 가이드 | ⏳ Pending |
| `docs/ESCAPE_ANALYSIS_DESIGN.md` | Escape Analysis 설계 문서 | ⏳ Pending |
| `docs/DIFFERENTIAL_ANALYSIS_GUIDE.md` | Differential Analysis 사용 가이드 | ⏳ Pending |
| `docs/PATH_SENSITIVE_DESIGN.md` | Path-sensitive 완성 문서 | ⏳ Pending |
| `docs/BENCHMARK_RESULTS_Q1.md` | Q1 벤치마크 결과 | ⏳ Pending |

### 코드베이스 변경

| 패키지 | 변경 내용 | LOC |
|--------|-----------|-----|
| `packages/codegraph-ir/src/benchmark/` | Config 통합 | +200 |
| `packages/codegraph-ir/src/features/escape_analysis/` | 신규 구현 | +450 |
| `packages/codegraph-ir/src/features/differential/` | 신규 구현 | +750 |
| `packages/codegraph-ir/src/features/taint_analysis/` | Path-sensitive 완성 | +141 |
| `packages/codegraph-ir/src/pipeline/` | Stage 통합 | +300 |
| `tools/benchmark/repo-test/` | Ground Truth 추가 | +5,000 (데이터) |
| **합계** | - | **~1,841 LOC** |

---

## 🚨 리스크 관리

### 주요 리스크

| 리스크 | 확률 | 영향 | 완화 방안 |
|--------|------|------|----------|
| **Config 시스템 파편화** | 중간 | 높음 | Option A 채택 (E2EPipelineConfig 활용) |
| **Ground Truth 품질 낮음** | 중간 | 높음 | 수동 검증 + 3회 실행 평균 |
| **Feature flag 복잡도** | 낮음 | 중간 | 최소한의 flag만 사용 (3-5개) |
| **Benchmark 실행 시간 증가** | 높음 | 중간 | Selective benchmark (changed stages only) |
| **CI/CD timeout** | 중간 | 중간 | Fast preset 사용, 병렬 실행 |

### Fallback Plan

**Phase 1 완료 후 검증 실패 시**:
1. Ground Truth 재검증 (수동 라벨링)
2. Tolerance 조정 (±5% → ±10%)
3. 추가 최적화 스프린트 (1-2주)

---

## ✅ 승인 프로세스

### Review Checklist

- [ ] **기술적 타당성** (Tech Lead):
  - [ ] Config 시스템 통합 방안 검토
  - [ ] Pipeline 의존성 그래프 검증
  - [ ] Feature flag 전략 승인

- [ ] **일정 실현 가능성** (PM):
  - [ ] 13주 일정 검토
  - [ ] 리소스 할당 (2명)
  - [ ] Milestone 설정 적절성

- [ ] **벤치마크 전략** (QA):
  - [ ] Ground Truth 품질 기준 검토
  - [ ] Tolerance 설정 승인
  - [ ] CI/CD 통합 계획 검토

- [ ] **문서화** (Documentation):
  - [ ] 산출물 목록 확인
  - [ ] Migration guide 필요성 검토

### 승인 서명

| 역할 | 이름 | 날짜 | 서명 |
|------|------|------|------|
| Author | Integration Team | 2025-12-29 | ✅ |
| Tech Lead | TBD | - | - |
| PM | TBD | - | - |
| QA | TBD | - | - |

---

**RFC Status**: Draft → Review → Approved → Implemented
**Next Review**: 2025-01-15
**Target Approval**: 2025-01-31

---

## 📚 참고 자료

### 관련 문서

- [RFC-074: SOTA 갭 해소 로드맵](RFC-SOTA-GAP-ROADMAP.md)
- [SOTA 갭 분석 (완전 검증판)](SOTA_GAP_ANALYSIS_FINAL.md)
- [RFC-002: Benchmark System](RFC-002-BENCHMARK.md) (추정)
- [RFC-001: Config System](RFC-CONFIG-SYSTEM.md)

### 레포지토리 구조

```
codegraph/
├── packages/codegraph-ir/
│   ├── src/
│   │   ├── benchmark/          # RFC-002 구현
│   │   ├── features/
│   │   │   ├── escape_analysis/   # ← Phase 1 추가
│   │   │   ├── differential/      # ← Phase 1 추가
│   │   │   └── taint_analysis/    # ← Phase 1 업그레이드
│   │   └── pipeline/
│   │       ├── end_to_end_config.rs  # L1-L37 stage control
│   │       └── processor/stages/     # Stage 구현
│   └── Cargo.toml             # Feature flags
├── tools/benchmark/repo-test/
│   ├── small/typer/           # ✅ 기존
│   ├── security/              # ← Phase 1 추가
│   │   ├── juliet/
│   │   └── owasp_regression/
│   ├── concurrency/           # ← Phase 1 추가
│   │   └── dacapo/
│   └── correctness/           # ← Phase 1 추가
│       └── droidbench/
└── docs/
    ├── RFC-075-INTEGRATION-PLAN.md  # 본 문서
    └── BENCHMARK_GROUND_TRUTH.md    # ← Phase 1 추가
```

### 기술 스택

**신규 의존성 (Phase 1)**:
```toml
[dependencies]
# Config 시스템 (RFC-001 대비)
# serde_yaml = "0.9"  # 이미 추가됨

# Escape Analysis (없음, Rust 표준 라이브러리로 구현)

# Differential Analysis
# (Git CLI 호출, 별도 dependency 없음)

[dev-dependencies]
# Ground Truth 검증
assert_approx_eq = "1.1"  # Float 비교
```

---

**End of RFC-075**
