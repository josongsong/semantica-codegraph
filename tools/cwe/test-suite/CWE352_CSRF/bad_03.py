"""CWE-352: Cross-Site Request Forgery - BAD

Vulnerable: Django view without CSRF middleware.
"""

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt  # BAD: Explicitly disabling CSRF protection
def update_password(request: HttpRequest) -> HttpResponse:
    """BAD: CSRF protection explicitly disabled."""
    if request.method == "POST":
        old_password = request.POST.get("old_password")  # SOURCE
        new_password = request.POST.get("new_password")  # SOURCE

        user = request.user
        if user.check_password(old_password):
            user.set_password(new_password)  # SINK: password change
            user.save()  # VULNERABILITY: No CSRF protection
            return HttpResponse("Password updated")

    return HttpResponse("Invalid request", status=400)


@csrf_exempt  # BAD: API endpoint but accepting browser requests
def api_transfer(request: HttpRequest) -> HttpResponse:
    """BAD: API without proper authentication, CSRF disabled."""
    if request.method == "POST":
        import json

        data = json.loads(request.body)  # SOURCE
        amount = data["amount"]
        to_user = data["to_user"]

        # SINK: Money transfer without CSRF
        from_user = request.user
        transfer_money(from_user, to_user, amount)  # VULNERABILITY

        return HttpResponse("Transfer complete")

    return HttpResponse("Method not allowed", status=405)


def transfer_money(from_user, to_user, amount):
    """Mock transfer function."""
    pass
