"""
Example usage of Retriever V3 (S-HMR-v3).

Demonstrates the complete pipeline with multi-index search results.
"""

from src.index.common.documents import SearchHit
from src.retriever.v3 import RetrieverV3Config, RetrieverV3Service


def main():
    """Run retriever v3 example."""

    # 1. Initialize service with custom config
    config = RetrieverV3Config(
        enable_explainability=True,
        enable_query_expansion=True,
    )
    service = RetrieverV3Service(config=config)

    # 2. Simulate multi-index search results
    # In production, these would come from actual index queries
    hits_by_strategy = {
        "vector": [
            SearchHit(
                chunk_id="chunk_auth_001",
                score=0.92,
                source="vector",
                file_path="src/auth/handlers/login.py",
                symbol_id="func:handle_login",
                metadata={"chunk_size": 450, "symbol_type": "function"},
            ),
            SearchHit(
                chunk_id="chunk_auth_002",
                score=0.85,
                source="vector",
                file_path="src/auth/middleware/verify.py",
                metadata={"chunk_size": 320},
            ),
            SearchHit(
                chunk_id="chunk_auth_003",
                score=0.78,
                source="vector",
                file_path="src/auth/utils/jwt.py",
                metadata={"chunk_size": 280},
            ),
        ],
        "lexical": [
            SearchHit(
                chunk_id="chunk_auth_001",
                score=18.5,
                source="lexical",
                file_path="src/auth/handlers/login.py",
                metadata={"chunk_size": 450},
            ),
            SearchHit(
                chunk_id="chunk_auth_004",
                score=12.3,
                source="lexical",
                file_path="src/auth/handlers/logout.py",
                metadata={"chunk_size": 380},
            ),
        ],
        "symbol": [
            SearchHit(
                chunk_id="chunk_auth_001",
                score=1.0,
                source="symbol",
                file_path="src/auth/handlers/login.py",
                symbol_id="func:handle_login",
                metadata={"symbol_type": "function", "fqn": "auth.handlers.login.handle_login"},
            ),
        ],
        "graph": [
            SearchHit(
                chunk_id="chunk_auth_001",
                score=0.88,
                source="runtime",
                file_path="src/auth/handlers/login.py",
                metadata={},
            ),
            SearchHit(
                chunk_id="chunk_db_005",
                score=0.65,
                source="runtime",
                file_path="src/db/session.py",
                metadata={"chunk_size": 500},
            ),
        ],
    }

    # 3. Metadata map (optional)
    metadata_map = {
        "chunk_auth_001": {
            "chunk_size": 450,
            "symbol_type": "function",
            "file_path": "src/auth/handlers/login.py",
        },
        "chunk_auth_002": {
            "chunk_size": 320,
            "file_path": "src/auth/middleware/verify.py",
        },
        "chunk_auth_003": {
            "chunk_size": 280,
            "file_path": "src/auth/utils/jwt.py",
        },
        "chunk_auth_004": {
            "chunk_size": 380,
            "file_path": "src/auth/handlers/logout.py",
        },
        "chunk_db_005": {
            "chunk_size": 500,
            "file_path": "src/db/session.py",
        },
    }

    # 4. Example query
    query = "login authentication handler"

    print(f"Query: {query}")
    print("=" * 80)

    # 5. Execute retrieval
    results, intent_prob = service.retrieve(
        query=query,
        hits_by_strategy=hits_by_strategy,
        metadata_map=metadata_map,
        enable_cache=False,
    )

    # 6. Display intent classification
    print("\n[Intent Classification]")
    print(f"  Symbol:   {intent_prob.symbol:.3f}")
    print(f"  Flow:     {intent_prob.flow:.3f}")
    print(f"  Concept:  {intent_prob.concept:.3f}")
    print(f"  Code:     {intent_prob.code:.3f}")
    print(f"  Balanced: {intent_prob.balanced:.3f}")
    print(f"  Dominant: {intent_prob.dominant_intent()}")

    # 7. Display top results
    print(f"\n[Top {min(5, len(results))} Results]")
    print("=" * 80)

    for i, result in enumerate(results[:5], 1):
        print(f"\n{i}. {result.chunk_id}")
        print(f"   File: {result.file_path}")
        print(f"   Final Score: {result.final_score:.4f}")
        print(f"   Consensus: {result.consensus_stats.num_strategies} strategies")
        print(f"   Consensus Factor: {result.consensus_stats.consensus_factor:.3f}x")

        # Show which strategies found this chunk
        strategies = list(result.consensus_stats.ranks.keys())
        print(f"   Found in: {', '.join(strategies)}")

        # Show feature vector (abbreviated)
        fv = result.feature_vector
        print(f"   RRF Scores: vec={fv.rrf_vec:.4f}, lex={fv.rrf_lex:.4f}, "
              f"sym={fv.rrf_sym:.4f}, graph={fv.rrf_graph:.4f}")

        # Show explanation
        if result.explanation:
            print(f"   Explanation: {result.explanation[:100]}...")

    # 8. Extract LTR features
    print("\n[LTR Feature Extraction]")
    chunk_ids, feature_arrays = service.get_feature_vectors(results[:5])

    print(f"Extracted features for {len(chunk_ids)} chunks")
    print(f"Feature dimension: {len(feature_arrays[0])}")
    print(f"Example feature vector (first 10): {feature_arrays[0][:10]}")

    # 9. Demonstrate different intent
    print("\n\n" + "=" * 80)
    print("[Concept Query Example]")
    print("=" * 80)

    concept_query = "how does authentication work in this system?"
    concept_results, concept_intent = service.retrieve(
        query=concept_query,
        hits_by_strategy=hits_by_strategy,
        metadata_map=metadata_map,
        enable_cache=False,
    )

    print(f"Query: {concept_query}")
    print(f"Dominant Intent: {concept_intent.dominant_intent()}")
    print(f"Concept Probability: {concept_intent.concept:.3f}")
    print(f"Results Count: {len(concept_results)}")
    print(f"Top Result: {concept_results[0].chunk_id} (score={concept_results[0].final_score:.4f})")

    # Compare weights
    print("\nWeight Comparison:")
    symbol_fv = results[0].feature_vector
    concept_fv = concept_results[0].feature_vector

    print(f"  Symbol query weights: vec={symbol_fv.weight_vec:.2f}, "
          f"lex={symbol_fv.weight_lex:.2f}, sym={symbol_fv.weight_sym:.2f}, "
          f"graph={symbol_fv.weight_graph:.2f}")
    print(f"  Concept query weights: vec={concept_fv.weight_vec:.2f}, "
          f"lex={concept_fv.weight_lex:.2f}, sym={concept_fv.weight_sym:.2f}, "
          f"graph={concept_fv.weight_graph:.2f}")


if __name__ == "__main__":
    main()
