"""
AlphaCode Sampler

대량 샘플링 + 클러스터링 + 필터링 파이프라인.
"""

import logging
import time
import uuid
from collections.abc import Callable

from .alphacode_models import AlphaCodeConfig, AlphaCodeResult, SampleCandidate
from .clustering import ClusteringEngine
from .filtering import FilterEngine

logger = logging.getLogger(__name__)


class AlphaCodeSampler:
    """AlphaCode 스타일 샘플러"""

    def __init__(self, config: AlphaCodeConfig | None = None):
        self.config = config or AlphaCodeConfig()
        self.clustering = ClusteringEngine(self.config)
        self.filtering = FilterEngine(self.config)

    async def sample(
        self,
        prompt: str,
        generate_fn: Callable[[str, int], list[SampleCandidate]],
        evaluate_fn: Callable[[SampleCandidate], None],
        parallel_workers: int | None = None,  # RFC-017 Phase 1: 병렬 평가
        embedding_fn: Callable[[SampleCandidate], list[float]] | None = None,  # RFC-017 Phase 3: Semantic embedding
    ) -> AlphaCodeResult:
        """
        AlphaCode 샘플링 실행

        Args:
            prompt: 프롬프트
            generate_fn: 샘플 생성 함수 (LLM)
            evaluate_fn: 샘플 평가 함수 (실행 + 테스트)

        Returns:
            샘플링 결과
        """
        total_start = time.time()

        # 1. 대량 샘플링
        logger.info(f"Generating {self.config.num_samples} samples...")
        sample_start = time.time()

        samples = generate_fn(prompt, self.config.num_samples)

        # 샘플 ID 부여
        for i, sample in enumerate(samples):
            if not sample.sample_id:
                sample.sample_id = f"sample_{i}_{uuid.uuid4().hex[:8]}"

        sampling_time = time.time() - sample_start
        logger.info(f"Generated {len(samples)} samples in {sampling_time:.2f}s")

        # 2. 평가 (RFC-017 Phase 1: 병렬 또는 순차)
        logger.info(f"Evaluating samples (parallel_workers={parallel_workers})...")
        eval_start = time.time()

        compiled = 0

        if parallel_workers and parallel_workers > 1:
            # 병렬 평가 (RFC-017 Phase 1)
            import concurrent.futures

            def _evaluate_one(sample: SampleCandidate) -> bool:
                """
                단일 샘플 평가 (thread-safe)

                Returns:
                    compile_success
                """
                try:
                    evaluate_fn(sample)
                    return sample.compile_success
                except Exception as e:
                    logger.warning(f"Failed to evaluate sample {sample.sample_id}: {e}")
                    sample.compile_success = False
                    return False

            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as executor:
                # 모든 샘플을 병렬로 평가
                futures = [executor.submit(_evaluate_one, s) for s in samples]

                # 결과 수집 (timeout 없음 - 모든 샘플이 평가될 때까지 대기)
                for future in concurrent.futures.as_completed(futures):
                    try:
                        if future.result():
                            compiled += 1
                    except Exception as e:
                        logger.error(f"Parallel evaluation error: {e}")

            logger.info(f"Parallel evaluation complete with {parallel_workers} workers")
        else:
            # 순차 평가 (기존 동작 - backward compatible)
            for sample in samples:
                try:
                    evaluate_fn(sample)
                    if sample.compile_success:
                        compiled += 1
                except Exception as e:
                    logger.warning(f"Failed to evaluate sample: {e}")
                    sample.compile_success = False

        evaluation_time = time.time() - eval_start
        compile_rate = compiled / len(samples) if samples else 0
        logger.info(f"Evaluated {len(samples)} samples in {evaluation_time:.2f}s, compile_rate={compile_rate:.2%}")

        # 3. 중복 제거
        samples = self.filtering.deduplicate(samples)

        # 4. 클러스터링 (RFC-017 Phase 3: custom embedding_fn)
        logger.info("Clustering samples...")
        cluster_start = time.time()

        clusters = self.clustering.cluster(samples, embedding_fn=embedding_fn)

        clustering_time = time.time() - cluster_start
        logger.info(f"Created {len(clusters)} clusters in {clustering_time:.2f}s")

        # 5. 필터링
        logger.info("Filtering samples...")
        final_samples = self.filtering.filter(samples)

        # 6. 최고 후보 선택
        best_candidate = None
        if final_samples:
            best_candidate = max(final_samples, key=lambda s: s.calculate_final_score())

        # 7. 결과 생성
        valid_samples = [s for s in samples if s.is_valid()]
        avg_test_pass_rate = sum(s.test_pass_rate for s in valid_samples) / len(valid_samples) if valid_samples else 0.0

        result = AlphaCodeResult(
            best_candidate=best_candidate,
            all_samples=samples,
            clusters=clusters,
            total_samples=len(samples),
            valid_samples=len(valid_samples),
            compile_rate=compile_rate,
            avg_test_pass_rate=avg_test_pass_rate,
            sampling_time=sampling_time,
            clustering_time=clustering_time,
            evaluation_time=evaluation_time,
        )

        total_time = time.time() - total_start
        logger.info(
            f"AlphaCode sampling completed in {total_time:.2f}s: "
            f"{len(valid_samples)}/{len(samples)} valid, "
            f"best_score={best_candidate.calculate_final_score() if best_candidate else 0.0:.2f}"
        )

        return result

    def sample_sync(
        self,
        prompt: str,
        generate_fn: Callable[[str, int], list[SampleCandidate]],
        evaluate_fn: Callable[[SampleCandidate], None],
    ) -> AlphaCodeResult:
        """
        동기 버전 (테스트용)

        Args:
            prompt: 프롬프트
            generate_fn: 샘플 생성 함수
            evaluate_fn: 샘플 평가 함수

        Returns:
            샘플링 결과
        """
        import asyncio

        return asyncio.run(self.sample(prompt, generate_fn, evaluate_fn))
