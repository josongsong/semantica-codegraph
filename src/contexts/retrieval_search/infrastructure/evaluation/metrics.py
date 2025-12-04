"""
Evaluation Metrics

Implementations of standard information retrieval metrics:
- MRR (Mean Reciprocal Rank)
- nDCG (Normalized Discounted Cumulative Gain)
- Precision@K
- Recall@K

Phase 1 Target: MRR > 0.8
"""

import math
from typing import Any


def reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    """
    Calculate Reciprocal Rank (RR).

    RR = 1 / rank_of_first_relevant_item

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)

    Returns:
        Reciprocal rank (0.0 if no relevant item found)

    Example:
        retrieved = ["chunk1", "chunk2", "chunk3", "chunk4"]
        relevant = ["chunk3", "chunk5"]
        rr = 1 / 3 = 0.333  (first relevant is at position 3)
    """
    relevant_set = set(relevant)

    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant_set:
            return 1.0 / rank

    return 0.0


def mean_reciprocal_rank(queries_results: list[dict[str, Any]]) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR) across multiple queries.

    MRR = (1/|Q|) * Σ RR(q)

    Args:
        queries_results: List of dicts with "retrieved" and "relevant" keys
            Example: [
                {"retrieved": ["c1", "c2"], "relevant": ["c2"]},
                {"retrieved": ["c3", "c4"], "relevant": ["c3"]},
            ]

    Returns:
        Mean reciprocal rank (0.0 to 1.0)

    Phase 1 Target: > 0.8
    """
    if not queries_results:
        return 0.0

    total_rr = sum(reciprocal_rank(result["retrieved"], result["relevant"]) for result in queries_results)

    return total_rr / len(queries_results)


def dcg_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """
    Calculate Discounted Cumulative Gain at K (DCG@K).

    DCG@K = Σ(i=1 to k) (rel_i / log2(i + 1))

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)
        k: Cutoff rank

    Returns:
        DCG@K score
    """
    relevant_set = set(relevant)
    dcg = 0.0

    for i, chunk_id in enumerate(retrieved[:k], start=1):
        if chunk_id in relevant_set:
            # Relevance = 1 for binary relevance
            dcg += 1.0 / math.log2(i + 1)

    return dcg


def ndcg_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain at K (nDCG@K).

    nDCG@K = DCG@K / IDCG@K

    Where IDCG@K is the DCG of an ideal ranking.

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)
        k: Cutoff rank

    Returns:
        nDCG@K score (0.0 to 1.0)

    Example:
        retrieved = ["c1", "c2", "c3", "c4", "c5"]
        relevant = ["c2", "c4"]
        k = 5

        DCG@5 = 1/log2(3) + 1/log2(5) = 0.631 + 0.431 = 1.062
        IDCG@5 = 1/log2(2) + 1/log2(3) = 1.0 + 0.631 = 1.631
        nDCG@5 = 1.062 / 1.631 = 0.651
    """
    dcg = dcg_at_k(retrieved, relevant, k)

    # Ideal DCG: all relevant items at top ranks
    num_relevant = min(len(relevant), k)
    if num_relevant == 0:
        return 0.0

    idcg = sum(1.0 / math.log2(i + 2) for i in range(num_relevant))

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """
    Calculate Precision at K (P@K).

    P@K = (# relevant in top K) / K

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)
        k: Cutoff rank

    Returns:
        Precision@K (0.0 to 1.0)

    Example:
        retrieved = ["c1", "c2", "c3", "c4", "c5"]
        relevant = ["c2", "c4", "c6"]
        k = 5

        P@5 = 2 / 5 = 0.4  (c2 and c4 are relevant)
    """
    if k == 0:
        return 0.0

    relevant_set = set(relevant)
    top_k = retrieved[:k]

    num_relevant_in_top_k = sum(1 for chunk_id in top_k if chunk_id in relevant_set)

    return num_relevant_in_top_k / k


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """
    Calculate Recall at K (R@K).

    R@K = (# relevant in top K) / (total # relevant)

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)
        k: Cutoff rank

    Returns:
        Recall@K (0.0 to 1.0)

    Example:
        retrieved = ["c1", "c2", "c3", "c4", "c5"]
        relevant = ["c2", "c4", "c6"]
        k = 5

        R@5 = 2 / 3 = 0.667  (found c2 and c4, missed c6)
    """
    if not relevant:
        return 0.0

    relevant_set = set(relevant)
    top_k = retrieved[:k]

    num_relevant_in_top_k = sum(1 for chunk_id in top_k if chunk_id in relevant_set)

    return num_relevant_in_top_k / len(relevant)


def f1_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """
    Calculate F1 score at K.

    F1@K = 2 * (P@K * R@K) / (P@K + R@K)

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)
        k: Cutoff rank

    Returns:
        F1@K score (0.0 to 1.0)
    """
    precision = precision_at_k(retrieved, relevant, k)
    recall = recall_at_k(retrieved, relevant, k)

    if precision + recall == 0:
        return 0.0

    return 2 * (precision * recall) / (precision + recall)


def average_precision(retrieved: list[str], relevant: list[str]) -> float:
    """
    Calculate Average Precision (AP).

    AP = (Σ P@k * rel(k)) / |relevant|

    Where rel(k) = 1 if kth item is relevant, 0 otherwise.

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)

    Returns:
        Average precision (0.0 to 1.0)
    """
    if not relevant:
        return 0.0

    relevant_set = set(relevant)
    precision_sum = 0.0
    num_relevant_seen = 0

    for k, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant_set:
            num_relevant_seen += 1
            precision_at_this_k = num_relevant_seen / k
            precision_sum += precision_at_this_k

    return precision_sum / len(relevant)


def mean_average_precision(queries_results: list[dict[str, Any]]) -> float:
    """
    Calculate Mean Average Precision (MAP) across multiple queries.

    MAP = (1/|Q|) * Σ AP(q)

    Args:
        queries_results: List of dicts with "retrieved" and "relevant" keys

    Returns:
        Mean average precision (0.0 to 1.0)
    """
    if not queries_results:
        return 0.0

    total_ap = sum(average_precision(result["retrieved"], result["relevant"]) for result in queries_results)

    return total_ap / len(queries_results)


def compute_all_metrics(
    retrieved: list[str],
    relevant: list[str],
    k_values: list[int] | None = None,
) -> dict[str, float]:
    """
    Compute all standard metrics for a single query.

    Args:
        retrieved: List of retrieved chunk IDs (in order)
        relevant: List of relevant chunk IDs (ground truth)
        k_values: K values for P@K, R@K, nDCG@K (default: [5, 10, 20])

    Returns:
        Dict with all metrics:
        {
            "rr": ...,
            "ap": ...,
            "ndcg@5": ...,
            "ndcg@10": ...,
            "ndcg@20": ...,
            "precision@5": ...,
            "precision@10": ...,
            "precision@20": ...,
            "recall@5": ...,
            "recall@20": ...,
            "f1@5": ...,
        }
    """
    if k_values is None:
        k_values = [5, 10, 20]

    metrics = {
        "rr": reciprocal_rank(retrieved, relevant),
        "ap": average_precision(retrieved, relevant),
    }

    for k in k_values:
        metrics[f"ndcg@{k}"] = ndcg_at_k(retrieved, relevant, k)
        metrics[f"precision@{k}"] = precision_at_k(retrieved, relevant, k)
        metrics[f"recall@{k}"] = recall_at_k(retrieved, relevant, k)
        metrics[f"f1@{k}"] = f1_at_k(retrieved, relevant, k)

    return metrics
