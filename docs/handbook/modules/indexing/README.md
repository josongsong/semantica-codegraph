# 인덱싱 시스템 문서 디렉토리

> 인덱싱 파이프라인의 모든 것

---

## 문서 구조

```
indexing/
├── README.md (여기)                          # 문서 디렉토리 가이드
├── VERIFICATION-RESULT.md ⭐                 # 비판적 검증 최종 결과 (필독!)
├── pipelines-detailed.md                     # 파이프라인 상세 분석 (16 엣지케이스)
├── pipelines-quick-ref.md                    # 빠른 참조 (3분 읽기)
├── pipelines-diagrams.md                     # Mermaid 다이어그램 모음
├── edge-case-coverage.md                     # 엣지케이스 해결 가능성 분석
├── sota-comparison.md                        # SOTA 비교 분석
├── 9-stage-pipeline.md                       # 9단계 파이프라인 상세
├── job-orchestrator.md                       # Job 기반 인덱싱
├── git-history-analysis.md                   # Git 히스토리 분석
├── configuration.md                          # 설정 가이드
├── troubleshooting.md                        # 문제 해결
└── testing.md                                # 테스트 시나리오
```

---

## 빠른 시작

### 먼저 읽을 것 (필독!)
1. **VERIFICATION-RESULT.md** ⭐ - 비판적 검증 결과 (5분, 필독!)

### 처음 읽는 사람
1. **pipelines-quick-ref.md** (3분) - 전체 개요
2. **pipelines-diagrams.md** - 시각적 이해
3. **configuration.md** - 설정 방법

### 상세 분석이 필요한 사람
1. **pipelines-detailed.md** (20분) - 모든 엣지케이스
3. **edge-case-coverage.md** - 엣지케이스 해결 가능성 (코드 검증)
4. **sota-comparison.md** 🏆 - SOTA 비교 분석
5. **9-stage-pipeline.md** - 각 단계별 상세
6. **job-orchestrator.md** - Job 시스템

### 문제 해결이 필요한 사람
1. **troubleshooting.md** - 증상별 해결책
2. **testing.md** - 테스트 방법 (원칙 포함)

---

## 주요 개념

### 파이프라인 (6종)
1. **ShadowFS Plugin** - IDE 편집 실시간
2. **FileWatcher** - 외부 변경 감지
3. **BackgroundScheduler** - Idle 자동
4. **ChangeDetector** - CLI/API
5. **Job Queue** - 대규모 배치
6. **PR 분석** - 미구현

### 모드 (5종)
1. **FAST** - 변경만 (~5초)
2. **BALANCED** - 변경+1hop (~2분)
3. **DEEP** - 변경+2hop (~30분)
4. **BOOTSTRAP** - 전체 (~10분)
5. **REPAIR** - 복구 (가변)

### 레이어 (L0-L4)
- **L0** - 변경 감지 (git/mtime/hash)
- **L1** - 파싱 (AST)
- **L2** - 기본 IR + 청크
- **L3** - Semantic IR (CFG/DFG)
- **L4** - 고급 분석 (Cross-function)

---

## 아키텍처

```
User
 ├─ IDE 편집 ──→ ShadowFS ──→ IncrementalPlugin ──→ Indexing
 ├─ git pull ──→ FileWatcher ──→ Debouncer ──→ Indexing
 ├─ Idle ──→ BackgroundScheduler ──→ Job Queue ──→ Indexing
 └─ CLI ──→ ChangeDetector ──→ ModeManager ──→ Indexing

Indexing
 ├─ 9-Stage Pipeline
 │   ├─ GitStage
 │   ├─ DiscoveryStage
 │   ├─ ParsingStage
 │   ├─ IRStage
 │   ├─ SemanticIRStage
 │   ├─ GraphStage
 │   ├─ ChunkStage
 │   ├─ RepoMapStage
 │   └─ IndexingStage
 │
 └─ Storage
     ├─ PostgreSQL (metadata)
     ├─ Qdrant (vectors)
     ├─ Zoekt (lexical)
     └─ Tantivy (delta)
```

---

## 핵심 컴포넌트

### Orchestrators
- **IndexingOrchestratorSlim** - 기본 9단계
- **IndexingOrchestrator** - + Mode/Scope
- **IndexJobOrchestrator** - + Distributed Lock

### Managers
- **ModeManager** - 모드 자동 선택
- **ScopeExpander** - 범위 확장 + Escalation
- **BackgroundScheduler** - Idle 감지 + Job Queue

### Detectors
- **ChangeDetector** - git/mtime/hash
- **IdleDetector** - 사용자 활동 추적
- **FileWatcher** - Watchdog 기반

---

## 사용 사례

### 시나리오 1: 개인 개발자 (Laptop)
```python
# 자동 설정 (권장)
ENABLE_SHADOWFS = True          # IDE 편집
ENABLE_FILE_WATCHER = True      # git pull
ENABLE_BACKGROUND_SCHEDULER = True  # Idle 5분

# 결과
- 코드 편집 중: < 피드백
- git pull 후: < 자동 인덱싱
- 점심시간: BALANCED 자동 실행
```

### 시나리오 2: 팀 서버 (CI/CD)
```python
# Job-based 설정
ENABLE_FILE_WATCHER = True       # 실시간
BACKGROUND_BALANCED_HOURS = 6    # 6시간마다
NIGHTLY_DEEP = True              # 매일 0시

# 결과
- 실시간: FAST
- 정기: BALANCED (6h)
- 야간: DEEP (0시)
```

### 시나리오 3: 최초 clone
```bash
python -m src.cli.main index /repo --mode bootstrap
# BOOTSTRAP 모드 (L1+L2+L3_SUMMARY)
# 예상 시간: ~10분 (10K 파일)
```

---

## 성능 특성

### 레이턴시 (10K 파일 기준)

| 파이프라인 | 시작 | 1개 파일 | 100개 파일 |
|-----------|------|---------|-----------|
| ShadowFS | < | < | <1s |
| FileWatcher | < | < | <1s |
| Background | 5min | ~2min | ~5min |

### 메모리

| 컴포넌트 | Base | Peak | GC 후 |
|---------|------|------|-------|
| ShadowFS | ~5MB | ~50MB | ~10MB |
| FileWatcher | ~10MB | ~30MB | ~10MB |
| Background | ~2MB | ~20MB | ~5MB |

---

## 우선순위

```
충돌 시 우선순위:
FAST > REPAIR > BALANCED > DEEP

예: BALANCED 실행 중 + FAST 요청
→ BALANCED pause → FAST 실행 → 재개
```

---

## 엣지케이스 (Top 5)

1. **SIGNATURE_CHANGED 자동 DEEP**
   - `def func(x)` → `def func(x, y)`
   - FAST 시도 → 자동 DEEP escalation

2. **BALANCED pause & resume**
   - 50% 완료 → 사용자 활동
   - pause → FAST → 50%부터 재개

3. **Debouncing**
   - Cmd+S 3회 ()
   -  후 1회만 인덱싱

4. **Rename 감지**
   - git: R100 판정
   - no git: similarity ≥ 0.90

5. **Stale transaction**
   - 1시간 후 자동 cleanup

---

## 관련 문서

### RFC/ADR
- RFC-019: 실시간, 분석모드
- RFC-018: SQLite First Strategy
- ADR-002: QueryEngine

### 시스템 전체
- codegraph-full-system-v3.md

---

## 기여 가이드

### 새 파이프라인 추가
1. `pipelines-detailed.md`에 엣지케이스 추가
2. `pipelines-diagrams.md`에 다이어그램 추가
3. `configuration.md`에 설정 추가
4. 테스트 작성

### 문서 업데이트
- 모든 변경사항은 `README.md`에도 반영
- 날짜 업데이트 필수
- 예제 코드 검증

---

**Last 
**Maintainer:** Infrastructure Team
**Status:** 🟢 Production Ready (PR 파이프라인 제외)
