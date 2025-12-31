"""
Tests for SOTA Chunk Types

Tests new chunk types:
- async_function
- property
- fixture
- enum
- model
- protocol
- dataclass
"""

import pytest


class TestSOTAChunkTypes:
    """Test SOTA chunk types detection"""

    def test_async_function_detection(self):
        """Test async function is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        # Mock async function node
        node = Node(
            id="func_async",
            kind=NodeKind.FUNCTION,
            fqn="test.async_func",
            file_path="test.py",
            span=Span(1, 1, 5, 1),
            language="python",
            name="async_func",
            attrs={"is_async": True, "decorators": []},
        )

        kind = builder._determine_function_kind(node, [])

        assert kind == "async_function"

    def test_property_detection(self):
        """Test @property is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="func_prop",
            kind=NodeKind.METHOD,
            fqn="test.MyClass.name",
            file_path="test.py",
            span=Span(1, 1, 3, 1),
            language="python",
            name="name",
            attrs={},
        )

        decorators = ["property"]
        kind = builder._determine_function_kind(node, decorators)

        assert kind == "property"

    def test_fixture_detection(self):
        """Test pytest fixture is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="func_fixture",
            kind=NodeKind.FUNCTION,
            fqn="test.db_fixture",
            file_path="test.py",
            span=Span(1, 1, 5, 1),
            language="python",
            name="db_fixture",
            attrs={},
        )

        decorators = ["pytest.fixture"]
        kind = builder._determine_function_kind(node, decorators)

        assert kind == "fixture"

    def test_enum_detection(self):
        """Test Enum class is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="class_enum",
            kind=NodeKind.CLASS,
            fqn="test.Status",
            file_path="test.py",
            span=Span(1, 1, 5, 1),
            language="python",
            name="Status",
            attrs={"base_classes": ["Enum"]},
        )

        kind = builder._determine_class_kind(node, "class")

        assert kind == "enum"

    def test_model_detection(self):
        """Test ORM Model is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="class_model",
            kind=NodeKind.CLASS,
            fqn="test.User",
            file_path="test.py",
            span=Span(1, 1, 10, 1),
            language="python",
            name="User",
            attrs={"base_classes": ["Model"]},
        )

        kind = builder._determine_class_kind(node, "class")

        assert kind == "model"

    def test_protocol_detection(self):
        """Test Protocol is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="class_protocol",
            kind=NodeKind.CLASS,
            fqn="test.Drawable",
            file_path="test.py",
            span=Span(1, 1, 5, 1),
            language="python",
            name="Drawable",
            attrs={"base_classes": ["Protocol"]},
        )

        kind = builder._determine_class_kind(node, "class")

        assert kind == "protocol"

    def test_dataclass_detection(self):
        """Test @dataclass is detected"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="class_dc",
            kind=NodeKind.CLASS,
            fqn="test.User",
            file_path="test.py",
            span=Span(1, 1, 5, 1),
            language="python",
            name="User",
            attrs={"decorators": ["dataclass"]},
        )

        kind = builder._determine_class_kind(node, "class")

        assert kind == "dataclass"

    def test_regular_function_unchanged(self):
        """Test regular function stays as 'function'"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="func_normal",
            kind=NodeKind.FUNCTION,
            fqn="test.normal_func",
            file_path="test.py",
            span=Span(1, 1, 5, 1),
            language="python",
            name="normal_func",
            attrs={},
        )

        kind = builder._determine_function_kind(node, [])

        assert kind == "function"

    def test_semantic_class_preserved(self):
        """Test graph semantic kind is preserved for non-special classes"""
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span

        builder = ChunkBuilder(id_generator=None)

        node = Node(
            id="class_service",
            kind=NodeKind.CLASS,
            fqn="test.UserService",
            file_path="test.py",
            span=Span(1, 1, 10, 1),
            language="python",
            name="UserService",
            attrs={},
        )

        # Graph detected it as "service"
        kind = builder._determine_class_kind(node, "service")

        # Should preserve graph's semantic kind
        assert kind == "service"

    def test_chunk_attrs_preserved(self):
        """Test chunk attrs contain decorators and other info"""
        from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk

        chunk = Chunk(
            chunk_id="test",
            repo_id="test",
            snapshot_id="main",
            project_id=None,
            module_path=None,
            file_path="test.py",
            kind="async_function",
            fqn="test.fetch",
            start_line=1,
            end_line=10,
            original_start_line=1,
            original_end_line=10,
            content_hash="abc",
            parent_id=None,
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="test",
            symbol_owner_id="test",
            summary=None,
            importance=None,
            attrs={
                "decorators": ["app.route", "auth_required"],
                "is_async": True,
                "parameters": [{"name": "request", "type": "Request"}],
            },
        )

        # Verify attrs are preserved
        assert chunk.attrs["decorators"] == ["app.route", "auth_required"]
        assert chunk.attrs["is_async"] is True
        assert "parameters" in chunk.attrs
