"""
CWE-863: Incorrect Authorization (IDOR) - GOOD Example 01
Mitigation: Ownership verification before resource access
"""

from flask import Flask, abort, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


@app.route("/api/documents/<int:doc_id>")
@login_required
def get_document(doc_id):
    """GOOD: Ownership check before document access."""
    from models import Document

    doc = Document.query.get(doc_id)

    if not doc:
        return jsonify({"error": "not found"}), 404

    # SAFE: Verify ownership
    if doc.owner_id != current_user.id:
        abort(403)  # SAFE: Authorization check

    return jsonify({"title": doc.title, "content": doc.content})


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def delete_document(doc_id):
    """GOOD: Authorization check before deletion."""
    from models import Document, db

    doc = Document.query.get(doc_id)

    if not doc:
        return jsonify({"error": "not found"}), 404

    # SAFE: Only owner can delete
    if doc.owner_id != current_user.id:
        abort(403)

    db.session.delete(doc)  # SAFE: Ownership verified
    db.session.commit()

    return jsonify({"status": "deleted"})
