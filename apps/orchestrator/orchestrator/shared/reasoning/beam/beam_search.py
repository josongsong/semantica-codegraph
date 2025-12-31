"""
Beam Search Engine

병렬 후보 탐색 및 top-k 유지 전략.
"""

import logging
import time
import uuid

from apps.orchestrator.orchestrator.ports.reasoning_protocols import EvaluateFunction, ExpandFunction

from .beam_models import BeamCandidate, BeamConfig, BeamSearchResult
from .beam_ranker import BeamRanker

logger = logging.getLogger(__name__)


class BeamSearchEngine:
    """Beam Search 실행 엔진"""

    def __init__(self, config: BeamConfig | None = None):
        self.config = config or BeamConfig()
        self.ranker = BeamRanker(self.config)

    async def search(
        self,
        initial_prompt: str,
        expand_fn: ExpandFunction,
        evaluate_fn: EvaluateFunction,
    ) -> BeamSearchResult:
        """
        Beam Search 실행

        Args:
            initial_prompt: 초기 프롬프트
            expand_fn: 후보 확장 함수 (LLM 호출)
            evaluate_fn: 후보 평가 함수 (실행 + 테스트)

        Returns:
            검색 결과
        """
        start_time = time.time()

        # 초기화
        self.ranker.reset_seen_hashes()
        all_candidates: list[BeamCandidate] = []
        beam_sizes: list[int] = []

        # 1. 초기 후보 생성
        initial_candidate = BeamCandidate(
            candidate_id=str(uuid.uuid4()),
            depth=0,
            reasoning=initial_prompt,
        )

        current_beam = [initial_candidate]
        max_depth_reached = 0

        # 2. Beam Search Loop
        for depth in range(self.config.max_depth):
            logger.info(f"Beam Search depth {depth}, beam size: {len(current_beam)}")

            # 2.1 각 후보를 확장
            next_candidates: list[BeamCandidate] = []

            for candidate in current_beam:
                try:
                    # 확장 (LLM으로 n개 후보 생성)
                    expanded = expand_fn(candidate)

                    # 깊이 설정
                    for exp in expanded:
                        exp.depth = depth + 1
                        exp.parent_id = candidate.candidate_id

                    next_candidates.extend(expanded)

                except Exception as e:
                    logger.warning(f"Failed to expand candidate: {e}")
                    continue

            if not next_candidates:
                logger.warning(f"No candidates at depth {depth}")
                break

            # 2.2 평가
            for candidate in next_candidates:
                try:
                    score = evaluate_fn(candidate)
                    candidate.score = score
                    candidate.quality_score = score
                except Exception as e:
                    logger.warning(f"Failed to evaluate candidate: {e}")
                    candidate.score = 0.0

            # 2.3 랭킹 및 Pruning
            current_beam = self.ranker.rank_and_prune(next_candidates)

            # 통계
            all_candidates.extend(next_candidates)
            beam_sizes.append(len(current_beam))
            max_depth_reached = depth + 1

            if not current_beam:
                logger.warning(f"Empty beam at depth {depth}")
                break

        # 3. 최종 결과
        search_time = time.time() - start_time

        # Best candidate 선택
        valid_candidates = [c for c in all_candidates if c.is_valid()]
        best_candidate = None
        if valid_candidates:
            best_candidate = max(valid_candidates, key=lambda c: c.score)

        result = BeamSearchResult(
            best_candidate=best_candidate,
            all_candidates=all_candidates,
            total_candidates=len(all_candidates),
            valid_candidates=len(valid_candidates),
            search_time=search_time,
            avg_beam_size=sum(beam_sizes) / len(beam_sizes) if beam_sizes else 0,
            max_depth_reached=max_depth_reached,
        )

        logger.info(
            f"Beam Search completed: {len(valid_candidates)}/{len(all_candidates)} valid, "
            f"best_score={best_candidate.score if best_candidate else 0.0:.2f}"
        )

        return result

    def search_sync(
        self,
        initial_prompt: str,
        expand_fn: ExpandFunction,
        evaluate_fn: EvaluateFunction,
    ) -> BeamSearchResult:
        """
        동기 버전 (테스트용)

        Args:
            initial_prompt: 초기 프롬프트
            expand_fn: 후보 확장 함수
            evaluate_fn: 후보 평가 함수

        Returns:
            검색 결과
        """
        import asyncio

        # SOTA: Handle running event loop gracefully
        try:
            asyncio.get_running_loop()
            # Already in async context - cannot use asyncio.run()
            raise RuntimeError("search_sync() cannot be called from async context. Use await engine.search() instead.")
        except RuntimeError:
            pass  # No running loop - continue

        return asyncio.run(self.search(initial_prompt, expand_fn, evaluate_fn))
