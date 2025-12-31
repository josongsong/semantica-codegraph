"""
Golden Set Management

검색 품질 평가를 위한 골든셋 관리.

골든셋 구조:
- 쿼리 + Intent
- 정답 문서/심볼 리스트
- Relevance 점수 (optional)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GoldenSetItem:
    """
    골든셋 단일 항목.

    쿼리에 대한 정답 문서/심볼 정의.
    """

    query: str
    """검색 쿼리"""

    intent: str
    """QueryIntent"""

    gold_ids: list[str]
    """정답 chunk/symbol ID 리스트"""

    relevance_scores: dict[str, float] = field(default_factory=dict)
    """ID별 relevance 점수 (0-3: 0=irrelevant, 3=perfect)"""

    repo_id: str | None = None
    """레포지토리 ID (특정 레포용)"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """추가 메타데이터"""

    def to_dict(self) -> dict:
        """JSON 저장용."""
        return {
            "query": self.query,
            "intent": self.intent,
            "gold_ids": self.gold_ids,
            "relevance_scores": self.relevance_scores,
            "repo_id": self.repo_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GoldenSetItem":
        """JSON 로드용."""
        return cls(
            query=data["query"],
            intent=data["intent"],
            gold_ids=data["gold_ids"],
            relevance_scores=data.get("relevance_scores", {}),
            repo_id=data.get("repo_id"),
            metadata=data.get("metadata", {}),
        )


class GoldenSet:
    """
    골든셋 컬렉션.

    Intent별로 쿼리-정답 쌍을 관리.
    """

    def __init__(self, items: list[GoldenSetItem] | None = None):
        """
        Initialize golden set.

        Args:
            items: 골든셋 항목 리스트
        """
        self.items = items or []

    def add_item(self, item: GoldenSetItem) -> None:
        """항목 추가."""
        self.items.append(item)

    def get_by_intent(self, intent: str) -> list[GoldenSetItem]:
        """Intent별 필터링."""
        return [item for item in self.items if item.intent == intent]

    def get_by_repo(self, repo_id: str) -> list[GoldenSetItem]:
        """Repo별 필터링."""
        return [item for item in self.items if item.repo_id is None or item.repo_id == repo_id]

    def group_by_intent(self) -> dict[str, list[GoldenSetItem]]:
        """Intent별 그룹화."""
        groups: dict[str, list[GoldenSetItem]] = {}
        for item in self.items:
            if item.intent not in groups:
                groups[item.intent] = []
            groups[item.intent].append(item)
        return groups

    def save(self, file_path: Path | str) -> None:
        """JSON 파일로 저장."""
        file_path = Path(file_path)

        data = {
            "version": "1.0",
            "items": [item.to_dict() for item in self.items],
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, file_path: Path | str) -> "GoldenSet":
        """JSON 파일에서 로드."""
        file_path = Path(file_path)

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        items = [GoldenSetItem.from_dict(item) for item in data["items"]]
        return cls(items=items)

    def __len__(self) -> int:
        """항목 개수."""
        return len(self.items)

    def stats(self) -> dict[str, int]:
        """Intent별 통계."""
        groups = self.group_by_intent()
        return {intent: len(items) for intent, items in groups.items()}


class GoldenSetBuilder:
    """
    골든셋 빌더.

    로그에서 골든셋 생성 또는 수동 추가.
    """

    def __init__(self):
        self.golden_set = GoldenSet()

    def add_from_log(
        self,
        query: str,
        intent: str,
        clicked_hit_id: str,
        resolved: bool,
        repo_id: str | None = None,
    ) -> None:
        """
        로그에서 골든셋 항목 생성.

        조건:
        - 클릭 있음
        - 해결됨 (resolved=True)
        - Dwell time > 10초 (optional)

        Args:
            query: 쿼리
            intent: Intent
            clicked_hit_id: 클릭된 결과
            resolved: 해결 여부
            repo_id: 레포 ID
        """
        if not resolved:
            # 해결 안 된 경우 골든셋에 추가 안 함
            return

        # 기존 항목 찾기
        existing = next((item for item in self.golden_set.items if item.query == query and item.intent == intent), None)

        if existing:
            # 기존 항목에 정답 추가
            if clicked_hit_id not in existing.gold_ids:
                existing.gold_ids.append(clicked_hit_id)
                existing.relevance_scores[clicked_hit_id] = 3.0  # Perfect match
        else:
            # 새 항목 생성
            item = GoldenSetItem(
                query=query,
                intent=intent,
                gold_ids=[clicked_hit_id],
                relevance_scores={clicked_hit_id: 3.0},
                repo_id=repo_id,
            )
            self.golden_set.add_item(item)

    def add_manual(
        self,
        query: str,
        intent: str,
        gold_ids: list[str],
        relevance_scores: dict[str, float] | None = None,
        repo_id: str | None = None,
    ) -> None:
        """
        수동으로 골든셋 항목 추가.

        Args:
            query: 쿼리
            intent: Intent
            gold_ids: 정답 ID 리스트
            relevance_scores: ID별 relevance (0-3)
            repo_id: 레포 ID
        """
        item = GoldenSetItem(
            query=query,
            intent=intent,
            gold_ids=gold_ids,
            relevance_scores=relevance_scores or {},
            repo_id=repo_id,
        )
        self.golden_set.add_item(item)

    def build(self) -> GoldenSet:
        """완성된 골든셋 반환."""
        return self.golden_set
