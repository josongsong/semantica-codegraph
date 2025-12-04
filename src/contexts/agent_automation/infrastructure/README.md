# Incremental Indexing Adapter

## 사용법

### 1. PostgresStore 초기화 (필수)

증분 인덱싱을 사용하기 전에 PostgresStore를 초기화해야 합니다:

```python
from src.container import container

# PostgresStore 초기화
await container.postgres_store.initialize()
```

### 2. 증분 인덱싱 실행

```python
service = container.incremental_indexing_service
registry = container.repo_registry

# 리포지토리 등록
repo_path = Path("/path/to/repo")
registry.register("my-repo", repo_path)

# 증분 인덱싱 실행
result = await service.index_files(
    repo_id="my-repo",
    snapshot_id="main",
    file_paths=["src/file1.py", "src/file2.py"],
    reason="agent_apply",
    execute_immediately=True,  # 백그라운드에서 즉시 실행
)

# 결과 확인
print(f"Status: {result.status}")
print(f"Success: {result.success}")
print(f"Total files: {result.total_files}")
```

### 3. 작업 완료 대기 (선택적)

```python
# 특정 repo의 인덱싱이 완료될 때까지 대기
completed = await service.wait_until_idle(
    repo_id="my-repo",
    snapshot_id="main",
    timeout=30.0,
)

if completed:
    print("Indexing completed!")
else:
    print("Timeout - still running in background")
```

## 주의사항

1. **PostgresStore 초기화**: 반드시 `await container.postgres_store.initialize()` 호출
2. **execute_immediately**: `True`(기본값)이면 백그라운드에서 즉시 실행, `False`면 Job만 큐에 넣음
3. **indexed_count**: 항상 0 (백그라운드 실행이므로)
4. **5종 인덱스**: Symbol index는 Memgraph unhealthy 시 비활성화됨

## 아키텍처

```
Agent → IncrementalIndexingAdapter → IndexJobOrchestrator
                                    ↓
                            submit_job() → DB (QUEUED)
                                    ↓
                     execute_immediately=True
                                    ↓
                            Background Task → execute_job()
                                    ↓
                            IndexingOrchestrator → 5종 인덱스
```
