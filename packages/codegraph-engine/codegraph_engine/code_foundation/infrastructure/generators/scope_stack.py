"""
Scope Stack for tracking context during AST traversal
"""

from dataclasses import dataclass, field

from codegraph_engine.code_foundation.infrastructure.ir.models.core import ScopeKind


@dataclass
class ScopeFrame:
    """
    Single scope frame (module/class/function).
    """

    kind: ScopeKind
    name: str  # Scope name
    fqn: str  # Fully qualified name
    node_id: str | None = None  # IR Node ID (once created)

    # Symbol table for this scope
    symbols: dict[str, str] = field(default_factory=dict)  # name -> node_id


class ScopeStack:
    """
    Stack-based scope tracker for AST traversal.

    Tracks:
    - Current module/class/function context
    - Symbol definitions (name -> node_id)
    - Import aliases
    """

    def __init__(self, module_fqn: str):
        """
        Initialize with module scope.

        Args:
            module_fqn: Fully qualified module name
        """
        self._stack: list[ScopeFrame] = []
        self._imports: dict[str, str] = {}  # alias -> full_symbol

        # Push module scope
        self.push(ScopeKind.MODULE, module_fqn, module_fqn)

    def push(self, kind: ScopeKind | str, name: str, fqn: str) -> ScopeFrame:
        """
        Push new scope frame.

        Args:
            kind: Scope kind (ScopeKind enum or string for backward compatibility)
            name: Scope name
            fqn: Fully qualified name

        Returns:
            New scope frame
        """
        # Convert string to enum for backward compatibility
        if isinstance(kind, str):
            kind = ScopeKind(kind)
        frame = ScopeFrame(kind=kind, name=name, fqn=fqn)
        self._stack.append(frame)
        return frame

    def pop(self) -> ScopeFrame | None:
        """Pop current scope frame"""
        if len(self._stack) > 1:  # Keep module scope
            return self._stack.pop()
        return None

    @property
    def current(self) -> ScopeFrame:
        """Get current scope frame"""
        return self._stack[-1]

    @property
    def module(self) -> ScopeFrame:
        """Get module scope"""
        return self._stack[0]

    @property
    def class_scope(self) -> ScopeFrame | None:
        """Get current class scope (if inside class)"""
        for frame in reversed(self._stack):
            if frame.kind == ScopeKind.CLASS:
                return frame
        return None

    @property
    def function_scope(self) -> ScopeFrame | None:
        """Get current function scope (if inside function)"""
        for frame in reversed(self._stack):
            if frame.kind == ScopeKind.FUNCTION:
                return frame
        return None

    def current_fqn(self) -> str:
        """Get current fully qualified name"""
        return self.current.fqn

    def register_symbol(self, name: str, node_id: str):
        """
        Register symbol in current scope.

        Args:
            name: Symbol name
            node_id: IR Node ID
        """
        self.current.symbols[name] = node_id

    def lookup_symbol(self, name: str) -> str | None:
        """
        Lookup symbol from current scope upward.

        Args:
            name: Symbol name to find

        Returns:
            Node ID if found, None otherwise
        """
        # Search from current scope up to module
        for frame in reversed(self._stack):
            if name in frame.symbols:
                return frame.symbols[name]
        return None

    def register_import(self, alias: str, full_symbol: str):
        """
        Register import alias.

        Args:
            alias: Import alias (e.g., "np")
            full_symbol: Full symbol (e.g., "numpy")
        """
        self._imports[alias] = full_symbol

    def resolve_import(self, alias: str) -> str | None:
        """
        Resolve import alias to full symbol.

        Args:
            alias: Import alias

        Returns:
            Full symbol if found
        """
        return self._imports.get(alias)

    def build_fqn(self, name: str) -> str:
        """
        Build FQN for a symbol in current scope.

        Args:
            name: Symbol name

        Returns:
            Fully qualified name
        """
        return f"{self.current_fqn()}.{name}"

    def __repr__(self) -> str:
        scopes = " -> ".join(f"{s.kind}:{s.name}" for s in self._stack)
        return f"ScopeStack({scopes})"
