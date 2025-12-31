"""CWE-352: Cross-Site Request Forgery - BAD

Vulnerable: POST endpoint without CSRF protection.
"""

from flask import Flask, redirect, request

app = Flask(__name__)


class Account:
    def __init__(self, balance: float):
        self.balance = balance

    def transfer(self, amount: float, to_account: "Account"):
        self.balance -= amount
        to_account.balance += amount


@app.route("/transfer", methods=["POST"])
def transfer_money():
    """BAD: No CSRF token validation."""
    amount = float(request.form["amount"])  # SOURCE: user input
    to_account_id = request.form["to_account"]

    # SINK: State change without CSRF protection
    from_account = get_account(request.cookies.get("user_id"))
    to_account = get_account(to_account_id)
    from_account.transfer(amount, to_account)  # VULNERABILITY: CSRF

    return redirect("/success")


def get_account(account_id: str) -> Account:
    # Mock implementation
    return Account(1000.0)


if __name__ == "__main__":
    app.run()
