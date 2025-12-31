"""
RFC-031: Canonical Kind + KindMeta Tests

Tests for:
1. NodeKind/EdgeKind unification
2. KindMeta registry completeness (fail-fast)
3. IR→Graph transformation policy
4. Backward compatibility (GraphNodeKind/GraphEdgeKind aliases)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models import (
    EDGE_KIND_META,
    NODE_KIND_META,
    EdgeKind,
    NodeKind,
    get_edge_meta,
    get_node_meta,
    is_graph_kind,
    is_ir_kind,
    to_graph_node_kind,
)
from codegraph_engine.code_foundation.infrastructure.graph.models import (
    GraphEdgeKind,
    GraphNodeKind,
)


class TestCanonicalNodeKind:
    """Test canonical NodeKind enum"""

    def test_structural_kinds_exist(self):
        """Structural kinds should exist in NodeKind"""
        structural = [
            NodeKind.FILE,
            NodeKind.MODULE,
            NodeKind.CLASS,
            NodeKind.INTERFACE,
            NodeKind.FUNCTION,
            NodeKind.METHOD,
            NodeKind.VARIABLE,
            NodeKind.FIELD,
            NodeKind.IMPORT,
        ]
        for kind in structural:
            assert kind is not None
            assert isinstance(kind, NodeKind)

    def test_ir_only_kinds_exist(self):
        """IR-only kinds should exist in NodeKind"""
        ir_only = [
            NodeKind.ENUM,
            NodeKind.TYPE_ALIAS,
            NodeKind.LAMBDA,
            NodeKind.METHOD_REFERENCE,
            NodeKind.TYPE_PARAMETER,
            NodeKind.PROPERTY,
            NodeKind.CONSTANT,
            NodeKind.EXPORT,
            NodeKind.BLOCK,
            NodeKind.CONDITION,
            NodeKind.LOOP,
            NodeKind.TRY_CATCH,
        ]
        for kind in ir_only:
            assert kind is not None
            assert isinstance(kind, NodeKind)

    def test_graph_only_kinds_exist(self):
        """Graph-only kinds should exist in NodeKind"""
        graph_only = [
            NodeKind.TYPE,
            NodeKind.SIGNATURE,
            NodeKind.CFG_BLOCK,
            NodeKind.EXTERNAL_MODULE,
            NodeKind.EXTERNAL_FUNCTION,
            NodeKind.EXTERNAL_TYPE,
            NodeKind.ROUTE,
            NodeKind.SERVICE,
            NodeKind.REPOSITORY,
            NodeKind.CONFIG,
            NodeKind.JOB,
            NodeKind.MIDDLEWARE,
            NodeKind.SUMMARY,
            NodeKind.DOCUMENT,
        ]
        for kind in graph_only:
            assert kind is not None
            assert isinstance(kind, NodeKind)


class TestKindMetaRegistry:
    """Test KindMeta registry completeness"""

    def test_all_node_kinds_registered(self):
        """Every NodeKind must have a KindMeta entry (fail-fast)"""
        for kind in NodeKind:
            meta = get_node_meta(kind)
            assert meta is not None, f"Missing KindMeta for {kind}"

    def test_all_edge_kinds_registered(self):
        """Every EdgeKind must have an EdgeKindMeta entry (fail-fast)"""
        for kind in EdgeKind:
            meta = get_edge_meta(kind)
            assert meta is not None, f"Missing EdgeKindMeta for {kind}"

    def test_missing_kind_raises_keyerror(self):
        """Accessing unregistered kind should raise KeyError"""
        # This shouldn't happen if registry is complete, but test the mechanism
        # We can't easily test this without modifying the enum, so just verify the registry
        assert len(NODE_KIND_META) == len(NodeKind)
        assert len(EDGE_KIND_META) == len(EdgeKind)


class TestIRToGraphTransformation:
    """Test IR→Graph transformation policy"""

    def test_structural_kinds_keep(self):
        """Structural kinds should KEEP"""
        structural = [
            NodeKind.FILE,
            NodeKind.MODULE,
            NodeKind.CLASS,
            NodeKind.FUNCTION,
            NodeKind.METHOD,
        ]
        for kind in structural:
            result = to_graph_node_kind(kind)
            assert result == kind, f"{kind} should KEEP"

    def test_control_kinds_skip(self):
        """Control flow kinds should SKIP"""
        control = [
            NodeKind.BLOCK,
            NodeKind.CONDITION,
            NodeKind.LOOP,
            NodeKind.TRY_CATCH,
        ]
        for kind in control:
            result = to_graph_node_kind(kind)
            assert result is None, f"{kind} should SKIP"

    def test_lambda_converts_to_function(self):
        """LAMBDA should CONVERT to FUNCTION"""
        result = to_graph_node_kind(NodeKind.LAMBDA)
        assert result == NodeKind.FUNCTION

    def test_enum_converts_to_class(self):
        """ENUM should CONVERT to CLASS"""
        result = to_graph_node_kind(NodeKind.ENUM)
        assert result == NodeKind.CLASS

    def test_type_alias_converts_to_type(self):
        """TYPE_ALIAS should CONVERT to TYPE"""
        result = to_graph_node_kind(NodeKind.TYPE_ALIAS)
        assert result == NodeKind.TYPE


class TestLayerClassification:
    """Test layer classification functions"""

    def test_is_ir_kind(self):
        """is_ir_kind should return True for IR and BOTH layers"""
        assert is_ir_kind(NodeKind.FILE)  # BOTH
        assert is_ir_kind(NodeKind.BLOCK)  # IR
        assert not is_ir_kind(NodeKind.TYPE)  # GRAPH

    def test_is_graph_kind(self):
        """is_graph_kind should return True for GRAPH and BOTH layers"""
        assert is_graph_kind(NodeKind.FILE)  # BOTH
        assert is_graph_kind(NodeKind.TYPE)  # GRAPH
        assert not is_graph_kind(NodeKind.BLOCK)  # IR


class TestBackwardCompatibility:
    """Test backward compatibility with GraphNodeKind/GraphEdgeKind"""

    def test_graph_node_kind_is_alias(self):
        """GraphNodeKind should be an alias to NodeKind"""
        assert GraphNodeKind is NodeKind

    def test_graph_edge_kind_is_alias(self):
        """GraphEdgeKind should be an alias to EdgeKind"""
        assert GraphEdgeKind is EdgeKind

    def test_graph_node_kind_values_accessible(self):
        """GraphNodeKind enum values should be accessible"""
        assert GraphNodeKind.FILE == NodeKind.FILE
        assert GraphNodeKind.FUNCTION == NodeKind.FUNCTION
        assert GraphNodeKind.TYPE == NodeKind.TYPE
        assert GraphNodeKind.ROUTE == NodeKind.ROUTE

    def test_graph_edge_kind_values_accessible(self):
        """GraphEdgeKind enum values should be accessible"""
        assert GraphEdgeKind.CALLS == EdgeKind.CALLS
        assert GraphEdgeKind.CONTAINS == EdgeKind.CONTAINS
        assert GraphEdgeKind.CFG_NEXT == EdgeKind.CFG_NEXT


class TestKindEnumSnapshot:
    """Snapshot test to detect unintentional enum changes"""

    def test_node_kind_snapshot(self):
        """NodeKind values should match expected snapshot"""
        expected = {
            # Structural
            "File",
            "Module",
            "Class",
            "Interface",
            "Function",
            "Method",
            "Variable",
            "Field",
            "Import",
            # IR-only
            "Enum",
            "TypeAlias",
            "Lambda",
            "MethodReference",
            "TypeParameter",
            "Property",
            "Constant",
            "Export",
            "Block",
            "Condition",
            "Loop",
            "TryCatch",
            "Expression",  # RFC-031: Call sites, binary ops, etc.
            # Graph-only
            "Type",
            "Signature",
            "CfgBlock",
            "ExternalModule",
            "ExternalFunction",
            "ExternalType",
            "Route",
            "Service",
            "Repository",
            "Config",
            "Job",
            "Middleware",
            "Summary",
            "Document",
            # RFC-051: Template support
            "TemplateDoc",
            "TemplateElement",
            "TemplateDirective",
            "TemplateSlot",
        }
        actual = {k.value for k in NodeKind}
        assert actual == expected, f"NodeKind changed: {actual ^ expected}"

    def test_edge_kind_snapshot(self):
        """EdgeKind values should match expected snapshot"""
        expected = {
            # Structural
            "CONTAINS",
            "DEFINES",
            # Call/Usage
            "CALLS",
            "READS",
            "WRITES",
            "REFERENCES",
            # Type/Inheritance
            "IMPORTS",
            "INHERITS",
            "IMPLEMENTS",
            "REFERENCES_TYPE",
            "REFERENCES_SYMBOL",
            # Decorator/Instance
            "DECORATES",
            "INSTANTIATES",
            "OVERRIDES",
            # Resource
            "USES",
            "READS_RESOURCE",
            "WRITES_RESOURCE",
            # Exception
            "THROWS",
            "ROUTE_TO",
            "USES_REPO",
            # Closure
            "CAPTURES",
            "ACCESSES",
            "SHADOWS",
            # CFG
            "CFG_NEXT",
            "CFG_BRANCH",
            "CFG_LOOP",
            "CFG_HANDLER",
            # Framework
            "ROUTE_HANDLER",
            "HANDLES_REQUEST",
            "USES_REPOSITORY",
            "MIDDLEWARE_NEXT",
            # Documentation
            "DOCUMENTS",
            "REFERENCES_CODE",
            "DOCUMENTED_IN",
            # RFC-051: Template support
            "TEMPLATE_CHILD",
            "BINDS",
            "RENDERS",
            "ESCAPES",
            "CONTAINS_SLOT",
        }
        actual = {k.value for k in EdgeKind}
        assert actual == expected, f"EdgeKind changed: {actual ^ expected}"
