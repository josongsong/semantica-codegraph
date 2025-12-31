"""
IRDocument Resolver Tests

RFC-052: MCP Service Layer Architecture
Tests for IRDocument resolution (no mocks).

Test Coverage:
- NotImplementedError when no source configured
- Cache hit/miss
- Fallback behavior
"""

import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir_document_resolver import (
    IRDocumentResolver,
)


class TestIRDocumentResolverNoMock:
    """IRDocument resolver with no mock - real behavior"""

    @pytest.mark.asyncio
    async def test_resolve_without_sources_raises(self):
        """Resolver raises NotImplementedError when no sources configured"""
        resolver = IRDocumentResolver()

        with pytest.raises(NotImplementedError, match="Cannot resolve IRDocument"):
            await resolver.resolve("test_repo", "snap_001")

    @pytest.mark.asyncio
    async def test_cache_works(self):
        """Cache prevents duplicate resolution"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        # Mock store that tracks calls
        call_count = 0

        class MockStore:
            async def load_latest(self, repo_id):
                nonlocal call_count
                call_count += 1
                return IRDocument(repo_id=repo_id, snapshot_id="snap_latest")

        resolver = IRDocumentResolver(ir_store=MockStore())

        # First call
        doc1 = await resolver.resolve("test_repo")
        assert call_count == 1

        # Second call (cache hit)
        doc2 = await resolver.resolve("test_repo")
        assert call_count == 1  # No additional call

        # Same object
        assert doc1 is doc2

    def test_clear_cache(self):
        """Cache can be cleared"""
        resolver = IRDocumentResolver()

        # Manually populate cache
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        doc = IRDocument(repo_id="test", snapshot_id="snap_001")
        resolver._cache[("test", "snap_001")] = doc

        assert len(resolver._cache) == 1

        # Clear
        resolver.clear_cache()

        assert len(resolver._cache) == 0


class TestIRDocumentResolverFileSystem:
    """File system fallback tests"""

    @pytest.mark.asyncio
    async def test_file_system_fallback(self):
        """Can load from file system if configured"""
        import json

        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        # Create temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "test_repo"
            repo_dir.mkdir()

            ir_file = repo_dir / "snap_001.json"

            # Write IRDocument
            ir_data = {
                "repo_id": "test_repo",
                "snapshot_id": "snap_001",
                "schema_version": "2.3",
                "nodes": [],
                "edges": [],
            }

            with open(ir_file, "w") as f:
                json.dump(ir_data, f)

            # Resolve
            resolver = IRDocumentResolver(file_system_path=Path(tmpdir))
            doc = await resolver.resolve("test_repo", "snap_001")

            assert doc.repo_id == "test_repo"
            assert doc.snapshot_id == "snap_001"

    @pytest.mark.asyncio
    async def test_file_not_found_raises(self):
        """File system fallback raises if file not found"""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = IRDocumentResolver(file_system_path=Path(tmpdir))

            # Raises NotImplementedError because filesystem load fails too
            with pytest.raises(NotImplementedError, match="Cannot resolve IRDocument"):
                await resolver.resolve("nonexistent_repo", "snap_001")
