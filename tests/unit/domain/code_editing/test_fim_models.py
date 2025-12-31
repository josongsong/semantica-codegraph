"""
FIM Domain Models Unit Tests

/ss Rule 3 준수:
✅ Happy path
✅ Invalid input (type mismatch, nullable violation)
✅ Boundary / Edge Case
✅ 모든 validation 검증
"""

import pytest

from apps.orchestrator.orchestrator.domain.code_editing.fim import (
    Completion,
    FIMEngine,
    FIMRequest,
    FIMResult,
)

# ============================================================================
# FIMRequest Tests
# ============================================================================


class TestFIMRequest:
    """FIMRequest 테스트"""

    def test_happy_path_basic(self):
        """Happy path: 기본 요청"""
        req = FIMRequest(
            prefix="def add(a, b):",
            suffix="return result",
            file_path="/test/math.py",
            language="python",
        )
        assert req.prefix == "def add(a, b):"
        assert req.suffix == "return result"
        assert req.max_tokens == 500  # default
        assert req.temperature == 0.7  # default
        assert req.num_completions == 3  # default
        assert req.engine is None  # default

    def test_happy_path_full_params(self):
        """Happy path: 모든 파라미터 지정"""
        req = FIMRequest(
            prefix="class MyClass:",
            suffix="pass",
            file_path="/test/app.py",
            language="python",
            max_tokens=1000,
            temperature=0.2,
            num_completions=5,
            context_files=["/test/helper.py"],
            engine=FIMEngine.OPENAI,
        )
        assert req.max_tokens == 1000
        assert req.temperature == 0.2
        assert req.num_completions == 5
        assert req.context_files == ["/test/helper.py"]
        assert req.engine == FIMEngine.OPENAI

    def test_prefix_only(self):
        """Boundary: prefix만 있는 경우"""
        req = FIMRequest(
            prefix="import os\n",
            suffix="",
            file_path="/test/main.py",
            language="python",
        )
        assert req.suffix == ""
        assert req.total_context_length == len("import os\n")

    def test_suffix_only(self):
        """Boundary: suffix만 있는 경우"""
        req = FIMRequest(
            prefix="",
            suffix="\nprint('done')",
            file_path="/test/main.py",
            language="python",
        )
        assert req.prefix == ""
        assert req.total_context_length == len("\nprint('done')")

    def test_both_empty_fails(self):
        """Invalid: prefix/suffix 둘 다 비어있음"""
        with pytest.raises(ValueError, match="prefix and suffix cannot both be empty"):
            FIMRequest(
                prefix="",
                suffix="",
                file_path="/test/main.py",
                language="python",
            )

    def test_max_tokens_boundary_min(self):
        """Boundary: max_tokens = 1 (최소값)"""
        req = FIMRequest(
            prefix="x = 1",
            suffix="",
            file_path="/test/main.py",
            language="python",
            max_tokens=1,
        )
        assert req.max_tokens == 1

    def test_max_tokens_boundary_max(self):
        """Boundary: max_tokens = 4096 (최대값)"""
        req = FIMRequest(
            prefix="x = 1",
            suffix="",
            file_path="/test/main.py",
            language="python",
            max_tokens=4096,
        )
        assert req.max_tokens == 4096

    def test_max_tokens_invalid_zero(self):
        """Invalid: max_tokens = 0"""
        with pytest.raises(ValueError, match="max_tokens must be 1-4096"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                max_tokens=0,
            )

    def test_max_tokens_invalid_negative(self):
        """Invalid: max_tokens < 0"""
        with pytest.raises(ValueError, match="max_tokens must be 1-4096"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                max_tokens=-100,
            )

    def test_max_tokens_invalid_too_large(self):
        """Invalid: max_tokens > 4096"""
        with pytest.raises(ValueError, match="max_tokens must be 1-4096"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                max_tokens=5000,
            )

    def test_max_tokens_invalid_float(self):
        """Invalid: max_tokens는 int만 허용"""
        with pytest.raises(TypeError, match="max_tokens must be int"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                max_tokens=500.5,  # type: ignore
            )

    def test_temperature_boundary_min(self):
        """Boundary: temperature = 0.0"""
        req = FIMRequest(
            prefix="x = 1",
            suffix="",
            file_path="/test/main.py",
            language="python",
            temperature=0.0,
        )
        assert req.temperature == 0.0

    def test_temperature_boundary_max(self):
        """Boundary: temperature = 2.0"""
        req = FIMRequest(
            prefix="x = 1",
            suffix="",
            file_path="/test/main.py",
            language="python",
            temperature=2.0,
        )
        assert req.temperature == 2.0

    def test_temperature_invalid_negative(self):
        """Invalid: temperature < 0"""
        with pytest.raises(ValueError, match="temperature must be 0.0-2.0"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                temperature=-0.1,
            )

    def test_temperature_invalid_too_large(self):
        """Invalid: temperature > 2.0"""
        with pytest.raises(ValueError, match="temperature must be 0.0-2.0"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                temperature=2.5,
            )

    def test_num_completions_boundary_min(self):
        """Boundary: num_completions = 1"""
        req = FIMRequest(
            prefix="x = 1",
            suffix="",
            file_path="/test/main.py",
            language="python",
            num_completions=1,
        )
        assert req.num_completions == 1

    def test_num_completions_boundary_max(self):
        """Boundary: num_completions = 5"""
        req = FIMRequest(
            prefix="x = 1",
            suffix="",
            file_path="/test/main.py",
            language="python",
            num_completions=5,
        )
        assert req.num_completions == 5

    def test_num_completions_invalid_zero(self):
        """Invalid: num_completions = 0"""
        with pytest.raises(ValueError, match="num_completions must be 1-5"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                num_completions=0,
            )

    def test_num_completions_invalid_too_large(self):
        """Invalid: num_completions > 5"""
        with pytest.raises(ValueError, match="num_completions must be 1-5"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="python",
                num_completions=10,
            )

    def test_file_path_empty(self):
        """Invalid: file_path 비어있음"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="",
                language="python",
            )

    def test_language_empty(self):
        """Invalid: language 비어있음"""
        with pytest.raises(ValueError, match="language cannot be empty"):
            FIMRequest(
                prefix="x = 1",
                suffix="",
                file_path="/test/main.py",
                language="",
            )

    def test_total_context_length(self):
        """Property: total_context_length"""
        req = FIMRequest(
            prefix="abc",  # 3 chars
            suffix="def",  # 3 chars
            file_path="/test/main.py",
            language="python",
        )
        assert req.total_context_length == 6

    def test_is_simple_true(self):
        """Property: is_simple = True"""
        req = FIMRequest(
            prefix="x = ",  # 4 chars (< 500)
            suffix="",
            file_path="/test/main.py",
            language="python",
            num_completions=1,
        )
        assert req.is_simple() is True

    def test_is_simple_false_large_context(self):
        """Property: is_simple = False (큰 컨텍스트)"""
        req = FIMRequest(
            prefix="x = " * 200,  # 800 chars (> 500)
            suffix="",
            file_path="/test/main.py",
            language="python",
            num_completions=1,
        )
        assert req.is_simple() is False

    def test_is_simple_false_multiple_completions(self):
        """Property: is_simple = False (여러 후보)"""
        req = FIMRequest(
            prefix="x = ",  # 4 chars (< 500)
            suffix="",
            file_path="/test/main.py",
            language="python",
            num_completions=3,
        )
        assert req.is_simple() is False


# ============================================================================
# Completion Tests
# ============================================================================


class TestCompletion:
    """Completion 테스트"""

    def test_happy_path_basic(self):
        """Happy path: 기본 완성"""
        comp = Completion(
            text="result = a + b",
            score=0.95,
        )
        assert comp.text == "result = a + b"
        assert comp.score == 0.95
        assert comp.reasoning == ""  # default
        assert comp.tokens_used == 0  # default
        assert comp.finish_reason == "stop"  # default

    def test_happy_path_full_params(self):
        """Happy path: 모든 파라미터"""
        comp = Completion(
            text="result = a + b",
            score=0.85,
            reasoning="Simple arithmetic addition",
            tokens_used=10,
            finish_reason="stop",
        )
        assert comp.reasoning == "Simple arithmetic addition"
        assert comp.tokens_used == 10
        assert comp.finish_reason == "stop"

    def test_score_boundary_min(self):
        """Boundary: score = 0.0"""
        comp = Completion(text="x", score=0.0)
        assert comp.score == 0.0

    def test_score_boundary_max(self):
        """Boundary: score = 1.0"""
        comp = Completion(text="x", score=1.0)
        assert comp.score == 1.0

    def test_score_invalid_negative(self):
        """Invalid: score < 0.0"""
        with pytest.raises(ValueError, match="score must be 0.0-1.0"):
            Completion(text="x", score=-0.1)

    def test_score_invalid_too_large(self):
        """Invalid: score > 1.0"""
        with pytest.raises(ValueError, match="score must be 0.0-1.0"):
            Completion(text="x", score=1.5)

    def test_tokens_used_boundary_zero(self):
        """Boundary: tokens_used = 0"""
        comp = Completion(text="x", score=0.5, tokens_used=0)
        assert comp.tokens_used == 0

    def test_tokens_used_invalid_negative(self):
        """Invalid: tokens_used < 0"""
        with pytest.raises(ValueError, match="tokens_used must be >= 0"):
            Completion(text="x", score=0.5, tokens_used=-10)

    def test_text_empty_with_stop_fails(self):
        """Invalid: finish_reason='stop'인데 text 비어있음"""
        with pytest.raises(ValueError, match="text cannot be empty when finish_reason is 'stop'"):
            Completion(text="", score=0.5, finish_reason="stop")

    def test_text_empty_with_length_ok(self):
        """Valid: finish_reason='length'이면 text 비어도 됨"""
        comp = Completion(text="", score=0.0, finish_reason="length")
        assert comp.text == ""
        assert comp.finish_reason == "length"

    def test_is_high_quality_true(self):
        """Property: is_high_quality = True"""
        comp = Completion(text="x", score=0.9, finish_reason="stop")
        assert comp.is_high_quality is True

    def test_is_high_quality_false_low_score(self):
        """Property: is_high_quality = False (낮은 점수)"""
        comp = Completion(text="x", score=0.7, finish_reason="stop")
        assert comp.is_high_quality is False

    def test_is_high_quality_false_not_stop(self):
        """Property: is_high_quality = False (finish_reason != stop)"""
        comp = Completion(text="x", score=0.9, finish_reason="length")
        assert comp.is_high_quality is False

    def test_sorting_by_score(self):
        """Sorting: 점수 기반 정렬"""
        c1 = Completion(text="a", score=0.5)
        c2 = Completion(text="b", score=0.8)
        c3 = Completion(text="c", score=0.3)

        sorted_list = sorted([c1, c2, c3], reverse=True)
        assert sorted_list[0].score == 0.8
        assert sorted_list[1].score == 0.5
        assert sorted_list[2].score == 0.3


# ============================================================================
# FIMResult Tests
# ============================================================================


class TestFIMResult:
    """FIMResult 테스트"""

    def test_happy_path_success(self):
        """Happy path: 성공 케이스"""
        result = FIMResult(
            completions=[
                Completion(text="a", score=0.9),
                Completion(text="b", score=0.7),
            ],
            execution_time_ms=123.45,
            total_tokens=50,
            engine_used=FIMEngine.OPENAI,
        )
        assert result.success is True
        assert result.error is None
        assert len(result.completions) == 2
        assert result.execution_time_ms == 123.45
        assert result.total_tokens == 50
        assert result.engine_used == FIMEngine.OPENAI

    def test_happy_path_failure(self):
        """Happy path: 실패 케이스"""
        result = FIMResult(
            completions=[],
            execution_time_ms=50.0,
            error="LLM timeout",
        )
        assert result.success is False
        assert result.error == "LLM timeout"
        assert len(result.completions) == 0

    def test_auto_sort_by_score(self):
        """Auto-sort: 점수 내림차순 자동 정렬"""
        result = FIMResult(
            completions=[
                Completion(text="c", score=0.3),
                Completion(text="a", score=0.9),
                Completion(text="b", score=0.7),
            ],
            execution_time_ms=100.0,
        )
        # 자동 정렬되어야 함
        assert result.completions[0].score == 0.9
        assert result.completions[1].score == 0.7
        assert result.completions[2].score == 0.3

    def test_execution_time_boundary_zero(self):
        """Boundary: execution_time_ms = 0"""
        result = FIMResult(
            completions=[Completion(text="x", score=0.5)],
            execution_time_ms=0,
        )
        assert result.execution_time_ms == 0

    def test_execution_time_invalid_negative(self):
        """Invalid: execution_time_ms < 0"""
        with pytest.raises(ValueError, match="execution_time_ms must be >= 0"):
            FIMResult(
                completions=[Completion(text="x", score=0.5)],
                execution_time_ms=-10.0,
            )

    def test_total_tokens_boundary_zero(self):
        """Boundary: total_tokens = 0"""
        result = FIMResult(
            completions=[Completion(text="x", score=0.5)],
            execution_time_ms=100.0,
            total_tokens=0,
        )
        assert result.total_tokens == 0

    def test_total_tokens_invalid_negative(self):
        """Invalid: total_tokens < 0"""
        with pytest.raises(ValueError, match="total_tokens must be >= 0"):
            FIMResult(
                completions=[Completion(text="x", score=0.5)],
                execution_time_ms=100.0,
                total_tokens=-50,
            )

    def test_completions_invalid_type(self):
        """Invalid: completions가 list가 아님"""
        with pytest.raises(TypeError, match="completions must be list"):
            FIMResult(
                completions="not a list",  # type: ignore
                execution_time_ms=100.0,
            )

    def test_success_but_empty_completions_fails(self):
        """Invalid: 성공인데 completions 비어있음"""
        with pytest.raises(ValueError, match="completions cannot be empty when error is None"):
            FIMResult(
                completions=[],
                execution_time_ms=100.0,
                error=None,
            )

    def test_failure_but_no_error_fails(self):
        """Invalid: 실패인데 error 없음"""
        with pytest.raises(ValueError, match="completions cannot be empty when error is None"):
            FIMResult(
                completions=[],
                execution_time_ms=100.0,
                error=None,
            )

    def test_best_completion_property(self):
        """Property: best_completion (최고 점수)"""
        result = FIMResult(
            completions=[
                Completion(text="c", score=0.3),
                Completion(text="a", score=0.9),
                Completion(text="b", score=0.7),
            ],
            execution_time_ms=100.0,
        )
        assert result.best_completion is not None
        assert result.best_completion.score == 0.9
        assert result.best_completion.text == "a"

    def test_best_completion_none_when_empty(self):
        """Property: best_completion = None (실패 시)"""
        result = FIMResult(
            completions=[],
            execution_time_ms=100.0,
            error="Failed",
        )
        assert result.best_completion is None

    def test_average_score_property(self):
        """Property: average_score"""
        result = FIMResult(
            completions=[
                Completion(text="a", score=0.8),
                Completion(text="b", score=0.6),
                Completion(text="c", score=0.4),
            ],
            execution_time_ms=100.0,
        )
        assert result.average_score == pytest.approx(0.6)

    def test_average_score_zero_when_empty(self):
        """Property: average_score = 0 (실패 시)"""
        result = FIMResult(
            completions=[],
            execution_time_ms=100.0,
            error="Failed",
        )
        assert result.average_score == 0.0

    def test_get_top_k_property(self):
        """Property: get_top_k"""
        result = FIMResult(
            completions=[
                Completion(text="a", score=0.9),
                Completion(text="b", score=0.7),
                Completion(text="c", score=0.5),
            ],
            execution_time_ms=100.0,
        )
        top_2 = result.get_top_k(2)
        assert len(top_2) == 2
        assert top_2[0].score == 0.9
        assert top_2[1].score == 0.7

    def test_get_top_k_more_than_available(self):
        """Edge: get_top_k(k > len)"""
        result = FIMResult(
            completions=[Completion(text="a", score=0.5)],
            execution_time_ms=100.0,
        )
        top_10 = result.get_top_k(10)
        assert len(top_10) == 1  # 최대 1개만 있음
