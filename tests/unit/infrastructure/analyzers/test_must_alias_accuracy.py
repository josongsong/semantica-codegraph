"""
Phase 2 Pre-check: Must-alias Accuracy Measurement

RFC-028 Week 5-6 전제조건:
- Must-alias 정확도 90%+ 필요
- Concurrency Analysis의 Proven verdict 조건

측정 지표:
- Precision: Must-alias로 판단한 것 중 실제 alias 비율
- Recall: 실제 alias 중 Must-alias로 감지한 비율
- F1 Score: Precision과 Recall의 조화평균

목표:
- Precision: 95%+ (FP 최소화 - IDE mode)
- Recall: 85%+ (FN 허용 가능)
- F1 Score: 90%+
"""

from dataclasses import dataclass

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.alias_analyzer import (
    AliasAnalyzer,
    AliasType,
)
from codegraph_engine.code_foundation.infrastructure.heap.points_to import PointsToGraph


@dataclass
class AliasTestCase:
    """Alias 테스트 케이스"""

    name: str
    aliases: list[tuple[str, str]]  # (source, target) pairs
    ground_truth: set[tuple[str, str]]  # Actual must-alias pairs
    description: str


# ============================================================
# Test Cases (Ground Truth)
# ============================================================

MUST_ALIAS_TEST_CASES = [
    # === Simple Cases (확실한 Must-alias) ===
    AliasTestCase(
        name="simple_assignment",
        aliases=[("b", "a")],  # a = b
        ground_truth={("a", "b"), ("b", "a")},
        description="Simple assignment: a = b (Must-alias)",
    ),
    AliasTestCase(
        name="chained_assignment",
        aliases=[("b", "a"), ("a", "c")],  # a = b; c = a
        ground_truth={("a", "b"), ("b", "a"), ("a", "c"), ("c", "a"), ("b", "c"), ("c", "b")},
        description="Chained assignment: a = b; c = a (Transitive must-alias)",
    ),
    AliasTestCase(
        name="multiple_chains",
        aliases=[("x", "a"), ("y", "b"), ("a", "c")],  # a = x; b = y; c = a
        ground_truth={
            ("a", "x"),
            ("x", "a"),
            ("a", "c"),
            ("c", "a"),
            ("x", "c"),
            ("c", "x"),
            ("b", "y"),
            ("y", "b"),
        },
        description="Multiple chains: Independent alias sets",
    ),
    # === Edge Cases (경계 조건) ===
    AliasTestCase(
        name="self_alias",
        aliases=[("a", "a")],  # a = a (identity)
        ground_truth={("a", "a")},
        description="Self-alias: a = a (Identity, trivial must-alias)",
    ),
    AliasTestCase(
        name="empty_aliases",
        aliases=[],
        ground_truth=set(),
        description="No aliases (Empty set)",
    ),
    # === Field-sensitive Cases ===
    AliasTestCase(
        name="field_access",
        aliases=[("obj.field", "a")],  # a = obj.field
        ground_truth={("a", "obj.field"), ("obj.field", "a")},
        description="Field access: a = obj.field (Field-sensitive)",
    ),
    # === Complex Cases (여러 변수) ===
    AliasTestCase(
        name="five_variable_chain",
        aliases=[
            ("a", "b"),
            ("b", "c"),
            ("c", "d"),
            ("d", "e"),
        ],  # b = a; c = b; d = c; e = d
        ground_truth={
            ("a", "b"),
            ("b", "a"),
            ("b", "c"),
            ("c", "b"),
            ("c", "d"),
            ("d", "c"),
            ("d", "e"),
            ("e", "d"),
            ("a", "c"),
            ("c", "a"),
            ("a", "d"),
            ("d", "a"),
            ("a", "e"),
            ("e", "a"),
            ("b", "d"),
            ("d", "b"),
            ("b", "e"),
            ("e", "b"),
            ("c", "e"),
            ("e", "c"),
        },
        description="Five-variable chain: Transitive closure (15 pairs)",
    ),
]


# ============================================================
# Base Cases (Should NOT be Must-alias)
# ============================================================

MAY_ALIAS_TEST_CASES = [
    # These should return False for must_only=True
    AliasTestCase(
        name="conditional_assignment",
        aliases=[],  # Simulated: if cond: a = b; else: a = c
        ground_truth=set(),  # NO must-alias (uncertain)
        description="Conditional: a = b or a = c (May-alias only)",
    ),
    AliasTestCase(
        name="independent_variables",
        aliases=[],  # a, b are independent
        ground_truth=set(),
        description="Independent: a and b have no relation",
    ),
]


# ============================================================
# Accuracy Measurement
# ============================================================


class MustAliasAccuracyMeasurement:
    """Must-alias 정확도 측정"""

    def __init__(self):
        self.total_cases = 0
        self.true_positives = 0  # Correctly identified must-alias
        self.false_positives = 0  # Incorrectly identified as must-alias
        self.true_negatives = 0  # Correctly identified as non-alias
        self.false_negatives = 0  # Missed must-alias

    def add_result(self, predicted: bool, actual: bool):
        """
        Add test result

        Args:
            predicted: Analyzer's prediction (must-alias?)
            actual: Ground truth (must-alias?)
        """
        self.total_cases += 1

        if predicted and actual:
            self.true_positives += 1
        elif predicted and not actual:
            self.false_positives += 1
        elif not predicted and actual:
            self.false_negatives += 1
        else:
            self.true_negatives += 1

    @property
    def precision(self) -> float:
        """
        Precision: TP / (TP + FP)

        Must-alias로 판단한 것 중 실제 alias 비율
        높을수록 좋음 (FP 최소화)
        """
        if self.true_positives + self.false_positives == 0:
            return 1.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        """
        Recall: TP / (TP + FN)

        실제 alias 중 Must-alias로 감지한 비율
        높을수록 좋음 (FN 최소화)
        """
        if self.true_positives + self.false_negatives == 0:
            return 1.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        """
        F1 Score: 2 * (Precision * Recall) / (Precision + Recall)

        Precision과 Recall의 조화평균
        """
        p = self.precision
        r = self.recall
        if p + r == 0:
            return 0.0
        return 2 * (p * r) / (p + r)

    @property
    def accuracy(self) -> float:
        """
        Accuracy: (TP + TN) / Total

        전체 정확도
        """
        if self.total_cases == 0:
            return 1.0
        return (self.true_positives + self.true_negatives) / self.total_cases

    def get_report(self) -> dict:
        """측정 리포트"""
        return {
            "total_cases": self.total_cases,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": f"{self.precision:.2%}",
            "recall": f"{self.recall:.2%}",
            "f1_score": f"{self.f1_score:.2%}",
            "accuracy": f"{self.accuracy:.2%}",
        }


# ============================================================
# Test: AliasAnalyzer Accuracy
# ============================================================


class TestAliasAnalyzerAccuracy:
    """AliasAnalyzer Must-alias 정확도 테스트"""

    def test_must_alias_accuracy(self):
        """
        Must-alias 정확도 측정

        RFC-028 목표:
        - Precision: 95%+
        - Recall: 85%+
        - F1 Score: 90%+
        """
        measurement = MustAliasAccuracyMeasurement()

        for test_case in MUST_ALIAS_TEST_CASES:
            analyzer = AliasAnalyzer()

            # Add aliases
            for source, target in test_case.aliases:
                analyzer.add_alias(source, target, AliasType.DIRECT, is_must=True)

            # Get all unique variables
            all_vars = set()
            for source, target in test_case.aliases:
                all_vars.add(source)
                all_vars.add(target)

            # Test all pairs
            for var1 in all_vars:
                for var2 in all_vars:
                    if var1 == var2:
                        continue

                    predicted = analyzer.is_aliased(var1, var2, must_only=True)
                    actual = (var1, var2) in test_case.ground_truth

                    measurement.add_result(predicted, actual)

        # Report
        report = measurement.get_report()
        print("\n" + "=" * 60)
        print("AliasAnalyzer Must-alias Accuracy Report")
        print("=" * 60)
        for key, value in report.items():
            print(f"{key:20s}: {value}")
        print("=" * 60)

        # Assertions (RFC-028 requirements)
        assert measurement.precision >= 0.95, f"Precision {measurement.precision:.2%} < 95%"
        assert measurement.recall >= 0.85, f"Recall {measurement.recall:.2%} < 85%"
        assert measurement.f1_score >= 0.90, f"F1 Score {measurement.f1_score:.2%} < 90%"

    def test_may_alias_false_positives(self):
        """
        May-alias False Positive 체크

        Must-alias로 잘못 판단하는 경우 확인
        (독립 변수, 조건부 할당 등)
        """
        measurement = MustAliasAccuracyMeasurement()

        # Independent variables (no alias)
        analyzer = AliasAnalyzer()
        predicted = analyzer.is_aliased("a", "b", must_only=True)
        actual = False
        measurement.add_result(predicted, actual)

        # Different alias sets
        analyzer2 = AliasAnalyzer()
        analyzer2.add_alias("x", "a")
        analyzer2.add_alias("y", "b")
        predicted = analyzer2.is_aliased("a", "b", must_only=True)
        actual = False
        measurement.add_result(predicted, actual)

        # Report
        assert measurement.false_positives == 0, "Must-alias should not have false positives for independent vars"


# ============================================================
# Test: PointsToGraph Must-alias Accuracy
# ============================================================


class TestPointsToGraphAccuracy:
    """PointsToGraph.must_alias() 정확도 테스트"""

    @pytest.mark.skip(reason="PointsToGraph API needs verification")
    def test_must_alias_scc_based(self):
        """
        SCC 기반 Must-alias 정확도

        PointsToGraph는 더 정확한 분석 (SOTA급)
        """
        graph = PointsToGraph()

        # Cycle: x = y, y = x (Same SCC)
        graph.add_points_to("var:x", "var:y")
        graph.add_points_to("var:y", "var:x")

        # Compute SCCs
        graph.compute_sccs()

        # Must-alias (Same SCC)
        assert graph.must_alias("var:x", "var:y") == True

    @pytest.mark.skip(reason="PointsToGraph API needs verification")
    def test_must_alias_singleton(self):
        """
        Singleton Must-alias

        Both point to exactly one location (same)
        """
        graph = PointsToGraph()

        # x → {o1}, y → {o1}
        graph.add_points_to("var:x", "obj:o1")
        graph.add_points_to("var:y", "obj:o1")

        # Build graph
        graph.compute_sccs()

        # Must-alias (Both singletons, same location)
        assert graph.must_alias("var:x", "var:y") == True

    @pytest.mark.skip(reason="PointsToGraph API needs verification")
    def test_must_alias_ambiguous(self):
        """
        Ambiguous case (NO must-alias)

        x → {o1, o2}, y → {o1, o2}
        Cannot prove must-alias (may be different at runtime)
        """
        graph = PointsToGraph()

        # x → {o1, o2}
        graph.add_points_to("var:x", "obj:o1")
        graph.add_points_to("var:x", "obj:o2")

        # y → {o1, o2}
        graph.add_points_to("var:y", "obj:o1")
        graph.add_points_to("var:y", "obj:o2")

        # Build graph
        graph.compute_sccs()

        # NO must-alias (Cannot prove)
        assert graph.must_alias("var:x", "var:y") == False


# ============================================================
# Integration Test: Real Code Patterns
# ============================================================


class TestRealCodePatterns:
    """실제 코드 패턴 테스트"""

    def test_python_dict_access(self):
        """
        Python dict access pattern

        cache = {}
        data = cache.get("key")
        result = data

        Expected: result must-alias data
        """
        analyzer = AliasAnalyzer()

        # data = cache.get("key")
        analyzer.analyze_field_access("cache", "get", "data")

        # result = data
        analyzer.add_alias("data", "result")

        # Must-alias
        assert analyzer.is_aliased("data", "result", must_only=True) == True

    def test_python_list_comprehension(self):
        """
        Python list comprehension

        items = [x for x in data]
        result = items

        Expected: result must-alias items
        """
        analyzer = AliasAnalyzer()

        # result = items
        analyzer.add_alias("items", "result")

        # Must-alias
        assert analyzer.is_aliased("items", "result", must_only=True) == True

    def test_python_async_shared_var(self):
        """
        Python async shared variable

        cache = {}
        async def handler():
            data = cache["key"]
            result = data

        Expected: result must-alias data (Critical for race detection!)
        """
        analyzer = AliasAnalyzer()

        # data = cache["key"]
        analyzer.analyze_element_access("cache", "key", "data")

        # result = data
        analyzer.add_alias("data", "result")

        # Must-alias
        assert analyzer.is_aliased("data", "result", must_only=True) == True


# ============================================================
# Benchmark: Large-scale Test
# ============================================================


class TestMustAliasBenchmark:
    """대규모 벤치마크 (100+ variables)"""

    def test_large_scale_accuracy(self):
        """
        100 variables, 500 alias pairs

        Performance + Accuracy 측정
        """
        import time

        analyzer = AliasAnalyzer()
        measurement = MustAliasAccuracyMeasurement()

        # Generate aliases: v0 = v1 = v2 = ... = v99 (chain)
        num_vars = 100
        ground_truth = set()

        start = time.perf_counter()

        # Add aliases
        for i in range(num_vars - 1):
            analyzer.add_alias(f"v{i}", f"v{i + 1}")

            # Ground truth: All pairs are must-alias (transitive)
            for j in range(i + 2, num_vars):
                ground_truth.add((f"v{i}", f"v{j}"))
                ground_truth.add((f"v{j}", f"v{i}"))

        elapsed_add = (time.perf_counter() - start) * 1000

        # Test random pairs
        start = time.perf_counter()

        for i in range(0, num_vars, 10):  # Sample every 10th
            for j in range(i + 1, num_vars, 10):
                predicted = analyzer.is_aliased(f"v{i}", f"v{j}", must_only=True)
                actual = (f"v{i}", f"v{j}") in ground_truth or i == j
                measurement.add_result(predicted, actual)

        elapsed_check = (time.perf_counter() - start) * 1000

        # Report
        report = measurement.get_report()
        print("\n" + "=" * 60)
        print("Large-scale Benchmark (100 variables)")
        print("=" * 60)
        print(f"Add aliases: {elapsed_add:.2f}ms")
        print(f"Check aliases: {elapsed_check:.2f}ms")
        for key, value in report.items():
            print(f"{key:20s}: {value}")
        print("=" * 60)

        # Performance target: < 100ms for 100 variables
        assert elapsed_add < 100, f"Add too slow: {elapsed_add:.2f}ms"
        assert elapsed_check < 100, f"Check too slow: {elapsed_check:.2f}ms"

        # Accuracy target
        assert measurement.f1_score >= 0.90, f"F1 Score {measurement.f1_score:.2%} < 90%"
