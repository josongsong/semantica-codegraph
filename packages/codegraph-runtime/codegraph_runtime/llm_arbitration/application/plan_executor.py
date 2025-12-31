"""Plan Executor - Generate execution plan from intent"""

from typing import Any
from uuid import uuid4


class PlanExecutor:
    """
    사용자 Intent → RFC Spec 변환 (Planning).

    LLM을 사용하여 자연어 요청을 구조화된 Spec으로 변환.
    """

    async def plan(self, intent: str, context: dict[str, Any] | None = None) -> dict:
        """
        사용자 Intent를 RFC Spec으로 변환.

        Args:
            intent: 자연어 요청 (e.g., "Find SQL injection vulnerabilities")
            context: 추가 컨텍스트 (repo_id, snapshot_id 등)

        Returns:
            Generated spec:
            {
                "intent": "analyze",
                "template_id": "sql_injection",
                "scope": {...},
                "limits": {...},
                "reasoning": "..."
            }
        """
        context = context or {}

        # CRITICAL: PlanExecutor requires LLM for Intent → Spec
        # Currently using simple pattern matching (limited)
        # For production: Implement LLM-based planning

        # Fallback: Simple pattern matching (limited coverage)
        spec = self._simple_pattern_match(intent, context)

        return {
            "spec": spec,
            "reasoning": f"Converted intent '{intent}' to {spec['intent']} spec",
            "confidence": 0.8,
        }

    def _simple_pattern_match(self, intent: str, context: dict[str, Any]) -> dict[str, Any]:
        """간단한 패턴 매칭 (LLM 대체)"""
        intent_lower = intent.lower()

        # Security analysis patterns
        if "sql injection" in intent_lower or "sqli" in intent_lower:
            return {
                "intent": "analyze",
                "template_id": "sql_injection",
                "scope": {
                    "repo_id": context.get("repo_id", ""),
                    "snapshot_id": context.get("snapshot_id", ""),
                },
                "limits": {"max_paths": 200, "timeout_ms": 30000},
            }

        if "xss" in intent_lower or "cross-site scripting" in intent_lower:
            return {
                "intent": "analyze",
                "template_id": "xss",
                "scope": {
                    "repo_id": context.get("repo_id", ""),
                    "snapshot_id": context.get("snapshot_id", ""),
                },
                "limits": {"max_paths": 200, "timeout_ms": 30000},
            }

        # Retrieval patterns
        if "find" in intent_lower or "search" in intent_lower:
            return {
                "intent": "retrieve",
                "mode": "graph_guided",
                "scope": {
                    "repo_id": context.get("repo_id", ""),
                    "snapshot_id": context.get("snapshot_id", ""),
                },
                "seed_symbols": [],
                "k": 50,
            }

        # Default: retrieve
        return {
            "intent": "retrieve",
            "mode": "hybrid",
            "scope": {
                "repo_id": context.get("repo_id", ""),
                "snapshot_id": context.get("snapshot_id", ""),
            },
            "seed_symbols": [],
            "k": 50,
        }
