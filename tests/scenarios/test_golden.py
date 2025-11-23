"""
Scenario / Golden Test 예시

Rules:
- Golden JSON 파일 기반
- 순서(order) strict match
- 검색 품질 회귀 방지
"""

import pytest


@pytest.mark.scenario
def test_symbol_search_golden(container, load_golden):
    """
    GIVEN: Golden test 데이터가 있고
    WHEN: 검색을 실행하면
    THEN: 예상한 순서로 결과가 반환된다

    ⚠️  Rule: golden 파일 기반 strict ranking 검증
    """
    # GIVEN
    golden = load_golden("sample_golden.json")
    query = golden["query"]
    expected_nodes = golden["expected_nodes"]

    # TODO: 실제 구현 시
    # search_service = container.search_service

    # WHEN
    # results = search_service.search(query)

    # THEN
    # assert len(results) == len(expected_nodes)
    #
    # for i, expected in enumerate(expected_nodes):
    #     actual = results[i]
    #     assert actual["symbol"] == expected["symbol"]
    #     assert actual["file"] == expected["file"]
    #     assert actual["line"] == expected["line"]


@pytest.mark.scenario
def test_graph_dependency_golden(container, load_golden):
    """
    GIVEN: Golden graph test 데이터가 있고
    WHEN: 그래프 쿼리를 실행하면
    THEN: 예상한 dependency chain을 찾는다
    """
    # TODO: golden 파일 준비 후 구현
    pass


@pytest.mark.scenario
def test_hybrid_ranking_golden(container, load_golden):
    """
    GIVEN: Hybrid ranking golden test 데이터가 있고
    WHEN: hybrid search를 실행하면
    THEN: lexical + semantic + graph 점수가 올바르게 합쳐진다
    """
    # TODO: golden 파일 준비 후 구현
    pass
