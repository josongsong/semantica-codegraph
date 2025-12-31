"""RFC Execute API - POST /rfc/execute"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from codegraph_runtime.llm_arbitration.application import ExecuteExecutor
from codegraph_engine.shared_kernel.contracts import ResultEnvelope

router = APIRouter()  # No prefix (set by parent)


class ExecuteRequest(BaseModel):
    """Execute request body"""

    spec: dict[str, Any]


class ExecuteResponse(BaseModel):
    """Execute response (ResultEnvelope)"""

    request_id: str
    summary: str
    claims: list[dict[str, Any]]
    evidences: list[dict[str, Any]]
    conclusion: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    escalation: dict[str, Any] | None = None
    replay_ref: str | None = None
    legacy_result: dict[str, Any] | None = None


@router.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    """
    RFC Spec 실행 → ResultEnvelope 반환.

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
    ResultEnvelope with claims, evidences, conclusion.
    """
    try:
        executor = ExecuteExecutor()
        envelope = await executor.execute(request.spec)

        # ResultEnvelope → dict 변환
        return ExecuteResponse(
            request_id=envelope.request_id,
            summary=envelope.summary,
            claims=[_claim_to_dict(c) for c in envelope.claims],
            evidences=[_evidence_to_dict(e) for e in envelope.evidences],
            conclusion=_conclusion_to_dict(envelope.conclusion) if envelope.conclusion else None,
            metrics=_metrics_to_dict(envelope.metrics) if envelope.metrics else None,
            escalation=_escalation_to_dict(envelope.escalation) if envelope.escalation else None,
            replay_ref=envelope.replay_ref,
            legacy_result=envelope.legacy_result,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


def _claim_to_dict(claim: Any) -> dict[str, Any]:
    """Claim → dict"""
    return {
        "id": claim.id,
        "type": claim.type,
        "severity": claim.severity,
        "confidence": claim.confidence,
        "confidence_basis": claim.confidence_basis.value,
        "proof_obligation": {
            "assumptions": claim.proof_obligation.assumptions,
            "broken_if": claim.proof_obligation.broken_if,
            "unknowns": claim.proof_obligation.unknowns,
        },
        "suppressed": claim.suppressed,
        "suppression_reason": claim.suppression_reason,
    }


def _evidence_to_dict(evidence: Any) -> dict[str, Any]:
    """Evidence → dict"""
    return {
        "id": evidence.id,
        "kind": evidence.kind.value,
        "location": {
            "file_path": evidence.location.file_path,
            "start_line": evidence.location.start_line,
            "end_line": evidence.location.end_line,
            "start_col": evidence.location.start_col,
            "end_col": evidence.location.end_col,
        },
        "content": evidence.content,
        "provenance": {
            "engine": evidence.provenance.engine,
            "template": evidence.provenance.template,
            "snapshot_id": evidence.provenance.snapshot_id,
            "version": evidence.provenance.version,
            "timestamp": evidence.provenance.timestamp,
        },
        "claim_ids": evidence.claim_ids,
    }


def _conclusion_to_dict(conclusion: Any) -> dict[str, Any]:
    """Conclusion → dict"""
    return {
        "reasoning_summary": conclusion.reasoning_summary,
        "coverage": conclusion.coverage,
        "counterevidence": conclusion.counterevidence,
        "recommendation": conclusion.recommendation,
    }


def _metrics_to_dict(metrics: Any) -> dict[str, Any]:
    """Metrics → dict"""
    return {
        "execution_time_ms": metrics.execution_time_ms,
        "paths_analyzed": metrics.paths_analyzed,
        "claims_generated": metrics.claims_generated,
        "claims_suppressed": metrics.claims_suppressed,
        "metadata": metrics.metadata,
    }


def _escalation_to_dict(escalation: Any) -> dict[str, Any]:
    """Escalation → dict"""
    return {
        "required": escalation.required,
        "reason": escalation.reason,
        "decision_needed": escalation.decision_needed,
        "options": escalation.options,
        "resume_token": escalation.resume_token,
    }
