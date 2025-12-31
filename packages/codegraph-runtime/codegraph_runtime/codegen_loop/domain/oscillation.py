"""
Oscillation Detector

순수 함수 기반 진동 감지
"""

from .patch import Patch


class OscillationDetector:
    """
    진동 감지기 (순수 로직)

    패치가 반복적으로 같은 패턴을 보이는지 감지
    """

    def __init__(self, window_size: int = 3, similarity_threshold: float = 0.9):
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        if not (0.0 <= similarity_threshold <= 1.0):
            raise ValueError("similarity_threshold must be between 0 and 1")
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold

    def is_oscillating(self, patches: list[Patch]) -> bool:
        """
        진동 여부 판정

        최근 N개 패치가 유사한 패턴 반복 시 True
        """
        if len(patches) < self.window_size * 2:
            return False

        recent = patches[-self.window_size :]
        prev = patches[-self.window_size * 2 : -self.window_size]

        similarity = self._calculate_similarity(recent, prev)
        return similarity >= self.similarity_threshold

    def _calculate_similarity(self, seq1: list[Patch], seq2: list[Patch]) -> float:
        """
        두 패치 시퀀스의 유사도 계산

        간단한 diff 기반 (추후 semantic 비교로 개선 가능)
        """
        if len(seq1) != len(seq2):
            return 0.0

        similarities = []
        for p1, p2 in zip(seq1, seq2, strict=False):
            sim = self._patch_similarity(p1, p2)
            similarities.append(sim)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _patch_similarity(self, p1: Patch, p2: Patch) -> float:
        """
        두 패치의 유사도

        TODO: 추후 AST 기반으로 개선
        """
        # Multi-file 지원: 파일 경로 집합이 다르면 다름
        if p1.modified_files != p2.modified_files:
            return 0.0

        # 각 파일별 유사도 평균
        similarities = []
        for file_path in p1.modified_files:
            f1 = p1.get_file_change(file_path)
            f2 = p2.get_file_change(file_path)

            if f1 and f2:
                lines1 = set(f1.diff_lines)
                lines2 = set(f2.diff_lines)

                if not lines1 and not lines2:
                    similarities.append(1.0)
                else:
                    intersection = len(lines1 & lines2)
                    union = len(lines1 | lines2)
                    similarities.append(intersection / union if union > 0 else 0.0)

        return sum(similarities) / len(similarities) if similarities else 0.0
