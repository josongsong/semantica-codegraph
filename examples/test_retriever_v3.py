"""
Quick test script for Retriever V3.

Tests different query types and shows intent classification + ranking.
"""

from src.index.common.documents import SearchHit
from src.retriever.v3 import RetrieverV3Config, RetrieverV3Service


def create_sample_hits():
    """Create sample hits for testing."""
    return {
        "vector": [
            SearchHit(
                chunk_id="auth_login_handler",
                score=0.95,
                source="vector",
                file_path="src/auth/login.py",
                symbol_id="func:login",
                metadata={"chunk_size": 500, "symbol_type": "function"},
            ),
            SearchHit(
                chunk_id="auth_verify_token",
                score=0.88,
                source="vector",
                file_path="src/auth/verify.py",
                metadata={"chunk_size": 350},
            ),
            SearchHit(
                chunk_id="db_connection",
                score=0.75,
                source="vector",
                file_path="src/db/connection.py",
                metadata={"chunk_size": 450},
            ),
        ],
        "lexical": [
            SearchHit(
                chunk_id="auth_login_handler",
                score=22.5,
                source="lexical",
                file_path="src/auth/login.py",
                metadata={"chunk_size": 500},
            ),
            SearchHit(
                chunk_id="auth_logout",
                score=18.0,
                source="lexical",
                file_path="src/auth/logout.py",
                metadata={"chunk_size": 300},
            ),
            SearchHit(
                chunk_id="user_profile",
                score=15.5,
                source="lexical",
                file_path="src/user/profile.py",
                metadata={"chunk_size": 400},
            ),
        ],
        "symbol": [
            SearchHit(
                chunk_id="auth_login_handler",
                score=1.0,
                source="symbol",
                file_path="src/auth/login.py",
                symbol_id="func:login",
                metadata={"symbol_type": "function"},
            ),
            SearchHit(
                chunk_id="auth_class",
                score=0.9,
                source="symbol",
                file_path="src/auth/authenticator.py",
                symbol_id="class:Authenticator",
                metadata={"symbol_type": "class"},
            ),
        ],
        "graph": [
            SearchHit(
                chunk_id="auth_login_handler",
                score=0.85,
                source="runtime",
                file_path="src/auth/login.py",
                metadata={},
            ),
            SearchHit(
                chunk_id="db_connection",
                score=0.70,
                source="runtime",
                file_path="src/db/connection.py",
                metadata={},
            ),
            SearchHit(
                chunk_id="session_manager",
                score=0.65,
                source="runtime",
                file_path="src/session/manager.py",
                metadata={"chunk_size": 600},
            ),
        ],
    }


def test_query(service, query, hits):
    """Test a single query and display results."""
    print(f"\n{'=' * 80}")
    print(f"Query: '{query}'")
    print("=" * 80)

    results, intent = service.retrieve(
        query=query,
        hits_by_strategy=hits,
        enable_cache=False,
    )

    # Show intent
    print("\n📊 Intent Classification:")
    print(f"  • Symbol:   {intent.symbol:.3f} {'⭐' if intent.symbol > 0.3 else ''}")
    print(f"  • Flow:     {intent.flow:.3f} {'⭐' if intent.flow > 0.3 else ''}")
    print(f"  • Concept:  {intent.concept:.3f} {'⭐' if intent.concept > 0.3 else ''}")
    print(f"  • Code:     {intent.code:.3f} {'⭐' if intent.code > 0.3 else ''}")
    print(f"  • Balanced: {intent.balanced:.3f} {'⭐' if intent.balanced > 0.3 else ''}")
    print(f"  → Dominant: {intent.dominant_intent().upper()}")

    # Show weights
    if results:
        fv = results[0].feature_vector
        print("\n⚖️  Strategy Weights:")
        print(f"  • Vector:  {fv.weight_vec:.2f}")
        print(f"  • Lexical: {fv.weight_lex:.2f}")
        print(f"  • Symbol:  {fv.weight_sym:.2f}")
        print(f"  • Graph:   {fv.weight_graph:.2f}")

    # Show top results
    print(f"\n🏆 Top {min(3, len(results))} Results:")
    for i, result in enumerate(results[:3], 1):
        consensus = result.consensus_stats
        print(f"\n  {i}. {result.chunk_id}")
        print(f"     Score: {result.final_score:.4f}")
        print(f"     Consensus: {consensus.num_strategies} strategies, {consensus.consensus_factor:.2f}x boost")
        print(f"     Strategies: {', '.join(consensus.ranks.keys())}")


def main():
    """Run tests."""
    print("=" * 80)
    print(" Retriever V3 - Quick Test")
    print("=" * 80)

    # Initialize service
    config = RetrieverV3Config(
        enable_explainability=True,
        enable_query_expansion=True,
    )
    service = RetrieverV3Service(config=config)
    hits = create_sample_hits()

    # Test 1: Symbol query (short identifier)
    test_query(service, "login", hits)

    # Test 2: Concept query
    test_query(service, "how does authentication work?", hits)

    # Test 3: Flow trace query
    test_query(service, "trace call from login to database", hits)

    # Test 4: Code search query
    test_query(service, "show me authentication implementation example", hits)

    # Test 5: Mixed query
    test_query(service, "find LoginHandler class", hits)

    # Summary
    print(f"\n{'=' * 80}")
    print("✅ All tests completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
