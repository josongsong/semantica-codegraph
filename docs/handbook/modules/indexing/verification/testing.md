# 인덱싱 시스템 테스트 가이드

> 테스트 시나리오 및 벤치마크

---

## 테스트 원칙 (필수)

- **NO Fake/Stub**: 항상 성공/고정값을 반환하는 Fake는 금지 (실버그를 놓침)
- **필요 최소한만 Mock**: 외부 의존성/비용(예: IR 빌드)이 과도한 지점만 제한적으로 Mock
- **Real 데이터 우선**: 반환값/상태는 실제 형태로 맞추고, 테스트는 재현 가능한 입력/기대 출력 중심으로 구성

---

## 목차

1. [Unit Tests](#1-unit-tests)
2. [Integration Tests](#2-integration-tests)
3. [E2E Tests](#3-e2e-tests)
4. [Performance Tests](#4-performance-tests)
5. [Chaos Engineering](#5-chaos-engineering)

---

## 1. Unit Tests

### ChangeDetector

```python
# tests/unit/analysis_indexing/test_change_detector.py
import pytest
from src.contexts.analysis_indexing.infrastructure.change_detector import (
    ChangeDetector,
    ChangeSet,
)

class TestChangeDetector:
    def test_git_diff_detection(self, tmp_path):
        """git diff 기반 변경 감지"""
        # Setup
        repo = create_test_repo(tmp_path)
        detector = ChangeDetector(git_helper=GitHelper())

        # Add file
        (repo / "new_file.py").write_text("print('hello')")
        git_commit(repo, "Add new file")

        # Detect
        changes = detector.detect_changes(repo, "test-repo")

        # Assert
        assert "new_file.py" in changes.added
        assert changes.is_empty() == False

    def test_rename_detection_by_similarity(self, tmp_path):
        """Similarity 기반 rename 감지"""
        # Setup
        repo = create_test_repo(tmp_path)
        detector = ChangeDetector(enable_content_similarity=True)

        # Create and delete (simulate rename)
        change_set = ChangeSet(
            added={"src/new.py"},
            deleted={"src/old.py"},
            modified=set(),
        )

        # Mock file_hash_store
        detector.file_hash_store = MockHashStore({
            "src/old.py": {"size": 1000}
        })

        # Detect rename
        result = detector._detect_renames_by_similarity(repo, change_set)

        # Assert
        assert "src/old.py" in result.renamed
        assert result.renamed["src/old.py"] == "src/new.py"

    def test_mtime_fallback(self, tmp_path):
        """git 없을 때 mtime fallback"""
        # No git repo
        detector = ChangeDetector(git_helper=None)

        changes = detector.detect_changes(
            tmp_path,
            "test-repo",
            use_git=False,
            use_mtime=True,
        )

        assert isinstance(changes, ChangeSet)
```

### ScopeExpander

```python
# tests/unit/analysis_indexing/test_scope_expander.py
class TestScopeExpander:
    @pytest.mark.asyncio
    async def test_fast_mode_no_expansion(self):
        """FAST 모드는 확장 안 함"""
        expander = ScopeExpander()
        change_set = ChangeSet(modified={"main.py"})

        result = await expander.expand_scope(
            change_set,
            mode=IndexingMode.FAST,
            repo_id="test",
        )

        assert result == {"main.py"}

    @pytest.mark.asyncio
    async def test_signature_changed_auto_deep(self):
        """SIGNATURE_CHANGED → 자동 DEEP"""
        expander = ScopeExpander()
        impact_result = MockImpactResult(
            changed_symbols=[
                ChangedSymbol(
                    fqn="func",
                    change_type=ChangeType.SIGNATURE_CHANGED,
                )
            ]
        )

        result = await expander.expand_scope(
            ChangeSet(modified={"main.py"}),
            mode=IndexingMode.FAST,  # FAST 시도
            repo_id="test",
            impact_result=impact_result,
        )

        # DEEP로 자동 escalation → 2-hop 확장
        assert len(result) > 1
```

### ModeManager

```python
# tests/unit/analysis_indexing/test_mode_manager.py
class TestModeManager:
    @pytest.mark.asyncio
    async def test_auto_mode_selection_bootstrap(self):
        """첫 인덱싱 → BOOTSTRAP"""
        manager = ModeManager(
            change_detector=detector,
            scope_expander=expander,
            metadata_store=MockMetadataStore(last_indexed=None),
        )

        plan = await manager.create_plan(
            repo_path=Path("/repo"),
            repo_id="test",
            mode=None,  # 자동 선택
            auto_mode=True,
        )

        assert plan.mode == IndexingMode.BOOTSTRAP

    def test_transition_to_balanced(self):
        """Idle 5분 → BALANCED 전환"""
        manager = ModeManager(...)

        should_transition = manager.should_transition_to_balanced(
            repo_id="test",
            idle_minutes=6.0,  # 5분 초과
        )

        assert should_transition == True
```

---

## 2. Integration Tests

### 9-Stage Pipeline

```python
# tests/integration/analysis_indexing/test_orchestrator.py
class TestIndexingOrchestrator:
    @pytest.mark.asyncio
    async def test_full_pipeline_fast_mode(self, test_repo):
        """FAST 모드 전체 파이프라인"""
        orchestrator = IndexingOrchestrator(
            parser_service=parser,
            ir_builder=ir_builder,
            # ... 기타 컴포넌트
        )

        result = await orchestrator.execute(
            repo_path=test_repo,
            repo_id="test-repo",
            snapshot_id="snap-123",
            mode=IndexingMode.FAST,
        )

        assert result.success == True
        assert result.indexed_files > 0
        assert result.duration_ms < 10000  # <10초

    @pytest.mark.asyncio
    async def test_graceful_stop(self, test_repo):
        """Graceful stop + checkpoint"""
        orchestrator = IndexingOrchestrator(...)
        stop_event = asyncio.Event()
        progress = JobProgress(job_id="test-job")

        # 비동기 실행
        task = asyncio.create_task(
            orchestrator.execute_with_stop(
                test_repo,
                stop_event,
                progress,
            )
        )

        # 1초 후 중단
        await asyncio.sleep(1)
        stop_event.set()

        result = await task

        # 부분 완료 확인
        assert result.partial == True
        assert len(progress.completed_files) > 0
        assert progress.processing_file is None  # 현재 파일 완료
```

### Job Orchestrator

```python
# tests/integration/analysis_indexing/test_job_orchestrator.py
class TestJobOrchestrator:
    @pytest.mark.asyncio
    async def test_distributed_lock(self, redis_client):
        """Distributed lock으로 single writer 보장"""
        orchestrator1 = IndexJobOrchestrator(
            ...,
            redis_client=redis_client,
            instance_id="worker-1",
        )
        orchestrator2 = IndexJobOrchestrator(
            ...,
            redis_client=redis_client,
            instance_id="worker-2",
        )

        # 동일 repo+snapshot에 두 Job 제출
        job1 = await orchestrator1.submit_job("repo", "snap", repo_path)
        job2 = await orchestrator2.submit_job("repo", "snap", repo_path)

        # 동시 실행 시도
        results = await asyncio.gather(
            orchestrator1.execute_job(job1.id, repo_path),
            orchestrator2.execute_job(job2.id, repo_path),
            return_exceptions=True,
        )

        # 하나는 성공, 하나는 LockAcquisitionError
        assert sum(1 for r in results if not isinstance(r, Exception)) == 1

    @pytest.mark.asyncio
    async def test_checkpoint_resume(self, postgres_store):
        """Checkpoint에서 재개"""
        orchestrator = IndexJobOrchestrator(...)

        # Job 시작 → 중단 (50% 완료)
        job = await orchestrator.submit_job("repo", "snap", repo_path)

        # Checkpoint 저장 (50개 파일 완료)
        await orchestrator._save_checkpoint(
            job.id,
            JobProgress(
                job_id=job.id,
                completed_files=[f"file_{i}.py" for i in range(50)],
                total_files=100,
            ),
        )

        # 재실행
        result = await orchestrator.execute_job(job.id, repo_path)

        # 나머지 50개만 처리
        assert result.files_processed == 50
```

### FileWatcher

```python
# tests/integration/analysis_indexing/test_file_watcher.py
class TestFileWatcher:
    @pytest.mark.asyncio
    async def test_debouncing(self, tmp_path):
        """연속 저장 → 1회만 인덱싱"""
        batches = []

        async def on_changes(change_set: ChangeSet):
            batches.append(change_set)

        watcher = FileWatcher(
            repo_path=tmp_path,
            repo_id="test",
            on_changes=on_changes,
            debounce_ms=300,
        )

        await watcher.start()

        # 3회 연속 저장 ( 간격)
        file = tmp_path / "test.py"
        for i in range(3):
            file.write_text(f"version {i}")
            await asyncio.sleep(0.1)

        # Debounce 대기 ()
        await asyncio.sleep(0.4)

        # 1개 배치만 생성
        assert len(batches) == 1
        assert "test.py" in batches[0].modified
```

---

## 3. E2E Tests

### 실제 레포 인덱싱

```python
# tests/e2e/test_real_repo_indexing.py
class TestRealRepoIndexing:
    @pytest.mark.slow
    @pytest.mark.e2e
    async def test_index_small_repo(self):
        """작은 실제 레포 (typer - 100 files)"""
        repo_url = "https://github.com/tiangolo/typer.git"
        repo_path = clone_repo(repo_url)

        orchestrator = IndexingOrchestrator.from_config(
            load_config("config/test.toml")
        )

        result = await orchestrator.execute(
            repo_path=repo_path,
            repo_id="typer",
            snapshot_id="test",
            mode=IndexingMode.BALANCED,
        )

        # Assertions
        assert result.success == True
        assert result.indexed_files >= 50
        assert result.duration_ms < 60000  # <1분

        # 검색 테스트
        search_result = await search_service.search(
            repo_id="typer",
            query="def main",
        )
        assert len(search_result.results) > 0

    @pytest.mark.slow
    @pytest.mark.e2e
    async def test_index_medium_repo(self):
        """중간 레포 (rich - 1K files)"""
        repo_url = "https://github.com/Textualize/rich.git"
        repo_path = clone_repo(repo_url)

        result = await orchestrator.execute(
            repo_path=repo_path,
            repo_id="rich",
            snapshot_id="test",
            mode=IndexingMode.DEEP,
        )

        assert result.success == True
        assert result.indexed_files >= 500
        assert result.duration_ms < 300000  # <5분
```

### 증분 인덱싱

```python
class TestIncrementalIndexing:
    @pytest.mark.e2e
    async def test_incremental_after_commit(self, test_repo):
        """커밋 후 증분 인덱싱"""
        # 1. 최초 인덱싱
        result1 = await orchestrator.execute(
            repo_path=test_repo,
            repo_id="test",
            snapshot_id="snap-1",
            mode=IndexingMode.BOOTSTRAP,
        )

        # 2. 파일 변경 + 커밋
        (test_repo / "main.py").write_text("# Updated")
        git_commit(test_repo, "Update main.py")

        # 3. 증분 인덱싱
        result2 = await orchestrator.execute(
            repo_path=test_repo,
            repo_id="test",
            snapshot_id="snap-2",
            mode=IndexingMode.FAST,
        )

        # 변경된 1개 파일만 처리
        assert result2.indexed_files == 1
        assert result2.duration_ms < result1.duration_ms
```

---

## 4. Performance Tests

### 벤치마크

```python
# tests/performance/test_indexing_benchmark.py
class TestIndexingBenchmark:
    @pytest.mark.benchmark
    def test_parse_1000_files(self, benchmark):
        """1000 파일 파싱 벤치마크"""
        files = generate_test_files(count=1000)
        parser = ParsingStage(...)

        result = benchmark(lambda: asyncio.run(parser.execute(files)))

        # 목표: <30초
        assert result.stats['mean'] < 30.0

    @pytest.mark.benchmark
    def test_embedding_throughput(self, benchmark):
        """임베딩 처리량"""
        chunks = generate_test_chunks(count=100)
        embedding_service = EmbeddingService(batch_size=32)

        result = benchmark(lambda: asyncio.run(
            embedding_service.embed_batch(chunks)
        ))

        # 목표: >100 chunks/sec
        throughput = 100 / result.stats['mean']
        assert throughput > 100
```

### Stress Test

```python
class TestStressScenarios:
    @pytest.mark.stress
    async def test_100_concurrent_jobs(self):
        """100개 동시 Job"""
        orchestrator = IndexJobOrchestrator(...)

        jobs = [
            await orchestrator.submit_job(f"repo-{i}", "snap", repo_path)
            for i in range(100)
        ]

        results = await asyncio.gather(
            *[orchestrator.execute_job(j.id, repo_path) for j in jobs],
            return_exceptions=True,
        )

        # 모두 성공 또는 Conflict로 skip
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0

    @pytest.mark.stress
    async def test_memory_leak(self):
        """메모리 누수 테스트"""
        import tracemalloc

        tracemalloc.start()
        initial_mem = tracemalloc.get_traced_memory()[0]

        # 100회 반복
        for i in range(100):
            await orchestrator.execute(
                repo_path=test_repo,
                repo_id="test",
                snapshot_id=f"snap-{i}",
                mode=IndexingMode.FAST,
            )

        final_mem = tracemalloc.get_traced_memory()[0]
        growth = (final_mem - initial_mem) / initial_mem

        # 10% 이내 증가
        assert growth < 0.10
```

---

## 5. Chaos Engineering

### 장애 시나리오

```python
# tests/chaos/test_failure_scenarios.py
class TestChaosEngineering:
    @pytest.mark.chaos
    async def test_redis_failure_during_indexing(self):
        """인덱싱 중 Redis 장애"""
        orchestrator = IndexJobOrchestrator(...)
        job = await orchestrator.submit_job("repo", "snap", repo_path)

        # 인덱싱 시작
        task = asyncio.create_task(
            orchestrator.execute_job(job.id, repo_path)
        )

        # 50% 완료 후 Redis 중단
        await asyncio.sleep(2)
        stop_redis()

        # Checkpoint 저장 실패 → Job 실패
        with pytest.raises(RedisConnectionError):
            await task

        # Redis 복구
        start_redis()

        # 재시도 → 성공
        result = await orchestrator.execute_job(job.id, repo_path)
        assert result.success == True

    @pytest.mark.chaos
    async def test_postgres_failure(self):
        """PostgreSQL 장애"""
        stop_postgres()

        with pytest.raises(DatabaseConnectionError):
            await orchestrator.submit_job("repo", "snap", repo_path)

        start_postgres()

        # 재시도 성공
        job = await orchestrator.submit_job("repo", "snap", repo_path)
        assert job.id is not None

    @pytest.mark.chaos
    async def test_network_partition(self):
        """네트워크 파티션"""
        # Qdrant 격리
        isolate_container("qdrant")

        # 인덱싱 시도 → Vector 인덱싱 실패
        result = await orchestrator.execute(
            repo_path=test_repo,
            repo_id="test",
            snapshot_id="snap",
            mode=IndexingMode.FAST,
        )

        # 부분 성공 (Lexical/Symbol만)
        assert result.partial == True

        # 네트워크 복구
        unisolate_container("qdrant")
```

---

## 테스트 실행

### Pytest 명령

```bash
# Unit tests
pytest tests/unit/analysis_indexing/ -v

# Integration tests
pytest tests/integration/analysis_indexing/ -v

# E2E tests (느림)
pytest tests/e2e/ -v --slow

# Performance tests
pytest tests/performance/ -v --benchmark

# Stress tests
pytest tests/stress/ -v --stress

# Chaos tests
pytest tests/chaos/ -v --chaos

# 전체 (CI)
pytest tests/ -v --cov=src/contexts/analysis_indexing
```

### Coverage

```bash
# Coverage 측정
pytest tests/ --cov=src/contexts/analysis_indexing --cov-report=html

# 목표: >80%
# 현재: 75% ()
```

---

## CI/CD 통합

### GitHub Actions

```yaml
# .github/workflows/test-indexing.yml
name: Test Indexing System

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest tests/unit/analysis_indexing/ -v

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
      qdrant:
        image: qdrant/qdrant:latest
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: pytest tests/integration/analysis_indexing/ -v

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E tests
        run: pytest tests/e2e/ -v --slow
```

---

## 참고

### Test Fixtures
```
tests/fixtures/
├── repos/
│   ├── small/  (typer)
│   ├── medium/ (rich)
│   └── large/  (django)
├── configs/
│   └── test.toml
└── mocks/
    ├── mock_git.py
    ├── mock_redis.py
    └── mock_qdrant.py
```

### 관련 문서
- `troubleshooting.md` - 문제 해결
- `configuration.md` - 테스트 설정
- `pipelines-detailed.md` - 엣지케이스

---

**Last 
