from src.parsers.python_parser import PythonParser


def test_python_parser_basic():
    """기본 파싱 테스트"""
    parser = PythonParser()
    code = """
def hello():
    return "world"

class MyClass:
    def method(self):
        pass
"""
    nodes = parser.parse(code, "test.py")
    assert len(nodes) > 0


def test_extract_imports():
    """import 추출 테스트"""
    parser = PythonParser()
    code = """
import os
from typing import List
"""
    imports = parser.extract_imports(code)
    assert len(imports) == 2
    assert "import os" in imports[0]


def test_extract_definitions():
    """정의 추출 테스트"""
    parser = PythonParser()
    code = """
def my_function():
    pass

class MyClass:
    pass
"""
    nodes = parser.extract_definitions(code)
    assert len(nodes) == 2
    assert any(n.name == "my_function" for n in nodes)
    assert any(n.name == "MyClass" for n in nodes)
