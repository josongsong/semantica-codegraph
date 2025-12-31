"""
Weight Presets Management

Intent별 최적 RRF weight 관리.

버전 관리:
- weights_v1.json, weights_v2.json
- 롤백 지원
- A/B 테스트 지원
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)
# 기본 presets (수동 설정)
DEFAULT_WEIGHT_PRESETS = {
    "IDENTIFIER": {
        "lexical": 0.1,
        "vector": 0.1,
        "symbol": 0.6,  # Symbol index가 강함
        "fuzzy": 0.1,
        "domain": 0.1,
    },
    "NATURAL_QUESTION": {
        "lexical": 0.2,
        "vector": 0.5,  # Vector search가 강함
        "symbol": 0.1,
        "fuzzy": 0.1,
        "domain": 0.1,
    },
    "ERROR_LOG": {
        "lexical": 0.3,
        "vector": 0.3,
        "symbol": 0.2,
        "fuzzy": 0.1,
        "domain": 0.1,
    },
    "CALLER_USAGE": {
        "lexical": 0.1,
        "vector": 0.2,
        "symbol": 0.5,  # Symbol graph 활용
        "fuzzy": 0.1,
        "domain": 0.1,
    },
    "DEFINITION": {
        "lexical": 0.2,
        "vector": 0.2,
        "symbol": 0.4,
        "fuzzy": 0.1,
        "domain": 0.1,
    },
    "IMPLEMENTATION": {
        "lexical": 0.2,
        "vector": 0.3,
        "symbol": 0.3,
        "fuzzy": 0.1,
        "domain": 0.1,
    },
    "DEFAULT": {
        "lexical": 0.2,
        "vector": 0.3,
        "symbol": 0.2,
        "fuzzy": 0.15,
        "domain": 0.15,
    },
}


@dataclass
class WeightPresetVersion:
    """
    Weight preset 버전.

    버전별로 weight를 관리하여 롤백/A/B 테스트 지원.
    """

    version: str
    """버전 ID (예: v1, v2, v3)"""

    presets: dict[str, dict[str, float]]
    """Intent별 weight presets"""

    baseline_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    """Intent별 baseline 성능"""

    created_at: datetime = field(default_factory=datetime.now)
    """생성 시각"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """추가 메타데이터 (튜닝 방법, 골든셋 크기 등)"""

    def to_dict(self) -> dict:
        """JSON 저장용."""
        return {
            "version": self.version,
            "presets": self.presets,
            "baseline_metrics": self.baseline_metrics,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WeightPresetVersion":
        """JSON 로드용."""
        return cls(
            version=data["version"],
            presets=data["presets"],
            baseline_metrics=data.get("baseline_metrics", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )


class WeightPresetManager:
    """
    Weight preset 관리자.

    기능:
    - 버전별 preset 저장/로드
    - 롤백
    - A/B 테스트 지원
    """

    def __init__(self, presets_dir: Path | str = "./.presets"):
        """
        Initialize preset manager.

        Args:
            presets_dir: Preset 파일 저장 디렉토리
        """
        self.presets_dir = Path(presets_dir)
        self.presets_dir.mkdir(exist_ok=True, parents=True)

        # 현재 active preset
        self._current_version: WeightPresetVersion | None = None

        # A/B 테스트용 (선택적)
        self._ab_test_version: WeightPresetVersion | None = None
        self._ab_test_ratio: float = 0.0  # 0.0 - 1.0

    def load_latest(self) -> WeightPresetVersion:
        """최신 버전 로드."""
        versions = self._list_versions()

        if not versions:
            # 기본 preset 생성
            logger.info("No saved presets, using defaults")
            return self._create_default_version()

        # 최신 버전 로드
        latest = versions[-1]
        return self.load_version(latest)

    def load_version(self, version: str) -> WeightPresetVersion:
        """특정 버전 로드."""
        file_path = self.presets_dir / f"weights_{version}.json"

        if not file_path.exists():
            logger.warning(f"Version {version} not found, using defaults")
            return self._create_default_version()

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        preset = WeightPresetVersion.from_dict(data)
        self._current_version = preset

        logger.info(f"Loaded weight preset version {version}")
        return preset

    def save_version(self, preset: WeightPresetVersion) -> None:
        """새 버전 저장."""
        file_path = self.presets_dir / f"weights_{preset.version}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(preset.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Saved weight preset version {preset.version}")

        # Current로 설정
        self._current_version = preset

    def get_weights(
        self,
        intent: str,
        ab_test_group: str | None = None,
    ) -> dict[str, float]:
        """
        Intent에 맞는 weight 가져오기.

        A/B 테스트 지원: ab_test_group에 따라 다른 버전 반환.

        Args:
            intent: QueryIntent
            ab_test_group: A/B 테스트 그룹 (None, "control", "treatment")

        Returns:
            Weight dict
        """
        # Current version 확보
        if not self._current_version:
            self._current_version = self.load_latest()

        # A/B 테스트: treatment group만 새 버전 사용
        if ab_test_group == "treatment" and self._ab_test_version:
            preset = self._ab_test_version
        else:
            # control group 또는 A/B 테스트 비활성화
            preset = self._current_version

        # Intent별 weight
        if intent in preset.presets:
            return preset.presets[intent].copy()

        # Fallback to DEFAULT
        if "DEFAULT" in preset.presets:
            logger.debug(f"No preset for {intent}, using DEFAULT")
            return preset.presets["DEFAULT"].copy()

        # Ultimate fallback
        logger.warning(f"No preset found for {intent}, using uniform")
        return {
            "lexical": 0.2,
            "vector": 0.2,
            "symbol": 0.2,
            "fuzzy": 0.2,
            "domain": 0.2,
        }

    def enable_ab_test(
        self,
        treatment_version: str,
        treatment_ratio: float = 0.1,
    ) -> None:
        """
        A/B 테스트 활성화.

        Args:
            treatment_version: 테스트할 새 버전
            treatment_ratio: Treatment 그룹 비율 (0.0 - 1.0)
        """
        # Treatment version 로드 (current_version 건드리지 않음)
        file_path = self.presets_dir / f"weights_{treatment_version}.json"

        if not file_path.exists():
            logger.error(f"Treatment version {treatment_version} not found")
            return

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        self._ab_test_version = WeightPresetVersion.from_dict(data)
        self._ab_test_ratio = treatment_ratio

        logger.info(f"A/B test enabled: {treatment_ratio * 100:.1f}% will use {treatment_version}")

    def disable_ab_test(self) -> None:
        """A/B 테스트 비활성화."""
        self._ab_test_version = None
        self._ab_test_ratio = 0.0
        logger.info("A/B test disabled")

    def _list_versions(self) -> list[str]:
        """저장된 버전 리스트."""
        version_files = sorted(self.presets_dir.glob("weights_*.json"))
        versions = [f.stem.replace("weights_", "") for f in version_files]
        return versions

    def _create_default_version(self) -> WeightPresetVersion:
        """기본 preset 생성."""
        return WeightPresetVersion(
            version="v0_default",
            presets=DEFAULT_WEIGHT_PRESETS.copy(),
            metadata={"source": "manual_defaults"},
        )

    def rollback_to_version(self, version: str) -> None:
        """특정 버전으로 롤백."""
        preset = self.load_version(version)
        self._current_version = preset
        logger.info(f"Rolled back to version {version}")


# Global manager instance
_preset_manager: WeightPresetManager | None = None


def get_preset_manager() -> WeightPresetManager:
    """Get global preset manager."""
    global _preset_manager
    if _preset_manager is None:
        _preset_manager = WeightPresetManager()
        _preset_manager.load_latest()
    return _preset_manager


def get_weights_for_intent(intent: str) -> dict[str, float]:
    """
    Intent에 맞는 weight 가져오기 (편의 함수).

    Args:
        intent: QueryIntent

    Returns:
        Weight dict
    """
    manager = get_preset_manager()
    return manager.get_weights(intent)
