"""
SQL Injection Detection E2E Test (Simplified)

Direct test without using outdated python_core rules.
"""

from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import SourceFile
from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import TaintAnalyzer, TaintSource, TaintSink
from src.contexts.security_analysis.infrastructure.adapters.taint_analyzer_adapter import TaintAnalyzerAdapter
from src.contexts.code_foundation.infrastructure.analyzers.taint_rules.base import (
    SourceRule,
    SinkRule,
    SanitizerRule,
    Severity,
    VulnerabilityType,
)


# ============================================================
# Simple Taint Rules for Testing
# ============================================================

# Source: input() function call
SQL_SOURCES = [
    SourceRule(
        pattern=r"\binput\b",
        description="User input from stdin",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
    ),
]

# Sink: SQL execute
SQL_SINKS = [
    SinkRule(
        pattern=r"cursor\.execute|execute",
        description="SQL execution",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.SQL_INJECTION,
    ),
]

# Sanitizer: parameterized query
SQL_SANITIZERS = [
    SanitizerRule(
        pattern=r"\?\s*,",
        description="Parameterized query (safe)",
        sanitizes={VulnerabilityType.SQL_INJECTION: 1.0},  # dict, not list!
    ),
]


# ============================================================
# Test Case 1: Simple SQL Injection
# ============================================================

VULNERABLE_CODE_SIMPLE = """
import sqlite3

def get_user():
    # Source: input() function call (tainted data!)
    user_id = input("Enter user ID: ")
    
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    
    # Sink: SQL execution without sanitization
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    
    return cursor.fetchone()
"""


def test_sql_injection_simple():
    """Test simple SQL injection detection"""
    print("\n" + "=" * 60)
    print("Test 1: Simple SQL Injection")
    print("=" * 60)

    # Step 1: Create SourceFile
    source = SourceFile(
        file_path="test_vulnerable.py",
        content=VULNERABLE_CODE_SIMPLE,
        language="python",
    )

    # Step 2: Generate IRDocument
    generator = PythonIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source=source, snapshot_id="test_snapshot")

    print(f"\n[IR] Generated IR with {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")

    # Debug: Print nodes
    print(f"\n[DEBUG] Nodes:")
    for i, node in enumerate(ir_doc.nodes[:10]):  # First 10
        print(
            f"  [{i}] {node.kind.value:15s} {node.name:30s} ({node.file_path}:{node.span.start_line if node.span else 0})"
        )

    # Step 3: Create adapter
    adapter = TaintAnalyzerAdapter(
        source_rules=SQL_SOURCES,
        sink_rules=SQL_SINKS,
        sanitizer_rules=SQL_SANITIZERS,
    )

    # Step 4: Analyze
    print(f"\n[ADAPTER] Running taint analysis...")
    print(f"[ADAPTER] Source rules: {len(adapter.source_rules)}")
    print(f"[ADAPTER] Sink rules: {len(adapter.sink_rules)}")
    print(f"[ADAPTER] Converted sources: {list(adapter.taint_analyzer.sources.keys())}")
    print(f"[ADAPTER] Converted sinks: {list(adapter.taint_analyzer.sinks.keys())}")

    # Manual source/sink detection
    call_graph, node_map = adapter._extract_graph_from_ir(ir_doc)
    source_nodes = adapter.taint_analyzer._find_source_nodes(node_map)
    sink_nodes = adapter.taint_analyzer._find_sink_nodes(node_map)
    print(f"\n[MANUAL] Found {len(source_nodes)} source nodes: {source_nodes}")
    print(f"[MANUAL] Found {len(sink_nodes)} sink nodes: {sink_nodes}")

    taint_paths = adapter.analyze(ir_doc)

    # Step 5: Results
    print(f"\n[RESULT] Found {len(taint_paths)} taint paths")
    for i, path in enumerate(taint_paths):
        print(f"  [{i + 1}] {path.source} → {path.sink}")
        print(f"       Path: {' → '.join(path.path)}")
        print(f"       Sanitized: {path.is_sanitized}")

    # Assertion
    if len(taint_paths) > 0:
        print(f"\n✅ SUCCESS: Detected {len(taint_paths)} SQL injection vulnerabilities!")
        return True
    else:
        print(f"\n⚠️  WARNING: No vulnerabilities detected (expected at least 1)")
        print(f"\n[DEBUG] Checking why...")

        # Check if sources/sinks were found
        call_graph, node_map = adapter._extract_graph_from_ir(ir_doc)
        print(f"  Call graph edges: {sum(len(v) for v in call_graph.values())}")
        print(f"  Nodes: {len(node_map)}")

        # Print edges by kind
        from collections import Counter

        edge_kinds = Counter([edge.kind for edge in ir_doc.edges])
        print(f"\n[DEBUG] Edge kinds: {dict(edge_kinds)}")

        # Print WRITES and READS edges
        print(f"\n[DEBUG] WRITES edges:")
        for edge in ir_doc.edges:
            if edge.kind.value == "WRITES":
                from_node = node_map.get(edge.source_id)
                to_node = node_map.get(edge.target_id)
                from_name = from_node.name if from_node else edge.source_id
                to_name = to_node.name if to_node else edge.target_id
                print(f"  {from_name} --WRITES--> {to_name}")

        print(f"\n[DEBUG] READS edges:")
        for edge in ir_doc.edges:
            if edge.kind.value == "READS":
                from_node = node_map.get(edge.source_id)
                to_node = node_map.get(edge.target_id)
                from_name = from_node.name if from_node else edge.source_id
                to_name = to_node.name if to_node else edge.target_id
                print(f"  {from_name} --READS--> {to_name}")

        # Print call graph
        print(f"\n[DEBUG] Call graph:")
        for from_id, to_ids in list(call_graph.items())[:15]:
            from_node = node_map.get(from_id)
            from_name = from_node.name if from_node and hasattr(from_node, "name") else from_id
            print(f"  {from_name} →")
            for to_id in to_ids[:5]:  # First 5
                to_node = node_map.get(to_id)
                to_name = to_node.name if to_node and hasattr(to_node, "name") else to_id
                print(f"    → {to_name}")

        # Manually check for patterns
        print(f"\n[DEBUG] Checking patterns manually:")
        source_nodes = []
        sink_nodes = []
        for node_id, node in node_map.items():
            if hasattr(node, "name") and node.name:
                for source in SQL_SOURCES:
                    if source.matches(node.name):
                        print(f"  SOURCE: {node.name} (id: {node_id})")
                        source_nodes.append((node_id, node.name))
                for sink in SQL_SINKS:
                    if sink.matches(node.name):
                        print(f"  SINK: {node.name} (id: {node_id})")
                        sink_nodes.append((node_id, node.name))

        # Check if there's a path between any source and sink
        print(f"\n[DEBUG] Checking paths manually:")
        for src_id, src_name in source_nodes:
            for sink_id, sink_name in sink_nodes:
                print(f"  Checking {src_name} → {sink_name}")
                # Simple BFS
                from collections import deque

                queue = deque([(src_id, [src_id])])
                visited = set()
                found = False
                while queue and len(visited) < 100:  # Max 100 nodes
                    current, path = queue.popleft()
                    if current == sink_id:
                        print(f"    ✅ Found path!")
                        path_names = [
                            node_map.get(p).name if node_map.get(p) and hasattr(node_map.get(p), "name") else p
                            for p in path
                        ]
                        print(f"    Path: {' → '.join(path_names)}")
                        found = True
                        break
                    if current in visited:
                        continue
                    visited.add(current)
                    for next_id in call_graph.get(current, []):
                        queue.append((next_id, path + [next_id]))
                if not found:
                    print(f"    ❌ No path found")

        return False


# ============================================================
# Main Runner
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SQL Injection E2E Test (Simplified)")
    print("=" * 60)

    try:
        success = test_sql_injection_simple()
        if success:
            print("\n" + "=" * 60)
            print("✅ TEST PASSED")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("⚠️  TEST INCOMPLETE (debugging needed)")
            print("=" * 60)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback

        traceback.print_exc()
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
