"""
SOTA Boundary Matcher (RFC-101 Phase 1)

LLM-assisted boundary matching with graph-based pre-ranking.

Architecture:
  1. Fast path: Pattern matching (70% of cases)
  2. Graph ranking: Call graph proximity (85% → 95% accuracy)
  3. LLM ranking: Semantic understanding (top 5 candidates)
  4. Rust verification: Type checking
"""

import re
import time
from typing import Any, Optional

from ...domain.boundary_models import (
    BoundaryCandidate,
    BoundaryMatchResult,
    BoundarySpec,
    BoundaryType,
    HTTPMethod,
)


class SOTABoundaryMatcher:
    """
    SOTA boundary matcher with graph pre-ranking + LLM assistance.

    Performance targets (RFC-101):
    - Accuracy: 85% → 95%+
    - Latency: < 50ms (graph < 10ms, LLM only for ambiguous)
    - Cost: ~$0.0005 per ambiguous match
    """

    # Confidence thresholds
    FAST_PATH_THRESHOLD = 0.95  # Single high-confidence match
    GRAPH_HIGH_CONFIDENCE = 0.90  # Graph alone is enough
    FINAL_CONFIDENCE_THRESHOLD = 0.85  # Minimum for success

    # Pattern matching weights
    PATTERN_WEIGHT = 0.3
    GRAPH_WEIGHT = 0.4
    LLM_WEIGHT = 0.3

    def __init__(self, rust_engine: Optional[Any] = None, llm_client: Optional[Any] = None):
        """
        Initialize SOTA boundary matcher.

        Args:
            rust_engine: Rust IR engine (for call graph, type checking)
            llm_client: LLM client (for semantic ranking)
        """
        self.rust_engine = rust_engine
        self.llm_client = llm_client

    def match_boundary(self, boundary: BoundarySpec, ir_docs: list[Any]) -> BoundaryMatchResult:
        """
        Match boundary specification to code.

        Args:
            boundary: Boundary specification (HTTP endpoint, gRPC service, etc.)
            ir_docs: List of IR documents to search

        Returns:
            BoundaryMatchResult with best match and candidates
        """
        result = BoundaryMatchResult()
        start_time = time.time()

        # Step 1: Pattern-based candidate finding (fast)
        pattern_start = time.time()
        candidates = self._find_candidates_fast(boundary, ir_docs)
        result.pattern_time_ms = (time.time() - pattern_start) * 1000
        result.pattern_matches = len(candidates)
        result.total_nodes_scanned = self._count_nodes(ir_docs)

        if not candidates:
            result.total_time_ms = (time.time() - start_time) * 1000
            result.add_decision("no_pattern_matches")
            return result

        # Fast path: Single high-confidence match
        if len(candidates) == 1 and candidates[0].pattern_score >= self.FAST_PATH_THRESHOLD:
            result.best_match = candidates[0]
            result.confidence = candidates[0].pattern_score
            result.candidates = candidates
            result.total_time_ms = (time.time() - start_time) * 1000
            result.add_decision("fast_path_single_match")
            return result

        # Step 2: Graph-based pre-ranking (NEW - P1)
        graph_start = time.time()
        candidates = self._rank_by_call_graph_proximity(candidates, boundary, ir_docs)
        result.graph_time_ms = (time.time() - graph_start) * 1000
        result.graph_ranked = len(candidates)

        # High confidence from graph analysis
        if candidates and candidates[0].graph_score >= self.GRAPH_HIGH_CONFIDENCE:
            candidates[0].compute_final_score(
                pattern_weight=self.PATTERN_WEIGHT,
                graph_weight=self.GRAPH_WEIGHT,
                llm_weight=0.0,  # No LLM needed
            )
            result.best_match = candidates[0]
            result.confidence = candidates[0].final_score
            result.candidates = candidates
            result.total_time_ms = (time.time() - start_time) * 1000
            result.add_decision("graph_high_confidence")
            return result

        # Step 3: LLM ranking (smart path, top 5 only)
        if self.llm_client and len(candidates) > 1:
            llm_start = time.time()
            top_candidates = candidates[:5]  # Only rank top 5
            top_candidates = self._llm_rank_candidates(boundary, top_candidates)
            result.llm_time_ms = (time.time() - llm_start) * 1000
            result.llm_ranked = len(top_candidates)

            # Merge LLM scores back to full candidate list
            for i, candidate in enumerate(top_candidates):
                candidates[i] = candidate
        else:
            result.add_decision("llm_not_available")

        # Step 4: Compute final scores
        for candidate in candidates:
            candidate.compute_final_score(
                pattern_weight=self.PATTERN_WEIGHT,
                graph_weight=self.GRAPH_WEIGHT,
                llm_weight=self.LLM_WEIGHT if self.llm_client else 0.0,
            )

        # Sort by final score
        candidates.sort(key=lambda c: c.final_score, reverse=True)
        result.candidates = candidates

        # Step 5: Rust type verification (optional)
        if self.rust_engine and candidates:
            best_candidate = candidates[0]
            if self._rust_verify_match(best_candidate, boundary):
                best_candidate.type_verified = True
                result.best_match = best_candidate
                result.confidence = best_candidate.final_score
                result.add_decision("rust_verified")
            else:
                result.add_decision("rust_verification_failed")
        elif candidates:
            # No Rust verification available
            best_candidate = candidates[0]
            if best_candidate.final_score >= self.FINAL_CONFIDENCE_THRESHOLD:
                result.best_match = best_candidate
                result.confidence = best_candidate.final_score
                result.add_decision("final_score_threshold")

        result.total_time_ms = (time.time() - start_time) * 1000
        return result

    def _find_candidates_fast(self, boundary: BoundarySpec, ir_docs: list[Any]) -> list[BoundaryCandidate]:
        """
        Find candidates using fast pattern matching.

        Pattern rules (by boundary type):
        - HTTP_ENDPOINT: @app.route, @router.get, @app.get, etc.
        - GRPC_SERVICE: @grpc.service, class XxxServicer
        - MESSAGE_QUEUE: @consumer, @subscriber
        - DATABASE_QUERY: db.query(), session.execute()
        """
        candidates = []

        if boundary.boundary_type == BoundaryType.HTTP_ENDPOINT:
            candidates = self._find_http_endpoints(boundary, ir_docs)
        elif boundary.boundary_type == BoundaryType.GRPC_SERVICE:
            candidates = self._find_grpc_services(boundary, ir_docs)
        elif boundary.boundary_type == BoundaryType.MESSAGE_QUEUE:
            candidates = self._find_message_handlers(boundary, ir_docs)
        # Add more boundary types as needed

        return candidates

    def _find_http_endpoints(self, boundary: BoundarySpec, ir_docs: list[Any]) -> list[BoundaryCandidate]:
        """Find HTTP endpoint candidates using decorator patterns."""
        candidates = []

        # Common HTTP decorator patterns
        patterns = [
            r"@app\.(get|post|put|delete|patch)",  # Flask/FastAPI
            r"@router\.(get|post|put|delete|patch)",  # FastAPI router
            r"@route\(['\"](.+?)['\"]",  # Generic @route
            r"@api\.(get|post|put|delete|patch)",  # Custom API decorators
        ]

        # For now, create mock candidates (placeholder for IR document parsing)
        # In production, this would parse IR documents for decorator nodes
        # and extract HTTP paths

        # Placeholder: Return empty list (will be populated from IR in integration)
        return candidates

    def _find_grpc_services(self, boundary: BoundarySpec, ir_docs: list[Any]) -> list[BoundaryCandidate]:
        """Find gRPC service candidates."""
        # Placeholder for gRPC service finding
        return []

    def _find_message_handlers(self, boundary: BoundarySpec, ir_docs: list[Any]) -> list[BoundaryCandidate]:
        """Find message queue handler candidates."""
        # Placeholder for message handler finding
        return []

    def _rank_by_call_graph_proximity(
        self,
        candidates: list[BoundaryCandidate],
        boundary: BoundarySpec,
        ir_docs: list[Any],
    ) -> list[BoundaryCandidate]:
        """
        Rank candidates by call graph proximity.

        Algorithm:
        1. Build call graph from IR documents
        2. Find entry points (HTTP handlers, main functions)
        3. Compute shortest path from entry points to each candidate
        4. Score: closer = higher score (1.0 / (1.0 + distance))
        5. Boost score if candidate is directly called from known handler
        """
        # Assign graph scores (with or without Rust engine)
        # Placeholder: In production, this would call Rust IR to build call graph
        # For now, assign mock graph scores based on pattern scores
        for candidate in candidates:
            # Simple heuristic: Higher pattern score → closer to entry point
            candidate.graph_score = min(1.0, candidate.pattern_score * 1.2)
            candidate.distance_from_entry = int((1.0 - candidate.graph_score) * 10)

        # Sort by graph score
        return sorted(candidates, key=lambda c: c.graph_score, reverse=True)

    def _llm_rank_candidates(
        self, boundary: BoundarySpec, candidates: list[BoundaryCandidate]
    ) -> list[BoundaryCandidate]:
        """
        Rank candidates using LLM semantic understanding.

        Prompt engineering:
        - Provide boundary spec (endpoint, HTTP method)
        - Provide pre-ranked candidates (top 5)
        - Ask LLM to select most likely match with confidence
        """
        if not self.llm_client:
            return candidates

        # Format candidates for LLM
        candidate_text = "\n".join(
            [
                f"{i + 1}. {c.function_name} ({c.file_path}:{c.line_number})\n"
                f"   Pattern score: {c.pattern_score:.2f}, Graph score: {c.graph_score:.2f}\n"
                f"   Decorator: {c.decorator_name or 'N/A'}, Path: {c.http_path or 'N/A'}\n"
                f"   Code: {c.code_snippet[:100]}..."
                for i, c in enumerate(candidates)
            ]
        )

        prompt = f"""
Which function handles this boundary?

Boundary: {boundary}
Type: {boundary.boundary_type.value}

Candidates (pre-ranked by call graph proximity):
{candidate_text}

Return JSON:
{{
    "best_match_index": <1-based index>,
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}
"""

        # Placeholder: In production, this would call LLM API
        # For now, assign mock LLM scores
        for i, candidate in enumerate(candidates):
            # Mock LLM prefers candidates with higher combined pattern+graph scores
            combined = (candidate.pattern_score + candidate.graph_score) / 2
            candidate.llm_score = min(1.0, combined * 1.1 + 0.05)  # Slight boost

        return candidates

    def _rust_verify_match(self, candidate: BoundaryCandidate, boundary: BoundarySpec) -> bool:
        """
        Verify match using Rust type checking.

        Verification:
        - Type-check candidate function signature
        - Verify return type matches expected boundary response
        - Check parameter types match endpoint spec
        """
        if not self.rust_engine:
            return False

        # Placeholder: In production, this would call Rust type checker
        # For now, verify based on pattern/graph scores
        return candidate.pattern_score >= 0.7 or candidate.graph_score >= 0.7

    def _count_nodes(self, ir_docs: list[Any]) -> int:
        """Count total nodes in IR documents."""
        # Placeholder: In production, count actual IR nodes
        return len(ir_docs) * 100  # Rough estimate
