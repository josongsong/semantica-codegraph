# RFC-074: SOTA 갭 해소 로드맵 (2025 Q1-Q4)
**Status**: Draft
**Author**: Analysis Team
**Created**: 2025-12-29
**Updated**: 2025-12-29
**Related**: [SOTA_GAP_ANALYSIS_FINAL.md](SOTA_GAP_ANALYSIS_FINAL.md)

---

## 📋 요약 (Executive Summary)

본 RFC는 [SOTA_GAP_ANALYSIS_FINAL.md](SOTA_GAP_ANALYSIS_FINAL.md)에서 식별된 33개 갭 중 **크리티컬 갭 18개**를 단계적으로 해소하는 로드맵을 제시합니다.

**목표**:
- **3개월 후** (2025 Q1): Security 70% → 85%, Concurrency 40% → 60%
- **6개월 후** (2025 Q2): 전체 정확도 75% → 88%
- **12개월 후** (2025 Q4): SOTA 수준 95% 달성

**우선순위 기준**:
1. **P0 (Critical)**: 신뢰도 저하 요인 (FP rate 40% 이상)
2. **P1 (High)**: 주요 버그 클래스 미탐지 (암호학, 타이밍 공격)
3. **P2 (Medium)**: 분석 정밀도 향상

---

## 🎯 Phase 1: Quick Wins (2025 Q1, 3개월)

**목표**: 즉시 효과가 큰 P0 갭 3개 해소

### 1.1. P0-1: Escape Analysis 구현 (3주)

**문제 정의**:
- 현재 동시성 분석의 **FP rate 40-60%**
- Local 변수를 shared로 오인하여 불필요한 Race 경고 다수
- 분석 신뢰도 저하의 최대 원인

**검증된 현황**:
```bash
$ rg "escape.*analysis|EscapeAnalysis" packages/codegraph-ir/src --type rust -i
# Result: 주석 2줄만 존재, 구현 없음 (0%)
```

**구현 계획**:

#### Week 1: 기본 Escape Graph 구현
- **파일**: `packages/codegraph-ir/src/features/escape_analysis/`
- **구조**:
  ```rust
  pub struct EscapeAnalyzer {
      /// Escape graph: var -> escape status
      escape_graph: FxHashMap<VarId, EscapeStatus>,
      /// Call graph for interprocedural analysis
      call_graph: CallGraph,
  }

  pub enum EscapeStatus {
      NoEscape,           // Stack-only (local)
      ArgEscape,          // Escapes via return
      GlobalEscape,       // Escapes to heap/global
      ThreadEscape,       // Escapes to other threads
  }
  ```

#### Week 2: Interprocedural Escape 분석
- **알고리즘**: Bottom-up SCC traversal (Tarjan)
- **입력**: Call graph + DFG
- **출력**: `Map<FunctionId, Set<ParamId, EscapeStatus>>`

#### Week 3: 동시성 분석 통합
- **파일**: `packages/codegraph-ir/src/features/concurrency/race_detector.rs`
- **수정**:
  ```rust
  // Before
  if is_shared_access(var) {
      report_race(var);  // ← Too many FPs!
  }

  // After
  if is_shared_access(var) && escapes_to_threads(var) {
      report_race(var);  // ← Precise!
  }
  ```

**예상 효과**:
- Concurrency FP: 60% → **20%** (-67%)
- 분석 속도: 1.5x 향상 (불필요한 검사 제거)

**검증 방법**:
- **Benchmark**: Juliet CWE-366 (Race Condition) 200개 케이스
- **목표**: FP 60% → 20% 이하

**산출물**:
- [ ] `escape_analysis/domain/escape_graph.rs` (150 LOC)
- [ ] `escape_analysis/infrastructure/analyzer.rs` (300 LOC)
- [ ] `escape_analysis/tests/integration_tests.rs` (10 test cases)
- [ ] 문서: `docs/ESCAPE_ANALYSIS_DESIGN.md`

---

### 1.2. P0-2: Differential Taint Analysis (6주)

**문제 정의**:
- 코드 변경 시 **Security regression 탐지 불가**
- Sanitizer 제거, Taint source 추가 등 자동 탐지 필요

**검증된 현황**:
```bash
$ rg "struct.*DifferentialAnalyzer" packages/codegraph-ir/src --type rust -i
# Result: 0 - Semantic diff 없음 (0%)
# Storage diff만 존재 (SnapshotDiff)
```

**구현 계획**:

#### Week 1-2: Semantic Diff 기본 구조
- **파일**: `packages/codegraph-ir/src/features/differential/`
- **구조**:
  ```rust
  pub struct DifferentialTaintAnalyzer {
      old_ir: IRDocument,
      new_ir: IRDocument,
      differ: SemanticDiffer,
  }

  pub struct TaintRegression {
      kind: RegressionKind,
      location: Location,
      old_state: TaintState,
      new_state: TaintState,
  }

  pub enum RegressionKind {
      SanitizerRemoved,      // Sanitizer 제거
      NewTaintSource,        // 새로운 source 추가
      PathBypass,            // Sanitization path 우회
      SinkExposed,           // Sink 노출
  }
  ```

#### Week 3-4: Interprocedural Diff
- **알고리즘**:
  1. Function signature matching (name + params)
  2. CFG diff (added/removed/modified blocks)
  3. Taint 재분석 (old vs new)
  4. Regression 탐지

#### Week 5-6: CI/CD 통합
- **Pre-commit hook**: 자동 differential analysis
- **Output**: JSON report
- **Integration**: GitHub Actions, GitLab CI

**예상 효과**:
- Security regression 자동 탐지: **0% → 85%**
- CI/CD 통합으로 PR 단계에서 차단

**검증 방법**:
- **Benchmark**: OWASP Top 10 regression 시나리오 50개
- **목표**: 85% 이상 탐지율

**산출물**:
- [ ] `differential/domain/regression.rs` (200 LOC)
- [ ] `differential/infrastructure/analyzer.rs` (400 LOC)
- [ ] `differential/adapters/ci_reporter.rs` (150 LOC)
- [ ] GitHub Action: `.github/workflows/differential-analysis.yml`
- [ ] 문서: `docs/DIFFERENTIAL_ANALYSIS_GUIDE.md`

---

### 1.3. P0-3: Path-sensitive Analysis 완성 (4주)

**문제 정의**:
- 현재 **65-70% 구현**, stub 함수로 인해 복잡한 조건 분기 처리 불가
- DFG 통합 없어서 `extract_branch_condition`이 placeholder

**검증된 현황**:
```rust
// packages/codegraph-ir/src/features/taint_analysis/infrastructure/path_sensitive.rs
fn extract_branch_condition(&self, node_id: &str) -> Result<String, String> {
    Ok(format!("condition_{}", node_id))  // ← Placeholder!
}

fn get_called_function(&self, _node_id: &str) -> Option<String> {
    None  // ← Not implemented!
}
```

**구현 계획**:

#### Week 1-2: DFG 통합
- **파일**: `path_sensitive.rs` (현재 659 LOC → 800 LOC)
- **수정**:
  ```rust
  pub struct PathSensitiveTaintAnalyzer {
      cfg_edges: Vec<CFGEdge>,
      dfg: DataFlowGraph,  // ← 이미 있음, 활용 강화
      // ...
  }

  fn extract_branch_condition(&self, node_id: &str) -> Result<PathCondition, String> {
      // DFG에서 실제 조건 추출
      let def_use = self.dfg.get_def_use(node_id)?;
      match def_use.kind {
          DefUseKind::BinaryOp { op, lhs, rhs } => {
              Ok(PathCondition::comparison(lhs, op, rhs, true))
          }
          // ...
      }
  }
  ```

#### Week 3: Infeasible Path Pruning
- **알고리즘**: Simple inconsistency detection
  ```rust
  fn is_path_feasible(conditions: &[PathCondition]) -> bool {
      // x > 10 and x < 5 → false
      // is_admin and not is_admin → false
      for (i, c1) in conditions.iter().enumerate() {
          for c2 in &conditions[i+1..] {
              if is_contradictory(c1, c2) {
                  return false;
              }
          }
      }
      true
  }
  ```

#### Week 4: SMT 통합 (Optional)
- **조건**: Z3 feature flag 활성화 시
- **활용**: 복잡한 수학 조건 검증
  ```rust
  if cfg!(feature = "z3") {
      let smt = SmtOrchestrator::new();
      smt.check_path_feasibility(conditions)
  }
  ```

**예상 효과**:
- Path-sensitive 정확도: 65% → **95%**
- Taint FP+FN: -15-25%

**검증 방법**:
- **Benchmark**: OWASP Benchmark path-sensitive 케이스
- **목표**: Precision 75% → 85%

**산출물**:
- [ ] `path_sensitive.rs` 완성 (659 → 800 LOC)
- [ ] `path_sensitive_tests.rs` 확장 (3 → 15 tests)
- [ ] 문서: `docs/PATH_SENSITIVE_DESIGN.md`

---

### Phase 1 요약

| 작업 | 기간 | 산출물 | 예상 효과 |
|------|------|--------|----------|
| Escape Analysis | 3주 | 450 LOC + 10 tests | Concurrency FP -67% |
| Differential Taint | 6주 | 750 LOC + CI/CD | Security regression 85% |
| Path-sensitive 완성 | 4주 | +141 LOC + 12 tests | Taint 정확도 +20% |
| **합계** | **13주** | **~1,350 LOC** | **Security 85%, Concurrency 60%** |

---

## 🏗️ Phase 2: Foundation (2025 Q2, 6개월)

**목표**: 핵심 분석 능력 강화 (P1 갭)

### 2.1. P1-1: Flow-sensitive Points-to Analysis (6주)

**문제 정의**:
- 현재 **0% Flow-sensitive** (이전 "60%" 오류)
- `parallel_andersen.rs`가 논문만 참조, 실제는 flow-insensitive

**기술 부채**:
```rust
// packages/codegraph-ir/src/features/points_to/infrastructure/parallel_andersen.rs
//! # References
//! - Hardekopf & Lin "Semi-sparse Flow-Sensitive Pointer Analysis" (POPL 2009)
// ← 논문만 참조, 실제 구현은 flow-insensitive!
```

**구현 계획**:

#### Week 1-2: Flow-sensitive Points-to Graph
- **파일**: `packages/codegraph-ir/src/features/points_to/infrastructure/flow_sensitive_pta.rs`
- **구조**:
  ```rust
  pub struct FlowSensitivePTA {
      /// Points-to sets at each program point
      pts_at_point: FxHashMap<(ProgramPoint, VarId), PointsToSet>,
      cfg: ControlFlowGraph,
      dfg: DataFlowGraph,
  }

  pub enum Update {
      Strong,  // Kill old, set new (p = new obj)
      Weak,    // Union with old (p may point to multiple)
  }
  ```

#### Week 3-4: Strong Update 구현
- **알고리즘**: Must-alias 판별 후 strong update
  ```rust
  fn transfer(&mut self, stmt: &Statement, in_state: &PTState) -> PTState {
      match stmt {
          Statement::Assign { lhs, rhs } => {
              if self.must_alias_singleton(lhs) {
                  // Strong update: kill old
                  out_state.kill(lhs);
                  out_state.add(lhs, eval(rhs));
              } else {
                  // Weak update: union
                  out_state.union(lhs, eval(rhs));
              }
          }
          // ...
      }
  }
  ```

#### Week 5-6: Sparse Analysis + Optimization
- **최적화**: Only track pointer variables (not all vars)
- **성능 목표**: Flow-insensitive의 2-3x 느림 허용

**예상 효과**:
- Must-alias precision: +15-20%
- False sharing 탐지 가능
- Null dereference FP -30%

**검증 방법**:
- **Benchmark**: DaCapo benchmark suite (Java)
- **목표**: Must-alias recall 80% 이상

**산출물**:
- [ ] `flow_sensitive_pta.rs` (600 LOC)
- [ ] `strong_update.rs` (200 LOC)
- [ ] `flow_sensitive_tests.rs` (20 tests)
- [ ] 문서: `docs/FLOW_SENSITIVE_PTA.md`

---

### 2.2. P1-2: Symbolic Execution (완성, 16주)

**문제 정의**:
- 현재 **40% 구현** (Z3 backend만, path exploration 없음)
- 암호학적 버그, input validation bypass 탐지 불가

**검증된 현황**:
```bash
$ wc -l z3_backend.rs interval_tracker.rs
# Result: 339 + 474 = 813 LOC (SMT 기반만)
# Path exploration, symbolic memory 없음
```

**구현 계획**:

#### Week 1-4: Symbolic Memory Model
- **파일**: `packages/codegraph-ir/src/features/symbolic_execution/`
- **구조**:
  ```rust
  pub struct SymbolicMemory {
      /// Symbolic heap
      heap: FxHashMap<SymbolicAddr, SymbolicValue>,
      /// Path constraints
      constraints: Vec<Constraint>,
  }

  pub enum SymbolicValue {
      Concrete(i64),
      Symbolic(SymbolId),
      Binary { op: BinOp, lhs: Box<Self>, rhs: Box<Self> },
  }
  ```

#### Week 5-8: Path Exploration Engine
- **알고리즘**: BFS/DFS with state merging
- **구조**:
  ```rust
  pub struct PathExplorer {
      worklist: VecDeque<ExecutionState>,
      visited: FxHashSet<StateHash>,
      max_depth: usize,
  }

  pub struct ExecutionState {
      pc: ProgramCounter,
      memory: SymbolicMemory,
      constraints: Vec<Constraint>,
  }
  ```

#### Week 9-12: Concolic Execution
- **알고리즘**: Concrete + Symbolic (SAGE-style)
- **활용**: 실제 input 생성으로 crash 재현

#### Week 13-16: Optimization + Integration
- **최적화**: State merging, constraint caching
- **통합**: Taint analysis와 결합 (symbolic taint tracking)

**예상 효과**:
- 암호학적 버그 탐지: 0% → **70%**
- Input validation bypass 자동 발견
- Integer overflow edge cases 탐지

**검증 방법**:
- **Benchmark**: KLEE test suite (Coreutils)
- **목표**: Bug 발견 개수 KLEE 대비 80% 수준

**산출물**:
- [ ] `symbolic_execution/` 모듈 (2,000 LOC)
- [ ] Concolic executor (500 LOC)
- [ ] 통합 테스트 (30 cases)
- [ ] 문서: `docs/SYMBOLIC_EXECUTION.md`

---

### 2.3. P1-3: Typestate Analysis (8주)

**문제 정의**:
- 현재 **0% 구현** (TypeState는 type narrowing용)
- File protocol violation, resource leak 탐지 불가

**검증된 현황**:
```rust
// packages/codegraph-ir/src/features/taint_analysis/infrastructure/type_narrowing.rs
pub struct TypeState {
    // Basic type state for narrowing (NOT protocol typestate!)
}
```

**구현 계획**:

#### Week 1-3: Typestate Automaton
- **파일**: `packages/codegraph-ir/src/features/typestate/`
- **구조**:
  ```rust
  pub struct TypestateAnalyzer {
      /// Protocol definitions
      protocols: FxHashMap<TypeId, Protocol>,
      /// Current states
      states: FxHashMap<VarId, State>,
  }

  pub struct Protocol {
      states: Vec<State>,
      transitions: Vec<Transition>,
      error_states: FxHashSet<StateId>,
  }

  pub struct Transition {
      from: StateId,
      method: String,
      to: StateId,
  }
  ```

#### Week 4-5: Protocol Definition (DSL)
- **예시**: File protocol
  ```rust
  protocol File {
      states: [Closed, Open, Error]

      transition Closed --(open)--> Open
      transition Open --(read)--> Open
      transition Open --(close)--> Closed

      error: Open --(read after close)--> Error
  }
  ```

#### Week 6-8: Interprocedural Typestate
- **알고리즘**: Summary-based interprocedural
- **처리**: Function call로 state 전파

**예상 효과**:
- Resource leak 탐지: 0% → **80%**
- Protocol violation 자동 탐지

**검증 방법**:
- **Benchmark**: DroidBench (Android resource leak)
- **목표**: Recall 80% 이상

**산출물**:
- [ ] `typestate/` 모듈 (800 LOC)
- [ ] Protocol DSL parser (200 LOC)
- [ ] Predefined protocols (File, Socket, DB) (300 LOC)
- [ ] 문서: `docs/TYPESTATE_ANALYSIS.md`

---

### Phase 2 요약

| 작업 | 기간 | 산출물 | 예상 효과 |
|------|------|--------|----------|
| Flow-sensitive PTA | 6주 | 800 LOC + 20 tests | Must-alias +15-20% |
| Symbolic Execution | 16주 | 2,500 LOC + 30 tests | Crypto bugs 70% |
| Typestate Analysis | 8주 | 1,300 LOC + protocols | Resource leak 80% |
| **합계** | **30주** | **~4,600 LOC** | **전체 정확도 88%** |

---

## 🚀 Phase 3: Advanced (2025 Q3-Q4, 12개월)

**목표**: SOTA 수준 도달 (P2 갭)

### 3.1. P2 갭 해소 계획

| 갭 | 현재 | 목표 | 기간 | 우선순위 |
|---|------|------|------|---------|
| Context-sensitive Heap | 50% | 90% | 8주 | P2-1 |
| Demand-driven Analysis | 15% | 90% | 8주 | P2-2 |
| String Analysis | 25% | 80% | 6주 | P2-3 |
| Array Bounds | 75% | 95% | 3주 | P2-4 |
| Information Flow | 0% | 70% | 8주 | P2-5 |
| Relational Analysis | 0% | 60% | 10주 | P2-6 |

### 3.2. Minor 갭 (15개)

- 우선순위 낮음
- 시간 여유 시 선택적 구현
- 총 30-42주 예상

---

## 📊 검증 프레임워크

### Benchmark Suite

각 Phase 완료 시 다음 벤치마크 실행:

| Benchmark | 목적 | 목표 |
|-----------|------|------|
| **Juliet CWE Suite** | Security bugs (CWE-78, 89, 190, 366, ...) | Recall 85%+ |
| **OWASP Benchmark** | Web security (SQLI, XSS, etc.) | Precision 90%+ |
| **LAVA-M** | Buffer overflow, injection | Bug 발견 70%+ |
| **DaCapo** | Points-to precision | Must-alias 80%+ |
| **KLEE Test Suite** | Symbolic execution | KLEE 대비 80% |
| **DroidBench** | Android resource leak | Recall 80%+ |

### 성능 프로파일링

```rust
pub struct PerformanceProfile {
    pub analysis_time: Duration,
    pub memory_usage: usize,
    pub scalability: ScalabilityMetrics,
}

pub struct ScalabilityMetrics {
    pub loc_1k: Duration,
    pub loc_10k: Duration,
    pub loc_100k: Duration,
}
```

**목표**:
- 1K LOC: <1초
- 10K LOC: <10초
- 100K LOC: <2분

---

## 🎯 예상 결과

### Phase 1 (3개월 후)

| 메트릭 | 현재 | 목표 | 달성 방법 |
|--------|------|------|----------|
| Security 정확도 | 70% | **85%** | Differential + Path-sensitive |
| Concurrency 정확도 | 40% | **60%** | Escape Analysis |
| Overall 정확도 | 75% | **80%** | P0 3개 해소 |

### Phase 2 (6개월 후)

| 메트릭 | 현재 | 목표 | 달성 방법 |
|--------|------|------|----------|
| Security 정확도 | 70% | **90%** | Symbolic Execution |
| Concurrency 정확도 | 40% | **75%** | Flow-sensitive PTA |
| Correctness 정확도 | 75% | **88%** | Typestate |
| Overall 정확도 | 75% | **88%** | P1 3개 해소 |

### Phase 3 (12개월 후)

| 메트릭 | 현재 | 목표 | 달성 방법 |
|--------|------|------|----------|
| Overall 정확도 | 75% | **95%** | P2 갭 해소 |
| SOTA 수준 달성 | 48% | **95%** | 150개 기법 중 142개 |

---

## 📝 마일스톤

### Q1 2025 (Phase 1)
- [ ] 2025-01-31: Escape Analysis 완료
- [ ] 2025-02-28: Differential Taint 완료
- [ ] 2025-03-31: Path-sensitive 완성 + Phase 1 벤치마크

### Q2 2025 (Phase 2)
- [ ] 2025-04-30: Flow-sensitive PTA 완료
- [ ] 2025-06-15: Symbolic Execution 완료
- [ ] 2025-06-30: Typestate Analysis 완료 + Phase 2 벤치마크

### Q3-Q4 2025 (Phase 3)
- [ ] 2025-09-30: P2 갭 50% 해소
- [ ] 2025-12-31: SOTA 95% 수준 달성 + 최종 벤치마크

---

## 🔧 기술 스택

### 신규 의존성

```toml
[dependencies]
# Symbolic Execution
z3 = { version = "0.12", optional = true, features = ["static-link-z3"] }

# Protocol DSL Parser (Typestate)
pest = "2.7"
pest_derive = "2.7"

# Performance
rayon = "1.8"  # Already exists
dashmap = "5.5"  # Concurrent HashMap
```

### 개발 도구

```toml
[dev-dependencies]
criterion = "0.5"  # Benchmarking
proptest = "1.4"   # Property-based testing
```

---

## 📚 문서화 계획

각 Phase 완료 시 다음 문서 작성:

- [ ] `docs/ESCAPE_ANALYSIS_DESIGN.md`
- [ ] `docs/DIFFERENTIAL_ANALYSIS_GUIDE.md`
- [ ] `docs/PATH_SENSITIVE_DESIGN.md`
- [ ] `docs/FLOW_SENSITIVE_PTA.md`
- [ ] `docs/SYMBOLIC_EXECUTION.md`
- [ ] `docs/TYPESTATE_ANALYSIS.md`
- [ ] `docs/BENCHMARK_RESULTS_Q1.md`
- [ ] `docs/BENCHMARK_RESULTS_Q2.md`
- [ ] `docs/SOTA_ACHIEVEMENT_REPORT.md` (최종)

---

## 🚨 리스크 관리

### 주요 리스크

| 리스크 | 확률 | 영향 | 완화 방안 |
|--------|------|------|----------|
| Symbolic Execution 성능 저하 | 높음 | 높음 | Selective SE + timeout |
| Flow-sensitive PTA 복잡도 폭발 | 중간 | 높음 | Sparse analysis + caching |
| Z3 dependency 문제 | 낮음 | 중간 | Optional feature flag |
| 벤치마크 미달성 | 중간 | 중간 | Iterative refinement |

### Fallback Plan

Phase 1-2 완료 후 벤치마크 미달성 시:
- Phase 3 일정 조정
- P2 갭 우선순위 재조정
- 추가 최적화 스프린트 (2-4주)

---

## 💰 비용 추정

### 개발 인력

| Phase | 기간 | 인력 | 총 공수 |
|-------|------|------|---------|
| Phase 1 | 3개월 | 2명 | 6 man-months |
| Phase 2 | 6개월 | 2명 | 12 man-months |
| Phase 3 | 12개월 | 1-2명 | 12-18 man-months |
| **합계** | **21개월** | **2명** | **30-36 man-months** |

### 인프라 비용

- **CI/CD 증가**: Benchmark 실행 시간 증가 (30분 → 2시간)
- **Z3 라이선스**: MIT License (무료)
- **추가 서버**: Benchmark 전용 서버 (optional)

---

## 🎓 참고 자료

### 학계 논문

**Escape Analysis**:
- Choi et al. (1999): "Escape Analysis for Java"
- Gay & Steensgaard (2000): "Fast Escape Analysis and Stack Allocation"

**Flow-sensitive PTA**:
- Hardekopf & Lin (2009): "Semi-sparse Flow-Sensitive Pointer Analysis" (POPL)
- Sui et al. (2016): "SVF: Interprocedural Static Value-Flow Analysis" (CC)

**Symbolic Execution**:
- Cadar et al. (2008): "KLEE: Unassisted and Automatic Generation of High-Coverage Tests"
- Godefroid et al. (2008): "Automated Whitebox Fuzz Testing" (SAGE)

**Typestate**:
- Strom & Yemini (1986): "Typestate: A Programming Language Concept for Enhancing Software Reliability"
- Fink et al. (2008): "Effective Typestate Verification in the Presence of Aliasing" (ISSTA)

### 오픈소스 도구

- **KLEE**: Symbolic execution engine
- **Infer**: Facebook's static analyzer (Separation Logic)
- **SVF**: Static Value-Flow analysis framework
- **Soot**: Java optimization framework (Points-to)

---

## ✅ 승인 프로세스

### Review Checklist

- [ ] 기술적 타당성 검토 (Tech Lead)
- [ ] 일정 실현 가능성 검토 (PM)
- [ ] 예산 승인 (Management)
- [ ] 벤치마크 목표 합의 (QA)

### 승인 서명

| 역할 | 이름 | 날짜 | 서명 |
|------|------|------|------|
| Author | Analysis Team | 2025-12-29 | ✅ |
| Tech Lead | TBD | - | - |
| PM | TBD | - | - |
| Management | TBD | - | - |

---

**RFC Status**: Draft → Review → Approved → Implemented
**Next Review**: 2025-01-15
**Target Approval**: 2025-01-31
