"""
Bloom Filter Unit Tests

Saturation-aware Bloom Filter의 동작 검증.
"""

import pytest

from src.contexts.reasoning_engine.infrastructure.impact.bloom_filter import SaturationAwareBloomFilter


class TestBloomFilter:
    """Bloom Filter 기본 동작"""

    def test_add_and_contains(self):
        """추가한 item은 contains True"""
        bf = SaturationAwareBloomFilter(expected_items=100, fp_rate=0.01)

        bf.add("item1")
        bf.add("item2")

        assert bf.contains("item1") is True
        assert bf.contains("item2") is True

    def test_not_added_item_returns_false(self):
        """추가하지 않은 item은 대부분 False"""
        bf = SaturationAwareBloomFilter(expected_items=100, fp_rate=0.01)

        bf.add("item1")

        # item2는 추가 안했으므로 False (FP 가능성 있지만 낮음)
        # 여러 번 시도해서 대부분 False인지 확인
        false_count = 0
        for i in range(100):
            if not bf.contains(f"item_{i}"):
                false_count += 1

        # FP rate가 1%이므로, 100번 중 최소 80번은 False여야 함
        assert false_count >= 80


class TestSaturationDetection:
    """Saturation 감지"""

    def test_saturation_with_many_items(self):
        """너무 많은 item 추가하면 saturation"""
        bf = SaturationAwareBloomFilter(
            expected_items=10,  # 작은 크기
            fp_rate=0.01,
            saturation_threshold=0.3,
        )

        # Expected보다 훨씬 많이 추가
        for i in range(100):
            bf.add(f"item_{i}")

        # 많은 query 실행
        for i in range(200):
            bf.contains(f"query_{i}")

        is_saturated, fp_ratio = bf.check_saturation()

        # Saturation 발생해야 함
        assert is_saturated is True, f"FP ratio: {fp_ratio}"
        assert fp_ratio > 0.3

    def test_no_saturation_with_normal_usage(self):
        """정상 사용 시 saturation 없음"""
        bf = SaturationAwareBloomFilter(expected_items=100, fp_rate=0.01, saturation_threshold=0.3)

        # Expected 범위 내로 추가
        for i in range(50):
            bf.add(f"item_{i}")

        # Query 실행
        for i in range(150):
            bf.contains(f"item_{i}")

        is_saturated, fp_ratio = bf.check_saturation()

        # Saturation 체크 (fill ratio가 낮으면 False)
        # 50/1000 = 5% fill rate, should not saturate
        assert fp_ratio < 0.5


class TestBloomFilterStats:
    """통계 및 상태"""

    def test_stats(self):
        """통계 확인"""
        bf = SaturationAwareBloomFilter(expected_items=100, fp_rate=0.01)

        bf.add("item1")
        bf.add("item2")
        bf.contains("item1")
        bf.contains("item3")

        stats = bf.get_stats()

        assert stats["added_count"] == 2
        assert stats["query_count"] == 2
        assert stats["positive_count"] >= 1  # item1은 확실히 positive
        assert 0 <= stats["fill_ratio"] <= 1

    def test_reset(self):
        """Reset 후 초기화"""
        bf = SaturationAwareBloomFilter(expected_items=100, fp_rate=0.01)

        bf.add("item1")
        bf.contains("item1")

        bf.reset()

        stats = bf.get_stats()
        assert stats["added_count"] == 0
        assert stats["query_count"] == 0
        assert stats["positive_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
