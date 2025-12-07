"""
Integration tests for SOTA Boundary Matcher

Tests multi-strategy matching with real-world examples
"""

from __future__ import annotations

import pytest

# Use local fixtures instead of real models
from src.contexts.reasoning_engine.infrastructure.cross_lang import (
    BoundaryCodeMatcher,
    BoundarySpec,
    Confidence,
)


# Fixture provided by conftest.py


class TestBoundaryCodeMatcher:
    """Test SOTA boundary matching"""

    def test_decorator_exact_match(self, sample_ir_documents):
        """Exact decorator match → HIGH confidence"""
        matcher = BoundaryCodeMatcher()

        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/api/users/{user_id}",
            request_schema={},
            response_schema={},
            http_method="GET",
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        assert match is not None
        assert match.symbol_id == "user_handler:get_user"
        assert match.confidence == Confidence.HIGH
        assert "decorator" in match.reason
        assert match.score == 1.0

    def test_decorator_method_mismatch(self, sample_ir_documents):
        """Decorator match but wrong HTTP method → no match"""
        matcher = BoundaryCodeMatcher()

        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/api/users/{user_id}",
            request_schema={},
            response_schema={},
            http_method="POST",  # Wrong method!
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        # Should not match or match with lower confidence
        if match:
            assert match.confidence != Confidence.HIGH

    def test_fuzzy_endpoint_match(self, sample_ir_documents):
        """Fuzzy endpoint matching with path variables"""
        matcher = BoundaryCodeMatcher()

        # Slightly different path variable name
        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/api/users/{id}",  # {id} vs {user_id}
            request_schema={},
            response_schema={},
            http_method="GET",
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        assert match is not None
        # Should still match (path variables normalized)
        assert match.symbol_id == "user_handler:get_user"

    def test_operation_id_match(self, sample_ir_documents):
        """OperationId exact match"""
        # Add operation ID to document
        sample_ir_documents[0].nodes[0].name = "getUser"

        matcher = BoundaryCodeMatcher()

        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/some/path",
            request_schema={},
            response_schema={},
            metadata={"operation_id": "getUser"},
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        assert match is not None
        assert match.symbol_id == "user_handler:get_user"
        assert match.confidence == Confidence.HIGH

    def test_fuzzy_name_match(self, sample_ir_documents):
        """Fuzzy name matching based on endpoint"""
        matcher = BoundaryCodeMatcher()

        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/api/posts",
            request_schema={},
            response_schema={},
            http_method="GET",
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        assert match is not None
        # Should match list_posts by keyword "posts"
        assert "post" in match.symbol_id.lower()

    def test_no_match(self, sample_ir_documents):
        """No matching handler → None"""
        matcher = BoundaryCodeMatcher()

        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/api/nonexistent",
            request_schema={},
            response_schema={},
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        # May return None or low confidence match
        if match:
            assert match.confidence == Confidence.LOW

    def test_batch_matching(self, sample_ir_documents):
        """Batch match multiple boundaries"""
        matcher = BoundaryCodeMatcher()

        boundaries = [
            BoundarySpec(
                boundary_type="rest_api",
                service_name="api",
                endpoint="/api/users/{user_id}",
                request_schema={},
                response_schema={},
                http_method="GET",
            ),
            BoundarySpec(
                boundary_type="rest_api",
                service_name="api",
                endpoint="/api/posts",
                request_schema={},
                response_schema={},
                http_method="GET",
            ),
        ]

        results = matcher.batch_match(boundaries, sample_ir_documents)

        assert len(results) == 2
        assert results["/api/users/{user_id}"] is not None
        assert results["/api/posts"] is not None

    def test_file_path_filtering(self, sample_ir_documents):
        """Should prioritize handler/controller files"""
        matcher = BoundaryCodeMatcher()

        boundary = BoundarySpec(
            boundary_type="rest_api",
            service_name="api",
            endpoint="/api/users/{id}",
            request_schema={},
            response_schema={},
            http_method="GET",
        )

        match = matcher.match_boundary(boundary, sample_ir_documents)

        # Should NOT match helpers.py
        assert match is not None
        assert "handler" in match.file_path.lower()
        assert "helper" not in match.file_path.lower()

    def test_endpoint_normalization(self, sample_ir_documents):
        """Different path variable styles should match"""
        matcher = BoundaryCodeMatcher()

        # Test various path variable formats
        endpoints = [
            "/api/users/{id}",  # OpenAPI
            "/api/users/<int:id>",  # Flask
            "/api/users/:id",  # Express
        ]

        for endpoint in endpoints:
            boundary = BoundarySpec(
                boundary_type="rest_api",
                service_name="api",
                endpoint=endpoint,
                request_schema={},
                response_schema={},
                http_method="GET",
            )

            match = matcher.match_boundary(boundary, sample_ir_documents)

            # All should match the same handler
            assert match is not None
            assert "get_user" in match.symbol_id.lower()


class TestMatchingAccuracy:
    """Test overall matching accuracy"""

    def test_high_confidence_matches(self, sample_ir_documents):
        """High confidence matches should be accurate"""
        matcher = BoundaryCodeMatcher()

        # All these should get HIGH confidence
        high_conf_boundaries = [
            BoundarySpec(
                boundary_type="rest_api",
                service_name="api",
                endpoint="/api/users/{user_id}",
                request_schema={},
                response_schema={},
                http_method="GET",
            ),
            BoundarySpec(
                boundary_type="rest_api",
                service_name="api",
                endpoint="/api/users",
                request_schema={},
                response_schema={},
                http_method="POST",
            ),
        ]

        for boundary in high_conf_boundaries:
            match = matcher.match_boundary(boundary, sample_ir_documents)

            assert match is not None
            assert match.confidence == Confidence.HIGH
            assert match.score >= 0.8
