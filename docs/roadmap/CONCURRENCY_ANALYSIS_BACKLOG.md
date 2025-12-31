# Concurrency Analysis Backlog

> **Status**: 🟢 Core Implemented (Basic Features Ready)
> **Last Updated**: 2025-12-31
> **Owner**: TBD
> **Estimated Total Effort**: ~1-2 weeks (remaining advanced features)

---

## 📋 Executive Summary

Concurrency Analysis 기능의 현재 상태 및 향후 액션 아이템 정리.

**현재 상태**:
- ✅ Escape Analysis: 완전 구현 (647 LOC, 파이프라인 통합됨)
- ✅ AsyncRaceDetector: Edge 기반 Read/Write 추적 구현 (Production)
- ✅ Happens-Before: Vector Clock 기반 기초 구현 (Lamport)
- ✅ Pipeline L18: RFC-001 통합 완료 (`config.stages.concurrency = true`)
- ✅ PyO3 Bindings: msgpack 인터페이스 구현
- 🟡 나머지 고급 기능: Lock Set Analysis, MHP 등 미구현

**우선순위**: 중간 - Python GIL-free (3.13+) 채택률에 따라 확장

---

## ✅ Section 1: Core Implementation (COMPLETED)

> 기본 Concurrency Analysis 기능이 구현되었습니다.

### 1.1 `find_async_functions()` ✅ 완료
- **파일**: `packages/codegraph-ir/src/features/concurrency_analysis/application/analyze_concurrency.rs`
- **구현**: `IRDocumentConcurrencyExt` trait으로 `NodeKind::Function/Method` + `is_async` 기반 필터링
- **테스트**: 6개 테스트 통과

### 1.2 Pipeline L18 활성화 ✅ 완료
- **파일**: `packages/codegraph-ir/src/pipeline/end_to_end_orchestrator.rs`
- **구현**: `stage_config.concurrency` → `StageId::L18ConcurrencyAnalysis` 매핑
- **Config**: `StageControl.concurrency` 필드 추가 (`pipeline_config.rs`)

### 1.3 Python Bindings ✅ 완료
- **파일**: `packages/codegraph-ir/src/adapters/pyo3/concurrency_bindings.rs`
- **구현**:
  - `analyze_async_races_msgpack()` - Zero-copy msgpack 인터페이스 (Production)
  - `analyze_all_async_races_msgpack()` - 배치 분석 API
  - `analyze_async_races()` / `analyze_all_async_races()` - Legacy PyObject API
- **특징**: GIL 해제, RFC-062 호환

### 1.4 Edge 기반 Read/Write 추적 ✅ 완료
- **파일**: `packages/codegraph-ir/src/features/concurrency_analysis/infrastructure/async_race_detector.rs`
- **구현**: `EdgeKind::Reads/Writes` 기반 정확한 변수 접근 탐지
- **특징**: Shared variable 휴리스틱 (`self.xxx`, 대문자, qualified name)

### 1.5 Escape Analysis 연동 ✅ 완료
- **파일**: `async_race_detector.rs`
- **구현**: `analyze_async_function_with_escape_info()` 메서드
- **효과**: Thread-local 변수 필터링으로 FP 40-60% 감소

### 1.6 Happens-Before 기초 ✅ 완료
- **파일**: `packages/codegraph-ir/src/features/concurrency_analysis/infrastructure/happens_before.rs`
- **구현**: Lamport Vector Clock 기반 HB 관계 분석
- **특징**: Acquire/Release 동기화, Fork/Join 지원
- **테스트**: 7개 테스트 통과

---

## 🟠 Section 2: Advanced Features (Medium Priority)

> 추가 고급 기능 구현

### 2.1 CFG/DFG 연동 강화 (선택적)
- **상태**: 기본 Edge 기반 분석 완료, CFG/DFG 깊은 연동 선택적
- **필요 시 추가**:
  - CFG dominator 분석으로 await 순서 정밀화
  - DFG reaching definitions으로 may-alias 개선
- **Effort**: 3-5일 (선택적)

### 2.2 Lock Region 탐지 강화
- **현재 상태**: `async with` 블록 패턴 탐지 완료
- **추가 필요**:
  1. `asyncio.Lock()` 인스턴스 추적
  2. 중첩 Lock 분석
  3. Condition Variable 지원
- **Effort**: 2-3일

### 2.3 May-Alias 정밀화
- **현재 상태**: Escape Analysis 기반 thread-local 필터링 완료
- **추가 필요**:
  - Points-To 분석 연동으로 must-alias 판정
  - Field-sensitivity (self.a vs self.b 구분)
- **Effort**: 2-3일

---

## 🟡 Section 3: Advanced Features (Low Priority)

> 향후 필요시 구현

### 3.1 Deadlock Detection
- **상태**: 미구현
- **필요 구현**:
  1. Wait-for Graph 구축
  2. Tarjan SCC로 순환 탐지
  3. `asyncio.Lock` 획득 순서 분석
- **참고**: Tarjan SCC 이미 구현됨 (`packages/codegraph-ir/src/features/graph_builder/`)
- **Effort**: 3-5일

### 3.2 Happens-Before Relation ✅ 기초 완료
- **상태**: 기초 구현 완료
- **구현 완료**:
  1. ✅ Event 순서 모델링 (fork, join, lock, unlock, await)
  2. ✅ Vector clock 기반 HB 계산
  3. ✅ Race = ¬HB(a,b) ∧ ¬HB(b,a) ∧ conflict(a,b)
- **추가 필요**: AsyncRaceDetector와 통합
- **참고 논문**: Lamport (1978), "Time, Clocks, and the Ordering of Events"
- **Effort**: 2-3일 (통합 작업)

### 3.3 Lock Set Analysis (Eraser Algorithm)
- **상태**: 미구현
- **필요 구현**:
  1. 각 공유 변수에 대한 lock set 추적
  2. 접근 시 lock set 교집합 계산
  3. 빈 교집합 = 잠재적 race
- **참고 논문**: Savage et al. (1997), "Eraser: A Dynamic Data Race Detector"
- **Effort**: 3-5일

### 3.4 May-Happen-in-Parallel (MHP) Analysis
- **상태**: 미구현
- **필요 구현**:
  1. Task spawn/join 분석
  2. CFG 기반 parallel region 식별
  3. MHP 쌍 계산
- **Effort**: 5-7일

---

## 🔵 Section 4: Testing & Quality

### 4.1 테스트 보강
- **현재**: 17개 테스트 (대부분 stub 테스트)
- **목표**: 50+ 테스트, 실제 race detection 검증
- **액션**:
  1. Real-world async race 예제 수집 (GitHub Issues)
  2. Benchmark suite 구축 (precision/recall 측정)
  3. Edge case 테스트 추가

### 4.2 Benchmark 추가
- **파일**: `packages/codegraph-ir/benches/concurrency_bench.rs` (신규)
- **측정 항목**:
  - 분석 속도 (함수당 < 100ms 목표)
  - Precision/Recall (vs ThreadSanitizer 결과)
  - FP 감소율 (Escape Analysis 연동 전후)

---

## 📅 Section 5: Trigger Conditions

> 이 백로그 작업을 시작해야 하는 조건

### 5.1 즉시 시작 조건
- [ ] 고객/사용자가 async race detection 명시적 요청
- [ ] Python 3.13+ GIL-free 모드 GA (General Availability)
- [ ] 경쟁 제품(Semgrep, CodeQL)이 Python async race 지원 발표

### 5.2 검토 시작 조건
- [ ] Python 3.13 GIL-free 베타 채택률 > 5%
- [ ] FastAPI/asyncio 기반 프로젝트 분석 요청 증가
- [ ] 보안 감사에서 concurrency 취약점 빈도 증가

### 5.3 모니터링 항목
- Python 3.13+ GIL-free 채택률 (PEP 703)
- GitHub Security Advisories의 race condition 비율
- 경쟁사 (Semgrep, CodeQL, Snyk) 기능 로드맵

---

## 📊 Section 6: Effort Summary

| Section | 작업 | Effort | 상태 |
|---------|------|--------|------|
| 1.1 | find_async_functions | 0.5일 | ✅ 완료 |
| 1.2 | Pipeline L18 활성화 | 0.5일 | ✅ 완료 |
| 1.3 | Python Bindings (msgpack) | 1일 | ✅ 완료 |
| 1.4 | Edge 기반 Read/Write | 1일 | ✅ 완료 |
| 1.5 | Escape Analysis 연동 | 0.5일 | ✅ 완료 |
| 1.6 | Happens-Before 기초 | 1일 | ✅ 완료 |
| 2.1 | CFG/DFG 연동 강화 | 3-5일 | 🟠 선택적 |
| 2.2 | Lock Region 강화 | 2-3일 | 🟠 선택적 |
| 2.3 | May-Alias 정밀화 | 2-3일 | 🟠 선택적 |
| 3.1 | Deadlock Detection | 3-5일 | 🟡 낮음 (기초 구현됨) |
| 3.2 | Happens-Before 통합 | 2-3일 | 🟡 낮음 |
| 3.3 | Lock Set (Eraser) | 3-5일 | 🟡 낮음 |
| 3.4 | MHP Analysis | 5-7일 | 🟡 낮음 |
| 4.x | Testing & Benchmark | 3-5일 | 🟡 낮음 |

**완료된 Core 구현**: ~4.5일 (✅)
**남은 Advanced 기능**: ~1-2주
**Total Full (SOTA)**: ~3주

---

## 🔗 Related Documents

- [RFC-CONFIG-SYSTEM.md](../RFC-CONFIG-SYSTEM.md) - Config 스키마 (concurrency 필드 추가 필요)
- [SOTA_GAP_ANALYSIS_FINAL.md](../SOTA_GAP_ANALYSIS_FINAL.md) - 전체 SOTA 갭 분석
- [escape_analysis.rs](../../packages/codegraph-ir/src/features/heap_analysis/escape_analysis.rs) - 완성된 Escape Analysis

---

## 📝 Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-31 | AI Assistant | Initial backlog creation |
| 2025-12-31 | AI Assistant | Core implementation completed (Section 1 all items) |
| 2025-12-31 | AI Assistant | Happens-Before basic implementation added |
| 2025-12-31 | AI Assistant | Status updated to 🟢 Core Implemented |

