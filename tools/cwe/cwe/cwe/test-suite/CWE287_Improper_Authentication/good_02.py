"""CWE-287: Improper Authentication - GOOD

Safe: Using Django's built-in authentication.
"""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def login_view(request: HttpRequest) -> HttpResponse:
    """GOOD: Using Django's authenticate() function."""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        # SANITIZER: Django's authenticate handles password verification
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Safe: Only login after proper authentication
            login(request, user)
            return redirect("dashboard")
        else:
            return HttpResponse("Invalid credentials", status=401)

    return HttpResponse(
        """
        <form method="POST">
            <input name="username" type="text">
            <input name="password" type="password">
            <button type="submit">Login</button>
        </form>
    """
    )


def api_login_view(request: HttpRequest) -> HttpResponse:
    """GOOD: API authentication with Django."""
    import json

    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        # SANITIZER: Proper authentication
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return HttpResponse(json.dumps({"status": "success", "user_id": user.id}), content_type="application/json")

        return HttpResponse(json.dumps({"error": "Invalid credentials"}), status=401, content_type="application/json")

    return HttpResponse("Method not allowed", status=405)


@login_required
def protected_view(request: HttpRequest) -> HttpResponse:
    """GOOD: Protected by login_required decorator."""
    return HttpResponse(f"Welcome, {request.user.username}!")
