"""
Multi Index Domain Models Tests

Test Coverage:
- Enums: IndexType
- Data Models: UpsertResult, DeleteResult
- Edge cases: Error handling, defaults
"""

import pytest

from codegraph_engine.multi_index.domain.models import (
    DeleteResult,
    IndexType,
    UpsertResult,
)


class TestIndexType:
    """IndexType enum tests"""

    def test_all_types_defined(self):
        """All index types exist"""
        assert IndexType.LEXICAL.value == "lexical"
        assert IndexType.VECTOR.value == "vector"
        assert IndexType.SYMBOL.value == "symbol"
        assert IndexType.FUZZY.value == "fuzzy"
        assert IndexType.DOMAIN.value == "domain"

    def test_enum_count(self):
        """Expected number of index types"""
        assert len(IndexType) == 5

    def test_is_string_enum(self):
        """Index types are string enums"""
        for idx_type in IndexType:
            assert isinstance(idx_type.value, str)


class TestUpsertResult:
    """UpsertResult model tests"""

    def test_create_success_result(self):
        """Create successful upsert result"""
        result = UpsertResult(
            index_type=IndexType.VECTOR,
            success=True,
            count=100,
        )
        assert result.index_type == IndexType.VECTOR
        assert result.success is True
        assert result.count == 100
        assert result.errors == []  # default

    def test_create_failure_result(self):
        """Create failed upsert result"""
        result = UpsertResult(
            index_type=IndexType.LEXICAL,
            success=False,
            count=0,
            errors=["Connection timeout", "Index unavailable"],
        )
        assert result.success is False
        assert result.count == 0
        assert len(result.errors) == 2

    def test_partial_success(self):
        """Partial success (some errors)"""
        result = UpsertResult(
            index_type=IndexType.SYMBOL,
            success=True,
            count=95,
            errors=["5 documents failed validation"],
        )
        assert result.success is True
        assert result.count == 95
        assert len(result.errors) == 1

    def test_zero_count_success(self):
        """Success with zero count (no-op)"""
        result = UpsertResult(
            index_type=IndexType.FUZZY,
            success=True,
            count=0,
        )
        assert result.success is True
        assert result.count == 0


class TestDeleteResult:
    """DeleteResult model tests"""

    def test_create_delete_result(self):
        """Create delete result"""
        result = DeleteResult(
            index_type=IndexType.VECTOR,
            deleted_count=50,
        )
        assert result.index_type == IndexType.VECTOR
        assert result.deleted_count == 50

    def test_zero_deleted(self):
        """Delete with zero count"""
        result = DeleteResult(
            index_type=IndexType.LEXICAL,
            deleted_count=0,
        )
        assert result.deleted_count == 0

    def test_large_delete(self):
        """Large delete operation"""
        result = DeleteResult(
            index_type=IndexType.SYMBOL,
            deleted_count=1000000,
        )
        assert result.deleted_count == 1000000


class TestEdgeCases:
    """Edge case tests"""

    def test_all_index_types_in_results(self):
        """All index types can be used in results"""
        for idx_type in IndexType:
            upsert = UpsertResult(index_type=idx_type, success=True, count=1)
            delete = DeleteResult(index_type=idx_type, deleted_count=1)
            assert upsert.index_type == idx_type
            assert delete.index_type == idx_type

    def test_empty_errors_list(self):
        """Empty errors list is default"""
        result = UpsertResult(
            index_type=IndexType.DOMAIN,
            success=True,
            count=10,
        )
        assert result.errors == []
        assert len(result.errors) == 0

    def test_unicode_in_errors(self):
        """Unicode in error messages"""
        result = UpsertResult(
            index_type=IndexType.VECTOR,
            success=False,
            count=0,
            errors=["인덱스 오류 발생 🔴", "연결 실패"],
        )
        assert "인덱스" in result.errors[0]

    def test_negative_count_allowed(self):
        """Negative count (edge case, may indicate bug)"""
        # Model doesn't validate, just stores
        result = UpsertResult(
            index_type=IndexType.LEXICAL,
            success=False,
            count=-1,
        )
        assert result.count == -1

    def test_result_mutability(self):
        """Results are mutable dataclasses"""
        result = UpsertResult(
            index_type=IndexType.VECTOR,
            success=True,
            count=10,
        )
        result.count = 20
        assert result.count == 20
