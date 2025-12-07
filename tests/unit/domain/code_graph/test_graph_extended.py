"""
Test Extended CodeGraph (Phase 3)

Tests role-based node detection, framework edges, and extended indexes.
"""

import pytest
from src.foundation.generators import PythonIRGenerator
from src.foundation.graph import GraphBuilder, GraphEdgeKind, GraphNodeKind
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir import DefaultSemanticIrBuilder


@pytest.fixture
def python_generator():
    """Create Python IR generator"""
    return PythonIRGenerator(repo_id="test-repo")


@pytest.fixture
def semantic_builder():
    """Create semantic IR builder"""
    return DefaultSemanticIrBuilder()


@pytest.fixture
def graph_builder():
    """Create graph builder"""
    return GraphBuilder()


def test_role_based_node_types(python_generator, semantic_builder, graph_builder):
    """Test that nodes with roles are converted to specialized types"""

    code = """
class UserService:
    \"\"\"Service for user operations\"\"\"
    def get_user(self, user_id: int):
        return user_id

class UserRepository:
    \"\"\"Repository for user data\"\"\"
    def find_by_id(self, user_id: int):
        return user_id
"""

    # Generate IR
    source = SourceFile.from_content("src/services/user_service.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Manually set roles (normally done by role tagger)
    for node in ir_doc.nodes:
        if node.name == "UserService":
            node.role = "service"
        elif node.name == "UserRepository":
            node.role = "repository"
        elif node.name == "get_user":
            node.role = "service"
        elif node.name == "find_by_id":
            node.role = "repository"

    # Generate Semantic IR
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Graph Stats:")
    stats = graph_doc.stats()
    print(f"    - Total nodes: {stats['total_nodes']}")
    print(f"    - Node kinds: {stats['nodes_by_kind']}")

    # Verify specialized nodes were created
    assert "Service" in stats["nodes_by_kind"]
    assert "Repository" in stats["nodes_by_kind"]

    # Verify specific nodes
    service_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.SERVICE)
    repository_nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.REPOSITORY)

    assert len(service_nodes) >= 1
    assert len(repository_nodes) >= 1

    print(f"    - Services: {[n.name for n in service_nodes]}")
    print(f"    - Repositories: {[n.name for n in repository_nodes]}")

    print("\n✅ Role-based node types test passed!")


def test_extended_indexes(python_generator, semantic_builder, graph_builder):
    """Test extended indexes (routes_by_path, services_by_domain)"""

    code = """
class OrderService:
    \"\"\"Service for order operations\"\"\"
    def create_order(self, order_data):
        pass

class PaymentService:
    \"\"\"Service for payment operations\"\"\"
    def process_payment(self, payment_data):
        pass
"""

    # Generate IR
    source = SourceFile.from_content("src/services/order_service.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Set roles and domain tags
    for node in ir_doc.nodes:
        if "OrderService" in str(node.name):
            node.role = "service"
            node.attrs["domain_tags"] = ["order", "ecommerce"]
        elif "PaymentService" in str(node.name):
            node.role = "service"
            node.attrs["domain_tags"] = ["payment", "ecommerce"]

    # Generate Semantic IR
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Extended Indexes:")

    # Test services_by_domain index
    ecommerce_services = graph_doc.indexes.get_services_by_domain("ecommerce")
    print(f"    - E-commerce services: {len(ecommerce_services)}")
    assert len(ecommerce_services) >= 2

    order_services = graph_doc.indexes.get_services_by_domain("order")
    print(f"    - Order services: {len(order_services)}")
    assert len(order_services) >= 1

    payment_services = graph_doc.indexes.get_services_by_domain("payment")
    print(f"    - Payment services: {len(payment_services)}")
    assert len(payment_services) >= 1

    print("\n✅ Extended indexes test passed!")


def test_decorator_edges(python_generator, semantic_builder, graph_builder):
    """Test DECORATES edges (Phase 3)"""

    # Note: This test is a placeholder since decorator detection
    # needs to be implemented in the IR generator
    # For now, we'll test that the edge type and index exist

    code = """
def route_decorator(path: str):
    def wrapper(func):
        return func
    return wrapper

@route_decorator("/api/users")
def get_users():
    pass
"""

    # Generate IR
    source = SourceFile.from_content("src/routes/users.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Generate Semantic IR
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Decorator Support:")
    print(f"    - DECORATES edge type exists: {GraphEdgeKind.DECORATES in GraphEdgeKind}")
    print(f"    - decorators_by_target index exists: {hasattr(graph_doc.indexes, 'decorators_by_target')}")

    assert GraphEdgeKind.DECORATES in GraphEdgeKind
    assert hasattr(graph_doc.indexes, "decorators_by_target")

    print("\n✅ Decorator edges test passed!")


def test_request_flow_index(python_generator, semantic_builder, graph_builder):
    """Test request_flow_index (Route → Handler → Service → Repository)"""

    # Note: This test verifies the index structure exists
    # Full integration testing needs route/handler detection in IR generator

    code = """
class UserService:
    def get_user(self, user_id: int):
        return user_id
"""

    # Generate IR
    source = SourceFile.from_content("src/services/user_service.py", code, "python")
    ir_doc = python_generator.generate(source, "snap:001")

    # Set role
    for node in ir_doc.nodes:
        if "UserService" in str(node.name):
            node.role = "service"

    # Generate Semantic IR
    semantic_snapshot, _ = semantic_builder.build_full(ir_doc)

    # Build Graph
    graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)

    print("\n  Request Flow Index:")
    print(f"    - request_flow_index exists: {hasattr(graph_doc.indexes, 'request_flow_index')}")
    print(f"    - Index size: {len(graph_doc.indexes.request_flow_index)}")

    assert hasattr(graph_doc.indexes, "request_flow_index")
    assert isinstance(graph_doc.indexes.request_flow_index, dict)

    print("\n✅ Request flow index test passed!")


def test_all_extended_node_kinds():
    """Test that all Phase 3 node kinds are defined"""

    extended_kinds = [
        GraphNodeKind.ROUTE,
        GraphNodeKind.SERVICE,
        GraphNodeKind.REPOSITORY,
        GraphNodeKind.CONFIG,
        GraphNodeKind.JOB,
        GraphNodeKind.MIDDLEWARE,
        GraphNodeKind.SUMMARY,
    ]

    print("\n  Extended Node Kinds:")
    for kind in extended_kinds:
        print(f"    - {kind.value}: ✓")
        assert kind in GraphNodeKind

    print("\n✅ All extended node kinds test passed!")


def test_all_extended_edge_kinds():
    """Test that all Phase 3 edge kinds are defined"""

    extended_kinds = [
        GraphEdgeKind.ROUTE_HANDLER,
        GraphEdgeKind.HANDLES_REQUEST,
        GraphEdgeKind.USES_REPOSITORY,
        GraphEdgeKind.MIDDLEWARE_NEXT,
        GraphEdgeKind.INSTANTIATES,
        GraphEdgeKind.DECORATES,
    ]

    print("\n  Extended Edge Kinds:")
    for kind in extended_kinds:
        print(f"    - {kind.value}: ✓")
        assert kind in GraphEdgeKind

    print("\n✅ All extended edge kinds test passed!")


if __name__ == "__main__":
    gen = PythonIRGenerator(repo_id="test-repo")
    sem_builder = DefaultSemanticIrBuilder()
    g_builder = GraphBuilder()

    print("=" * 60)
    print("Phase 3 Extended CodeGraph Tests")
    print("=" * 60)

    print("\n" + "=" * 60)
    print("Test 1: Role-based Node Types")
    print("=" * 60)
    test_role_based_node_types(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 2: Extended Indexes")
    print("=" * 60)
    test_extended_indexes(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 3: Decorator Edges")
    print("=" * 60)
    test_decorator_edges(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 4: Request Flow Index")
    print("=" * 60)
    test_request_flow_index(gen, sem_builder, g_builder)

    print("\n" + "=" * 60)
    print("Test 5: All Extended Node Kinds")
    print("=" * 60)
    test_all_extended_node_kinds()

    print("\n" + "=" * 60)
    print("Test 6: All Extended Edge Kinds")
    print("=" * 60)
    test_all_extended_edge_kinds()

    print("\n" + "=" * 60)
    print("✅ All Phase 3 Extended CodeGraph tests passed!")
    print("=" * 60)
