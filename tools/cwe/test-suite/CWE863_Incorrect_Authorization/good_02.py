"""
CWE-863: Incorrect Authorization (IDOR) - GOOD Example 02
Mitigation: Query filtering by owner
"""

from flask import Flask, abort, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


@app.route("/api/accounts/<int:account_id>/balance")
@login_required
def get_balance(account_id):
    """GOOD: Query filtered by owner."""
    from models import Account

    # SAFE: Query includes ownership constraint
    account = Account.query.filter_by(id=account_id, owner_id=current_user.id).first()  # SAFE: Ownership in query

    if not account:
        return jsonify({"error": "not found or unauthorized"}), 404

    return jsonify({"balance": float(account.balance)})


@app.route("/api/accounts/<int:account_id>/transfer", methods=["POST"])
@login_required
def transfer_money(account_id):
    """GOOD: Verify ownership before transfer."""
    from models import Account, db

    amount = float(request.json.get("amount", 0))
    to_account_id = request.json.get("to_account")

    # SAFE: Only get accounts owned by current user
    from_account = Account.query.filter_by(
        id=account_id, owner_id=current_user.id
    ).first_or_404()  # SAFE: Ownership verified

    to_account = Account.query.get_or_404(to_account_id)

    if amount <= 0 or from_account.balance < amount:
        return jsonify({"error": "invalid amount"}), 400

    from_account.balance -= amount
    to_account.balance += amount
    db.session.commit()

    return jsonify({"status": "transferred"})
