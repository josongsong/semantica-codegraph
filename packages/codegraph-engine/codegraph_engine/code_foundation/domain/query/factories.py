"""
Q and E Factories

Factory methods for creating selectors with fluent API.
"""

from .selectors import EdgeSelector, NodeSelector
from .types import EdgeType, SelectorType


class Q:
    """
    NodeSelector Factory

    Provides fluent API for creating node selectors.

    Examples:
        Q.Var("user")                   # Variable
        Q.Func("process_payment")       # Function
        Q.Call("logger.write")          # Call site
        Q.Module("core.*")              # Module (glob pattern)
        Q.Source("request")             # Security source
        Q.Any()                         # Wildcard
    """

    @staticmethod
    def Var(
        name: str | None = None, type: str | None = None, scope: str | None = None, context: str | None = None
    ) -> NodeSelector:
        """
        Variable selector

        Args:
            name: Variable name (supports field access: "user.password")
            type: Variable type
            scope: Variable scope (function FQN)
            context: Call context for context-sensitive analysis

        Examples:
            Q.Var("input")                      # Any variable named "input"
            Q.Var("user.password")              # Field access
            Q.Var(type="str")                   # All string variables
            Q.Var("x", scope="main")            # Variable x in main()
            Q.Var("x", context="call_123")      # Variable x in specific call context
        """
        return NodeSelector(
            selector_type=SelectorType.VAR, name=name, context=context, attrs={"type": type, "scope": scope}
        )

    @staticmethod
    def Func(name: str | None = None) -> NodeSelector:
        """
        Function selector

        Args:
            name: Function name (can include class: "Calculator.add")

        Examples:
            Q.Func("process_payment")
            Q.Func("Calculator.add")            # Method
        """
        return NodeSelector(selector_type=SelectorType.FUNC, name=name)

    @staticmethod
    def Call(name: str | None = None) -> NodeSelector:
        """
        Call site selector

        Args:
            name: Callee name

        Examples:
            Q.Call("execute")                   # Any call to execute()
            Q.Call("logger.write")              # Specific logger method
        """
        return NodeSelector(selector_type=SelectorType.CALL, name=name)

    @staticmethod
    def Block(kind: str | None = None, label: str | None = None) -> NodeSelector:  # Deprecated: use 'kind' instead
        """
        Control flow block selector

        Args:
            kind: Block kind (CFGBlockKind enum or string)
                  Values: "Entry", "Exit", "Block", "Condition", "LoopHeader",
                         "Try", "Catch", "Finally", "Suspend", "Resume"
            label: (Deprecated) Use 'kind' instead for clarity

        Examples:
            # ✅ Type-safe with enum (recommended)
            from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind
            Q.Block(kind=CFGBlockKind.CONDITION)
            Q.Block(kind=CFGBlockKind.LOOP_HEADER)
            Q.Block(kind=CFGBlockKind.TRY)

            # ✅ String (for dynamic queries)
            Q.Block(kind="Condition")
            Q.Block(kind="LoopHeader")

            # ✅ All blocks
            Q.Block()

            # ⚠️ Deprecated (backward compatibility)
            Q.Block(label="Condition")  # Still works but use kind instead
        """
        # Backward compatibility: label → kind
        if label is not None and kind is None:
            import warnings

            warnings.warn(
                "Q.Block(label=...) is deprecated. Use Q.Block(kind=...) instead.", DeprecationWarning, stacklevel=2
            )
            kind = label

        # Convert CFGBlockKind enum to string value
        if kind is not None and hasattr(kind, "value"):
            kind = kind.value

        return NodeSelector(
            selector_type=SelectorType.BLOCK,
            name=kind,  # Internal storage (compatible with node_matcher)
            attrs={"block_kind": kind} if kind else {},
        )

    @staticmethod
    def Module(pattern: str | None = None) -> NodeSelector:
        """
        Module/File selector

        Args:
            pattern: Glob pattern for module path

        Examples:
            Q.Module("core.*")                  # All modules under core/
            Q.Module("*.utils")                 # All utils modules
        """
        return NodeSelector(selector_type=SelectorType.MODULE, pattern=pattern)

    @staticmethod
    def Class(name: str | None = None) -> NodeSelector:
        """
        Class selector

        Args:
            name: Class name

        Examples:
            Q.Class("User")
            Q.Class("models.User")              # With module
        """
        return NodeSelector(selector_type=SelectorType.CLASS, name=name)

    @staticmethod
    def Source(category: str) -> NodeSelector:
        """
        Security source selector

        Args:
            category: Source identifier
                     - Atom ID (e.g., "input.http.flask") for YAML-based analysis
                     - Category (e.g., "request") for simple queries

        Categories (simple queries):
            - "request": HTTP request parameters
            - "file": File input
            - "socket": Network input
            - "env": Environment variables
            - "database": Database queries

        Atom IDs (YAML-based analysis):
            - "input.http.flask": Flask HTTP input
            - "input.http.django": Django HTTP input
            - "input.file.read": File read operations
            - "input.env": Environment variables

        Examples:
            # Simple category-based
            Q.Source("request")                 # User input
            Q.Source("file")                    # File reads

            # YAML atom ID
            Q.Source("input.http.flask")        # Flask-specific
        """
        return NodeSelector(selector_type=SelectorType.SOURCE, name=category)

    @staticmethod
    def Sink(category: str) -> NodeSelector:
        """
        Security sink selector

        Args:
            category: Sink identifier
                     - Atom ID (e.g., "sink.sql.sqlite3") for YAML-based analysis
                     - Category (e.g., "execute") for simple queries

        Categories (simple queries):
            - "execute": Command execution
            - "eval": Code evaluation
            - "sql": SQL queries
            - "log": Logging
            - "file": File writes
            - "network": Network output

        Atom IDs (YAML-based analysis):
            - "sink.sql.sqlite3": SQLite3 execution
            - "sink.sql.psycopg2": PostgreSQL execution
            - "sink.command.os": OS command execution
            - "sink.command.subprocess": Subprocess execution
            - "sink.code.eval": Code evaluation

        Examples:
            # Simple category-based
            Q.Sink("execute")                   # Command injection risk
            Q.Sink("sql")                       # SQL injection risk

            # YAML atom ID
            Q.Sink("sink.sql.sqlite3")          # SQLite-specific
        """
        return NodeSelector(selector_type=SelectorType.SINK, name=category)

    @staticmethod
    def Any() -> NodeSelector:
        """
        Wildcard selector (matches any node)

        Examples:
            Q.Any() >> target                   # All paths to target
            source >> Q.Any()                   # All paths from source
        """
        return NodeSelector(selector_type=SelectorType.ANY)

    @staticmethod
    def Field(obj_name: str, field_name: str) -> NodeSelector:
        """
        Field selector (field-sensitive analysis)

        Args:
            obj_name: Object/variable name
            field_name: Field name (e.g., "id", "name", "[0]")

        Examples:
            Q.Field("user", "id")     # user.id
            Q.Field("list", "[0]")    # list[0]
            Q.Field("obj", "a.b")     # obj.a.b (nested)
        """
        return NodeSelector(
            selector_type=SelectorType.FIELD,
            name=f"{obj_name}.{field_name}",
            attrs={"obj_name": obj_name, "field_name": field_name},
        )

    @staticmethod
    def Expr(kind: str | None = None, id: str | None = None) -> NodeSelector:  # 🔥 id 추가
        """
        Expression selector (NEW: 2025-12)

        Selects expression nodes by ExprKind or ID.

        Args:
            kind: Expression kind (ExprKind enum or string)
            id: Expression ID (for direct matching) 🔥 NEW

        Expression Categories:
            - Value access: NAME_LOAD, ATTRIBUTE, SUBSCRIPT
            - Operations: BINARY_OP, UNARY_OP, COMPARE
            - Calls: CALL
            - Control: IF_EXP, WHILE, FOR
            - Other: LAMBDA, COMPREHENSION, AWAIT, YIELD

        Examples:
            Q.Expr(kind="CALL")                 # All call expressions
            Q.Expr(kind="BINARY_OP")            # All binary operations
            Q.Expr(id="expr::test.py:10:5:1")   # Specific expression 🔥 NEW
        """
        return NodeSelector(
            selector_type=SelectorType.EXPR,
            name=id,  # 🔥 Use name field for ID
            attrs={"expr_kind": kind} if kind else {},
        )

    @staticmethod
    def AliasOf(var_name: str) -> NodeSelector:
        """
        Alias selector (NEW: 2025-12)

        Finds all aliases of a variable using Points-to Analysis.

        Args:
            var_name: Variable name

        Examples:
            # Find all aliases of x
            Q.AliasOf("x")
            # → If x=y, returns [x, y]

            # Alias-aware taint flow
            query = (Q.AliasOf("user_input") >> Q.Sink("execute")).via(E.DFG)
            # → x=user_input; y=x; execute(y) 탐지 가능

        Note:
            Requires Points-to Analysis (heap/points_to.py)
            If alias info unavailable, returns original variable only.
        """
        return NodeSelector(selector_type=SelectorType.ALIAS, name=var_name)

    @staticmethod
    def TemplateSlot(context_kind: str | None = None, is_sink: bool | None = None) -> NodeSelector:
        """
        Template slot selector (RFC-051)

        Finds template slots (XSS analysis targets).

        Args:
            context_kind: Slot context (RAW_HTML, URL_ATTR, HTML_TEXT, etc.)
            is_sink: Filter by sink status (True = XSS sinks only)

        Examples:
            # All RAW_HTML sinks (v-html, dangerouslySetInnerHTML)
            Q.TemplateSlot(context_kind="RAW_HTML")

            # All XSS sinks (RAW_HTML + URL_ATTR)
            Q.TemplateSlot(is_sink=True)

            # Find data flow to XSS sink
            query = (Q.Var("user_input") >> Q.TemplateSlot(is_sink=True)).via(E.BINDS)
            # → Detects: user_input flows to v-html

        Note:
            Requires template_slots in IRDocument (Layer 5.5)
            Use with E.BINDS edge type for variable → slot binding
        """
        attrs = {}
        if context_kind is not None:
            attrs["context_kind"] = context_kind
        if is_sink is not None:
            attrs["is_sink"] = is_sink

        return NodeSelector(selector_type=SelectorType.TEMPLATE_SLOT, attrs=attrs)


class E:
    """
    EdgeSelector Factory

    Provides edge type constants and modifiers.

    Examples:
        E.DFG                               # Data-flow edges
        E.CFG                               # Control-flow edges
        E.CALL                              # Call-graph edges
        E.ALL                               # All edge types
        E.DFG.backward()                    # Backward data-flow
        E.CFG.depth(5)                      # Max 5 hops
        E.DFG | E.CALL                      # Data-flow OR call
    """

    DFG = EdgeSelector(edge_type=EdgeType.DFG)
    """Data-flow edges (variable def-use)"""

    CFG = EdgeSelector(edge_type=EdgeType.CFG)
    """Control-flow edges (sequential execution)"""

    CALL = EdgeSelector(edge_type=EdgeType.CALL)
    """Call-graph edges (function calls)"""

    BINDS = EdgeSelector(edge_type=EdgeType.BINDS)
    """Template binding edges (variable → slot) - RFC-051"""

    RENDERS = EdgeSelector(edge_type=EdgeType.RENDERS)
    """Template rendering edges (function → template) - RFC-051"""

    ESCAPES = EdgeSelector(edge_type=EdgeType.ESCAPES)
    """Template escaping edges (sanitizer → slot) - RFC-051"""

    ALL = EdgeSelector(edge_type=EdgeType.ALL)
    """All edge types (DFG | CFG | CALL | BINDS | RENDERS | ESCAPES)"""
