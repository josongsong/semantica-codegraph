"""
Unit Test 예시

Rules:
- Fake/Mock만 사용
- 외부 IO 금지
- GIVEN-WHEN-THEN 구조
"""

import pytest


@pytest.mark.unit
def test_vector_search_returns_top_results(fake_vector, fake_llm):
    """
    GIVEN: 벡터 스토어에 문서가 인덱싱되어 있고
    WHEN: 검색 쿼리를 실행하면
    THEN: 유사도 순으로 결과가 반환된다
    """
    # GIVEN
    fake_vector.upsert(
        "test_collection",
        [
            {
                "id": "doc1",
                "vector": fake_llm.embed("Python function"),
                "payload": {"file": "test.py", "symbol": "func1"},
            },
            {
                "id": "doc2",
                "vector": fake_llm.embed("JavaScript function"),
                "payload": {"file": "test.js", "symbol": "func2"},
            },
        ],
    )

    # WHEN
    query_vector = fake_llm.embed("Python")
    results = fake_vector.search(
        collection_name="test_collection",
        query_vector=query_vector,
        limit=10,
    )

    # THEN
    assert len(results) == 2
    assert results[0]["id"] == "doc1"  # Python이 더 유사
    assert results[0]["score"] > results[1]["score"]


@pytest.mark.unit
def test_graph_traverse_follows_call_chain(fake_graph):
    """
    GIVEN: 함수 호출 그래프가 있고
    WHEN: 시작점에서 multi-hop traversal을 하면
    THEN: 호출 체인을 따라 모든 노드를 찾는다
    """
    # GIVEN
    fake_graph.add_node("func1", "FUNCTION", {"name": "search"})
    fake_graph.add_node("func2", "FUNCTION", {"name": "query"})
    fake_graph.add_node("func3", "FUNCTION", {"name": "execute"})

    fake_graph.add_edge("func1", "func2", "CALLS")
    fake_graph.add_edge("func2", "func3", "CALLS")

    # WHEN
    visited = fake_graph.traverse(
        start_id="func1",
        edge_types=["CALLS"],
        max_depth=3,
    )

    # THEN
    assert len(visited) == 3
    node_names = [n["name"] for n in visited]
    assert "search" in node_names
    assert "query" in node_names
    assert "execute" in node_names


@pytest.mark.unit
def test_lexical_search_matches_substring(fake_lexical):
    """
    GIVEN: 문서가 인덱싱되어 있고
    WHEN: substring 검색을 하면
    THEN: 매칭되는 문서를 찾는다
    """
    # GIVEN
    fake_lexical.index("doc1", "def search_route(): pass")
    fake_lexical.index("doc2", "def create_route(): pass")

    # WHEN
    results = fake_lexical.search("search", limit=10)

    # THEN
    assert len(results) == 1
    assert results[0]["id"] == "doc1"


@pytest.mark.unit
def test_fake_llm_embedding_is_deterministic(fake_llm):
    """
    GIVEN: Fake LLM Provider가 있고
    WHEN: 같은 텍스트를 여러 번 임베딩하면
    THEN: 항상 같은 벡터를 반환한다 (deterministic)
    """
    # GIVEN
    text = "test text"

    # WHEN
    vec1 = fake_llm.embed(text)
    vec2 = fake_llm.embed(text)

    # THEN
    assert vec1 == vec2
    assert len(vec1) == 1536  # embedding_dim
