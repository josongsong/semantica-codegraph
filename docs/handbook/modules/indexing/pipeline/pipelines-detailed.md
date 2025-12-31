# 인덱싱 파이프라인 상세 분석 - 엣지케이스 비교

> 모든 인덱싱 파이프라인의 엣지케이스, 충돌, 우선순위 분석

---

## 목차

1. [파이프라인 전체 맵](#1-파이프라인-전체-맵)
2. [트리거 방식 비교](#2-트리거-방식-비교)
3. [엣지케이스 매트릭스](#3-엣지케이스-매트릭스)
4. [충돌 시나리오 & 해결책](#4-충돌-시나리오--해결책)
5. [우선순위 & 중단 정책](#5-우선순위--중단-정책)
6. [성능 특성 비교](#6-성능-특성-비교)
7. [권장 사용 시나리오](#7-권장-사용-시나리오)

---

## 1. 파이프라인 전체 맵

### 1.1 실행 모드 (5종)

| 모드 | 레이어 | 범위 | 예상 시간 | 사용 시점 |
|------|--------|------|----------|----------|
| **FAST** | L1+L2 | 변경 파일만 | 초 단위 | 실시간 피드백 |
| **BALANCED** | L1+L2+L3 | 변경 + 1-hop | 분 단위 | 일반 개발 |
| **DEEP** | L1+L2+L3+L4 | 변경 + 2-hop 또는 전체 | 10분+ | 시그니처 변경 시 |
| **BOOTSTRAP** | L1+L2+L3_SUMMARY | 전체 레포 | 5-15분 | 최초 인덱싱 |
| **REPAIR** | 동적 | 손상 영역 + 참조 | 가변 | 복구 작업 |

### 1.2 트리거 방식 (6종)

| 트리거 | 구현 | 자동화 | 레이턴시 | 범위 |
|--------|------|--------|---------|------|
| **ShadowFS Plugin** | `IncrementalUpdatePlugin` | ✅ | < | 코드 편집 (IDE 내부) |
| **FileWatcher** | `FileWatcher` (Watchdog) | ✅ | < | 외부 변경 (git pull) |
| **BackgroundScheduler** | `BackgroundScheduler` | ✅ | Idle 5분 후 | BALANCED 자동 실행 |
| **ChangeDetector** | `ChangeDetector` (CLI/API) | ⏸️ | 즉시 | 명시적 호출 |
| **Job Queue** | `JobOrchestrator` | ⏸️ | 우선순위 기반 | 대규모 배치 |
| **PR 분석** | (미구현) | - | - | CI/CD 통합 |

---

## 2. 트리거 방식 비교

### 2.1 ShadowFS Plugin vs FileWatcher

| 항목 | ShadowFS Plugin | FileWatcher |
|------|----------------|-------------|
| **트리거** | IDE 코드 편집 (write 이벤트) | 파일 시스템 이벤트 (외부 변경) |
| **변경 감지** | Transaction 기반 (commit 시 배치) | Watchdog 이벤트 ( debounce) |
| **IR 델타** | 배치 처리 (언어별 병렬) | N/A (ChangeDetector로 위임) |
| **인덱싱** | commit 시 자동 | 배치 준비 후 콜백 |
| **엣지케이스** | txn timeout (1h TTL), rollback | 중복 이벤트, 디렉토리 이동 |
| **성능** | < (배치) | < (debounced) |
| **사용 시점** | 🔥 **IDE 내부 편집** | 🔥 **git pull, 외부 에디터** |

**엣지케이스 1: 동시 트리거 (같은 파일)**
```
시나리오: IDE에서 파일 저장 + git pull로 같은 파일 변경
- ShadowFS: txn-123 (user edit)
- FileWatcher: git pull 감지

해결: ShadowFS가 먼저 commit → FileWatcher는 이미 최신이므로 skip
```

**엣지케이스 2: 외부 에디터 편집**
```
시나리오: vim으로 파일 수정 (IDE 외부)
- ShadowFS: 감지 못함 (IDE 외부)
- FileWatcher: 감지 → 인덱싱 트리거 ✅

해결: FileWatcher가 유일한 감지 수단
```

### 2.2 BackgroundScheduler 자동 전환

**트리거 조건:**
```python
# src/contexts/analysis_indexing/infrastructure/models/mode.py
class ModeTransitionConfig:
    FAST_TO_BALANCED_IDLE_MINUTES = 5      # Idle 5분
    FAST_TO_BALANCED_HOURS_SINCE_LAST = 24  # 24시간마다
    FAST_TO_BALANCED_MIN_CHANGED_FILES = 10 # 변경 10개 이상
```

**엣지케이스 3: Idle 중 활동 재개**
```
시나리오: BALANCED 실행 중 (60% 완료) → 사용자 파일 편집
해결:
1. IdleDetector.mark_activity() → 더 이상 idle 아님
2. pause_current_job() 호출 → stop_event.set()
3. 현재 파일 처리 완료 후 graceful stop
4. JobProgress 저장 (60% checkpoint)
5. FAST 모드 우선 실행
6. 다시 idle되면 60%부터 재개
```

**엣지케이스 4: DEEP 중 중단 불가**
```
시나리오: DEEP 실행 중 사용자 활동
제약: DEEP는 pause 불가 (ModeScopeLimit.DEEP_NEIGHBOR_DEPTH = 2)
해결: DEEP 완료까지 대기 (timeout 30초 후 force stop)
```

### 2.3 ChangeDetector 전략 우선순위

**감지 전략 (3단계):**
```
1. git diff (빠름, 정확) → 우선
2. mtime (git 없을 때)
3. content hash (최종 검증)
```

**엣지케이스 5: Rename 감지 실패**
```
시나리오: git 없고, file_hash_store도 없음
- ChangeDetector: old_file → deleted, new_file → added
- 결과: 불필요한 재인덱싱

해결: _detect_renames_by_similarity() 활성화
- Extension별 그룹핑 (O(k²), k=같은 타입 파일 수)
- filename_similarity (Jaccard) ≥ 0.90 → rename 판정
```

**엣지케이스 6: Git rename + content 변경**
```
시나리오: git mv old.py new.py + 코드 수정
- git diff: R100 old.py new.py (rename) + M new.py (modify)
- ChangeSet: renamed={old.py: new.py} + modified={new.py}

해결: renamed와 modified 모두 포함 (정상)
```

---

## 3. 엣지케이스 매트릭스

### 3.1 ScopeExpander 자동 Escalation

| 감지 조건 | 기존 모드 | 자동 변경 | 이유 |
|----------|----------|---------|------|
| **SIGNATURE_CHANGED** | FAST | DEEP | Transitive invalidation 필요 |
| **SIGNATURE_CHANGED** | BALANCED | DEEP | 1-hop 불충분, 2-hop 필요 |
| **Deleted + References** | FAST | REPAIR | 참조 무결성 복구 |
| **10+ files changed** | FAST | BALANCED | 자동 전환 (ModeTransitionConfig) |

**엣지케이스 7: SIGNATURE_CHANGED 자동 DEEP**
```python
# src/contexts/analysis_indexing/infrastructure/scope_expander.py
async def expand_scope(change_set, mode, impact_result):
    # 🔥 SOTA: 시그니처 변경 감지 → 자동 escalation
    if impact_result and self._has_signature_changes(impact_result):
        if mode in (FAST, BALANCED):
            logger.warning("signature_change_detected_auto_escalating_to_deep")
            mode = IndexingMode.DEEP  # 자동 변경!
```

**시나리오:**
```
1. 사용자: FAST 모드로 def func(x) → def func(x, y) 변경
2. ImpactAnalyzer: func → SIGNATURE_CHANGED 감지
3. ScopeExpander: FAST → DEEP 자동 escalation
4. 결과: func 호출하는 모든 파일 (2-hop) 재인덱싱
```

### 3.2 ImpactAnalyzer 통합

**확장 전략 비교:**

| 모드 | Import 관계 | CALLS 관계 | INHERITS 관계 | Transitive |
|------|------------|-----------|--------------|-----------|
| FAST | ❌ | ❌ | ❌ | ❌ |
| BALANCED | ✅ (1-hop) | ✅ (direct) | ✅ (direct) | ❌ |
| DEEP | ✅ (2-hop) | ✅ (전체) | ✅ (전체) | ✅ |

**엣지케이스 8: 순환 의존성**
```
시나리오: A imports B, B imports A (circular)
- ScopeExpander: BFS로 visited set 관리
- 결과: A, B 각 1회만 방문 (무한 루프 방지)
```

**엣지케이스 9: Max files limit**
```
시나리오: BALANCED 1-hop → 1000개 파일
제약: ModeScopeLimit.BALANCED_MAX_NEIGHBORS = 100
결과: 처음 100개만 확장 (BFS 순서)
로그: "Reached max files limit: 100"
```

---

## 4. 충돌 시나리오 & 해결책

### 4.1 동시 인덱싱 충돌

| 충돌 시나리오 | 우선순위 | 해결 방법 |
|-------------|---------|----------|
| FAST (실시간) vs BALANCED (백그라운드) | FAST 우선 | BALANCED pause → 재개 |
| FAST vs DEEP (백그라운드) | FAST 우선 | DEEP timeout 30초 후 force stop |
| BALANCED vs REPAIR | REPAIR 우선 | BALANCED 중단 + 재스케줄 |
| 2개 FAST (동일 파일) | 먼저 시작 | 나중 요청은 대기 |

**엣지케이스 10: FAST 동시 요청**
```
시나리오:
- 사용자 A: main.py 저장 (txn-123)
- 사용자 B: main.py 저장 (txn-456)

ShadowFS 동작:
1. txn-123 commit → IncrementalPlugin 실행 (배치 처리 중)
2. txn-456 commit → IncrementalPlugin 실행 (큐 대기)
3. txn-123 완료 → txn-456 시작
4. main.py 중복 인덱싱 (idempotent하므로 안전)
```

**엣지케이스 11: BALANCED pause → FAST → resume**
```
타임라인:
00:00 - BALANCED 시작 (1000 files)
00:05 - 500 files 완료 (50%)
00:06 - 사용자 활동 (FAST 트리거)
00:06 - pause_current_job() → JobProgress 저장
00:06 - FAST 실행 (10 files, <5초)
00:07 - Idle 5분 대기
00:12 - resume_paused_job() → 500번째부터 재개
00:15 - BALANCED 완료 (총 15분)
```

### 4.2 FileWatcher Debouncing

**엣지케이스 12: 연속 저장 (Cmd+S 연타)**
```
이벤트 시퀀스:
00:00.000 - main.py modified
00:00.100 - main.py modified
00:00.200 - main.py modified

Debouncer 동작:
00:00.000 - 이벤트 추가 (debounce  시작)
00:00.100 - 기존 이벤트 덮어쓰기 ( 리셋)
00:00.200 - 기존 이벤트 덮어쓰기 ( 리셋)
00:00.500 - 배치 준비 완료 (main.py 1회만 처리)
```

**엣지케이스 13: 디렉토리 이동**
```
이벤트: mv src/old_dir src/new_dir (100 files)
FileWatcher:
- 100개 MOVED 이벤트 발생
- Debouncer: max_batch_window_ms=5000 내 모아서 처리
- ChangeSet: renamed={old/a.py: new/a.py, ...} (100개)
```

### 4.3 Transaction Timeout & Cleanup

**엣지케이스 14: Stale transaction**
```
시나리오: ShadowFS write → 1시간 내 commit 없음
- IncrementalPlugin: TTL 1시간 (3600s)
- Cleanup task: 1시간 후 _pending_changes, _pending_ir_deltas 삭제
- 로그: "stale_txns_cleaned: 1"
```

---

## 5. 우선순위 & 중단 정책

### 5.1 BackgroundScheduler 우선순위

```python
class Priority(int, Enum):
    HIGH = 1    # REPAIR (데이터 복구)
    MEDIUM = 2  # BALANCED (일반)
    LOW = 3     # DEEP (비용 큼)
```

**우선순위 큐 동작:**
```
대기열:
1. Job(DEEP, priority=LOW)
2. Job(BALANCED, priority=MEDIUM)
3. Job(REPAIR, priority=HIGH)

실행 순서: REPAIR → BALANCED → DEEP
```

### 5.2 Graceful Stop

**엣지케이스 15: BALANCED 중단 (graceful)**
```python
await scheduler.stop(graceful=True, timeout=30.0)

동작:
1. stop_event.set() → IndexingOrchestrator에 신호
2. 현재 파일 처리 완료 대기 (최대 30초)
3. JobProgress 저장 (completed_files, processing_file)
4. scheduler.stop 완료

현재 파일 처리 완료 후:
- processing_file = None
- completed_files = [f1, f2, ..., f500]
- is_paused = True
```

**엣지케이스 16: Timeout 초과**
```
시나리오: 현재 파일 처리 30초 초과 (매우 큰 파일)
- graceful_stop_timeout 발생
- 로그: "graceful_stop_timeout, timeout_seconds=30"
- 강제 중단 (JobProgress 손실 가능)
```

---

## 6. 성능 특성 비교

### 6.1 레이턴시 비교 (10K 파일 기준)

| 파이프라인 | 시작 레이턴시 | 처리 시간 (변경 1개) | 처리 시간 (변경 100개) | Overhead |
|-----------|-------------|-------------------|---------------------|----------|
| ShadowFS (FAST) | < | < | <1초 | 배치 처리 |
| FileWatcher (FAST) | < | < | <1초 | Debouncing |
| BackgroundScheduler (BALANCED) | Idle 5분 | ~2분 | ~5분 | Idle 감지 |
| ChangeDetector (CLI) | 즉시 | ~5초 | ~30초 | git diff |

### 6.2 메모리 사용량

| 컴포넌트 | Base | Peak (100 concurrent) | GC 후 |
|---------|------|---------------------|-------|
| ShadowFS Plugin | ~5MB | ~50MB (transaction 추적) | ~10MB |
| FileWatcher | ~10MB | ~30MB (event queue) | ~10MB |
| BackgroundScheduler | ~2MB | ~20MB (JobProgress) | ~5MB |

### 6.3 병렬 처리

**ShadowFS 언어별 병렬:**
```python
# incremental_plugin.py:_on_commit()
files_by_lang = {
    "python": [a.py, b.py],
    "typescript": [x.ts, y.ts],
}
tasks = [
    process_language_batch("python", [a.py, b.py]),
    process_language_batch("typescript", [x.ts, y.ts]),
]
await asyncio.gather(*tasks)  # 병렬 실행
```

**성능 향상:**
- 순차:  (python) +  (ts) = 
- 병렬: max(, ) =  ✅

---

## 7. 권장 사용 시나리오

### 7.1 시나리오별 최적 파이프라인

| 시나리오 | 추천 파이프라인 | 모드 | 이유 |
|---------|--------------|------|------|
| **IDE 코드 편집** | ShadowFS Plugin | FAST | <, 배치 처리 |
| **git pull** | FileWatcher | FAST | 외부 변경 유일 감지 |
| **점심시간 (Idle)** | BackgroundScheduler | BALANCED | 자동, 방해 없음 |
| **시그니처 변경** | Auto-escalation | DEEP | Transitive 필요 |
| **최초 clone** | CLI (ChangeDetector) | BOOTSTRAP | 전체 레포 |
| **CI/CD** | (미구현) | FAST | PR diff만 |
| **데이터 복구** | CLI | REPAIR | 참조 무결성 |

### 7.2 안티패턴

| 안티패턴 | 문제 | 해결책 |
|---------|------|--------|
| DEEP 모드를 실시간으로 | 30분 소요 | FAST → 자동 escalation |
| FileWatcher 없이 외부 에디터 | 변경 누락 | FileWatcher 필수 |
| BackgroundScheduler 없이 24시간 | Stale index | Scheduler 활성화 |
| 동일 파일 중복 인덱싱 | 리소스 낭비 | Idempotent 설계 (안전) |

### 7.3 Best Practice 조합

**개인 개발자 (Laptop):**
```
1. ShadowFS Plugin (FAST) - 실시간
2. FileWatcher (FAST) - git pull 대응
3. BackgroundScheduler (BALANCED) - Idle 시
```

**팀 개발 (Server):**
```
1. FileWatcher (FAST) - 실시간
2. BackgroundScheduler (BALANCED) - 6시간마다
3. Job Queue (DEEP) - nightly (0시)
4. PR Pipeline (FAST) - CI/CD
```

---

## 8. 체크리스트

### 8.1 구현 완료 ✅

- [x] ShadowFS IncrementalUpdatePlugin
- [x] FileWatcher (Watchdog)
- [x] BackgroundScheduler (Idle 감지)
- [x] ChangeDetector (git/mtime/hash)
- [x] ScopeExpander (SIGNATURE_CHANGED escalation)
- [x] Graceful stop (JobProgress)
- [x] Rename 감지 (similarity)
- [x] Priority Queue
- [x] Debouncing ()

### 8.2 미구현 ⏳

- [ ] PR 전용 파이프라인 (CI/CD)
- [ ] Multi-repo FileWatcher 통합
- [ ] Job Queue 실시간 모니터링 UI
- [ ] ImpactAnalyzer ← GraphStore 완전 통합
- [ ] DEEP 모드 checkpointing (현재 BALANCED만)

### 8.3 개선 필요 🟡

- [ ] DEEP timeout 30초 → 설정 가능하게
- [ ] BALANCED max_neighbors 100 → 동적 조정
- [ ] Rename similarity 0.90 → 튜닝 필요
- [ ] FileWatcher exclude_patterns → 설정 파일로

---

## 9. 참고 파일

### 9.1 핵심 구현

```
src/contexts/analysis_indexing/infrastructure/
├── mode_manager.py              # 모드 결정
├── background_scheduler.py      # Idle → BALANCED
├── file_watcher.py              # Watchdog
├── change_detector.py           # git/mtime/hash
├── scope_expander.py            # 범위 확장 + escalation
├── watcher_debouncer.py         #  debounce
├── models/mode.py               # IndexingMode, Layer
└── models/job.py                # JobProgress

src/contexts/codegen_loop/infrastructure/shadowfs/plugins/
└── incremental_plugin.py        # ShadowFS 통합
```

### 9.2 RFC/ADR

```
_docs/_backlog/RFC-019-Infer-grade-null-analysis.md  # 실시간, 분석모드
_docs/system-handbook/codegraph-full-system-v3.md  # 전체 시스템
```

---

## 10. 결론

**복잡도:** 5개 모드 × 6개 트리거 = 30개 조합 (실제 사용 ~15개)

**핵심 전략:**
1. **실시간 = ShadowFS (FAST)** - IDE 내부
2. **외부 변경 = FileWatcher (FAST)** - git pull
3. **자동 = BackgroundScheduler (BALANCED)** - Idle 5분
4. **시그니처 변경 = Auto-escalation (DEEP)** - 자동 감지
5. **최초 = BOOTSTRAP** - 한 번만

**엣지케이스 대응:**
- 16개 엣지케이스 문서화 ✅
- Graceful stop (JobProgress) ✅
- Debouncing () ✅
- Priority Queue (HIGH/MEDIUM/LOW) ✅
- Idempotent 설계 (중복 인덱싱 안전) ✅

**미래 작업:**
- PR 파이프라인 구현
- DEEP checkpointing
- 동적 threshold 조정

---

## 11. 파이프라인 레이어 상세 (SOTA)

### 11.1 전체 레이어 구조 (9 Layers)

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1: Structural IR (Tree-sitter)                            │
│   - AST 파싱 → Nodes/Edges                                       │
│   - 상대적 비용: 낮음-중간                                        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Occurrences (SCIP)                                     │
│   - Definition/Reference 추출                                     │
│   - 상대적 비용: 낮음                                             │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Type Enrichment (RFC-032/033/034)                     │
│   - RFC-032: Return Type Summary (Inter-procedural)            │
│   - RFC-032 Ext: Variable Type Enrichment                      │
│   - RFC-033: Expression Type Inference                         │
│   - RFC-034: Generic/TypeVar Type Inference                    │
│   - 상대적 비용: 낮음                                             │
│   - 로컬 커버리지: 높음 (99%+)                                   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Cross-file Resolution                                  │
│   - Symbol linking                                              │
│   - 상대적 비용: 매우 낮음                                        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 5: Semantic IR (CFG/DFG/BFG/Expression)                  │
│   - Control Flow Graph                                          │
│   - Data Flow Graph                                             │
│   - Basic Block Flow Graph                                      │
│   - Expression IR                                               │
│   - 상대적 비용: 높음 (가장 무거움)                              │
├─────────────────────────────────────────────────────────────────┤
│ Layer 6: Advanced Analysis (PDG/Taint)                         │
│   - Program Dependence Graph                                    │
│   - Taint Analysis                                              │
│   - 상대적 비용: 중간                                             │
├─────────────────────────────────────────────────────────────────┤
│ Layer 7: Retrieval Indexes                                      │
│   - RAG/Search 최적화                                            │
│   - 상대적 비용: 매우 낮음                                        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 8: Diagnostics                                            │
│   - Linter errors                                               │
│   - 상대적 비용: 매우 낮음                                        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 9: Package Analysis                                       │
│   - 의존성 분석                                                  │
│   - 상대적 비용: 매우 낮음                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 11.2 Layer 3: Type Enrichment 상세

**RFC-032: Return Type Summary (Inter-procedural)**
```
목적: 함수 간 타입 전파
방법: Tarjan SCC + Fixed-point iteration
성능: O(N) with call graph
커버리지: 높음 (Summary 기반)
```

**RFC-032 Ext: Variable Type Enrichment**
```
목적: 변수 타입 추론
방법: Assignment 분석 (call/attribute/literal)
성능: O(Variables) with name index
커버리지: 중간 (Class inference)
```

**RFC-033: Expression Type Inference**
```
목적: Expression 레벨 타입 (DFG/Taint 정밀도)
방법: Bidirectional inference
성능: O(Expressions)
사용: Binary ops, conditionals, subscripts
```

**RFC-034: Generic/TypeVar Type Inference**
```
목적: Generic 타입 인스턴스화
방법: Robinson's Unification (1965) + Hindley-Milner (1978)
성능: O(Generics × TypeVars)
커버리지: Generic 함수/클래스 완전 지원
오버헤드: 낮음

지원 언어:
  - Python: TypeVar 직접 파싱
  - TypeScript: generic_params
  - Java: type_parameters
  - Kotlin: type_parameters

예시:
  def identity(x: T) -> T: return x
  result = identity(42)  # → result: int ✅
```

### 11.3 고급 알고리즘 요약

| RFC | 알고리즘 | 복잡도 | 상대적 비용 |
|-----|---------|--------|-------------|
| RFC-030 | Sparse Constant Propagation | O(N) | 낮음 |
| RFC-032 | Tarjan SCC + Fixed-point | O(N) | 낮음 |
| RFC-033 | Bidirectional Type Inference | O(Expr) | 낮음 |
| RFC-034 | Robinson's Unification | O(G×T) | 매우 낮음 |

**특징:**
- Layer 5 (Semantic IR)가 가장 무거움 (전체의 50%+)
- Type Enrichment (L3)는 경량 (전체의 5% 내외)
- RFC-034 Generic 추론은 오버헤드 최소 (1% 미만)

---

**Status:** 🟢 Production Ready
