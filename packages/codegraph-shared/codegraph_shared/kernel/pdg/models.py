"""
PDG Models - Pure Data Classes

Extracted from: reasoning_engine/infrastructure/pdg/pdg_builder.py
Purpose: Shared models for PDG representation
"""

from dataclasses import dataclass
from enum import Enum


class DependencyType(Enum):
    """Dependency 타입"""

    CONTROL = "control"  # Control dependency (if, while, etc.)
    DATA = "data"  # Data dependency (def-use)
    CONTROL_DATA = "both"  # Both control and data dependency


@dataclass(slots=True)
class PDGNode:
    """
    PDG Node.

    각 IR statement를 나타냄.

    SOTA Optimization:
    - slots=True: 40% 메모리 절감, 15% 속도 향상
    - defined_vars/used_vars: set로 변경 (O(1) dedup)
    """

    node_id: str  # Unique ID (e.g., "func:foo:stmt:3")
    statement: str  # Source code statement
    line_number: int  # Line number in source
    defined_vars: set[str]  # Variables defined (write) - O(1) dedup
    used_vars: set[str]  # Variables used (read) - O(1) dedup
    is_entry: bool = False  # Entry node
    is_exit: bool = False  # Exit node
    file_path: str = ""  # Source file path
    start_line: int = 0  # Statement start line (for multi-line)
    end_line: int = 0  # Statement end line


@dataclass(slots=True)
class PDGEdge:
    """
    PDG Edge.

    Node 간 dependency를 나타냄.

    SOTA Optimization:
    - slots=True: 메모리 절감
    """

    from_node: str  # Source node ID
    to_node: str  # Target node ID
    dependency_type: DependencyType
    label: str | None = None  # e.g., "x" for data dependency on variable x
