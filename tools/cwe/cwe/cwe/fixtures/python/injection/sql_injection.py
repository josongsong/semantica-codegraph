"""
SQL Injection Test Fixtures

CWE-89: SQL Injection
CVE-2008-5416: Django SQL Injection
CVE-2014-1932: Python-social-auth SQL Injection
"""

import sqlite3

# Optional imports (install with: pip install codegraph[cwe])
try:
    import mysql.connector

    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

try:
    import psycopg2

    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

try:
    from sqlalchemy import create_engine, text

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

# ==================================================
# VULNERABLE: String concatenation (CVE-2008-5416)
# ==================================================


def sql_injection_vulnerable_1(user_id: str):
    """
    ❌ CRITICAL: Direct string concatenation

    Real attack: user_id = "1 OR 1=1"
    Result: Returns all users
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # VULNERABLE: String concatenation
    query = f"SELECT * FROM users WHERE id={user_id}"
    cursor.execute(query)  # SINK: cursor.execute with tainted SQL

    return cursor.fetchall()


def sql_injection_vulnerable_2(username: str, password: str):
    """
    ❌ CRITICAL: Authentication bypass

    Real attack: username = "admin'--", password = anything
    Result: Bypasses password check
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # VULNERABLE: String interpolation
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)  # SINK

    user = cursor.fetchone()
    return user is not None


def sql_injection_vulnerable_3(search_term: str):
    """
    ❌ CRITICAL: UNION-based SQL injection

    Real attack: search_term = "' UNION SELECT password FROM admin_users--"
    Result: Leaks admin passwords
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # VULNERABLE: % formatting
    query = "SELECT name, email FROM products WHERE name LIKE '%%%s%%'" % search_term
    cursor.execute(query)  # SINK

    return cursor.fetchall()


def sql_injection_vulnerable_4_format(category: str):
    """
    ❌ CRITICAL: .format() method

    Real attack: category = "'; DROP TABLE users--"
    Result: Table deletion
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # VULNERABLE: .format()
    query = f"SELECT * FROM products WHERE category='{category}'"
    cursor.execute(query)  # SINK

    return cursor.fetchall()


def sql_injection_vulnerable_5_psycopg2(email: str):
    """
    ❌ CRITICAL: PostgreSQL injection

    CVE-2014-1932: Real-world PostgreSQL injection
    """
    if not HAS_POSTGRES:
        raise ImportError("psycopg2 not installed. Install with: pip install codegraph[cwe]")

    conn = psycopg2.connect("dbname=test user=postgres")
    cursor = conn.cursor()

    # VULNERABLE
    query = f"SELECT * FROM accounts WHERE email='{email}'"
    cursor.execute(query)  # SINK: psycopg2.cursor.execute

    return cursor.fetchall()


def sql_injection_vulnerable_6_mysql(order_id: str):
    """
    ❌ CRITICAL: MySQL injection
    """
    if not HAS_MYSQL:
        raise ImportError("mysql-connector-python not installed. Install with: pip install codegraph[cwe]")

    conn = mysql.connector.connect(host="localhost", user="root", password="password", database="shop")
    cursor = conn.cursor()

    # VULNERABLE
    cursor.execute(f"SELECT * FROM orders WHERE id={order_id}")  # SINK

    return cursor.fetchall()


def sql_injection_vulnerable_7_sqlalchemy(user_input: str):
    """
    ❌ CRITICAL: SQLAlchemy text() injection
    """
    if not HAS_SQLALCHEMY:
        raise ImportError("sqlalchemy not installed. Install with: pip install codegraph[cwe]")

    engine = create_engine("sqlite:///app.db")
    conn = engine.connect()

    # VULNERABLE: text() with string interpolation
    query = text(f"SELECT * FROM users WHERE name='{user_input}'")
    result = conn.execute(query)  # SINK: Connection.execute

    return result.fetchall()


def sql_injection_vulnerable_8_executemany(user_ids: list):
    """
    ❌ CRITICAL: executemany with bad query
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # VULNERABLE: Even executemany is dangerous with string concat
    query = f"DELETE FROM sessions WHERE user_id IN ({','.join(user_ids)})"
    cursor.execute(query)  # SINK

    conn.commit()


# ==================================================
# SAFE: Parameterized queries (BEST PRACTICE)
# ==================================================


def sql_injection_safe_1_parameterized(user_id: str):
    """
    ✅ SECURE: Parameterized query (sqlite3)

    The database driver handles escaping automatically.
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # SAFE: ? placeholder
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))

    return cursor.fetchall()


def sql_injection_safe_2_named_params(username: str, password: str):
    """
    ✅ SECURE: Named parameters
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # SAFE: Named placeholders
    cursor.execute("SELECT * FROM users WHERE username=:user AND password=:pass", {"user": username, "pass": password})

    return cursor.fetchone()


def sql_injection_safe_3_psycopg2(email: str):
    """
    ✅ SECURE: PostgreSQL parameterized query
    """
    conn = psycopg2.connect("dbname=test user=postgres")
    cursor = conn.cursor()

    # SAFE: %s placeholder (not % formatting!)
    cursor.execute("SELECT * FROM accounts WHERE email=%s", (email,))

    return cursor.fetchall()


def sql_injection_safe_4_mysql(order_id: str):
    """
    ✅ SECURE: MySQL parameterized query
    """
    conn = mysql.connector.connect(host="localhost", user="root", password="password", database="shop")
    cursor = conn.cursor()

    # SAFE: %s placeholder
    cursor.execute("SELECT * FROM orders WHERE id=%s", (order_id,))

    return cursor.fetchall()


def sql_injection_safe_5_sqlalchemy(user_input: str):
    """
    ✅ SECURE: SQLAlchemy bound parameters
    """
    engine = create_engine("sqlite:///app.db")
    conn = engine.connect()

    # SAFE: Bound parameters
    query = text("SELECT * FROM users WHERE name=:name")
    result = conn.execute(query, {"name": user_input})

    return result.fetchall()


def sql_injection_safe_6_executemany(user_ids: list):
    """
    ✅ SECURE: executemany with parameters
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # SAFE: Use placeholders
    placeholders = ",".join("?" * len(user_ids))
    query = f"DELETE FROM sessions WHERE user_id IN ({placeholders})"
    cursor.execute(query, user_ids)

    conn.commit()


# ==================================================
# SAFE: ORM methods (RECOMMENDED)
# ==================================================


def sql_injection_safe_7_orm_filter(user_id: str):
    """
    ✅ SECURE: Using ORM (e.g., SQLAlchemy ORM)

    ORM methods handle parameterization automatically.
    """
    from models import User  # Hypothetical
    from sqlalchemy.orm import Session

    session = Session()

    # SAFE: ORM filter
    user = session.query(User).filter(User.id == user_id).first()

    return user


def sql_injection_safe_8_django_orm(username: str):
    """
    ✅ SECURE: Django ORM
    """
    from django.contrib.auth.models import User

    # SAFE: Django ORM methods
    users = User.objects.filter(username=username)

    return list(users)


# ==================================================
# EDGE CASES: Still vulnerable patterns
# ==================================================


def sql_injection_edge_case_1_orm_raw(user_input: str):
    """
    ⚠️ VULNERABLE: ORM raw() with string interpolation

    Even ORMs can be vulnerable if you use raw SQL incorrectly!
    """
    from django.contrib.auth.models import User

    # VULNERABLE: raw() with f-string
    users = User.objects.raw(f"SELECT * FROM auth_user WHERE username='{user_input}'")

    return list(users)


def sql_injection_edge_case_2_orm_extra(sort_column: str):
    """
    ⚠️ VULNERABLE: ORM extra() with user input

    Django's extra() can be dangerous with unvalidated input.
    """
    from django.contrib.auth.models import User

    # VULNERABLE: ORDER BY injection
    users = User.objects.extra(order_by=[sort_column])

    return list(users)


# ==================================================
# Input validation (Defense in depth)
# ==================================================


def sql_injection_safe_9_validated(user_id: str):
    """
    ✅ SECURE: Input validation + parameterized query

    Defense in depth: Validate input AND use safe SQL practices.
    """
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # Validate input (defense in depth)
    if not user_id.isdigit():
        raise ValueError("Invalid user ID")

    # SAFE: Parameterized query
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))

    return cursor.fetchall()
