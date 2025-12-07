"""
Saturation-Aware Bloom Filter

Bloom Filter with saturation detection.
FP ratio > 30% → fallback to normal mode.
"""

import math

import mmh3
from bitarray import bitarray


class SaturationAwareBloomFilter:
    """
    Saturation detection 포함 Bloom Filter.

    사용 사례:
    - 변경 후보군을 빠르게 필터링
    - FP는 허용 (Builder가 처리)
    - Saturation 감지 → Filter 재구축 또는 비활성화
    """

    def __init__(self, expected_items: int = 10000, fp_rate: float = 0.01, saturation_threshold: float = 0.3):
        """
        Args:
            expected_items: 예상 항목 수
            fp_rate: False Positive 비율
            saturation_threshold: Saturation 임계값 (FP ratio)
        """
        self.expected_items = expected_items
        self.fp_rate = fp_rate
        self.saturation_threshold = saturation_threshold

        # Optimal parameters
        self.size = self._optimal_size(expected_items, fp_rate)
        self.hash_count = self._optimal_hash_count(self.size, expected_items)

        # Bit array
        self.bits = bitarray(self.size)
        self.bits.setall(0)

        # Statistics
        self.added_count = 0
        self.query_count = 0
        self.positive_count = 0
        self.is_saturated = False

    def add(self, item: str):
        """Item 추가"""
        for i in range(self.hash_count):
            index = mmh3.hash(item, i) % self.size
            self.bits[index] = 1

        self.added_count += 1

    def contains(self, item: str) -> bool:
        """
        Item 포함 여부 (FP 가능).

        Returns:
            True: 포함될 가능성 있음 (FP 가능)
            False: 확실히 포함 안됨
        """
        self.query_count += 1

        result = all(self.bits[mmh3.hash(item, i) % self.size] for i in range(self.hash_count))

        if result:
            self.positive_count += 1

        return result

    def check_saturation(self) -> tuple[bool, float]:
        """
        Saturation 감지.

        Returns:
            (is_saturated, fp_ratio)
        """
        if self.query_count < 100:
            # 충분한 query가 쌓이지 않음
            return False, 0.0

        # FP ratio 계산
        fp_ratio = self.positive_count / self.query_count

        # Saturation 판정
        self.is_saturated = fp_ratio > self.saturation_threshold

        return self.is_saturated, fp_ratio

    def reset(self):
        """Filter 초기화"""
        self.bits.setall(0)
        self.added_count = 0
        self.query_count = 0
        self.positive_count = 0
        self.is_saturated = False

    def rebuild(self, items: list[str]):
        """
        Filter 재구축.

        Saturation 발생 시 크기를 늘려서 재구축.
        """
        # 크기를 2배로 증가
        new_expected = self.expected_items * 2

        self.__init__(expected_items=new_expected, fp_rate=self.fp_rate, saturation_threshold=self.saturation_threshold)

        # Items 재추가
        for item in items:
            self.add(item)

    def get_stats(self) -> dict:
        """통계 반환"""
        is_saturated, fp_ratio = self.check_saturation()

        return {
            "size": self.size,
            "hash_count": self.hash_count,
            "added_count": self.added_count,
            "query_count": self.query_count,
            "positive_count": self.positive_count,
            "fp_ratio": fp_ratio,
            "is_saturated": is_saturated,
            "fill_ratio": self.bits.count() / self.size if self.size > 0 else 0,
        }

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        """
        최적 비트 배열 크기.

        Formula: m = -(n * ln(p)) / (ln(2)^2)
        """
        m = -(n * math.log(p)) / (math.log(2) ** 2)
        return max(1, int(m))

    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        """
        최적 해시 함수 개수.

        Formula: k = (m / n) * ln(2)
        """
        if n == 0:
            return 1

        k = (m / n) * math.log(2)
        return max(1, int(k))


# =============================================================================
# Usage Example
# =============================================================================


def example_usage():
    """Bloom Filter 사용 예시"""
    # 1. Filter 생성
    bf = SaturationAwareBloomFilter(expected_items=1000, fp_rate=0.01, saturation_threshold=0.3)

    # 2. Items 추가
    changed_symbols = {"func_a", "func_b", "func_c"}
    for symbol in changed_symbols:
        bf.add(symbol)

    # 3. 빠른 필터링
    candidates = ["func_a", "func_d", "func_e", "func_b"]
    [c for c in candidates if bf.contains(c)]

    # likely_changed: ["func_a", "func_b"]
    # FP 가능: "func_d" 또는 "func_e"도 포함될 수 있음

    # 4. Saturation 체크
    is_saturated, fp_ratio = bf.check_saturation()
    if is_saturated:
        print(f"Filter saturated (FP ratio: {fp_ratio:.2%})")
        # Fallback to normal mode or rebuild

    # 5. Stats 확인
    stats = bf.get_stats()
    print(f"Stats: {stats}")


if __name__ == "__main__":
    example_usage()
