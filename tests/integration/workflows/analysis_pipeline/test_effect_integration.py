"""
Effect System Integration Tests
"""

import pytest

from src.contexts.reasoning_engine.domain.effect_models import EffectDiff, EffectType
from src.contexts.reasoning_engine.infrastructure.semantic_diff.effect_analyzer import EffectAnalyzer
from src.contexts.reasoning_engine.infrastructure.semantic_diff.effect_differ import EffectDiffer


class TestEffectAnalysis:
    """Effect 분석 테스트"""

    def test_pure_function(self):
        """Pure function 감지"""
        analyzer = EffectAnalyzer()

        code = "def add(x, y): return x + y"
        effect = analyzer.analyze_code(code, "add")

        assert effect.is_pure()
        assert EffectType.PURE in effect.effects

    def test_io_function(self):
        """I/O effect 감지"""
        analyzer = EffectAnalyzer()

        code = "def log(msg):\n    print(msg)"
        effect = analyzer.analyze_code(code, "log")

        assert effect.has_side_effect()
        assert effect.includes(EffectType.IO)

    def test_global_mutation(self):
        """Global mutation 감지"""
        analyzer = EffectAnalyzer()

        code = "def inc():\n    global COUNT\n    COUNT += 1"
        effect = analyzer.analyze_code(code, "inc")

        assert effect.includes(EffectType.GLOBAL_MUTATION)
        assert not effect.idempotent

    def test_database_write(self):
        """Database write 감지"""
        analyzer = EffectAnalyzer()

        code = "def save(x):\n    db.insert(x)"
        effect = analyzer.analyze_code(code, "save")

        assert effect.includes(EffectType.DB_WRITE)


class TestEffectDiff:
    """Effect diff 테스트"""

    def test_pure_to_mutation_breaking(self):
        """Pure → Global mutation = BREAKING"""
        diff = EffectDiff(symbol_id="func", before={EffectType.PURE}, after={EffectType.GLOBAL_MUTATION})

        assert diff.is_breaking
        assert diff.severity == "critical"
        assert EffectType.GLOBAL_MUTATION in diff.added

    def test_no_change_safe(self):
        """변화 없으면 safe"""
        diff = EffectDiff(symbol_id="func", before={EffectType.IO}, after={EffectType.IO})

        assert not diff.has_changes()
        assert diff.is_safe()
        assert diff.severity == "none"

    def test_io_to_pure_safe(self):
        """Side-effect 제거 = safe"""
        diff = EffectDiff(symbol_id="func", before={EffectType.IO}, after={EffectType.PURE})

        assert not diff.is_breaking
        assert diff.severity == "low"
        assert EffectType.IO in diff.removed


class TestEffectDiffer:
    """EffectDiffer 통합 테스트"""

    def test_compare_codes(self):
        """코드 비교"""
        differ = EffectDiffer()

        before = "def func(): return 1"
        after = "def func():\n    print('debug')\n    return 1"

        diff = differ.compare(before, after, "func")

        assert diff.has_changes()
        assert EffectType.IO in diff.added

    def test_batch_compare(self):
        """여러 함수 동시 비교"""
        differ = EffectDiffer()

        changes = {
            "f1": ("def f1(): return 1", "def f1(): print(1); return 1"),
            "f2": ("def f2(): x = 1", "def f2(): x = 1"),
        }

        diffs = differ.batch_compare(changes)

        assert len(diffs) == 2

        # f1: IO 추가
        f1_diff = [d for d in diffs if d.symbol_id == "f1"][0]
        assert f1_diff.has_changes()

        # f2: 변화 없음
        f2_diff = [d for d in diffs if d.symbol_id == "f2"][0]
        assert not f2_diff.has_changes()

    def test_get_breaking_changes(self):
        """Breaking changes 추출"""
        differ = EffectDiffer()

        changes = {
            "f1": ("def f1(): return 1", "def f1(): print(1); return 1"),  # Pure→IO (breaking)
            "f2": ("def f2(): return 2", "def f2():\n    global X\n    X += 1\n    return 2"),  # Pure→Global (breaking)
            "f3": ("def f3(): print(1)", "def f3(): print(1); print(2)"),  # IO→IO (safe)
        }

        diffs = differ.batch_compare(changes)
        breaking = differ.get_breaking_changes(diffs)

        # f1, f2 are breaking (Pure → side-effect)
        assert len(breaking) == 2
        assert {d.symbol_id for d in breaking} == {"f1", "f2"}

    def test_summarize(self):
        """Diff 요약"""
        differ = EffectDiffer()

        diffs = [
            EffectDiff("f1", {EffectType.PURE}, {EffectType.PURE}),  # none
            EffectDiff("f2", {EffectType.PURE}, {EffectType.IO}),  # high
            EffectDiff("f3", {EffectType.PURE}, {EffectType.GLOBAL_MUTATION}),  # critical
        ]

        # Verify individual severities
        assert diffs[0].severity == "none"
        assert diffs[1].severity == "high"
        assert diffs[2].severity == "critical"

        summary = differ.summarize(diffs)

        assert summary["none"] == 1
        assert summary["high"] == 1
        assert summary["critical"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
