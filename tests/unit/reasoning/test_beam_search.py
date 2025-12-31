"""
Beam Search 테스트
"""

import pytest

from apps.orchestrator.orchestrator.shared.reasoning.beam import (
    BeamCandidate,
    BeamConfig,
    BeamRanker,
    BeamSearchEngine,
    BeamSearchResult,
)


class TestBeamConfig:
    """BeamConfig 테스트"""

    def test_default_config(self):
        """기본 설정"""
        config = BeamConfig()
        assert config.beam_width == 5
        assert config.max_depth == 3
        assert config.temperature == 0.7
        assert config.diversity_penalty == 0.1

    def test_custom_config(self):
        """커스텀 설정"""
        config = BeamConfig(beam_width=10, max_depth=5, temperature=0.9, diversity_penalty=0.2)
        assert config.beam_width == 10
        assert config.max_depth == 5


class TestBeamCandidate:
    """BeamCandidate 테스트"""

    def test_candidate_creation(self):
        """후보 생성"""
        candidate = BeamCandidate(candidate_id="test1", depth=0, code_diff="print('hello')")
        assert candidate.candidate_id == "test1"
        assert candidate.depth == 0

    def test_valid_candidate(self):
        """유효한 후보"""
        candidate = BeamCandidate(
            candidate_id="test1",
            depth=0,
            compile_success=True,
            test_pass_rate=0.8,
        )
        assert candidate.is_valid()

    def test_invalid_candidate_no_compile(self):
        """컴파일 실패 = 유효하지 않음"""
        candidate = BeamCandidate(candidate_id="test1", depth=0, compile_success=False)
        assert not candidate.is_valid()

    def test_invalid_candidate_low_test_rate(self):
        """테스트 통과율 낮음 = 유효하지 않음"""
        candidate = BeamCandidate(
            candidate_id="test1",
            depth=0,
            compile_success=True,
            test_pass_rate=0.3,  # < 0.5
        )
        assert not candidate.is_valid()

    def test_calculate_final_score(self):
        """최종 점수 계산"""
        candidate = BeamCandidate(
            candidate_id="test1",
            depth=0,
            compile_success=True,
            log_prob=-0.5,
            quality_score=0.9,
        )
        score = candidate.calculate_final_score(diversity_penalty=0.0)
        assert 0.0 <= score <= 1.0

    def test_calculate_final_score_with_penalty(self):
        """다양성 페널티 적용"""
        candidate = BeamCandidate(
            candidate_id="test1",
            depth=0,
            compile_success=True,
            log_prob=-0.5,
            quality_score=0.9,
        )
        score_no_penalty = candidate.calculate_final_score(0.0)
        score_with_penalty = candidate.calculate_final_score(0.2)
        assert score_with_penalty < score_no_penalty


class TestBeamRanker:
    """BeamRanker 테스트"""

    def test_rank_empty_list(self):
        """빈 리스트"""
        config = BeamConfig(beam_width=5)
        ranker = BeamRanker(config)
        result = ranker.rank_and_prune([])
        assert result == []

    def test_rank_and_prune(self):
        """랭킹 및 pruning"""
        config = BeamConfig(beam_width=2)
        ranker = BeamRanker(config)

        candidates = [
            BeamCandidate("c1", 0, compile_success=True, quality_score=0.9, log_prob=-0.1),
            BeamCandidate("c2", 0, compile_success=True, quality_score=0.7, log_prob=-0.3),
            BeamCandidate("c3", 0, compile_success=True, quality_score=0.5, log_prob=-0.5),
        ]

        top_k = ranker.rank_and_prune(candidates)
        assert len(top_k) == 2  # beam_width=2
        # 점수 순으로 정렬되어야 함
        assert top_k[0].candidate_id == "c1"

    def test_deduplication(self):
        """중복 제거"""
        config = BeamConfig(beam_width=5)
        ranker = BeamRanker(config)

        # 같은 code_diff
        candidates = [
            BeamCandidate("c1", 0, code_diff="print('hello')", compile_success=True),
            BeamCandidate("c2", 0, code_diff="print('hello')", compile_success=True),
        ]

        # Private method 직접 테스트
        unique = ranker._deduplicate(candidates)
        assert len(unique) == 1


class TestBeamSearchResult:
    """BeamSearchResult 테스트"""

    def test_empty_result(self):
        """빈 결과"""
        result = BeamSearchResult()
        assert result.best_candidate is None
        assert result.total_candidates == 0

    def test_get_top_k(self):
        """상위 k개"""
        candidates = [
            BeamCandidate("c1", 0, compile_success=True, test_pass_rate=0.9, score=0.9),
            BeamCandidate("c2", 0, compile_success=True, test_pass_rate=0.7, score=0.7),
            BeamCandidate("c3", 0, compile_success=True, test_pass_rate=0.5, score=0.5),
        ]

        result = BeamSearchResult(all_candidates=candidates)
        top_2 = result.get_top_k(2)
        assert len(top_2) == 2
        assert top_2[0].score >= top_2[1].score

    def test_diversity_score(self):
        """다양성 점수"""
        candidates = [
            BeamCandidate("c1", 0, reasoning="approach A"),
            BeamCandidate("c2", 0, reasoning="approach B"),
            BeamCandidate("c3", 0, reasoning="approach A"),  # 중복
        ]

        result = BeamSearchResult(all_candidates=candidates)
        diversity = result.get_diversity_score()
        assert 0.0 <= diversity <= 1.0
        # 2 unique / 3 total = 0.666...
        assert abs(diversity - 2 / 3) < 0.01
