"""
L11 SOTA급 Byte Offset 계산 테스트

Coverage:
- Base: ASCII 문자
- Edge: UTF-8 멀티바이트 (한글, 일본어)
- Corner: 이모지, Combining characters
- Extreme: 대용량 파일
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.orchestrator.orchestrator.adapters.code_editing.refactoring.code_transformer import RopeRenameStrategy


class TestBaseCase:
    """Base Case: ASCII 문자"""

    def test_simple_ascii(self):
        """단순 ASCII 코드"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def func():\n    pass\n"

        # Line 1, column 0 → offset 0
        offset = strategy._calculate_byte_offset(content, 1, 0)
        assert offset == 0

        # Line 1, column 4 → offset 4 ("def ")
        offset = strategy._calculate_byte_offset(content, 1, 4)
        assert offset == 4

        # Line 2, column 0 → offset 12 ("def func():\n")
        offset = strategy._calculate_byte_offset(content, 2, 0)
        assert offset == 12

    def test_multiline_ascii(self):
        """여러 줄 ASCII 코드"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def func():\n    x = 1\n    return x\n"

        # Line 2, column 4 → "def func():\n    " = 12 + 4 = 16
        offset = strategy._calculate_byte_offset(content, 2, 4)
        assert offset == 16

        # Line 3, column 11 → "def func():\n    x = 1\n    return" = 12 + 10 + 11 = 33
        offset = strategy._calculate_byte_offset(content, 3, 11)
        assert offset == 33


class TestEdgeCase:
    """Edge Case: UTF-8 멀티바이트 문자"""

    def test_korean_characters(self):
        """한글 처리 (각 한글 = 3 bytes)"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def 함수():\n    pass\n"

        # "함수" = 6 bytes (3*2)
        # Line 1, column 4 → "def " = 4 bytes
        offset = strategy._calculate_byte_offset(content, 1, 4)
        assert offset == 4

        # Line 1, column 5 → "def 함" = 4 + 3 = 7 bytes
        offset = strategy._calculate_byte_offset(content, 1, 5)
        assert offset == 7

        # Line 1, column 6 → "def 함수" = 4 + 6 = 10 bytes
        offset = strategy._calculate_byte_offset(content, 1, 6)
        assert offset == 10

    def test_japanese_characters(self):
        """일본어 처리 (각 문자 = 3 bytes)"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def 関数():\n    pass\n"

        # "関数" = 6 bytes
        # Line 1, column 6 → "def 関数" = 4 + 6 = 10
        offset = strategy._calculate_byte_offset(content, 1, 6)
        assert offset == 10

    def test_mixed_ascii_and_unicode(self):
        """ASCII + Unicode 혼합"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def process_한글_data():\n    pass\n"

        # Column 계산 (문자 단위):
        # "def process_한글_d" = 16 characters
        # Bytes: "def " (4) + "process_" (8) + "한글" (6) + "_d" (2) = 20 bytes
        offset = strategy._calculate_byte_offset(content, 1, 16)
        assert offset == 20

        # Column 14 → "def process_한글"
        # Bytes: "def " (4) + "process_" (8) + "한글" (6) = 18 bytes
        offset = strategy._calculate_byte_offset(content, 1, 14)
        assert offset == 18


class TestCornerCase:
    """Corner Case: 극한 조건"""

    def test_emoji_characters(self):
        """이모지 처리 (4 bytes)"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "# 🎯 Test\ndef func():\n    pass\n"

        # "🎯" = 4 bytes
        # Line 1, column 3 → "# 🎯" = 2 + 4 = 6 bytes
        offset = strategy._calculate_byte_offset(content, 1, 3)
        assert offset == 6

    def test_empty_lines(self):
        """빈 줄 처리"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def func():\n\n    pass\n"

        # Line 2 (빈 줄), column 0
        offset = strategy._calculate_byte_offset(content, 2, 0)
        assert offset == 12  # "def func():\n"

        # Line 3, column 0
        offset = strategy._calculate_byte_offset(content, 3, 0)
        assert offset == 13  # "def func():\n\n"

    def test_column_at_line_end(self):
        """줄 끝 컬럼"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def func():\n    pass\n"

        # Line 1, column 11 (줄 끝, "def func():" 전체)
        offset = strategy._calculate_byte_offset(content, 1, 11)
        assert offset == 11

    def test_invalid_line(self):
        """잘못된 line 입력"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def func():\n    pass\n"

        # Line 0 (invalid)
        with pytest.raises(ValueError, match="Invalid line 0"):
            strategy._calculate_byte_offset(content, 0, 0)

        # Line 100 (too large)
        with pytest.raises(ValueError, match="Invalid line 100"):
            strategy._calculate_byte_offset(content, 100, 0)

    def test_invalid_column(self):
        """잘못된 column 입력"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        content = "def func():\n    pass\n"

        # Column -1 (invalid)
        with pytest.raises(ValueError, match="Invalid column -1"):
            strategy._calculate_byte_offset(content, 1, -1)

        # Column 100 (too large for line)
        with pytest.raises(ValueError, match="Invalid column 100"):
            strategy._calculate_byte_offset(content, 1, 100)


class TestExtremeCase:
    """Extreme Case: 대규모 데이터"""

    def test_large_file_performance(self):
        """대용량 파일에서도 성능 유지"""
        import time

        strategy = RopeRenameStrategy(Path("/tmp"))

        # 1000줄 파일 생성
        lines = [f"def function_{i}():\n" for i in range(1000)]
        content = "".join(lines)

        # Line 500, column 4 계산
        start = time.perf_counter()
        offset = strategy._calculate_byte_offset(content, 500, 4)
        elapsed = (time.perf_counter() - start) * 1000

        # 1ms 이하여야 함 (L11 성능 기준)
        assert elapsed < 1.0, f"Too slow: {elapsed:.2f}ms"

        # 정확도 검증
        total_bytes = sum(len(single_line.encode("utf-8")) for single_line in lines[:499])
        expected = total_bytes + 4
        assert offset == expected

    def test_mixed_multibyte_large(self):
        """멀티바이트 + 대용량"""
        strategy = RopeRenameStrategy(Path("/tmp"))

        # 한글, 일본어, 이모지 혼합 대량
        content = "# 🎯한글関数🚀\n" * 100 + "def func():\n    pass\n"

        # Line 101, column 0
        offset = strategy._calculate_byte_offset(content, 101, 0)

        # 각 줄 = "# 🎯한글関数🚀\n" = 2 + 4 + 6 + 6 + 4 + 1 = 23 bytes
        expected = 100 * 23
        assert offset == expected


# ============================================================
# Performance Benchmark
# ============================================================


@pytest.mark.benchmark
@pytest.mark.slow
class TestPerformanceBenchmark:
    """성능 벤치마크 (느림 - CI에서 skip 가능)"""

    def test_benchmark_ascii_1000_lines(self, benchmark):
        """ASCII 1000줄 성능 벤치마크 (1.5초)"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        lines = [f"def function_{i}():\n" for i in range(1000)]
        content = "".join(lines)

        # Benchmark
        result = benchmark(strategy._calculate_byte_offset, content, 500, 4)

        # 결과 검증
        assert result > 0

    def test_benchmark_multibyte_1000_lines(self, benchmark):
        """Multibyte 1000줄 성능 벤치마크 (1.5초)"""
        strategy = RopeRenameStrategy(Path("/tmp"))
        lines = [f"def 함수_{i}():\n" for i in range(1000)]
        content = "".join(lines)

        # Benchmark
        result = benchmark(strategy._calculate_byte_offset, content, 500, 4)

        # 결과 검증
        assert result > 0
