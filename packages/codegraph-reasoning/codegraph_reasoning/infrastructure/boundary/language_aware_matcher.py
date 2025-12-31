"""
Language-Aware SOTA Boundary Matcher (RFC-101 Cross-Language Support)

Extends SOTA Boundary Matcher with multi-language support.
Uses Hexagonal Architecture + Strategy Pattern.
"""

import time
from typing import Any, Optional

from ...domain.boundary_models import (
    BoundaryCandidate,
    BoundaryMatchResult,
    BoundarySpec,
    BoundaryType,
)
from ...domain.language_detector import (
    BoundaryDetectionContext,
    DetectedBoundary,
    IBoundaryDetector,
    Language,
)
from .language_detector_registry import LanguageDetectorRegistry


class LanguageAwareSOTAMatcher:
    """
    Language-aware SOTA boundary matcher.

    Extends base SOTABoundaryMatcher with multi-language support.
    Delegates language-specific detection to registered detectors.

    Follows:
    - Hexagonal Architecture (ports & adapters)
    - Strategy Pattern (language-specific detectors)
    - Dependency Injection (detector registry)
    """

    # Confidence thresholds
    FAST_PATH_THRESHOLD = 0.95
    GRAPH_HIGH_CONFIDENCE = 0.90
    FINAL_CONFIDENCE_THRESHOLD = 0.85

    # Pattern matching weights
    PATTERN_WEIGHT = 0.3
    GRAPH_WEIGHT = 0.4
    LLM_WEIGHT = 0.3

    def __init__(
        self,
        detector_registry: Optional[LanguageDetectorRegistry] = None,
        rust_engine: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        """
        Initialize language-aware matcher.

        Args:
            detector_registry: Language detector registry (DI)
            rust_engine: Rust IR engine (for call graph)
            llm_client: LLM client (for semantic ranking)
        """
        self.detector_registry = detector_registry or LanguageDetectorRegistry()
        self.rust_engine = rust_engine
        self.llm_client = llm_client

    def match_boundary(
        self,
        boundary: BoundarySpec,
        ir_docs: list[Any],
        language: Optional[Language] = None,
        file_paths: Optional[list[str]] = None,
    ) -> BoundaryMatchResult:
        """
        Match boundary specification to code (language-aware).

        Args:
            boundary: Boundary specification
            ir_docs: IR documents to search
            language: Optional language hint (auto-detected if not provided)
            file_paths: Optional file paths (for language detection)

        Returns:
            BoundaryMatchResult with best match
        """
        result = BoundaryMatchResult()
        start_time = time.time()

        # Step 1: Detect language (if not provided)
        if not language and file_paths:
            language = self._detect_language_from_files(file_paths, ir_docs)
        elif not language:
            # Default to Python if no hints
            language = Language.PYTHON

        result.add_decision(f"language_detected_{language.value}")

        # Step 2: Get language-specific detector
        detector = self.detector_registry.get_detector(language)
        if not detector:
            result.add_decision("no_detector_for_language")
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Step 3: Find candidates using language-specific detector
        pattern_start = time.time()
        candidates = self._find_candidates_with_detector(boundary, ir_docs, detector, file_paths)
        result.pattern_time_ms = (time.time() - pattern_start) * 1000
        result.pattern_matches = len(candidates)
        result.total_nodes_scanned = self._count_nodes(ir_docs)

        if not candidates:
            result.total_time_ms = (time.time() - start_time) * 1000
            result.add_decision("no_pattern_matches")
            return result

        # Step 4: Fast path - single high-confidence match
        if len(candidates) == 1 and candidates[0].pattern_score >= self.FAST_PATH_THRESHOLD:
            result.best_match = candidates[0]
            result.confidence = candidates[0].pattern_score
            result.candidates = candidates
            result.total_time_ms = (time.time() - start_time) * 1000
            result.add_decision("fast_path_single_match")
            return result

        # Step 5: Graph-based pre-ranking
        graph_start = time.time()
        candidates = self._rank_by_call_graph_proximity(candidates, boundary, ir_docs)
        result.graph_time_ms = (time.time() - graph_start) * 1000
        result.graph_ranked = len(candidates)

        # High confidence from graph analysis
        if candidates and candidates[0].graph_score >= self.GRAPH_HIGH_CONFIDENCE:
            candidates[0].compute_final_score(
                pattern_weight=self.PATTERN_WEIGHT,
                graph_weight=self.GRAPH_WEIGHT,
                llm_weight=0.0,
            )
            result.best_match = candidates[0]
            result.confidence = candidates[0].final_score
            result.candidates = candidates
            result.total_time_ms = (time.time() - start_time) * 1000
            result.add_decision("graph_high_confidence")
            return result

        # Step 6: LLM ranking (if available)
        if self.llm_client and len(candidates) > 1:
            llm_start = time.time()
            top_candidates = candidates[:5]
            top_candidates = self._llm_rank_candidates(boundary, top_candidates)
            result.llm_time_ms = (time.time() - llm_start) * 1000
            result.llm_ranked = len(top_candidates)

            for i, candidate in enumerate(top_candidates):
                candidates[i] = candidate
        else:
            result.add_decision("llm_not_available")

        # Step 7: Compute final scores
        for candidate in candidates:
            candidate.compute_final_score(
                pattern_weight=self.PATTERN_WEIGHT,
                graph_weight=self.GRAPH_WEIGHT,
                llm_weight=self.LLM_WEIGHT if self.llm_client else 0.0,
            )

        # Sort by final score
        candidates.sort(key=lambda c: c.final_score, reverse=True)
        result.candidates = candidates

        # Step 8: Select best match
        if candidates:
            best_candidate = candidates[0]
            if best_candidate.final_score >= self.FINAL_CONFIDENCE_THRESHOLD:
                result.best_match = best_candidate
                result.confidence = best_candidate.final_score
                result.add_decision("final_score_threshold")

        result.total_time_ms = (time.time() - start_time) * 1000
        return result

    def _detect_language_from_files(self, file_paths: list[str], ir_docs: list[Any]) -> Language:
        """
        Detect language from file paths or IR documents.

        Args:
            file_paths: List of file paths
            ir_docs: IR documents

        Returns:
            Detected Language
        """
        if file_paths:
            # Use first file path for detection
            first_file = file_paths[0]
            code = self._extract_code_from_ir(ir_docs, first_file) if ir_docs else ""
            return self.detector_registry.detect_language(first_file, code)

        return Language.PYTHON  # Default

    def _extract_code_from_ir(self, ir_docs: list[Any], file_path: str) -> str:
        """
        Extract code content from IR documents.

        Placeholder: In production, this would extract code from IR.
        """
        # TODO: Implement IR code extraction
        return ""

    def _find_candidates_with_detector(
        self,
        boundary: BoundarySpec,
        ir_docs: list[Any],
        detector: IBoundaryDetector,
        file_paths: Optional[list[str]] = None,
    ) -> list[BoundaryCandidate]:
        """
        Find boundary candidates using language-specific detector.

        Args:
            boundary: Boundary specification
            ir_docs: IR documents
            detector: Language-specific detector
            file_paths: Optional file paths

        Returns:
            List of BoundaryCandidate
        """
        candidates = []

        # Process each IR document (or file)
        for i, ir_doc in enumerate(ir_docs):
            file_path = file_paths[i] if file_paths and i < len(file_paths) else f"file_{i}.py"

            # Extract code from IR (placeholder)
            code = self._extract_code_from_ir([ir_doc], file_path)

            # Create detection context
            context = BoundaryDetectionContext(
                language=detector.infer_framework(code).__class__.__name__.split(".")[-1]
                if hasattr(detector, "infer_framework")
                else Language.PYTHON,
                file_path=file_path,
                code=code,
                ir_doc=ir_doc,
            )

            # Detect boundaries using language-specific detector
            detected: list[DetectedBoundary] = []

            if boundary.boundary_type == BoundaryType.HTTP_ENDPOINT:
                detected = detector.detect_http_endpoints(context)
            elif boundary.boundary_type == BoundaryType.GRPC_SERVICE:
                detected = detector.detect_grpc_services(context)
            elif boundary.boundary_type == BoundaryType.MESSAGE_QUEUE:
                detected = detector.detect_message_handlers(context)
            elif boundary.boundary_type == BoundaryType.DATABASE_QUERY:
                detected = detector.detect_database_boundaries(context)

            # Convert DetectedBoundary to BoundaryCandidate
            for det in detected:
                candidate = self._convert_to_candidate(det, boundary)
                if candidate:
                    candidates.append(candidate)

        return candidates

    def _convert_to_candidate(
        self, detected: DetectedBoundary, boundary_spec: BoundarySpec
    ) -> Optional[BoundaryCandidate]:
        """
        Convert DetectedBoundary to BoundaryCandidate.

        Applies scoring based on match quality.

        Args:
            detected: Detected boundary
            boundary_spec: Original boundary spec

        Returns:
            BoundaryCandidate or None
        """
        # Check if detected boundary matches spec
        score = detected.pattern_score

        # Adjust score based on match quality
        if boundary_spec.endpoint and detected.endpoint:
            # Exact match
            if boundary_spec.endpoint == detected.endpoint:
                score *= 1.0
            # Partial match (prefix)
            elif boundary_spec.endpoint in detected.endpoint or detected.endpoint in boundary_spec.endpoint:
                score *= 0.9
            else:
                score *= 0.7

        if boundary_spec.http_method and detected.http_method:
            if boundary_spec.http_method.value == detected.http_method:
                score *= 1.0
            else:
                score *= 0.5  # Wrong method is a big penalty

        # Create candidate
        candidate = BoundaryCandidate(
            node_id=f"{detected.file_path}:{detected.line_number}",
            file_path=detected.file_path,
            function_name=detected.function_name,
            line_number=detected.line_number,
            code_snippet=detected.code_snippet,
            pattern_score=score,
            decorator_name=detected.decorator_name,
            http_path=detected.endpoint,
        )

        return candidate

    def _rank_by_call_graph_proximity(
        self,
        candidates: list[BoundaryCandidate],
        boundary: BoundarySpec,
        ir_docs: list[Any],
    ) -> list[BoundaryCandidate]:
        """
        Rank candidates by call graph proximity.

        Placeholder: In production, this would use Rust IR call graph.
        """
        # Assign mock graph scores (higher pattern score → higher graph score)
        for candidate in candidates:
            candidate.graph_score = min(1.0, candidate.pattern_score * 1.2)
            candidate.distance_from_entry = int((1.0 - candidate.graph_score) * 10)

        return sorted(candidates, key=lambda c: c.graph_score, reverse=True)

    def _llm_rank_candidates(
        self, boundary: BoundarySpec, candidates: list[BoundaryCandidate]
    ) -> list[BoundaryCandidate]:
        """
        Rank candidates using LLM.

        Placeholder: In production, this would call LLM API.
        """
        for i, candidate in enumerate(candidates):
            combined = (candidate.pattern_score + candidate.graph_score) / 2
            candidate.llm_score = min(1.0, combined * 1.1 + 0.05)

        return candidates

    def _count_nodes(self, ir_docs: list[Any]) -> int:
        """Count total nodes in IR documents."""
        return len(ir_docs) * 100  # Rough estimate
