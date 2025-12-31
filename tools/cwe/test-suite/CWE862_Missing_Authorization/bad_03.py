"""CWE-862: Missing Authorization - BAD

Vulnerable: Django view missing authorization for sensitive operations.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404


class Account:
    """Mock Account model."""

    def __init__(self, id: int, user_id: int, balance: float):
        self.id = id
        self.user_id = user_id
        self.balance = balance

    @classmethod
    def objects_get(cls, **kwargs):
        return cls(kwargs.get("id", 1), 1, 1000.0)

    def save(self):
        pass


class Transaction:
    """Mock Transaction model."""

    def __init__(self, id: int, account_id: int, amount: float):
        self.id = id
        self.account_id = account_id
        self.amount = amount

    @classmethod
    def objects_filter(cls, **kwargs):
        return [cls(1, kwargs.get("account_id", 1), 100.0)]


@login_required
def view_account(request: HttpRequest, account_id: int) -> JsonResponse:
    """BAD: Can view any account without ownership check."""
    # SOURCE: account_id from URL
    # SINK: Direct account access
    account = Account.objects_get(id=account_id)  # VULNERABILITY

    return JsonResponse({"id": account.id, "balance": account.balance})


@login_required
def view_transactions(request: HttpRequest, account_id: int) -> JsonResponse:
    """BAD: Can view any account's transactions."""
    # SOURCE: account_id from URL
    # SINK: Access to sensitive financial data
    transactions = Transaction.objects_filter(account_id=account_id)  # VULNERABILITY: No ownership check

    return JsonResponse({"transactions": [{"id": t.id, "amount": t.amount} for t in transactions]})


@login_required
def transfer_money(request: HttpRequest) -> JsonResponse:
    """BAD: Can transfer from any account."""
    from_account_id = request.POST.get("from_account")  # SOURCE
    to_account_id = request.POST.get("to_account")
    amount = float(request.POST.get("amount"))

    # SINK: Modify any account without authorization
    from_account = Account.objects_get(id=from_account_id)  # VULNERABILITY
    to_account = Account.objects_get(id=to_account_id)

    from_account.balance -= amount
    to_account.balance += amount
    from_account.save()  # VULNERABILITY: No ownership check
    to_account.save()

    return JsonResponse({"status": "success"})
