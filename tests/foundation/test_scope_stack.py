"""
Scope Stack Tests

Tests for scope tracking during AST traversal.
"""


from src.foundation.generators.scope_stack import ScopeFrame, ScopeStack


class TestScopeFrame:
    """Test ScopeFrame dataclass."""

    def test_scope_frame_creation(self):
        """Test ScopeFrame can be instantiated."""
        frame = ScopeFrame(
            kind="function",
            name="foo",
            fqn="module.foo",
        )

        assert frame.kind == "function"
        assert frame.name == "foo"
        assert frame.fqn == "module.foo"
        assert frame.node_id is None
        assert frame.symbols == {}

    def test_scope_frame_with_node_id(self):
        """Test ScopeFrame with node_id."""
        frame = ScopeFrame(
            kind="class",
            name="MyClass",
            fqn="module.MyClass",
            node_id="node_123",
        )

        assert frame.node_id == "node_123"

    def test_scope_frame_symbols(self):
        """Test ScopeFrame symbol table."""
        frame = ScopeFrame(kind="module", name="test", fqn="test")

        # Add symbols
        frame.symbols["x"] = "node_1"
        frame.symbols["y"] = "node_2"

        assert frame.symbols["x"] == "node_1"
        assert frame.symbols["y"] == "node_2"
        assert len(frame.symbols) == 2


class TestScopeStackInitialization:
    """Test ScopeStack initialization."""

    def test_scope_stack_creation(self):
        """Test ScopeStack initializes with module scope."""
        stack = ScopeStack(module_fqn="my_module")

        assert stack is not None
        assert len(stack._stack) == 1
        assert stack.current.kind == "module"
        assert stack.current.name == "my_module"
        assert stack.current.fqn == "my_module"

    def test_module_property(self):
        """Test module property returns module scope."""
        stack = ScopeStack(module_fqn="test.module")

        module_frame = stack.module

        assert module_frame.kind == "module"
        assert module_frame.fqn == "test.module"


class TestPushPop:
    """Test push/pop scope operations."""

    def test_push_function_scope(self):
        """Test pushing function scope."""
        stack = ScopeStack(module_fqn="module")

        frame = stack.push("function", "foo", "module.foo")

        assert frame.kind == "function"
        assert frame.name == "foo"
        assert frame.fqn == "module.foo"
        assert len(stack._stack) == 2
        assert stack.current is frame

    def test_push_class_scope(self):
        """Test pushing class scope."""
        stack = ScopeStack(module_fqn="module")

        frame = stack.push("class", "MyClass", "module.MyClass")

        assert frame.kind == "class"
        assert len(stack._stack) == 2

    def test_push_nested_scopes(self):
        """Test pushing nested scopes."""
        stack = ScopeStack(module_fqn="module")

        # Push class
        class_frame = stack.push("class", "MyClass", "module.MyClass")
        assert len(stack._stack) == 2

        # Push method inside class
        method_frame = stack.push("function", "method", "module.MyClass.method")
        assert len(stack._stack) == 3
        assert stack.current is method_frame

    def test_pop_scope(self):
        """Test popping scope."""
        stack = ScopeStack(module_fqn="module")

        # Push function
        func_frame = stack.push("function", "foo", "module.foo")
        assert stack.current is func_frame

        # Pop function
        popped = stack.pop()

        assert popped is func_frame
        assert stack.current.kind == "module"
        assert len(stack._stack) == 1

    def test_pop_keeps_module_scope(self):
        """Test pop doesn't remove module scope."""
        stack = ScopeStack(module_fqn="module")

        # Try to pop module scope
        popped = stack.pop()

        assert popped is None
        assert len(stack._stack) == 1
        assert stack.current.kind == "module"

    def test_pop_nested_scopes(self):
        """Test popping nested scopes."""
        stack = ScopeStack(module_fqn="module")

        # Build nested structure
        stack.push("class", "MyClass", "module.MyClass")
        stack.push("function", "method", "module.MyClass.method")

        assert len(stack._stack) == 3

        # Pop method
        stack.pop()
        assert len(stack._stack) == 2
        assert stack.current.name == "MyClass"

        # Pop class
        stack.pop()
        assert len(stack._stack) == 1
        assert stack.current.kind == "module"


class TestCurrentScope:
    """Test current scope properties."""

    def test_current_property(self):
        """Test current property returns top of stack."""
        stack = ScopeStack(module_fqn="module")

        assert stack.current.kind == "module"

        func_frame = stack.push("function", "foo", "module.foo")
        assert stack.current is func_frame

    def test_current_fqn(self):
        """Test current_fqn method."""
        stack = ScopeStack(module_fqn="module")

        assert stack.current_fqn() == "module"

        stack.push("class", "MyClass", "module.MyClass")
        assert stack.current_fqn() == "module.MyClass"

        stack.push("function", "method", "module.MyClass.method")
        assert stack.current_fqn() == "module.MyClass.method"


class TestScopeProperties:
    """Test class_scope and function_scope properties."""

    def test_class_scope_none_at_module_level(self):
        """Test class_scope returns None at module level."""
        stack = ScopeStack(module_fqn="module")

        assert stack.class_scope is None

    def test_class_scope_inside_class(self):
        """Test class_scope returns class when inside class."""
        stack = ScopeStack(module_fqn="module")

        class_frame = stack.push("class", "MyClass", "module.MyClass")

        assert stack.class_scope is class_frame

    def test_class_scope_inside_method(self):
        """Test class_scope returns class when inside method."""
        stack = ScopeStack(module_fqn="module")

        class_frame = stack.push("class", "MyClass", "module.MyClass")
        stack.push("function", "method", "module.MyClass.method")

        # Should still return class scope
        assert stack.class_scope is class_frame

    def test_function_scope_none_at_module_level(self):
        """Test function_scope returns None at module level."""
        stack = ScopeStack(module_fqn="module")

        assert stack.function_scope is None

    def test_function_scope_inside_function(self):
        """Test function_scope returns function when inside function."""
        stack = ScopeStack(module_fqn="module")

        func_frame = stack.push("function", "foo", "module.foo")

        assert stack.function_scope is func_frame

    def test_function_scope_not_inside_class(self):
        """Test function_scope returns None when only inside class."""
        stack = ScopeStack(module_fqn="module")

        stack.push("class", "MyClass", "module.MyClass")

        # Inside class but not function
        assert stack.function_scope is None

    def test_function_scope_nested_functions(self):
        """Test function_scope with nested functions."""
        stack = ScopeStack(module_fqn="module")

        stack.push("function", "outer", "module.outer")
        inner_frame = stack.push("function", "inner", "module.outer.inner")

        # Should return innermost function
        assert stack.function_scope is inner_frame


class TestSymbolRegistration:
    """Test symbol registration and lookup."""

    def test_register_symbol_in_current_scope(self):
        """Test registering symbol in current scope."""
        stack = ScopeStack(module_fqn="module")

        stack.register_symbol("x", "node_1")

        assert stack.current.symbols["x"] == "node_1"

    def test_register_multiple_symbols(self):
        """Test registering multiple symbols."""
        stack = ScopeStack(module_fqn="module")

        stack.register_symbol("x", "node_1")
        stack.register_symbol("y", "node_2")
        stack.register_symbol("z", "node_3")

        assert len(stack.current.symbols) == 3
        assert stack.current.symbols["y"] == "node_2"

    def test_lookup_symbol_in_current_scope(self):
        """Test looking up symbol in current scope."""
        stack = ScopeStack(module_fqn="module")

        stack.register_symbol("x", "node_1")

        found = stack.lookup_symbol("x")
        assert found == "node_1"

    def test_lookup_symbol_not_found(self):
        """Test looking up non-existent symbol."""
        stack = ScopeStack(module_fqn="module")

        found = stack.lookup_symbol("unknown")
        assert found is None

    def test_lookup_symbol_in_parent_scope(self):
        """Test looking up symbol from parent scope."""
        stack = ScopeStack(module_fqn="module")

        # Register in module scope
        stack.register_symbol("x", "node_1")

        # Push function scope
        stack.push("function", "foo", "module.foo")

        # Should find 'x' from parent module scope
        found = stack.lookup_symbol("x")
        assert found == "node_1"

    def test_lookup_symbol_shadowing(self):
        """Test symbol shadowing in nested scopes."""
        stack = ScopeStack(module_fqn="module")

        # Register 'x' in module scope
        stack.register_symbol("x", "node_1")

        # Push function scope and shadow 'x'
        stack.push("function", "foo", "module.foo")
        stack.register_symbol("x", "node_2")

        # Should find shadowed version
        found = stack.lookup_symbol("x")
        assert found == "node_2"

        # Pop function scope
        stack.pop()

        # Should find original version
        found = stack.lookup_symbol("x")
        assert found == "node_1"


class TestImports:
    """Test import registration and resolution."""

    def test_register_import(self):
        """Test registering import alias."""
        stack = ScopeStack(module_fqn="module")

        stack.register_import("np", "numpy")

        assert stack._imports["np"] == "numpy"

    def test_register_multiple_imports(self):
        """Test registering multiple imports."""
        stack = ScopeStack(module_fqn="module")

        stack.register_import("np", "numpy")
        stack.register_import("pd", "pandas")
        stack.register_import("plt", "matplotlib.pyplot")

        assert len(stack._imports) == 3

    def test_resolve_import_success(self):
        """Test resolving import alias successfully."""
        stack = ScopeStack(module_fqn="module")

        stack.register_import("np", "numpy")

        resolved = stack.resolve_import("np")
        assert resolved == "numpy"

    def test_resolve_import_not_found(self):
        """Test resolving non-existent import."""
        stack = ScopeStack(module_fqn="module")

        resolved = stack.resolve_import("unknown")
        assert resolved is None


class TestBuildFqn:
    """Test building fully qualified names."""

    def test_build_fqn_at_module_level(self):
        """Test building FQN at module level."""
        stack = ScopeStack(module_fqn="module")

        fqn = stack.build_fqn("foo")

        assert fqn == "module.foo"

    def test_build_fqn_inside_class(self):
        """Test building FQN inside class."""
        stack = ScopeStack(module_fqn="module")

        stack.push("class", "MyClass", "module.MyClass")

        fqn = stack.build_fqn("method")

        assert fqn == "module.MyClass.method"

    def test_build_fqn_nested_scopes(self):
        """Test building FQN in deeply nested scopes."""
        stack = ScopeStack(module_fqn="my.package.module")

        stack.push("class", "OuterClass", "my.package.module.OuterClass")
        stack.push("class", "InnerClass", "my.package.module.OuterClass.InnerClass")

        fqn = stack.build_fqn("method")

        assert fqn == "my.package.module.OuterClass.InnerClass.method"


class TestRepr:
    """Test string representation."""

    def test_repr_module_only(self):
        """Test __repr__ with module scope only."""
        stack = ScopeStack(module_fqn="test_module")

        repr_str = repr(stack)

        assert "ScopeStack" in repr_str
        assert "module:test_module" in repr_str

    def test_repr_with_function(self):
        """Test __repr__ with function scope."""
        stack = ScopeStack(module_fqn="module")
        stack.push("function", "foo", "module.foo")

        repr_str = repr(stack)

        assert "module:module" in repr_str
        assert "function:foo" in repr_str
        assert "->" in repr_str

    def test_repr_nested_scopes(self):
        """Test __repr__ with nested scopes."""
        stack = ScopeStack(module_fqn="module")
        stack.push("class", "MyClass", "module.MyClass")
        stack.push("function", "method", "module.MyClass.method")

        repr_str = repr(stack)

        assert "module:module" in repr_str
        assert "class:MyClass" in repr_str
        assert "function:method" in repr_str
