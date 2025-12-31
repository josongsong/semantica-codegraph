"""CWE-352: Cross-Site Request Forgery - GOOD

Safe: Django view with built-in CSRF protection.
"""

from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_protect


@csrf_protect  # GOOD: CSRF protection decorator
def update_password(request: HttpRequest) -> HttpResponse:
    """GOOD: Protected by Django CSRF middleware."""
    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")

        user = request.user
        if user.check_password(old_password):
            user.set_password(new_password)
            user.save()  # Safe: CSRF protected
            return HttpResponse("Password updated")

    return HttpResponse("Invalid request", status=400)


def transfer_view(request: HttpRequest) -> HttpResponse:
    """GOOD: Django middleware automatically protects POST.

    With CsrfViewMiddleware enabled in settings.MIDDLEWARE,
    all POST requests require valid CSRF token.
    """
    if request.method == "POST":
        amount = request.POST.get("amount")
        to_user = request.POST.get("to_user")

        # Safe: Django CSRF middleware validates token
        from_user = request.user
        transfer_money(from_user, to_user, float(amount))

        return HttpResponse("Transfer complete")

    # Render form with CSRF token
    return HttpResponse(
        """
        <form method="POST">
            {% csrf_token %}
            <input name="amount" type="number">
            <input name="to_user" type="text">
            <button type="submit">Transfer</button>
        </form>
    """
    )


def transfer_money(from_user, to_user, amount):
    """Mock transfer function."""
    pass
