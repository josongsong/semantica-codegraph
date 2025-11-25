"""
Hard Negative Mining

Collects hard negatives from user feedback for model improvement.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class TrainingSample:
    """
    Training sample with positive and hard negative examples.

    Attributes:
        query: User query
        positive_chunk_id: Chunk selected by user
        selected_rank: Rank of selected chunk (1-based)
        hard_negatives: Chunk IDs of hard negatives (ranked higher but not selected)
        timestamp: Sample collection timestamp
        metadata: Additional metadata
    """

    query: str
    positive_chunk_id: str
    selected_rank: int
    hard_negatives: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)


class RetrainingTrigger(Protocol):
    """Protocol for retraining triggers."""

    def trigger(self, training_data: list[TrainingSample]) -> None:
        """
        Trigger model retraining.

        Args:
            training_data: Collected training samples
        """
        ...


class HardNegativeMiner:
    """
    Collects hard negatives from user selections.

    Strategy (from 실행안):
    - Rank 5 이하 선택: 현재 검색 적절 (no collection)
    - Rank 10+ 선택: 상위 결과들이 모두 hard negative
    - 100개 쌓이면 re-training trigger
    """

    def __init__(
        self,
        storage_path: str = "data/hard_negatives.jsonl",
        min_rank_for_collection: int = 6,
        retraining_threshold: int = 100,
        retraining_trigger: RetrainingTrigger | None = None,
    ):
        """
        Initialize hard negative miner.

        Args:
            storage_path: Path to store training samples
            min_rank_for_collection: Minimum rank to trigger collection
            retraining_threshold: Number of samples before retraining
            retraining_trigger: Callback for retraining
        """
        self.storage_path = Path(storage_path)
        self.min_rank_for_collection = min_rank_for_collection
        self.retraining_threshold = retraining_threshold
        self.retraining_trigger = retraining_trigger

        # In-memory buffer
        self.training_data: list[TrainingSample] = []

        # Create storage directory
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data
        self._load_existing_data()

    def log_user_selection(
        self,
        query: str,
        shown_results: list[dict],  # List of {"chunk_id": ..., ...}
        selected_chunk_id: str,
        selected_rank: int,
    ) -> None:
        """
        Log user selection and collect hard negatives if applicable.

        Args:
            query: User query
            shown_results: List of chunks shown to user (ordered by rank)
            selected_chunk_id: Chunk ID selected by user
            selected_rank: Rank of selected chunk (1-based)
        """
        # Check if collection is warranted
        if selected_rank < self.min_rank_for_collection:
            logger.debug(
                f"User selected rank {selected_rank} - no hard negative collection "
                f"(threshold: {self.min_rank_for_collection})"
            )
            return

        # Collect hard negatives (chunks ranked higher but not selected)
        hard_negatives = []

        for i, result in enumerate(shown_results[:selected_rank], start=1):
            chunk_id = result.get("chunk_id", "")
            if chunk_id and chunk_id != selected_chunk_id:
                hard_negatives.append(chunk_id)

        if not hard_negatives:
            logger.warning("No hard negatives found despite high rank selection")
            return

        # Create training sample
        sample = TrainingSample(
            query=query,
            positive_chunk_id=selected_chunk_id,
            selected_rank=selected_rank,
            hard_negatives=hard_negatives,
            metadata={
                "total_shown": len(shown_results),
                "num_hard_negatives": len(hard_negatives),
            },
        )

        # Add to buffer
        self.training_data.append(sample)

        # Persist to disk
        self._append_to_storage(sample)

        logger.info(
            f"Collected hard negatives: query='{query[:50]}...', "
            f"rank={selected_rank}, hard_negatives={len(hard_negatives)}, "
            f"total_samples={len(self.training_data)}"
        )

        # Check if retraining threshold reached
        if len(self.training_data) >= self.retraining_threshold:
            logger.info(
                f"Retraining threshold reached ({len(self.training_data)} samples) "
                f"- triggering retraining"
            )
            self._trigger_retraining()

    def get_training_data(self) -> list[TrainingSample]:
        """
        Get collected training samples.

        Returns:
            List of training samples
        """
        return self.training_data.copy()

    def clear_training_data(self) -> None:
        """Clear in-memory training data (after successful retraining)."""
        self.training_data.clear()
        logger.info("Cleared in-memory training data")

    def _load_existing_data(self) -> None:
        """Load existing training data from disk."""
        if not self.storage_path.exists():
            logger.info(f"No existing training data at {self.storage_path}")
            return

        try:
            with open(self.storage_path) as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        sample = TrainingSample(**data)
                        self.training_data.append(sample)

            logger.info(
                f"Loaded {len(self.training_data)} existing training samples "
                f"from {self.storage_path}"
            )
        except Exception as e:
            logger.error(f"Error loading training data: {e}")

    def _append_to_storage(self, sample: TrainingSample) -> None:
        """Append training sample to storage file."""
        try:
            with open(self.storage_path, "a") as f:
                f.write(json.dumps(asdict(sample)) + "\n")
        except Exception as e:
            logger.error(f"Error appending to storage: {e}")

    def _trigger_retraining(self) -> None:
        """Trigger model retraining if configured."""
        if self.retraining_trigger:
            try:
                self.retraining_trigger.trigger(self.training_data)
                logger.info("Retraining triggered successfully")
            except Exception as e:
                logger.error(f"Error triggering retraining: {e}")
        else:
            logger.warning("Retraining trigger not configured - skipping automatic retraining")

    def export_for_training(self, output_path: str) -> None:
        """
        Export training data in format suitable for model training.

        Args:
            output_path: Path to export training data
        """
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path_obj, "w") as f:
            json.dump([asdict(sample) for sample in self.training_data], f, indent=2)

        logger.info(f"Exported {len(self.training_data)} samples to {output_path}")
