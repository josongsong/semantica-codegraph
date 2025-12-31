"""Unit Tests: V8 Strategy Selection (RFC-016 Phase 1)

Tests for:
1. ReasoningStrategy enum
2. V8Config validation (strategy-specific)
3. DeepReasoningRequest validation
4. _select_strategy() logic
5. _get_strategy_config() helper

Rule 3 (Test Code 필수):
- Happy path ✅
- Invalid input ✅
- Boundary cases ✅
- Auto-selection logic ✅
"""

import pytest

from apps.orchestrator.orchestrator.domain.models import AgentTask
from apps.orchestrator.orchestrator.errors import ValidationError
from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator,
    DeepReasoningRequest,
)
from apps.orchestrator.orchestrator.orchestrator.models import ReasoningStrategy, V8Config
from apps.orchestrator.orchestrator.shared.reasoning import ReasoningDecision, ReasoningPath

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_task():
    """샘플 Agent Task"""
    return AgentTask(
        task_id="test-123",
        repo_id="test-repo",
        snapshot_id="snap-001",  # REQUIRED field
        description="Fix bug in user authentication",
        context_files=["src/auth.py"],
        metadata={},
    )


@pytest.fixture
def mock_decision_simple():
    """Simple code decision (System 1)"""
    return ReasoningDecision(
        path=ReasoningPath.SYSTEM_1,
        confidence=0.9,
        reasoning="Simple code",
        complexity_score=0.3,
        risk_score=0.2,
        estimated_cost=0.01,
        estimated_time=5.0,
    )


@pytest.fixture
def mock_decision_complex():
    """Complex code decision (System 2)"""
    return ReasoningDecision(
        path=ReasoningPath.SYSTEM_2,
        confidence=0.85,
        reasoning="Complex code",
        complexity_score=0.85,
        risk_score=0.75,
        estimated_cost=0.15,
        estimated_time=45.0,
    )


# ============================================================================
# Test 1: ReasoningStrategy Enum
# ============================================================================


def test_reasoning_strategy_enum_values():
    """ReasoningStrategy enum이 모든 전략을 포함하는지"""
    assert ReasoningStrategy.AUTO.value == "auto"
    assert ReasoningStrategy.TOT.value == "tot"
    assert ReasoningStrategy.BEAM.value == "beam"
    assert ReasoningStrategy.O1.value == "o1"
    assert ReasoningStrategy.DEBATE.value == "debate"
    assert ReasoningStrategy.ALPHACODE.value == "alphacode"


def test_reasoning_strategy_from_string():
    """String에서 enum 변환"""
    assert ReasoningStrategy("beam") == ReasoningStrategy.BEAM
    assert ReasoningStrategy("o1") == ReasoningStrategy.O1

    with pytest.raises(ValueError):
        ReasoningStrategy("invalid_strategy")


# ============================================================================
# Test 2: V8Config Validation (Strategy-specific)
# ============================================================================


def test_v8config_beam_validation_valid():
    """Beam config validation - happy path"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    config: V8Config = {
        "beam_width": 5,
        "max_depth": 2,
    }

    # Should not raise
    validate_v8_config(config)


def test_v8config_beam_validation_invalid_width():
    """Beam config validation - invalid beam_width"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # Too small
    config: V8Config = {"beam_width": 2}
    with pytest.raises(ValidationError) as exc_info:
        validate_v8_config(config)
    assert "beam_width must be 3-10" in str(exc_info.value)

    # Too large
    config: V8Config = {"beam_width": 11}
    with pytest.raises(ValidationError) as exc_info:
        validate_v8_config(config)
    assert "beam_width must be 3-10" in str(exc_info.value)


def test_v8config_o1_validation_valid():
    """o1 config validation - happy path"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    config: V8Config = {
        "o1_max_attempts": 5,
        "o1_verification_threshold": 0.7,
    }

    validate_v8_config(config)


def test_v8config_o1_validation_invalid_threshold():
    """o1 config validation - invalid threshold"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # Too low
    config: V8Config = {"o1_verification_threshold": 0.4}
    with pytest.raises(ValidationError) as exc_info:
        validate_v8_config(config)
    assert "o1_verification_threshold must be 0.5-1.0" in str(exc_info.value)


def test_v8config_debate_validation_valid():
    """Debate config validation - happy path"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    config: V8Config = {
        "num_proposers": 3,
        "num_critics": 2,
        "max_rounds": 2,
    }

    validate_v8_config(config)


def test_v8config_debate_validation_invalid_proposers():
    """Debate config validation - invalid num_proposers"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # Too few
    config: V8Config = {"num_proposers": 1}
    with pytest.raises(ValidationError) as exc_info:
        validate_v8_config(config)
    assert "num_proposers must be 2-5" in str(exc_info.value)


# ============================================================================
# Test 3: DeepReasoningRequest Validation
# ============================================================================


def test_v8_agent_request_with_strategy_enum(sample_task):
    """DeepReasoningRequest with strategy (enum)"""
    request = DeepReasoningRequest(
        task=sample_task,
        strategy=ReasoningStrategy.BEAM,
    )

    assert request.strategy == ReasoningStrategy.BEAM
    assert request.force_system_2 is False


def test_v8_agent_request_with_strategy_string(sample_task):
    """DeepReasoningRequest with strategy (string literal)"""
    request = DeepReasoningRequest(
        task=sample_task,
        strategy="beam",
    )

    # Should be converted to enum in __post_init__
    assert request.strategy == ReasoningStrategy.BEAM


def test_v8_agent_request_invalid_strategy(sample_task):
    """DeepReasoningRequest with invalid strategy"""
    with pytest.raises(ValidationError) as exc_info:
        DeepReasoningRequest(
            task=sample_task,
            strategy="invalid_strategy",
        )

    assert "Invalid strategy" in str(exc_info.value)


def test_v8_agent_request_backward_compatibility(sample_task):
    """force_system_2=True (backward compatibility)"""
    request = DeepReasoningRequest(
        task=sample_task,
        force_system_2=True,
    )

    assert request.force_system_2 is True
    assert request.strategy is None


# ============================================================================
# Test 4: _get_strategy_config() Helper
# ============================================================================


def test_get_strategy_config_beam_with_custom():
    """Beam config 추출 - custom values"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._get_strategy_config = DeepReasoningOrchestrator._get_strategy_config.__get__(orchestrator)

    config: V8Config = {
        "beam_width": 7,
        "max_depth": 3,
        "temperature": 0.9,
    }

    beam_config = orchestrator._get_strategy_config(config, "beam")

    assert beam_config["beam_width"] == 7
    assert beam_config["max_depth"] == 3
    assert beam_config["temperature"] == 0.9


def test_get_strategy_config_beam_with_defaults():
    """Beam config 추출 - default values"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._get_strategy_config = DeepReasoningOrchestrator._get_strategy_config.__get__(orchestrator)

    beam_config = orchestrator._get_strategy_config(None, "beam")

    assert beam_config["beam_width"] == 5  # default
    assert beam_config["max_depth"] == 2  # default
    assert beam_config["temperature"] == 0.7  # default


def test_get_strategy_config_o1():
    """o1 config 추출"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._get_strategy_config = DeepReasoningOrchestrator._get_strategy_config.__get__(orchestrator)

    config: V8Config = {
        "o1_max_attempts": 7,
        "o1_verification_threshold": 0.8,
    }

    o1_config = orchestrator._get_strategy_config(config, "o1")

    assert o1_config["max_iterations"] == 7
    assert o1_config["verification_threshold"] == 0.8


def test_get_strategy_config_debate():
    """Debate config 추출"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._get_strategy_config = DeepReasoningOrchestrator._get_strategy_config.__get__(orchestrator)

    config: V8Config = {
        "num_proposers": 4,
        "num_critics": 3,
        "max_rounds": 2,
    }

    debate_config = orchestrator._get_strategy_config(config, "debate")

    assert debate_config["num_proposers"] == 4
    assert debate_config["num_critics"] == 3
    assert debate_config["max_rounds"] == 2


# ============================================================================
# Test 5: _select_strategy() Logic
# ============================================================================


@pytest.mark.asyncio
async def test_select_strategy_explicit_beam(sample_task, mock_decision_simple):
    """명시적 strategy=beam 지정"""
    from unittest.mock import AsyncMock, MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    request = DeepReasoningRequest(task=sample_task, strategy=ReasoningStrategy.BEAM)

    strategy = await orchestrator._select_strategy(request, mock_decision_simple)

    assert strategy == ReasoningStrategy.BEAM


@pytest.mark.asyncio
async def test_select_strategy_force_system_2(sample_task, mock_decision_simple):
    """force_system_2=True → ToT (backward compatibility)"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    request = DeepReasoningRequest(task=sample_task, force_system_2=True)

    strategy = await orchestrator._select_strategy(request, mock_decision_simple)

    assert strategy == ReasoningStrategy.TOT


@pytest.mark.asyncio
async def test_select_strategy_auto_high_complexity(sample_task, mock_decision_complex):
    """Auto selection - high complexity → BEAM"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    request = DeepReasoningRequest(task=sample_task)  # strategy=None

    # complexity=0.85, risk=0.75
    strategy = await orchestrator._select_strategy(request, mock_decision_complex)

    # complexity > 0.8 AND risk > 0.7 → BEAM (ALPHACODE fallback)
    assert strategy == ReasoningStrategy.BEAM


@pytest.mark.asyncio
async def test_select_strategy_auto_high_risk(sample_task):
    """Auto selection - high risk → O1"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    request = DeepReasoningRequest(task=sample_task)

    decision = ReasoningDecision(
        path=ReasoningPath.SYSTEM_2,
        confidence=0.8,
        reasoning="High risk",
        complexity_score=0.5,  # moderate
        risk_score=0.8,  # high
        estimated_cost=0.12,
        estimated_time=30.0,
    )

    strategy = await orchestrator._select_strategy(request, decision)

    # risk > 0.7 → O1
    assert strategy == ReasoningStrategy.O1


@pytest.mark.asyncio
async def test_select_strategy_auto_many_files(sample_task):
    """Auto selection - many files → DEBATE"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    # 6개 파일
    task_with_many_files = AgentTask(
        task_id="test-123",
        repo_id="test-repo",
        snapshot_id="snap-002",  # REQUIRED
        description="Refactor authentication module",
        context_files=[f"src/file{i}.py" for i in range(6)],
        metadata={},
    )

    request = DeepReasoningRequest(task=task_with_many_files)

    decision = ReasoningDecision(
        path=ReasoningPath.SYSTEM_1,
        confidence=0.7,
        reasoning="Moderate",
        complexity_score=0.5,
        risk_score=0.5,
        estimated_cost=0.05,
        estimated_time=15.0,
    )

    strategy = await orchestrator._select_strategy(request, decision)

    # len(context_files) > 5 → DEBATE
    assert strategy == ReasoningStrategy.DEBATE


@pytest.mark.asyncio
async def test_select_strategy_auto_default(sample_task, mock_decision_simple):
    """Auto selection - default → TOT"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    request = DeepReasoningRequest(task=sample_task)

    strategy = await orchestrator._select_strategy(request, mock_decision_simple)

    # 조건 모두 미충족 → TOT (default)
    assert strategy == ReasoningStrategy.TOT


# ============================================================================
# Test 6: Priority Logic
# ============================================================================


@pytest.mark.asyncio
async def test_strategy_priority_explicit_over_force(sample_task, mock_decision_simple):
    """strategy가 force_system_2보다 우선순위 높음"""
    from unittest.mock import MagicMock

    orchestrator = MagicMock(spec=DeepReasoningOrchestrator)
    orchestrator._select_strategy = DeepReasoningOrchestrator._select_strategy.__get__(orchestrator)

    # Both specified
    request = DeepReasoningRequest(
        task=sample_task,
        strategy=ReasoningStrategy.BEAM,
        force_system_2=True,
    )

    strategy = await orchestrator._select_strategy(request, mock_decision_simple)

    # strategy가 우선
    assert strategy == ReasoningStrategy.BEAM


# ============================================================================
# Test 7: Edge Cases
# ============================================================================


def test_v8_agent_request_none_values(sample_task):
    """모든 optional 파라미터 None"""
    request = DeepReasoningRequest(task=sample_task)

    assert request.config is None
    assert request.force_system_2 is False
    assert request.strategy is None


def test_v8_agent_request_all_specified(sample_task):
    """모든 파라미터 지정"""
    config: V8Config = {
        "max_iterations": 5,
        "beam_width": 7,
        "o1_max_attempts": 6,
    }

    request = DeepReasoningRequest(
        task=sample_task,
        config=config,
        strategy=ReasoningStrategy.O1,
        force_system_2=False,
    )

    assert request.strategy == ReasoningStrategy.O1
    assert request.config["beam_width"] == 7


# ============================================================================
# Test 8: Boundary Cases
# ============================================================================


def test_v8config_beam_width_boundary():
    """beam_width 경계값 테스트"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # Min valid
    config: V8Config = {"beam_width": 3}
    validate_v8_config(config)  # OK

    # Max valid
    config: V8Config = {"beam_width": 10}
    validate_v8_config(config)  # OK

    # Below min
    with pytest.raises(ValidationError):
        config: V8Config = {"beam_width": 2}
        validate_v8_config(config)

    # Above max
    with pytest.raises(ValidationError):
        config: V8Config = {"beam_width": 11}
        validate_v8_config(config)


def test_v8config_max_depth_boundary():
    """max_depth 경계값 테스트"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # Min valid
    config: V8Config = {"max_depth": 1}
    validate_v8_config(config)

    # Max valid
    config: V8Config = {"max_depth": 5}
    validate_v8_config(config)

    # Below min
    with pytest.raises(ValidationError):
        config: V8Config = {"max_depth": 0}
        validate_v8_config(config)

    # Above max
    with pytest.raises(ValidationError):
        config: V8Config = {"max_depth": 6}
        validate_v8_config(config)


# ============================================================================
# Test 9: Type Safety
# ============================================================================


def test_v8config_type_mismatch():
    """Config 타입 mismatch 감지"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    # beam_width는 int여야 함
    config: V8Config = {"beam_width": "5"}  # type: ignore
    with pytest.raises(ValidationError):
        validate_v8_config(config)

    # o1_verification_threshold는 float여야 함
    config: V8Config = {"o1_verification_threshold": "0.7"}  # type: ignore
    with pytest.raises(ValidationError):
        validate_v8_config(config)


# ============================================================================
# Test 10: Integration with existing validation
# ============================================================================


def test_v8config_mixed_validation():
    """기존 config + 신규 strategy config 동시 검증"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    config: V8Config = {
        "max_iterations": 5,  # 기존
        "temperature": 0.7,  # 기존
        "beam_width": 6,  # 신규
        "num_proposers": 4,  # 신규
    }

    # All valid
    validate_v8_config(config)


def test_v8config_mixed_validation_with_error():
    """기존 + 신규 중 하나라도 invalid면 실패"""
    from apps.orchestrator.orchestrator.orchestrator.models import validate_v8_config

    config: V8Config = {
        "max_iterations": 11,  # invalid (기존)
        "beam_width": 6,  # valid (신규)
    }

    with pytest.raises(ValidationError) as exc_info:
        validate_v8_config(config)

    assert "max_iterations must be 1-10" in str(exc_info.value)
