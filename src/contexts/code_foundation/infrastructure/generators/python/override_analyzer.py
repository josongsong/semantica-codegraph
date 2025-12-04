"""
Method Override Analyzer

Analyzes method override relationships in Python code.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models import Edge, IRDocument, Node


def analyze_method_overrides(ir_doc: "IRDocument") -> list["Edge"]:
    """
    Analyze method override relationships and create OVERRIDES edges.

    Strategy:
    1. Build class hierarchy from INHERITS edges
    2. For each class, find its methods
    3. For each method, check if parent class has same method
    4. Create OVERRIDES edge if match found

    Args:
        ir_doc: IR document with nodes and edges

    Returns:
        List of OVERRIDES edges

    Note:
        This requires:
        - Classes to have base_classes in attrs
        - INHERITS edges to be created during IR generation
        For full implementation, these should be added to PythonIRGenerator._process_class()
    """
    from src.contexts.code_foundation.infrastructure.ir.models import Edge, EdgeKind, NodeKind

    override_edges = []

    # Build class index: class_fqn → node
    class_index: dict[str, Node] = {}
    for node in ir_doc.nodes:
        if node.kind == NodeKind.CLASS:
            class_index[node.fqn] = node

    # Build method index: class_fqn → {method_name: node}
    method_index: dict[str, dict[str, Node]] = {}
    for node in ir_doc.nodes:
        if node.kind == NodeKind.METHOD:
            # Extract class FQN from method FQN (e.g., "module.Class.method" → "module.Class")
            parts = node.fqn.split(".")
            if len(parts) >= 2:
                class_fqn = ".".join(parts[:-1])
                method_name = parts[-1]

                if class_fqn not in method_index:
                    method_index[class_fqn] = {}
                method_index[class_fqn][method_name] = node

    # Find method overrides
    for class_fqn, class_node in class_index.items():
        # Get base classes from attrs (if available)
        base_classes = class_node.attrs.get("base_classes", [])

        if not base_classes:
            continue

        # Get methods of this class
        child_methods = method_index.get(class_fqn, {})

        # Check each method against parent class methods
        for method_name, method_node in child_methods.items():
            # Skip special methods like __init__, __str__ (not overrides in semantic sense)
            if method_name.startswith("__") and method_name.endswith("__"):
                continue

            # Check each base class for matching method
            for base_fqn in base_classes:
                # base_classes now contains fully resolved FQNs from PythonIRGenerator
                # No need to re-resolve - trust the FQN resolution done during IR generation

                # Find parent method
                parent_methods = method_index.get(base_fqn, {})
                parent_method = parent_methods.get(method_name)

                if parent_method:
                    # Create OVERRIDES edge
                    edge_id = f"edge:override:{method_node.id}:{parent_method.id}"
                    override_edge = Edge(
                        id=edge_id,
                        kind=EdgeKind.OVERRIDES,
                        source_id=method_node.id,
                        target_id=parent_method.id,
                        span=None,  # Edge doesn't have specific location
                        attrs={
                            "method_name": method_name,
                            "child_class": class_fqn,
                            "parent_class": base_fqn,
                        },
                    )
                    override_edges.append(override_edge)
                    break  # Found override, no need to check other bases

    return override_edges


def extract_base_classes_from_ast(class_node) -> list[str]:
    """
    Extract base class names from class_definition AST node.

    Args:
        class_node: Tree-sitter class_definition node

    Returns:
        List of base class names

    Example:
        class Child(Parent, Mixin):
            pass
        → ["Parent", "Mixin"]
    """
    base_classes = []

    # Find argument_list node (contains base classes)
    for child in class_node.children:
        if child.type == "argument_list":
            # Extract each base class from argument_list
            for arg_child in child.children:
                if arg_child.type == "identifier":
                    # Simple base class: class Child(Parent)
                    base_name = arg_child.text.decode("utf-8") if arg_child.text else ""
                    if base_name:
                        base_classes.append(base_name)
                elif arg_child.type == "attribute":
                    # Qualified base class: class Child(module.Parent)
                    base_name = arg_child.text.decode("utf-8") if arg_child.text else ""
                    if base_name:
                        base_classes.append(base_name)

    return base_classes
