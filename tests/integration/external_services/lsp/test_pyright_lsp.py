"""
Test Pyright LSP Client

Tests the LSP client implementation.
"""

import pytest
from src.foundation.ir.external_analyzers.pyright_lsp import PyrightLSPClient


@pytest.fixture
def sample_python_file(tmp_path):
    """Create a sample Python file for testing"""
    code = '''
from typing import List

class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

def get_users() -> List[User]:
    """Get list of users"""
    return [User("Alice", 30), User("Bob", 25)]

def find_user(users: List[User], name: str) -> User | None:
    """Find user by name"""
    for user in users:
        if user.name == name:
            return user
    return None

# Variable with inferred type
result = get_users()
'''

    file_path = tmp_path / "sample.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def pyright_client(tmp_path):
    """Create Pyright LSP client"""
    try:
        client = PyrightLSPClient(tmp_path)
        yield client
        client.shutdown()
    except RuntimeError as e:
        if "pyright-langserver not found" in str(e):
            pytest.skip("pyright-langserver not installed")
        raise


def test_pyright_client_initialization(pyright_client):
    """Test that LSP client initializes properly"""
    assert pyright_client._initialized
    assert pyright_client._server_process is not None
    assert pyright_client._server_process.poll() is None  # Process is running


def test_hover_on_typed_variable(pyright_client, sample_python_file):
    """Test hover on a variable with type annotation"""
    # Hover on 'name: str' parameter (line 5, col 25)
    hover_info = pyright_client.hover(sample_python_file, line=5, col=25)

    assert hover_info is not None
    assert "type" in hover_info
    assert "str" in hover_info["type"]


def test_hover_on_function_return_type(pyright_client, sample_python_file):
    """Test hover on function with return type"""
    # Hover on 'get_users' function name (line 9, col 4)
    hover_info = pyright_client.hover(sample_python_file, line=9, col=4)

    assert hover_info is not None
    assert "type" in hover_info
    # Should show function signature with List[User] return type
    assert "User" in hover_info["type"]


def test_hover_on_inferred_type(pyright_client, sample_python_file):
    """Test hover on variable with inferred type"""
    # Hover on 'result' variable (line 20, col 0)
    hover_info = pyright_client.hover(sample_python_file, line=20, col=0)

    assert hover_info is not None
    assert "type" in hover_info
    # Should infer List[User] from get_users() return type
    assert "User" in hover_info["type"] or "List" in hover_info["type"]


def test_definition_on_class(pyright_client, sample_python_file):
    """Test go-to-definition on class reference"""
    # Get definition of 'User' in return type (line 9)
    definition = pyright_client.definition(sample_python_file, line=9, col=24)

    assert definition is not None
    assert definition.file_path == sample_python_file
    assert definition.line == 4  # Line where User class is defined


def test_definition_on_function_call(pyright_client, sample_python_file):
    """Test go-to-definition on function call"""
    # Get definition of 'get_users()' call (line 20)
    definition = pyright_client.definition(sample_python_file, line=20, col=9)

    assert definition is not None
    assert definition.file_path == sample_python_file
    assert definition.line == 9  # Line where get_users is defined


def test_references_on_class(pyright_client, sample_python_file):
    """Test find-all-references on class"""
    # Get all references to 'User' class (defined at line 4)
    references = pyright_client.references(sample_python_file, line=4, col=6)

    assert len(references) > 0
    # Should include: class definition, return type annotations, constructor calls
    assert any(ref.line == 4 for ref in references)  # Definition
    assert any(ref.line == 9 for ref in references)  # Return type
    assert any(ref.line == 13 for ref in references)  # Parameter type


def test_hover_caching(pyright_client, sample_python_file):
    """Test that hover results are cached"""
    # First hover
    hover1 = pyright_client.hover(sample_python_file, line=5, col=25)

    # Second hover at same position
    hover2 = pyright_client.hover(sample_python_file, line=5, col=25)

    # Should return cached result (same object)
    assert hover1 == hover2
    assert (str(sample_python_file), 5, 25) in pyright_client._hover_cache


def test_analyze_symbol_compatibility(pyright_client, sample_python_file):
    """Test analyze_symbol compatibility method"""
    # Analyze 'name' parameter
    type_info = pyright_client.analyze_symbol(sample_python_file, line=5, col=25)

    assert type_info is not None
    assert type_info.inferred_type is not None
    assert "str" in type_info.inferred_type
    assert type_info.file_path == str(sample_python_file)
    assert type_info.line == 5


def test_shutdown(pyright_client):
    """Test clean shutdown"""
    assert pyright_client._initialized

    pyright_client.shutdown()

    assert not pyright_client._initialized
    assert pyright_client._server_process is None
    assert len(pyright_client._hover_cache) == 0


def test_multiple_files(pyright_client, tmp_path):
    """Test LSP client can handle multiple files"""
    # Create file 1
    file1 = tmp_path / "file1.py"
    file1.write_text("def func1() -> int:\n    return 42\n")

    # Create file 2
    file2 = tmp_path / "file2.py"
    file2.write_text("def func2() -> str:\n    return 'hello'\n")

    # Hover on both files
    hover1 = pyright_client.hover(file1, line=1, col=4)
    hover2 = pyright_client.hover(file2, line=1, col=4)

    assert hover1 is not None
    assert hover2 is not None

    # Check that both documents are opened
    assert file1.as_uri() in pyright_client._opened_documents
    assert file2.as_uri() in pyright_client._opened_documents


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
