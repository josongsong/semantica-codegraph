"""
Alerting Rules for Production Monitoring

Provides threshold-based alerting for performance and reliability monitoring.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock

from src.infra.observability.metrics import MetricsCollector, get_metrics_collector


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"  # Informational, no action needed
    WARNING = "warning"  # Potential issue, investigate
    ERROR = "error"  # Active issue, action needed
    CRITICAL = "critical"  # Severe issue, immediate action needed


class AlertChannel(Enum):
    """Alert notification channels."""

    LOG = "log"  # Log only (default)
    SLACK = "slack"  # Slack webhook
    PAGERDUTY = "pagerduty"  # PagerDuty incident
    EMAIL = "email"  # Email notification


@dataclass
class AlertRule:
    """
    Definition of an alert rule.

    An alert fires when the condition is met for the specified duration.
    """

    # Identification
    name: str
    description: str

    # Condition
    metric_name: str
    threshold: float
    comparison: str  # "gt", "lt", "gte", "lte", "eq"

    # Timing
    duration_seconds: float = 60.0  # Alert fires if condition true for this long
    cooldown_seconds: float = 300.0  # Min time between repeated alerts

    # Severity and routing
    severity: AlertSeverity = AlertSeverity.WARNING
    channels: list[AlertChannel] = field(default_factory=lambda: [AlertChannel.LOG])

    # Metadata
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass
class AlertState:
    """Current state of an alert rule."""

    rule: AlertRule
    is_firing: bool = False
    first_triggered_at: datetime | None = None
    last_fired_at: datetime | None = None
    fire_count: int = 0


@dataclass
class Alert:
    """A fired alert."""

    # Rule info
    rule_name: str
    severity: AlertSeverity
    description: str

    # Triggering data
    metric_name: str
    current_value: float
    threshold: float

    # Timing
    triggered_at: datetime
    fired_at: datetime

    # Metadata
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)


class AlertManager:
    """
    Manages alert rules and fires alerts based on metrics.

    Example:
        ```python
        manager = AlertManager(metrics_collector)

        # Define alert rule
        manager.add_rule(AlertRule(
            name="high_latency",
            description="Search latency p99 exceeds threshold",
            metric_name="search_latency_p99_ms",
            threshold=1000.0,
            comparison="gt",
            duration_seconds=60.0,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.SLACK],
        ))

        # Check alerts periodically
        manager.evaluate_all()
        ```
    """

    def __init__(
        self,
        metrics_collector: MetricsCollector | None = None,
        slack_webhook_url: str | None = None,
        email_config: dict | None = None,
        pagerduty_routing_key: str | None = None,
    ):
        """
        Initialize alert manager.

        Args:
            metrics_collector: Metrics collector to query (defaults to global)
            slack_webhook_url: Slack incoming webhook URL
            email_config: Email config dict {smtp_host, smtp_port, from_addr, to_addrs}
            pagerduty_routing_key: PagerDuty routing key for events API
        """
        self.metrics = metrics_collector or get_metrics_collector()

        # Channel configurations
        self._slack_webhook_url = slack_webhook_url
        self._email_config = email_config or {}
        self._pagerduty_routing_key = pagerduty_routing_key

        # Alert rules and state
        self._rules: dict[str, AlertRule] = {}
        self._states: dict[str, AlertState] = {}

        # Alert handlers - register all channels
        self._handlers: dict[AlertChannel, Callable[[Alert], None]] = {
            AlertChannel.LOG: self._handle_log,
            AlertChannel.SLACK: self._handle_slack,
            AlertChannel.EMAIL: self._handle_email,
            AlertChannel.PAGERDUTY: self._handle_pagerduty,
        }

        # Thread safety
        self._lock = Lock()

        # Alert history (for testing/debugging)
        self._alert_history: list[Alert] = []

    def add_rule(self, rule: AlertRule) -> None:
        """
        Add or update an alert rule.

        Args:
            rule: Alert rule definition
        """
        with self._lock:
            self._rules[rule.name] = rule
            if rule.name not in self._states:
                self._states[rule.name] = AlertState(rule=rule)

    def remove_rule(self, rule_name: str) -> None:
        """
        Remove an alert rule.

        Args:
            rule_name: Name of rule to remove
        """
        with self._lock:
            self._rules.pop(rule_name, None)
            self._states.pop(rule_name, None)

    def evaluate_all(self) -> list[Alert]:
        """
        Evaluate all alert rules and fire alerts if needed.

        Returns:
            List of alerts that fired
        """
        fired_alerts = []

        with self._lock:
            for rule in self._rules.values():
                alert = self._evaluate_rule(rule)
                if alert:
                    fired_alerts.append(alert)

        return fired_alerts

    def _evaluate_rule(self, rule: AlertRule) -> Alert | None:
        """
        Evaluate a single alert rule.

        Returns:
            Alert if condition is met, None otherwise
        """
        state = self._states[rule.name]

        # Get current metric value
        current_value = self._get_metric_value(rule.metric_name)
        if current_value is None:
            return None

        # Check condition
        condition_met = self._check_condition(current_value, rule.threshold, rule.comparison)

        now = datetime.now()

        if condition_met:
            # Condition is true
            if not state.is_firing:
                # First time triggering
                state.first_triggered_at = now
                state.is_firing = True

            # Check if duration threshold met
            if state.first_triggered_at:
                duration = (now - state.first_triggered_at).total_seconds()
                if duration >= rule.duration_seconds:
                    # Check cooldown
                    if self._check_cooldown(state, now, rule.cooldown_seconds):
                        # Fire alert!
                        alert = self._fire_alert(rule, state, current_value, now)
                        return alert

        else:
            # Condition is false, reset state
            if state.is_firing:
                state.is_firing = False
                state.first_triggered_at = None

        return None

    def _get_metric_value(self, metric_name: str) -> float | None:
        """Get current value of a metric."""
        # Try histogram stats first (for percentiles)
        if "_p99" in metric_name:
            base_name = metric_name.replace("_p99", "")
            stats = self.metrics.get_histogram_stats(base_name)
            return stats.get("p99")
        elif "_p95" in metric_name:
            base_name = metric_name.replace("_p95", "")
            stats = self.metrics.get_histogram_stats(base_name)
            return stats.get("p95")
        elif "_p50" in metric_name:
            base_name = metric_name.replace("_p50", "")
            stats = self.metrics.get_histogram_stats(base_name)
            return stats.get("p50")

        # Try gauge
        value = self.metrics.get_gauge(metric_name)
        if value != 0.0:
            return value

        # Try counter
        value = self.metrics.get_counter(metric_name)
        return value if value != 0.0 else None

    def _check_condition(self, value: float, threshold: float, comparison: str) -> bool:
        """Check if condition is met."""
        if comparison == "gt":
            return value > threshold
        elif comparison == "gte":
            return value >= threshold
        elif comparison == "lt":
            return value < threshold
        elif comparison == "lte":
            return value <= threshold
        elif comparison == "eq":
            return value == threshold
        return False

    def _check_cooldown(self, state: AlertState, now: datetime, cooldown_seconds: float) -> bool:
        """Check if cooldown period has passed since last alert."""
        if state.last_fired_at is None:
            return True

        elapsed = (now - state.last_fired_at).total_seconds()
        return elapsed >= cooldown_seconds

    def _fire_alert(
        self,
        rule: AlertRule,
        state: AlertState,
        current_value: float,
        now: datetime,
    ) -> Alert:
        """Fire an alert and notify via configured channels."""
        # Create alert
        alert = Alert(
            rule_name=rule.name,
            severity=rule.severity,
            description=rule.description,
            metric_name=rule.metric_name,
            current_value=current_value,
            threshold=rule.threshold,
            triggered_at=state.first_triggered_at or now,
            fired_at=now,
            labels=rule.labels,
            annotations=rule.annotations,
        )

        # Update state
        state.last_fired_at = now
        state.fire_count += 1

        # Store in history
        self._alert_history.append(alert)

        # Notify via channels
        for channel in rule.channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    handler(alert)
                except Exception as e:
                    print(f"Error sending alert to {channel.value}: {e}")

        return alert

    def register_handler(self, channel: AlertChannel, handler: Callable[[Alert], None]) -> None:
        """
        Register a custom alert handler.

        Args:
            channel: Alert channel
            handler: Function to handle alert

        Example:
            ```python
            def send_to_slack(alert: Alert):
                requests.post(slack_webhook_url, json={"text": alert.description})

            manager.register_handler(AlertChannel.SLACK, send_to_slack)
            ```
        """
        with self._lock:
            self._handlers[channel] = handler

    def _handle_log(self, alert: Alert) -> None:
        """Default handler: log to stdout."""
        print(
            f"[{alert.severity.value.upper()}] {alert.rule_name}: "
            f"{alert.description} "
            f"(current={alert.current_value:.2f}, threshold={alert.threshold:.2f})"
        )

    def _handle_slack(self, alert: Alert) -> None:
        """Send alert to Slack via incoming webhook."""
        if not self._slack_webhook_url:
            print(f"[SLACK] (no webhook configured) {alert.rule_name}: {alert.description}")
            return

        try:
            import httpx

            # Build Slack message with formatting
            severity_emoji = {
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.ERROR: "🔴",
                AlertSeverity.CRITICAL: "🚨",
            }.get(alert.severity, "📢")

            payload = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{severity_emoji} Alert: {alert.rule_name}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{alert.description}*\n\n"
                            f"• Metric: `{alert.metric_name}`\n"
                            f"• Current: `{alert.current_value:.2f}`\n"
                            f"• Threshold: `{alert.threshold:.2f}`\n"
                            f"• Severity: `{alert.severity.value}`",
                        },
                    },
                ],
            }

            # Add annotations if present
            if alert.annotations:
                annotation_text = "\n".join(f"• {k}: {v}" for k, v in alert.annotations.items())
                payload["blocks"].append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Details:*\n{annotation_text}"},
                    }
                )

            response = httpx.post(self._slack_webhook_url, json=payload, timeout=5.0)
            response.raise_for_status()

        except Exception as e:
            print(f"[SLACK ERROR] Failed to send alert: {e}")

    def _handle_email(self, alert: Alert) -> None:
        """Send alert via email using SMTP."""
        if not self._email_config.get("smtp_host"):
            print(f"[EMAIL] (no SMTP configured) {alert.rule_name}: {alert.description}")
            return

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert.severity.value.upper()}] Alert: {alert.rule_name}"
            msg["From"] = self._email_config.get("from_addr", "alerts@semantica.dev")
            msg["To"] = ", ".join(self._email_config.get("to_addrs", []))

            # Plain text body
            text_body = f"""
Alert: {alert.rule_name}
Severity: {alert.severity.value}

{alert.description}

Metric: {alert.metric_name}
Current Value: {alert.current_value:.2f}
Threshold: {alert.threshold:.2f}
Triggered At: {alert.triggered_at.isoformat()}
"""

            # HTML body
            html_body = f"""
<html>
<body>
<h2>🔔 Alert: {alert.rule_name}</h2>
<p><strong>{alert.description}</strong></p>
<table border="1" cellpadding="5">
    <tr><td>Severity</td><td>{alert.severity.value}</td></tr>
    <tr><td>Metric</td><td>{alert.metric_name}</td></tr>
    <tr><td>Current Value</td><td>{alert.current_value:.2f}</td></tr>
    <tr><td>Threshold</td><td>{alert.threshold:.2f}</td></tr>
    <tr><td>Triggered At</td><td>{alert.triggered_at.isoformat()}</td></tr>
</table>
</body>
</html>
"""

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            smtp_host = self._email_config["smtp_host"]
            smtp_port = self._email_config.get("smtp_port", 587)

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if self._email_config.get("use_tls", True):
                    server.starttls()
                if self._email_config.get("username"):
                    server.login(self._email_config["username"], self._email_config.get("password", ""))
                server.send_message(msg)

        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send alert: {e}")

    def _handle_pagerduty(self, alert: Alert) -> None:
        """Send alert to PagerDuty via Events API v2."""
        if not self._pagerduty_routing_key:
            print(f"[PAGERDUTY] (no routing key configured) {alert.rule_name}: {alert.description}")
            return

        try:
            import httpx

            # Map severity to PagerDuty severity
            pd_severity = {
                AlertSeverity.INFO: "info",
                AlertSeverity.WARNING: "warning",
                AlertSeverity.ERROR: "error",
                AlertSeverity.CRITICAL: "critical",
            }.get(alert.severity, "warning")

            payload = {
                "routing_key": self._pagerduty_routing_key,
                "event_action": "trigger",
                "dedup_key": f"semantica-{alert.rule_name}",
                "payload": {
                    "summary": f"{alert.rule_name}: {alert.description}",
                    "severity": pd_severity,
                    "source": "semantica-codegraph",
                    "timestamp": alert.fired_at.isoformat(),
                    "custom_details": {
                        "metric_name": alert.metric_name,
                        "current_value": alert.current_value,
                        "threshold": alert.threshold,
                        "labels": alert.labels,
                        "annotations": alert.annotations,
                    },
                },
            }

            response = httpx.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=5.0,
            )
            response.raise_for_status()

        except Exception as e:
            print(f"[PAGERDUTY ERROR] Failed to send alert: {e}")

    def get_active_alerts(self) -> list[AlertState]:
        """Get all currently firing alerts."""
        with self._lock:
            return [state for state in self._states.values() if state.is_firing]

    def get_alert_history(self, limit: int = 100) -> list[Alert]:
        """Get recent alert history."""
        with self._lock:
            return self._alert_history[-limit:]

    def clear_history(self) -> None:
        """Clear alert history (for testing)."""
        with self._lock:
            self._alert_history.clear()


# Predefined alert rules (from roadmap P0-3)
def get_standard_alert_rules() -> list[AlertRule]:
    """
    Get standard alert rules for production monitoring.

    Rules from IMPLEMENTATION_ROADMAP P0-3:
    - search_latency_p99 > 1000ms
    - error_rate_5min > 5%
    - embedding_api_failure > 10 (consecutive failures)
    """
    return [
        AlertRule(
            name="high_search_latency",
            description="Search latency p99 exceeds 1 second",
            metric_name="search_latency_p99_ms",
            threshold=1000.0,
            comparison="gt",
            duration_seconds=60.0,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG, AlertChannel.SLACK],
            annotations={
                "summary": "Search performance degradation detected",
                "runbook": "Check query complexity, index health, and resource usage",
            },
        ),
        AlertRule(
            name="high_error_rate",
            description="Error rate exceeds 5% over 5 minutes",
            metric_name="error_rate_percent",
            threshold=5.0,
            comparison="gt",
            duration_seconds=300.0,  # 5 minutes
            severity=AlertSeverity.ERROR,
            channels=[AlertChannel.LOG, AlertChannel.SLACK, AlertChannel.PAGERDUTY],
            annotations={
                "summary": "High error rate detected",
                "runbook": "Check logs for error patterns, verify service health",
            },
        ),
        AlertRule(
            name="embedding_api_failures",
            description="Consecutive embedding API failures exceed threshold",
            metric_name="embedding_api_consecutive_failures",
            threshold=10.0,
            comparison="gte",
            duration_seconds=10.0,
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.LOG, AlertChannel.PAGERDUTY],
            annotations={
                "summary": "Embedding API is unreachable or failing",
                "runbook": "Check API credentials, rate limits, and service status",
            },
        ),
        AlertRule(
            name="indexing_failure_rate",
            description="Indexing job failure rate exceeds 10%",
            metric_name="indexing_failure_rate_percent",
            threshold=10.0,
            comparison="gt",
            duration_seconds=300.0,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG, AlertChannel.SLACK],
            annotations={
                "summary": "High indexing failure rate",
                "runbook": "Check parsing errors, resource limits, and repository access",
            },
        ),
        AlertRule(
            name="cache_miss_rate_high",
            description="Cache miss rate exceeds 50%",
            metric_name="cache_miss_rate_percent",
            threshold=50.0,
            comparison="gt",
            duration_seconds=300.0,
            severity=AlertSeverity.INFO,
            channels=[AlertChannel.LOG],
            annotations={
                "summary": "Cache effectiveness is low",
                "runbook": "Check cache configuration, TTL settings, and memory limits",
            },
        ),
        AlertRule(
            name="memory_usage_high",
            description="Memory usage exceeds 80%",
            metric_name="memory_usage_percent",
            threshold=80.0,
            comparison="gt",
            duration_seconds=120.0,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG, AlertChannel.SLACK],
            annotations={
                "summary": "High memory usage detected",
                "runbook": "Check for memory leaks, increase resources, or scale horizontally",
            },
        ),
    ]


def _example_usage():
    """Example demonstrating alerting usage."""
    from src.infra.observability.metrics import record_gauge, record_histogram

    # Create alert manager
    manager = AlertManager()

    # Add standard rules
    for rule in get_standard_alert_rules():
        manager.add_rule(rule)

    # Simulate metrics
    for i in range(20):
        # Simulate increasing latency
        latency = 500.0 + (i * 50)  # 500ms -> 1450ms
        record_histogram("search_latency_ms", latency)

        # Simulate error rate
        error_rate = 2.0 + (i * 0.3)  # 2% -> 7.7%
        record_gauge("error_rate_percent", error_rate)

        # Evaluate alerts
        fired = manager.evaluate_all()
        if fired:
            print(f"\n=== Iteration {i}: {len(fired)} alert(s) fired ===")
            for alert in fired:
                print(f"  {alert.rule_name}: {alert.description}")

        time.sleep(0.1)

    # Show alert history
    print("\n=== Alert History ===")
    for alert in manager.get_alert_history():
        print(f"{alert.fired_at.strftime('%H:%M:%S')} - {alert.rule_name}")


if __name__ == "__main__":
    _example_usage()
