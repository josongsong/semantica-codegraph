"""
Input Validation Test Fixtures

CWE-20: Improper Input Validation
CVE-2020-8554: Kubernetes input validation bypass
CVE-2021-22901: curl input validation vulnerability
"""

import re
from typing import Any

# ==================================================
# VULNERABLE: No validation
# ==================================================


def input_validation_vulnerable_1(user_input: str):
    """
    ❌ HIGH: No input validation

    Real attack: user_input = "<script>alert(1)</script>"
    """
    # VULNERABLE: No validation
    return process_data(user_input)  # SINK


def input_validation_vulnerable_2(age: str):
    """
    ❌ HIGH: Type confusion

    Real attack: age = "999999999999999999999"
    """
    # VULNERABLE: No type/range validation
    age_int = int(age)  # Can overflow or cause issues

    return age_int


def input_validation_vulnerable_3(email: str):
    """
    ❌ HIGH: Weak email validation
    """
    # VULNERABLE: Weak regex
    if "@" in email:
        return save_email(email)

    raise ValueError("Invalid email")


# ==================================================
# VULNERABLE: Client-side validation only
# ==================================================


def input_validation_vulnerable_4(price: str):
    """
    ❌ HIGH: Trusting client-side validation

    Client sends: price = "0.01" (bypassing frontend check)
    """
    # VULNERABLE: No server-side validation
    price_float = float(price)

    return create_order(price_float)


# ==================================================
# VULNERABLE: Integer overflow
# ==================================================


def input_validation_vulnerable_5(quantity: str):
    """
    ❌ HIGH: Integer overflow

    Real attack: quantity = "2147483648" (INT_MAX + 1)
    """
    # VULNERABLE: No range check
    qty = int(quantity)

    total = qty * 100  # Can overflow

    return total


# ==================================================
# VULNERABLE: Format string
# ==================================================


def input_validation_vulnerable_6(template: str):
    """
    ❌ CRITICAL: Format string vulnerability
    """
    # VULNERABLE: User-controlled format string
    message = template.format(user="admin")

    return message


# ==================================================
# SAFE: Type validation
# ==================================================


def input_validation_safe_1_type_check(age: Any):
    """
    ✅ SECURE: Type and range validation
    """
    # SAFE: Type check
    if not isinstance(age, (int, str)):
        raise TypeError("Invalid type")

    # Convert and validate
    try:
        age_int = int(age)
    except ValueError:
        raise ValueError("Invalid age format")

    # Range check
    if not (0 <= age_int <= 150):
        raise ValueError("Age out of range")

    return age_int


def input_validation_safe_2_string_length(username: str):
    """
    ✅ SECURE: String length validation
    """
    # SAFE: Length check
    if not isinstance(username, str):
        raise TypeError("Username must be string")

    if not (3 <= len(username) <= 32):
        raise ValueError("Username length must be 3-32 chars")

    # Character validation
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise ValueError("Invalid characters in username")

    return username


# ==================================================
# SAFE: Regex validation
# ==================================================


def input_validation_safe_3_email(email: str):
    """
    ✅ SECURE: Email validation with regex
    """
    # SAFE: Proper email regex
    EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not isinstance(email, str):
        raise TypeError("Email must be string")

    if len(email) > 254:  # RFC 5321
        raise ValueError("Email too long")

    if not re.match(EMAIL_REGEX, email):
        raise ValueError("Invalid email format")

    return email.lower()


def input_validation_safe_4_url(url: str):
    """
    ✅ SECURE: URL validation
    """
    from urllib.parse import urlparse

    # SAFE: Parse and validate
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL")

    # Validate scheme
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL scheme")

    # Validate hostname
    if not parsed.hostname:
        raise ValueError("Missing hostname")

    return url


# ==================================================
# SAFE: Numeric validation
# ==================================================


def input_validation_safe_5_price(price: str):
    """
    ✅ SECURE: Price validation
    """
    # SAFE: Decimal validation
    try:
        from decimal import Decimal, InvalidOperation

        price_decimal = Decimal(price)
    except InvalidOperation:
        raise ValueError("Invalid price format")

    # Range check
    if not (Decimal("0.01") <= price_decimal <= Decimal("999999.99")):
        raise ValueError("Price out of range")

    # Precision check (max 2 decimal places)
    if price_decimal.as_tuple().exponent < -2:
        raise ValueError("Too many decimal places")

    return price_decimal


def input_validation_safe_6_quantity(quantity: str):
    """
    ✅ SECURE: Quantity validation
    """
    # SAFE: Integer with range
    try:
        qty = int(quantity)
    except ValueError:
        raise ValueError("Invalid quantity")

    # Range check (prevent overflow)
    if not (1 <= qty <= 10000):
        raise ValueError("Quantity must be 1-10000")

    return qty


# ==================================================
# SAFE: Allowlist validation
# ==================================================


def input_validation_safe_7_enum(status: str):
    """
    ✅ SECURE: Enum/allowlist validation
    """
    # SAFE: Allowlist
    ALLOWED_STATUSES = {"pending", "approved", "rejected"}

    if status not in ALLOWED_STATUSES:
        raise ValueError("Invalid status")

    return status


def input_validation_safe_8_country_code(code: str):
    """
    ✅ SECURE: Country code validation
    """
    # SAFE: ISO 3166-1 alpha-2
    if not isinstance(code, str):
        raise TypeError("Country code must be string")

    if len(code) != 2:
        raise ValueError("Country code must be 2 chars")

    if not code.isupper():
        raise ValueError("Country code must be uppercase")

    # Additional: check against ISO list
    try:
        import pycountry
    except ImportError:
        raise ImportError("pycountry not installed. Install with: pip install codegraph[cwe]")

    try:
        pycountry.countries.get(alpha_2=code)
    except KeyError:
        raise ValueError("Invalid country code")

    return code


# ==================================================
# SAFE: Date/time validation
# ==================================================


def input_validation_safe_9_date(date_str: str):
    """
    ✅ SECURE: Date validation
    """
    from datetime import datetime

    # SAFE: Parse with specific format
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid date format (use YYYY-MM-DD)")

    # Range check
    from datetime import date as date_type

    today = date_type.today()

    if not (date_type(1900, 1, 1) <= date.date() <= today):
        raise ValueError("Date out of range")

    return date


def input_validation_safe_10_timestamp(ts: str):
    """
    ✅ SECURE: Timestamp validation
    """
    # SAFE: Unix timestamp
    try:
        ts_int = int(ts)
    except ValueError:
        raise ValueError("Invalid timestamp")

    # Range check (reasonable range)
    MIN_TS = 0  # 1970-01-01
    MAX_TS = 2147483647  # 2038-01-19 (32-bit limit)

    if not (MIN_TS <= ts_int <= MAX_TS):
        raise ValueError("Timestamp out of range")

    return ts_int


# ==================================================
# SAFE: File validation
# ==================================================


def input_validation_safe_11_filename(filename: str):
    """
    ✅ SECURE: Filename validation
    """
    # SAFE: Strict filename validation
    if not isinstance(filename, str):
        raise TypeError("Filename must be string")

    if len(filename) > 255:
        raise ValueError("Filename too long")

    # No path separators
    if "/" in filename or "\\" in filename:
        raise ValueError("Path separators not allowed")

    # No hidden files
    if filename.startswith("."):
        raise ValueError("Hidden files not allowed")

    # Alphanumeric + safe chars only
    if not re.match(r"^[a-zA-Z0-9_.-]+$", filename):
        raise ValueError("Invalid filename characters")

    return filename


# ==================================================
# SAFE: JSON validation
# ==================================================


def input_validation_safe_12_json_schema(data: dict):
    """
    ✅ SECURE: JSON schema validation
    """
    try:
        import jsonschema
    except ImportError:
        raise ImportError("jsonschema not installed. Install with: pip install codegraph[cwe]")

    # Define schema
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 100},
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
            "email": {"type": "string", "format": "email"},
        },
        "required": ["name", "age", "email"],
        "additionalProperties": False,
    }

    # SAFE: Validate against schema
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Invalid data: {e.message}")

    return data


# ==================================================
# SAFE: Pydantic validation
# ==================================================


def input_validation_safe_13_pydantic():
    """
    ✅ SECURE: Pydantic model validation
    """
    from pydantic import BaseModel, EmailStr, conint, constr, validator

    class UserInput(BaseModel):
        username: constr(min_length=3, max_length=32, regex=r"^[a-zA-Z0-9_-]+$")
        email: EmailStr
        age: conint(ge=0, le=150)

        @validator("username")
        def username_no_admin(cls, v):
            if "admin" in v.lower():
                raise ValueError('Username cannot contain "admin"')
            return v

    # SAFE: Pydantic validates automatically
    def create_user(data: dict):
        user = UserInput(**data)  # Raises ValidationError if invalid
        return user


# ==================================================
# Helper functions
# ==================================================


def process_data(data: Any):
    """Mock processor"""
    return f"Processed: {data}"


def save_email(email: str):
    """Mock save"""
    return f"Saved: {email}"


def create_order(price: float):
    """Mock order"""
    return f"Order: ${price}"
