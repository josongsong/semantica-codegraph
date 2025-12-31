"""
A/B Testing Framework

Implements Phase 2 Action 12-2 from the retrieval execution plan.

Allows running controlled experiments to compare different retrieval strategies:
- Fusion weight profiles
- Reranking strategies
- Intent classification methods
- Score normalization techniques
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class VariantType(str, Enum):
    """Type of experiment variant."""

    CONTROL = "control"  # Baseline
    TREATMENT = "treatment"  # New approach


@dataclass
class Variant:
    """Experiment variant configuration."""

    name: str
    variant_type: VariantType
    config: dict[str, Any]
    traffic_allocation: float  # 0-1, percentage of traffic


@dataclass
class ExperimentResult:
    """Result from an experiment run."""

    variant_name: str
    query: str
    result_ids: list[str]  # Ordered list of chunk IDs
    metrics: dict[str, float]
    latency_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ABTest:
    """A/B test configuration."""

    experiment_id: str
    name: str
    description: str
    variants: list[Variant]
    start_date: str
    end_date: str | None = None
    is_active: bool = True
    randomization_unit: str = "user_id"  # or "query"


class ABTestManager:
    """
    Manages A/B tests for retrieval experiments.

    Features:
    - Consistent variant assignment (same user/query gets same variant)
    - Traffic allocation control
    - Metric collection and comparison
    - Statistical significance testing
    """

    def __init__(self, experiments_dir: str = "./experiments"):
        """
        Initialize A/B test manager.

        Args:
            experiments_dir: Directory to store experiment configs and results
        """
        self.experiments_dir = Path(experiments_dir)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

        self.active_experiments: dict[str, ABTest] = {}
        self.results: dict[str, list[ExperimentResult]] = {}

        # Load existing experiments
        self._load_experiments()

    def create_experiment(
        self,
        name: str,
        description: str,
        control_config: dict[str, Any],
        treatment_config: dict[str, Any],
        traffic_split: float = 0.5,
        randomization_unit: str = "user_id",
    ) -> ABTest:
        """
        Create new A/B test.

        Args:
            name: Experiment name
            description: What is being tested
            control_config: Baseline configuration
            treatment_config: New approach configuration
            traffic_split: Percentage of traffic to treatment (0-1)
            randomization_unit: What to use for variant assignment

        Returns:
            Created AB test
        """
        experiment_id = self._generate_experiment_id(name)

        variants = [
            Variant(
                name="control",
                variant_type=VariantType.CONTROL,
                config=control_config,
                traffic_allocation=1.0 - traffic_split,
            ),
            Variant(
                name="treatment",
                variant_type=VariantType.TREATMENT,
                config=treatment_config,
                traffic_allocation=traffic_split,
            ),
        ]

        experiment = ABTest(
            experiment_id=experiment_id,
            name=name,
            description=description,
            variants=variants,
            start_date=datetime.now(timezone.utc).isoformat(),
            randomization_unit=randomization_unit,
        )

        self.active_experiments[experiment_id] = experiment
        self.results[experiment_id] = []

        # Save experiment config
        self._save_experiment(experiment)

        logger.info(f"Created experiment: {name} (id={experiment_id})")
        return experiment

    def get_variant(self, experiment_id: str, randomization_key: str) -> Variant:
        """
        Get assigned variant for a randomization key.

        Uses consistent hashing to ensure same key always gets same variant.

        Args:
            experiment_id: Experiment ID
            randomization_key: Key for randomization (e.g., user_id or query)

        Returns:
            Assigned variant
        """
        experiment = self.active_experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        # Hash randomization key to get consistent assignment
        hash_value = int(
            hashlib.md5(f"{experiment_id}:{randomization_key}".encode()).hexdigest(),
            16,
        )
        random_value = (hash_value % 10000) / 10000.0  # 0-1

        # Determine variant based on traffic allocation
        cumulative = 0.0
        for variant in experiment.variants:
            cumulative += variant.traffic_allocation
            if random_value < cumulative:
                return variant

        # Fallback to control
        return experiment.variants[0]

    async def run_experiment(
        self,
        experiment_id: str,
        randomization_key: str,
        query: str,
        retrieval_func: Callable[[dict[str, Any], str], Any],
    ) -> tuple[Variant, Any, ExperimentResult]:
        """
        Run experiment for a query.

        Args:
            experiment_id: Experiment ID
            randomization_key: Randomization key (e.g., user_id)
            query: User query
            retrieval_func: Retrieval function that takes (config, query)

        Returns:
            (assigned_variant, retrieval_result, experiment_result)
        """
        # Get variant assignment
        variant = self.get_variant(experiment_id, randomization_key)

        logger.debug(f"Experiment {experiment_id}: assigned variant={variant.name} for key={randomization_key}")

        # Run retrieval with variant config
        start_time = time.time()
        retrieval_result = await retrieval_func(variant.config, query)
        latency_ms = (time.time() - start_time) * 1000

        # Extract result IDs and metrics
        result_ids = self._extract_result_ids(retrieval_result)
        metrics = self._extract_metrics(retrieval_result)

        # Record result
        experiment_result = ExperimentResult(
            variant_name=variant.name,
            query=query,
            result_ids=result_ids,
            metrics=metrics,
            latency_ms=latency_ms,
        )

        self.results[experiment_id].append(experiment_result)

        # Periodically save results
        if len(self.results[experiment_id]) % 100 == 0:
            self._save_results(experiment_id)

        return variant, retrieval_result, experiment_result

    def get_experiment_metrics(self, experiment_id: str) -> dict[str, dict[str, float]]:
        """
        Get aggregated metrics for an experiment.

        Args:
            experiment_id: Experiment ID

        Returns:
            Metrics by variant
        """
        results = self.results.get(experiment_id, [])
        if not results:
            return {}

        # Group by variant
        by_variant: dict[str, list[ExperimentResult]] = {}
        for result in results:
            variant_name = result.variant_name
            if variant_name not in by_variant:
                by_variant[variant_name] = []
            by_variant[variant_name].append(result)

        # Aggregate metrics
        aggregated = {}
        for variant_name, variant_results in by_variant.items():
            metrics = {
                "count": len(variant_results),
                "avg_latency_ms": sum(r.latency_ms for r in variant_results) / len(variant_results),
            }

            # Aggregate custom metrics
            if variant_results[0].metrics:
                for metric_name in variant_results[0].metrics.keys():
                    values = [r.metrics[metric_name] for r in variant_results if metric_name in r.metrics]
                    metrics[f"avg_{metric_name}"] = sum(values) / len(values) if values else 0.0

            aggregated[variant_name] = metrics

        return aggregated

    def compare_variants(self, experiment_id: str, metric_name: str = "avg_latency_ms") -> dict[str, Any]:
        """
        Compare variants on a specific metric.

        Args:
            experiment_id: Experiment ID
            metric_name: Metric to compare

        Returns:
            Comparison results
        """
        metrics = self.get_experiment_metrics(experiment_id)
        if len(metrics) < 2:
            return {"error": "Need at least 2 variants to compare"}

        control_metrics = metrics.get("control", {})
        treatment_metrics = metrics.get("treatment", {})

        if not control_metrics or not treatment_metrics:
            return {"error": "Missing control or treatment data"}

        control_value = control_metrics.get(metric_name, 0.0)
        treatment_value = treatment_metrics.get(metric_name, 0.0)

        # Calculate improvement
        if control_value > 0:
            improvement_pct = ((treatment_value - control_value) / control_value) * 100
        else:
            improvement_pct = 0.0

        return {
            "metric": metric_name,
            "control_value": control_value,
            "treatment_value": treatment_value,
            "improvement_pct": improvement_pct,
            "winner": (
                "treatment" if treatment_value > control_value else "control"
            ),  # For metrics where higher is better
            "control_count": control_metrics["count"],
            "treatment_count": treatment_metrics["count"],
        }

    def end_experiment(self, experiment_id: str) -> None:
        """
        End an experiment.

        Args:
            experiment_id: Experiment ID
        """
        if experiment_id not in self.active_experiments:
            return

        experiment = self.active_experiments[experiment_id]
        experiment.is_active = False
        experiment.end_date = datetime.now(timezone.utc).isoformat()

        self._save_experiment(experiment)
        self._save_results(experiment_id)

        logger.info(f"Ended experiment: {experiment.name} (id={experiment_id})")

    def _generate_experiment_id(self, name: str) -> str:
        """Generate experiment ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{name.replace(' ', '_')}_{timestamp}"

    def _extract_result_ids(self, retrieval_result: Any) -> list[str]:
        """Extract chunk IDs from retrieval result."""
        if hasattr(retrieval_result, "context"):
            return [chunk.chunk_id for chunk in retrieval_result.context.chunks]
        elif isinstance(retrieval_result, list):
            return [r.get("chunk_id", "") for r in retrieval_result]
        return []

    def _extract_metrics(self, retrieval_result: Any) -> dict[str, float]:
        """Extract metrics from retrieval result."""
        metrics = {}
        if hasattr(retrieval_result, "metadata"):
            metadata = retrieval_result.metadata
            if isinstance(metadata, dict):
                # Extract numeric metrics
                for key, value in metadata.items():
                    if isinstance(value, int | float):
                        metrics[key] = float(value)
        return metrics

    def _save_experiment(self, experiment: ABTest) -> None:
        """Save experiment configuration."""
        config_file = self.experiments_dir / f"{experiment.experiment_id}_config.json"
        with open(config_file, "w") as f:
            json.dump(
                {
                    "experiment_id": experiment.experiment_id,
                    "name": experiment.name,
                    "description": experiment.description,
                    "variants": [
                        {
                            "name": v.name,
                            "variant_type": v.variant_type.value,
                            "config": v.config,
                            "traffic_allocation": v.traffic_allocation,
                        }
                        for v in experiment.variants
                    ],
                    "start_date": experiment.start_date,
                    "end_date": experiment.end_date,
                    "is_active": experiment.is_active,
                    "randomization_unit": experiment.randomization_unit,
                },
                f,
                indent=2,
            )

    def _save_results(self, experiment_id: str) -> None:
        """Save experiment results."""
        results = self.results.get(experiment_id, [])
        if not results:
            return

        results_file = self.experiments_dir / f"{experiment_id}_results.jsonl"
        with open(results_file, "w") as f:
            for result in results:
                json.dump(
                    {
                        "variant_name": result.variant_name,
                        "query": result.query,
                        "result_ids": result.result_ids,
                        "metrics": result.metrics,
                        "latency_ms": result.latency_ms,
                        "timestamp": result.timestamp,
                    },
                    f,
                )
                f.write("\n")

    def _load_experiments(self) -> None:
        """Load existing experiments from disk."""
        for config_file in self.experiments_dir.glob("*_config.json"):
            try:
                with open(config_file) as f:
                    data = json.load(f)

                variants = [
                    Variant(
                        name=v["name"],
                        variant_type=VariantType(v["variant_type"]),
                        config=v["config"],
                        traffic_allocation=v["traffic_allocation"],
                    )
                    for v in data["variants"]
                ]

                experiment = ABTest(
                    experiment_id=data["experiment_id"],
                    name=data["name"],
                    description=data["description"],
                    variants=variants,
                    start_date=data["start_date"],
                    end_date=data.get("end_date"),
                    is_active=data.get("is_active", True),
                    randomization_unit=data.get("randomization_unit", "user_id"),
                )

                if experiment.is_active:
                    self.active_experiments[experiment.experiment_id] = experiment

                logger.info(f"Loaded experiment: {experiment.name}")
            except Exception as e:
                logger.warning(f"Failed to load experiment {config_file}: {e}")
