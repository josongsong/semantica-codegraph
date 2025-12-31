# 인덱싱 파이프라인 빠른 참조 (Quick Reference)

> 어떤 파이프라인을 언제 사용할지 3분 안에 이해하기

---

## TL;DR

```
IDE 편집 중      → ShadowFS (FAST, <)
git pull 후      → FileWatcher (FAST, <)
점심시간 (Idle)  → BackgroundScheduler (BALANCED, 자동)
시그니처 변경    → 자동 DEEP escalation
최초 clone       → BOOTSTRAP
```

---

## 1. 파이프라인 선택 플로우차트

```
변경 발생
    ├─ IDE 내부 편집? ──→ YES ──→ ShadowFS Plugin (FAST)
    │                       │
    │                       └─ 시그니처 변경? ──→ YES ──→ 자동 DEEP
    │
    ├─ 외부 변경 (git pull)? ──→ YES ──→ FileWatcher (FAST)
    │
    ├─ Idle 5분 이상? ──→ YES ──→ BackgroundScheduler (BALANCED)
    │
    ├─ 최초 인덱싱? ──→ YES ──→ BOOTSTRAP
    │
    └─ 데이터 손상? ──→ YES ──→ REPAIR
```

---

## 2. 모드 비교 (10K 파일 기준)

| 모드 | 레이어 | 시간 | 사용 시점 |
|------|--------|------|----------|
| FAST | L1+L2 | ~5초 | 실시간 피드백 |
| BALANCED | L1+L2+L3 | ~2분 | 자동 (Idle 5분) |
| DEEP | L1+L2+L3+L4 | ~30분 | 시그니처 변경 시 |
| BOOTSTRAP | L1+L2+L3_SUMMARY | ~10분 | 최초 |
| REPAIR | 동적 | 가변 | 복구 |

---

## 3. 트리거 비교

| 트리거 | 레이턴시 | 자동화 | 사용 시점 |
|--------|---------|--------|----------|
| ShadowFS | < | ✅ | 코드 편집 |
| FileWatcher | < | ✅ | git pull |
| BackgroundScheduler | Idle 5분 | ✅ | 자동 |
| CLI | 즉시 | ⏸️ | 수동 |

---

## 4. 핵심 엣지케이스 (Top 5)

### 4.1 SIGNATURE_CHANGED 자동 DEEP
```
def func(x) → def func(x, y)  # 시그니처 변경
FAST 시도 → 자동 DEEP escalation
```

### 4.2 BALANCED 중단 + 재개
```
BALANCED 50% 완료 → 사용자 활동
→ pause → FAST 실행 → Idle 후 50%부터 재개
```

### 4.3 중복 이벤트 (Debouncing)
```
Cmd+S 3회 ( 간격)
→  debounce → 1회만 인덱싱
```

### 4.4 Rename 감지
```
git mv old.py new.py
→ ChangeDetector: RENAMED (재인덱싱 불필요)
git 없으면 → similarity 0.90+ 판정
```

### 4.5 동시 트리거 우선순위
```
FAST (실시간) > REPAIR > BALANCED > DEEP
BALANCED 실행 중 + FAST 요청
→ BALANCED pause → FAST 실행
```

---

## 5. 충돌 해결 매트릭스

| 상황 | 우선순위 | 동작 |
|------|---------|------|
| FAST vs BALANCED | FAST | BALANCED pause |
| FAST vs DEEP | FAST | DEEP timeout 30초 |
| REPAIR vs 모든 것 | REPAIR | 기존 중단 |
| 2개 FAST | 먼저 시작 | 나중 대기 |

---

## 6. 설정 (기본값)

```python
# 모드 전환 조건
FAST_TO_BALANCED_IDLE_MINUTES = 5       # Idle 5분 후
FAST_TO_BALANCED_HOURS_SINCE_LAST = 24  # 24시간마다
FAST_TO_BALANCED_MIN_CHANGED_FILES = 10 # 변경 10개 이상

# 범위 제한
BALANCED_MAX_NEIGHBORS = 100            # 1-hop 최대 100개
DEEP_SUBSET_MAX_FILES = 500             # DEEP subset 최대
DEEP_SUBSET_MAX_PERCENT = 0.1           # 전체의 10%

# Debouncing
DEBOUNCE_MS = 300                       # 
MAX_BATCH_WINDOW_MS = 5000              # 5초

# Timeout
TTL = 3600                              # Transaction 1시간
GRACEFUL_STOP_TIMEOUT = 30              # 30초
```

---

## 7. Best Practice

### 개인 개발자
```bash
# .env 또는 설정
ENABLE_SHADOWFS=true           # IDE 편집
ENABLE_FILE_WATCHER=true       # git pull
ENABLE_BACKGROUND_SCHEDULER=true  # Idle
```

### 팀 서버
```bash
ENABLE_FILE_WATCHER=true       # 실시간
BACKGROUND_BALANCED_HOURS=6    # 6시간마다
NIGHTLY_DEEP=true              # 매일 0시 DEEP
```

---

## 8. 안티패턴

| 안티패턴 | 문제 | 해결책 |
|---------|------|--------|
| DEEP를 실시간으로 | 30분 소요 | FAST + 자동 escalation |
| FileWatcher 비활성화 | 외부 변경 누락 | 항상 켜기 |
| BackgroundScheduler 없음 | Stale index | 활성화 |

---

## 9. 디버깅 체크리스트

### 인덱싱이 안 됨
- [ ] ShadowFS Plugin 활성화?
- [ ] FileWatcher 실행 중?
- [ ] `.gitignore` 제외 패턴 확인
- [ ] 로그 확인: `file_watcher_batch_ready`

### 너무 느림
- [ ] DEEP 모드 중? → pause 후 FAST
- [ ] Debouncing 길이 확인 ()
- [ ] 파일 개수 확인 (>10K?)

### 자동 전환 안 됨
- [ ] Idle 5분 경과?
- [ ] `IdleDetector.mark_activity()` 호출 중?
- [ ] BackgroundScheduler 실행 중?

---

## 10. 로그 키워드

```bash
# 정상 동작
grep "file_watcher_batch_ready" logs/
grep "background_job_starting" logs/
grep "signature_change_detected_auto_escalating" logs/

# 에러
grep "graceful_stop_timeout" logs/
grep "hash_mtime_detection_failed" logs/
grep "background_job_failed" logs/
```

---

## 11. 관련 문서

- 상세 분석: `indexing-pipelines-detailed.md`
- 시스템 전체: `codegraph-full-system-v3.md`
- RFC-019: 실시간, 분석모드

---

**Last 
**읽는 시간:** 3분
