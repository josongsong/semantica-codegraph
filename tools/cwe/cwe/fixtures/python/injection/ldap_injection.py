"""
LDAP Injection Test Fixtures

Real-world LDAP injection vulnerabilities
Based on authentication bypass patterns
"""

import ldap


def ldap_injection_vulnerable_1(username):
    """
    VULNERABLE: LDAP authentication bypass

    Real attack: username = "admin)(&(objectClass=*"
    Result: Bypasses password check
    """
    conn = ldap.initialize("ldap://localhost")

    # VULNERABLE: Unsanitized username
    search_filter = f"(&(uid={username})(objectClass=person))"

    results = conn.search_s("dc=example,dc=com", ldap.SCOPE_SUBTREE, search_filter)  # SINK: ldap.search_s

    return results


def ldap_injection_vulnerable_2(username, password):
    """
    VULNERABLE: LDAP login bypass

    Real attack: username = "*)(uid=*))(|(uid=*"
    Result: Returns all users, bypasses authentication
    """
    conn = ldap.initialize("ldap://localhost")

    # VULNERABLE
    filter_str = f"(&(uid={username})(userPassword={password}))"

    users = conn.search_st(  # SINK: ldap.search_st
        "ou=users,dc=example,dc=com", ldap.SCOPE_ONELEVEL, filter_str, timeout=10
    )

    return len(users) > 0


def ldap_injection_vulnerable_3(search_term):
    """
    VULNERABLE: LDAP search injection

    Real attack: search_term = "*)(&(password=*"
    Result: Leaks password hashes
    """
    conn = ldap.initialize("ldap://localhost")

    # VULNERABLE
    search_filter = f"(cn={search_term}*)"

    results = conn.search("dc=example,dc=com", ldap.SCOPE_SUBTREE, search_filter)  # SINK: ldap.search

    return results


def ldap_injection_safe_1(username):
    """
    SAFE: LDAP filter escaping
    """
    conn = ldap.initialize("ldap://localhost")

    # SAFE: Escaped
    safe_username = escape_ldap(username)
    search_filter = f"(&(uid={safe_username})(objectClass=person))"

    results = conn.search_s("dc=example,dc=com", ldap.SCOPE_SUBTREE, search_filter)

    return results


def ldap_injection_safe_2(username):
    """
    SAFE: Using LDAP filter chars sanitizer
    """
    conn = ldap.initialize("ldap://localhost")

    # SAFE: Sanitized
    clean = escape_filter_chars(username)
    search_filter = f"(uid={clean})"

    results = conn.search_s("dc=example,dc=com", ldap.SCOPE_SUBTREE, search_filter)

    return results


# Helpers


def escape_ldap(value):
    """
    LDAP filter escape

    Escapes special LDAP filter characters
    """
    escape_chars = {
        "*": "\\2a",
        "(": "\\28",
        ")": "\\29",
        "\\": "\\5c",
        "\x00": "\\00",
    }

    for char, escaped in escape_chars.items():
        value = value.replace(char, escaped)

    return value


def escape_filter_chars(value):
    """LDAP filter character sanitizer"""
    dangerous = ["*", "(", ")", "\\", "&", "|", "!"]
    for char in dangerous:
        value = value.replace(char, "")
    return value
