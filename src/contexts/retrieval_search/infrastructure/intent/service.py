"""
Intent Analysis Service

Coordinates LLM-based and rule-based intent classification with fallback.
"""

import asyncio
import json
import time
from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.intent.models import (
    IntentClassificationResult,
    IntentKind,
    QueryIntent,
)
from src.contexts.retrieval_search.infrastructure.intent.monitor import IntentFallbackMonitor
from src.contexts.retrieval_search.infrastructure.intent.prompts import build_classification_prompt
from src.contexts.retrieval_search.infrastructure.intent.rule_classifier import RuleBasedClassifier

if TYPE_CHECKING:
    from src.ports import LLMPort
from src.common.observability import get_logger

logger = get_logger(__name__)


class IntentAnalyzer:
    """
    Query intent analyzer with LLM and rule-based fallback.

    Attempts LLM classification first, falls back to rule-based
    if LLM fails or times out.
    """

    def __init__(
        self,
        llm_client: "LLMPort",
        timeout_seconds: float = 1.5,
        enable_llm: bool = True,
    ):
        """
        Initialize intent analyzer.

        Args:
            llm_client: LLM client for classification
            timeout_seconds: Timeout for LLM classification
            enable_llm: Whether to use LLM (can disable for testing)
        """
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds
        self.enable_llm = enable_llm

        self.rule_classifier = RuleBasedClassifier()
        self.monitor = IntentFallbackMonitor(alert_threshold=100, alert_rate=0.3)

    async def analyze_intent(self, query: str) -> IntentClassificationResult:
        """
        Analyze query intent with LLM → rule-based fallback.

        Args:
            query: User query string

        Returns:
            IntentClassificationResult with classified intent
        """
        start_time = time.time()

        # Try LLM classification first (if enabled)
        if self.enable_llm:
            try:
                intent = await self._llm_classify(query)
                latency_ms = (time.time() - start_time) * 1000

                self.monitor.log_llm_success(latency_ms)

                logger.debug(f"LLM intent classification succeeded: {intent.kind.value} ({latency_ms:.1f}ms)")

                return IntentClassificationResult(
                    intent=intent,
                    method="llm",
                    latency_ms=latency_ms,
                )

            except asyncio.TimeoutError:
                logger.warning(f"LLM intent classification timeout ({self.timeout_seconds}s)")
                self.monitor.log_fallback("timeout")
                return self._fallback_to_rule(query, start_time, "timeout")

            except json.JSONDecodeError as e:
                logger.warning(f"LLM intent response parse error: {e}")
                self.monitor.log_fallback("parse_error")
                return self._fallback_to_rule(query, start_time, "parse_error")

            except Exception as e:
                logger.warning(f"LLM intent classification error: {e}")
                self.monitor.log_fallback("llm_error")
                return self._fallback_to_rule(query, start_time, "llm_error")

        # LLM disabled → use rule-based
        return self._fallback_to_rule(query, start_time, "llm_disabled")

    async def _llm_classify(self, query: str) -> QueryIntent:
        """
        Classify query using LLM with timeout.

        Args:
            query: User query string

        Returns:
            QueryIntent from LLM

        Raises:
            asyncio.TimeoutError: If LLM takes too long
            json.JSONDecodeError: If LLM response is invalid JSON
        """
        # Build prompt
        prompt = build_classification_prompt(query, include_examples=False)

        # Call LLM with timeout
        response_text = await asyncio.wait_for(
            self.llm_client.generate(prompt, max_tokens=200, temperature=0.3),
            timeout=self.timeout_seconds,
        )

        # Parse JSON response
        response_json = self._extract_json(response_text)

        # Convert to QueryIntent
        intent = self._parse_llm_response(response_json, query)

        return intent

    def _extract_json(self, text: str) -> dict:
        """
        Extract JSON from LLM response (handles markdown code blocks).

        Args:
            text: LLM response text

        Returns:
            Parsed JSON dict

        Raises:
            json.JSONDecodeError: If no valid JSON found
        """
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Last attempt: find first {...} block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))

        raise json.JSONDecodeError("No valid JSON found in LLM response", text, 0)

    def _parse_llm_response(self, response: dict, query: str) -> QueryIntent:
        """
        Parse LLM JSON response into QueryIntent.

        Args:
            response: Parsed JSON dict from LLM
            query: Original query string

        Returns:
            QueryIntent object
        """
        intent_str = response.get("intent", "code_search")
        try:
            intent_kind = IntentKind(intent_str)
        except ValueError:
            logger.warning(f"Unknown intent kind '{intent_str}', defaulting to code_search")
            intent_kind = IntentKind.CODE_SEARCH

        return QueryIntent(
            kind=intent_kind,
            symbol_names=response.get("symbol_names", []),
            file_paths=response.get("file_paths", []),
            module_paths=response.get("module_paths", []),
            confidence=float(response.get("confidence", 0.8)),
            raw_query=query,
        )

    def _fallback_to_rule(self, query: str, start_time: float, reason: str) -> IntentClassificationResult:
        """
        Fallback to rule-based classification.

        Args:
            query: User query string
            start_time: Start time for latency calculation
            reason: Reason for fallback

        Returns:
            IntentClassificationResult using rule-based method
        """
        intent = self.rule_classifier.classify(query)
        latency_ms = (time.time() - start_time) * 1000

        logger.debug(
            f"Rule-based intent classification: {intent.kind.value} "
            f"(confidence: {intent.confidence:.2f}, {latency_ms:.1f}ms)"
        )

        return IntentClassificationResult(
            intent=intent,
            method="rule",
            latency_ms=latency_ms,
            fallback_reason=reason,
        )

    def get_monitor_stats(self) -> dict:
        """
        Get monitoring statistics.

        Returns:
            Dict with fallback statistics
        """
        return self.monitor.get_summary()
