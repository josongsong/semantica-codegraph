"""
Integration Tests for CLI Error Handling

Validates that error.details are properly output to stderr in CLI.
"""

import subprocess
import sys
from pathlib import Path

import pytest


class TestCLIErrorOutput:
    """CLI에서 error.details가 제대로 출력되는지 검증"""

    def test_validation_error_shows_details_in_stderr(self):
        """ValidationError details가 stderr에 출력되는지 확인"""
        # Create test script that triggers ValidationError
        test_script = """
import sys
sys.path.insert(0, '/Users/songmin/Documents/code-jo/semantica-v2/codegraph')

from apps.orchestrator.orchestrator.orchestrator.models import V8Config, validate_v8_config

# Invalid config
config: V8Config = {"max_iterations": -1}

try:
    validate_v8_config(config)
except Exception as e:
    # Simulate CLI error handling
    print(f"❌ Validation error: {e.message}", file=sys.stderr)
    if hasattr(e, 'details') and e.details:
        print(f"   Details: {e.details}", file=sys.stderr)
    sys.exit(22)
"""

        result = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True)

        # Verify
        assert result.returncode == 22
        assert "Validation error" in result.stderr
        assert "Details:" in result.stderr
        assert "field" in result.stderr
        assert "max_iterations" in result.stderr
        assert "value" in result.stderr
        assert "-1" in result.stderr

    def test_fallback_error_shows_both_errors_in_stderr(self):
        """FallbackError에서 v8_error + v7_error 모두 출력되는지 확인"""
        test_script = """
import sys
sys.path.insert(0, '/Users/songmin/Documents/code-jo/semantica-v2/codegraph')

from apps.orchestrator.orchestrator.errors import FallbackError

error = FallbackError(
    "All orchestrators failed",
    {"v8_error": "LLM timeout", "v7_error": "Config missing"}
)

# Simulate CLI handling
print(f"❌ Critical: All orchestrators failed", file=sys.stderr)
print(f"   {error.message}", file=sys.stderr)
if error.details:
    print(f"   Errors: {error.details}", file=sys.stderr)
sys.exit(1)
"""

        result = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True)

        assert result.returncode == 1
        assert "Critical" in result.stderr
        assert "Errors:" in result.stderr
        assert "v8_error" in result.stderr
        assert "v7_error" in result.stderr
        assert "LLM timeout" in result.stderr
        assert "Config missing" in result.stderr

    def test_error_http_status_code_accessible(self):
        """Error의 http_status_code가 CLI에서 접근 가능한지"""
        test_script = """
import sys
sys.path.insert(0, '/Users/songmin/Documents/code-jo/semantica-v2/codegraph')

from apps.orchestrator.orchestrator.errors import ValidationError, FallbackError, TimeoutError

# Test different errors
v_error = ValidationError("Test")
print(f"ValidationError: {v_error.http_status_code}", file=sys.stderr)

f_error = FallbackError("Test")
print(f"FallbackError: {f_error.http_status_code}", file=sys.stderr)

t_error = TimeoutError("Test")
print(f"TimeoutError: {t_error.http_status_code}", file=sys.stderr)
"""

        result = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True)

        assert "ValidationError: 422" in result.stderr
        assert "FallbackError: 503" in result.stderr
        assert "TimeoutError: 504" in result.stderr


class TestCLIValidationIntegration:
    """CLI와 Validation의 실제 통합 테스트"""

    def test_v8_config_validation_in_request(self):
        """DeepReasoningRequest 생성 시 validation이 실제로 동작하는지"""
        test_script = """
import sys
sys.path.insert(0, '/Users/songmin/Documents/code-jo/semantica-v2/codegraph')

from apps.orchestrator.orchestrator.orchestrator import DeepReasoningRequest
from apps.orchestrator.orchestrator.orchestrator.models import V8Config
from apps.orchestrator.orchestrator.domain.models import AgentTask

task = AgentTask(
    task_id="test",
    repo_id=".",
    snapshot_id="s",
    description="test"
)

# Invalid config
config: V8Config = {"temperature": 3.0}  # ❌ Max is 2.0

try:
    request = DeepReasoningRequest(task=task, config=config)
    print("FAIL: Should have raised ValidationError", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    if "temperature" in str(e):
        print(f"SUCCESS: Validation caught temperature error", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"FAIL: Wrong error: {e}", file=sys.stderr)
        sys.exit(1)
"""

        result = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True)

        assert result.returncode == 0
        assert "SUCCESS" in result.stderr
        assert "Validation caught temperature error" in result.stderr

    def test_v8_response_validation_integration(self):
        """DeepReasoningResponse 생성 시 validation이 실제로 동작하는지"""
        test_script = """
import sys
sys.path.insert(0, '/Users/songmin/Documents/code-jo/semantica-v2/codegraph')

from apps.orchestrator.orchestrator.orchestrator import DeepReasoningResponse
from apps.orchestrator.orchestrator.domain.models import AgentTask, WorkflowResult, WorkflowState, WorkflowStepType
from apps.orchestrator.orchestrator.domain.reasoning import ReasoningDecision, ReasoningPath

task = AgentTask(task_id="t", repo_id=".", snapshot_id="s", description="t")
final_state = WorkflowState(task=task, current_step=WorkflowStepType.TEST)
result = WorkflowResult(
    success=True,
    final_state=final_state,
    total_iterations=1,
    total_time_seconds=1.0,
    changes=[],
    test_results=[]
)
decision = ReasoningDecision(
    path=ReasoningPath.SYSTEM_1,
    confidence=0.9,
    reasoning="test",
    complexity_score=0.3,
    risk_score=0.2,
    estimated_cost=0.01,
    estimated_time=1.0
)

try:
    # Invalid: negative execution_time_ms
    response = DeepReasoningResponse(
        success=True,
        workflow_result=result,
        reasoning_decision=decision,
        execution_time_ms=-100.0  # ❌ Negative!
    )
    print("FAIL: Should have raised ValidationError", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    if "execution_time_ms" in str(e):
        print(f"SUCCESS: Validation caught negative execution_time_ms", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"FAIL: Wrong error: {e}", file=sys.stderr)
        sys.exit(1)
"""

        result = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True)

        assert result.returncode == 0
        assert "SUCCESS" in result.stderr
        assert "Validation caught negative execution_time_ms" in result.stderr
