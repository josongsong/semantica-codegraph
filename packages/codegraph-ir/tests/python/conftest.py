#!/usr/bin/env python3
"""Pytest configuration and shared fixtures for Python integration tests."""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Callable, List, Tuple

import pytest


# Add codegraph packages to path
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages/codegraph-engine"))
sys.path.insert(0, str(REPO_ROOT / "packages/codegraph-shared"))


@pytest.fixture
def temp_repo() -> Callable[[dict], Tuple[str, List[str]]]:
    """Fixture factory for creating temporary repositories.

    Returns:
        A function that creates a temp repo from a dict of {filename: content}.

    Example:
        >>> temp_repo_factory = temp_repo
        >>> repo_path, filenames = temp_repo_factory({
        ...     "main.py": "def hello(): pass"
        ... })
    """
    created_repos = []

    def _create_temp_repo(files: dict) -> Tuple[str, List[str]]:
        """Create a temporary repository with given files.

        Args:
            files: Dict mapping filename to file content

        Returns:
            Tuple of (repo_path, list of filenames)
        """
        tmpdir = tempfile.mkdtemp(prefix="codegraph_test_")
        created_repos.append(tmpdir)

        for filename, content in files.items():
            filepath = os.path.join(tmpdir, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                f.write(content)

        return tmpdir, list(files.keys())

    yield _create_temp_repo

    # Cleanup
    for repo_path in created_repos:
        shutil.rmtree(repo_path, ignore_errors=True)


@pytest.fixture
def simple_python_repo(temp_repo) -> Tuple[str, List[str]]:
    """Create a simple Python repository for testing.

    Contains:
    - module_a.py: A simple module with functions and a class
    - module_b.py: Module that imports from module_a
    - utils.py: Utility functions
    """
    files = {
        "module_a.py": '''
"""Module A - Example module"""

def hello(name: str) -> str:
    """Say hello"""
    return f"Hello, {name}!"

class Greeter:
    """A greeter class"""
    def __init__(self, greeting: str):
        self.greeting = greeting

    def greet(self, name: str) -> str:
        return f"{self.greeting}, {name}!"
''',
        "module_b.py": '''
"""Module B - Imports from A"""
from module_a import hello, Greeter

def main():
    """Main function"""
    message = hello("World")
    print(message)

    greeter = Greeter("Hi")
    result = greeter.greet("Alice")
    print(result)

if __name__ == "__main__":
    main()
''',
        "utils.py": '''
"""Utility functions"""

def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b

def factorial(n: int) -> int:
    """Calculate factorial"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)
''',
    }
    return temp_repo(files)


@pytest.fixture
def security_test_repo(temp_repo) -> Tuple[str, List[str]]:
    """Create a repository with security vulnerability patterns.

    Contains:
    - auth.py: Authentication module with potential SQL injection
    - api.py: API handlers with data flow
    - utils.py: Utility functions including Calculator class
    """
    files = {
        "auth.py": '''
"""Authentication module"""

def sanitize_input(user_input: str) -> str:
    """Sanitize user input"""
    return user_input.strip().lower()

def validate_credentials(username: str, password: str) -> bool:
    """Validate user credentials"""
    # Source: user input
    clean_username = sanitize_input(username)
    clean_password = sanitize_input(password)

    # Sink: database query (potential SQL injection)
    query = f"SELECT * FROM users WHERE username='{clean_username}' AND password='{clean_password}'"
    return execute_query(query)

def execute_query(query: str):
    """Execute SQL query"""
    # Sink point - potential vulnerability
    pass
''',
        "api.py": '''
"""API handlers"""
from auth import validate_credentials

def login_handler(request):
    """Handle login request"""
    # Source: HTTP request
    username = request.get("username")
    password = request.get("password")

    # Data flow: request -> validate_credentials -> execute_query
    if validate_credentials(username, password):
        return {"status": "success"}
    return {"status": "failed"}

def register_handler(request):
    """Handle registration"""
    username = request.get("username")
    email = request.get("email")

    user_data = create_user(username, email)
    return user_data

def create_user(username: str, email: str):
    """Create new user"""
    return {"username": username, "email": email}
''',
        "utils.py": '''
"""Utility functions"""

class Calculator:
    """Mathematical calculator"""

    def __init__(self):
        self.result = 0

    def add(self, x: int, y: int) -> int:
        """Add two numbers"""
        self.result = x + y
        return self.result

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers"""
        self.result = x * y
        return self.result

def factorial(n: int) -> int:
    """Calculate factorial recursively"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n: int) -> int:
    """Calculate fibonacci"""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
''',
    }
    return temp_repo(files)


@pytest.fixture
def codegraph_engine_path() -> Path:
    """Return path to codegraph-engine package for testing."""
    path = REPO_ROOT / "packages/codegraph-engine"
    if not path.exists():
        pytest.skip(f"codegraph-engine not found at {path}")
    return path


@pytest.fixture
def codegraph_ir_path() -> Path:
    """Return path to codegraph-ir package for testing."""
    path = REPO_ROOT / "packages/codegraph-rust/codegraph-ir"
    if not path.exists():
        pytest.skip(f"codegraph-ir not found at {path}")
    return path


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "benchmark: mark test as a performance benchmark")
    config.addinivalue_line("markers", "slow: mark test as slow (> 5 seconds)")
    config.addinivalue_line("markers", "integration: mark test as integration test")


# Performance assertion helpers
class PerformanceAssertion:
    """Helper for asserting performance metrics."""

    @staticmethod
    def assert_indexing_time(elapsed_ms: float, max_ms: float, loc: int):
        """Assert indexing time is within limits.

        Args:
            elapsed_ms: Actual elapsed time in milliseconds
            max_ms: Maximum allowed time in milliseconds
            loc: Lines of code processed
        """
        assert elapsed_ms < max_ms, f"Indexing should complete in < {max_ms}ms for {loc} LOC, got {elapsed_ms:.2f}ms"

    @staticmethod
    def assert_query_time(elapsed_ms: float, max_ms: float):
        """Assert query time is within limits.

        Args:
            elapsed_ms: Actual elapsed time in milliseconds
            max_ms: Maximum allowed time in milliseconds
        """
        assert elapsed_ms < max_ms, f"Query should complete in < {max_ms}ms, got {elapsed_ms:.3f}ms"

    @staticmethod
    def assert_conversion_rate(nodes: int, elapsed_ms: float, min_rate: int):
        """Assert conversion rate meets minimum threshold.

        Args:
            nodes: Number of nodes converted
            elapsed_ms: Time taken in milliseconds
            min_rate: Minimum conversion rate (nodes/sec)
        """
        rate = nodes / (elapsed_ms / 1000)
        assert rate >= min_rate, (
            f"Conversion rate should be >= {min_rate:,} nodes/s, "
            f"got {rate:,.0f} nodes/s ({elapsed_ms:.2f}ms for {nodes:,} nodes)"
        )


@pytest.fixture
def perf() -> PerformanceAssertion:
    """Provide performance assertion helpers."""
    return PerformanceAssertion()
