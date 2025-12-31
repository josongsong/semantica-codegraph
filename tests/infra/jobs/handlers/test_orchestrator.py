"""
Parallel Indexing Orchestrator 통합 테스트.

SemanticaTaskEngine과의 통합 및 병렬 파이프라인 동작 검증.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from codegraph_shared.infra.jobs.handlers.orchestrator import (
    ParallelIndexingOrchestrator,
    PipelineResult,
)
from codegraph_shared.infra.jobs.semantica_adapter import SemanticaAdapter
from codegraph_shared.infra.jobs.models import Job, JobState


@dataclass
class MockJobSnapshot:
    """Mock JobSnapshot for testing."""

    job_id: str
    state: str
    progress: int | None = None
    error_message: str | None = None


# Patch target for SemanticaTaskClient (imported inside function)
SEMANTICA_CLIENT_PATCH = "semantica_task_engine.SemanticaTaskClient"


class TestPipelineResult:
    """PipelineResult 테스트."""

    def test_empty_creates_success_result(self):
        """empty()는 성공 결과 생성."""
        result = PipelineResult.empty()
        assert result.success
        assert result.files_processed == 0
        assert result.errors == []

    def test_merge_combines_results(self):
        """merge()는 두 결과 병합."""
        result1 = PipelineResult(
            success=True,
            files_processed=10,
            nodes_created=100,
            edges_created=50,
            chunks_created=20,
            vectors_indexed=20,
            lexical_files_indexed=10,
            duration_seconds=5.0,
            errors=[],
        )
        result2 = PipelineResult(
            success=True,
            files_processed=5,
            nodes_created=50,
            edges_created=25,
            chunks_created=10,
            vectors_indexed=10,
            lexical_files_indexed=5,
            duration_seconds=3.0,
            errors=["warning"],
        )

        merged = result1.merge(result2)

        assert merged.success
        assert merged.files_processed == 15
        assert merged.nodes_created == 150
        assert merged.chunks_created == 30
        assert merged.duration_seconds == 5.0  # max
        assert merged.errors == ["warning"]

    def test_merge_propagates_failure(self):
        """merge()는 실패 전파."""
        result1 = PipelineResult.empty()
        result2 = PipelineResult(
            success=False,
            files_processed=0,
            nodes_created=0,
            edges_created=0,
            chunks_created=0,
            vectors_indexed=0,
            lexical_files_indexed=0,
            duration_seconds=0,
            errors=["Failed"],
        )

        merged = result1.merge(result2)
        assert not merged.success


class TestParallelIndexingOrchestrator:
    """Parallel Indexing Orchestrator 테스트."""

    @pytest.fixture
    def mock_adapter(self):
        """Mock SemanticaAdapter."""
        adapter = MagicMock(spec=SemanticaAdapter)
        adapter.url = "http://localhost:9527"
        adapter.handlers = {}
        return adapter

    @pytest.fixture
    def orchestrator(self, mock_adapter):
        """Orchestrator with mocked adapter."""
        return ParallelIndexingOrchestrator(
            adapter=mock_adapter,
            ir_cache={},
            chunk_cache={},
        )

    @pytest.mark.asyncio
    async def test_register_handlers_populates_adapter(self, orchestrator, mock_adapter):
        """register_handlers()는 adapter에 handler 등록."""
        await orchestrator.register_handlers()

        assert "BUILD_IR" in mock_adapter.handlers
        assert "LEXICAL_INDEX" in mock_adapter.handlers
        assert "BUILD_CHUNK" in mock_adapter.handlers
        assert "VECTOR_INDEX" in mock_adapter.handlers

    @pytest.mark.asyncio
    async def test_parallel_execution_of_ir_and_lexical(self, orchestrator, mock_adapter, tmp_path):
        """L1 (IR)과 L3 (Lexical) 병렬 실행 검증."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        # Mock enqueue
        job_counter = 0

        async def mock_enqueue(**kwargs):
            nonlocal job_counter
            job_counter += 1
            return Job(
                job_id=f"job-{job_counter}",
                job_type=kwargs["job_type"],
                queue=kwargs["queue"],
                subject_key=kwargs["subject_key"],
                payload=kwargs["payload"],
            )

        mock_adapter.enqueue = AsyncMock(side_effect=mock_enqueue)

        # Mock SemanticaTaskClient
        with patch(SEMANTICA_CLIENT_PATCH) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock()

            # Mock wait_for_job - Phase 1 jobs complete
            async def mock_wait(job_id, timeout_ms=30000):
                if "1" in job_id:  # IR job
                    return MockJobSnapshot(job_id=job_id, state="DONE", progress=10)
                elif "2" in job_id:  # Lexical job
                    return MockJobSnapshot(job_id=job_id, state="DONE", progress=10)
                elif "3" in job_id:  # Chunk job
                    return MockJobSnapshot(job_id=job_id, state="DONE", progress=50)
                elif "4" in job_id:  # Vector job
                    return MockJobSnapshot(job_id=job_id, state="DONE", progress=50)
                return MockJobSnapshot(job_id=job_id, state="DONE")

            mock_client.wait_for_job = AsyncMock(side_effect=mock_wait)

            # Execute
            result = await orchestrator.index_repository(
                repo_path=str(tmp_path),
                repo_id="test-repo",
                timeout_seconds=60,
            )

            # Verify parallel enqueue (IR and Lexical)
            enqueue_calls = mock_adapter.enqueue.call_args_list
            assert len(enqueue_calls) >= 2

            # First two calls should be IR and Lexical (parallel)
            job_types = [call.kwargs["job_type"] for call in enqueue_calls[:2]]
            assert "BUILD_IR" in job_types
            assert "LEXICAL_INDEX" in job_types

    @pytest.mark.asyncio
    async def test_chunk_waits_for_ir_completion(self, orchestrator, mock_adapter, tmp_path):
        """L2 (Chunk)는 L1 (IR) 완료 후 실행."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        enqueue_order = []

        async def mock_enqueue(**kwargs):
            enqueue_order.append(kwargs["job_type"])
            return Job(
                job_id=f"job-{len(enqueue_order)}",
                job_type=kwargs["job_type"],
                queue=kwargs["queue"],
                subject_key=kwargs["subject_key"],
                payload=kwargs["payload"],
            )

        mock_adapter.enqueue = AsyncMock(side_effect=mock_enqueue)

        with patch(SEMANTICA_CLIENT_PATCH) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock()

            mock_client.wait_for_job = AsyncMock(return_value=MockJobSnapshot(job_id="job", state="DONE", progress=10))

            await orchestrator.index_repository(
                repo_path=str(tmp_path),
                repo_id="test-repo",
            )

            # Verify order: IR/Lexical first, then Chunk, then Vector
            assert "BUILD_IR" in enqueue_order[:2]
            assert "LEXICAL_INDEX" in enqueue_order[:2]
            chunk_idx = enqueue_order.index("BUILD_CHUNK")
            assert chunk_idx > enqueue_order.index("BUILD_IR")

    @pytest.mark.asyncio
    async def test_ir_failure_stops_pipeline(self, orchestrator, mock_adapter, tmp_path):
        """L1 (IR) 실패 시 파이프라인 중단."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        job_counter = 0

        async def mock_enqueue(**kwargs):
            nonlocal job_counter
            job_counter += 1
            return Job(
                job_id=f"job-{job_counter}",
                job_type=kwargs["job_type"],
                queue=kwargs["queue"],
                subject_key=kwargs["subject_key"],
                payload=kwargs["payload"],
            )

        mock_adapter.enqueue = AsyncMock(side_effect=mock_enqueue)

        with patch(SEMANTICA_CLIENT_PATCH) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock()

            # IR fails, Lexical succeeds
            async def mock_wait(job_id, timeout_ms=30000):
                if "1" in job_id:  # IR job
                    return MockJobSnapshot(
                        job_id=job_id,
                        state="FAILED",
                        error_message="IR build error",
                    )
                return MockJobSnapshot(job_id=job_id, state="DONE", progress=10)

            mock_client.wait_for_job = AsyncMock(side_effect=mock_wait)

            result = await orchestrator.index_repository(
                repo_path=str(tmp_path),
                repo_id="test-repo",
            )

            assert not result.success
            assert any("IR build failed" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_skip_vector_option(self, orchestrator, mock_adapter, tmp_path):
        """skip_vector=True 시 벡터 인덱싱 스킵."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        enqueue_types = []

        async def mock_enqueue(**kwargs):
            enqueue_types.append(kwargs["job_type"])
            return Job(
                job_id=f"job-{len(enqueue_types)}",
                job_type=kwargs["job_type"],
                queue=kwargs["queue"],
                subject_key=kwargs["subject_key"],
                payload=kwargs["payload"],
            )

        mock_adapter.enqueue = AsyncMock(side_effect=mock_enqueue)

        with patch(SEMANTICA_CLIENT_PATCH) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock()

            mock_client.wait_for_job = AsyncMock(return_value=MockJobSnapshot(job_id="job", state="DONE", progress=10))

            await orchestrator.index_repository(
                repo_path=str(tmp_path),
                repo_id="test-repo",
                skip_vector=True,
            )

            assert "VECTOR_INDEX" not in enqueue_types

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self, orchestrator, mock_adapter, tmp_path):
        """타임아웃 시 실패 반환."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        job_counter = 0

        async def mock_enqueue(**kwargs):
            nonlocal job_counter
            job_counter += 1
            return Job(
                job_id=f"job-{job_counter}",
                job_type=kwargs["job_type"],
                queue=kwargs["queue"],
                subject_key=kwargs["subject_key"],
                payload=kwargs["payload"],
            )

        mock_adapter.enqueue = AsyncMock(side_effect=mock_enqueue)

        with patch(SEMANTICA_CLIENT_PATCH) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock()

            # Simulate timeout - the wait_for_job raises TimeoutError
            async def timeout_wait(*args, **kwargs):
                raise TimeoutError("Simulated timeout")

            mock_client.wait_for_job = timeout_wait

            result = await orchestrator.index_repository(
                repo_path=str(tmp_path),
                repo_id="test-repo",
                timeout_seconds=1,
            )

            assert not result.success
            # Timeout or error message should be present
            assert len(result.errors) > 0


class TestCacheSharing:
    """캐시 공유 테스트."""

    @pytest.mark.asyncio
    async def test_ir_cache_shared_between_handlers(self):
        """IR 캐시는 IRBuildHandler와 ChunkBuildHandler 간 공유."""
        shared_cache = {}

        from codegraph_shared.infra.jobs.handlers.ir_handler import IRBuildHandler
        from codegraph_shared.infra.jobs.handlers.chunk_handler import ChunkBuildHandler

        ir_handler = IRBuildHandler(ir_cache=shared_cache)
        chunk_handler = ChunkBuildHandler(ir_cache=shared_cache)

        # IRBuildHandler가 캐시에 저장
        shared_cache["ir:test:main"] = {
            "ir_documents": {"test.py": MagicMock(nodes=[], edges=[])},
            "repo_id": "test",
        }

        # ChunkBuildHandler가 캐시에서 읽기
        assert "ir:test:main" in chunk_handler.ir_cache

    @pytest.mark.asyncio
    async def test_chunk_cache_shared_between_handlers(self):
        """Chunk 캐시는 ChunkBuildHandler와 VectorIndexHandler 간 공유."""
        shared_cache = {}

        from codegraph_shared.infra.jobs.handlers.chunk_handler import ChunkBuildHandler
        from codegraph_shared.infra.jobs.handlers.vector_handler import VectorIndexHandler

        chunk_handler = ChunkBuildHandler(chunk_cache=shared_cache)
        vector_handler = VectorIndexHandler(chunk_cache=shared_cache)

        # ChunkBuildHandler가 캐시에 저장
        shared_cache["chunks:test:main"] = {
            "chunks": [MagicMock()],
            "repo_id": "test",
        }

        # VectorIndexHandler가 캐시에서 읽기
        assert "chunks:test:main" in vector_handler.chunk_cache
