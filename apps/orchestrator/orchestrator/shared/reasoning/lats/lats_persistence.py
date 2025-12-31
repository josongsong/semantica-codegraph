"""
LATS Tree Persistence (v9 Advanced)

Graph DB 기반 Tree 저장/복원

EXTREME-ADDENDUM P2 항목
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from .lats_models import LATSNode, LATSSearchMetrics

logger = logging.getLogger(__name__)


class LATSTreePersistence:
    """
    LATS Tree Persistence (Domain Service)

    책임:
    1. Tree를 직렬화하여 저장
    2. 저장된 Tree 복원
    3. Crash Recovery

    SOTA:
    - JSON 직렬화 (간단)
    - Graph DB (선택, Redis/PostgreSQL JSONB)

    효과:
    - Pause & Resume
    - Crash Recovery
    - Time-Travel Debugging

    EXTREME-ADDENDUM P2
    """

    def __init__(self, storage_dir: str = "data/lats/trees"):
        """
        Args:
            storage_dir: Tree 저장 디렉토리
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"LATSTreePersistence initialized: {self.storage_dir}")

    def save_tree(
        self,
        root: LATSNode,
        search_id: str,
        metrics: LATSSearchMetrics,
    ) -> str:
        """
        Tree 저장

        Args:
            root: Root 노드
            search_id: Search ID
            metrics: Search 메트릭

        Returns:
            저장 파일 경로
        """
        logger.debug(f"Saving tree: {search_id}")

        # Tree 직렬화
        tree_data = {
            "search_id": search_id,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics.to_dict(),
            "tree": self._serialize_node(root),
        }

        # 파일명
        filename = f"{search_id}.json"
        filepath = self.storage_dir / filename

        # JSON 저장
        filepath.write_text(json.dumps(tree_data, indent=2, ensure_ascii=False))

        logger.info(f"Tree saved: {filepath}")

        return str(filepath)

    def load_tree(self, search_id: str) -> tuple[LATSNode, LATSSearchMetrics]:
        """
        Tree 복원

        Args:
            search_id: Search ID

        Returns:
            (Root 노드, Metrics)
        """
        logger.debug(f"Loading tree: {search_id}")

        # 파일 경로
        filename = f"{search_id}.json"
        filepath = self.storage_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Tree not found: {search_id}")

        # JSON 로드
        tree_data = json.loads(filepath.read_text())

        # Tree 복원
        root = self._deserialize_node(tree_data["tree"])

        # Metrics 복원
        metrics = self._deserialize_metrics(tree_data["metrics"])

        logger.info(f"Tree loaded: {search_id}")

        return root, metrics

    def list_saved_trees(self, limit: int = 10) -> list[dict]:
        """
        저장된 Tree 목록

        Args:
            limit: 최대 개수

        Returns:
            Tree 메타데이터 리스트
        """
        trees = []

        for filepath in sorted(self.storage_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                data = json.loads(filepath.read_text())
                trees.append(
                    {
                        "search_id": data["search_id"],
                        "timestamp": data["timestamp"],
                        "iterations": data["metrics"]["iterations"],
                        "nodes": data["metrics"]["nodes_created"],
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to load tree metadata: {filepath}, {e}")

        return trees

    def delete_tree(self, search_id: str):
        """
        Tree 삭제

        Args:
            search_id: Search ID
        """
        filename = f"{search_id}.json"
        filepath = self.storage_dir / filename

        if filepath.exists():
            filepath.unlink()
            logger.info(f"Tree deleted: {search_id}")

    # ========================================================================
    # Serialization
    # ========================================================================

    def _serialize_node(self, node: LATSNode) -> dict:
        """
        노드 직렬화 (재귀)

        Args:
            node: LATSNode

        Returns:
            딕셔너리
        """
        return {
            "node_id": node.node_id,
            "partial_thought": node.partial_thought,
            "thought_diff": node.thought_diff,
            "depth": node.depth,
            "visit_count": node.visit_count,
            "total_value": node.total_value,
            "q_value": node.q_value,
            "thought_score": node.thought_score,
            "is_promising": node.is_promising,
            "is_terminal": node.is_terminal,
            "rejected_reasons": node.rejected_reasons,
            "children": [self._serialize_node(c) for c in node.children],
            # completed_strategy는 너무 크므로 생략 (TODO: 별도 저장)
        }

    def _deserialize_node(
        self,
        data: dict,
        parent: LATSNode | None = None,
    ) -> LATSNode:
        """
        노드 복원 (재귀)

        Args:
            data: 직렬화된 데이터
            parent: 부모 노드

        Returns:
            LATSNode
        """
        node = LATSNode(
            node_id=data["node_id"],
            parent=parent,
            partial_thought=data["partial_thought"],
            thought_diff=data["thought_diff"],
            depth=data["depth"],
            visit_count=data["visit_count"],
            total_value=data["total_value"],
            q_value=data["q_value"],
            thought_score=data["thought_score"],
            is_promising=data["is_promising"],
            is_terminal=data["is_terminal"],
            rejected_reasons=data.get("rejected_reasons", []),
        )

        # 자식 복원
        for child_data in data.get("children", []):
            child = self._deserialize_node(child_data, parent=node)
            node.children.append(child)

        return node

    def _deserialize_metrics(self, data: dict) -> LATSSearchMetrics:
        """
        Metrics 복원

        Args:
            data: 직렬화된 Metrics

        Returns:
            LATSSearchMetrics
        """
        metrics = LATSSearchMetrics(
            total_tokens_used=data.get("total_tokens", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            iterations_completed=data.get("iterations", 0),
            nodes_created=data.get("nodes_created", 0),
            nodes_pruned=data.get("nodes_pruned", 0),
            duplicates_removed=data.get("duplicates_removed", 0),
        )

        return metrics
