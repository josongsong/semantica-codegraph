"""
TypeScript CFG Lowering

TypeScript AST → MiniIR 변환 (간소화 버전).

CFG 빌드를 위한 기본 제어 흐름 구조 추출.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
from src.common.observability import get_logger

logger = get_logger(__name__)
# TypeScript 제어 흐름 노드 타입
TS_BRANCH_TYPES = {
    "if_statement",
    "switch_statement",
    "conditional_expression",  # ternary
}

TS_LOOP_TYPES = {
    "for_statement",
    "for_in_statement",
    "while_statement",
    "do_statement",
}

TS_TRY_TYPES = {
    "try_statement",
}


def calculate_control_flow_summary(body_node: "TSNode") -> dict:
    """
    Calculate control flow summary for TypeScript function body.

    Args:
        body_node: Function/method body AST node

    Returns:
        Dict with cyclomatic_complexity, has_loop, has_try, branch_count
    """
    if not body_node:
        return {
            "cyclomatic_complexity": 1,
            "has_loop": False,
            "has_try": False,
            "branch_count": 0,
        }

    branch_count = 0
    has_loop = False
    has_try = False

    def traverse(node: "TSNode") -> None:
        nonlocal branch_count, has_loop, has_try

        if node.type in TS_BRANCH_TYPES:
            branch_count += 1
        elif node.type in TS_LOOP_TYPES:
            has_loop = True
            branch_count += 1  # Loop adds complexity
        elif node.type in TS_TRY_TYPES:
            has_try = True
            branch_count += 1  # Try-catch adds complexity

        for child in node.children:
            traverse(child)

    traverse(body_node)

    # Cyclomatic complexity = edges - nodes + 2 (simplified: branches + 1)
    cyclomatic_complexity = branch_count + 1

    return {
        "cyclomatic_complexity": cyclomatic_complexity,
        "has_loop": has_loop,
        "has_try": has_try,
        "branch_count": branch_count,
    }
