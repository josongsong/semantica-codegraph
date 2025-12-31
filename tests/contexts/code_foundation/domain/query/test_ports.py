"""
Query Ports Unit Tests

SOTA L11급:
- Port Protocol 정의 확인
- Hexagonal Architecture 준수
"""

from typing import Protocol

import pytest


class TestPortsAreProtocols:
    """모든 Port가 Protocol인지 확인"""

    def test_graph_index_port(self):
        """GraphIndexPort is Protocol"""
        from codegraph_engine.code_foundation.domain.query.ports import GraphIndexPort

        assert issubclass(GraphIndexPort.__class__, type(Protocol))

    def test_node_matcher_port(self):
        """NodeMatcherPort is Protocol"""
        from codegraph_engine.code_foundation.domain.query.ports import NodeMatcherPort

        assert issubclass(NodeMatcherPort.__class__, type(Protocol))

    def test_edge_resolver_port(self):
        """EdgeResolverPort is Protocol"""
        from codegraph_engine.code_foundation.domain.query.ports import EdgeResolverPort

        assert issubclass(EdgeResolverPort.__class__, type(Protocol))

    def test_traversal_port(self):
        """TraversalPort is Protocol"""
        from codegraph_engine.code_foundation.domain.query.ports import TraversalPort

        assert issubclass(TraversalPort.__class__, type(Protocol))

    def test_code_trace_provider(self):
        """CodeTraceProvider is Protocol"""
        from codegraph_engine.code_foundation.domain.query.ports import CodeTraceProvider

        assert issubclass(CodeTraceProvider.__class__, type(Protocol))


class TestPortsHexagonalCompliance:
    """Port가 Infrastructure import 없는지 확인"""

    def test_no_infrastructure_import(self):
        """ports.py에 infrastructure import 없음"""
        from pathlib import Path

        ports_file = Path("src/contexts/code_foundation/domain/query/ports.py")
        content = ports_file.read_text()

        assert "from codegraph_engine.code_foundation.infrastructure" not in content
        assert "import codegraph_engine.code_foundation.infrastructure" not in content


class TestPortMethodSignatures:
    """Port 메서드 시그니처 확인"""

    def test_graph_index_port_methods(self):
        """GraphIndexPort 메서드"""
        from codegraph_engine.code_foundation.domain.query.ports import GraphIndexPort

        # 필수 메서드 존재 확인
        assert hasattr(GraphIndexPort, "get_node")
        assert hasattr(GraphIndexPort, "get_edges_from")
        assert hasattr(GraphIndexPort, "get_edges_to")
        assert hasattr(GraphIndexPort, "find_vars_by_name")
        assert hasattr(GraphIndexPort, "find_funcs_by_name")
        assert hasattr(GraphIndexPort, "get_all_nodes")

    def test_traversal_port_methods(self):
        """TraversalPort 메서드"""
        from codegraph_engine.code_foundation.domain.query.ports import TraversalPort

        assert hasattr(TraversalPort, "find_paths")

    def test_code_trace_provider_methods(self):
        """CodeTraceProvider 메서드"""
        from codegraph_engine.code_foundation.domain.query.ports import CodeTraceProvider

        assert hasattr(CodeTraceProvider, "get_trace")
        assert hasattr(CodeTraceProvider, "get_node_source")
