"""
NoSQL Injection Test Fixtures

Real-world NoSQL injection vulnerabilities
Focuses on MongoDB (most common NoSQL DB)
"""

# Optional imports (install with: pip install codegraph[cwe])
try:
    from pymongo import MongoClient

    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

try:
    import redis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


def nosql_injection_vulnerable_1(username, password):
    """
    VULNERABLE: MongoDB authentication bypass

    Real attack: username = {"$ne": null}, password = {"$ne": null}
    Result: Bypasses authentication (matches all users)
    """
    if not HAS_PYMONGO:
        raise ImportError("pymongo not installed. Install with: pip install codegraph[cwe]")

    client = MongoClient()
    db = client.users_db

    # VULNERABLE: Direct dict injection
    user = db.users.find_one(
        {
            "username": username,  # TAINTED
            "password": password,  # TAINTED
        }
    )  # SINK: collection.find_one

    return user is not None


def nosql_injection_vulnerable_2(user_id):
    """
    VULNERABLE: MongoDB operator injection

    Real attack: user_id = {"$gt": ""}
    Result: Returns all users with ID > empty string
    """
    client = MongoClient()
    db = client.app_db

    # VULNERABLE
    results = db.users.find({"_id": user_id})  # SINK: collection.find

    return list(results)


def nosql_injection_vulnerable_3(role):
    """
    VULNERABLE: MongoDB $where injection

    Real attack: role = "admin'; return true; var fake='"
    Result: JavaScript injection in $where clause
    """
    client = MongoClient()
    db = client.app_db

    # VULNERABLE: $where with user input
    query = {"$where": f"this.role == '{role}'"}

    users = db.users.find(query)  # SINK: collection.find with $where
    return list(users)


def nosql_injection_vulnerable_4(category):
    """
    VULNERABLE: MongoDB update injection

    Real attack: category = {"$set": {"admin": true}}
    Result: Privilege escalation
    """
    client = MongoClient()
    db = client.products_db

    # VULNERABLE
    result = db.products.update(
        {"category": category},
        {"$set": {"visible": True}},  # TAINTED
    )  # SINK: collection.update

    return result


def nosql_injection_vulnerable_5(data):
    """
    VULNERABLE: Redis eval injection

    Real attack: data = "return redis.call('FLUSHALL')"
    Result: Deletes all Redis data
    """
    if not HAS_REDIS:
        raise ImportError("redis not installed. Install with: pip install codegraph[cwe]")

    r = redis.Redis()

    # VULNERABLE: eval with user data
    result = r.eval(data)  # SINK: redis.eval

    return result


def nosql_injection_safe_1(username, password):
    """
    SAFE: Type validation
    """
    client = MongoClient()
    db = client.users_db

    # SAFE: Ensure string type
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("Invalid input type")

    user = db.users.find_one(
        {
            "username": username,
            "password": password,
        }
    )

    return user is not None


def nosql_injection_safe_2(user_id):
    """
    SAFE: Sanitized input
    """
    client = MongoClient()
    db = client.app_db

    # SAFE: Sanitize
    clean_id = sanitize_mongo(user_id)

    results = db.users.find({"_id": clean_id})
    return list(results)


# Helpers


def sanitize_mongo(value):
    """MongoDB sanitizer: ensure string type and escape operators"""
    if not isinstance(value, str):
        raise ValueError("Expected string")

    # Remove MongoDB operators
    if value.startswith("$"):
        return value[1:]

    return value
