"""CWE-89: SQL Injection - GOOD (Input validation only, no SQL)"""


def get_user_id() -> str:
    """Get and validate user ID - no SQL operations"""
    user_input = input("User ID: ")

    # GOOD: Validate input (no SQL query at all)
    if not user_input.isdigit():
        raise ValueError("Invalid user ID")

    return user_input
