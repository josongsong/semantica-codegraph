"""
CWE-90: LDAP Injection - GOOD Example 02
Mitigation: Input validation and ldap3 escaping
"""

import re

from flask import Flask, request
from ldap3 import ALL, Connection, Server
from ldap3.utils.conv import escape_filter_chars

app = Flask(__name__)


def validate_username(username: str) -> bool:
    """Validate username format."""
    return bool(re.match(r"^[a-zA-Z0-9._-]+$", username))


@app.route("/auth", methods=["POST"])
def authenticate():
    """GOOD: Validation and escaping for ldap3."""
    username = request.form.get("user")  # SOURCE
    password = request.form.get("pass")  # SOURCE

    # SAFE: Input validation first
    if not validate_username(username):
        return "Invalid username format", 400

    server = Server("ldap://localhost", get_info=ALL)
    conn = Connection(server, auto_bind=True)

    base_dn = "ou=users,dc=company,dc=com"
    # SAFE: Escaped values
    safe_user = escape_filter_chars(username)
    safe_pass = escape_filter_chars(password)
    search_filter = f"(&(uid={safe_user})(userPassword={safe_pass}))"
    conn.search(base_dn, search_filter)  # SAFE

    return "OK" if conn.entries else "Denied"


@app.route("/lookup")
def lookup_by_email():
    """GOOD: Email validation and escaping."""
    email = request.args.get("email")  # SOURCE

    # SAFE: Validate email format
    if not re.match(r"^[\w.+-]+@[\w.-]+\.\w+$", email):
        return "Invalid email", 400

    server = Server("ldap://localhost")
    conn = Connection(server, auto_bind=True)

    # SAFE: Escaped email
    safe_email = escape_filter_chars(email)
    filter_str = f"(mail={safe_email})"
    conn.search("dc=example,dc=com", filter_str, attributes=["cn", "mail"])  # SAFE

    return str([entry.cn.value for entry in conn.entries])
