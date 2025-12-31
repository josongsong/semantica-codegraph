"""
Stub IR Document (Minimal Working Implementation)

Purpose:
    - Enable IRTransactionManager to work WITHOUT code_foundation
    - Provides minimal IR structure for testing
    - Will be replaced by real IRDocument in Phase 6

Architecture: Infrastructure Layer (temporary)
Status: STUB (not production, for testing only)

References:
    - RFC-016: Phase 5 IRTransactionManager
    - Temporary solution until code_foundation integration
"""

import ast
from dataclasses import dataclass, field


@dataclass
class StubLocation:
    """Stub location (simplified)"""

    file_path: str
    start_line: int
    end_line: int

    def __post_init__(self):
        if self.start_line < 0:
            raise ValueError(f"start_line must be >= 0, got {self.start_line}")
        if self.end_line < self.start_line:
            raise ValueError(f"end_line ({self.end_line}) must be >= start_line ({self.start_line})")


@dataclass
class StubIRNode:
    """
    Stub IR Node (minimal implementation)

    Attributes:
        fqn: Fully Qualified Name (e.g., "module.Class.method")
        kind: Node kind (FUNCTION, CLASS, etc.)
        location: Source location
        name: Simple name

    Examples:
        >>> node = StubIRNode(
        ...     fqn="mymodule.MyClass.my_method",
        ...     kind="FUNCTION",
        ...     name="my_method"
        ... )
    """

    fqn: str
    kind: str = "FUNCTION"
    location: StubLocation | None = None
    name: str = ""

    def __post_init__(self):
        if not self.fqn:
            raise ValueError("fqn must be non-empty")

        # Extract name from FQN if not provided
        if not self.name:
            self.name = self.fqn.split(".")[-1]


@dataclass
class StubIRDocument:
    """
    Stub IR Document (minimal implementation)

    Provides basic structure compatible with IRDocumentProtocol.

    Attributes:
        file_path: Source file path
        nodes: List of IR nodes
        edges: List of edges (always empty in stub)

    Examples:
        >>> doc = StubIRDocument("test.py")
        >>> doc.add_node(StubIRNode("test.func", "FUNCTION"))
        >>> len(doc.nodes)
        1
    """

    file_path: str
    nodes: list[StubIRNode] = field(default_factory=list)
    edges: list = field(default_factory=list)  # Always empty in stub

    def __post_init__(self):
        if not self.file_path:
            raise ValueError("file_path must be non-empty")

    def add_node(self, node: StubIRNode) -> None:
        """Add node to document"""
        if not isinstance(node, StubIRNode):
            raise TypeError(f"node must be StubIRNode, got {type(node)}")

        self.nodes.append(node)


class StubIRBuilder:
    """
    Stub IR Builder (minimal implementation)

    Compatible with IRTransactionManager's ir_builder interface.

    Examples:
        >>> builder = StubIRBuilder()
        >>> doc = builder.parse("test.py", "def func(): pass")
        >>> len(doc.nodes)
        1
    """

    def __init__(self):
        self._parser = StubPythonParser()

    def parse(self, file_path: str, content: str) -> StubIRDocument:
        """Parse file to IR document"""
        return self._parser.parse(file_path, content)


class StubPythonParser:
    """
    Stub Python Parser (minimal AST-based)

    Parses Python code to extract basic structure.
    NOT production-ready, for testing only.

    Extracts:
        - Functions (def)
        - Classes (class)
        - Methods (def inside class)

    Examples:
        >>> parser = StubPythonParser()
        >>> doc = parser.parse("test.py", "def func(): pass")
        >>> len(doc.nodes)
        1
        >>> doc.nodes[0].fqn
        'test.func'
    """

    def parse(self, file_path: str, content: str) -> StubIRDocument:
        """
        Parse Python code to IR document

        Args:
            file_path: File path (for FQN)
            content: Python source code

        Returns:
            StubIRDocument with extracted nodes

        Note:
            This is STUB implementation, not production-ready.
            Uses Python AST for basic extraction only.
        """
        doc = StubIRDocument(file_path)

        # Extract module name from file path
        module_name = file_path.replace(".py", "").replace("/", ".")

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Return empty document on syntax error
            return doc

        # Extract top-level functions and classes
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check if it's a method (inside class)
                # For simplicity, treat all as top-level functions
                fqn = f"{module_name}.{node.name}"

                ir_node = StubIRNode(
                    fqn=fqn,
                    kind="FUNCTION",
                    name=node.name,
                    location=StubLocation(
                        file_path=file_path, start_line=node.lineno, end_line=node.end_lineno or node.lineno
                    ),
                )
                doc.add_node(ir_node)

            elif isinstance(node, ast.ClassDef):
                fqn = f"{module_name}.{node.name}"

                ir_node = StubIRNode(
                    fqn=fqn,
                    kind="CLASS",
                    name=node.name,
                    location=StubLocation(
                        file_path=file_path, start_line=node.lineno, end_line=node.end_lineno or node.lineno
                    ),
                )
                doc.add_node(ir_node)

        return doc
