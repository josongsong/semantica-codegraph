"""
Cost Tracking for Production Infrastructure

Tracks API costs, storage costs, and resource usage for budget management.
Now integrated with OpenTelemetry metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Any

from codegraph_shared.infra.config.logging import get_logger
from codegraph_shared.infra.observability.otel_setup import get_meter

logger = get_logger(__name__)


class CostCategory(Enum):
    """Categories of costs."""

    LLM_API = "llm_api"  # OpenAI, Anthropic, etc.
    EMBEDDING_API = "embedding_api"  # OpenAI embeddings
    VECTOR_STORAGE = "vector_storage"  # Qdrant, Pinecone
    DATABASE = "database"  # PostgreSQL, Redis
    GRAPH_DATABASE = "graph_database"  # Kuzu
    COMPUTE = "compute"  # CPU, memory, bandwidth
    OTHER = "other"


@dataclass
class CostEvent:
    """Single cost event."""

    # Identification
    category: CostCategory
    service: str  # e.g., "openai", "qdrant", "postgresql"
    operation: str  # e.g., "gpt-4-turbo-completion", "vector-search"

    # Cost
    cost_usd: float
    quantity: float  # e.g., tokens, queries, GB-hours
    unit: str  # e.g., "tokens", "queries", "GB"

    # Timing
    timestamp: datetime = field(default_factory=datetime.now)

    # Metadata
    labels: dict[str, str] = field(default_factory=dict)


class CostTracker:
    """
    Tracks costs across different services.

    Example:
        ```python
        tracker = CostTracker()

        # Track LLM API call
        tracker.record_llm_tokens(
            model="gpt-4-turbo",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        # Track embedding API call
        tracker.record_embedding_tokens(
            model="text-embedding-3-small",
            tokens=2000,
        )

        # Track vector search
        tracker.record_vector_search(queries=100)

        # Get costs
        print(tracker.get_total_cost(period_days=1))
        print(tracker.get_cost_by_category(period_days=7))
        ```
    """

    # Pricing (as of 2025-01, in USD)
    # Source: OpenAI pricing page
    LLM_PRICING = {
        "gpt-4-turbo": {"prompt": 0.01 / 1000, "completion": 0.03 / 1000},  # per token
        "gpt-4": {"prompt": 0.03 / 1000, "completion": 0.06 / 1000},
        "gpt-3.5-turbo": {"prompt": 0.0005 / 1000, "completion": 0.0015 / 1000},
        "claude-3-opus": {"prompt": 0.015 / 1000, "completion": 0.075 / 1000},
        "claude-3-sonnet": {"prompt": 0.003 / 1000, "completion": 0.015 / 1000},
    }

    EMBEDDING_PRICING = {
        "text-embedding-3-small": 0.02 / 1_000_000,  # per token
        "text-embedding-3-large": 0.13 / 1_000_000,
        "text-embedding-ada-002": 0.10 / 1_000_000,
    }

    # Vector storage (estimated)
    QDRANT_PRICING = {
        "storage_gb_month": 0.25,  # per GB per month
        "query": 0.001,  # per 1000 queries
    }

    # Database (estimated based on cloud provider)
    POSTGRES_PRICING = {
        "storage_gb_month": 0.10,  # per GB per month
        "query": 0.0001,  # per 1000 queries
    }

    def __init__(self):
        # Cost event storage
        self._events: list[CostEvent] = []

        # Thread safety
        self._lock = Lock()

        # OTEL instruments (lazy init)
        self._cost_counter = None
        self._quantity_counter = None
        self._init_instruments()

    def _init_instruments(self):
        """Initialize OTEL metric instruments (lazy)."""
        meter = get_meter(__name__)
        if meter is None:
            return

        try:
            self._cost_counter = meter.create_counter(
                name="infrastructure.cost.total",
                description="Total infrastructure cost in USD",
                unit="USD",
            )

            self._quantity_counter = meter.create_counter(
                name="infrastructure.usage.total",
                description="Total infrastructure usage",
                unit="1",
            )

            logger.info("cost_tracking_metrics_initialized")
        except Exception as e:
            logger.warning("cost_tracking_metrics_init_failed", error=str(e))

    def _ensure_instruments(self):
        """Ensure OTEL instruments are initialized."""
        if self._cost_counter is None:
            self._init_instruments()

    def record_llm_tokens(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Record LLM API usage and calculate cost.

        Args:
            model: Model name (e.g., "gpt-4-turbo")
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            labels: Optional labels (e.g., {"user_id": "123", "operation": "search"})

        Returns:
            Cost in USD

        Example:
            ```python
            cost = tracker.record_llm_tokens(
                model="gpt-4-turbo",
                prompt_tokens=1000,
                completion_tokens=500,
            )
            print(f"Cost: ${cost:.4f}")
            ```
        """
        pricing = self.LLM_PRICING.get(model, {"prompt": 0.0, "completion": 0.0})

        prompt_cost = prompt_tokens * pricing["prompt"]
        completion_cost = completion_tokens * pricing["completion"]
        total_cost = prompt_cost + completion_cost

        # Record event
        event = CostEvent(
            category=CostCategory.LLM_API,
            service="openai",
            operation=f"{model}-completion",
            cost_usd=total_cost,
            quantity=prompt_tokens + completion_tokens,
            unit="tokens",
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

        # Record to OTEL
        self._ensure_instruments()
        if self._cost_counter:
            try:
                attrs = {
                    "category": event.category.value,
                    "service": event.service,
                    "model": model,
                }
                self._cost_counter.add(total_cost, attrs)
                self._quantity_counter.add(prompt_tokens + completion_tokens, {**attrs, "unit": "tokens"})
            except Exception as e:
                logger.debug("cost_tracking_otel_failed", error=str(e))

        return total_cost

    def record_embedding_tokens(
        self,
        model: str,
        tokens: int,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Record embedding API usage and calculate cost.

        Args:
            model: Model name (e.g., "text-embedding-3-small")
            tokens: Number of tokens
            labels: Optional labels

        Returns:
            Cost in USD
        """
        pricing = self.EMBEDDING_PRICING.get(model, 0.0)
        cost = tokens * pricing

        event = CostEvent(
            category=CostCategory.EMBEDDING_API,
            service="openai",
            operation=f"{model}-embedding",
            cost_usd=cost,
            quantity=tokens,
            unit="tokens",
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

        # Record to OTEL
        self._ensure_instruments()
        if self._cost_counter:
            try:
                attrs = {
                    "category": event.category.value,
                    "service": event.service,
                    "model": model,
                }
                self._cost_counter.add(cost, attrs)
                self._quantity_counter.add(tokens, {**attrs, "unit": "tokens"})
            except Exception as e:
                logger.debug("cost_tracking_otel_failed", error=str(e))

        return cost

    def record_vector_search(
        self,
        queries: int,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Record vector search operations and calculate cost.

        Args:
            queries: Number of queries
            labels: Optional labels

        Returns:
            Cost in USD
        """
        cost = (queries / 1000) * self.QDRANT_PRICING["query"]

        event = CostEvent(
            category=CostCategory.VECTOR_STORAGE,
            service="qdrant",
            operation="vector-search",
            cost_usd=cost,
            quantity=queries,
            unit="queries",
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

        return cost

    def record_vector_storage(
        self,
        storage_gb: float,
        duration_hours: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Record vector storage usage and calculate cost.

        Args:
            storage_gb: Storage size in GB
            duration_hours: Duration in hours (for prorated monthly cost)
            labels: Optional labels

        Returns:
            Cost in USD
        """
        # Prorate monthly cost to hourly
        monthly_cost = storage_gb * self.QDRANT_PRICING["storage_gb_month"]
        hourly_cost = monthly_cost / (30 * 24)  # Assume 30 days/month
        cost = hourly_cost * duration_hours

        event = CostEvent(
            category=CostCategory.VECTOR_STORAGE,
            service="qdrant",
            operation="storage",
            cost_usd=cost,
            quantity=storage_gb * duration_hours,
            unit="GB-hours",
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

        return cost

    def record_database_queries(
        self,
        service: str,  # "postgresql", "redis"
        queries: int,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Record database queries and calculate cost.

        Args:
            service: Database service name
            queries: Number of queries
            labels: Optional labels

        Returns:
            Cost in USD
        """
        cost = (queries / 1000) * self.POSTGRES_PRICING["query"]

        event = CostEvent(
            category=CostCategory.DATABASE,
            service=service,
            operation="query",
            cost_usd=cost,
            quantity=queries,
            unit="queries",
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

        return cost

    def record_database_storage(
        self,
        service: str,
        storage_gb: float,
        duration_hours: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Record database storage usage and calculate cost.

        Args:
            service: Database service name
            storage_gb: Storage size in GB
            duration_hours: Duration in hours
            labels: Optional labels

        Returns:
            Cost in USD
        """
        monthly_cost = storage_gb * self.POSTGRES_PRICING["storage_gb_month"]
        hourly_cost = monthly_cost / (30 * 24)
        cost = hourly_cost * duration_hours

        event = CostEvent(
            category=CostCategory.DATABASE,
            service=service,
            operation="storage",
            cost_usd=cost,
            quantity=storage_gb * duration_hours,
            unit="GB-hours",
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

        return cost

    def record_custom_cost(
        self,
        category: CostCategory,
        service: str,
        operation: str,
        cost_usd: float,
        quantity: float = 1.0,
        unit: str = "units",
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a custom cost event.

        Args:
            category: Cost category
            service: Service name
            operation: Operation name
            cost_usd: Cost in USD
            quantity: Quantity of units
            unit: Unit name
            labels: Optional labels
        """
        event = CostEvent(
            category=category,
            service=service,
            operation=operation,
            cost_usd=cost_usd,
            quantity=quantity,
            unit=unit,
            labels=labels or {},
        )

        with self._lock:
            self._events.append(event)

    def get_total_cost(self, period_days: int | None = None) -> float:
        """
        Get total cost over a period.

        Args:
            period_days: Number of days to look back (None = all time)

        Returns:
            Total cost in USD
        """
        events = self._filter_events_by_period(period_days)
        return sum(event.cost_usd for event in events)

    def get_cost_by_category(self, period_days: int | None = None) -> dict[str, float]:
        """
        Get costs grouped by category.

        Args:
            period_days: Number of days to look back

        Returns:
            Dict mapping category to cost
        """
        events = self._filter_events_by_period(period_days)

        costs = {}
        for event in events:
            category = event.category.value
            costs[category] = costs.get(category, 0.0) + event.cost_usd

        return costs

    def get_cost_by_service(self, period_days: int | None = None) -> dict[str, float]:
        """
        Get costs grouped by service.

        Args:
            period_days: Number of days to look back

        Returns:
            Dict mapping service to cost
        """
        events = self._filter_events_by_period(period_days)

        costs = {}
        for event in events:
            service = event.service
            costs[service] = costs.get(service, 0.0) + event.cost_usd

        return costs

    def get_cost_breakdown(self, period_days: int | None = None) -> dict[str, Any]:
        """
        Get detailed cost breakdown.

        Args:
            period_days: Number of days to look back

        Returns:
            Dict with total, by_category, by_service, and top_operations
        """
        events = self._filter_events_by_period(period_days)

        by_category = {}
        by_service = {}
        by_operation = {}

        for event in events:
            # By category
            category = event.category.value
            by_category[category] = by_category.get(category, 0.0) + event.cost_usd

            # By service
            service = event.service
            by_service[service] = by_service.get(service, 0.0) + event.cost_usd

            # By operation
            operation = f"{event.service}:{event.operation}"
            by_operation[operation] = by_operation.get(operation, 0.0) + event.cost_usd

        # Sort operations by cost
        top_operations = sorted(by_operation.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_usd": sum(event.cost_usd for event in events),
            "period_days": period_days or "all_time",
            "event_count": len(events),
            "by_category": by_category,
            "by_service": by_service,
            "top_operations": dict(top_operations),
        }

    def _filter_events_by_period(self, period_days: int | None) -> list[CostEvent]:
        """Filter events by time period."""
        with self._lock:
            if period_days is None:
                return self._events.copy()

            cutoff = datetime.now() - timedelta(days=period_days)
            return [event for event in self._events if event.timestamp >= cutoff]

    def get_events(self, limit: int = 100) -> list[CostEvent]:
        """Get recent cost events."""
        with self._lock:
            return self._events[-limit:]

    def clear(self) -> None:
        """Clear all cost events (for testing)."""
        with self._lock:
            self._events.clear()

    def export_to_dict(self, period_days: int | None = None) -> list[dict[str, Any]]:
        """
        Export cost events to list of dicts (for JSON export).

        Args:
            period_days: Number of days to look back

        Returns:
            List of cost event dicts
        """
        events = self._filter_events_by_period(period_days)

        return [
            {
                "timestamp": event.timestamp.isoformat(),
                "category": event.category.value,
                "service": event.service,
                "operation": event.operation,
                "cost_usd": round(event.cost_usd, 6),
                "quantity": event.quantity,
                "unit": event.unit,
                "labels": event.labels,
            }
            for event in events
        ]


# Global cost tracker instance
_global_tracker: CostTracker | None = None
_tracker_lock = Lock()


def get_cost_tracker() -> CostTracker:
    """Get or create global cost tracker."""
    global _global_tracker
    if _global_tracker is None:
        with _tracker_lock:
            if _global_tracker is None:
                _global_tracker = CostTracker()
    return _global_tracker


# Convenience functions using global tracker
def record_llm_cost(model: str, prompt_tokens: int, completion_tokens: int, **labels) -> float:
    """Record LLM API cost using global tracker."""
    return get_cost_tracker().record_llm_tokens(model, prompt_tokens, completion_tokens, labels)


def record_embedding_cost(model: str, tokens: int, **labels) -> float:
    """Record embedding API cost using global tracker."""
    return get_cost_tracker().record_embedding_tokens(model, tokens, labels)


def record_vector_search_cost(queries: int, **labels) -> float:
    """Record vector search cost using global tracker."""
    return get_cost_tracker().record_vector_search(queries, labels)


def get_total_cost(period_days: int | None = None) -> float:
    """Get total cost using global tracker."""
    return get_cost_tracker().get_total_cost(period_days)


def get_cost_breakdown(period_days: int | None = None) -> dict[str, Any]:
    """Get cost breakdown using global tracker."""
    return get_cost_tracker().get_cost_breakdown(period_days)


def _example_usage():
    """Example demonstrating cost tracking usage."""
    import json

    tracker = CostTracker()

    # Simulate various operations
    print("=== Simulating operations ===\n")

    # LLM API calls
    cost1 = tracker.record_llm_tokens(
        model="gpt-4-turbo",
        prompt_tokens=1000,
        completion_tokens=500,
        labels={"user_id": "user_123", "operation": "code_search"},
    )
    print(f"LLM API (gpt-4-turbo): ${cost1:.4f}")

    cost2 = tracker.record_llm_tokens(
        model="gpt-3.5-turbo",
        prompt_tokens=2000,
        completion_tokens=800,
        labels={"user_id": "user_456", "operation": "summarization"},
    )
    print(f"LLM API (gpt-3.5-turbo): ${cost2:.4f}")

    # Embedding API calls
    cost3 = tracker.record_embedding_tokens(
        model="text-embedding-3-small",
        tokens=50000,
        labels={"operation": "chunk_embedding"},
    )
    print(f"Embedding API: ${cost3:.4f}")

    # Vector search
    cost4 = tracker.record_vector_search(
        queries=1000,
        labels={"operation": "hybrid_search"},
    )
    print(f"Vector search (1000 queries): ${cost4:.4f}")

    # Vector storage
    cost5 = tracker.record_vector_storage(
        storage_gb=10.5,
        duration_hours=24,  # 1 day
        labels={"repo": "semantica"},
    )
    print(f"Vector storage (10.5GB for 24h): ${cost5:.4f}")

    # Database queries
    cost6 = tracker.record_database_queries(
        service="postgresql",
        queries=5000,
        labels={"operation": "symbol_lookup"},
    )
    print(f"PostgreSQL queries (5000): ${cost6:.4f}")

    # Get cost breakdown
    print("\n=== Cost Breakdown (All Time) ===\n")
    breakdown = tracker.get_cost_breakdown()
    print(json.dumps(breakdown, indent=2))

    # Get cost by category
    print("\n=== Cost by Category ===")
    by_category = tracker.get_cost_by_category()
    for category, cost in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        print(f"{category}: ${cost:.4f}")

    # Get total cost
    total = tracker.get_total_cost()
    print(f"\nTotal Cost: ${total:.4f}")


if __name__ == "__main__":
    _example_usage()
