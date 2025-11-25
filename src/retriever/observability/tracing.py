"""
Retrieval Tracing

Tracks and traces the complete retrieval process for debugging and analysis.
"""

import time
from contextlib import contextmanager

from .models import RetrievalTrace


class RetrievalTracer:
    """
    Traces the retrieval process from query to results.

    Tracks latencies, source queries, fusion methods, and intermediate results.
    """

    def __init__(self):
        """Initialize tracer."""
        self.current_trace: RetrievalTrace | None = None
        self._stage_start_time: float = 0.0

    def start_trace(
        self, query: str, intent: str = "unknown", scope_type: str = "repo"
    ) -> RetrievalTrace:
        """
        Start a new retrieval trace.

        Args:
            query: The search query
            intent: Detected intent (find_definition, find_usage, etc.)
            scope_type: Scope selection type (repo, file, function, etc.)

        Returns:
            New trace object
        """
        self.current_trace = RetrievalTrace(
            query=query,
            intent=intent,
            scope_type=scope_type,
            num_sources_queried=0,
            source_results={},
            fusion_method="weighted",
            reranking_applied=False,
            total_latency_ms=0.0,
            stage_latencies={},
        )
        self._trace_start_time = time.time()
        return self.current_trace

    def record_source_query(self, source_name: str, num_results: int):
        """
        Record that a source was queried.

        Args:
            source_name: Name of the source (lexical, vector, etc.)
            num_results: Number of results returned
        """
        if not self.current_trace:
            return

        self.current_trace.num_sources_queried += 1
        self.current_trace.source_results[source_name] = num_results

    def record_fusion_method(self, method: str):
        """
        Record the fusion method used.

        Args:
            method: Fusion method name (weighted, rrf, correlation_aware, etc.)
        """
        if self.current_trace:
            self.current_trace.fusion_method = method

    def record_reranking(self, applied: bool = True):
        """
        Record that reranking was applied.

        Args:
            applied: Whether reranking was applied
        """
        if self.current_trace:
            self.current_trace.reranking_applied = applied

    @contextmanager
    def stage(self, stage_name: str):
        """
        Context manager to track stage latency.

        Usage:
            with tracer.stage("lexical_search"):
                # perform search
                pass

        Args:
            stage_name: Name of the stage
        """
        start = time.time()
        try:
            yield
        finally:
            elapsed_ms = (time.time() - start) * 1000
            if self.current_trace:
                self.current_trace.stage_latencies[stage_name] = elapsed_ms

    def finalize_trace(self) -> RetrievalTrace | None:
        """
        Finalize the current trace and calculate total latency.

        Returns:
            Completed trace or None if no trace is active
        """
        if not self.current_trace:
            return None

        total_elapsed = time.time() - self._trace_start_time
        self.current_trace.total_latency_ms = total_elapsed * 1000

        completed_trace = self.current_trace
        self.current_trace = None
        return completed_trace

    def get_trace_summary(self, trace: RetrievalTrace) -> dict[str, any]:
        """
        Get a human-readable summary of a trace.

        Args:
            trace: Completed trace

        Returns:
            Summary dictionary
        """
        # Calculate stage percentages
        total_latency = trace.total_latency_ms
        stage_percentages = {}
        if total_latency > 0:
            for stage, latency in trace.stage_latencies.items():
                percentage = (latency / total_latency) * 100
                stage_percentages[stage] = f"{latency:.1f}ms ({percentage:.1f}%)"

        # Identify bottlenecks (stages taking >30% of time)
        bottlenecks = []
        for stage, latency in trace.stage_latencies.items():
            if total_latency > 0 and (latency / total_latency) > 0.3:
                bottlenecks.append(stage)

        return {
            "query": trace.query,
            "intent": trace.intent,
            "scope": trace.scope_type,
            "sources_queried": trace.num_sources_queried,
            "source_results": trace.source_results,
            "fusion_method": trace.fusion_method,
            "reranking_applied": trace.reranking_applied,
            "total_latency_ms": f"{trace.total_latency_ms:.1f}ms",
            "stage_breakdown": stage_percentages,
            "bottlenecks": bottlenecks if bottlenecks else None,
        }


class TracingRetrieverWrapper:
    """
    Wrapper that adds tracing to any retriever.

    Automatically tracks all stages and provides trace results.
    """

    def __init__(self, retriever, tracer: RetrievalTracer | None = None):
        """
        Initialize wrapper.

        Args:
            retriever: The retriever to wrap
            tracer: Optional tracer (creates new one if not provided)
        """
        self.retriever = retriever
        self.tracer = tracer or RetrievalTracer()

    async def retrieve_with_trace(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        intent: str = "unknown",
        scope_type: str = "repo",
        **kwargs,
    ) -> tuple[list[dict], RetrievalTrace]:
        """
        Perform retrieval with full tracing.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            query: Search query
            intent: Query intent
            scope_type: Scope type
            **kwargs: Additional retriever arguments

        Returns:
            Tuple of (results, trace)
        """
        # Start trace
        self.tracer.start_trace(query, intent, scope_type)

        # Execute retrieval (assuming retriever has a retrieve method)
        results = await self.retriever.retrieve(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            intent=intent,
            scope_type=scope_type,
            **kwargs,
        )

        # Finalize trace
        trace = self.tracer.finalize_trace()

        return results, trace

    def get_tracer(self) -> RetrievalTracer:
        """Get the underlying tracer for manual control."""
        return self.tracer


class TraceCollector:
    """
    Collects and analyzes traces for performance monitoring.

    Useful for identifying patterns, bottlenecks, and optimization opportunities.
    """

    def __init__(self, max_traces: int = 1000):
        """
        Initialize collector.

        Args:
            max_traces: Maximum number of traces to keep in memory
        """
        self.traces: list[RetrievalTrace] = []
        self.max_traces = max_traces

    def add_trace(self, trace: RetrievalTrace):
        """Add a trace to the collection."""
        self.traces.append(trace)
        if len(self.traces) > self.max_traces:
            self.traces = self.traces[-self.max_traces :]

    def get_statistics(self) -> dict[str, any]:
        """
        Get aggregate statistics across all collected traces.

        Returns:
            Statistics dictionary
        """
        if not self.traces:
            return {"error": "No traces collected"}

        # Calculate average latencies
        total_latencies = [t.total_latency_ms for t in self.traces]
        avg_total = sum(total_latencies) / len(total_latencies)

        # Stage latencies
        stage_stats = {}
        for trace in self.traces:
            for stage, latency in trace.stage_latencies.items():
                if stage not in stage_stats:
                    stage_stats[stage] = []
                stage_stats[stage].append(latency)

        avg_stage_latencies = {
            stage: sum(latencies) / len(latencies)
            for stage, latencies in stage_stats.items()
        }

        # Source usage
        source_usage = {}
        for trace in self.traces:
            for source in trace.source_results.keys():
                source_usage[source] = source_usage.get(source, 0) + 1

        # Intent distribution
        intent_distribution = {}
        for trace in self.traces:
            intent = trace.intent
            intent_distribution[intent] = intent_distribution.get(intent, 0) + 1

        # Reranking usage
        reranking_count = sum(1 for t in self.traces if t.reranking_applied)
        reranking_percentage = (reranking_count / len(self.traces)) * 100

        return {
            "total_traces": len(self.traces),
            "avg_latency_ms": f"{avg_total:.1f}ms",
            "avg_stage_latencies": {
                k: f"{v:.1f}ms" for k, v in avg_stage_latencies.items()
            },
            "source_usage": source_usage,
            "intent_distribution": intent_distribution,
            "reranking_usage": f"{reranking_percentage:.1f}%",
        }

    def get_slow_queries(self, threshold_ms: float = 1000.0) -> list[RetrievalTrace]:
        """
        Get traces that exceeded a latency threshold.

        Args:
            threshold_ms: Latency threshold in milliseconds

        Returns:
            List of slow traces
        """
        return [t for t in self.traces if t.total_latency_ms > threshold_ms]

    def get_traces_by_intent(self, intent: str) -> list[RetrievalTrace]:
        """Get all traces for a specific intent."""
        return [t for t in self.traces if t.intent == intent]
