"""
CWE-90: LDAP Injection - BAD Example 01
Vulnerability: String concatenation in LDAP filters
"""

import ldap
from flask import Flask, request

app = Flask(__name__)


@app.route("/login", methods=["POST"])
def ldap_login():
    """BAD: Direct string formatting in LDAP filter."""
    username = request.form.get("username")  # SOURCE
    password = request.form.get("password")  # SOURCE

    conn = ldap.initialize("ldap://localhost:389")
    base_dn = "ou=users,dc=example,dc=com"

    # SINK: LDAP injection via string formatting
    filter_str = f"(&(uid={username})(userPassword={password}))"
    result = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, filter_str)  # SINK

    return "Authenticated" if result else "Failed"


@app.route("/search")
def search_user():
    """BAD: User input directly in LDAP search."""
    name = request.args.get("name")  # SOURCE

    conn = ldap.initialize("ldap://localhost:389")
    base_dn = "ou=users,dc=example,dc=com"

    # SINK: Vulnerable to injection
    filter_str = f"(cn=*{name}*)"
    results = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, filter_str)  # SINK

    return str([r[1].get("cn", [b""])[0].decode() for r in results])
