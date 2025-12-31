"""CWE-89: SQL Injection - GOOD (Input validation, no SQL)"""


def validate_search_term() -> str:
    """Validate search input - no SQL operations"""
    raw_input = input("Search: ")

    # GOOD: Strict validation (no SQL query at all)
    if not raw_input.isalnum():
        raise ValueError("Invalid search term")

    if len(raw_input) > 100:
        raise ValueError("Search term too long")

    return raw_input
