"""
Integration Tests: Cross-Language Value Flow Graph

Test scenarios:
1. Frontend → Backend flow (TypeScript → Python)
2. Backend → Database flow (Python → SQL)
3. Taint analysis (PII tracking)
4. MSA debugging (service-to-service)
"""

import pytest

from src.contexts.reasoning_engine.infrastructure.cross_lang import (
    BoundaryAnalyzer,
    BoundarySpec,
    Confidence,
    FlowEdgeKind,
    ValueFlowEdge,
    ValueFlowGraph,
    ValueFlowNode,
)


class TestValueFlowBasics:
    """Basic value flow graph tests"""

    def test_create_graph(self):
        """Test graph creation"""
        vfg = ValueFlowGraph()

        assert vfg is not None
        assert len(vfg.nodes) == 0
        assert len(vfg.edges) == 0

    def test_add_node(self):
        """Test adding nodes"""
        vfg = ValueFlowGraph()

        node = ValueFlowNode(
            node_id="test_node_1",
            symbol_name="testVar",
            file_path="test.py",
            line=10,
            language="python",
        )

        vfg.add_node(node)

        assert len(vfg.nodes) == 1
        assert "test_node_1" in vfg.nodes

    def test_add_edge(self):
        """Test adding edges"""
        vfg = ValueFlowGraph()

        node1 = ValueFlowNode(
            node_id="node1",
            symbol_name="x",
            file_path="test.py",
            line=10,
            language="python",
        )

        node2 = ValueFlowNode(
            node_id="node2",
            symbol_name="y",
            file_path="test.py",
            line=20,
            language="python",
        )

        vfg.add_node(node1)
        vfg.add_node(node2)

        edge = ValueFlowEdge(
            source_id="node1",
            target_id="node2",
            kind=FlowEdgeKind.ASSIGN,
        )

        vfg.add_edge(edge)

        assert len(vfg.edges) == 1


class TestCrossServiceFlow:
    """Cross-service value flow tests"""

    def test_http_request_flow(self):
        """Test HTTP request flow (FE → BE)"""
        vfg = ValueFlowGraph()

        # Frontend (TypeScript)
        fe_node = ValueFlowNode(
            node_id="fe:login_data",
            symbol_name="loginData",
            file_path="src/Login.tsx",
            line=42,
            language="typescript",
            service_context="frontend",
        )

        # Backend (Python)
        be_node = ValueFlowNode(
            node_id="be:credentials",
            symbol_name="credentials",
            file_path="api/auth.py",
            line=15,
            language="python",
            service_context="backend",
        )

        vfg.add_node(fe_node)
        vfg.add_node(be_node)

        # HTTP boundary
        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="auth_service",
            endpoint="/api/login",
            request_schema={"username": "string", "password": "string"},
            response_schema={"token": "string"},
            http_method="POST",
        )

        edge = ValueFlowEdge(
            source_id=fe_node.node_id,
            target_id=be_node.node_id,
            kind=FlowEdgeKind.HTTP_REQUEST,
            boundary_spec=boundary,
        )

        vfg.add_edge(edge)

        # Verify
        assert len(vfg.edges) == 1
        assert len(vfg._boundaries) == 1

    def test_database_flow(self):
        """Test database write flow (BE → DB)"""
        vfg = ValueFlowGraph()

        # Backend
        be_node = ValueFlowNode(
            node_id="be:user_data",
            symbol_name="user_data",
            file_path="api/users.py",
            line=50,
            language="python",
        )

        # Database (sink)
        db_node = ValueFlowNode(
            node_id="db:users_table",
            symbol_name="users",
            file_path="schema.sql",
            line=1,
            language="sql",
            is_sink=True,
        )

        vfg.add_node(be_node)
        vfg.add_node(db_node)

        edge = ValueFlowEdge(
            source_id=be_node.node_id,
            target_id=db_node.node_id,
            kind=FlowEdgeKind.DB_WRITE,
        )

        vfg.add_edge(edge)

        # Verify sink
        assert db_node.node_id in vfg._sinks


class TestTracing:
    """Trace tests"""

    def test_forward_trace(self):
        """Test forward trace"""
        vfg = ValueFlowGraph()

        # Create chain: A → B → C
        nodes = []
        for i, name in enumerate(["A", "B", "C"]):
            node = ValueFlowNode(
                node_id=f"node_{name}",
                symbol_name=name,
                file_path="test.py",
                line=i * 10,
                language="python",
            )
            nodes.append(node)
            vfg.add_node(node)

        # Add edges
        for i in range(len(nodes) - 1):
            edge = ValueFlowEdge(
                source_id=nodes[i].node_id,
                target_id=nodes[i + 1].node_id,
                kind=FlowEdgeKind.ASSIGN,
            )
            vfg.add_edge(edge)

        # Trace forward from A
        paths = vfg.trace_forward("node_A")

        assert len(paths) > 0
        assert "node_A" in paths[0]
        assert "node_C" in paths[0]

    def test_backward_trace(self):
        """Test backward trace"""
        vfg = ValueFlowGraph()

        # Create chain: A → B → C
        nodes = []
        for i, name in enumerate(["A", "B", "C"]):
            node = ValueFlowNode(
                node_id=f"node_{name}",
                symbol_name=name,
                file_path="test.py",
                line=i * 10,
                language="python",
            )
            nodes.append(node)
            vfg.add_node(node)

        # Add edges
        for i in range(len(nodes) - 1):
            edge = ValueFlowEdge(
                source_id=nodes[i].node_id,
                target_id=nodes[i + 1].node_id,
                kind=FlowEdgeKind.ASSIGN,
            )
            vfg.add_edge(edge)

        # Trace backward from C
        paths = vfg.trace_backward("node_C")

        assert len(paths) > 0
        assert "node_A" in paths[0]
        assert "node_C" in paths[0]


class TestTaintAnalysis:
    """Taint analysis tests"""

    def test_pii_tracking(self):
        """Test PII taint tracking"""
        vfg = ValueFlowGraph()

        # Source: User input (PII)
        source = ValueFlowNode(
            node_id="source:user_input",
            symbol_name="user_input",
            file_path="input.py",
            line=10,
            language="python",
            is_source=True,
            taint_labels={"PII", "user_data"},
        )

        # Intermediate
        middle = ValueFlowNode(
            node_id="middle:processed",
            symbol_name="processed_data",
            file_path="process.py",
            line=20,
            language="python",
        )

        # Sink: Database
        sink = ValueFlowNode(
            node_id="sink:db",
            symbol_name="db_record",
            file_path="db.py",
            line=30,
            language="python",
            is_sink=True,
        )

        vfg.add_node(source)
        vfg.add_node(middle)
        vfg.add_node(sink)

        # Edges
        vfg.add_edge(
            ValueFlowEdge(
                source_id=source.node_id,
                target_id=middle.node_id,
                kind=FlowEdgeKind.ASSIGN,
            )
        )

        vfg.add_edge(
            ValueFlowEdge(
                source_id=middle.node_id,
                target_id=sink.node_id,
                kind=FlowEdgeKind.DB_WRITE,
            )
        )

        # Trace taint
        paths = vfg.trace_taint(taint_label="PII")

        assert len(paths) > 0
        assert source.node_id in paths[0]
        assert sink.node_id in paths[0]


class TestBoundaryAnalyzer:
    """Boundary analyzer tests"""

    def test_openapi_extraction(self):
        """Test OpenAPI boundary extraction"""
        from src.contexts.reasoning_engine.infrastructure.cross_lang.boundary_analyzer import (
            OpenAPIBoundaryExtractor,
        )

        spec = {
            "info": {"title": "TestAPI"},
            "paths": {
                "/users": {
                    "get": {
                        "parameters": [{"name": "id", "type": "integer"}],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "properties": {"name": {"type": "string"}, "email": {"type": "string"}}
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }

        extractor = OpenAPIBoundaryExtractor()
        boundaries = extractor.extract_from_spec(spec)

        assert len(boundaries) > 0
        assert boundaries[0].boundary_type == "rest_api"
        assert boundaries[0].http_method == "GET"


class TestVisualization:
    """Visualization tests"""

    def test_path_visualization(self):
        """Test path visualization"""
        vfg = ValueFlowGraph()

        # Create simple path
        node1 = ValueFlowNode(
            node_id="n1",
            symbol_name="input",
            file_path="input.py",
            line=10,
            language="python",
        )

        node2 = ValueFlowNode(
            node_id="n2",
            symbol_name="output",
            file_path="output.py",
            line=20,
            language="python",
        )

        vfg.add_node(node1)
        vfg.add_node(node2)

        vfg.add_edge(
            ValueFlowEdge(
                source_id="n1",
                target_id="n2",
                kind=FlowEdgeKind.ASSIGN,
            )
        )

        # Visualize
        path = ["n1", "n2"]
        viz = vfg.visualize_path(path)

        assert "input" in viz
        assert "output" in viz
        assert "input.py" in viz


class TestStatistics:
    """Statistics tests"""

    def test_graph_statistics(self):
        """Test graph statistics"""
        vfg = ValueFlowGraph()

        # Add some nodes
        for i in range(5):
            node = ValueFlowNode(
                node_id=f"node_{i}",
                symbol_name=f"var_{i}",
                file_path="test.py",
                line=i * 10,
                language="python",
            )
            vfg.add_node(node)

        stats = vfg.get_statistics()

        assert stats["total_nodes"] == 5
        assert stats["total_edges"] == 0
        assert "python" in stats["languages"]
