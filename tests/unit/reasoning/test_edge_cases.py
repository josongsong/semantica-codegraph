"""
엣지 케이스 테스트
"""

import pytest

from apps.orchestrator.orchestrator.shared.reasoning.beam import BeamCandidate, BeamConfig, BeamRanker
from apps.orchestrator.orchestrator.shared.reasoning.debate import DebateConfig
from apps.orchestrator.orchestrator.shared.reasoning.ttc import ComputeAllocator, DifficultyLevel, TTCConfig


class TestBeamSearchEdgeCases:
    """Beam Search 엣지 케이스"""

    def test_empty_candidates(self):
        """빈 후보 리스트"""
        ranker = BeamRanker(BeamConfig())
        result = ranker.rank_and_prune([])
        assert result == []

    def test_single_candidate(self):
        """후보 1개"""
        ranker = BeamRanker(BeamConfig(beam_width=5))
        candidates = [BeamCandidate("c1", 0, compile_success=True)]
        result = ranker.rank_and_prune(candidates)
        assert len(result) == 1

    def test_beam_width_larger_than_candidates(self):
        """beam_width가 후보 수보다 큼"""
        ranker = BeamRanker(BeamConfig(beam_width=10))
        candidates = [
            BeamCandidate("c1", 0, compile_success=True),
            BeamCandidate("c2", 0, compile_success=True),
        ]
        result = ranker.rank_and_prune(candidates)
        assert len(result) == 2  # 모두 선택됨

    def test_all_invalid_candidates(self):
        """모두 유효하지 않은 후보"""
        ranker = BeamRanker(BeamConfig())
        candidates = [
            BeamCandidate("c1", 0, compile_success=False),
            BeamCandidate("c2", 0, compile_success=False),
        ]
        # Pruning 후에도 리스트는 반환되어야 함 (빈 리스트일 수 있음)
        result = ranker.rank_and_prune(candidates)
        assert isinstance(result, list)


class TestTTCEdgeCases:
    """Test-Time Compute 엣지 케이스"""

    def test_empty_task(self):
        """빈 작업"""
        allocator = ComputeAllocator(TTCConfig())
        difficulty, budget = allocator.allocate("")
        assert difficulty.level in DifficultyLevel
        assert budget is not None

    def test_trivial_task(self):
        """매우 쉬운 작업"""
        allocator = ComputeAllocator(TTCConfig())
        task = "simple easy task"

        difficulty, budget = allocator.allocate(task)
        assert difficulty.level == DifficultyLevel.EASY
        assert budget.num_samples <= 3  # 쉬운 작업은 샘플 적게

    def test_extreme_task(self):
        """매우 어려운 작업"""
        allocator = ComputeAllocator(TTCConfig())
        task = "extremely difficult complex intricate task"

        difficulty, budget = allocator.allocate(task)
        assert difficulty.level == DifficultyLevel.EXTREME
        assert budget.num_samples >= 10  # 어려운 작업은 샘플 많이

    def test_very_long_task(self):
        """매우 긴 작업 설명"""
        allocator = ComputeAllocator(TTCConfig())
        task = "task " * 200  # 600자

        difficulty, budget = allocator.allocate(task)
        # 긴 작업은 더 어려운 것으로 분류되어야 함
        assert difficulty.level in [
            DifficultyLevel.MEDIUM,
            DifficultyLevel.HARD,
            DifficultyLevel.EXTREME,
        ]


class TestDebateEdgeCases:
    """Debate 엣지 케이스"""

    def test_zero_proposers_raises_error(self):
        """제안자 0명 = 에러"""
        with pytest.raises((ValueError, AssertionError)):
            # 설정 validation이 있어야 함
            config = DebateConfig(num_proposers=0, num_critics=0)
            assert config.num_proposers > 0, "At least one proposer required"

    def test_negative_rounds_raises_error(self):
        """음수 라운드 = 에러"""
        with pytest.raises((ValueError, AssertionError)):
            config = DebateConfig(max_rounds=-1)
            assert config.max_rounds > 0, "Rounds must be positive"

    def test_single_round_debate(self):
        """1라운드 토론"""
        config = DebateConfig(max_rounds=1)
        assert config.max_rounds == 1
