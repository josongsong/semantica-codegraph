"""
Effect Analyzer Adapter

Infrastructure EffectDiffer를 Port로 래핑
"""

from ..domain.effect_models import EffectDiff
from ..infrastructure.semantic_diff.effect_differ import EffectDiffer


class EffectAnalyzerAdapter:
    """
    EffectDiffer Adapter

    Infrastructure → Port 브릿지
    """

    def __init__(self):
        """Initialize adapter"""
        self._differ = EffectDiffer()

    def compare(
        self,
        symbol_id: str,
        old_code: str,
        new_code: str,
    ) -> EffectDiff:
        """Effect 비교 (Port 메서드)"""
        return self._differ.compare(symbol_id, old_code, new_code)

    def batch_compare(
        self,
        changes: dict[str, tuple[str, str]],
    ) -> list[EffectDiff]:
        """Batch effect 비교 (Port 메서드)"""
        return self._differ.batch_compare(changes)

    def get_breaking_changes(
        self,
        diffs: list[EffectDiff],
    ) -> list[EffectDiff]:
        """Breaking changes 필터링 (Port 메서드)"""
        return self._differ.get_breaking_changes(diffs)


# Type check
def _type_check() -> None:
    EffectAnalyzerAdapter()
