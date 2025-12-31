"""CWE-639: IDOR - BAD"""


def get_user():
    user_id = input("User ID: ")
    # BAD: direct object reference
    user = User.objects.get(id=user_id)
    return user
