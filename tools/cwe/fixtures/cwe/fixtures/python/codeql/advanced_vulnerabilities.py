"""CodeQL: Advanced Real-world Vulnerabilities"""

import pickle
import re
import xml.etree.ElementTree as ET
from typing import Any

# ============================================================
# ReDoS (Regular Expression Denial of Service)
# ============================================================


def redos_vulnerable(user_input: str) -> bool:
    """ReDoS - exponential backtracking - VULNERABLE"""
    # VULNERABLE: Catastrophic backtracking
    pattern = r"^(a+)+$"
    return bool(re.match(pattern, user_input))


def redos_vulnerable_email(email: str) -> bool:
    """ReDoS in email validation - VULNERABLE"""
    # VULNERABLE: Nested quantifiers
    pattern = r"^([a-zA-Z0-9]+)*@([a-zA-Z0-9]+)*\.com$"
    return bool(re.match(pattern, email))


def redos_safe(user_input: str) -> bool:
    """ReDoS - safe pattern - SAFE"""
    # SAFE: Linear time complexity
    pattern = r"^a+$"
    return bool(re.match(pattern, user_input))


# ============================================================
# Second-order SQL Injection
# ============================================================


class SecondOrderSQLInjection:
    """Second-order SQL injection - data stored then used"""

    def store_user_data(self, username: str, db):
        """Store user input - VULNERABLE if used later"""
        # First query - parameterized (safe)
        cursor = db.cursor()
        cursor.execute("INSERT INTO users (name) VALUES (?)", (username,))
        db.commit()

    def retrieve_and_use_vulnerable(self, user_id: int, db):
        """Second query - uses stored data unsafely - VULNERABLE"""
        cursor = db.cursor()

        # Retrieve data
        cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        username = cursor.fetchone()[0]

        # VULNERABLE: Use retrieved data without sanitization
        query = f"SELECT * FROM posts WHERE author = '{username}'"
        cursor.execute(query)
        return cursor.fetchall()

    def retrieve_and_use_safe(self, user_id: int, db):
        """Second query - safe - SAFE"""
        cursor = db.cursor()

        cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        username = cursor.fetchone()[0]

        # SAFE: Parameterized even for stored data
        cursor.execute("SELECT * FROM posts WHERE author = ?", (username,))
        return cursor.fetchall()


# ============================================================
# XXE (XML External Entity) Injection
# ============================================================


def xxe_vulnerable(xml_data: str) -> dict:
    """XXE - unsafe XML parsing - VULNERABLE"""
    # VULNERABLE: Default parser allows external entities
    tree = ET.fromstring(xml_data)
    return {"data": tree.text}


def xxe_safe(xml_data: str) -> dict:
    """XXE - safe XML parsing - SAFE"""
    # SAFE: Disable external entity resolution
    parser = ET.XMLParser()
    parser.entity = {}  # Disable entities
    tree = ET.fromstring(xml_data, parser=parser)
    return {"data": tree.text}


# ============================================================
# Insecure Deserialization (Advanced)
# ============================================================


class DeserializationVulnerability:
    """Advanced deserialization attacks"""

    @staticmethod
    def pickle_vulnerable(data: bytes) -> Any:
        """Pickle deserialization - VULNERABLE"""
        # VULNERABLE: Can execute arbitrary code
        return pickle.loads(data)

    @staticmethod
    def eval_vulnerable(code_str: str) -> Any:
        """Eval injection - VULNERABLE"""
        # VULNERABLE: Arbitrary code execution
        return eval(code_str)

    @staticmethod
    def exec_vulnerable(code_str: str):
        """Exec injection - VULNERABLE"""
        # VULNERABLE: Arbitrary code execution
        exec(code_str)

    @staticmethod
    def safe_deserialize(data: dict) -> dict:
        """Safe deserialization - SAFE"""
        # SAFE: Only accept whitelisted keys
        allowed_keys = {"name", "age", "email"}
        return {k: v for k, v in data.items() if k in allowed_keys}


# ============================================================
# Template Injection
# ============================================================


def template_injection_vulnerable(user_input: str) -> str:
    """Template injection - VULNERABLE"""
    # VULNERABLE: User input in template
    template = f"Hello {user_input}!"
    return eval(f'f"""{template}"""')


def template_injection_jinja_vulnerable(user_input: str) -> str:
    """Jinja2 SSTI - VULNERABLE"""
    from jinja2 import Template

    # VULNERABLE: User controls template
    template = Template(user_input)
    return template.render()


def template_safe(user_input: str) -> str:
    """Template - safe - SAFE"""
    # SAFE: Escape user input
    import html

    escaped = html.escape(user_input)
    return f"Hello {escaped}!"


# ============================================================
# Time-of-Check to Time-of-Use (TOCTOU)
# ============================================================

import os
import time


def toctou_vulnerable(filename: str):
    """TOCTOU race condition - VULNERABLE"""
    # VULNERABLE: File can change between check and use
    if os.path.exists(filename):
        # Race condition window here
        time.sleep(0.001)
        with open(filename) as f:
            return f.read()


def toctou_safe(filename: str):
    """TOCTOU - safe - SAFE"""
    # SAFE: Try to open directly, handle exception
    try:
        with open(filename) as f:
            return f.read()
    except FileNotFoundError:
        return None


# ============================================================
# Open Redirect
# ============================================================


def open_redirect_vulnerable(redirect_url: str):
    """Open redirect - VULNERABLE"""
    # VULNERABLE: No URL validation
    return f"Location: {redirect_url}"


def open_redirect_safe(redirect_url: str, allowed_domains: list):
    """Open redirect - safe - SAFE"""
    from urllib.parse import urlparse

    # SAFE: Validate domain
    parsed = urlparse(redirect_url)
    if parsed.hostname in allowed_domains:
        return f"Location: {redirect_url}"
    else:
        raise ValueError("Untrusted redirect")


# ============================================================
# LDAP Injection
# ============================================================


def ldap_injection_vulnerable(username: str) -> str:
    """LDAP injection - VULNERABLE"""
    # VULNERABLE: Direct string concatenation
    ldap_query = f"(&(uid={username})(objectClass=person))"
    return ldap_query


def ldap_injection_safe(username: str) -> str:
    """LDAP injection - safe - SAFE"""

    # SAFE: Escape LDAP special characters
    def escape_ldap(s: str) -> str:
        replacements = {"\\": "\\5c", "*": "\\2a", "(": "\\28", ")": "\\29", "\x00": "\\00"}
        for char, escaped in replacements.items():
            s = s.replace(char, escaped)
        return s

    escaped_username = escape_ldap(username)
    return f"(&(uid={escaped_username})(objectClass=person))"


# ============================================================
# JWT Vulnerabilities
# ============================================================

import base64
import json


class JWTVulnerabilities:
    """JWT security issues"""

    @staticmethod
    def none_algorithm_vulnerable(token: str) -> dict:
        """JWT 'none' algorithm - VULNERABLE"""
        # VULNERABLE: Accepts 'none' algorithm
        parts = token.split(".")
        payload = base64.b64decode(parts[1] + "==")
        return json.loads(payload)

    @staticmethod
    def algorithm_confusion_vulnerable(token: str, public_key: str) -> dict:
        """JWT algorithm confusion - VULNERABLE"""
        # VULNERABLE: Using public key as HMAC secret
        import hmac

        parts = token.split(".")
        signature = parts[2]

        # Algorithm confusion: RS256 -> HS256
        expected = hmac.new(public_key.encode(), f"{parts[0]}.{parts[1]}".encode(), "sha256").digest()

        if base64.b64encode(expected).decode() == signature:
            payload = base64.b64decode(parts[1] + "==")
            return json.loads(payload)


# ============================================================
# Integer Overflow/Underflow
# ============================================================


def integer_overflow_vulnerable(user_input: int) -> int:
    """Integer overflow - VULNERABLE"""
    # VULNERABLE: No bounds checking
    result = user_input * 1000000
    return result


def integer_overflow_safe(user_input: int, max_value: int = 2**31 - 1) -> int:
    """Integer overflow - safe - SAFE"""
    # SAFE: Check bounds before operation
    if user_input > max_value // 1000000:
        raise ValueError("Would overflow")
    return user_input * 1000000


# ============================================================
# Null Pointer Dereference
# ============================================================


def null_dereference_vulnerable(data: dict) -> str:
    """Null dereference - VULNERABLE"""
    # VULNERABLE: No null check
    user = data.get("user")
    return user["name"]  # Crashes if user is None


def null_dereference_safe(data: dict) -> str:
    """Null dereference - safe - SAFE"""
    # SAFE: Check before access
    user = data.get("user")
    if user is None:
        return "Unknown"
    return user.get("name", "Unknown")
