"""RFC Explain API - POST /rfc/explain"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from codegraph_runtime.llm_arbitration.application.explain_executor import ExplainExecutor

router = APIRouter()  # No prefix (set by parent)


class ExplainRequest(BaseModel):
    """Explain request body"""

    request_id: str
    focus: str | None = None  # claim_id or "all"


class ExplainResponse(BaseModel):
    """Explain response"""

    request_id: str
    summary: str
    claim_explanations: list[dict[str, Any]]
    reasoning_trace: str


@router.post("/explain", response_model=ExplainResponse)
async def explain(request: ExplainRequest) -> ExplainResponse:
    """
    ResultEnvelope 설명 생성 (Human-readable).

    ## Request Body
    ```json
    {
      "request_id": "req_abc123",
      "focus": "claim_001"
    }
    ```

    ## Response
    ```json
    {
      "request_id": "req_abc123",
      "summary": "Found 2 SQL injection vulnerabilities",
      "claim_explanations": [
        {
          "claim_id": "claim_001",
          "explanation": "Static taint analysis found...",
          "evidence_count": 3,
          "confidence_basis": "proven"
        }
      ],
      "reasoning_trace": "1. Detected source...\\n2. Traced flow...\\n3. Found sink..."
    }
    ```

    ## Usage
    1. Execute analysis with `/execute`
    2. Get request_id from response
    3. Call `/explain` for detailed explanation
    """
    try:
        executor = ExplainExecutor()
        result = await executor.explain(request.request_id, request.focus)

        return ExplainResponse(
            request_id=result["request_id"],
            summary=result["summary"],
            claim_explanations=result["claim_explanations"],
            reasoning_trace=result["reasoning_trace"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")
