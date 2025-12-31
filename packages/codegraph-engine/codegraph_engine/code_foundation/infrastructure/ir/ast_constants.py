"""Language-specific AST node type constants for Tree-sitter."""

# Python
PYTHON_BRANCH_TYPES = {"if_statement"}
PYTHON_LOOP_TYPES = {"for_statement", "while_statement"}
PYTHON_TRY_TYPES = {"try_statement"}

# Java
JAVA_BRANCH_TYPES = {
    "if_statement",
    "switch_expression",
    "switch_statement",
}
JAVA_LOOP_TYPES = {
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
}
JAVA_TRY_TYPES = {
    "try_statement",
    "try_with_resources_statement",
}

# Kotlin
KOTLIN_BRANCH_TYPES = {
    "if_expression",
    "when_expression",
}
KOTLIN_LOOP_TYPES = {
    "for_statement",
    "while_statement",
    "do_while_statement",
}
KOTLIN_TRY_TYPES = {
    "try_expression",
    "catch_block",
    "finally_block",
}


def get_branch_types(language: str) -> set[str]:
    """Get branch types for language."""
    mapping = {
        "python": PYTHON_BRANCH_TYPES,
        "java": JAVA_BRANCH_TYPES,
        "kotlin": KOTLIN_BRANCH_TYPES,
    }
    return mapping.get(language.lower(), set())


def get_loop_types(language: str) -> set[str]:
    """Get loop types for language."""
    mapping = {
        "python": PYTHON_LOOP_TYPES,
        "java": JAVA_LOOP_TYPES,
        "kotlin": KOTLIN_LOOP_TYPES,
    }
    return mapping.get(language.lower(), set())


def get_try_types(language: str) -> set[str]:
    """Get try/catch types for language."""
    mapping = {
        "python": PYTHON_TRY_TYPES,
        "java": JAVA_TRY_TYPES,
        "kotlin": KOTLIN_TRY_TYPES,
    }
    return mapping.get(language.lower(), set())
