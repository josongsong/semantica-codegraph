"""
Kuzu Graph Store Connection Example

This example demonstrates how to:
1. Initialize Kuzu graph store
2. Save a GraphDocument
3. Query the graph
"""

from pathlib import Path

from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.infra.graph.kuzu import KuzuGraphStore


def main():
    # 1. Initialize Kuzu store
    db_path = Path("./data/kuzu_example")
    store = KuzuGraphStore(db_path=db_path, include_framework_rels=False)

    print(f"✓ Initialized Kuzu database at: {db_path}")

    # 2. Create sample GraphDocument
    graph_doc = GraphDocument(
        repo_id="example_repo",
        snapshot_id="snapshot_001",
    )

    # Add nodes
    file_node = GraphNode(
        id="file:example.py",
        kind=GraphNodeKind.FILE,
        repo_id="example_repo",
        snapshot_id="snapshot_001",
        fqn="example.py",
        name="example.py",
        path="example.py",
    )

    function_node = GraphNode(
        id="func:example.calculate",
        kind=GraphNodeKind.FUNCTION,
        repo_id="example_repo",
        snapshot_id="snapshot_001",
        fqn="example.calculate",
        name="calculate",
        attrs={"language": "python"},
    )

    graph_doc.graph_nodes[file_node.id] = file_node
    graph_doc.graph_nodes[function_node.id] = function_node

    # Add edge (file contains function)
    contains_edge = GraphEdge(
        id="edge:file_contains_func",
        kind=GraphEdgeKind.CONTAINS,
        source_id=file_node.id,
        target_id=function_node.id,
    )
    graph_doc.graph_edges.append(contains_edge)

    print(f"✓ Created GraphDocument with {graph_doc.node_count} nodes and {graph_doc.edge_count} edges")

    # 3. Save to Kuzu
    store.save_graph(graph_doc)
    print("✓ Saved GraphDocument to Kuzu")

    # 4. Query the graph
    children = store.query_contains_children(file_node.id)
    print(f"✓ Query result: file contains {len(children)} child(ren): {children}")

    # 5. Query node by ID
    node_data = store.query_node_by_id(function_node.id)
    if node_data:
        print(f"✓ Retrieved node: {node_data['name']} (kind: {node_data['kind']})")

    # 6. Clean up
    store.close()
    print("✓ Closed Kuzu connection")


if __name__ == "__main__":
    main()
