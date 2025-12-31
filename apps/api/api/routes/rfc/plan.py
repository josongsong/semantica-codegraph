"""RFC Plan API - POST /rfc/plan"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from codegraph_runtime.llm_arbitration.application.plan_executor import PlanExecutor

router = APIRouter()  # No prefix (set by parent)


class PlanRequest(BaseModel):
    """Plan request body"""

    intent: str
    context: dict[str, Any] | None = None


class PlanResponse(BaseModel):
    """Plan response"""

    spec: dict[str, Any]
    reasoning: str
    confidence: float


@router.post("/plan", response_model=PlanResponse)
async def plan(request: PlanRequest) -> PlanResponse:
    """
    사용자 Intent → RFC Spec 생성 (Planning).

    ## Request Body
    ```json
    {
      "intent": "Find SQL injection vulnerabilities in my API",
      "context": {
        "repo_id": "repo:123",
        "snapshot_id": "snap:456"
      }
    }
    ```

    ## Response
    ```json
    {
      "spec": {
        "intent": "analyze",
        "template_id": "sql_injection",
        "scope": {
          "repo_id": "repo:123",
          "snapshot_id": "snap:456"
        },
        "limits": {
          "max_paths": 200,
          "timeout_ms": 30000
        }
      },
      "reasoning": "Detected security analysis request for SQL injection",
      "confidence": 0.9
    }
    ```

    ## Usage
    1. Call `/plan` to convert natural language → Spec
    2. Review generated spec
    3. Call `/execute` with the spec
    """
    try:
        executor = PlanExecutor()
        result = await executor.plan(request.intent, request.context)

        return PlanResponse(
            spec=result["spec"],
            reasoning=result["reasoning"],
            confidence=result["confidence"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(e)}")
