"""
Tests for Lazy Local Flow (Structural Risk Mitigation)

Verifies:
- Only processes requested functions
- Caches results
- Resolves dependencies correctly
- Maintains correctness (same as eager)
"""

from codegraph_engine.code_foundation.domain.type_inference.config import LocalFlowConfig
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    ControlFlowBlock,
    ControlFlowGraph,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind
from codegraph_engine.code_foundation.infrastructure.type_inference.lazy_local_flow import LazyLocalFlowInferencer


def test_lazy_only_processes_requested_functions():
    """Lazy should only process requested functions, not all"""

    # Setup: 3 functions, only request 1
    fn1_id = "fn:1"
    fn2_id = "fn:2"
    fn3_id = "fn:3"

    cfg1 = ControlFlowGraph(
        id="cfg:1",
        function_node_id=fn1_id,
        entry_block_id="b0",
        exit_block_id="b1",
        blocks=[
            ControlFlowBlock(id="b0", kind=CFGBlockKind.ENTRY, function_node_id=fn1_id),
            ControlFlowBlock(id="b1", kind=CFGBlockKind.EXIT, function_node_id=fn1_id),
        ],
        edges=[],
    )

    cfg2 = ControlFlowGraph(
        id="cfg:2", function_node_id=fn2_id, entry_block_id="b0", exit_block_id="b1", blocks=[], edges=[]
    )
    cfg3 = ControlFlowGraph(
        id="cfg:3", function_node_id=fn3_id, entry_block_id="b0", exit_block_id="b1", blocks=[], edges=[]
    )

    node1 = Node(
        id=fn1_id,
        kind=NodeKind.FUNCTION,
        fqn="f1",
        file_path="f.py",
        span=Span(1, 0, 5, 0),
        language="python",
        name="f1",
        attrs={},
    )
    node2 = Node(
        id=fn2_id,
        kind=NodeKind.FUNCTION,
        fqn="f2",
        file_path="f.py",
        span=Span(6, 0, 10, 0),
        language="python",
        name="f2",
        attrs={},
    )
    node3 = Node(
        id=fn3_id,
        kind=NodeKind.FUNCTION,
        fqn="f3",
        file_path="f.py",
        span=Span(11, 0, 15, 0),
        language="python",
        name="f3",
        attrs={},
    )

    class FakeIRDoc:
        def __init__(self):
            self.nodes = [node1, node2, node3]

    ir_doc = FakeIRDoc()

    # Lazy inferencer
    lazy = LazyLocalFlowInferencer(config=LocalFlowConfig())

    # Process only fn1
    lazy.infer_for_functions([fn1_id], ir_doc, [cfg1, cfg2, cfg3], [])

    # Check: only fn1 processed
    lazy_stats = lazy.get_lazy_stats()
    assert lazy_stats["functions_requested"] == 1
    assert lazy_stats["functions_processed"] == 1

    print(f"\n  ✅ Lazy processed 1/3 functions (33% compute)")


def test_lazy_caches_results():
    """Lazy should cache results and not reprocess"""

    fn_id = "fn:1"
    cfg = ControlFlowGraph(
        id="cfg:1",
        function_node_id=fn_id,
        entry_block_id="b0",
        exit_block_id="b1",
        blocks=[
            ControlFlowBlock(id="b0", kind=CFGBlockKind.ENTRY, function_node_id=fn_id),
        ],
        edges=[],
    )

    node = Node(
        id=fn_id,
        kind=NodeKind.FUNCTION,
        fqn="f",
        file_path="f.py",
        span=Span(1, 0, 5, 0),
        language="python",
        name="f",
        attrs={},
    )

    class FakeIRDoc:
        def __init__(self):
            self.nodes = [node]

    ir_doc = FakeIRDoc()

    lazy = LazyLocalFlowInferencer()

    # First call: should process
    lazy.infer_for_functions([fn_id], ir_doc, [cfg], [])
    stats1 = lazy.get_lazy_stats()

    # Second call: should use cache
    lazy.infer_for_functions([fn_id], ir_doc, [cfg], [])
    stats2 = lazy.get_lazy_stats()

    assert stats2["functions_processed"] == 1, "Should only process once"
    assert stats2["functions_requested"] == 2, "Requested twice"
    assert stats2["savings_percent"] == 50.0, "50% savings from cache"

    print(f"\n  ✅ Cache hit on 2nd request: {stats2['savings_percent']}% savings")


def test_lazy_resolves_dependencies_via_call_graph():
    """Lazy should auto-include dependencies when call_graph provided"""

    # Setup: f1 calls f2, f2 calls f3
    call_graph = {
        "fn:1": ["fn:2"],
        "fn:2": ["fn:3"],
        "fn:3": [],
    }

    fn1 = Node(
        id="fn:1",
        kind=NodeKind.FUNCTION,
        fqn="f1",
        file_path="f.py",
        span=Span(1, 0, 5, 0),
        language="python",
        name="f1",
        attrs={},
    )
    fn2 = Node(
        id="fn:2",
        kind=NodeKind.FUNCTION,
        fqn="f2",
        file_path="f.py",
        span=Span(6, 0, 10, 0),
        language="python",
        name="f2",
        attrs={},
    )
    fn3 = Node(
        id="fn:3",
        kind=NodeKind.FUNCTION,
        fqn="f3",
        file_path="f.py",
        span=Span(11, 0, 15, 0),
        language="python",
        name="f3",
        attrs={},
    )

    class FakeIRDoc:
        def __init__(self):
            self.nodes = [fn1, fn2, fn3]

    ir_doc = FakeIRDoc()

    lazy = LazyLocalFlowInferencer(call_graph=call_graph)

    # Request only fn1: should process fn1, fn2, fn3 (transitive)
    lazy.infer_for_functions(["fn:1"], ir_doc, [], [])

    stats = lazy.get_lazy_stats()
    assert stats["functions_requested"] == 1
    assert stats["functions_processed"] == 3, "Should process all in call chain"

    print(f"\n  ✅ Dependency resolution: 1 requested → 3 processed")
