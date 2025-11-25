"""
Test BFG (Basic Flow Graph) Builder

Tests basic block extraction from IR.
"""


from src.foundation.ir.models import IRDocument, Node, NodeKind, Span
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir.bfg.builder import BfgBuilder
from src.foundation.semantic_ir.bfg.models import BFGBlockKind


def test_bfg_builder_simple_function():
    """Test BFG extraction for simple function"""
    # Create simple IR with one function
    func_node = Node(
        id="test_func",
        kind=NodeKind.FUNCTION,
        name="test_func",
        fqn="test_func",
        file_path="test.py",
        language="python",
        span=Span(1, 0, 3, 0),
        body_span=Span(2, 4, 3, 0),
        parent_id=None,
    )

    ir_doc = IRDocument(
        repo_id="test_repo",
        snapshot_id="test_snapshot",
        schema_version="1.0",
        nodes=[func_node],
    )

    # Build BFG without source map (simplified mode)
    builder = BfgBuilder()
    bfg_graphs, bfg_blocks = builder.build_full(ir_doc, {})

    # Assertions
    assert len(bfg_graphs) == 1
    assert bfg_graphs[0].function_node_id == "test_func"

    # Should have Entry + Exit + Body blocks (3 total)
    assert len(bfg_blocks) == 3

    # Check block kinds
    block_kinds = {b.kind for b in bfg_blocks}
    assert BFGBlockKind.ENTRY in block_kinds
    assert BFGBlockKind.EXIT in block_kinds
    assert BFGBlockKind.STATEMENT in block_kinds


def test_bfg_builder_with_source():
    """Test BFG extraction with source code (enhanced mode)"""
    source_code = """def hello(name):
    if name:
        print(f"Hello {name}")
    else:
        print("Hello stranger")
"""

    source_file = SourceFile(file_path="test.py", content=source_code, language="python")

    func_node = Node(
        id="hello_func",
        kind=NodeKind.FUNCTION,
        name="hello",
        fqn="hello",
        file_path="test.py",
        language="python",
        span=Span(1, 0, 5, 0),
        body_span=Span(2, 4, 5, 0),
        parent_id=None,
    )

    ir_doc = IRDocument(
        repo_id="test_repo",
        snapshot_id="test_snapshot",
        schema_version="1.0",
        nodes=[func_node],
    )

    # Build BFG with source map
    builder = BfgBuilder()
    bfg_graphs, bfg_blocks = builder.build_full(ir_doc, {"test.py": source_file})

    # Assertions
    assert len(bfg_graphs) == 1

    # Should have Entry, Exit, Condition, and Statement blocks
    block_kinds = {b.kind for b in bfg_blocks}
    assert BFGBlockKind.ENTRY in block_kinds
    assert BFGBlockKind.EXIT in block_kinds
    assert BFGBlockKind.CONDITION in block_kinds


def test_bfg_builder_loop():
    """Test BFG extraction with loop"""
    source_code = """def count():
    for i in range(10):
        print(i)
"""

    source_file = SourceFile(file_path="test.py", content=source_code, language="python")

    func_node = Node(
        id="count_func",
        kind=NodeKind.FUNCTION,
        name="count",
        fqn="count",
        file_path="test.py",
        language="python",
        span=Span(1, 0, 3, 0),
        body_span=Span(2, 4, 3, 0),
        parent_id=None,
    )

    ir_doc = IRDocument(
        repo_id="test_repo",
        snapshot_id="test_snapshot",
        schema_version="1.0",
        nodes=[func_node],
    )

    # Build BFG
    builder = BfgBuilder()
    bfg_graphs, bfg_blocks = builder.build_full(ir_doc, {"test.py": source_file})

    # Should have LOOP_HEADER block
    block_kinds = {b.kind for b in bfg_blocks}
    assert BFGBlockKind.LOOP_HEADER in block_kinds


def test_bfg_builder_try_except():
    """Test BFG extraction with try/except"""
    source_code = """def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return None
"""

    source_file = SourceFile(file_path="test.py", content=source_code, language="python")

    func_node = Node(
        id="divide_func",
        kind=NodeKind.FUNCTION,
        name="safe_divide",
        fqn="safe_divide",
        file_path="test.py",
        language="python",
        span=Span(1, 0, 5, 0),
        body_span=Span(2, 4, 5, 0),
        parent_id=None,
    )

    ir_doc = IRDocument(
        repo_id="test_repo",
        snapshot_id="test_snapshot",
        schema_version="1.0",
        nodes=[func_node],
    )

    # Build BFG
    builder = BfgBuilder()
    bfg_graphs, bfg_blocks = builder.build_full(ir_doc, {"test.py": source_file})

    # Should have TRY and CATCH blocks
    block_kinds = {b.kind for b in bfg_blocks}
    assert BFGBlockKind.TRY in block_kinds
    assert BFGBlockKind.CATCH in block_kinds


def test_bfg_id_format():
    """Test BFG ID format"""
    func_node = Node(
        id="test::func",
        kind=NodeKind.FUNCTION,
        name="func",
        fqn="test.func",
        file_path="test.py",
        language="python",
        span=Span(1, 0, 2, 0),
        parent_id=None,
    )

    ir_doc = IRDocument(
        repo_id="test_repo",
        snapshot_id="test_snapshot",
        schema_version="1.0",
        nodes=[func_node],
    )

    builder = BfgBuilder()
    bfg_graphs, bfg_blocks = builder.build_full(ir_doc, {})

    # Check BFG ID format
    assert bfg_graphs[0].id == "bfg:test::func"

    # Check block ID format
    for block in bfg_blocks:
        assert block.id.startswith("bfg:test::func:block:")
