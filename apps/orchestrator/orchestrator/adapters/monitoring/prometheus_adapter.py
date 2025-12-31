"""
Prometheus Metrics Adapter

기존 MetricsCollector를 IMetricsCollector Port로 래핑
"""

from typing import Any

from codegraph_shared.infra.observability.metrics import MetricsCollector, get_metrics_collector
from codegraph_shared.ports import IMetricsCollector


class PrometheusMetricsAdapter(IMetricsCollector):
    """
    Prometheus 메트릭 수집 Adapter.

    기존 infra/observability/metrics.MetricsCollector를 Port로 래핑.
    """

    def __init__(self, collector: MetricsCollector | None = None):
        """
        Initialize adapter.

        Args:
            collector: MetricsCollector 인스턴스 (None이면 global 사용)
        """
        self._collector = collector or get_metrics_collector()

    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Counter 기록"""
        self._collector.record_counter(name, value, labels)

    def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Gauge 기록"""
        self._collector.record_gauge(name, value, labels)

    def record_histogram(
        self,
        name: str,
        value: float,
    ) -> None:
        """Histogram 기록"""
        self._collector.record_histogram(name, value)

    def get_all_metrics(self) -> dict[str, Any]:
        """모든 메트릭 반환"""
        return self._collector.get_all_metrics()


# Agent-specific 메트릭 이름
class AgentMetrics:
    """Agent 시스템 메트릭 이름"""

    # Agent 실행
    AGENT_TASKS_TOTAL = "agent_tasks_total"
    AGENT_TASK_DURATION_MS = "agent_task_duration_ms"
    AGENT_TASKS_IN_PROGRESS = "agent_tasks_in_progress"

    # Multi-Agent
    MULTI_AGENT_SESSIONS_TOTAL = "multi_agent_sessions_total"
    MULTI_AGENT_LOCKS_TOTAL = "multi_agent_locks_total"
    MULTI_AGENT_CONFLICTS_TOTAL = "multi_agent_conflicts_total"
    MULTI_AGENT_HASH_DRIFTS_TOTAL = "multi_agent_hash_drifts_total"

    # Human-in-the-loop
    HITL_APPROVALS_TOTAL = "hitl_approvals_total"
    HITL_REJECTIONS_TOTAL = "hitl_rejections_total"
    HITL_PARTIAL_COMMITS_TOTAL = "hitl_partial_commits_total"

    # LLM API
    LLM_CALLS_TOTAL = "llm_calls_total"
    LLM_TOKENS_TOTAL = "llm_tokens_total"
    LLM_COST_USD = "llm_cost_usd"
    LLM_LATENCY_MS = "llm_latency_ms"

    # Sandbox
    SANDBOX_EXECUTIONS_TOTAL = "sandbox_executions_total"
    SANDBOX_ERRORS_TOTAL = "sandbox_errors_total"
    SANDBOX_DURATION_MS = "sandbox_duration_ms"

    # Guardrails
    GUARDRAIL_VALIDATIONS_TOTAL = "guardrail_validations_total"
    GUARDRAIL_VIOLATIONS_TOTAL = "guardrail_violations_total"

    # VCS
    VCS_COMMITS_TOTAL = "vcs_commits_total"
    VCS_ROLLBACKS_TOTAL = "vcs_rollbacks_total"

    # Workflow
    WORKFLOW_STEPS_TOTAL = "workflow_steps_total"
    WORKFLOW_STEP_DURATION_MS = "workflow_step_duration_ms"
    WORKFLOW_ERRORS_TOTAL = "workflow_errors_total"


# 편의 함수 (Agent 메트릭)
def record_agent_task_start(metrics: IMetricsCollector, task_id: str) -> None:
    """Agent Task 시작 기록"""
    metrics.record_counter(AgentMetrics.AGENT_TASKS_TOTAL)
    metrics.record_gauge(AgentMetrics.AGENT_TASKS_IN_PROGRESS, 1)


def record_agent_task_complete(metrics: IMetricsCollector, task_id: str, duration_ms: float, success: bool) -> None:
    """Agent Task 완료 기록"""
    metrics.record_histogram(AgentMetrics.AGENT_TASK_DURATION_MS, duration_ms)
    metrics.record_gauge(AgentMetrics.AGENT_TASKS_IN_PROGRESS, 0)
    metrics.record_counter(
        AgentMetrics.AGENT_TASKS_TOTAL,
        labels={"status": "success" if success else "error"},
    )


def record_multi_agent_lock(metrics: IMetricsCollector, agent_id: str, file_path: str) -> None:
    """Multi-Agent Lock 기록"""
    metrics.record_counter(AgentMetrics.MULTI_AGENT_LOCKS_TOTAL, labels={"agent": agent_id})


def record_multi_agent_conflict(metrics: IMetricsCollector, agent_a: str, agent_b: str) -> None:
    """Multi-Agent 충돌 기록"""
    metrics.record_counter(AgentMetrics.MULTI_AGENT_CONFLICTS_TOTAL)


def record_multi_agent_hash_drift(metrics: IMetricsCollector, file_path: str) -> None:
    """Multi-Agent Hash Drift 기록"""
    metrics.record_counter(AgentMetrics.MULTI_AGENT_HASH_DRIFTS_TOTAL)


def record_llm_call(
    metrics: IMetricsCollector,
    model: str,
    tokens: int,
    cost_usd: float,
    latency_ms: float,
) -> None:
    """LLM API 호출 기록"""
    metrics.record_counter(AgentMetrics.LLM_CALLS_TOTAL, labels={"model": model})
    metrics.record_counter(AgentMetrics.LLM_TOKENS_TOTAL, value=tokens, labels={"model": model})
    metrics.record_counter(AgentMetrics.LLM_COST_USD, value=cost_usd, labels={"model": model})
    metrics.record_histogram(AgentMetrics.LLM_LATENCY_MS, latency_ms)


def record_hitl_approval(metrics: IMetricsCollector, approved: bool, file_count: int) -> None:
    """Human-in-the-loop Approval 기록"""
    if approved:
        metrics.record_counter(AgentMetrics.HITL_APPROVALS_TOTAL)
    else:
        metrics.record_counter(AgentMetrics.HITL_REJECTIONS_TOTAL)
