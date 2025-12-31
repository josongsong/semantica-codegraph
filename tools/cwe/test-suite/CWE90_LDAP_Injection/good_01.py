"""
CWE-90: LDAP Injection - GOOD Example 01
Mitigation: Using escape_filter_chars for LDAP escaping
"""

import ldap
from flask import Flask, request
from ldap.filter import escape_filter_chars

app = Flask(__name__)


@app.route("/login", methods=["POST"])
def ldap_login():
    """GOOD: Escaping special characters in LDAP filter."""
    username = request.form.get("username")  # SOURCE
    password = request.form.get("password")  # SOURCE

    conn = ldap.initialize("ldap://localhost:389")
    base_dn = "ou=users,dc=example,dc=com"

    # SAFE: Properly escaped filter values
    safe_user = escape_filter_chars(username)
    safe_pass = escape_filter_chars(password)
    filter_str = f"(&(uid={safe_user})(userPassword={safe_pass}))"
    result = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, filter_str)  # SAFE

    return "Authenticated" if result else "Failed"


@app.route("/search")
def search_user():
    """GOOD: Using escape_filter_chars for search."""
    name = request.args.get("name")  # SOURCE

    conn = ldap.initialize("ldap://localhost:389")
    base_dn = "ou=users,dc=example,dc=com"

    # SAFE: Escaped user input
    safe_name = escape_filter_chars(name)
    filter_str = f"(cn=*{safe_name}*)"
    results = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, filter_str)  # SAFE

    return str([r[1].get("cn", [b""])[0].decode() for r in results])
