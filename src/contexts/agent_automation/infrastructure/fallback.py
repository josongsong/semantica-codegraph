"""
Fallback mechanisms for agent modes when LLM is not available.

Provides rule-based implementations that can work without LLM for basic functionality.
"""

import re

from src.common.observability import get_logger

logger = get_logger(__name__)


class SimpleLLMFallback:
    """
    Simple rule-based fallback when LLM is not available.

    Provides basic functionality using templates and pattern matching
    instead of LLM generation.
    """

    @staticmethod
    def generate_implementation(query: str, file_path: str = "generated.py") -> str:
        """
        Generate basic implementation code using templates.

        Args:
            query: Implementation query
            file_path: Target file path

        Returns:
            Generated code string
        """
        # Extract function/class name from query
        name = SimpleLLMFallback._extract_name(query)

        # Determine what to generate based on keywords
        if "class" in query.lower():
            return SimpleLLMFallback._generate_class(name, query)
        elif "function" in query.lower() or "def" in query.lower():
            return SimpleLLMFallback._generate_function(name, query)
        else:
            # Default to function
            return SimpleLLMFallback._generate_function(name, query)

    @staticmethod
    def generate_fix(error_type: str, error_message: str, code_context: str = "") -> str:
        """
        Generate basic fix suggestions using pattern matching.

        Args:
            error_type: Type of error (e.g., "NameError", "TypeError")
            error_message: Error message
            code_context: Surrounding code context

        Returns:
            Fix suggestion code
        """
        if "NameError" in error_type:
            # Extract undefined name
            match = re.search(r"name '(\w+)' is not defined", error_message)
            if match:
                name = match.group(1)
                return f"# Fix: Define {name}\n{name} = None  # TODO: Initialize properly\n"

        elif "TypeError" in error_type:
            if "missing" in error_message and "required positional argument" in error_message:
                return (
                    "# Fix: Add missing argument to function call\n"
                    "# Check function signature and provide required arguments\n"
                )

        elif "AttributeError" in error_type:
            match = re.search(r"'(\w+)' object has no attribute '(\w+)'", error_message)
            if match:
                obj_type, attr = match.groups()
                return (
                    f"# Fix: Add missing attribute\n"
                    f"# Check if {obj_type} should have {attr} or use correct attribute name\n"
                )

        elif "ImportError" in error_type or "ModuleNotFoundError" in error_type:
            match = re.search(r"No module named '(\w+)'", error_message)
            if match:
                module = match.group(1)
                return f"# Fix: Install missing module\n# Run: pip install {module}\n"

        # Generic fix
        return (
            f"# Fix for {error_type}\n"
            f"# Error: {error_message}\n"
            "# Review and correct the code based on the error message\n"
        )

    @staticmethod
    def generate_test(function_name: str, code: str = "") -> str:
        """
        Generate basic test code using templates.

        Args:
            function_name: Name of function/class to test
            code: Source code to test

        Returns:
            Generated test code
        """
        test_name = f"test_{function_name}"

        # Determine if it's a class or function
        if code and "class " in code:
            return f"""def {test_name}():
    \"\"\"Test {function_name} class.\"\"\"
    # Arrange
    instance = {function_name}()

    # Act
    # TODO: Call methods on instance

    # Assert
    assert instance is not None
"""
        else:
            return f"""def {test_name}():
    \"\"\"Test {function_name} function.\"\"\"
    # Arrange
    # TODO: Setup test data

    # Act
    result = {function_name}()

    # Assert
    assert result is not None
"""

    @staticmethod
    def generate_docstring(code: str, name: str = "") -> str:
        """
        Generate basic docstring using templates.

        Args:
            code: Source code
            name: Function/class name

        Returns:
            Code with added docstring
        """
        # Find function/class definition
        lines = code.split("\n")
        result_lines = []

        for i, line in enumerate(lines):
            result_lines.append(line)

            # Check if this is a function/class definition
            if line.strip().startswith("def ") or line.strip().startswith("class "):
                # Extract name if not provided
                if not name:
                    match = re.match(r"\s*(?:def|class)\s+(\w+)", line)
                    if match:
                        name = match.group(1)

                # Check if next line is already a docstring
                if i + 1 < len(lines) and lines[i + 1].strip().startswith(('"""', "'''")):
                    continue

                # Add basic docstring
                indent = " " * (len(line) - len(line.lstrip()))
                inner = f"{indent}    "
                if line.strip().startswith("def "):
                    docstring = (
                        f'{inner}"""\n{inner}{name} function.\n{inner}\n'
                        f'{inner}TODO: Add detailed description\n{inner}"""\n'
                    )
                else:
                    docstring = (
                        f'{inner}"""\n{inner}{name} class.\n{inner}\n'
                        f'{inner}TODO: Add detailed description\n{inner}"""\n'
                    )

                result_lines.append(docstring)

        return "\n".join(result_lines)

    @staticmethod
    def _extract_name(query: str) -> str:
        """Extract function/class name from query."""
        # Look for common patterns
        patterns = [
            r"create (\w+)",
            r"implement (\w+)",
            r"add (\w+)",
            r"generate (\w+)",
            r"(\w+) class",
            r"(\w+) function",
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)

        # Default name
        return "generated_function"

    @staticmethod
    def _generate_function(name: str, query: str) -> str:
        """Generate a function template."""
        # Check if async is mentioned
        is_async = "async" in query.lower()

        async_prefix = "async " if is_async else ""
        # Note: await_prefix could be used in more complex implementations
        _ = "await " if is_async else ""  # Reserved for future use

        return f"""{async_prefix}def {name}(*args, **kwargs):
    \"\"\"
    {name} - Generated from query: {query[:80]}

    TODO: Implement function logic
    \"\"\"
    # Implementation needed
    pass
"""

    @staticmethod
    def _generate_class(name: str, query: str) -> str:
        """Generate a class template."""
        return f"""class {name}:
    \"\"\"
    {name} - Generated from query: {query[:80]}

    TODO: Implement class logic
    \"\"\"

    def __init__(self):
        \"\"\"Initialize {name}.\"\"\"
        pass

    def __repr__(self):
        \"\"\"String representation.\"\"\"
        return f"{name}()"
"""


class FallbackRegistry:
    """
    Registry of fallback mechanisms for different agent modes.

    Allows modes to gracefully degrade when LLM is not available.
    """

    _fallbacks = {
        "implementation": SimpleLLMFallback.generate_implementation,
        "debug": SimpleLLMFallback.generate_fix,
        "test": SimpleLLMFallback.generate_test,
        "documentation": SimpleLLMFallback.generate_docstring,
    }

    @classmethod
    def get_fallback(cls, mode: str):
        """Get fallback function for a mode."""
        return cls._fallbacks.get(mode)

    @classmethod
    def register_fallback(cls, mode: str, fallback_fn):
        """Register a custom fallback for a mode."""
        cls._fallbacks[mode] = fallback_fn
        logger.info(f"Registered fallback for mode: {mode}")
