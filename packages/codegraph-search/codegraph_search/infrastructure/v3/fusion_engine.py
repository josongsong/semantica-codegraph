"""
Fusion Engine V3.

Main fusion pipeline that integrates all components (RFC sections 6-10).
"""

from collections import defaultdict
from typing import Any

from codegraph_search.infrastructure.v3.config import RetrieverV3Config, WeightProfile
from codegraph_search.infrastructure.v3.consensus_engine import ConsensusEngine
from codegraph_search.infrastructure.v3.models import (
    ConsensusStats,
    FeatureVector,
    FusedResultV3,
    IntentProbability,
    RankedHit,
)
from codegraph_search.infrastructure.v3.rrf_normalizer import RRFNormalizer
from codegraph_shared.infra.observability import get_logger, record_histogram

logger = get_logger(__name__)


class FusionEngineV3:
    """
    Main fusion engine for v3 retriever.

    Orchestrates the complete fusion pipeline:
    1. RRF normalization with weights
    2. Consensus boosting
    3. Feature vector generation
    4. Final ranking
    5. Explainability
    """

    def __init__(self, config: RetrieverV3Config):
        """
        Initialize fusion engine.

        Args:
            config: Complete v3 configuration
        """
        self.config = config
        self.rrf_normalizer = RRFNormalizer(config.rrf)
        self.consensus_engine = ConsensusEngine(config.consensus)

    def fuse(
        self,
        hits_by_strategy: dict[str, list[RankedHit]],
        intent_prob: IntentProbability,
        metadata_map: dict[str, dict[str, Any]] | None = None,
        query_expansions: dict[str, list[str]] | None = None,
    ) -> list[FusedResultV3]:
        """
        Execute complete fusion pipeline.

        Args:
            hits_by_strategy: Dict of strategy → list of RankedHit
            intent_prob: Multi-label intent probabilities
            metadata_map: Optional dict of chunk_id → metadata
            query_expansions: Optional query expansions (symbols, file_paths, modules)

        Returns:
            List of FusedResultV3 sorted by final_score (descending)
        """
        metadata_map = metadata_map or {}

        # Step 1: Calculate intent-based weights (with non-linear boosting)
        weights = self._calculate_intent_weights(intent_prob)
        logger.debug("intent_weights_calculated", weights=weights.to_dict())

        # Step 2: RRF normalization and weighting
        base_scores, rrf_scores = self.rrf_normalizer.normalize_and_weight(hits_by_strategy, weights)
        logger.debug("base_scores_calculated", chunks_count=len(base_scores))
        record_histogram("retriever_fusion_base_scores_count", len(base_scores))

        # Step 2.5: Apply query expansion boosting (P1 improvement)
        if query_expansions:
            base_scores = self._apply_expansion_boost(base_scores, hits_by_strategy, query_expansions)
            logger.debug("query_expansion_boost_applied", expansions_count=len(query_expansions))
            record_histogram("retriever_fusion_query_expansions_count", len(query_expansions))

        # Step 3: Consensus boosting
        final_scores, consensus_stats = self.consensus_engine.apply_consensus_boost(base_scores, hits_by_strategy)
        logger.debug("consensus_boost_applied", chunks_count=len(final_scores))
        record_histogram("retriever_fusion_consensus_chunks_count", len(final_scores))

        # Step 4: Generate feature vectors
        feature_vectors = self._generate_feature_vectors(
            hits_by_strategy=hits_by_strategy,
            rrf_scores=rrf_scores,
            weights=weights,
            consensus_stats=consensus_stats,
            metadata_map=metadata_map,
        )

        # Step 5: Build fused results
        fused_results = self._build_fused_results(
            final_scores=final_scores,
            feature_vectors=feature_vectors,
            consensus_stats=consensus_stats,
            hits_by_strategy=hits_by_strategy,
            metadata_map=metadata_map,
        )

        # Step 6: Sort by final score
        fused_results.sort(key=lambda r: r.final_score, reverse=True)

        # Step 7: Add explainability if enabled
        if self.config.enable_explainability:
            self._add_explanations(fused_results, intent_prob, weights)

        dominant_intent = intent_prob.dominant_intent()
        logger.info(
            "fusion_complete",
            results_count=len(fused_results),
            dominant_intent=dominant_intent,
            explainability_enabled=self.config.enable_explainability,
        )
        record_histogram("retriever_fusion_results_count", len(fused_results))

        return fused_results

    def _calculate_intent_weights(self, intent_prob: IntentProbability) -> WeightProfile:
        """
        Calculate weighted combination of intent profiles (RFC 5-2).

        P1 Improvement: Apply non-linear boost for dominant intents (flow, symbol).

        Args:
            intent_prob: Intent probability distribution

        Returns:
            Combined WeightProfile
        """
        # Get base profiles
        profiles = {
            "symbol": self.config.intent_weights.symbol,
            "flow": self.config.intent_weights.flow,
            "concept": self.config.intent_weights.concept,
            "code": self.config.intent_weights.code,
            "balanced": self.config.intent_weights.balanced,
        }

        # Linear combination
        combined = {
            "vec": 0.0,
            "lex": 0.0,
            "sym": 0.0,
            "graph": 0.0,
        }

        intent_dict = intent_prob.to_dict()

        for intent_name, probability in intent_dict.items():
            profile = profiles[intent_name]
            combined["vec"] += probability * profile.vec
            combined["lex"] += probability * profile.lex
            combined["sym"] += probability * profile.sym
            combined["graph"] += probability * profile.graph

        # P1 Improvement: Non-linear boost for dominant intents
        dominant = intent_prob.dominant_intent()

        if dominant == "flow" and intent_prob.flow > 0.2:
            # Boost graph weight for flow queries
            boost_factor = 1.3
            combined["graph"] *= boost_factor
            logger.debug("flow_intent_boost_applied", boost_factor=boost_factor, graph_weight=combined["graph"])
            record_histogram("retriever_fusion_intent_boost_factor", boost_factor)

        elif dominant == "symbol" and intent_prob.symbol > 0.3:
            # Boost symbol weight for symbol queries
            boost_factor = 1.2
            combined["sym"] *= boost_factor
            logger.debug("symbol_intent_boost_applied", boost_factor=boost_factor, sym_weight=combined["sym"])
            record_histogram("retriever_fusion_intent_boost_factor", boost_factor)

        # Re-normalize to ensure weights sum to ~1.0
        total = combined["vec"] + combined["lex"] + combined["sym"] + combined["graph"]
        if total > 0:
            combined["vec"] /= total
            combined["lex"] /= total
            combined["sym"] /= total
            combined["graph"] /= total

        # Create normalized WeightProfile
        return WeightProfile(
            vec=combined["vec"],
            lex=combined["lex"],
            sym=combined["sym"],
            graph=combined["graph"],
        )

    def _apply_expansion_boost(
        self,
        base_scores: dict[str, float],
        hits_by_strategy: dict[str, list[RankedHit]],
        query_expansions: dict[str, list[str]],
    ) -> dict[str, float]:
        """
        Apply boosting for chunks that match query expansions.

        P1 Improvement: Use extracted symbols, file_paths, modules to boost relevant chunks.

        Args:
            base_scores: Dict of chunk_id → base score
            hits_by_strategy: Dict of strategy → list of RankedHit
            query_expansions: Dict with keys: symbols, file_paths, modules

        Returns:
            Updated base_scores dict with expansion boosts applied
        """
        expansion_boost_factor = 1.1  # 10% boost for expansion matches

        # Extract all chunks and their metadata
        chunk_metadata: dict[str, dict[str, Any]] = {}
        for _strategy, hits in hits_by_strategy.items():
            for hit in hits:
                if hit.chunk_id not in chunk_metadata:
                    chunk_metadata[hit.chunk_id] = {
                        "file_path": hit.file_path,
                        "symbol_id": hit.symbol_id or "",
                        "metadata": hit.metadata,
                    }

        # Check each chunk for expansion matches
        boosted_chunks = 0
        for chunk_id, score in base_scores.items():
            metadata = chunk_metadata.get(chunk_id, {})
            has_match = False

            # Check symbol matches
            if "symbols" in query_expansions:
                symbol_id = metadata.get("symbol_id", "")
                for expanded_symbol in query_expansions["symbols"]:
                    if expanded_symbol.lower() in symbol_id.lower():
                        has_match = True
                        break

            # Check file path matches
            if not has_match and "file_paths" in query_expansions:
                file_path = metadata.get("file_path", "")
                for expanded_path in query_expansions["file_paths"]:
                    if expanded_path.lower() in file_path.lower():
                        has_match = True
                        break

            # Check module matches
            if not has_match and "modules" in query_expansions:
                file_path = metadata.get("file_path", "")
                for expanded_module in query_expansions["modules"]:
                    if expanded_module.lower() in file_path.lower():
                        has_match = True
                        break

            # Apply boost if match found
            if has_match:
                base_scores[chunk_id] = score * expansion_boost_factor
                boosted_chunks += 1

        if boosted_chunks > 0:
            logger.debug("expansion_boost_applied", boosted_chunks=boosted_chunks, boost_factor=expansion_boost_factor)
            record_histogram("retriever_fusion_expansion_boosted_chunks", boosted_chunks)

        return base_scores

    def _generate_feature_vectors(
        self,
        hits_by_strategy: dict[str, list[RankedHit]],
        rrf_scores: dict[str, dict[str, float]],
        weights: WeightProfile,
        consensus_stats: dict[str, ConsensusStats],
        metadata_map: dict[str, dict[str, Any]],
    ) -> dict[str, FeatureVector]:
        """
        Generate LTR-ready feature vectors for all chunks.

        Args:
            hits_by_strategy: Dict of strategy → list of RankedHit
            rrf_scores: Dict of chunk_id → dict of strategy → rrf_score
            weights: Intent-based weights
            consensus_stats: Dict of chunk_id → ConsensusStats
            metadata_map: Dict of chunk_id → metadata

        Returns:
            Dict of chunk_id → FeatureVector
        """
        feature_vectors = {}
        weight_map = weights.to_dict()

        # Build chunk → strategy → rank map
        chunk_ranks: dict[str, dict[str, int]] = defaultdict(dict)
        for strategy, hits in hits_by_strategy.items():
            for hit in hits:
                chunk_ranks[hit.chunk_id][strategy] = hit.rank

        # Generate feature vector for each chunk
        for chunk_id in chunk_ranks.keys():
            stats = consensus_stats.get(chunk_id)
            metadata = metadata_map.get(chunk_id, {})

            # Extract metadata features
            chunk_size = metadata.get("chunk_size", 0)
            file_path = metadata.get("file_path", "")
            file_depth = file_path.count("/") if file_path else 0
            symbol_type = metadata.get("symbol_type", "")

            # Build feature vector
            feature_vec = FeatureVector(
                chunk_id=chunk_id,
                # Ranks
                rank_vec=chunk_ranks[chunk_id].get("vector"),
                rank_lex=chunk_ranks[chunk_id].get("lexical"),
                rank_sym=chunk_ranks[chunk_id].get("symbol"),
                rank_graph=chunk_ranks[chunk_id].get("graph"),
                # RRF scores
                rrf_vec=rrf_scores.get(chunk_id, {}).get("vector", 0.0),
                rrf_lex=rrf_scores.get(chunk_id, {}).get("lexical", 0.0),
                rrf_sym=rrf_scores.get(chunk_id, {}).get("symbol", 0.0),
                rrf_graph=rrf_scores.get(chunk_id, {}).get("graph", 0.0),
                # Weights
                weight_vec=weight_map["vector"],
                weight_lex=weight_map["lexical"],
                weight_sym=weight_map["symbol"],
                weight_graph=weight_map["graph"],
                # Consensus
                num_strategies=stats.num_strategies if stats else 0,
                best_rank=stats.best_rank if stats else 999999,
                avg_rank=stats.avg_rank if stats else 999999.0,
                consensus_factor=stats.consensus_factor if stats else 1.0,
                # Metadata
                chunk_size=chunk_size,
                file_depth=file_depth,
                symbol_type=symbol_type,
                metadata=metadata,
            )

            feature_vectors[chunk_id] = feature_vec

        return feature_vectors

    def _build_fused_results(
        self,
        final_scores: dict[str, float],
        feature_vectors: dict[str, FeatureVector],
        consensus_stats: dict[str, ConsensusStats],
        hits_by_strategy: dict[str, list[RankedHit]],
        metadata_map: dict[str, dict[str, Any]],
    ) -> list[FusedResultV3]:
        """
        Build final fused results from all components.

        Args:
            final_scores: Dict of chunk_id → final_score
            feature_vectors: Dict of chunk_id → FeatureVector
            consensus_stats: Dict of chunk_id → ConsensusStats
            hits_by_strategy: Dict of strategy → list of RankedHit
            metadata_map: Dict of chunk_id → metadata

        Returns:
            List of FusedResultV3
        """
        fused_results = []

        for chunk_id, final_score in final_scores.items():
            feature_vec = feature_vectors[chunk_id]
            stats = consensus_stats[chunk_id]
            metadata = metadata_map.get(chunk_id, {})

            # Get file_path and symbol_id from first hit
            file_path = None
            symbol_id = None

            for hits in hits_by_strategy.values():
                for hit in hits:
                    if hit.chunk_id == chunk_id:
                        file_path = hit.file_path
                        symbol_id = hit.symbol_id
                        break
                if file_path:
                    break

            result = FusedResultV3(
                chunk_id=chunk_id,
                file_path=file_path,
                symbol_id=symbol_id,
                final_score=final_score,
                feature_vector=feature_vec,
                consensus_stats=stats,
                metadata=metadata,
            )

            fused_results.append(result)

        return fused_results

    def _add_explanations(
        self,
        results: list[FusedResultV3],
        intent_prob: IntentProbability,
        weights: WeightProfile,
    ):
        """
        Add human-readable explanations to results.

        Modifies results in-place.

        Args:
            results: List of FusedResultV3
            intent_prob: Intent probabilities
            weights: Intent-based weights
        """
        dominant = intent_prob.dominant_intent()
        weights.to_dict()

        for result in results:
            stats = result.consensus_stats
            fv = result.feature_vector

            # Build explanation
            parts = []

            # Dominant intent
            parts.append(f"Intent: {dominant} ({intent_prob.to_dict()[dominant]:.2f})")

            # Consensus
            consensus_exp = self.consensus_engine.explain_consensus(stats)
            parts.append(consensus_exp)

            # Strategy contributions
            strategy_contribs = []
            for strategy in ["vector", "lexical", "symbol", "graph"]:
                rrf_key = f"rrf_{strategy[:3]}"
                rrf_score = getattr(fv, rrf_key, 0.0)
                weight_key = f"weight_{strategy[:3]}"
                weight = getattr(fv, weight_key, 0.0)

                if rrf_score > 0:
                    contrib = rrf_score * weight
                    strategy_contribs.append(f"{strategy}={contrib:.4f} (rrf={rrf_score:.4f}, w={weight:.2f})")

            if strategy_contribs:
                parts.append("Contributions: " + ", ".join(strategy_contribs))

            # Final score
            parts.append(f"Final score: {result.final_score:.4f}")

            result.explanation = " | ".join(parts)

    def apply_cutoff(self, results: list[FusedResultV3], intent_prob: IntentProbability) -> list[FusedResultV3]:
        """
        Apply intent-based top-K cutoff (RFC 8-2, 13-4).

        Args:
            results: List of FusedResultV3 (assumed sorted)
            intent_prob: Intent probabilities

        Returns:
            Cutoff list of FusedResultV3
        """
        # Determine k based on dominant intent
        dominant = intent_prob.dominant_intent()

        k = getattr(self.config.cutoff, dominant, self.config.cutoff.balanced)

        logger.debug("applying_cutoff", k=k, intent=dominant, results_before=len(results))
        record_histogram("retriever_fusion_cutoff_k", k)

        return results[:k]
