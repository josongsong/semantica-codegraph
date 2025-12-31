# File Watcher Integration Guide

SOTA File Watcher로 실시간 증분 인덱싱을 구현하는 완전 가이드.

## 목차

1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [기본 사용법](#기본-사용법)
4. [FastAPI 통합](#fastapi-통합)
5. [고급 설정](#고급-설정)
6. [모니터링](#모니터링)
7. [문제 해결](#문제-해결)

---

## 개요

FileWatcherManager는 엔터프라이즈급 파일 감시 시스템으로, 다음 기능을 제공합니다:

- ✅ **Multi-repository 동시 감시**: 여러 저장소를 동시에 감시
- ✅ **Intelligent debouncing**: 파일별 독립 디바운싱 (300ms)
- ✅ **Batch processing**: 연속 변경 묶음 처리 (2초 윈도우)
- ✅ **Rate limiting**: 과부하 방지 (초당 100 이벤트)
- ✅ **Graceful shutdown**: 안전한 종료
- ✅ **Error recovery**: 자동 에러 복구
- ✅ **Metrics & observability**: 완전한 관찰 가능성

### 성능 특성

| 항목 | 값 | 설명 |
|------|-----|------|
| **Debounce Delay** | 300ms | 연속 저장 방지 |
| **Batch Window** | 2초 | 배치 윈도우 |
| **Max Batch Size** | 50 files | 최대 배치 크기 |
| **Rate Limit** | 100 events/sec | 초당 최대 이벤트 |
| **Supported Extensions** | .py, .rs, .ts, .js, .java, .kt, .go | 감시 대상 확장자 |

---

## 아키텍처

```
FileWatcherManager (Singleton)
  ├─ RepoWatcher (per repository)
  │   ├─ Observer (watchdog)
  │   ├─ IncrementalIndexEventHandler
  │   ├─ IntelligentDebouncer
  │   └─ RateLimiter
  └─ IncrementalIndexer (shared)
```

### 컴포넌트 설명

1. **FileWatcherManager**: 전체 시스템 관리 (싱글톤)
   - 여러 저장소 중앙 관리
   - Graceful shutdown
   - 통계 집계

2. **RepoWatcher**: 저장소별 감시
   - Observer 생명주기 관리
   - Event handler 연결
   - 인덱싱 조정

3. **IntelligentDebouncer**: 지능형 디바운싱
   - 파일별 독립 디바운스
   - 배치 집계
   - 적응형 스케줄링

4. **RateLimiter**: 속도 제한
   - Token bucket 알고리즘
   - 과부하 방지

5. **IncrementalIndexEventHandler**: 이벤트 처리
   - 파일 필터링 (확장자, 무시 디렉토리)
   - 이벤트 정규화
   - 비동기 처리

---

## 기본 사용법

### 1. 기본 설정

```python
from pathlib import Path
from codegraph_engine.multi_index.infrastructure.watch.file_watcher import (
    FileWatcherManager,
    WatchConfig,
)
from codegraph_engine.multi_index.infrastructure.service.incremental_indexer import (
    IncrementalIndexer,
)

# IncrementalIndexer 생성
indexer = IncrementalIndexer(
    registry=index_registry,
    file_queue=file_queue,
    queue_threshold=10,
)

# WatchConfig 생성 (기본값 사용 가능)
config = WatchConfig(
    debounce_delay=0.3,  # 300ms
    batch_window=2.0,  # 2초
    max_batch_size=50,
    max_events_per_second=100,
)

# FileWatcherManager 생성 (싱글톤)
manager = FileWatcherManager(indexer, config)
```

### 2. 시작 및 저장소 추가

```python
import asyncio

async def main():
    # 매니저 시작
    await manager.start()

    # 저장소 추가
    await manager.add_repository(
        repo_id="my_project",
        repo_path=Path("/path/to/project")
    )

    print("File watcher started. Monitoring /path/to/project")

    # 감시 계속 (무한 루프)
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stopping file watcher...")
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. 여러 저장소 감시

```python
async def watch_multiple_repos():
    await manager.start()

    # 여러 저장소 동시 감시
    repos = {
        "frontend": Path("/workspace/frontend"),
        "backend": Path("/workspace/backend"),
        "shared": Path("/workspace/shared-lib"),
    }

    for repo_id, repo_path in repos.items():
        await manager.add_repository(repo_id, repo_path)
        print(f"Watching {repo_id}: {repo_path}")

    # 통계 확인
    stats = manager.get_stats()
    print(f"Total repositories: {stats['repository_count']}")
```

---

## FastAPI 통합

### 완전한 FastAPI 통합 예제

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from codegraph_engine.multi_index.infrastructure.watch.file_watcher import (
    FileWatcherManager,
    WatchConfig,
)
from codegraph_engine.multi_index.infrastructure.service.incremental_indexer import (
    IncrementalIndexer,
)

# Global manager instance
file_watcher_manager: FileWatcherManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 생명주기 관리"""
    global file_watcher_manager

    # Startup: FileWatcher 시작
    print("Starting File Watcher Manager...")

    # IndexRegistry, IncrementalIndexer 초기화 (실제 구현에 맞게 수정)
    from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexRegistry

    registry = IndexRegistry()
    indexer = IncrementalIndexer(registry=registry)

    # FileWatcherManager 생성 및 시작
    config = WatchConfig()
    file_watcher_manager = FileWatcherManager(indexer, config)
    await file_watcher_manager.start()

    # 기본 저장소 추가 (환경변수나 설정에서 가져오기)
    import os
    default_repo = os.getenv("DEFAULT_REPO_PATH")
    if default_repo:
        await file_watcher_manager.add_repository(
            repo_id="default",
            repo_path=Path(default_repo)
        )
        print(f"Watching default repository: {default_repo}")

    print("File Watcher Manager started!")

    yield  # 애플리케이션 실행

    # Shutdown: FileWatcher 중지
    print("Stopping File Watcher Manager...")
    await file_watcher_manager.stop()
    print("File Watcher Manager stopped!")


# FastAPI 앱 생성
app = FastAPI(
    title="Codegraph API with File Watching",
    lifespan=lifespan,
)


# API 모델
class AddRepoRequest(BaseModel):
    repo_id: str
    repo_path: str


class RepoStats(BaseModel):
    repo_id: str
    is_running: bool
    indexing_in_progress: bool
    pending_events: int
    current_rate: int


# API 엔드포인트
@app.post("/api/v1/watch/repositories")
async def add_repository(request: AddRepoRequest):
    """저장소 감시 시작"""
    if file_watcher_manager is None:
        raise HTTPException(status_code=500, detail="File watcher not initialized")

    repo_path = Path(request.repo_path)
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail=f"Repository path not found: {request.repo_path}")

    await file_watcher_manager.add_repository(request.repo_id, repo_path)

    return {
        "status": "success",
        "message": f"Started watching repository: {request.repo_id}",
        "repo_path": str(repo_path),
    }


@app.delete("/api/v1/watch/repositories/{repo_id}")
async def remove_repository(repo_id: str):
    """저장소 감시 중지"""
    if file_watcher_manager is None:
        raise HTTPException(status_code=500, detail="File watcher not initialized")

    if not file_watcher_manager.is_watching(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")

    await file_watcher_manager.remove_repository(repo_id)

    return {
        "status": "success",
        "message": f"Stopped watching repository: {repo_id}",
    }


@app.get("/api/v1/watch/repositories")
async def list_repositories():
    """감시 중인 저장소 목록"""
    if file_watcher_manager is None:
        raise HTTPException(status_code=500, detail="File watcher not initialized")

    repos = file_watcher_manager.get_watched_repositories()

    return {
        "total": len(repos),
        "repositories": repos,
    }


@app.get("/api/v1/watch/stats")
async def get_stats():
    """전체 통계"""
    if file_watcher_manager is None:
        raise HTTPException(status_code=500, detail="File watcher not initialized")

    stats = file_watcher_manager.get_stats()

    return stats


@app.get("/api/v1/watch/repositories/{repo_id}/stats", response_model=RepoStats)
async def get_repo_stats(repo_id: str):
    """특정 저장소 통계"""
    if file_watcher_manager is None:
        raise HTTPException(status_code=500, detail="File watcher not initialized")

    if not file_watcher_manager.is_watching(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")

    stats = file_watcher_manager.get_stats()
    repo_stats = stats["repositories"].get(repo_id)

    if not repo_stats:
        raise HTTPException(status_code=404, detail=f"Stats not found for: {repo_id}")

    return repo_stats


# Health check
@app.get("/health")
async def health():
    """서비스 헬스 체크"""
    if file_watcher_manager is None:
        return {"status": "degraded", "file_watcher": "not_initialized"}

    stats = file_watcher_manager.get_stats()

    return {
        "status": "healthy",
        "file_watcher": {
            "running": stats["is_running"],
            "repositories": stats["repository_count"],
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7200)
```

### 사용 예제

```bash
# 서버 시작
uvicorn main:app --reload

# 저장소 추가
curl -X POST http://localhost:7200/api/v1/watch/repositories \
  -H "Content-Type: application/json" \
  -d '{"repo_id": "my_project", "repo_path": "/workspace/my_project"}'

# 감시 중인 저장소 목록
curl http://localhost:7200/api/v1/watch/repositories

# 전체 통계
curl http://localhost:7200/api/v1/watch/stats

# 특정 저장소 통계
curl http://localhost:7200/api/v1/watch/repositories/my_project/stats

# 저장소 제거
curl -X DELETE http://localhost:7200/api/v1/watch/repositories/my_project
```

---

## 고급 설정

### 커스텀 WatchConfig

```python
from codegraph_engine.multi_index.infrastructure.watch.file_watcher import WatchConfig

# 고성능 설정 (빠른 반응)
fast_config = WatchConfig(
    debounce_delay=0.1,  # 100ms (더 빠른 반응)
    batch_window=0.5,  # 500ms (더 작은 배치)
    max_batch_size=20,
    max_events_per_second=200,  # 더 높은 처리량
)

# 저성능 시스템 설정 (안정성 우선)
slow_config = WatchConfig(
    debounce_delay=1.0,  # 1초 (안정적)
    batch_window=5.0,  # 5초 (큰 배치)
    max_batch_size=100,
    max_events_per_second=50,  # 낮은 부하
)

# 추가 확장자 감시
custom_config = WatchConfig(
    watched_extensions=(".py", ".rs", ".ts", ".js", ".java", ".kt", ".go", ".cpp", ".c"),
    ignored_dirs=(
        "__pycache__", ".git", "node_modules", "target", ".venv",
        "build", "dist", ".pytest_cache", ".mypy_cache",
    ),
)
```

### 환경변수 설정

```bash
# .env 파일
FILE_WATCHER_DEBOUNCE_DELAY=0.3
FILE_WATCHER_BATCH_WINDOW=2.0
FILE_WATCHER_MAX_BATCH_SIZE=50
FILE_WATCHER_RATE_LIMIT=100
DEFAULT_REPO_PATH=/workspace/my_project
```

```python
import os

config = WatchConfig(
    debounce_delay=float(os.getenv("FILE_WATCHER_DEBOUNCE_DELAY", "0.3")),
    batch_window=float(os.getenv("FILE_WATCHER_BATCH_WINDOW", "2.0")),
    max_batch_size=int(os.getenv("FILE_WATCHER_MAX_BATCH_SIZE", "50")),
    max_events_per_second=int(os.getenv("FILE_WATCHER_RATE_LIMIT", "100")),
)
```

---

## 모니터링

### 로그 분석

FileWatcher는 구조화된 로그를 출력합니다:

```python
# 정상 작동 예시 로그
INFO file_watcher_manager_started
INFO repository_added_to_watch repo_id=my_project repo_path=/workspace/my_project
DEBUG file_event_received file_path=main.py event_type=modified repo_id=my_project
INFO batch_indexing_started repo_id=my_project file_count=3 event_count=5
INFO batch_indexing_completed repo_id=my_project status=success indexed_count=3 duration_ms=145

# 에러 예시 로그
WARNING event_dropped_rate_limit file_path=test.py event_type=modified
ERROR batch_indexing_failed repo_id=my_project error=TimeoutError
WARNING indexing_already_in_progress_skipping repo_id=my_project event_count=2
```

### Metrics 수집

```python
from codegraph_shared.infra.observability import record_counter, record_histogram

# 통계 메트릭 수집
stats = manager.get_stats()

for repo_id, repo_stats in stats["repositories"].items():
    # Prometheus metrics 예시
    record_counter(
        "file_watcher_pending_events",
        labels={"repo_id": repo_id},
        value=repo_stats["pending_events"],
    )

    record_counter(
        "file_watcher_current_rate",
        labels={"repo_id": repo_id},
        value=repo_stats["current_rate"],
    )

    # 인덱싱 진행 상태
    if repo_stats["indexing_in_progress"]:
        record_counter(
            "file_watcher_indexing_in_progress",
            labels={"repo_id": repo_id},
            value=1,
        )
```

### 헬스 체크

```python
def check_file_watcher_health() -> dict:
    """FileWatcher 헬스 체크"""
    stats = manager.get_stats()

    # 기본 상태
    if not stats["is_running"]:
        return {"status": "down", "reason": "manager_not_running"}

    # 저장소별 체크
    unhealthy_repos = []
    for repo_id, repo_stats in stats["repositories"].items():
        # 대기 중인 이벤트가 너무 많으면 경고
        if repo_stats["pending_events"] > 100:
            unhealthy_repos.append({
                "repo_id": repo_id,
                "issue": "high_pending_events",
                "count": repo_stats["pending_events"],
            })

        # Rate limit 초과 확인
        if repo_stats["current_rate"] > 90:  # 90 events/sec
            unhealthy_repos.append({
                "repo_id": repo_id,
                "issue": "high_event_rate",
                "rate": repo_stats["current_rate"],
            })

    if unhealthy_repos:
        return {
            "status": "degraded",
            "unhealthy_repositories": unhealthy_repos,
        }

    return {
        "status": "healthy",
        "repository_count": stats["repository_count"],
    }
```

---

## 문제 해결

### Q1: 파일 변경이 감지되지 않아요

**원인**:
- 파일 확장자가 `watched_extensions`에 없음
- 디렉토리가 `ignored_dirs`에 포함됨
- Observer가 시작되지 않음

**해결**:
```python
# 1. 확장자 확인
config = WatchConfig(
    watched_extensions=(".py", ".rs", ".ts"),  # 원하는 확장자 추가
)

# 2. 로그 확인
import logging
logging.basicConfig(level=logging.DEBUG)

# 3. 저장소 상태 확인
stats = manager.get_stats()
print(stats["repositories"]["my_repo"]["is_running"])  # True여야 함
```

### Q2: Rate limit exceeded 에러가 발생해요

**원인**:
- 너무 많은 파일이 동시에 변경됨
- `max_events_per_second`가 너무 낮음

**해결**:
```python
# Rate limit 증가
config = WatchConfig(
    max_events_per_second=200,  # 기본값 100 → 200
)

# 또는 일시적으로 비활성화
config = WatchConfig(
    enable_rate_limiting=False,  # 주의: 과부하 위험!
)
```

### Q3: 인덱싱이 너무 느려요

**원인**:
- Batch window가 너무 큼
- 파일이 너무 많음

**해결**:
```python
# 1. Batch window 줄이기
config = WatchConfig(
    batch_window=1.0,  # 2초 → 1초
    max_batch_size=20,  # 50 → 20
)

# 2. Priority 높이기
await indexer.index_files(
    repo_id="my_repo",
    snapshot_id="main",
    file_paths=files,
    priority=2,  # 즉시 실행 (큐 사용 안 함)
)
```

### Q4: 메모리 사용량이 계속 증가해요

**원인**:
- Pending events가 계속 쌓임
- Debouncer에 취소되지 않은 태스크가 남아있음

**해결**:
```python
# 1. 통계 확인
stats = manager.get_stats()
for repo_id, repo_stats in stats["repositories"].items():
    if repo_stats["pending_events"] > 100:
        print(f"WARNING: {repo_id} has {repo_stats['pending_events']} pending events")

# 2. 저장소 재시작
await manager.remove_repository("problematic_repo")
await manager.add_repository("problematic_repo", Path("/path/to/repo"))
```

### Q5: Graceful shutdown이 안 돼요

**원인**:
- 인덱싱이 진행 중
- Observer가 멈추지 않음

**해결**:
```python
import asyncio

# Timeout을 추가한 shutdown
async def graceful_shutdown(manager, timeout=10.0):
    try:
        await asyncio.wait_for(manager.stop(), timeout=timeout)
        print("Shutdown completed")
    except asyncio.TimeoutError:
        print(f"WARNING: Shutdown timed out after {timeout}s")
        # Force stop (watchdog Observer.stop() 호출)
        for repo_id in list(manager._watchers.keys()):
            watcher = manager._watchers.pop(repo_id)
            watcher.observer.stop()
            watcher.observer.join(timeout=1.0)
```

---

## 참고 자료

- [INDEXING_STRATEGY.md](./INDEXING_STRATEGY.md) - 인덱싱 전략 전체 문서
- [IncrementalIndexer 소스](../packages/codegraph-engine/codegraph_engine/multi_index/infrastructure/service/incremental_indexer.py)
- [FileWatcher 소스](../packages/codegraph-engine/codegraph_engine/multi_index/infrastructure/watch/file_watcher.py)
- [Watchdog 공식 문서](https://python-watchdog.readthedocs.io/)

---

## 다음 단계

1. ✅ **FileWatcher 구현 완료** (이 문서)
2. **Manual Trigger API 구현** ([INDEXING_STRATEGY.md](./INDEXING_STRATEGY.md) 참고)
3. **Cold Start 초기화** (FastAPI startup event)
4. **Git Hooks 구현** (post-commit 스크립트)
5. **Scheduler 구현** (APScheduler 통합)

---

**작성**: 2025-12-29
**버전**: 1.0
**상태**: Production Ready ✅
