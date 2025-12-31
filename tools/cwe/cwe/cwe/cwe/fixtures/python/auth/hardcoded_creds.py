"""
Hardcoded Credentials Fixtures

CWE-798: Use of Hard-coded Credentials
CVE-2019-10092: Apache hardcoded password
CVE-2020-8813: Cacti default credentials
"""

import os

# ===================================================
# VULNERABLE: Hardcoded passwords (CWE-798)
# ===================================================


def connect_to_database_vulnerable():
    """
    ❌ CRITICAL: Hardcoded database password

    CWE-798: Anyone with access to code can see credentials.
    """
    password = "admin123"
    db_connection = f"mysql://root:{password}@localhost/mydb"
    return db_connection


def api_client_vulnerable():
    """
    ❌ CRITICAL: Hardcoded API key

    CVE-2019-10092: Hardcoded credentials allow unauthorized access.
    """
    API_KEY = "sk-1234567890abcdef"
    return {"Authorization": f"Bearer {API_KEY}"}


def default_credentials_vulnerable():
    """
    ❌ CRITICAL: Default admin credentials

    CVE-2020-8813: Default credentials not changed.
    """
    username = "admin"
    password = "admin"
    return (username, password)


# ===================================================
# SECURE: Environment-based credentials
# ===================================================


def connect_to_database_secure():
    """
    ✅ SECURE: Credentials from environment
    """
    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise ValueError("DB_PASSWORD not set")
    db_connection = f"mysql://root:{password}@localhost/mydb"
    return db_connection


def api_client_secure():
    """
    ✅ SECURE: API key from config/secrets manager
    """
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY not configured")
    return {"Authorization": f"Bearer {api_key}"}
