"""
Adaptation Example Collector

Collects positive and negative examples for LoRA training.
"""

from datetime import datetime

from codegraph_ml.adaptive_embeddings.models import AdaptationExample, AdaptationStatus


class AdaptationCollector:
    """
    Collects examples for repo-adaptive embeddings.

    Tracks user interactions and builds training dataset for LoRA.
    """

    def __init__(
        self,
        min_samples_for_adaptation: int = 100,
        max_samples_per_repo: int = 5000,
    ):
        """
        Initialize collector.

        Args:
            min_samples_for_adaptation: Minimum samples before adaptation
            max_samples_per_repo: Maximum samples to keep per repo
        """
        self.min_samples = min_samples_for_adaptation
        self.max_samples = max_samples_per_repo
        self.examples: dict[str, list[AdaptationExample]] = {}

    def log_user_selection(
        self,
        repo_id: str,
        query: str,
        shown_results: list[dict],
        selected_chunk_id: str,
        selected_rank: int,
    ):
        """
        Log a user selection as a training example.

        Args:
            repo_id: Repository identifier
            query: User query
            shown_results: Results that were shown
            selected_chunk_id: Chunk the user selected
            selected_rank: Rank of selected chunk (1-indexed)
        """
        # Collect negative examples (results ranked above selection)
        negative_chunk_ids = []
        for i, result in enumerate(shown_results):
            if i + 1 < selected_rank:
                chunk_id = result.get("chunk_id")
                if chunk_id and chunk_id != selected_chunk_id:
                    negative_chunk_ids.append(chunk_id)

        # Create example
        example = AdaptationExample(
            query=query,
            positive_chunk_id=selected_chunk_id,
            negative_chunk_ids=negative_chunk_ids,
            repo_id=repo_id,
            timestamp=datetime.now(),
            metadata={"selected_rank": selected_rank},
        )

        # Add to collection
        if repo_id not in self.examples:
            self.examples[repo_id] = []

        self.examples[repo_id].append(example)

        # Trim if exceeds max
        if len(self.examples[repo_id]) > self.max_samples:
            # Keep most recent samples
            self.examples[repo_id] = self.examples[repo_id][-self.max_samples :]

    def log_implicit_negative(
        self,
        repo_id: str,
        query: str,
        shown_results: list[dict],
    ):
        """
        Log implicit negatives (query with no selection).

        If user doesn't select anything, top results are weak negatives.

        Args:
            repo_id: Repository identifier
            query: User query
            shown_results: Results that were shown but not selected
        """
        # Use top results as weak negatives
        negative_chunk_ids = [r.get("chunk_id") for r in shown_results[:5] if r.get("chunk_id")]

        if not negative_chunk_ids:
            return

        # Create example with no positive (only negatives)
        example = AdaptationExample(
            query=query,
            positive_chunk_id="",  # No positive
            negative_chunk_ids=negative_chunk_ids,
            repo_id=repo_id,
            timestamp=datetime.now(),
            metadata={"implicit_negative": True},
        )

        if repo_id not in self.examples:
            self.examples[repo_id] = []

        self.examples[repo_id].append(example)

    def get_status(self, repo_id: str) -> AdaptationStatus:
        """
        Get adaptation status for a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            Status object
        """
        examples = self.examples.get(repo_id, [])
        samples_collected = len(examples)

        # Check if ready for adaptation
        is_adapted = samples_collected >= self.min_samples

        # Find last adaptation time (if any)
        last_adaptation = None
        if examples:
            # Use timestamp of earliest example as proxy
            last_adaptation = min(ex.timestamp for ex in examples)

        return AdaptationStatus(
            repo_id=repo_id,
            is_adapted=is_adapted,
            samples_collected=samples_collected,
            samples_required=self.min_samples,
            last_adaptation=last_adaptation,
            adaptation_quality=0.0,  # Computed after training
        )

    def get_training_examples(self, repo_id: str, min_samples: int | None = None) -> list[AdaptationExample]:
        """
        Get training examples for a repository.

        Args:
            repo_id: Repository identifier
            min_samples: Minimum number of samples (uses default if None)

        Returns:
            List of examples, or empty if not ready
        """
        examples = self.examples.get(repo_id, [])
        min_required = min_samples or self.min_samples

        if len(examples) < min_required:
            return []

        # Filter out examples with no positives (implicit negatives only)
        return [ex for ex in examples if ex.positive_chunk_id]

    def clear_examples(self, repo_id: str):
        """Clear collected examples for a repository."""
        if repo_id in self.examples:
            del self.examples[repo_id]

    def get_all_repo_ids(self) -> list[str]:
        """Get all repository IDs with collected examples."""
        return list(self.examples.keys())
