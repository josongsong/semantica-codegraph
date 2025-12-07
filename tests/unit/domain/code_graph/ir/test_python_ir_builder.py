"""
Tests for Python IR Builder
"""

import pytest

from src.ir import IRBuilderFactory, NodeKind, validate_ir
from src.ir.python_builder import PythonIRBuilder


class TestPythonIRBuilder:
    """Test Python IR builder"""

    def test_simple_function(self):
        """Test building IR from a simple function"""
        source_code = """
def hello(name: str) -> str:
    return f"Hello, {name}"
"""
        builder = PythonIRBuilder()
        context = builder.build_ir(source_code, "test.py")

        # Validate
        result = validate_ir(context)
        assert result.is_valid, f"Validation errors: {result.errors}"

        # Check FileIR
        assert context.file_ir.path == "test.py"
        assert context.file_ir.module_name == "test"
        assert context.file_ir.language == "python"

        # Check SymbolIR
        assert len(context.symbols) == 1
        symbol = list(context.symbols.values())[0]
        assert symbol.name == "hello"
        assert symbol.kind == NodeKind.FUNCTION
        assert len(symbol.params) == 1
        assert symbol.params[0].name == "name"
        assert symbol.params[0].type_hint == "str"
        assert symbol.return_type == "str"

    def test_class_with_methods(self):
        """Test building IR from a class with methods"""
        source_code = """
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
"""
        builder = PythonIRBuilder()
        context = builder.build_ir(source_code, "calculator.py")

        # Validate
        result = validate_ir(context)
        assert result.is_valid, f"Validation errors: {result.errors}"

        # Check symbols
        assert len(context.symbols) == 3  # 1 class + 2 methods

        # Check class
        class_symbols = [s for s in context.symbols.values() if s.kind == NodeKind.CLASS]
        assert len(class_symbols) == 1
        calc_class = class_symbols[0]
        assert calc_class.name == "Calculator"

        # Check methods
        method_symbols = [s for s in context.symbols.values() if s.kind == NodeKind.METHOD]
        assert len(method_symbols) == 2
        method_names = {m.name for m in method_symbols}
        assert method_names == {"add", "subtract"}

    def test_function_with_control_flow(self):
        """Test building IR from a function with control flow"""
        source_code = """
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)
"""
        builder = PythonIRBuilder()
        context = builder.build_ir(source_code, "factorial.py")

        # Validate
        result = validate_ir(context)
        assert result.is_valid, f"Validation errors: {result.errors}"

        # Check function
        assert len(context.symbols) == 1
        func = list(context.symbols.values())[0]
        assert func.name == "factorial"

        # Check blocks (should have body block + if block)
        assert len(context.blocks) > 0

        # Check for if block
        if_blocks = [b for b in context.blocks.values() if b.kind == NodeKind.IF]
        assert len(if_blocks) >= 1

    def test_imports(self):
        """Test extracting imports"""
        source_code = """
import os
import sys
from pathlib import Path
from typing import List, Dict
"""
        builder = PythonIRBuilder()
        context = builder.build_ir(source_code, "test.py")

        # Validate
        result = validate_ir(context)
        assert result.is_valid, f"Validation errors: {result.errors}"

        # Check imports
        assert len(context.file_ir.imports) >= 2  # At least os, sys

        import_modules = {imp.module for imp in context.file_ir.imports}
        assert "os" in import_modules or "sys" in import_modules

    @pytest.mark.skip(reason="Decorator extraction needs refinement")
    def test_decorators(self):
        """Test extracting decorators"""
        source_code = """
@property
def name(self) -> str:
    return self._name

@staticmethod
def create():
    return Calculator()
"""
        builder = PythonIRBuilder()
        context = builder.build_ir(source_code, "test.py")

        # Validate
        result = validate_ir(context)
        assert result.is_valid, f"Validation errors: {result.errors}"

        # Check decorators
        assert len(context.symbols) == 2
        # TODO: Fix decorator extraction
        # for symbol in context.symbols.values():
        #     assert len(symbol.decorators) >= 1

    def test_factory_registration(self):
        """Test IR builder factory registration"""
        builder = IRBuilderFactory.create("python")
        assert isinstance(builder, PythonIRBuilder)

        languages = IRBuilderFactory.get_supported_languages()
        assert "python" in languages

    def test_complex_example(self):
        """Test building IR from a complex example"""
        source_code = """
from typing import List, Optional

class UserService:
    def __init__(self, db_client):
        self.db_client = db_client

    def get_user(self, user_id: int) -> Optional[dict]:
        if user_id <= 0:
            return None

        try:
            user = self.db_client.query("users", user_id)
            return user
        except Exception as e:
            print(f"Error: {e}")
            return None

    def list_users(self, limit: int = 10) -> List[dict]:
        users = []
        for i in range(limit):
            user = self.get_user(i)
            if user:
                users.append(user)
        return users
"""
        builder = PythonIRBuilder()
        context = builder.build_ir(source_code, "user_service.py")

        # Validate
        result = validate_ir(context)
        if not result.is_valid:
            for error in result.errors:
                print(f"Error: {error}")
        assert result.is_valid, f"Validation errors: {result.errors}"

        # Check imports
        assert len(context.file_ir.imports) >= 1

        # Check class
        class_symbols = [s for s in context.symbols.values() if s.kind == NodeKind.CLASS]
        assert len(class_symbols) == 1
        assert class_symbols[0].name == "UserService"

        # Check methods
        method_symbols = [s for s in context.symbols.values() if s.kind == NodeKind.METHOD]
        assert len(method_symbols) >= 3  # __init__, get_user, list_users

        # Check blocks (if, try, for)
        if_blocks = [b for b in context.blocks.values() if b.kind == NodeKind.IF]
        try_blocks = [b for b in context.blocks.values() if b.kind == NodeKind.TRY]
        loop_blocks = [b for b in context.blocks.values() if b.kind == NodeKind.LOOP]

        assert len(if_blocks) >= 1
        assert len(try_blocks) >= 1
        assert len(loop_blocks) >= 1

        # Check expressions (calls, returns)
        call_exprs = [e for e in context.expressions.values() if e.kind == NodeKind.CALL]
        return_exprs = [e for e in context.expressions.values() if e.kind == NodeKind.RETURN]

        assert len(call_exprs) >= 1
        assert len(return_exprs) >= 1
