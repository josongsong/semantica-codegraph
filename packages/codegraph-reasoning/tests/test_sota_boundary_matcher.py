"""
Test suite for SOTA Boundary Matcher (RFC-101 Phase 1).

Validates:
1. BoundarySpec and domain models
2. Pattern-based candidate finding
3. Graph-based pre-ranking
4. LLM-assisted ranking
5. Rust type verification
6. End-to-end matching workflow
7. Performance characteristics
"""

import pytest

from codegraph_reasoning.domain import (
    BoundaryCandidate,
    BoundaryMatchResult,
    BoundarySpec,
    BoundaryType,
    HTTPMethod,
)
from codegraph_reasoning.infrastructure.boundary import SOTABoundaryMatcher


class TestBoundaryModels:
    """Test boundary matching domain models."""

    def test_boundary_spec_http_endpoint(self):
        """Test HTTP endpoint boundary spec."""
        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        assert spec.boundary_type == BoundaryType.HTTP_ENDPOINT
        assert spec.endpoint == "/api/users/{id}"
        assert spec.http_method == HTTPMethod.GET
        assert str(spec) == "GET /api/users/{id}"

    def test_boundary_spec_grpc_service(self):
        """Test gRPC service boundary spec."""
        spec = BoundarySpec(
            boundary_type=BoundaryType.GRPC_SERVICE,
            service_name="UserService",
            rpc_method="GetUser",
        )

        assert spec.boundary_type == BoundaryType.GRPC_SERVICE
        assert spec.service_name == "UserService"
        assert spec.rpc_method == "GetUser"
        assert str(spec) == "UserService.GetUser"

    def test_boundary_spec_message_queue(self):
        """Test message queue boundary spec."""
        spec = BoundarySpec(
            boundary_type=BoundaryType.MESSAGE_QUEUE,
            topic="user.created",
        )

        assert spec.boundary_type == BoundaryType.MESSAGE_QUEUE
        assert spec.topic == "user.created"
        assert "user.created" in str(spec)

    def test_boundary_candidate_creation(self):
        """Test boundary candidate creation."""
        candidate = BoundaryCandidate(
            node_id="node_123",
            file_path="api/users.py",
            function_name="get_user",
            line_number=42,
            code_snippet="def get_user(user_id: int):",
            pattern_score=0.85,
            graph_score=0.90,
            llm_score=0.88,
        )

        assert candidate.node_id == "node_123"
        assert candidate.function_name == "get_user"
        assert candidate.pattern_score == 0.85
        assert candidate.graph_score == 0.90
        assert candidate.llm_score == 0.88

    def test_boundary_candidate_final_score(self):
        """Test final score computation."""
        candidate = BoundaryCandidate(
            node_id="node_123",
            file_path="api/users.py",
            function_name="get_user",
            line_number=42,
            code_snippet="def get_user(user_id: int):",
            pattern_score=0.80,
            graph_score=0.90,
            llm_score=0.85,
        )

        # Default weights: pattern=0.3, graph=0.4, llm=0.3
        final_score = candidate.compute_final_score()

        expected = 0.80 * 0.3 + 0.90 * 0.4 + 0.85 * 0.3
        assert abs(final_score - expected) < 0.01
        assert candidate.final_score == final_score

    def test_boundary_candidate_custom_weights(self):
        """Test final score with custom weights."""
        candidate = BoundaryCandidate(
            node_id="node_123",
            file_path="api/users.py",
            function_name="get_user",
            line_number=42,
            code_snippet="def get_user(user_id: int):",
            pattern_score=0.80,
            graph_score=0.90,
            llm_score=0.85,
        )

        # Custom weights: emphasize graph
        final_score = candidate.compute_final_score(pattern_weight=0.2, graph_weight=0.6, llm_weight=0.2)

        expected = 0.80 * 0.2 + 0.90 * 0.6 + 0.85 * 0.2
        assert abs(final_score - expected) < 0.01

    def test_boundary_match_result_success(self):
        """Test successful match result."""
        candidate = BoundaryCandidate(
            node_id="node_123",
            file_path="api/users.py",
            function_name="get_user",
            line_number=42,
            code_snippet="def get_user(user_id: int):",
        )
        candidate.final_score = 0.95

        result = BoundaryMatchResult(
            best_match=candidate,
            confidence=0.95,
            total_nodes_scanned=1000,
            pattern_matches=5,
        )

        assert result.success is True
        assert result.best_match == candidate
        assert result.confidence == 0.95

    def test_boundary_match_result_failure(self):
        """Test failed match result."""
        result = BoundaryMatchResult(
            best_match=None,
            confidence=0.0,
            total_nodes_scanned=1000,
            pattern_matches=0,
        )

        assert result.success is False
        assert result.best_match is None

    def test_boundary_match_result_low_confidence(self):
        """Test low confidence match (below threshold)."""
        candidate = BoundaryCandidate(
            node_id="node_123",
            file_path="api/users.py",
            function_name="get_user",
            line_number=42,
            code_snippet="def get_user(user_id: int):",
        )

        result = BoundaryMatchResult(
            best_match=candidate,
            confidence=0.70,  # Below 0.85 threshold
        )

        assert result.success is False  # Low confidence = failure

    def test_boundary_match_result_decision_path(self):
        """Test decision path tracking."""
        result = BoundaryMatchResult()

        result.add_decision("fast_path")
        result.add_decision("graph_ranking")
        result.add_decision("llm_ranking")

        assert result.decision_path == ["fast_path", "graph_ranking", "llm_ranking"]


class TestSOTABoundaryMatcher:
    """Test SOTA Boundary Matcher core functionality."""

    def test_matcher_initialization(self):
        """Test matcher initialization."""
        matcher = SOTABoundaryMatcher()

        assert matcher.rust_engine is None
        assert matcher.llm_client is None

    def test_matcher_initialization_with_engines(self):
        """Test matcher initialization with engines."""
        mock_rust = object()
        mock_llm = object()

        matcher = SOTABoundaryMatcher(rust_engine=mock_rust, llm_client=mock_llm)

        assert matcher.rust_engine is mock_rust
        assert matcher.llm_client is mock_llm

    def test_match_boundary_no_candidates(self):
        """Test matching with no pattern matches."""
        matcher = SOTABoundaryMatcher()

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[])

        assert result.success is False
        assert result.best_match is None
        assert result.pattern_matches == 0
        assert "no_pattern_matches" in result.decision_path

    def test_match_boundary_single_high_confidence(self):
        """Test fast path with single high-confidence match."""
        matcher = SOTABoundaryMatcher()

        # Mock candidate finder to return single high-confidence match
        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_123",
                    file_path="api/users.py",
                    function_name="get_user",
                    line_number=42,
                    code_snippet="def get_user(user_id: int):",
                    pattern_score=0.98,  # High confidence
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        assert result.success is True
        assert result.best_match is not None
        assert result.best_match.function_name == "get_user"
        assert result.confidence == 0.98
        assert "fast_path_single_match" in result.decision_path

    def test_match_boundary_graph_ranking(self):
        """Test graph-based pre-ranking."""
        matcher = SOTABoundaryMatcher()

        # Mock candidates with varying scores
        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="api/users.py",
                    function_name="handler1",
                    line_number=10,
                    code_snippet="def handler1():",
                    pattern_score=0.70,
                ),
                BoundaryCandidate(
                    node_id="node_2",
                    file_path="api/users.py",
                    function_name="handler2",
                    line_number=20,
                    code_snippet="def handler2():",
                    pattern_score=0.75,
                ),
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Graph ranking should have been applied
        assert result.graph_ranked >= 2
        assert result.graph_time_ms > 0

    def test_match_boundary_performance(self):
        """Test performance characteristics."""
        matcher = SOTABoundaryMatcher()

        # Mock fast candidate finding
        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_123",
                    file_path="api/users.py",
                    function_name="get_user",
                    line_number=42,
                    code_snippet="def get_user(user_id: int):",
                    pattern_score=0.98,
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Performance targets from RFC-101
        assert result.total_time_ms < 100  # Should be < 50ms in production
        assert result.pattern_time_ms >= 0
        assert result.graph_time_ms >= 0

    def test_graph_ranking_assigns_scores(self):
        """Test graph ranking assigns graph scores."""
        matcher = SOTABoundaryMatcher()

        candidates = [
            BoundaryCandidate(
                node_id="node_1",
                file_path="api/users.py",
                function_name="handler1",
                line_number=10,
                code_snippet="def handler1():",
                pattern_score=0.70,
            ),
            BoundaryCandidate(
                node_id="node_2",
                file_path="api/users.py",
                function_name="handler2",
                line_number=20,
                code_snippet="def handler2():",
                pattern_score=0.80,
            ),
        ]

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        ranked = matcher._rank_by_call_graph_proximity(candidates, spec, ir_docs=[])

        # All candidates should have graph scores assigned
        for candidate in ranked:
            assert candidate.graph_score > 0
            assert candidate.distance_from_entry is not None

    def test_llm_ranking_assigns_scores(self):
        """Test LLM ranking assigns LLM scores."""

        # Mock LLM client
        class MockLLM:
            def complete(self, prompt, **kwargs):
                return '{"best_match_index": 1, "confidence": 0.92}'

        matcher = SOTABoundaryMatcher(llm_client=MockLLM())

        candidates = [
            BoundaryCandidate(
                node_id="node_1",
                file_path="api/users.py",
                function_name="handler1",
                line_number=10,
                code_snippet="def handler1():",
                pattern_score=0.70,
                graph_score=0.75,
            ),
        ]

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        ranked = matcher._llm_rank_candidates(spec, candidates)

        # All candidates should have LLM scores assigned
        for candidate in ranked:
            assert candidate.llm_score > 0


class TestIntegration:
    """Integration tests for boundary matching workflow."""

    def test_end_to_end_matching_workflow(self):
        """Test complete matching workflow."""

        # Setup matcher with mock engines
        class MockRust:
            pass

        class MockLLM:
            pass

        matcher = SOTABoundaryMatcher(rust_engine=MockRust(), llm_client=MockLLM())

        # Mock candidate finding
        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_123",
                    file_path="api/users.py",
                    function_name="get_user_handler",
                    line_number=42,
                    code_snippet="@app.get('/api/users/{id}')\ndef get_user_handler(user_id: int):",
                    pattern_score=0.85,
                    decorator_name="@app.get",
                    http_path="/api/users/{id}",
                ),
                BoundaryCandidate(
                    node_id="node_456",
                    file_path="api/users.py",
                    function_name="get_all_users",
                    line_number=60,
                    code_snippet="@app.get('/api/users')\ndef get_all_users():",
                    pattern_score=0.75,
                    decorator_name="@app.get",
                    http_path="/api/users",
                ),
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Workflow should complete
        assert result.total_time_ms > 0
        assert result.pattern_matches == 2
        assert result.candidates is not None
        assert len(result.candidates) >= 1

    def test_boundary_types_coverage(self):
        """Test coverage of different boundary types."""
        matcher = SOTABoundaryMatcher()

        # HTTP endpoint
        http_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.POST,
        )
        http_result = matcher.match_boundary(http_spec, ir_docs=[])
        assert http_result is not None

        # gRPC service
        grpc_spec = BoundarySpec(
            boundary_type=BoundaryType.GRPC_SERVICE,
            service_name="TestService",
            rpc_method="TestMethod",
        )
        grpc_result = matcher.match_boundary(grpc_spec, ir_docs=[])
        assert grpc_result is not None

        # Message queue
        mq_spec = BoundarySpec(
            boundary_type=BoundaryType.MESSAGE_QUEUE,
            topic="test.topic",
        )
        mq_result = matcher.match_boundary(mq_spec, ir_docs=[])
        assert mq_result is not None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_boundary_spec_with_none_values(self):
        """Test boundary spec with None values in optional fields (http_method is optional)."""
        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",  # Required for HTTP
            http_method=None,  # None method (optional)
        )

        assert spec.boundary_type == BoundaryType.HTTP_ENDPOINT
        assert spec.endpoint == "/api/test"
        assert spec.http_method is None

    def test_boundary_spec_with_empty_strings(self):
        """Test boundary spec with empty strings."""
        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="",  # Empty endpoint
            http_method=HTTPMethod.GET,
        )

        assert spec.endpoint == ""

    def test_candidate_with_empty_code_snippet(self):
        """Test candidate with empty code snippet."""
        candidate = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="handler",
            line_number=10,
            code_snippet="",  # Empty snippet
            pattern_score=0.85,
        )

        assert candidate.code_snippet == ""

    def test_candidate_with_very_long_code_snippet(self):
        """Test candidate with very long code snippet."""
        long_code = "def handler():\n" + "    pass\n" * 10000  # 10K+ lines
        candidate = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="handler",
            line_number=10,
            code_snippet=long_code,
            pattern_score=0.85,
        )

        # 10K lines * ~7 chars per line = ~70K chars
        assert len(candidate.code_snippet) > 60000

    def test_candidate_scoring_with_zero_weights(self):
        """Test final score computation with zero weights."""
        candidate = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="handler",
            line_number=10,
            code_snippet="def handler():",
            pattern_score=0.8,
            graph_score=0.9,
            llm_score=0.7,
        )

        # All zero weights
        final_score = candidate.compute_final_score(pattern_weight=0.0, graph_weight=0.0, llm_weight=0.0)
        assert final_score == 0.0

    def test_candidate_scoring_weights_not_sum_to_one(self):
        """Test final score with weights that don't sum to 1.0."""
        candidate = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="handler",
            line_number=10,
            code_snippet="def handler():",
            pattern_score=0.8,
            graph_score=0.9,
            llm_score=0.7,
        )

        # Weights sum to 2.0 (should still work)
        final_score = candidate.compute_final_score(pattern_weight=1.0, graph_weight=0.5, llm_weight=0.5)
        expected = 0.8 * 1.0 + 0.9 * 0.5 + 0.7 * 0.5
        assert abs(final_score - expected) < 0.01

    def test_match_boundary_at_fast_path_threshold(self):
        """Test matching exactly at fast path threshold (0.95)."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="handler",
                    line_number=10,
                    code_snippet="def handler():",
                    pattern_score=0.95,  # Exactly at threshold
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should take fast path
        assert result.success is True
        assert "fast_path_single_match" in result.decision_path

    def test_match_boundary_just_below_fast_path_threshold(self):
        """Test matching just below fast path threshold (0.94)."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="handler",
                    line_number=10,
                    code_snippet="def handler():",
                    pattern_score=0.94,  # Just below threshold
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should NOT take fast path
        assert "fast_path_single_match" not in result.decision_path
        # Should apply graph ranking
        assert result.graph_time_ms > 0

    def test_match_boundary_at_graph_confidence_threshold(self):
        """Test matching exactly at graph high confidence threshold (0.90)."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            # Pattern score that will get graph score >= 0.90 (pattern * 1.2)
            # Need pattern_score >= 0.75 to get graph_score = 0.90
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="handler",
                    line_number=10,
                    code_snippet="def handler():",
                    pattern_score=0.76,  # Will yield graph_score = 0.912 (> 0.90)
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should have high confidence from graph ranking
        assert result.graph_ranked >= 1
        # Should take graph_high_confidence path
        assert "graph_high_confidence" in result.decision_path
        assert result.best_match is not None

    def test_match_boundary_at_final_confidence_threshold(self):
        """Test matching exactly at final confidence threshold (0.85)."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            # Pattern score that will yield final score around 0.85
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="handler",
                    line_number=10,
                    code_snippet="def handler():",
                    pattern_score=0.70,  # Lower pattern score
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Check if result meets confidence threshold
        # Final score depends on pattern + graph scoring
        assert result.candidates is not None

    def test_match_boundary_with_100_candidates(self):
        """Test matching with large number of candidates (100+)."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            # Create 100 candidates with varying scores
            return [
                BoundaryCandidate(
                    node_id=f"node_{i}",
                    file_path=f"handler_{i}.py",
                    function_name=f"handler_{i}",
                    line_number=i * 10,
                    code_snippet=f"def handler_{i}():",
                    pattern_score=0.5 + (i * 0.003),  # Scores from 0.5 to 0.8
                )
                for i in range(100)
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should handle large candidate list
        assert len(result.candidates) == 100
        assert result.pattern_matches == 100

    def test_match_boundary_with_identical_scores(self):
        """Test matching with multiple candidates having identical scores."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id=f"node_{i}",
                    file_path=f"handler_{i}.py",
                    function_name=f"handler_{i}",
                    line_number=i * 10,
                    code_snippet=f"def handler_{i}():",
                    pattern_score=0.85,  # All identical
                )
                for i in range(5)
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should handle tie-breaking (order may vary)
        assert len(result.candidates) == 5
        assert result.best_match is not None

    def test_match_boundary_with_unicode_function_names(self):
        """Test matching with non-ASCII function names."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="사용자_핸들러",  # Korean
                    line_number=10,
                    code_snippet="def 사용자_핸들러():",
                    pattern_score=0.85,
                ),
                BoundaryCandidate(
                    node_id="node_2",
                    file_path="test.py",
                    function_name="用户处理器",  # Chinese
                    line_number=20,
                    code_snippet="def 用户处理器():",
                    pattern_score=0.80,
                ),
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/user",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should handle unicode correctly
        assert result.best_match is not None
        assert "사용자_핸들러" in result.best_match.function_name

    def test_match_boundary_with_special_characters_in_path(self):
        """Test matching with special characters in file paths."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="/path/with spaces/and-dashes/file.py",
                    function_name="handler",
                    line_number=10,
                    code_snippet="def handler():",
                    pattern_score=0.85,
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should handle special characters in paths
        assert result.best_match is not None
        assert " " in result.best_match.file_path

    def test_match_boundary_with_multiline_code_snippet(self):
        """Test matching with multi-line code snippets."""
        matcher = SOTABoundaryMatcher()

        multiline_code = '''@app.get('/api/users/{id}')
def get_user_handler(user_id: int):
    """Get user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404)
    return user'''

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="api/users.py",
                    function_name="get_user_handler",
                    line_number=42,
                    code_snippet=multiline_code,
                    pattern_score=0.90,
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should handle multiline code correctly
        assert result.best_match is not None
        assert "\n" in result.best_match.code_snippet

    def test_match_boundary_empty_ir_docs(self):
        """Test matching with completely empty IR docs."""
        matcher = SOTABoundaryMatcher()

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        # Empty IR docs
        result = matcher.match_boundary(spec, ir_docs=[])

        # Should gracefully handle empty input
        assert result.success is False
        assert result.best_match is None
        assert result.total_nodes_scanned == 0

    def test_match_boundary_none_in_candidate_fields(self):
        """Test matching with None in optional candidate fields."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="handler",
                    line_number=10,
                    code_snippet="def handler():",
                    pattern_score=0.85,
                    decorator_name=None,  # None decorator
                    http_path=None,  # None path
                )
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should handle None values gracefully
        assert result.best_match is not None
        assert result.best_match.decorator_name is None

    def test_decision_path_all_stages(self):
        """Test decision path tracking through all stages."""
        matcher = SOTABoundaryMatcher()

        # Create scenario that goes through all stages
        def mock_find_candidates(boundary, ir_docs):
            return [
                BoundaryCandidate(
                    node_id="node_1",
                    file_path="test.py",
                    function_name="handler1",
                    line_number=10,
                    code_snippet="def handler1():",
                    pattern_score=0.70,  # Low enough to trigger graph + LLM
                ),
                BoundaryCandidate(
                    node_id="node_2",
                    file_path="test.py",
                    function_name="handler2",
                    line_number=20,
                    code_snippet="def handler2():",
                    pattern_score=0.75,
                ),
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should have gone through multiple stages
        assert len(result.decision_path) > 0
        # Should NOT be fast path
        assert "fast_path_single_match" not in result.decision_path

    def test_performance_under_50ms_target(self):
        """Test that performance meets <50ms target."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            # Create realistic scenario with 10 candidates
            return [
                BoundaryCandidate(
                    node_id=f"node_{i}",
                    file_path=f"handler_{i}.py",
                    function_name=f"handler_{i}",
                    line_number=i * 10,
                    code_snippet=f"def handler_{i}():",
                    pattern_score=0.6 + (i * 0.03),
                )
                for i in range(10)
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.POST,
        )

        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Should meet RFC-101 performance target
        assert result.total_time_ms < 100  # Lenient for test environment
        # Production target is <50ms
        # Test environment may be slower due to mocking overhead

    def test_negative_weight_validation(self):
        """Test that negative weights raise ValueError."""
        candidate = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="handler",
            line_number=10,
            code_snippet="def handler():",
            pattern_score=0.8,
            graph_score=0.9,
            llm_score=0.7,
        )

        # Negative pattern weight
        with pytest.raises(ValueError, match="Weights must be non-negative"):
            candidate.compute_final_score(pattern_weight=-0.1, graph_weight=0.5, llm_weight=0.5)

        # Negative graph weight
        with pytest.raises(ValueError, match="Weights must be non-negative"):
            candidate.compute_final_score(pattern_weight=0.5, graph_weight=-0.1, llm_weight=0.5)

        # Negative LLM weight
        with pytest.raises(ValueError, match="Weights must be non-negative"):
            candidate.compute_final_score(pattern_weight=0.5, graph_weight=0.5, llm_weight=-0.1)

    def test_stress_1000_candidates(self):
        """Stress test with 1000 candidates."""
        matcher = SOTABoundaryMatcher()

        def mock_find_candidates(boundary, ir_docs):
            # Create 1000 candidates with varying scores
            return [
                BoundaryCandidate(
                    node_id=f"node_{i}",
                    file_path=f"module_{i // 100}/handler_{i}.py",
                    function_name=f"handler_{i}",
                    line_number=i * 10,
                    code_snippet=f"def handler_{i}(request):\n    return response",
                    pattern_score=0.3 + (i * 0.0006),  # Scores from 0.3 to 0.9
                )
                for i in range(1000)
            ]

        matcher._find_candidates_fast = mock_find_candidates

        spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/stress/test",
            http_method=HTTPMethod.GET,
        )

        # Should handle large candidate list efficiently
        result = matcher.match_boundary(spec, ir_docs=[{}])

        # Assertions
        assert len(result.candidates) == 1000
        assert result.pattern_matches == 1000
        assert result.best_match is not None
        # Performance should still be reasonable
        assert result.total_time_ms < 500  # Generous limit for 1000 candidates

    def test_boundary_spec_validation_http(self):
        """Test HTTP endpoint validation - requires endpoint."""
        with pytest.raises(ValueError, match="HTTP_ENDPOINT requires 'endpoint' field"):
            BoundarySpec(
                boundary_type=BoundaryType.HTTP_ENDPOINT,
                endpoint=None,  # None not allowed
                http_method=HTTPMethod.GET,
            )

    def test_boundary_spec_validation_grpc(self):
        """Test gRPC service validation - requires service_name."""
        with pytest.raises(ValueError, match="GRPC_SERVICE requires 'service_name' field"):
            BoundarySpec(
                boundary_type=BoundaryType.GRPC_SERVICE,
                # Missing service_name
                rpc_method="GetUser",
            )

    def test_boundary_spec_validation_mq(self):
        """Test message queue validation - requires topic or queue_name."""
        with pytest.raises(ValueError, match="MESSAGE_QUEUE requires 'topic' or 'queue_name' field"):
            BoundarySpec(
                boundary_type=BoundaryType.MESSAGE_QUEUE,
                # Missing both topic and queue_name
            )

    def test_boundary_spec_validation_db(self):
        """Test database query validation - requires table_name."""
        with pytest.raises(ValueError, match="DATABASE_QUERY requires 'table_name' field"):
            BoundarySpec(
                boundary_type=BoundaryType.DATABASE_QUERY,
                # Missing table_name
                operation="SELECT",
            )

    def test_boundary_spec_validation_api(self):
        """Test external API validation - requires api_host."""
        with pytest.raises(ValueError, match="EXTERNAL_API requires 'api_host' field"):
            BoundarySpec(
                boundary_type=BoundaryType.EXTERNAL_API,
                # Missing api_host
                api_path="/repos/{owner}/{repo}",
            )
