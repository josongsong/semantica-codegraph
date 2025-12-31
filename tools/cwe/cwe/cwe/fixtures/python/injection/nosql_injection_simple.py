"""
Simplified NoSQL Injection Fixtures (no external dependencies)

Simulates MongoDB-like query patterns without actual pymongo
"""


def nosql_vulnerable_simple_1(username):
    """
    VULNERABLE: NoSQL authentication bypass simulation

    Attack: username = {"$ne": ""}
    """
    # Simulate MongoDB find_one
    query = {"username": username}  # TAINTED

    result = db_find_one(query)  # SINK: nosql.query
    return result


def nosql_vulnerable_simple_2(filter_dict):
    """
    VULNERABLE: Direct query object injection

    Attack: filter_dict = {"$where": "return true"}
    """
    # VULNERABLE
    results = db_execute(filter_dict)  # SINK: nosql.execute
    return results


def nosql_vulnerable_simple_3(user_id):
    """
    VULNERABLE: Operator injection

    Attack: user_id = {"$gt": 0}
    """
    query = {"_id": user_id}  # TAINTED

    results = collection_find(query)  # SINK: collection.find
    return results


def nosql_safe_simple_1(username):
    """
    SAFE: Type validation
    """
    # SAFE: Validate type
    if not isinstance(username, str):
        raise ValueError("Invalid type")

    clean_query = validate_query({"username": username})
    result = db_find_one(clean_query)
    return result


# Mock helpers (simulating NoSQL operations)


def db_find_one(query):
    """Simulates MongoDB find_one - SINK"""
    # This would execute the query
    return {"_id": 1, "username": "test"}


def db_execute(query):
    """Simulates NoSQL execute - SINK"""
    return [{"result": "data"}]


def collection_find(query):
    """Simulates collection.find - SINK"""
    return [{"_id": i} for i in range(10)]


def validate_query(query):
    """Query sanitizer"""
    # Remove dangerous operators
    if isinstance(query, dict):
        cleaned = {}
        for k, v in query.items():
            if not k.startswith("$"):
                cleaned[k] = v
        return cleaned
    return query
