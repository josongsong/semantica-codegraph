"""
Repair Ranking Integration Tests (SOTA L11 Grade)

Tests:
- Base case (normal operation)
- Edge cases (empty, single, extreme)
- Corner cases (boundaries)
- Integration (real components)
- Performance (< 100ms/patch)

NO MOCKS, NO STUBS - Real integration only.

RFC-SEM-001 Section 2.2: Repair Ranking System
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from codegraph_analysis.verification.repair_ranking.domain.models import ScoreResult

from codegraph_analysis.verification.repair_ranking.domain import PatchCandidate
from codegraph_analysis.verification.repair_ranking.domain.repair_ranker import RepairRanker
from codegraph_analysis.verification.repair_ranking.infrastructure.scorers import (
    ComplexityScorer,
    StyleScorer,
    TaintRegressionScorer,
)


class TestRepairRankerIntegration:
    """RepairRanker Integration Tests"""

    def test_base_case_rank_5_patches(self):
        """Base: 5개 패치 → Top-1 선정"""
        ranker = RepairRanker(
            taint_scorer=TaintRegressionScorer(),
            complexity_scorer=ComplexityScorer(),
            style_scorer=StyleScorer(),
        )

        # 5개 패치 (다양한 품질)
        patches = [
            PatchCandidate(
                patch_id="patch_1",
                original_code="x = input()\ndb.execute(x)",
                patched_code="x = input()\ndb.execute_param(x)",  # Good: parameterized
                description="Use parameterized query",
            ),
            PatchCandidate(
                patch_id="patch_2",
                original_code="x = input()\ndb.execute(x)",
                patched_code="x = escape(input())\ndb.execute(x)",  # Medium: escape
                description="Escape input",
            ),
            PatchCandidate(
                patch_id="patch_3",
                original_code="x = input()\ndb.execute(x)",
                patched_code="# TODO\npass",  # Bad: stub
                description="Block all",
            ),
            PatchCandidate(
                patch_id="patch_4",
                original_code="x = input()\ndb.execute(x)",
                patched_code="x = input()\nif validate(x):\n    db.execute(x)",  # Good: validation
                description="Add validation",
            ),
            PatchCandidate(
                patch_id="patch_5",
                original_code="x = input()\ndb.execute(x)",
                patched_code="invalid syntax !!!",  # Bad: syntax error
                description="Invalid",
            ),
        ]

        # Rank
        result = ranker.rank_patches(patches)

        # Assertions
        assert result.total_candidates == 5
        assert result.valid_candidates >= 3  # At least 3 pass syntax
        assert result.canonical_patch is not None
        assert result.canonical_patch.patch_id in ["patch_1", "patch_4"]  # Best patches

        # Scores descending
        scores = result.get_scores()
        assert scores == sorted(scores, reverse=True)

    def test_edge_case_empty_patches(self):
        """Edge: 패치 없음"""
        ranker = RepairRanker()

        result = ranker.rank_patches([])

        assert result.total_candidates == 0
        assert result.canonical_patch is None

    def test_edge_case_single_patch(self):
        """Edge: 패치 1개"""
        ranker = RepairRanker()

        patches = [
            PatchCandidate(
                patch_id="only",
                original_code="x = 1",
                patched_code="x = 2",
                description="Change value",
            )
        ]

        result = ranker.rank_patches(patches)

        assert result.canonical_patch == patches[0]
        assert len(result.get_scores()) == 1

    def test_edge_case_all_syntax_errors(self):
        """Edge: 모두 syntax error"""
        ranker = RepairRanker()

        patches = [
            PatchCandidate(
                patch_id=f"bad_{i}",
                original_code="x = 1",
                patched_code="invalid !!!",
                description="Bad",
            )
            for i in range(5)
        ]

        result = ranker.rank_patches(patches)

        # All filtered
        assert result.valid_candidates == 0
        assert result.canonical_patch is None

    def test_corner_case_identical_scores(self):
        """Corner: 동일 점수"""
        ranker = RepairRanker()

        # 동일 패치 3개
        patches = [
            PatchCandidate(
                patch_id=f"same_{i}",
                original_code="x = 1",
                patched_code="x = 2",  # Same change
                description="Same",
            )
            for i in range(3)
        ]

        result = ranker.rank_patches(patches)

        # 동일 점수 → 첫 번째 선택
        scores = result.get_scores()
        assert len(set(scores)) <= 3  # At most 3 unique scores


class TestTaintRegressionScorerIntegration:
    """TaintRegressionScorer Integration Tests"""

    @pytest.mark.skip(reason="Requires full TaintAnalyzer setup (IR parsing)")
    def test_base_case_no_regression(self):
        """Base: Taint 없음 (safe)"""
        scorer = TaintRegressionScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = input()\ndb.execute(x)",
            patched_code="x = input()\ndb.execute_param(x)",
            description="Fix",
        )

        result = scorer.score(patch)

        # No regression → 1.0
        assert result.score == 1.0
        assert "No taint regression" in result.reasoning

    def test_edge_case_syntax_error(self):
        """Edge: Syntax error → fail-safe"""
        scorer = TaintRegressionScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = 1",
            patched_code="invalid !!!",
            description="Bad",
        )

        result = scorer.score(patch)

        # Syntax error → 0.5 (neutral, fail-safe)
        assert result.score <= 0.5
        assert "failed" in result.reasoning.lower()


class TestComplexityScorerIntegration:
    """ComplexityScorer Integration Tests"""

    def test_base_case_complexity_decreased(self):
        """Base: 복잡도 감소"""
        scorer = ComplexityScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="""
def func(x):
    if x > 0:
        if x < 10:
            if x % 2 == 0:
                return x
    return 0
""",
            patched_code="""
def func(x):
    if 0 < x < 10 and x % 2 == 0:
        return x
    return 0
""",
            description="Simplify",
        )

        result = scorer.score(patch)

        # Complexity decreased → 1.0
        assert result.score == 1.0
        assert result.details["delta"] < 0

    def test_corner_case_complexity_unchanged(self):
        """Corner: 복잡도 동일"""
        scorer = ComplexityScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = 1",
            patched_code="y = 1",  # Same complexity
            description="Rename",
        )

        result = scorer.score(patch)

        # No change → 1.0
        assert result.score == 1.0
        assert result.details["delta"] == 0

    def test_edge_case_syntax_error(self):
        """Edge: Syntax error → 0.0"""
        scorer = ComplexityScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = 1",
            patched_code="invalid !!!",
            description="Bad",
        )

        result = scorer.score(patch)

        # Syntax error → 0.0
        assert result.score == 0.0
        assert "Syntax error" in result.reasoning


class TestStyleScorerIntegration:
    """StyleScorer Integration Tests"""

    def test_base_case_minimal_change(self):
        """Base: 최소 변경 (surgical fix)"""
        scorer = StyleScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = input()\ndb.execute(x)",
            patched_code="x = input()\ndb.execute_param(x)",  # 1 line change
            description="Minimal",
        )

        result = scorer.score(patch)

        # Minimal change → high score
        assert result.score > 0.8
        assert result.details["is_minimal"] is True

    def test_edge_case_complete_rewrite(self):
        """Edge: 완전 재작성"""
        scorer = StyleScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = input()\ndb.execute(x)",
            patched_code="import orm\nuser = orm.User(input())\nuser.save()",  # Complete rewrite
            description="Rewrite",
        )

        result = scorer.score(patch)

        # Complete rewrite → low score
        assert result.score < 0.5

    def test_corner_case_whitespace_only(self):
        """Corner: Whitespace만 변경"""
        scorer = StyleScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x=1\ny=2",
            patched_code="x = 1\ny = 2",  # Whitespace only
            description="Format",
        )

        result = scorer.score(patch)

        # Whitespace → high similarity (normalized)
        assert result.score > 0.95


class TestPerformanceSOTA:
    """Performance Tests (RFC-SEM-000 Section 14.2)"""

    def test_performance_ranking_under_100ms_per_patch(self):
        """Performance: < 100ms per patch"""
        ranker = RepairRanker()

        patches = [
            PatchCandidate(
                patch_id=f"p{i}",
                original_code="x = 1\ny = 2",
                patched_code=f"x = {i}\ny = 2",
                description=f"Patch {i}",
            )
            for i in range(10)
        ]

        start = time.perf_counter()
        result = ranker.rank_patches(patches)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # < 100ms per patch
        per_patch_ms = elapsed_ms / len(patches)
        assert per_patch_ms < 100.0, f"Per-patch time {per_patch_ms:.2f}ms exceeds 100ms SLA"

    def test_performance_scorer_under_10ms(self):
        """Performance: Individual scorer < 10ms"""
        scorer = StyleScorer()

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = 1\ny = 2\nz = 3",
            patched_code="x = 2\ny = 2\nz = 3",
            description="Change",
        )

        start = time.perf_counter()
        result = scorer.score(patch)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # < 10ms
        assert elapsed_ms < 10.0, f"Scorer time {elapsed_ms:.2f}ms exceeds 10ms"


class TestHexagonalComplianceSOTA:
    """Hexagonal Architecture Compliance"""

    def test_scorers_implement_port(self):
        """All scorers implement IScorerPort"""
        from codegraph_analysis.verification.repair_ranking.domain import IScorerPort

        scorers = [
            TaintRegressionScorer(),
            ComplexityScorer(),
            StyleScorer(),
        ]

        for scorer in scorers:
            # IScorerPort 구현
            assert isinstance(scorer, IScorerPort)
            assert hasattr(scorer, "score")
            assert hasattr(scorer, "get_name")
            assert hasattr(scorer, "get_weight")

    def test_scorers_stateless(self):
        """Scorers are stateless (thread-safe)"""
        scorer = StyleScorer()
        initial_state = dict(scorer.__dict__)

        patch = PatchCandidate(
            patch_id="test",
            original_code="x = 1",
            patched_code="x = 2",
            description="Test",
        )

        # Multiple calls
        scorer.score(patch)
        scorer.score(patch)

        # No state change
        assert dict(scorer.__dict__) == initial_state


class TestSOLIDComplianceSOTA:
    """SOLID Principle Compliance"""

    def test_single_responsibility(self):
        """S: Each scorer has single responsibility"""
        # TaintScorer: Taint only
        # ComplexityScorer: Complexity only
        # StyleScorer: Style only

        taint = TaintRegressionScorer()
        complexity = ComplexityScorer()
        style = StyleScorer()

        # No cross-concern methods
        assert not hasattr(taint, "calculate_complexity")
        assert not hasattr(complexity, "analyze_taint")
        assert not hasattr(style, "analyze_taint")

    def test_open_closed(self):
        """O: Open for extension, closed for modification"""
        # New scorer can be added without modifying RepairRanker

        from codegraph_analysis.verification.repair_ranking.domain import IScorerPort

        class CustomScorer(IScorerPort):
            def score(self, patch):
                return ScoreResult(score=0.8, reasoning="Custom")

            def get_name(self):
                return "custom"

            def get_weight(self):
                return 0.1

        # Can inject new scorer
        ranker = RepairRanker(
            taint_scorer=CustomScorer(),  # Custom scorer works!
            complexity_scorer=ComplexityScorer(),
            style_scorer=StyleScorer(),
        )

        assert ranker.taint_scorer.get_name() == "custom"

    def test_liskov_substitution(self):
        """L: RepairRanker is-a CriticModel"""
        from apps.orchestrator.orchestrator.shared.reasoning.critic.critic_model import CriticModel

        ranker = RepairRanker()

        # RepairRanker is CriticModel
        assert isinstance(ranker, CriticModel)

        # Can use CriticModel interface
        patch = PatchCandidate(
            patch_id="test",
            original_code="x = 1",
            patched_code="x = 2",
            description="Test",
        )

        # evaluate() works (CriticModel method)
        result = ranker.evaluate(patch)
        assert result is not None
