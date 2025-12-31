"""
Beam Ranker

후보를 랭킹하고 top-k를 선택하는 로직.
"""

import hashlib

from .beam_models import BeamCandidate, BeamConfig


class BeamRanker:
    """Beam Search 후보 랭킹"""

    def __init__(self, config: BeamConfig):
        self.config = config
        self._seen_hashes: set[str] = set()

    def rank_and_prune(self, candidates: list[BeamCandidate]) -> list[BeamCandidate]:
        """
        후보를 랭킹하고 top-k만 유지

        Args:
            candidates: 후보 리스트

        Returns:
            상위 k개 후보
        """
        if not candidates:
            return []

        # 1. 중복 제거
        unique_candidates = self._deduplicate(candidates)

        # 2. 다양성 페널티 계산
        candidates_with_penalty = [(c, self._calculate_diversity_penalty(c)) for c in unique_candidates]

        # 3. 최종 점수로 정렬
        scored_candidates = [(c, c.calculate_final_score(penalty)) for c, penalty in candidates_with_penalty]
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # 4. Top-k 선택
        top_k = [c for c, _ in scored_candidates[: self.config.beam_width]]

        return top_k

    def _deduplicate(self, candidates: list[BeamCandidate]) -> list[BeamCandidate]:
        """
        중복 후보 제거

        Args:
            candidates: 후보 리스트

        Returns:
            중복 제거된 후보 리스트
        """
        unique = []
        seen = set()

        for candidate in candidates:
            # 코드 diff로 해시 생성
            content_hash = self._hash_candidate(candidate)

            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(candidate)

        return unique

    def _calculate_diversity_penalty(self, candidate: BeamCandidate) -> float:
        """
        다양성 페널티 계산

        Args:
            candidate: 후보

        Returns:
            페널티 값 (0.0 ~ 1.0)
        """
        content_hash = self._hash_candidate(candidate)

        # 이미 본 적 있는 유사한 후보면 페널티 부여
        if content_hash in self._seen_hashes:
            return self.config.diversity_penalty

        self._seen_hashes.add(content_hash)
        return 0.0

    def _hash_candidate(self, candidate: BeamCandidate) -> str:
        """
        후보의 해시 생성

        Args:
            candidate: 후보

        Returns:
            해시 문자열
        """
        # code_diff가 비어있으면 candidate_id를 포함
        # (비어있는 code_diff끼리는 서로 다른 것으로 간주)
        if not candidate.code_diff or candidate.code_diff.strip() == "":
            content = f"empty_{candidate.candidate_id}"
        else:
            content = candidate.code_diff[:100]

        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def reset_seen_hashes(self) -> None:
        """본 해시 리셋 (새로운 검색 시작 시)"""
        self._seen_hashes.clear()
