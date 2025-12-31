# 인덱싱 문제 해결 가이드

> 증상별 해결책

---

## 목차

1. [인덱싱이 안 됨](#1-인덱싱이-안-됨)
2. [너무 느림](#2-너무-느림)
3. [메모리 부족](#3-메모리-부족)
4. [Lock 문제](#4-lock-문제)
5. [데이터 불일치](#5-데이터-불일치)
6. [로그 분석](#6-로그-분석)

---

## 1. 인덱싱이 안 됨

### 증상 1-1: ShadowFS 이벤트 무반응

```
저장해도 인덱싱이 트리거되지 않음
```

**체크리스트:**

```bash
# 1. ShadowFS Plugin 활성화 확인
grep "IncrementalUpdatePlugin initialized" logs/

# 2. Transaction commit 확인
grep "on_event.*COMMIT" logs/

# 3. 파일 추적 확인
grep "Tracked.*for batch processing" logs/
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| Plugin 미등록 | EventBus.plugins 확인 | `bus.register(plugin)` |
| txn_id 불일치 | 로그에서 txn_id 추적 | transaction 관리 확인 |
| TTL 초과 | `stale_txns_cleaned` 로그 | TTL 증가 (3600 → 7200) |

**해결 방법:**

```python
# EventBus 상태 확인
print(f"Registered plugins: {len(event_bus.plugins)}")

# Plugin 재등록
plugin = IncrementalUpdatePlugin(ir_builder, indexer)
event_bus.register(plugin)

# 수동 트리거
await plugin.on_event(ShadowFSEvent(
    type="commit",
    txn_id="manual-123",
    timestamp=time.time(),
))
```

---

### 증상 1-2: FileWatcher 변경 감지 안 함

```
git pull 후에도 인덱싱 안 됨
```

**체크리스트:**

```bash
# 1. FileWatcher 실행 중인지
grep "file_watcher_started" logs/

# 2. Watchdog 이벤트 수신
grep "file_modified\|file_created" logs/

# 3. 제외 패턴 확인
grep "should_ignore" logs/
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| Watcher 중단됨 | `is_running=False` | `await watcher.start()` |
| 제외 패턴 매칭 | `.gitignore` 파일 확인 | `exclude_patterns` 수정 |
| 잘못된 확장자 | `supported_extensions` | 확장자 추가 |
| Debounce 대기 중 |  대기 | 잠시 대기 |

**해결 방법:**

```python
# Watcher 상태 확인
stats = watcher.get_stats()
print(f"Running: {stats['is_running']}")
print(f"Pending events: {stats['pending_events']}")

# 재시작
if not watcher.is_running:
    await watcher.start()

# 수동 트리거
await watcher._on_batch_ready(ChangeSet(
    added={"main.py"},
    modified=set(),
    deleted=set(),
))
```

---

### 증상 1-3: BackgroundScheduler 실행 안 됨

```
Idle 5분 경과해도 BALANCED 안 됨
```

**체크리스트:**

```bash
# 1. Scheduler 실행 중인지
grep "background_scheduler_started" logs/

# 2. Idle 상태 확인
grep "is_idle.*True" logs/

# 3. Job 스케줄 확인
grep "background_job_scheduled" logs/
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| Scheduler 시작 안 함 | `scheduler.is_running` | `await scheduler.start()` |
| 계속 활동 중 | `IdleDetector.get_idle_minutes()` | 활동 중단 |
| 최근 실행됨 | 마지막 실행 시간 | 24시간 대기 |
| Job queue full | `scheduler.get_queue_size()` | 큐 비우기 |

**해결 방법:**

```python
# Scheduler 상태
print(f"Running: {scheduler.is_running}")
print(f"Queue size: {scheduler.get_queue_size()}")
print(f"Idle: {idle_detector.is_idle()}")

# 강제 스케줄
await scheduler.schedule(
    repo_id="my-repo",
    mode=IndexingMode.BALANCED,
)
```

---

## 2. 너무 느림

### 증상 2-1: FAST 모드가 느림 (>5초)

```
변경 1개 파일 → 30초 소요
```

**체크리스트:**

```bash
# 1. 실제 모드 확인
grep "indexing_mode_selected" logs/ | tail -1

# 2. Stage별 시간
grep "stage_completed" logs/ | tail -10

# 3. 파일 개수 확인
grep "target_files_count" logs/ | tail -1
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| 자동 DEEP escalation | `auto_escalating_to_deep` | SIGNATURE_CHANGED 회피 |
| Scope 과도 확장 | `target_files_count` | `max_neighbors` 감소 |
| 외부 LSP 타임아웃 | Pyright 로그 | LSP 비활성화 |
| Qdrant 느림 | Embedding 시간 | Batch size 증가 |

**해결 방법:**

```bash
# 1. Mode 강제 지정
python -m src.cli.main index /repo --mode fast --no-auto-mode

# 2. Scope 제한
export BALANCED_MAX_NEIGHBORS=50

# 3. LSP 비활성화
export ENABLE_PYRIGHT=false

# 4. Embedding batch 증가
export EMBEDDING_BATCH_SIZE=64
```

---

### 증상 2-2: BALANCED가 멈춤

```
50% 진행 후 응답 없음
```

**체크리스트:**

```bash
# 1. 현재 처리 파일
grep "processing_file" logs/ | tail -1

# 2. 데드락 확인
ps aux | grep indexing

# 3. 메모리 확인
free -h
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| 큰 파일 파싱 중 | 파일 크기 확인 | Timeout 증가 |
| 메모리 부족 | OOM 로그 | 메모리 증가 |
| Lock 경합 | Redis 로그 | Lock 해제 |
| Checkpoint 실패 | PostgreSQL 로그 | DB 재연결 |

**해결 방법:**

```python
# Graceful stop
await scheduler.stop(graceful=True, timeout=30)

# 진행상태 확인
progress = scheduler.current_progress
print(f"Completed: {len(progress.completed_files)}/{progress.total_files}")

# Checkpoint에서 재개
await scheduler.resume_paused_job()
```

---

## 3. 메모리 부족

### 증상 3-1: OOM Killed

```
Killed (OOM)
```

**체크리스트:**

```bash
# 1. 메모리 사용량
ps aux --sort=-%mem | head -20

# 2. AST 캐시 크기
grep "ast_cache_size_mb" logs/

# 3. 파일 개수
wc -l <<< $(find . -name "*.py")
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| AST 캐시 과다 | 캐시 크기 로그 | `ast_cache_max_size_mb` 감소 |
| 병렬 처리 과다 | Worker 수 | `parsing_workers` 감소 |
| 큰 파일 | 파일 크기 확인 | 파일 크기 제한 |
| Embedding 배치 | Batch size | `embedding_batch_size` 감소 |

**해결 방법:**

```python
# config/performance.py
PERFORMANCE_CONFIG = {
    # Worker 수 감소 (8 → 4)
    "parsing_workers": 4,
    "ir_workers": 4,

    # 캐시 크기 감소
    "ast_cache_max_size_mb": 200,  # 500 → 200
    "ir_cache_max_size_mb": 500,   # 1000 → 500

    # Embedding batch 감소
    "embedding_batch_size": 16,    # 32 → 16
}
```

---

### 증상 3-2: Redis 메모리 부족

```
Redis OOM command not allowed
```

**해결 방법:**

```bash
# 1. Redis 메모리 확인
redis-cli INFO memory

# 2. 메모리 증가
redis-cli CONFIG SET maxmemory 2gb

# 3. Eviction 정책
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# 4. Lock 정리
redis-cli KEYS "indexing:*" | xargs redis-cli DEL
```

---

## 4. Lock 문제

### 증상 4-1: Lock 획득 실패

```
ERROR: Lock acquisition timeout after 30s
```

**체크리스트:**

```bash
# 1. 실행 중인 Job 확인
SELECT * FROM index_jobs WHERE status='RUNNING';

# 2. Redis Lock 확인
redis-cli KEYS "indexing:*"

# 3. Lock owner 확인
redis-cli GET "indexing:my-repo:snapshot-123"
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| 다른 워커 실행 중 | Job status | 완료 대기 또는 취소 |
| Stale lock | Lock TTL 만료 | Lock 강제 해제 |
| Redis 연결 끊김 | `redis-cli PING` | Redis 재시작 |

**해결 방법:**

```bash
# 1. 실행 중인 Job 취소
UPDATE index_jobs SET status='CANCELLED' WHERE id='job-123';

# 2. Lock 강제 해제
redis-cli DEL "indexing:my-repo:snapshot-123"

# 3. Job 재실행
python -m src.cli.main index /repo --force
```

---

### 증상 4-2: Lock 연장 실패

```
WARNING: Lock extension failed, job may be interrupted
```

**해결 방법:**

```python
# Lock TTL 증가
JOB_ORCHESTRATOR_CONFIG = {
    "lock_ttl_seconds": 600,        # 5분 → 10분
    "lock_extend_interval": 120,    # 2분마다 연장
}

# Redis 타임아웃 증가
REDIS_CONFIG = {
    "socket_timeout": 30,           # 30초
    "socket_connect_timeout": 30,
}
```

---

## 5. 데이터 불일치

### 증상 5-1: 인덱싱했는데 검색 안 됨

```
파일은 인덱싱되었으나 검색 결과 없음
```

**체크리스트:**

```bash
# 1. 인덱싱 완료 확인
SELECT * FROM index_jobs WHERE repo_id='my-repo' ORDER BY completed_at DESC LIMIT 1;

# 2. Qdrant 확인
curl http://localhost:6333/collections/code_chunks/points/count

# 3. Zoekt 확인
zoekt-webserver -index ./data/zoekt
```

**일반적 원인:**

| 원인 | 확인 방법 | 해결책 |
|-----|----------|--------|
| 부분 실패 | `indexed_files` vs 전체 | 재인덱싱 |
| Compaction 지연 | Delta 크기 | 수동 compaction |
| 인덱스 손상 | Consistency check | 인덱스 재빌드 |

**해결 방법:**

```bash
# 1. 일관성 체크
python -m src.cli.main index check /repo

# 2. 재인덱싱 (증분)
python -m src.cli.main index /repo --mode balanced

# 3. 재인덱싱 (전체)
python -m src.cli.main index /repo --mode bootstrap --force

# 4. 수동 compaction
python -m src.cli.main compaction trigger /repo
```

---

### 증상 5-2: Checkpoint 복구 실패

```
WARNING: Checkpoint corrupted, starting from scratch
```

**해결 방법:**

```sql
-- Checkpoint 삭제
UPDATE index_jobs
SET checkpoint = NULL
WHERE id = 'job-123';

-- 재실행
```

---

## 6. 로그 분석

### 주요 로그 패턴

```bash
# 성공 패턴
grep "job_completed\|stage_completed\|indexed.*files" logs/

# 실패 패턴
grep "ERROR\|FAILED\|timeout" logs/

# 성능 패턴
grep "duration_ms\|latency" logs/

# Lock 패턴
grep "lock_acquired\|lock_extended\|lock_released" logs/
```

### 로그 레벨 조정

```python
# config/logging.py
LOGGING_CONFIG = {
    "version": 1,
    "loggers": {
        "src.contexts.analysis_indexing": {
            "level": "DEBUG",  # INFO → DEBUG
        },
        "src.infra.cache.distributed_lock": {
            "level": "DEBUG",
        },
    },
}
```

---

## 긴급 복구 절차

### 1단계: 상태 확인

```bash
# Job 상태
SELECT id, status, started_at, duration_ms
FROM index_jobs
WHERE repo_id = 'my-repo'
ORDER BY created_at DESC
LIMIT 5;

# Lock 상태
redis-cli KEYS "indexing:*"

# 프로세스 상태
ps aux | grep indexing
```

### 2단계: 정리

```bash
# 멈춘 Job 취소
UPDATE index_jobs
SET status = 'CANCELLED'
WHERE status = 'RUNNING' AND started_at < NOW() - INTERVAL '1 hour';

# Stale lock 제거
redis-cli KEYS "indexing:*" | xargs redis-cli DEL

# 임시 파일 삭제
rm -rf /tmp/codegraph/*
```

### 3단계: 재시작

```bash
# Checkpoint 없이 재시작
python -m src.cli.main index /repo --mode fast --force

# 문제 지속 시 BOOTSTRAP
python -m src.cli.main index /repo --mode bootstrap
```

---

## 자주 묻는 질문 (FAQ)

### Q1: FAST 모드인데 왜 30분 걸리나요?

**A:** SIGNATURE_CHANGED 자동 DEEP escalation입니다.
- 함수 시그니처 변경 시 자동으로 DEEP 모드로 전환
- 해결: `--no-auto-mode` 플래그 사용

### Q2: 같은 파일이 계속 재인덱싱됩니다

**A:** ChangeDetector가 계속 변경을 감지합니다.
- git status로 파일 상태 확인
- mtime이 계속 변경되는지 확인
- .gitignore에 추가

### Q3: Qdrant가 디스크 공간을 많이 씁니다

**A:** 임베딩 벡터가 누적됩니다.
- 1M vectors × 768 dim × 4 bytes = 3GB
- 오래된 snapshot 삭제
- Compaction 실행

---

## 문의

### 이슈 리포팅

```bash
# 로그 수집
tar -czf logs.tar.gz logs/

# 설정 내보내기
python -m src.cli.main config export > config.json

# 환경 정보
python -m src.cli.main env > env.txt

# GitHub Issue 생성
gh issue create --title "Indexing stuck at 50%" \
  --body "Attach logs.tar.gz, config.json, env.txt"
```

---

**Last 
