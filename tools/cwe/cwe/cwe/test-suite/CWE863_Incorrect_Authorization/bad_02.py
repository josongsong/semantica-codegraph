"""
CWE-863: Incorrect Authorization (IDOR) - BAD Example 02
Vulnerability: Horizontal privilege escalation
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


@app.route("/api/accounts/<int:account_id>/balance")
@login_required
def get_balance(account_id):
    """BAD: Viewing any account balance without ownership check."""
    from models import Account

    # SOURCE: User-provided account ID
    account = Account.query.get(account_id)  # SINK: No authorization

    if not account:
        return jsonify({"error": "not found"}), 404

    # SINK: Exposing other users' financial data
    return jsonify({"balance": float(account.balance)})


@app.route("/api/accounts/<int:account_id>/transfer", methods=["POST"])
@login_required
def transfer_money(account_id):
    """BAD: Transferring from any account."""
    from models import Account, db

    amount = float(request.json.get("amount", 0))
    to_account_id = request.json.get("to_account")

    # SOURCE: User provides source account
    from_account = Account.query.get(account_id)  # SINK: No ownership check
    to_account = Account.query.get(to_account_id)

    # SINK: Unauthorized money transfer
    from_account.balance -= amount
    to_account.balance += amount
    db.session.commit()

    return jsonify({"status": "transferred"})
