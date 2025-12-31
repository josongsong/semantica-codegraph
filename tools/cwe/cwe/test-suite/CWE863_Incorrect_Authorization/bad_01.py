"""
CWE-863: Incorrect Authorization (IDOR) - BAD Example 01
Vulnerability: Accessing resources without ownership verification
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


@app.route("/api/documents/<int:doc_id>")
@login_required
def get_document(doc_id):
    """BAD: IDOR - No ownership check on document access."""
    from models import Document

    # SOURCE: User-provided document ID
    doc = Document.query.get(doc_id)  # SINK: No ownership check

    if not doc:
        return jsonify({"error": "not found"}), 404

    return jsonify({"title": doc.title, "content": doc.content})


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def delete_document(doc_id):
    """BAD: Deleting any document without authorization check."""
    from models import Document, db

    # SOURCE: User-provided ID
    doc = Document.query.get(doc_id)  # SINK: No authz check
    if doc:
        db.session.delete(doc)  # SINK: Unauthorized deletion
        db.session.commit()

    return jsonify({"status": "deleted"})
