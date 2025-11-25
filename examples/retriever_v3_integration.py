"""
V3 Retriever Integration Example.

Shows how to integrate V3 with existing multi-index orchestrator.
"""

from src.index.common.documents import SearchHit
from src.retriever import MultiIndexResult
from src.retriever.v3 import RetrieverV3Config
from src.retriever.v3.adapter import V3RetrieverAdapter, build_metadata_map


def main():
    """Run integration example."""
    print("=" * 80)
    print(" V3 Retriever Integration Example")
    print("=" * 80)

    # 1. Create V3 adapter
    config = RetrieverV3Config(
        enable_explainability=True,
        enable_query_expansion=True,
    )
    adapter = V3RetrieverAdapter(config=config)

    # 2. Simulate multi-index result (would come from orchestrator)
    multi_result = MultiIndexResult(
        vector_hits=[
            SearchHit(
                chunk_id="auth_handler",
                score=0.92,
                source="vector",
                file_path="src/auth/handler.py",
                metadata={"chunk_size": 500},
            ),
            SearchHit(
                chunk_id="db_connection",
                score=0.85,
                source="vector",
                file_path="src/db/connection.py",
                metadata={"chunk_size": 450},
            ),
        ],
        lexical_hits=[
            SearchHit(
                chunk_id="auth_handler",
                score=22.0,
                source="lexical",
                file_path="src/auth/handler.py",
                metadata={"chunk_size": 500},
            ),
        ],
        symbol_hits=[
            SearchHit(
                chunk_id="auth_handler",
                score=1.0,
                source="symbol",
                file_path="src/auth/handler.py",
                symbol_id="func:authenticate",
                metadata={"symbol_type": "function"},
            ),
        ],
        graph_hits=[
            SearchHit(
                chunk_id="auth_handler",
                score=0.88,
                source="runtime",
                file_path="src/auth/handler.py",
                metadata={},
            ),
            SearchHit(
                chunk_id="session_manager",
                score=0.70,
                source="runtime",
                file_path="src/session/manager.py",
                metadata={"chunk_size": 600},
            ),
        ],
    )

    # 3. Build metadata map
    metadata_map = build_metadata_map(multi_result)
    print("\n📦 Multi-index results:")
    print(f"  Vector:  {len(multi_result.vector_hits)} hits")
    print(f"  Lexical: {len(multi_result.lexical_hits)} hits")
    print(f"  Symbol:  {len(multi_result.symbol_hits)} hits")
    print(f"  Graph:   {len(multi_result.graph_hits)} hits")
    print(f"  Total metadata: {len(metadata_map)} chunks")

    # 4. Use V3 fusion
    query = "authentication handler"
    print(f"\n🔍 Query: '{query}'")

    fused_results, intent = adapter.fuse_multi_index_result(
        query=query,
        multi_result=multi_result,
        metadata_map=metadata_map,
    )

    # 5. Display results
    print(f"\n📊 Intent: {intent.dominant_intent()}")
    print(f"  Symbol:  {intent.symbol:.3f}")
    print(f"  Flow:    {intent.flow:.3f}")
    print(f"  Concept: {intent.concept:.3f}")
    print(f"  Code:    {intent.code:.3f}")

    print(f"\n🏆 Top {len(fused_results)} Results:")
    for i, result in enumerate(fused_results, 1):
        print(f"\n  {i}. {result.chunk_id}")
        print(f"     Score: {result.final_score:.4f}")
        print(f"     Consensus: {result.consensus_stats.num_strategies} strategies")
        print(f"     Boost: {result.consensus_stats.consensus_factor:.2f}x")

    # 6. Build context (simplified)
    context = adapter.build_context(fused_results, token_budget=4000)
    if context:
        print("\n📝 Context:")
        print(f"  Chunks: {context.chunk_count}")
        print(f"  Tokens: {context.total_tokens}/{context.token_budget}")

    # 7. Complete pipeline
    print("\n" + "=" * 80)
    print(" Complete Pipeline")
    print("=" * 80)

    fused_results2, intent2, context2 = adapter.retrieve_with_context(
        query="find authentication function",
        multi_result=multi_result,
        token_budget=4000,
        metadata_map=metadata_map,
    )

    print("\n✅ Complete!")
    print(f"  Intent: {intent2.dominant_intent()}")
    print(f"  Results: {len(fused_results2)}")
    print(f"  Context: {context2.chunk_count if context2 else 0} chunks")

    print("\n" + "=" * 80)
    print(" Integration Example Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
