"""
Job Handlers 단위 테스트.

각 Handler의 개별 동작 및 에러 분류 검증.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from codegraph_shared.infra.jobs.handler import JobResult
from codegraph_shared.infra.jobs.handlers.config import ErrorCategory, ErrorCode
from codegraph_shared.infra.jobs.handlers.ir_handler import IRBuildHandler
from codegraph_shared.infra.jobs.handlers.lexical_handler import LexicalIndexHandler
from codegraph_shared.infra.jobs.handlers.chunk_handler import ChunkBuildHandler
from codegraph_shared.infra.jobs.handlers.vector_handler import VectorIndexHandler


class TestIRBuildHandler:
    """IR Build Handler 테스트."""

    @pytest.fixture
    def handler(self):
        return IRBuildHandler(ir_cache={})

    @pytest.mark.asyncio
    async def test_missing_repo_path_returns_permanent_error(self, handler):
        """repo_path 누락 시 PERMANENT 에러."""
        result = await handler.execute({"repo_id": "test"})

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.INVALID_PAYLOAD

    @pytest.mark.asyncio
    async def test_missing_repo_id_returns_permanent_error(self, handler):
        """repo_id 누락 시 PERMANENT 에러."""
        result = await handler.execute({"repo_path": "/tmp/test"})

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.INVALID_PAYLOAD

    @pytest.mark.asyncio
    async def test_nonexistent_path_returns_permanent_error(self, handler):
        """존재하지 않는 경로 시 PERMANENT 에러."""
        result = await handler.execute(
            {
                "repo_path": "/nonexistent/path/12345",
                "repo_id": "test",
            }
        )

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.PATH_NOT_FOUND

    @pytest.mark.asyncio
    async def test_empty_repo_returns_success_with_warning(self, handler, tmp_path):
        """빈 레포지토리는 성공 + 경고."""
        result = await handler.execute(
            {
                "repo_path": str(tmp_path),
                "repo_id": "test",
            }
        )

        assert result.success
        assert result.data["files_processed"] == 0
        assert "warning" in result.data

    @pytest.mark.asyncio
    async def test_ir_cache_populated_on_success(self, handler, tmp_path):
        """성공 시 IR 캐시에 결과 저장 (Rust engine)."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        # Mock Rust engine (codegraph_ir)
        with patch("codegraph_shared.infra.jobs.handlers.ir_handler.codegraph_ir") as mock_ir:
            # Mock Rust result format
            mock_ir.process_python_files.return_value = [
                {
                    "success": True,
                    "file_index": 0,
                    "nodes": [
                        {"id": "node_1", "kind": "Function", "name": "foo"},
                    ],
                    "edges": [],
                    "occurrences": [],
                }
            ]

            result = await handler.execute(
                {
                    "repo_path": str(tmp_path),
                    "repo_id": "test-repo",
                    "snapshot_id": "main",
                }
            )

            assert result.success
            assert "ir:test-repo:main" in handler.ir_cache
            assert result.data["ir_cache_key"] == "ir:test-repo:main"


class TestLexicalIndexHandler:
    """Lexical Index Handler 테스트."""

    @pytest.fixture
    def handler(self):
        return LexicalIndexHandler()

    @pytest.mark.asyncio
    async def test_missing_repo_path_returns_permanent_error(self, handler):
        """repo_path 누락 시 PERMANENT 에러."""
        result = await handler.execute({"repo_id": "test"})

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT

    @pytest.mark.asyncio
    async def test_nonexistent_path_returns_permanent_error(self, handler):
        """존재하지 않는 경로 시 PERMANENT 에러."""
        result = await handler.execute(
            {
                "repo_path": "/nonexistent/path/12345",
                "repo_id": "test",
            }
        )

        assert not result.success
        assert result.data["error_code"] == ErrorCode.PATH_NOT_FOUND


class TestChunkBuildHandler:
    """Chunk Build Handler 테스트."""

    @pytest.fixture
    def handler(self):
        ir_cache = {}
        chunk_cache = {}
        return ChunkBuildHandler(ir_cache=ir_cache, chunk_cache=chunk_cache)

    @pytest.mark.asyncio
    async def test_missing_ir_cache_key_returns_permanent_error(self, handler):
        """ir_cache_key 누락 시 PERMANENT 에러."""
        result = await handler.execute({"repo_id": "test"})

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.INVALID_PAYLOAD

    @pytest.mark.asyncio
    async def test_ir_cache_miss_returns_permanent_error(self, handler):
        """IR 캐시 미스 시 PERMANENT 에러."""
        result = await handler.execute(
            {
                "repo_id": "test",
                "ir_cache_key": "ir:nonexistent:main",
            }
        )

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.IR_CACHE_MISS

    @pytest.mark.asyncio
    async def test_empty_ir_documents_returns_success_with_warning(self, handler):
        """빈 IR documents는 성공 + 경고."""
        handler.ir_cache["ir:test:main"] = {
            "ir_documents": {},
            "repo_path": "/tmp",
            "repo_id": "test",
            "snapshot_id": "main",
        }

        result = await handler.execute(
            {
                "repo_id": "test",
                "ir_cache_key": "ir:test:main",
            }
        )

        assert result.success
        assert result.data["chunks_created"] == 0
        assert "warning" in result.data


class TestVectorIndexHandler:
    """Vector Index Handler 테스트."""

    @pytest.fixture
    def handler(self):
        return VectorIndexHandler(chunk_cache={})

    @pytest.mark.asyncio
    async def test_missing_chunk_cache_key_returns_permanent_error(self, handler):
        """chunk_cache_key 누락 시 PERMANENT 에러."""
        result = await handler.execute({"repo_id": "test"})

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.INVALID_PAYLOAD

    @pytest.mark.asyncio
    async def test_chunk_cache_miss_returns_permanent_error(self, handler):
        """Chunk 캐시 미스 시 PERMANENT 에러."""
        result = await handler.execute(
            {
                "repo_id": "test",
                "chunk_cache_key": "chunks:nonexistent:main",
            }
        )

        assert not result.success
        assert result.data["error_category"] == ErrorCategory.PERMANENT
        assert result.data["error_code"] == ErrorCode.CHUNK_CACHE_MISS

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_success_with_warning(self, handler):
        """빈 chunks는 성공 + 경고."""
        handler.chunk_cache["chunks:test:main"] = {
            "chunks": [],
            "repo_id": "test",
            "snapshot_id": "main",
        }

        result = await handler.execute(
            {
                "repo_id": "test",
                "chunk_cache_key": "chunks:test:main",
            }
        )

        assert result.success
        assert result.data["vectors_indexed"] == 0
        assert "warning" in result.data

    @pytest.mark.asyncio
    async def test_successful_indexing_returns_metrics(self, handler):
        """성공 시 메트릭 반환."""
        # Mock chunks
        mock_chunks = [MagicMock() for _ in range(10)]
        handler.chunk_cache["chunks:test:main"] = {
            "chunks": mock_chunks,
            "repo_id": "test",
            "snapshot_id": "main",
        }

        result = await handler.execute(
            {
                "repo_id": "test",
                "chunk_cache_key": "chunks:test:main",
            }
        )

        assert result.success
        assert result.data["vectors_indexed"] == 10
        assert "duration_seconds" in result.data
        assert "throughput_vectors_per_sec" in result.data


class TestErrorClassification:
    """에러 분류 테스트."""

    def test_job_result_ok_factory(self):
        """JobResult.ok() 팩토리 메서드."""
        result = JobResult.ok({"key": "value"})
        assert result.success
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_job_result_fail_factory(self):
        """JobResult.fail() 팩토리 메서드."""
        result = JobResult.fail("Something went wrong", {"error_code": "TEST"})
        assert not result.success
        assert result.error == "Something went wrong"
        assert result.data["error_code"] == "TEST"

    @pytest.mark.asyncio
    async def test_error_categories_are_consistent(self):
        """에러 카테고리 일관성 검증."""
        valid_categories = {ErrorCategory.TRANSIENT, ErrorCategory.PERMANENT, ErrorCategory.INFRASTRUCTURE}

        # IRBuildHandler 에러 카테고리
        handler = IRBuildHandler()
        result = await handler.execute({})
        assert result.data.get("error_category") in valid_categories

        # LexicalIndexHandler 에러 카테고리
        handler = LexicalIndexHandler()
        result = await handler.execute({})
        assert result.data.get("error_category") in valid_categories

        # ChunkBuildHandler 에러 카테고리
        handler = ChunkBuildHandler()
        result = await handler.execute({})
        assert result.data.get("error_category") in valid_categories

        # VectorIndexHandler 에러 카테고리
        handler = VectorIndexHandler()
        result = await handler.execute({})
        assert result.data.get("error_category") in valid_categories
