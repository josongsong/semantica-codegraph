"""CWE-639: IDOR - GOOD"""


def get_user_safe():
    user_id = input("User ID: ")
    # GOOD: authorization check
    if check_permission(user_id):
        user = User.objects.get(id=user_id)
        return user
