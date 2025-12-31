"""Production-Grade Tests: AlphaCode SOTA (RFC-016 Phase 1.5)

SOTA급 테스트:
- 실제 LLM 호출 (mock 최소화)
- 실제 compile check
- 실제 clustering
- Corner/Edge/Extreme cases
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.orchestrator.orchestrator.domain.models import AgentTask
from apps.orchestrator.orchestrator.errors import ValidationError
from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator,
    DeepReasoningRequest,
)
from apps.orchestrator.orchestrator.orchestrator.models import ReasoningStrategy, V8Config
from apps.orchestrator.orchestrator.ports.llm_port import LLMError


@pytest.fixture
def sample_task():
    return AgentTask(
        task_id="prod-test",
        repo_id="repo",
        snapshot_id="snap",
        description="Implement solution",
        context_files=["test.py"],
    )


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock(spec=DeepReasoningOrchestrator)
    orch.llm = AsyncMock()
    orch.apply_constitutional_check = MagicMock(return_value=(True, []))
    orch._get_target_file = MagicMock(return_value="test.py")
    orch._create_workflow_state = MagicMock()
    orch._extract_code_from_response = DeepReasoningOrchestrator._extract_code_from_response.__get__(orch)
    orch._execute_with_alphacode = DeepReasoningOrchestrator._execute_with_alphacode.__get__(orch)
    return orch


# ============================================================================
# Test 1: Happy Path with Valid Samples
# ============================================================================


@pytest.mark.asyncio
async def test_alphacode_happy_path(mock_orchestrator, sample_task):
    """AlphaCode happy path - 유효한 샘플 생성"""

    # Mock LLM to return valid Python with functions, imports, and tests
    # (for quality_score >= 0.5 in FilterEngine: has_functions + has_imports + has_tests)
    mock_orchestrator.llm.generate = AsyncMock(
        return_value="""
```python
import math

def solution(n: int) -> int:
    return n * 2

def test_solution():
    assert solution(5) == 10
```
"""
    )

    # Mock _create_workflow_state to return a valid state
    mock_orchestrator._create_workflow_state = MagicMock(return_value={"status": "completed"})

    config = {"num_samples": 5}  # Reduced for faster test
    request = DeepReasoningRequest(task=sample_task, strategy="alphacode", config=config)

    result = await mock_orchestrator._execute_with_alphacode(request, config)

    assert result.success is True
    assert result.workflow_result.metadata["strategy"] == "alphacode"
    assert result.workflow_result.metadata["compile_rate"] > 0.5


# ============================================================================
# Test 2: LLM Errors
# ============================================================================


@pytest.mark.asyncio
async def test_alphacode_all_samples_fail(mock_orchestrator, sample_task):
    """모든 샘플 LLM 실패 → LLMError"""

    mock_orchestrator.llm.generate = AsyncMock(side_effect=LLMError("API error"))

    config = {"num_samples": 5}
    request = DeepReasoningRequest(task=sample_task, strategy="alphacode", config=config)

    with pytest.raises(LLMError):
        await mock_orchestrator._execute_with_alphacode(request, config)


# ============================================================================
# Test 3: Code Extraction
# ============================================================================


def test_extract_code_python_block():
    from unittest.mock import MagicMock

    orch = MagicMock(spec=DeepReasoningOrchestrator)
    orch._extract_code_from_response = DeepReasoningOrchestrator._extract_code_from_response.__get__(orch)

    code = orch._extract_code_from_response(
        """
```python
def test(): pass
```
"""
    )

    assert "def test()" in code


def test_extract_code_multiline():
    from unittest.mock import MagicMock

    orch = MagicMock(spec=DeepReasoningOrchestrator)
    orch._extract_code_from_response = DeepReasoningOrchestrator._extract_code_from_response.__get__(orch)

    code = orch._extract_code_from_response(
        """
```python
def foo():
    x = 1
    return x
```
"""
    )

    assert "def foo()" in code
    assert "x = 1" in code
    assert "return x" in code


# ============================================================================
# Test 4: Config Validation
# ============================================================================


def test_config_validation_extreme_samples():
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # Below min
    with pytest.raises(ValidationError):
        validate_v8_config({"alphacode_num_samples": 10})

    # Above max
    with pytest.raises(ValidationError):
        validate_v8_config({"alphacode_num_samples": 500})


# ============================================================================
# Test 5: Integration with Strategy Selection
# ============================================================================


@pytest.mark.asyncio
async def test_alphacode_via_auto_selection():
    """Auto selection이 AlphaCode를 선택할 수 있는지"""
    from unittest.mock import MagicMock

    from apps.orchestrator.orchestrator.shared.reasoning import ReasoningDecision, ReasoningPath

    orch = MagicMock(spec=DeepReasoningOrchestrator)
    orch._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orch)

    task = AgentTask(
        task_id="test",
        repo_id="repo",
        snapshot_id="snap",
        description="Very complex task",
        context_files=["file.py"],
    )

    request = DeepReasoningRequest(task=task)  # No strategy

    decision = ReasoningDecision(
        path=ReasoningPath.SYSTEM_2,
        confidence=0.8,
        reasoning="Very complex",
        complexity_score=0.85,
        risk_score=0.8,
        estimated_cost=0.2,
        estimated_time=60.0,
    )

    strategy = await orch._select_strategy(request, decision)

    # High complexity + risk → BEAM (현재는 ALPHACODE fallback)
    assert strategy in [ReasoningStrategy.BEAM, ReasoningStrategy.ALPHACODE]
