"""
Evaluation Metrics for Retrieval Quality

Implements standard IR metrics:
- MRR (Mean Reciprocal Rank): Position of first relevant result
- nDCG (Normalized Discounted Cumulative Gain): Ranked retrieval quality
- Precision@k: Fraction of relevant results in top k
- Recall@k: Fraction of relevant results retrieved in top k

Phase: P0-2 Golden Set Construction (Layer 18)
Phase 1 Target: MRR > 0.8
"""

import math
from collections.abc import Sequence


def reciprocal_rank(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
) -> float:
    """
    Calculate Reciprocal Rank (RR) for a single query.

    RR = 1/rank if relevant result found, else 0

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs

    Returns:
        Reciprocal rank (0 if no relevant result found, 1/rank otherwise)

    Example:
        >>> reciprocal_rank(["c1", "c2", "c3"], {"c2"})
        0.5  # First relevant at rank 2, so 1/2 = 0.5
        >>> reciprocal_rank(["c1", "c2", "c3"], {"c4"})
        0.0  # No relevant result found
    """
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(
    results: list[tuple[Sequence[str], set[str]]],
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR) across multiple queries.

    MRR = mean(RR_i) for all queries i

    Args:
        results: List of (retrieved_ids, relevant_ids) pairs

    Returns:
        Mean reciprocal rank [0.0, 1.0]

    Example:
        >>> results = [
        ...     (["c1", "c2"], {"c1"}),  # RR = 1.0
        ...     (["c1", "c2"], {"c2"}),  # RR = 0.5
        ...     (["c1", "c2"], {"c3"}),  # RR = 0.0
        ... ]
        >>> mean_reciprocal_rank(results)
        0.5  # (1.0 + 0.5 + 0.0) / 3 = 0.5
    """
    if not results:
        return 0.0

    rr_sum = sum(reciprocal_rank(retrieved, relevant) for retrieved, relevant in results)
    return rr_sum / len(results)


def dcg_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int | None = None,
) -> float:
    """
    Calculate Discounted Cumulative Gain (DCG) at position k.

    DCG@k = sum(rel_i / log2(i + 1)) for i in [1, k]
    where rel_i = 1 if relevant, 0 otherwise

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs
        k: Position to truncate (None = all results)

    Returns:
        DCG score

    Example:
        >>> dcg_at_k(["c1", "c2", "c3", "c4"], {"c1", "c3"}, k=4)
        1.5  # 1/log2(2) + 1/log2(4) = 1.0 + 0.5 = 1.5
    """
    if k is None:
        k = len(retrieved_ids)

    dcg = 0.0
    for i, chunk_id in enumerate(retrieved_ids[:k], start=1):
        if chunk_id in relevant_ids:
            # Relevance = 1 if relevant, 0 otherwise
            # Discount by log2(i + 1)
            dcg += 1.0 / math.log2(i + 1)

    return dcg


def idcg_at_k(num_relevant: int, k: int | None = None) -> float:
    """
    Calculate Ideal DCG (IDCG) at position k.

    IDCG is the maximum possible DCG when all relevant results are ranked first.

    Args:
        num_relevant: Number of relevant results
        k: Position to truncate (None = num_relevant)

    Returns:
        IDCG score

    Example:
        >>> idcg_at_k(3, k=5)
        2.13  # 1/log2(2) + 1/log2(3) + 1/log2(4) ≈ 2.13
    """
    if k is None:
        k = num_relevant

    # Ideal ranking: all relevant results first
    ideal_k = min(k, num_relevant)

    idcg = 0.0
    for i in range(1, ideal_k + 1):
        idcg += 1.0 / math.log2(i + 1)

    return idcg


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int | None = None,
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain (nDCG) at position k.

    nDCG@k = DCG@k / IDCG@k

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs
        k: Position to truncate (None = all results)

    Returns:
        nDCG score [0.0, 1.0]

    Example:
        >>> ndcg_at_k(["c1", "c2", "c3"], {"c1", "c3"}, k=3)
        0.77  # DCG / IDCG ≈ 0.77
    """
    if not relevant_ids:
        return 0.0

    dcg = dcg_at_k(retrieved_ids, relevant_ids, k)
    idcg = idcg_at_k(len(relevant_ids), k)

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def mean_ndcg_at_k(
    results: list[tuple[Sequence[str], set[str]]],
    k: int | None = None,
) -> float:
    """
    Calculate Mean nDCG across multiple queries.

    Args:
        results: List of (retrieved_ids, relevant_ids) pairs
        k: Position to truncate (None = all results)

    Returns:
        Mean nDCG [0.0, 1.0]

    Example:
        >>> results = [
        ...     (["c1", "c2", "c3"], {"c1"}),
        ...     (["c1", "c2", "c3"], {"c2"}),
        ... ]
        >>> mean_ndcg_at_k(results, k=3)
        0.5
    """
    if not results:
        return 0.0

    ndcg_sum = sum(ndcg_at_k(retrieved, relevant, k) for retrieved, relevant in results)
    return ndcg_sum / len(results)


def precision_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """
    Calculate Precision at k (P@k).

    P@k = (# relevant in top k) / k

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs
        k: Number of top results to consider

    Returns:
        Precision@k [0.0, 1.0]

    Example:
        >>> precision_at_k(["c1", "c2", "c3", "c4"], {"c1", "c3"}, k=4)
        0.5  # 2 relevant out of 4 = 0.5
        >>> precision_at_k(["c1", "c2", "c3", "c4"], {"c1", "c3"}, k=2)
        0.5  # 1 relevant out of 2 = 0.5
    """
    if k <= 0:
        return 0.0

    top_k = retrieved_ids[:k]
    relevant_in_top_k = sum(1 for chunk_id in top_k if chunk_id in relevant_ids)

    return relevant_in_top_k / k


def mean_precision_at_k(
    results: list[tuple[Sequence[str], set[str]]],
    k: int,
) -> float:
    """
    Calculate Mean Precision@k across multiple queries.

    Args:
        results: List of (retrieved_ids, relevant_ids) pairs
        k: Number of top results to consider

    Returns:
        Mean Precision@k [0.0, 1.0]

    Example:
        >>> results = [
        ...     (["c1", "c2"], {"c1"}),
        ...     (["c1", "c2"], {"c2"}),
        ... ]
        >>> mean_precision_at_k(results, k=2)
        0.5  # (0.5 + 0.5) / 2 = 0.5
    """
    if not results:
        return 0.0

    precision_sum = sum(precision_at_k(retrieved, relevant, k) for retrieved, relevant in results)
    return precision_sum / len(results)


def recall_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """
    Calculate Recall at k (R@k).

    R@k = (# relevant in top k) / (# total relevant)

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs
        k: Number of top results to consider

    Returns:
        Recall@k [0.0, 1.0]

    Example:
        >>> recall_at_k(["c1", "c2", "c3", "c4"], {"c1", "c3", "c5"}, k=4)
        0.667  # 2 relevant out of 3 total = 0.667
        >>> recall_at_k(["c1", "c2"], {"c1", "c3", "c5"}, k=2)
        0.333  # 1 relevant out of 3 total = 0.333
    """
    if not relevant_ids:
        return 0.0

    top_k = retrieved_ids[:k]
    relevant_in_top_k = sum(1 for chunk_id in top_k if chunk_id in relevant_ids)

    return relevant_in_top_k / len(relevant_ids)


def mean_recall_at_k(
    results: list[tuple[Sequence[str], set[str]]],
    k: int,
) -> float:
    """
    Calculate Mean Recall@k across multiple queries.

    Args:
        results: List of (retrieved_ids, relevant_ids) pairs
        k: Number of top results to consider

    Returns:
        Mean Recall@k [0.0, 1.0]

    Example:
        >>> results = [
        ...     (["c1", "c2"], {"c1", "c3"}),
        ...     (["c1", "c2"], {"c2", "c4"}),
        ... ]
        >>> mean_recall_at_k(results, k=2)
        0.5  # (0.5 + 0.5) / 2 = 0.5
    """
    if not results:
        return 0.0

    recall_sum = sum(recall_at_k(retrieved, relevant, k) for retrieved, relevant in results)
    return recall_sum / len(results)


def first_relevant_rank(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
) -> int | None:
    """
    Find the rank (1-indexed) of the first relevant result.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs

    Returns:
        Rank of first relevant result (1-indexed), or None if not found

    Example:
        >>> first_relevant_rank(["c1", "c2", "c3"], {"c2"})
        2
        >>> first_relevant_rank(["c1", "c2", "c3"], {"c4"})
        None
    """
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant_ids:
            return rank
    return None


def relevant_in_top_k_counts(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k_values: list[int] | None = None,
) -> dict[int, int]:
    """
    Count relevant results in top k for various k values.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs
        relevant_ids: Set of ground truth relevant chunk IDs
        k_values: List of k values to compute (default: [1, 5, 10, 20])

    Returns:
        Dictionary mapping k -> count of relevant results in top k

    Example:
        >>> relevant_in_top_k_counts(["c1", "c2", "c3", "c4"], {"c1", "c3"}, [1, 2, 5])
        {1: 1, 2: 1, 5: 2}
    """
    if k_values is None:
        k_values = [1, 5, 10, 20]

    counts = {}
    for k in k_values:
        top_k = retrieved_ids[:k]
        count = sum(1 for chunk_id in top_k if chunk_id in relevant_ids)
        counts[k] = count

    return counts


# ============================================================
# Aggregate Metrics
# ============================================================


def compute_aggregate_metrics(
    results: list[tuple[Sequence[str], set[str]]],
) -> dict[str, float]:
    """
    Compute all aggregate metrics for Phase 1 evaluation.

    Args:
        results: List of (retrieved_ids, relevant_ids) pairs

    Returns:
        Dictionary with MRR, nDCG, P@5, R@20

    Example:
        >>> results = [(["c1", "c2"], {"c1"}), (["c1", "c2"], {"c2"})]
        >>> metrics = compute_aggregate_metrics(results)
        >>> metrics["mrr"]
        0.75  # (1.0 + 0.5) / 2
    """
    return {
        "mrr": mean_reciprocal_rank(results),
        "ndcg": mean_ndcg_at_k(results),
        "precision_at_5": mean_precision_at_k(results, k=5),
        "recall_at_20": mean_recall_at_k(results, k=20),
    }


def compute_stratified_metrics(
    results_by_group: dict[str, list[tuple[Sequence[str], set[str]]]],
) -> dict[str, dict[str, float]]:
    """
    Compute metrics stratified by group (intent, difficulty, etc).

    Args:
        results_by_group: Dictionary mapping group name to list of results

    Returns:
        Dictionary mapping group name to aggregate metrics

    Example:
        >>> by_intent = {
        ...     "find_definition": [(["c1"], {"c1"})],
        ...     "understand_flow": [(["c1", "c2"], {"c2"})],
        ... }
        >>> stratified = compute_stratified_metrics(by_intent)
        >>> stratified["find_definition"]["mrr"]
        1.0
    """
    stratified = {}
    for group_name, group_results in results_by_group.items():
        if group_results:
            stratified[group_name] = compute_aggregate_metrics(group_results)

    return stratified
