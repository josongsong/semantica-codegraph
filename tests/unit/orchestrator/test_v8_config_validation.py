"""V8Config Validation Tests

TypedDict 기반 V8Config의 validation 로직을 검증합니다.
"""

import pytest

from apps.orchestrator.orchestrator.errors import ValidationError
from apps.orchestrator.orchestrator.orchestrator.models import V8Config, validate_v8_config


class TestV8ConfigValidation:
    """V8Config validation 테스트"""

    def test_none_config_valid(self):
        """None config는 유효"""
        validate_v8_config(None)  # Should not raise

    def test_empty_config_valid(self):
        """빈 config는 유효"""
        config: V8Config = {}
        validate_v8_config(config)  # Should not raise

    def test_valid_max_iterations(self):
        """유효한 max_iterations"""
        for val in [1, 5, 10]:
            config: V8Config = {"max_iterations": val}
            validate_v8_config(config)  # Should not raise

    def test_invalid_max_iterations_zero(self):
        """max_iterations = 0은 invalid"""
        config: V8Config = {"max_iterations": 0}

        with pytest.raises(ValidationError, match="max_iterations must be 1-10"):
            validate_v8_config(config)

    def test_invalid_max_iterations_negative(self):
        """max_iterations < 0은 invalid"""
        config: V8Config = {"max_iterations": -1}

        with pytest.raises(ValidationError, match="max_iterations must be 1-10"):
            validate_v8_config(config)

    def test_invalid_max_iterations_too_large(self):
        """max_iterations > 10은 invalid"""
        config: V8Config = {"max_iterations": 11}

        with pytest.raises(ValidationError, match="max_iterations must be 1-10"):
            validate_v8_config(config)

    def test_valid_timeout_seconds(self):
        """유효한 timeout_seconds"""
        for val in [1.0, 60.0, 300.0, 3600.0]:
            config: V8Config = {"timeout_seconds": val}
            validate_v8_config(config)

    def test_invalid_timeout_seconds_zero(self):
        """timeout_seconds = 0은 invalid"""
        config: V8Config = {"timeout_seconds": 0.0}

        with pytest.raises(ValidationError, match="timeout_seconds must be 0-3600"):
            validate_v8_config(config)

    def test_invalid_timeout_seconds_negative(self):
        """timeout_seconds < 0은 invalid"""
        config: V8Config = {"timeout_seconds": -10.0}

        with pytest.raises(ValidationError, match="timeout_seconds must be 0-3600"):
            validate_v8_config(config)

    def test_invalid_timeout_seconds_too_large(self):
        """timeout_seconds > 3600은 invalid"""
        config: V8Config = {"timeout_seconds": 3601.0}

        with pytest.raises(ValidationError, match="timeout_seconds must be 0-3600"):
            validate_v8_config(config)

    def test_valid_temperature(self):
        """유효한 temperature"""
        for val in [0.0, 0.5, 0.7, 1.0, 1.5, 2.0]:
            config: V8Config = {"temperature": val}
            validate_v8_config(config)

    def test_invalid_temperature_negative(self):
        """temperature < 0은 invalid"""
        config: V8Config = {"temperature": -0.1}

        with pytest.raises(ValidationError, match="temperature must be 0.0-2.0"):
            validate_v8_config(config)

    def test_invalid_temperature_too_large(self):
        """temperature > 2.0은 invalid"""
        config: V8Config = {"temperature": 2.1}

        with pytest.raises(ValidationError, match="temperature must be 0.0-2.0"):
            validate_v8_config(config)

    def test_valid_system_2_threshold(self):
        """유효한 system_2_threshold"""
        for val in [0.0, 0.5, 0.7, 1.0]:
            config: V8Config = {"system_2_threshold": val}
            validate_v8_config(config)

    def test_invalid_system_2_threshold_negative(self):
        """system_2_threshold < 0은 invalid"""
        config: V8Config = {"system_2_threshold": -0.1}

        with pytest.raises(ValidationError, match="system_2_threshold must be 0.0-1.0"):
            validate_v8_config(config)

    def test_invalid_system_2_threshold_too_large(self):
        """system_2_threshold > 1.0은 invalid"""
        config: V8Config = {"system_2_threshold": 1.1}

        with pytest.raises(ValidationError, match="system_2_threshold must be 0.0-1.0"):
            validate_v8_config(config)

    def test_multiple_valid_fields(self):
        """여러 필드 조합 유효"""
        config: V8Config = {
            "max_iterations": 5,
            "timeout_seconds": 300.0,
            "temperature": 0.7,
            "enable_reflection": True,
            "enable_tot": True,
            "system_2_threshold": 0.8,
        }
        validate_v8_config(config)

    def test_partial_config_valid(self):
        """일부 필드만 있어도 유효"""
        config: V8Config = {
            "max_iterations": 3,
            "temperature": 0.5,
        }
        validate_v8_config(config)

    def test_boolean_fields_valid(self):
        """Boolean 필드는 항상 유효"""
        config: V8Config = {
            "enable_reflection": False,
            "enable_tot": True,
        }
        validate_v8_config(config)


class TestDeepReasoningRequestValidation:
    """DeepReasoningRequest의 __post_init__ validation 테스트"""

    def test_request_with_valid_config(self):
        """유효한 config로 request 생성"""
        from apps.orchestrator.orchestrator.domain.models import AgentTask
        from apps.orchestrator.orchestrator.orchestrator import DeepReasoningRequest

        task = AgentTask(task_id="test", repo_id=".", snapshot_id="snap", description="Test task")

        config: V8Config = {
            "max_iterations": 5,
            "temperature": 0.7,
        }

        request = DeepReasoningRequest(task=task, config=config)
        assert request.config == config

    def test_request_with_invalid_config_raises(self):
        """Invalid config로 request 생성 시 ValueError"""
        from apps.orchestrator.orchestrator.domain.models import AgentTask
        from apps.orchestrator.orchestrator.orchestrator import DeepReasoningRequest

        task = AgentTask(task_id="test", repo_id=".", snapshot_id="snap", description="Test task")

        config: V8Config = {
            "max_iterations": -1,  # Invalid!
        }

        with pytest.raises(ValidationError, match="max_iterations must be 1-10"):
            DeepReasoningRequest(task=task, config=config)

    def test_request_with_none_config(self):
        """None config는 유효"""
        from apps.orchestrator.orchestrator.domain.models import AgentTask
        from apps.orchestrator.orchestrator.orchestrator import DeepReasoningRequest

        task = AgentTask(task_id="test", repo_id=".", snapshot_id="snap", description="Test task")

        request = DeepReasoningRequest(task=task, config=None)
        assert request.config is None
