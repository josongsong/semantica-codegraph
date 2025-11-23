"""
Integration Test 예시

Rules:
- container.py lazy singleton 사용
- docker-compose.test.yml 필요
- 실제 DB 연결

Run:
    docker-compose -f docker-compose.test.yml up -d
    pytest -m integration
    docker-compose -f docker-compose.test.yml down -v
"""

import pytest


@pytest.mark.integration
def test_search_service_hybrid_search(container, clean_db):
    """
    GIVEN: SearchService가 초기화되어 있고
    WHEN: hybrid search를 실행하면
    THEN: lexical + semantic 결과를 합쳐서 반환한다

    ⚠️  Rule: container에서 service를 가져온다 (직접 생성 금지)
    """
    # GIVEN
    search_service = container.search_service

    # TODO: 실제 구현 시
    # - 문서 인덱싱
    # - hybrid search 실행
    # - 결과 검증

    # WHEN
    # results = search_service.search("test query")

    # THEN
    # assert len(results) > 0


@pytest.mark.integration
def test_indexing_service_creates_graph(container, clean_db):
    """
    GIVEN: IndexingService가 초기화되어 있고
    WHEN: 코드를 인덱싱하면
    THEN: 그래프 노드와 엣지가 생성된다

    ⚠️  Rule: container.indexing_service 사용
    """
    # GIVEN
    indexing_service = container.indexing_service

    # TODO: 실제 구현 시
    # - 샘플 코드 인덱싱
    # - 그래프 구조 검증
    # - 벡터/lexical 인덱스 검증

    # WHEN
    # indexing_service.index_code(sample_code)

    # THEN
    # graph = container.graph_service.get_graph()
    # assert len(graph.nodes) > 0


@pytest.mark.integration
@pytest.mark.slow
def test_graph_service_multihop_traversal(container, clean_db):
    """
    GIVEN: 그래프에 call chain이 있고
    WHEN: multi-hop traversal을 실행하면
    THEN: 모든 경로를 찾는다

    ⚠️  Rule: container.graph_service 사용
    """
    # GIVEN
    graph_service = container.graph_service

    # TODO: 실제 구현 시
    # - 그래프 데이터 준비
    # - multi-hop query
    # - 결과 검증

    # WHEN
    # results = graph_service.traverse(start_id="func1", max_depth=3)

    # THEN
    # assert len(results) > 0
