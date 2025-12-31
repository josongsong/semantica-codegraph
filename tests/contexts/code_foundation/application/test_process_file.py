"""
Test Process File UseCase

Unit tests for ProcessFileUseCase.

Note:
    Uses Infrastructure IRDocument (nodes) instead of deprecated Domain IRDocument (symbols).
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from codegraph_engine.code_foundation.application.process_file import ProcessFileUseCase
from codegraph_engine.code_foundation.domain.models import (
    ASTDocument,
    Chunk,
    GraphDocument,
    GraphEdge,
    GraphNode,
    Language,
    Reference,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import (
    IRDocument,
    Node,
    NodeKind,
    Span,
)


def create_ir_document(
    file_path: str = "/test/file.py",
    nodes: list[Node] | None = None,
) -> IRDocument:
    """Create an Infrastructure IRDocument for testing"""
    return IRDocument(
        repo_id="test-repo",
        snapshot_id="test-snapshot",
        schema_version="4.1.0",
        nodes=nodes or [],
        edges=[],
        types=[],
        signatures=[],
        meta={"file_path": file_path, "language": "python"},
    )


def create_function_node(
    name: str,
    file_path: str = "/test/file.py",
    start_line: int = 1,
    end_line: int = 2,
) -> Node:
    """Create a function node for testing"""
    return Node(
        id=f"function:{file_path}:{name}",
        kind=NodeKind.FUNCTION,
        fqn=f"{file_path}::{name}",
        name=name,
        file_path=file_path,
        span=Span(start_line=start_line, end_line=end_line, start_col=0, end_col=8),
        language="python",
    )


class TestProcessFileUseCase:
    """Tests for ProcessFileUseCase"""

    @pytest.fixture
    def mock_parser(self):
        """Create mock parser"""
        parser = Mock()
        parser.parse_file = Mock(
            return_value=ASTDocument(
                file_path="/test/file.py",
                language=Language.PYTHON,
                source_code="def foo():\n    pass",
                tree=MagicMock(),
                metadata={"parser": "mock"},
            )
        )
        return parser

    @pytest.fixture
    def mock_ir_generator(self):
        """Create mock IR generator"""
        generator = Mock()
        node = create_function_node("foo")
        generator.generate = Mock(return_value=create_ir_document(nodes=[node]))
        return generator

    @pytest.fixture
    def mock_graph_builder(self):
        """Create mock graph builder"""
        builder = Mock()
        builder.build = Mock(
            return_value=GraphDocument(
                file_path="/test/file.py",
                nodes=[
                    GraphNode(
                        id="node:foo",
                        type="function",
                        name="foo",
                        file_path="/test/file.py",
                        start_line=1,
                        end_line=2,
                    )
                ],
                edges=[],
            )
        )
        return builder

    @pytest.fixture
    def mock_chunker(self):
        """Create mock chunker"""
        chunker = Mock()
        chunker.chunk = Mock(
            return_value=[
                Chunk(
                    id="chunk:1",
                    content="def foo():\n    pass",
                    file_path="/test/file.py",
                    start_line=1,
                    end_line=2,
                    chunk_type="function",
                    language=Language.PYTHON,
                    metadata={},
                )
            ]
        )
        return chunker

    def test_execute_full_pipeline(
        self,
        mock_parser,
        mock_ir_generator,
        mock_graph_builder,
        mock_chunker,
        tmp_path,
    ):
        """Test full processing pipeline"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass")

        use_case = ProcessFileUseCase(
            parser=mock_parser,
            ir_generator=mock_ir_generator,
            graph_builder=mock_graph_builder,
            chunker=mock_chunker,
        )

        ir_doc, graph_doc, chunks = use_case.execute(test_file, Language.PYTHON)

        assert ir_doc is not None
        assert graph_doc is not None
        assert len(chunks) == 1

        mock_parser.parse_file.assert_called_once()
        mock_ir_generator.generate.assert_called_once()
        mock_graph_builder.build.assert_called_once()
        mock_chunker.chunk.assert_called_once()

    def test_execute_with_auto_language_detection(
        self,
        mock_parser,
        mock_ir_generator,
        mock_graph_builder,
        mock_chunker,
        tmp_path,
    ):
        """Test execution with auto language detection"""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")

        use_case = ProcessFileUseCase(
            parser=mock_parser,
            ir_generator=mock_ir_generator,
            graph_builder=mock_graph_builder,
            chunker=mock_chunker,
        )

        ir_doc, graph_doc, chunks = use_case.execute(test_file)

        mock_parser.parse_file.assert_called_once_with(test_file, Language.PYTHON)

    @pytest.mark.parametrize(
        "extension,expected_language",
        [
            (".py", Language.PYTHON),
            (".js", Language.JAVASCRIPT),
            (".ts", Language.TYPESCRIPT),
            (".go", Language.GO),
            (".java", Language.JAVA),
        ],
    )
    def test_detect_language(
        self,
        extension,
        expected_language,
        mock_parser,
        mock_ir_generator,
        mock_graph_builder,
        mock_chunker,
    ):
        """Test language detection"""
        use_case = ProcessFileUseCase(
            parser=mock_parser,
            ir_generator=mock_ir_generator,
            graph_builder=mock_graph_builder,
            chunker=mock_chunker,
        )

        result = use_case._detect_language(Path(f"test{extension}"))

        assert result == expected_language


class TestProcessFileUseCaseEdgeCases:
    """Edge case tests"""

    @pytest.fixture
    def mock_deps(self):
        """Create all mock dependencies"""
        parser = Mock()
        parser.parse_file = Mock(
            return_value=ASTDocument(
                file_path="",
                language=Language.PYTHON,
                source_code="",
                tree=MagicMock(),
                metadata={},
            )
        )

        ir_generator = Mock()
        ir_generator.generate = Mock(return_value=create_ir_document(file_path=""))

        graph_builder = Mock()
        graph_builder.build = Mock(
            return_value=GraphDocument(
                file_path="",
                nodes=[],
                edges=[],
            )
        )

        chunker = Mock()
        chunker.chunk = Mock(return_value=[])

        return parser, ir_generator, graph_builder, chunker

    def test_empty_file(self, mock_deps, tmp_path):
        """Test processing empty file"""
        parser, ir_generator, graph_builder, chunker = mock_deps

        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        use_case = ProcessFileUseCase(
            parser=parser,
            ir_generator=ir_generator,
            graph_builder=graph_builder,
            chunker=chunker,
        )

        ir_doc, graph_doc, chunks = use_case.execute(test_file, Language.PYTHON)

        assert ir_doc is not None
        assert graph_doc is not None
        assert isinstance(chunks, list)

    def test_unknown_extension(self, mock_deps, tmp_path):
        """Test file with unknown extension"""
        parser, ir_generator, graph_builder, chunker = mock_deps

        test_file = tmp_path / "unknown.xyz"
        test_file.write_text("content")

        use_case = ProcessFileUseCase(
            parser=parser,
            ir_generator=ir_generator,
            graph_builder=graph_builder,
            chunker=chunker,
        )

        ir_doc, graph_doc, chunks = use_case.execute(test_file)

        parser.parse_file.assert_called_once_with(test_file, Language.UNKNOWN)


class TestProcessFileUseCaseIntegration:
    """Integration-style tests with more realistic scenarios"""

    @pytest.fixture
    def mock_deps_with_references(self):
        """Create mocks that return related data"""
        ast_doc = ASTDocument(
            file_path="/test/main.py",
            language=Language.PYTHON,
            source_code="def caller():\n    callee()\n\ndef callee():\n    pass",
            tree=MagicMock(),
            metadata={},
        )

        # Use Infrastructure IRDocument
        caller_node = create_function_node("caller", "/test/main.py", 1, 2)
        callee_node = create_function_node("callee", "/test/main.py", 4, 5)
        ir_doc = create_ir_document(
            file_path="/test/main.py",
            nodes=[caller_node, callee_node],
        )

        graph_doc = GraphDocument(
            file_path="/test/main.py",
            nodes=[
                GraphNode(
                    id="node:caller",
                    type="function",
                    name="caller",
                    file_path="/test/main.py",
                    start_line=1,
                    end_line=2,
                ),
                GraphNode(
                    id="node:callee",
                    type="function",
                    name="callee",
                    file_path="/test/main.py",
                    start_line=4,
                    end_line=5,
                ),
            ],
            edges=[
                GraphEdge(source="node:caller", target="node:callee", type="CALLS"),
            ],
        )

        parser = Mock()
        parser.parse_file = Mock(return_value=ast_doc)

        ir_generator = Mock()
        ir_generator.generate = Mock(return_value=ir_doc)

        graph_builder = Mock()
        graph_builder.build = Mock(return_value=graph_doc)

        chunker = Mock()
        chunker.chunk = Mock(
            return_value=[
                Chunk(
                    id="chunk:1",
                    content="def caller():\n    callee()",
                    file_path="/test/main.py",
                    start_line=1,
                    end_line=2,
                    chunk_type="function",
                    language=Language.PYTHON,
                    metadata={},
                ),
                Chunk(
                    id="chunk:2",
                    content="def callee():\n    pass",
                    file_path="/test/main.py",
                    start_line=4,
                    end_line=5,
                    chunk_type="function",
                    language=Language.PYTHON,
                    metadata={},
                ),
            ]
        )

        return parser, ir_generator, graph_builder, chunker

    def test_process_file_with_call_graph(self, mock_deps_with_references, tmp_path):
        """Test processing file that has function calls"""
        parser, ir_generator, graph_builder, chunker = mock_deps_with_references

        test_file = tmp_path / "main.py"
        test_file.write_text("def caller():\n    callee()\n\ndef callee():\n    pass")

        use_case = ProcessFileUseCase(
            parser=parser,
            ir_generator=ir_generator,
            graph_builder=graph_builder,
            chunker=chunker,
        )

        ir_doc, graph_doc, chunks = use_case.execute(test_file, Language.PYTHON)

        # Verify nodes (Infrastructure IRDocument uses 'nodes' not 'symbols')
        assert len(ir_doc.nodes) == 2
        assert ir_doc.nodes[0].name == "caller"
        assert ir_doc.nodes[1].name == "callee"

        # Verify graph
        assert len(graph_doc.nodes) == 2
        assert len(graph_doc.edges) == 1
        assert graph_doc.edges[0].type == "CALLS"

        # Verify chunks
        assert len(chunks) == 2
