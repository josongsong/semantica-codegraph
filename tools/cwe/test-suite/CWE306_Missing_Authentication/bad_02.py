"""
CWE-306: Missing Authentication for Critical Function - BAD Example 02
Vulnerability: Data export and bulk operations without auth
"""

import io

from flask import Flask, request, send_file

app = Flask(__name__)


@app.route("/api/export/all_users")
def export_all_users():
    """BAD: Exporting all user data without authentication."""
    # SOURCE: Critical data access
    from models import User

    users = User.query.all()  # SINK: No auth for sensitive data export

    data = "\n".join([f"{u.email},{u.name}" for u in users])
    return send_file(io.BytesIO(data.encode()), mimetype="text/csv", as_attachment=True)


@app.route("/api/bulk/delete", methods=["POST"])
def bulk_delete():
    """BAD: Bulk delete without authentication."""
    ids = request.json.get("ids", [])  # SOURCE

    from models import Item

    Item.query.filter(Item.id.in_(ids)).delete()  # SINK: No auth
    return {"deleted": len(ids)}
