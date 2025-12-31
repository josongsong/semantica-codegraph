"""
Retrieval Evaluator

Executes golden set evaluation and computes metrics.

Workflow:
1. Load golden set queries
2. Execute each query through retriever
3. Compute metrics (MRR, nDCG, P@5, R@20)
4. Aggregate results and save to database

Phase 1 Target: MRR > 0.8
"""

import json
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from codegraph_shared.common.observability import get_logger
from codegraph_search.infrastructure.evaluation.golden_set_service import GoldenSetService
from codegraph_search.infrastructure.evaluation.metrics import (
    compute_all_metrics,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from codegraph_search.infrastructure.evaluation.models import (
    EvaluationResult,
    QueryDifficulty,
    QueryIntent,
)
from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class RetrieverEvaluator:
    """
    Evaluator for retriever performance using golden set.

    Measures:
    - MRR (Mean Reciprocal Rank) - Phase 1 target: > 0.8
    - nDCG@20 (Normalized Discounted Cumulative Gain)
    - P@5 (Precision at 5)
    - R@20 (Recall at 20)

    Stratified metrics by:
    - Query intent (find_definition, find_references, etc.)
    - Query difficulty (easy, medium, hard, expert)
    """

    def __init__(
        self,
        golden_set_service: GoldenSetService,
        postgres: PostgresStore,
        retriever_service=None,  # Optional: injected retriever
    ):
        """
        Initialize evaluator.

        Args:
            golden_set_service: Golden set query service
            postgres: PostgreSQL storage for evaluation results
            retriever_service: Optional retriever service (for end-to-end eval)
        """
        self.golden_set_service = golden_set_service
        self.postgres = postgres
        self.retriever_service = retriever_service

    async def evaluate(
        self,
        eval_name: str,
        retriever_config: dict[str, Any],
        intent: QueryIntent | None = None,
        difficulty: QueryDifficulty | None = None,
        repo_id: str | None = None,
        max_queries: int | None = None,
        baseline_eval_id: UUID | None = None,
    ) -> EvaluationResult:
        """
        Run full evaluation on golden set.

        Args:
            eval_name: Name for this evaluation (e.g., "weekly_eval_2025_11_26")
            retriever_config: Retriever configuration being tested
            intent: Optional intent filter
            difficulty: Optional difficulty filter
            repo_id: Optional repo filter
            max_queries: Maximum queries to evaluate (None = all)
            baseline_eval_id: Optional previous eval for comparison

        Returns:
            EvaluationResult with metrics

        Raises:
            ValueError: If retriever_service not set
        """
        logger.info(f"Starting evaluation: {eval_name}")
        start_time = datetime.now()

        # Load golden set queries
        queries = await self.golden_set_service.list_queries(
            intent=intent,
            difficulty=difficulty,
            repo_id=repo_id,
            limit=max_queries or 10000,
        )

        if not queries:
            logger.warning("No golden set queries found")
            raise ValueError("No golden set queries available for evaluation")

        logger.info(f"Loaded {len(queries)} golden set queries")

        # Execute queries and compute metrics
        per_query_results = []
        queries_by_intent = defaultdict(list)
        queries_by_difficulty = defaultdict(list)

        for i, query in enumerate(queries):
            if (i + 1) % 10 == 0:
                logger.info(f"Evaluating query {i + 1}/{len(queries)}")

            # Execute query through retriever
            retrieved_chunk_ids = await self._execute_query(query.query, repo_id)

            # Compute all metrics for this query
            metrics = compute_all_metrics(
                retrieved=retrieved_chunk_ids,
                relevant=query.relevant_chunk_ids,
                k_values=[5, 10, 20],
            )

            # Store per-query result
            query_result = {
                "query_id": str(query.query_id),
                "query": query.query,
                "intent": query.intent.value,
                "difficulty": query.difficulty.value,
                "retrieved_count": len(retrieved_chunk_ids),
                "relevant_count": len(query.relevant_chunk_ids),
                **metrics,
            }
            per_query_results.append(query_result)

            # Group for stratified metrics
            queries_by_intent[query.intent.value].append(
                {
                    "retrieved": retrieved_chunk_ids,
                    "relevant": query.relevant_chunk_ids,
                }
            )
            queries_by_difficulty[query.difficulty.value].append(
                {
                    "retrieved": retrieved_chunk_ids,
                    "relevant": query.relevant_chunk_ids,
                }
            )

            # Update usage count
            await self.golden_set_service.increment_usage(query.query_id)

        # Compute aggregate metrics
        mrr = mean_reciprocal_rank(
            [
                {"retrieved": r["retrieved"], "relevant": r["relevant"]}
                for intent_results in queries_by_intent.values()
                for r in intent_results
            ]
        )

        # Aggregate nDCG, P@5, R@20
        all_ndcg_20 = [r["ndcg@20"] for r in per_query_results]
        all_p5 = [r["precision@5"] for r in per_query_results]
        all_r20 = [r["recall@20"] for r in per_query_results]

        avg_ndcg = sum(all_ndcg_20) / len(all_ndcg_20) if all_ndcg_20 else 0.0
        avg_p5 = sum(all_p5) / len(all_p5) if all_p5 else 0.0
        avg_r20 = sum(all_r20) / len(all_r20) if all_r20 else 0.0

        # Compute stratified metrics by intent
        metrics_by_intent = {}
        for intent_name, intent_queries in queries_by_intent.items():
            metrics_by_intent[intent_name] = {
                "mrr": mean_reciprocal_rank(intent_queries),
                "ndcg@20": sum(ndcg_at_k(q["retrieved"], q["relevant"], 20) for q in intent_queries)
                / len(intent_queries),
                "precision@5": sum(precision_at_k(q["retrieved"], q["relevant"], 5) for q in intent_queries)
                / len(intent_queries),
                "recall@20": sum(recall_at_k(q["retrieved"], q["relevant"], 20) for q in intent_queries)
                / len(intent_queries),
                "count": len(intent_queries),
            }

        # Compute stratified metrics by difficulty
        metrics_by_difficulty = {}
        for difficulty_name, difficulty_queries in queries_by_difficulty.items():
            metrics_by_difficulty[difficulty_name] = {
                "mrr": mean_reciprocal_rank(difficulty_queries),
                "ndcg@20": sum(ndcg_at_k(q["retrieved"], q["relevant"], 20) for q in difficulty_queries)
                / len(difficulty_queries),
                "precision@5": sum(precision_at_k(q["retrieved"], q["relevant"], 5) for q in difficulty_queries)
                / len(difficulty_queries),
                "recall@20": sum(recall_at_k(q["retrieved"], q["relevant"], 20) for q in difficulty_queries)
                / len(difficulty_queries),
                "count": len(difficulty_queries),
            }

        # Query intent distribution
        query_intents = {intent: len(queries) for intent, queries in queries_by_intent.items()}

        # Generate improvement summary if baseline provided
        improvement_summary = None
        if baseline_eval_id:
            improvement_summary = await self._generate_improvement_summary(
                baseline_eval_id, mrr, avg_ndcg, avg_p5, avg_r20
            )

        # Create evaluation result
        eval_result = EvaluationResult(
            eval_name=eval_name,
            eval_timestamp=start_time,
            retriever_config=retriever_config,
            query_set_size=len(queries),
            query_intents=query_intents,
            mrr=mrr,
            ndcg=avg_ndcg,
            precision_at_5=avg_p5,
            recall_at_20=avg_r20,
            metrics_by_intent=metrics_by_intent,
            metrics_by_difficulty=metrics_by_difficulty,
            detailed_results=per_query_results,
            baseline_eval_id=baseline_eval_id,
            improvement_summary=improvement_summary,
        )

        # Save to database
        await self._save_evaluation_result(eval_result)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"Evaluation complete: {eval_name}\n"
            f"  Queries: {len(queries)}\n"
            f"  MRR: {mrr:.4f} {'✅' if mrr > 0.8 else '⚠️ (target: > 0.8)'}\n"
            f"  nDCG@20: {avg_ndcg:.4f}\n"
            f"  P@5: {avg_p5:.4f}\n"
            f"  R@20: {avg_r20:.4f}\n"
            f"  Duration: {duration:.1f}s"
        )

        return eval_result

    async def _execute_query(self, query: str, repo_id: str | None) -> list[str]:
        """
        Execute query through retriever.

        Args:
            query: Natural language query
            repo_id: Optional repository ID

        Returns:
            List of retrieved chunk IDs (in rank order)

        Note:
            If retriever_service is not set, returns empty list.
            This allows testing metrics computation without full retriever.
        """
        if not self.retriever_service:
            logger.warning("No retriever_service set, returning empty results")
            return []

        # Execute retrieval
        try:
            results = await self.retriever_service.search(
                query=query,
                repo_id=repo_id,
                top_k=20,  # Retrieve top 20 for R@20
            )

            # Extract chunk IDs in rank order
            return [result.chunk_id for result in results]

        except Exception as e:
            logger.error(f"Retrieval failed for query '{query}': {e}")
            return []

    async def _generate_improvement_summary(
        self,
        baseline_eval_id: UUID,
        current_mrr: float,
        current_ndcg: float,
        current_p5: float,
        current_r20: float,
    ) -> str:
        """Generate improvement summary compared to baseline."""
        # Load baseline evaluation
        async with self.postgres.pool.acquire() as conn:
            baseline_row = await conn.fetchrow(
                "SELECT mrr, ndcg, precision_at_5, recall_at_20 FROM evaluation_results WHERE eval_id = $1",
                str(baseline_eval_id),
            )

        if not baseline_row:
            return "Baseline evaluation not found"

        baseline_mrr = baseline_row["mrr"]
        baseline_ndcg = baseline_row["ndcg"]
        baseline_p5 = baseline_row["precision_at_5"]
        baseline_r20 = baseline_row["recall_at_20"]

        mrr_change = ((current_mrr - baseline_mrr) / baseline_mrr * 100) if baseline_mrr > 0 else 0
        ndcg_change = ((current_ndcg - baseline_ndcg) / baseline_ndcg * 100) if baseline_ndcg > 0 else 0
        p5_change = ((current_p5 - baseline_p5) / baseline_p5 * 100) if baseline_p5 > 0 else 0
        r20_change = ((current_r20 - baseline_r20) / baseline_r20 * 100) if baseline_r20 > 0 else 0

        return (
            f"vs Baseline:\n"
            f"  MRR: {mrr_change:+.2f}%\n"
            f"  nDCG@20: {ndcg_change:+.2f}%\n"
            f"  P@5: {p5_change:+.2f}%\n"
            f"  R@20: {r20_change:+.2f}%"
        )

    async def _save_evaluation_result(self, result: EvaluationResult):
        """Save evaluation result to PostgreSQL."""
        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO evaluation_results (
                    eval_id, eval_name, eval_timestamp, retriever_config,
                    query_set_size, query_intents,
                    mrr, ndcg, precision_at_5, recall_at_20,
                    metrics_by_intent, metrics_by_difficulty,
                    detailed_results,
                    baseline_eval_id, improvement_summary,
                    is_production, notes
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
                )
                """,
                str(result.eval_id),
                result.eval_name,
                result.eval_timestamp,
                json.dumps(result.retriever_config),
                result.query_set_size,
                json.dumps(result.query_intents) if result.query_intents else None,
                result.mrr,
                result.ndcg,
                result.precision_at_5,
                result.recall_at_20,
                json.dumps(result.metrics_by_intent) if result.metrics_by_intent else None,
                json.dumps(result.metrics_by_difficulty) if result.metrics_by_difficulty else None,
                json.dumps(result.detailed_results) if result.detailed_results else None,
                str(result.baseline_eval_id) if result.baseline_eval_id else None,
                result.improvement_summary,
                result.is_production,
                result.notes,
            )

        logger.info(f"Saved evaluation result: {result.eval_id}")
