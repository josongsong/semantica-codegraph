"""
Feedback Batch Processor for Weight Learning

Processes unprocessed feedback logs from DB and feeds them to the weight learner.

Usage:
    # As standalone script
    python -m src.retriever.adaptive.feedback_processor

    # Or programmatically
    from codegraph_search.infrastructure.adaptive.feedback_processor import FeedbackProcessor
    processor = FeedbackProcessor(postgres_store, weight_learner)
    await processor.process_batch()
"""

import asyncio
from typing import Any

from codegraph_search.infrastructure.adaptive.weight_learner import AdaptiveWeightLearner, FeedbackSignal
from codegraph_search.infrastructure.evaluation.feedback_service import FeedbackService
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class FeedbackProcessor:
    """
    Processes feedback logs for weight learning.

    Reads unprocessed feedback from DB and updates weight learner.
    """

    def __init__(
        self,
        feedback_service: FeedbackService,
        weight_learner: AdaptiveWeightLearner,
        batch_size: int = 100,
    ):
        """
        Initialize processor.

        Args:
            feedback_service: Feedback service for DB access
            weight_learner: Weight learner to update
            batch_size: Number of feedback logs to process per batch
        """
        self.feedback_service = feedback_service
        self.weight_learner = weight_learner
        self.batch_size = batch_size

    async def process_batch(self, mark_processed: bool = True) -> dict[str, Any]:
        """
        Process one batch of unprocessed feedback.

        Args:
            mark_processed: Whether to mark feedback as processed after learning

        Returns:
            Processing statistics
        """
        logger.info("Starting feedback batch processing")

        # Get unprocessed feedback
        feedbacks = await self.feedback_service.list_unprocessed_feedback(limit=self.batch_size)

        if not feedbacks:
            logger.info("No unprocessed feedback found")
            return {
                "processed_count": 0,
                "skipped_count": 0,
                "error_count": 0,
            }

        processed = 0
        skipped = 0
        errors = 0

        for fb in feedbacks:
            try:
                # Skip if missing required metadata
                if not fb.query_intent or not fb.retrieval_metadata:
                    logger.debug(
                        "feedback_skipped_missing_metadata",
                        feedback_id=str(fb.feedback_id),
                    )
                    skipped += 1
                    continue

                # Extract strategy contributions from metadata
                hits_by_strategy = fb.retrieval_metadata.get("hits_by_strategy")
                if not hits_by_strategy:
                    logger.debug(
                        "feedback_skipped_no_strategy_info",
                        feedback_id=str(fb.feedback_id),
                    )
                    skipped += 1
                    continue

                # Determine if feedback is positive
                positive_actions = {"clicked", "copied", "upvoted", "marked_relevant"}
                is_positive = fb.action.value in positive_actions

                # Get selected chunks (target_chunk_ids or all retrieved)
                selected_chunks = fb.target_chunk_ids or fb.retrieved_chunk_ids

                # Create feedback signal
                signal = FeedbackSignal(
                    query=fb.query,
                    intent=fb.query_intent,
                    selected_chunk_ids=selected_chunks,
                    strategy_contributions=hits_by_strategy,
                    is_positive=is_positive,
                    timestamp=fb.timestamp.timestamp(),
                )

                # Record feedback
                self.weight_learner.record_feedback(signal)

                # Mark as processed if requested
                if mark_processed:
                    await self.feedback_service.mark_as_processed(fb.feedback_id)

                processed += 1

                logger.debug(
                    "feedback_processed",
                    feedback_id=str(fb.feedback_id),
                    intent=fb.query_intent,
                    is_positive=is_positive,
                )

            except Exception as e:
                logger.error(
                    "feedback_processing_error",
                    feedback_id=str(fb.feedback_id),
                    error=str(e),
                    exc_info=True,
                )
                errors += 1

        stats = {
            "processed_count": processed,
            "skipped_count": skipped,
            "error_count": errors,
            "total_feedback": len(feedbacks),
        }

        logger.info(
            "feedback_batch_complete",
            **stats,
        )

        return stats

    async def process_all(self, mark_processed: bool = True) -> dict[str, Any]:
        """
        Process all unprocessed feedback in batches.

        Args:
            mark_processed: Whether to mark feedback as processed

        Returns:
            Aggregate processing statistics
        """
        total_processed = 0
        total_skipped = 0
        total_errors = 0
        batch_count = 0

        while True:
            stats = await self.process_batch(mark_processed=mark_processed)

            total_processed += stats["processed_count"]
            total_skipped += stats["skipped_count"]
            total_errors += stats["error_count"]
            batch_count += 1

            # Stop if no more feedback
            if stats["total_feedback"] == 0:
                break

        logger.info(
            "all_feedback_processed",
            total_processed=total_processed,
            total_skipped=total_skipped,
            total_errors=total_errors,
            batch_count=batch_count,
        )

        return {
            "total_processed": total_processed,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "batch_count": batch_count,
        }


async def run_batch_processor():
    """
    Standalone entry point for batch processor.

    Reads from environment variables:
    - SEMANTICA_DATABASE_URL: PostgreSQL connection string
    - WEIGHT_LEARNER_PERSIST_PATH: Path to save learned weights (optional)
    """
    import os
    from pathlib import Path

    from codegraph_search.infrastructure.adaptive.weight_learner import (
        WeightLearnerConfig,
        get_weight_learner,
    )
    from codegraph_shared.infra.storage.postgres import create_postgres_store

    # Get configuration
    db_url = os.getenv(
        "SEMANTICA_DATABASE_URL",
        "postgresql://codegraph:codegraph_dev@localhost:7201/codegraph",
    )
    persist_path_str = os.getenv("WEIGHT_LEARNER_PERSIST_PATH")
    persist_path = Path(persist_path_str) if persist_path_str else None

    # Initialize services
    logger.info("Initializing feedback processor")
    postgres = create_postgres_store(db_url)
    await postgres.initialize()

    feedback_service = FeedbackService(postgres)

    # Create weight learner with persistence
    config = WeightLearnerConfig(weights_path=persist_path)
    weight_learner = get_weight_learner(config)

    # Create processor
    processor = FeedbackProcessor(feedback_service, weight_learner)

    # Process all feedback
    stats = await processor.process_all(mark_processed=True)

    logger.info("Batch processing complete", **stats)

    # Close connections
    await postgres.close()

    return stats


if __name__ == "__main__":
    # Run as standalone script
    asyncio.run(run_batch_processor())
