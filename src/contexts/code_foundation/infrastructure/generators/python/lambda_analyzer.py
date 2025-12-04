"""
Python Lambda Expression Analyzer

Analyzes lambda expressions in Python code and creates LAMBDA IR nodes.
"""

from typing import TYPE_CHECKING

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_logical_id
from src.contexts.code_foundation.infrastructure.ir.models import ControlFlowSummary, Node, NodeKind, Span

if TYPE_CHECKING:
    from collections.abc import Callable


class PythonLambdaAnalyzer:
    """
    Analyzes lambda expressions and creates LAMBDA IR nodes.

    Lambda expressions in Python:
    - lambda x: x * 2
    - lambda x, y: x + y
    - lambda x, y=10: x + y  (with default params)
    """

    def __init__(self):
        """Initialize lambda analyzer"""
        pass

    def process_lambdas_in_block(
        self,
        block_node: TSNode,
        parent_function_id: str,
        repo_id: str,
        file_path: str,
        language: str,
        module_path: str,
        get_span: "Callable[[TSNode], Span]",
        get_node_text: "Callable[[TSNode, bytes], str]",
        source_bytes: bytes,
        scope_fqn: str,
    ) -> list[Node]:
        """
        Process all lambda expressions in a code block.

        Args:
            block_node: AST block node to search
            parent_function_id: Parent function node ID
            repo_id: Repository ID
            file_path: Source file path
            language: Programming language
            module_path: Module path for imports
            get_span: Function to get span from node
            get_node_text: Function to get text from node
            source_bytes: Source code as bytes
            scope_fqn: Current scope FQN

        Returns:
            List of LAMBDA nodes created
        """
        lambda_nodes = []
        lambda_counter = [0]  # Use list for mutability in nested function

        def extract_lambdas(node: TSNode, depth: int = 0):
            """Recursively extract lambda expressions"""
            if depth > 50:  # Prevent infinite recursion
                return

            if node.type == "lambda":
                lambda_counter[0] += 1
                lambda_num = lambda_counter[0]

                # Build FQN for lambda (e.g., "module.func.<lambda_1>")
                lambda_fqn = f"{scope_fqn}.<lambda_{lambda_num}>"

                # Generate node ID
                span = get_span(node)
                node_id = generate_logical_id(
                    repo_id=repo_id,
                    kind=NodeKind.LAMBDA,
                    file_path=file_path,
                    fqn=lambda_fqn,
                )

                # Extract parameters from lambda_parameters
                params = []
                param_node = None
                body_node = None

                for child in node.children:
                    if child.type == "lambda_parameters":
                        param_node = child
                    elif child.type not in ("lambda", ":", "lambda_parameters"):
                        # Body is everything after ":"
                        body_node = child

                if param_node:
                    for param_child in param_node.children:
                        if param_child.type == "identifier":
                            param_name = get_node_text(param_child, source_bytes)
                            params.append(param_name)
                        elif param_child.type == "default_parameter":
                            # Extract parameter name from default_parameter
                            for dp_child in param_child.children:
                                if dp_child.type == "identifier":
                                    param_name = get_node_text(dp_child, source_bytes)
                                    params.append(param_name)
                                    break

                # Calculate control flow summary (lambdas are simple - single expression)
                cf_summary = ControlFlowSummary(
                    cyclomatic_complexity=1,  # Lambda is always complexity 1
                    has_loop=False,
                    has_try=False,
                    branch_count=0,
                )

                # Get body span
                body_span = get_span(body_node) if body_node else None

                # Create attrs dict
                attrs = {
                    "params": params,
                    "param_count": len(params),
                }

                # Create LAMBDA node
                lambda_node = Node(
                    id=node_id,
                    kind=NodeKind.LAMBDA,
                    fqn=lambda_fqn,
                    file_path=file_path,
                    span=span,
                    language=language,
                    name=f"<lambda_{lambda_num}>",
                    module_path=module_path,
                    parent_id=parent_function_id,
                    body_span=body_span,
                    control_flow_summary=cf_summary,
                    attrs=attrs,
                )

                lambda_nodes.append(lambda_node)

                # Only process body for nested lambdas
                # Don't re-process lambda_parameters or other parts
                if body_node:
                    extract_lambdas(body_node, depth + 1)
                return  # Don't process other children after finding lambda

            # Recursively process children
            for child in node.children:
                extract_lambdas(child, depth + 1)

        # Start extraction from block
        extract_lambdas(block_node)

        return lambda_nodes
