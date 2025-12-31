"""CWE-20: Improper Input Validation - GOOD

Safe: Using Pydantic for schema validation.
"""

from typing import Optional

from flask import Flask, jsonify, request
from pydantic import BaseModel, EmailStr, Field, HttpUrl, validator

app = Flask(__name__)


class ItemRequest(BaseModel):
    """Pydantic model for item requests."""

    item_id: int = Field(..., ge=0, le=100)

    @validator("item_id")
    def validate_item_id(cls, v):
        if v < 0:
            raise ValueError("item_id must be non-negative")
        return v


class SubscribeRequest(BaseModel):
    """Pydantic model with email validation."""

    email: EmailStr  # SANITIZER: Built-in email validation
    name: str = Field(..., min_length=1, max_length=100)


class FetchUrlRequest(BaseModel):
    """Pydantic model with URL validation."""

    url: HttpUrl  # SANITIZER: Built-in URL validation


class CalculateRequest(BaseModel):
    """Pydantic model for calculation."""

    a: float
    b: float
    operation: str = Field(..., regex="^(add|subtract|multiply|divide)$")

    @validator("b")
    def validate_divisor(cls, v, values):
        if values.get("operation") == "divide" and v == 0:
            raise ValueError("Cannot divide by zero")
        return v


@app.route("/item", methods=["POST"])
def get_item():
    """GOOD: Pydantic validation."""
    try:
        # SANITIZER: Schema validation
        data = ItemRequest.parse_obj(request.json)
        return jsonify({"item_id": data.item_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/subscribe", methods=["POST"])
def subscribe():
    """GOOD: Email validated by Pydantic."""
    try:
        # SANITIZER: EmailStr validates format
        data = SubscribeRequest.parse_obj(request.json)
        add_subscriber(data.email)
        return jsonify({"status": "subscribed", "email": data.email})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/fetch-url", methods=["POST"])
def fetch_url():
    """GOOD: URL validated by Pydantic."""
    try:
        # SANITIZER: HttpUrl validates URL format
        data = FetchUrlRequest.parse_obj(request.json)

        # Additional: Whitelist allowed domains
        allowed_domains = ["api.example.com", "cdn.example.com"]
        if data.url.host not in allowed_domains:
            return jsonify({"error": "Domain not allowed"}), 400

        # Safe to use
        return jsonify({"url": str(data.url)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/calculate", methods=["POST"])
def calculate():
    """GOOD: Full validation with Pydantic."""
    try:
        data = CalculateRequest.parse_obj(request.json)

        operations = {
            "add": lambda: data.a + data.b,
            "subtract": lambda: data.a - data.b,
            "multiply": lambda: data.a * data.b,
            "divide": lambda: data.a / data.b,
        }

        result = operations[data.operation]()
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def add_subscriber(email: str):
    pass


if __name__ == "__main__":
    app.run()
