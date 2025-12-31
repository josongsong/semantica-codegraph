"""CodeQL Scenario: Taint Analysis and Data Flow

This module demonstrates taint analysis patterns for vulnerability detection.
Tests source-to-sink data flow tracking.
"""

import os
import subprocess

# ============================================================
# Taint Sources
# ============================================================


def get_user_input():
    """Taint source: user input"""
    return input("Enter value: ")


def get_request_param(request):
    """Taint source: HTTP request parameter"""
    return request.GET.get("param")


def get_cookie_value(request):
    """Taint source: cookie data"""
    return request.COOKIES.get("session")


def read_file_content(path: str):
    """Taint source: file content"""
    with open(path) as f:
        return f.read()


# ============================================================
# Taint Sinks
# ============================================================


def execute_sql(query: str):
    """Sink: SQL execution (SQL Injection)"""
    import sqlite3

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()


def execute_command(cmd: str):
    """Sink: Command execution (Command Injection)"""
    return subprocess.call(cmd, shell=True)


def eval_code(code: str):
    """Sink: Code evaluation (Code Injection)"""
    return eval(code)


def render_html(html: str):
    """Sink: HTML rendering (XSS)"""
    return f"<div>{html}</div>"


def write_file(path: str, content: str):
    """Sink: File write (Path Traversal)"""
    with open(path, "w") as f:
        f.write(content)


# ============================================================
# Vulnerable Functions (Taint Flow)
# ============================================================


def vulnerable_sql_injection(request):
    """SQL Injection: user input -> SQL query"""
    user_id = get_request_param(request)
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return execute_sql(query)


def vulnerable_command_injection():
    """Command Injection: user input -> shell command"""
    filename = get_user_input()
    cmd = f"cat {filename}"
    return execute_command(cmd)


def vulnerable_code_injection(request):
    """Code Injection: request param -> eval()"""
    expr = get_request_param(request)
    return eval_code(expr)


def vulnerable_xss(request):
    """XSS: user input -> HTML rendering"""
    user_comment = get_request_param(request)
    return render_html(user_comment)


def vulnerable_path_traversal(request):
    """Path Traversal: user input -> file path"""
    filename = get_request_param(request)
    path = f"/var/www/uploads/{filename}"
    content = read_file_content(path)
    return content


def vulnerable_complex_flow(request):
    """Complex taint flow with multiple steps"""
    user_input = get_request_param(request)
    processed = transform_data(user_input)
    sanitized = weak_sanitizer(processed)
    return execute_sql(f"SELECT * FROM logs WHERE data = '{sanitized}'")


# ============================================================
# Sanitizers
# ============================================================


def weak_sanitizer(data: str) -> str:
    """Weak sanitization (still vulnerable)"""
    return data.replace("'", "")


def strong_sanitizer(data: str) -> str:
    """Strong sanitization (safe)"""
    import html

    return html.escape(data)


# ============================================================
# Safe Functions (No Taint Flow)
# ============================================================


def safe_sql_query(user_id: int):
    """Safe: parameterized query"""
    import sqlite3

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchall()


def safe_command_execution():
    """Safe: no user input"""
    cmd = ["ls", "-la", "/tmp"]
    return subprocess.run(cmd, capture_output=True)


def safe_html_rendering(request):
    """Safe: sanitized output"""
    user_input = get_request_param(request)
    sanitized = strong_sanitizer(user_input)
    return render_html(sanitized)


# ============================================================
# Helper Functions
# ============================================================


def transform_data(data: str) -> str:
    """Data transformation (propagates taint)"""
    return data.upper()


def log_data(data: str):
    """Logging (potential sink)"""
    print(f"[LOG] {data}")


def validate_input(data: str) -> bool:
    """Validation (does not sanitize)"""
    return len(data) < 100


# ============================================================
# Multi-step Taint Flow
# ============================================================


class UserRequest:
    """Request object with tainted data"""

    def __init__(self, params: dict):
        self.params = params

    def get_param(self, key: str) -> str:
        """Get parameter (taint source)"""
        return self.params.get(key, "")


class Database:
    """Database operations (potential sinks)"""

    def query(self, sql: str):
        """Execute SQL query (sink)"""
        return execute_sql(sql)

    def insert(self, table: str, data: dict):
        """Insert data (sink)"""
        columns = ", ".join(data.keys())
        values = ", ".join(f"'{v}'" for v in data.values())
        sql = f"INSERT INTO {table} ({columns}) VALUES ({values})"
        return self.query(sql)


def complex_taint_scenario():
    """Complex multi-step taint flow"""
    request = UserRequest({"id": "123", "name": "test"})

    # Step 1: Get tainted data
    user_id = request.get_param("id")

    # Step 2: Transform
    transformed = transform_data(user_id)

    # Step 3: Validate (doesn't remove taint)
    if validate_input(transformed):
        # Step 4: Log (potential leak)
        log_data(transformed)

        # Step 5: Use in query (vulnerable)
        db = Database()
        return db.query(f"SELECT * FROM users WHERE id = {transformed}")

    return None


# ============================================================
# Constants for Testing
# ============================================================

SAFE_CONSTANT = "safe_value"
TAINTED_GLOBAL = get_user_input()  # Global tainted variable
