"""
Oscillation Detector Tests (ACTUAL Implementation)

SOTA-Level: Base + Edge + Extreme Cases
Production-Grade: 실제 API 기반
"""

import pytest

from codegraph_runtime.codegen_loop.domain.oscillation import OscillationDetector
from codegraph_runtime.codegen_loop.domain.patch import FileChange, Patch, PatchStatus


class TestOscillationDetector:
    """OscillationDetector 테스트 (실제 구현 기반)"""

    def test_empty_patches_no_oscillation(self):
        """Base: 패치 없으면 진동 아님"""
        detector = OscillationDetector(window_size=3, similarity_threshold=0.9)

        assert not detector.is_oscillating([])

    def test_less_than_2window_no_oscillation(self):
        """Base: window_size * 2 미만이면 진동 판정 불가"""
        detector = OscillationDetector(window_size=3, similarity_threshold=0.9)

        # 5개 < 6 (3*2)
        patches = [
            Patch(
                id=f"p{i}",
                iteration=i,
                files=[FileChange("a.py", "", "", [])],
                status=PatchStatus.GENERATED,
            )
            for i in range(5)
        ]

        assert not detector.is_oscillating(patches)

    def test_repeated_patches_oscillating(self):
        """Base: 같은 패치 반복 → 진동"""
        detector = OscillationDetector(window_size=2, similarity_threshold=0.9)

        # A-A-A-A 패턴
        patches = [
            Patch(
                id=f"p{i}",
                iteration=i,
                files=[FileChange("a.py", "old", "new", ["-old", "+new"])],
                status=PatchStatus.GENERATED,
            )
            for i in range(4)
        ]

        # recent 2 = [p2, p3], prev 2 = [p0, p1]
        # 모두 동일하므로 similarity = 1.0 >= 0.9
        assert detector.is_oscillating(patches)

    def test_different_patches_no_oscillation(self):
        """Base: 모두 다른 패치 → 진동 아님"""
        detector = OscillationDetector(window_size=2, similarity_threshold=0.9)

        patches = [
            Patch(
                id=f"p{i}",
                iteration=i,
                files=[FileChange("a.py", "", "", [f"-variant{i}"])],
                status=PatchStatus.GENERATED,
            )
            for i in range(4)
        ]

        # 모두 다르므로 similarity = 0.0 < 0.9
        assert not detector.is_oscillating(patches)

    def test_patch_similarity_same_content(self):
        """Base: 동일 내용 → similarity = 1.0"""
        detector = OscillationDetector()

        p1 = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "old", "new", ["-old", "+new"])],
            status=PatchStatus.GENERATED,
        )

        p2 = Patch(
            id="p2",
            iteration=2,
            files=[FileChange("a.py", "old", "new", ["-old", "+new"])],
            status=PatchStatus.GENERATED,
        )

        sim = detector._patch_similarity(p1, p2)

        assert sim == 1.0

    def test_patch_similarity_different_files(self):
        """Base: 다른 파일 → similarity = 0.0"""
        detector = OscillationDetector()

        p1 = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        p2 = Patch(
            id="p2",
            iteration=2,
            files=[FileChange("b.py", "", "", [])],  # Different file
            status=PatchStatus.GENERATED,
        )

        sim = detector._patch_similarity(p1, p2)

        assert sim == 0.0

    def test_patch_similarity_partial_overlap(self):
        """Base: 부분 겹침 → 0 < similarity < 1"""
        detector = OscillationDetector()

        p1 = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "", "", ["-line1", "-line2", "+new1"])],
            status=PatchStatus.GENERATED,
        )

        p2 = Patch(
            id="p2",
            iteration=2,
            files=[FileChange("a.py", "", "", ["-line1", "+new2"])],  # Partial overlap
            status=PatchStatus.GENERATED,
        )

        sim = detector._patch_similarity(p1, p2)

        # Jaccard: {-line1, -line2, +new1} vs {-line1, +new2}
        # intersection = 1, union = 4
        assert 0.0 < sim < 1.0
        assert sim == pytest.approx(1 / 4, abs=0.01)


class TestOscillationEdgeCases:
    """Edge Cases"""

    def test_invalid_window_size_raises(self):
        """Edge: window_size < 2 에러"""
        with pytest.raises(ValueError, match="window_size must be >= 2"):
            OscillationDetector(window_size=1, similarity_threshold=0.9)

    def test_invalid_similarity_threshold_raises(self):
        """Edge: threshold 범위 밖 에러"""
        with pytest.raises(ValueError, match="similarity_threshold must be between 0 and 1"):
            OscillationDetector(window_size=3, similarity_threshold=1.5)

        with pytest.raises(ValueError, match="similarity_threshold must be between 0 and 1"):
            OscillationDetector(window_size=3, similarity_threshold=-0.1)

    def test_threshold_0_always_oscillating(self):
        """Edge: threshold=0이면 항상 진동"""
        detector = OscillationDetector(window_size=2, similarity_threshold=0.0)

        # 완전히 다른 패치들
        patches = [
            Patch(
                id=f"p{i}",
                iteration=i,
                files=[FileChange("a.py", "", "", [f"-unique{i}"])],
                status=PatchStatus.GENERATED,
            )
            for i in range(4)
        ]

        # similarity = 0.0 >= 0.0
        assert detector.is_oscillating(patches)

    def test_threshold_1_requires_perfect_match(self):
        """Edge: threshold=1.0이면 완전 일치만 진동"""
        detector = OscillationDetector(window_size=2, similarity_threshold=1.0)

        # 거의 같지만 조금 다름
        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "", "", ["-a", "-b"])],
                status=PatchStatus.GENERATED,
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "", "", ["-a", "-b"])],
                status=PatchStatus.GENERATED,
            ),
            Patch(
                id="p3",
                iteration=3,
                files=[FileChange("a.py", "", "", ["-a", "-b", "-c"])],  # Slightly different
                status=PatchStatus.GENERATED,
            ),
            Patch(
                id="p4",
                iteration=4,
                files=[FileChange("a.py", "", "", ["-a", "-b"])],
                status=PatchStatus.GENERATED,
            ),
        ]

        # recent=[p3,p4] vs prev=[p1,p2]
        # p3 != p1, so average similarity < 1.0
        assert not detector.is_oscillating(patches)

    def test_multi_file_patches(self):
        """Edge: Multi-file 패치"""
        detector = OscillationDetector(window_size=2, similarity_threshold=0.9)

        patches = [
            Patch(
                id=f"p{i}",
                iteration=i,
                files=[
                    FileChange("a.py", "", "", ["-a"]),
                    FileChange("b.py", "", "", ["-b"]),
                ],
                status=PatchStatus.GENERATED,
            )
            for i in range(4)
        ]

        # 모두 동일한 multi-file 패치 → 진동
        assert detector.is_oscillating(patches)


class TestOscillationExtremeCases:
    """Extreme Cases"""

    def test_large_window_size(self):
        """Extreme: window_size=10"""
        detector = OscillationDetector(window_size=10, similarity_threshold=0.9)

        # 20개 필요
        patches = [
            Patch(
                id=f"p{i}",
                iteration=i,
                files=[FileChange("a.py", "", "", ["-same"])],
                status=PatchStatus.GENERATED,
            )
            for i in range(20)
        ]

        assert detector.is_oscillating(patches)

    def test_alternating_pattern(self):
        """Integration: A-B-A-B 교대 패턴"""
        detector = OscillationDetector(window_size=2, similarity_threshold=0.5)

        patches = [
            Patch(
                id="p1",
                iteration=1,
                files=[FileChange("a.py", "", "", ["-A"])],
                status=PatchStatus.GENERATED,
            ),
            Patch(
                id="p2",
                iteration=2,
                files=[FileChange("a.py", "", "", ["-B"])],
                status=PatchStatus.GENERATED,
            ),
            Patch(
                id="p3",
                iteration=3,
                files=[FileChange("a.py", "", "", ["-A"])],  # Repeat A
                status=PatchStatus.GENERATED,
            ),
            Patch(
                id="p4",
                iteration=4,
                files=[FileChange("a.py", "", "", ["-B"])],  # Repeat B
                status=PatchStatus.GENERATED,
            ),
        ]

        # recent=[A,B] vs prev=[A,B] → similarity = 1.0
        assert detector.is_oscillating(patches)
