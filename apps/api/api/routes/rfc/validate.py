"""RFC Validate API - POST /rfc/validate"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from codegraph_runtime.llm_arbitration.application import ValidateExecutor

router = APIRouter()  # No prefix (set by parent)


class ValidateRequest(BaseModel):
    """Validate request body"""

    spec: dict[str, Any]


class ValidateResponse(BaseModel):
    """Validate response"""

    valid: bool
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []


class ValidationErrorResponse(BaseModel):
    """Validation error response (400)"""

    error_code: str
    message: str
    hint_schema: dict[str, Any] = {}
    suggested_fixes: list[dict[str, str]] = []


@router.post("/validate", response_model=ValidateResponse)
async def validate(request: ValidateRequest) -> ValidateResponse:
    """
    RFC Spec 유효성 검증.

    ## Request Body
    ```json
    {
      "spec": {
        "intent": "analyze",
        "template_id": "sql_injection",
        "scope": {
          "repo_id": "repo:123",
          "snapshot_id": "snap:456"
        },
        "params": {},
        "limits": {
          "max_paths": 200,
          "timeout_ms": 30000
        }
      }
    }
    ```

    ## Response
    ```json
    {
      "valid": true,
      "errors": [],
      "warnings": []
    }
    ```

    ## Error Response (400)
    ```json
    {
      "error_code": "MISSING_INTENT",
      "message": "'intent' field is required",
      "hint_schema": {
        "required_fields": ["intent"],
        "valid_intents": ["retrieve", "analyze", "edit"]
      },
      "suggested_fixes": [
        {
          "field": "intent",
          "suggestion": "Add 'intent' field"
        }
      ]
    }
    ```
    """
    try:
        executor = ValidateExecutor()
        result = executor.validate_spec(request.spec)

        # Invalid spec → 400 error with structured details
        if not result["valid"] and result.get("error_code"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": result["error_code"],
                    "message": result["errors"][0]["message"] if result["errors"] else "Validation failed",
                    "hint_schema": result.get("hint_schema", {}),
                    "suggested_fixes": result.get("suggested_fixes", []),
                },
            )

        return ValidateResponse(
            valid=result["valid"],
            errors=result.get("errors", []),
            warnings=result.get("warnings", []),
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")
