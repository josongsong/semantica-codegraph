"""
Adaptive Weight Learning for Retriever.

Learns optimal fusion weights from query feedback using:
1. Online learning with exponential moving average
2. Per-intent weight profiles
3. Feedback-based adjustment

This module implements true adaptive weighting beyond static intent profiles.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_search.infrastructure.v3.config import WeightProfile
from codegraph_search.infrastructure.v3.models import IntentProbability

logger = get_logger(__name__)


@dataclass
class FeedbackSignal:
    """Feedback signal for weight learning."""

    query: str
    intent: str
    selected_chunk_ids: list[str]  # User-selected/clicked chunks
    strategy_contributions: dict[str, list[str]]  # strategy → chunk_ids that came from it
    timestamp: float = field(default_factory=time.time)
    is_positive: bool = True  # True = good result, False = bad result


@dataclass
class WeightLearnerConfig:
    """Configuration for weight learner."""

    # Learning rate for EMA updates
    learning_rate: float = 0.1

    # Minimum weight for any strategy
    min_weight: float = 0.05

    # Maximum weight for any strategy
    max_weight: float = 0.8

    # Decay factor for old feedback
    feedback_decay: float = 0.95

    # Number of feedback signals to keep per intent
    max_feedback_history: int = 100

    # Persistence path for learned weights
    weights_path: Path | None = None


@dataclass
class LearnedWeights:
    """Learned weights with metadata."""

    weights: WeightProfile
    confidence: float  # 0-1, higher = more training data
    sample_count: int  # Number of feedback signals
    last_updated: float = field(default_factory=time.time)


class AdaptiveWeightLearner:
    """
    Learns optimal fusion weights from user feedback.

    Uses exponential moving average (EMA) to update weights
    based on which strategies contributed to successful results.
    """

    def __init__(self, config: WeightLearnerConfig | None = None):
        """Initialize weight learner."""
        self.config = config or WeightLearnerConfig()

        # Learned weights per intent
        self._learned_weights: dict[str, LearnedWeights] = {}

        # Feedback history per intent
        self._feedback_history: dict[str, list[FeedbackSignal]] = {
            "symbol": [],
            "flow": [],
            "concept": [],
            "code": [],
            "balanced": [],
        }

        # Strategy performance tracking
        self._strategy_success_rate: dict[str, dict[str, float]] = {
            "symbol": {"vector": 0.0, "lexical": 0.0, "symbol": 0.0, "graph": 0.0},
            "flow": {"vector": 0.0, "lexical": 0.0, "symbol": 0.0, "graph": 0.0},
            "concept": {"vector": 0.0, "lexical": 0.0, "symbol": 0.0, "graph": 0.0},
            "code": {"vector": 0.0, "lexical": 0.0, "symbol": 0.0, "graph": 0.0},
            "balanced": {"vector": 0.0, "lexical": 0.0, "symbol": 0.0, "graph": 0.0},
        }

        # Load persisted weights if available
        self._load_weights()

    def record_feedback(self, feedback: FeedbackSignal) -> None:
        """
        Record feedback signal and update weights.

        Args:
            feedback: Feedback signal from user interaction
        """
        intent = feedback.intent
        if intent not in self._feedback_history:
            intent = "balanced"

        # Add to history
        history = self._feedback_history[intent]
        history.append(feedback)

        # Trim old feedback
        if len(history) > self.config.max_feedback_history:
            history.pop(0)

        # Update strategy success rates
        self._update_success_rates(feedback)

        # Recompute weights for this intent
        self._recompute_weights(intent)

        # Persist if configured
        self._save_weights()

        logger.debug(
            f"Recorded feedback for intent={intent}, "
            f"selected_chunks={len(feedback.selected_chunk_ids)}, "
            f"is_positive={feedback.is_positive}"
        )

    def _update_success_rates(self, feedback: FeedbackSignal) -> None:
        """Update strategy success rates based on feedback."""
        intent = feedback.intent
        if intent not in self._strategy_success_rate:
            intent = "balanced"

        selected_set = set(feedback.selected_chunk_ids)

        # Calculate contribution of each strategy
        for strategy, chunk_ids in feedback.strategy_contributions.items():
            if strategy not in self._strategy_success_rate[intent]:
                continue

            # How many of this strategy's chunks were selected?
            if chunk_ids:
                hits = len(selected_set.intersection(chunk_ids))
                success_rate = hits / len(chunk_ids)
            else:
                success_rate = 0.0

            # Adjust for positive/negative feedback
            if not feedback.is_positive:
                success_rate = 1.0 - success_rate

            # EMA update
            current = self._strategy_success_rate[intent][strategy]
            updated = current * (1 - self.config.learning_rate) + success_rate * self.config.learning_rate

            self._strategy_success_rate[intent][strategy] = updated

    def _recompute_weights(self, intent: str) -> None:
        """Recompute weights for an intent based on success rates."""
        rates = self._strategy_success_rate[intent]

        # Convert success rates to weights
        total = sum(rates.values())
        if total <= 0:
            return

        raw_weights = {
            "vec": rates["vector"] / total,
            "lex": rates["lexical"] / total,
            "sym": rates["symbol"] / total,
            "graph": rates["graph"] / total,
        }

        # Clamp weights
        for key in raw_weights:
            raw_weights[key] = max(self.config.min_weight, min(self.config.max_weight, raw_weights[key]))

        # Re-normalize
        total = sum(raw_weights.values())
        for key in raw_weights:
            raw_weights[key] /= total

        # Create WeightProfile
        profile = WeightProfile(
            vec=raw_weights["vec"],
            lex=raw_weights["lex"],
            sym=raw_weights["sym"],
            graph=raw_weights["graph"],
        )

        # Calculate confidence based on sample count
        sample_count = len(self._feedback_history[intent])
        confidence = min(1.0, sample_count / 50)  # Full confidence at 50 samples

        self._learned_weights[intent] = LearnedWeights(
            weights=profile,
            confidence=confidence,
            sample_count=sample_count,
        )

    def get_adaptive_weights(
        self,
        intent_prob: IntentProbability,
        base_weights: dict[str, WeightProfile],
    ) -> WeightProfile:
        """
        Get adaptive weights combining learned weights with base weights.

        Interpolates between base (static) and learned weights based on confidence.

        Args:
            intent_prob: Intent probability distribution
            base_weights: Base weight profiles (static)

        Returns:
            Combined WeightProfile
        """
        intent_dict = intent_prob.to_dict()

        # Combine learned weights with base weights
        combined = {"vec": 0.0, "lex": 0.0, "sym": 0.0, "graph": 0.0}

        for intent_name, probability in intent_dict.items():
            learned = self._learned_weights.get(intent_name)
            base = base_weights.get(intent_name)

            if base is None:
                continue

            # Interpolate between base and learned based on confidence
            if learned and learned.confidence > 0:
                alpha = learned.confidence
                effective_weights = {
                    "vec": alpha * learned.weights.vec + (1 - alpha) * base.vec,
                    "lex": alpha * learned.weights.lex + (1 - alpha) * base.lex,
                    "sym": alpha * learned.weights.sym + (1 - alpha) * base.sym,
                    "graph": alpha * learned.weights.graph + (1 - alpha) * base.graph,
                }
            else:
                effective_weights = {
                    "vec": base.vec,
                    "lex": base.lex,
                    "sym": base.sym,
                    "graph": base.graph,
                }

            # Weighted combination by intent probability
            for key in combined:
                combined[key] += probability * effective_weights[key]

        # Normalize
        total = sum(combined.values())
        if total > 0:
            for key in combined:
                combined[key] /= total

        return WeightProfile(
            vec=combined["vec"],
            lex=combined["lex"],
            sym=combined["sym"],
            graph=combined["graph"],
        )

    def get_learned_weights(self, intent: str) -> LearnedWeights | None:
        """Get learned weights for a specific intent."""
        return self._learned_weights.get(intent)

    def get_all_learned_weights(self) -> dict[str, LearnedWeights]:
        """Get all learned weights."""
        return self._learned_weights.copy()

    def get_stats(self) -> dict[str, Any]:
        """Get learning statistics."""
        return {
            "feedback_counts": {intent: len(hist) for intent, hist in self._feedback_history.items()},
            "success_rates": self._strategy_success_rate,
            "learned_weights": {
                intent: {
                    "weights": lw.weights.to_dict(),
                    "confidence": lw.confidence,
                    "sample_count": lw.sample_count,
                }
                for intent, lw in self._learned_weights.items()
            },
        }

    def reset(self) -> None:
        """Reset all learned weights."""
        self._learned_weights.clear()
        for intent in self._feedback_history:
            self._feedback_history[intent].clear()
        for intent in self._strategy_success_rate:
            for strategy in self._strategy_success_rate[intent]:
                self._strategy_success_rate[intent][strategy] = 0.0

        logger.info("Weight learner reset")

    def _load_weights(self) -> None:
        """Load persisted weights from disk."""
        if not self.config.weights_path or not self.config.weights_path.exists():
            return

        try:
            with open(self.config.weights_path) as f:
                data = json.load(f)

            for intent, weight_data in data.get("learned_weights", {}).items():
                weights = weight_data.get("weights", {})
                self._learned_weights[intent] = LearnedWeights(
                    weights=WeightProfile(
                        vec=weights.get("vector", 0.25),
                        lex=weights.get("lexical", 0.25),
                        sym=weights.get("symbol", 0.25),
                        graph=weights.get("graph", 0.25),
                    ),
                    confidence=weight_data.get("confidence", 0.0),
                    sample_count=weight_data.get("sample_count", 0),
                    last_updated=weight_data.get("last_updated", time.time()),
                )

            self._strategy_success_rate = data.get("success_rates", self._strategy_success_rate)

            logger.info(f"Loaded learned weights from {self.config.weights_path}")

        except Exception as e:
            logger.warning(f"Failed to load weights: {e}")

    def _save_weights(self) -> None:
        """Persist learned weights to disk."""
        if not self.config.weights_path:
            return

        try:
            data = {
                "learned_weights": {
                    intent: {
                        "weights": lw.weights.to_dict(),
                        "confidence": lw.confidence,
                        "sample_count": lw.sample_count,
                        "last_updated": lw.last_updated,
                    }
                    for intent, lw in self._learned_weights.items()
                },
                "success_rates": self._strategy_success_rate,
            }

            # Ensure directory exists
            self.config.weights_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config.weights_path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save weights: {e}")


# Global instance for singleton access
_weight_learner: AdaptiveWeightLearner | None = None


def get_weight_learner(config: WeightLearnerConfig | None = None) -> AdaptiveWeightLearner:
    """Get or create the global weight learner instance."""
    global _weight_learner
    if _weight_learner is None:
        _weight_learner = AdaptiveWeightLearner(config)
    return _weight_learner
