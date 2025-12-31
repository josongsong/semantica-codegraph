"""
Feedback Collector

사용자 피드백을 수집하고 관리합니다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FeedbackType(str, Enum):
    """피드백 타입"""

    TRUE_POSITIVE = "tp"  # 실제 취약점
    FALSE_POSITIVE = "fp"  # 오탐
    UNSURE = "unsure"  # 불확실
    DEFERRED = "deferred"  # 나중에 확인


@dataclass
class UserFeedback:
    """사용자 피드백"""

    # 식별자
    feedback_id: str
    rule_id: str
    file_path: str
    line: int

    # 피드백 내용
    feedback_type: FeedbackType
    reason: str = ""

    # 메타데이터
    timestamp: float = field(default_factory=time.time)
    user_id: str = ""
    code_snippet: str = ""

    # 매치 정보
    match_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_false_positive(self) -> bool:
        return self.feedback_type == FeedbackType.FALSE_POSITIVE

    @property
    def is_true_positive(self) -> bool:
        return self.feedback_type == FeedbackType.TRUE_POSITIVE

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        d = asdict(self)
        d["feedback_type"] = self.feedback_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserFeedback:
        """딕셔너리에서 생성"""
        data = data.copy()
        data["feedback_type"] = FeedbackType(data["feedback_type"])
        return cls(**data)


class FeedbackCollector:
    """피드백 수집기"""

    def __init__(
        self,
        storage_path: str | Path | None = None,
    ) -> None:
        """
        Args:
            storage_path: 피드백 저장 경로 (JSON 파일)
        """
        self._feedbacks: list[UserFeedback] = []
        self._storage_path = Path(storage_path) if storage_path else None

        # 저장소에서 로드
        if self._storage_path and self._storage_path.exists():
            self._load()

    def add_feedback(
        self,
        rule_id: str,
        file_path: str,
        line: int,
        feedback_type: FeedbackType | str,
        reason: str = "",
        code_snippet: str = "",
        user_id: str = "",
        match_data: dict[str, Any] | None = None,
    ) -> UserFeedback:
        """
        피드백 추가

        Args:
            rule_id: 규칙 ID
            file_path: 파일 경로
            line: 라인 번호
            feedback_type: 피드백 타입
            reason: 사유
            code_snippet: 코드 스니펫
            user_id: 사용자 ID
            match_data: 매치 데이터

        Returns:
            UserFeedback: 생성된 피드백
        """
        if isinstance(feedback_type, str):
            feedback_type = FeedbackType(feedback_type)

        feedback = UserFeedback(
            feedback_id=f"{rule_id}:{file_path}:{line}:{int(time.time())}",
            rule_id=rule_id,
            file_path=file_path,
            line=line,
            feedback_type=feedback_type,
            reason=reason,
            code_snippet=code_snippet,
            user_id=user_id,
            match_data=match_data or {},
        )

        self._feedbacks.append(feedback)
        self._save()

        return feedback

    def mark_as_false_positive(
        self,
        rule_id: str,
        file_path: str,
        line: int,
        reason: str = "",
    ) -> UserFeedback:
        """False Positive로 마킹"""
        return self.add_feedback(
            rule_id=rule_id,
            file_path=file_path,
            line=line,
            feedback_type=FeedbackType.FALSE_POSITIVE,
            reason=reason,
        )

    def mark_as_true_positive(
        self,
        rule_id: str,
        file_path: str,
        line: int,
        reason: str = "",
    ) -> UserFeedback:
        """True Positive로 마킹"""
        return self.add_feedback(
            rule_id=rule_id,
            file_path=file_path,
            line=line,
            feedback_type=FeedbackType.TRUE_POSITIVE,
            reason=reason,
        )

    def get_all(self) -> list[UserFeedback]:
        """모든 피드백 반환"""
        return self._feedbacks.copy()

    def get_by_rule(self, rule_id: str) -> list[UserFeedback]:
        """규칙별 피드백"""
        return [f for f in self._feedbacks if f.rule_id == rule_id]

    def get_by_file(self, file_path: str) -> list[UserFeedback]:
        """파일별 피드백"""
        return [f for f in self._feedbacks if f.file_path == file_path]

    def get_false_positives(self) -> list[UserFeedback]:
        """False Positive만"""
        return [f for f in self._feedbacks if f.is_false_positive]

    def get_true_positives(self) -> list[UserFeedback]:
        """True Positive만"""
        return [f for f in self._feedbacks if f.is_true_positive]

    def get_recent(self, limit: int = 100) -> list[UserFeedback]:
        """최근 피드백"""
        sorted_feedbacks = sorted(
            self._feedbacks,
            key=lambda f: f.timestamp,
            reverse=True,
        )
        return sorted_feedbacks[:limit]

    def get_fp_rate_by_rule(self) -> dict[str, float]:
        """규칙별 FP율"""
        rule_stats: dict[str, dict[str, int]] = {}

        for feedback in self._feedbacks:
            if feedback.rule_id not in rule_stats:
                rule_stats[feedback.rule_id] = {"tp": 0, "fp": 0}

            if feedback.is_false_positive:
                rule_stats[feedback.rule_id]["fp"] += 1
            elif feedback.is_true_positive:
                rule_stats[feedback.rule_id]["tp"] += 1

        fp_rates: dict[str, float] = {}
        for rule_id, stats in rule_stats.items():
            total = stats["tp"] + stats["fp"]
            if total > 0:
                fp_rates[rule_id] = stats["fp"] / total
            else:
                fp_rates[rule_id] = 0.0

        return fp_rates

    def get_fp_rate_by_file(self) -> dict[str, float]:
        """파일별 FP율"""
        file_stats: dict[str, dict[str, int]] = {}

        for feedback in self._feedbacks:
            if feedback.file_path not in file_stats:
                file_stats[feedback.file_path] = {"tp": 0, "fp": 0}

            if feedback.is_false_positive:
                file_stats[feedback.file_path]["fp"] += 1
            elif feedback.is_true_positive:
                file_stats[feedback.file_path]["tp"] += 1

        fp_rates: dict[str, float] = {}
        for file_path, stats in file_stats.items():
            total = stats["tp"] + stats["fp"]
            if total > 0:
                fp_rates[file_path] = stats["fp"] / total
            else:
                fp_rates[file_path] = 0.0

        return fp_rates

    def count(self) -> int:
        """총 피드백 수"""
        return len(self._feedbacks)

    def clear(self) -> None:
        """모든 피드백 삭제"""
        self._feedbacks.clear()
        self._save()

    def __len__(self) -> int:
        return len(self._feedbacks)

    def __iter__(self) -> Iterator[UserFeedback]:
        return iter(self._feedbacks)

    def _save(self) -> None:
        """저장소에 저장"""
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = [f.to_dict() for f in self._feedbacks]
        with open(self._storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """저장소에서 로드"""
        if self._storage_path is None or not self._storage_path.exists():
            return

        # 빈 파일 처리
        if self._storage_path.stat().st_size == 0:
            return

        with open(self._storage_path) as f:
            data = json.load(f)

        self._feedbacks = [UserFeedback.from_dict(d) for d in data]
