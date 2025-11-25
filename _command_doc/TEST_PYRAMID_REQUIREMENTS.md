# Semantica Codegraph - 테스트 피라미드 필수 구현 기준

## 목차
1. [테스트 피라미드 개요](#테스트-피라미드-개요)
2. [레이어별 필수 테스트](#레이어별-필수-테스트)
3. [테스트 우선순위](#테스트-우선순위)
4. [실행 전략](#실행-전략)
5. [커버리지 목표](#커버리지-목표)

---

## 테스트 피라미드 개요

```
        ┌─────────────────┐
        │   E2E Tests     │  5-10%  (느림, 비용 높음)
        │   (scenario)    │
        ├─────────────────┤
        │  Integration    │  15-20% (중간 속도)
        │     Tests       │
        ├─────────────────┤
        │   Unit Tests    │  70-80% (빠름, 저비용)
        │                 │
        └─────────────────┘
```

### 테스트 마커 정의
```python
@pytest.mark.unit          # Unit tests (빠름, mock/fake 사용)
@pytest.mark.integration   # Integration tests (실제 DB/서비스)
@pytest.mark.scenario      # E2E/Scenario tests (전체 플로우)
```

---

## 레이어별 필수 테스트

### 1. Foundation Layer (Unit: 80%, Integration: 20%)

Foundation은 가장 기초적인 레이어로, **높은 unit test 커버리지**가 필수입니다.

#### 1.1 foundation.parsing ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/foundation/test_parser_registry.py
- test_register_parser()
- test_get_parser_by_language()
- test_unsupported_language_error()

# tests/foundation/test_source_file.py
- test_source_file_creation()
- test_source_file_content_loading()
- test_source_file_hash_calculation()

# tests/foundation/test_ast_tree.py
- test_ast_creation_from_python_code()
- test_ast_node_traversal()
- test_ast_node_query()
```

**Integration Tests - 필수**
```python
# tests/foundation/test_incremental_parsing.py
- test_incremental_parse_on_file_change()
- test_parse_multiple_files_in_repo()
```

#### 1.2 foundation.ir ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/foundation/test_python_generator_basic.py
- test_function_ir_generation()
- test_class_ir_generation()
- test_conditional_ir_generation()
- test_loop_ir_generation()
- test_scope_tracking()
- test_fqn_generation()

# tests/foundation/test_signature_models.py
- test_function_signature_creation()
- test_parameter_extraction()

# tests/foundation/test_typing_models.py
- test_type_resolution()
- test_generic_type_handling()
```

**Integration Tests - 선택**
```python
# tests/foundation/test_ir_to_ast_mapping.py
- test_ir_preserves_ast_location()
```

#### 1.3 foundation.graph ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/foundation/test_graph_builder.py
- test_create_function_node()
- test_create_class_node()
- test_create_call_edge()
- test_create_import_edge()
- test_create_inheritance_edge()

# tests/foundation/test_graph_dfg_integration.py
- test_data_flow_edge_creation()
- test_variable_def_use_tracking()
```

**Integration Tests - 필수**
```python
# tests/foundation/test_graph_extended.py
- test_build_graph_from_multiple_files()
- test_cross_file_references()
- test_entry_point_detection()
```

#### 1.4 foundation.chunk ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/foundation/test_chunk_builder.py
- test_leaf_chunk_creation()
- test_parent_chunk_creation()
- test_chunk_hierarchy_building()
- test_chunk_id_generation()

# tests/foundation/test_chunk_boundary.py
- test_chunk_boundary_detection()
- test_chunk_overlap_calculation()

# tests/foundation/test_chunk_models.py
- test_chunk_serialization()
- test_chunk_metadata()
```

**Integration Tests - 필수**
```python
# tests/foundation/test_chunk_graph_integration.py
- test_chunk_references_graph_nodes()
- test_chunk_hierarchy_consistency()

# tests/foundation/test_chunk_incremental.py
- test_chunk_update_on_file_change()
- test_chunk_deletion_on_file_removal()
```

#### 1.5 foundation.dfg ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/foundation/test_dfg_builder.py
- test_variable_definition_tracking()
- test_variable_use_tracking()
- test_data_flow_edge_creation()

# tests/foundation/test_dfg_advanced.py
- test_interprocedural_data_flow()
- test_aliasing_handling()
```

---

### 2. RepoMap Layer (Unit: 70%, Integration: 30%)

#### 2.1 repomap.builder ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/repomap/test_repomap_builder.py
- test_repomap_node_creation()
- test_repomap_tree_building()
- test_repomap_node_relationships()

# tests/repomap/test_repomap_models.py
- test_repomap_node_serialization()
- test_repomap_tree_traversal()
```

**Integration Tests - 필수**
```python
# tests/repomap/test_repomap_builder_integration.py
- test_build_repomap_from_ir_graph_chunk()
- test_repomap_references_foundation_objects()
```

#### 2.2 repomap.pagerank ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/repomap/test_repomap_pagerank.py
- test_pagerank_calculation()
- test_importance_score_assignment()
- test_hybrid_rank_calculation()
```

**Integration Tests - 선택**
```python
# tests/repomap/test_pagerank_with_real_graph.py
- test_pagerank_on_large_graph()
```

#### 2.3 repomap.summarizer ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/repomap/test_repomap_summarizer.py
- test_function_summary_generation()
- test_module_summary_generation()
- test_llm_summarizer_with_mock()
```

**Integration Tests - 선택**
```python
# tests/repomap/test_summarizer_with_real_llm.py
- test_summary_generation_with_real_llm()
```

#### 2.4 repomap.storage ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/repomap/test_postgres_store.py
- test_save_repomap_tree()
- test_load_repomap_tree()
- test_update_repomap_node()
```

**Integration Tests - 필수**
```python
# tests/repomap/test_incremental.py
- test_incremental_repomap_update()
- test_repomap_cache_invalidation()
```

---

### 3. Index Layer (Unit: 60%, Integration: 40%)

Index 레이어는 외부 서비스와 통합되므로 **integration test 비중이 높습니다**.

#### 3.1 index.lexical ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/index/test_lexical_adapter.py
- test_lexical_document_creation()
- test_lexical_query_building()
- test_lexical_result_parsing()
```

**Integration Tests - 필수**
```python
# tests/index/test_lexical_zoekt_integration.py
- test_index_chunks_to_zoekt()
- test_search_by_substring()
- test_search_by_regex()
```

#### 3.2 index.vector ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/index/test_vector_adapter.py
- test_vector_document_creation()
- test_embedding_generation()
- test_vector_query_building()
```

**Integration Tests - 필수**
```python
# tests/index/test_vector_qdrant_integration.py
- test_index_chunks_to_qdrant()
- test_semantic_search()
- test_hybrid_search()
```

#### 3.3 index.symbol ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/index/test_symbol_index.py
- test_symbol_definition_indexing()
- test_symbol_reference_indexing()
- test_symbol_scope_indexing()
```

**Integration Tests - 필수**
```python
# tests/index/test_symbol_kuzu_integration.py
- test_index_symbols_to_kuzu()
- test_find_definitions()
- test_find_references()
- test_find_implementations()
```

#### 3.4 index.fuzzy ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/index/test_fuzzy_adapter.py
- test_fuzzy_ngram_generation()
- test_fuzzy_query_building()
```

**Integration Tests - 필수**
```python
# tests/index/test_fuzzy_postgres_integration.py
- test_fuzzy_search_with_typos()
- test_fuzzy_search_with_partial_match()
```

#### 3.5 index.domain_meta ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/index/test_domain_adapter.py
- test_readme_indexing()
- test_openapi_indexing()
- test_schema_indexing()
```

**Integration Tests - 선택**
```python
# tests/index/test_domain_integration.py
- test_domain_to_code_mapping()
```

#### 3.6 index.service ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/index/test_service_error_handling.py
- test_service_error_handling()
- test_service_retry_logic()
- test_service_circuit_breaker()
```

**Integration Tests - 필수**
```python
# tests/index/test_service_orchestration.py
- test_multi_index_orchestration()
- test_index_pipeline_execution()
```

---

### 4. Retriever Layer (Unit: 50%, Integration: 40%, E2E: 10%)

Retriever는 전체 시스템을 통합하므로 **E2E 테스트가 중요합니다**.

#### 4.1 retriever.intent ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/retriever/test_intent_classifier.py
- test_intent_classification()
- test_query_type_detection()
- test_retrieval_plan_generation()

# tests/retriever/test_intent_rule_classifier.py
- test_rule_based_classification()
- test_pattern_matching()
```

**Integration Tests - 선택**
```python
# tests/retriever/test_intent_with_llm.py
- test_llm_based_intent_classification()
```

#### 4.2 retriever.multi_index ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/retriever/test_multi_index_orchestrator.py
- test_parallel_index_queries()
- test_index_client_coordination()
- test_candidate_set_creation()
```

**Integration Tests - 필수**
```python
# tests/retriever/test_multi_index_integration.py
- test_query_all_indexes()
- test_index_timeout_handling()
- test_index_failure_resilience()
```

#### 4.3 retriever.fusion ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/retriever/test_fusion_engine.py
- test_weighted_score_fusion()
- test_score_normalization()
- test_final_ranking()

# tests/retriever/test_fusion_weights.py
- test_weight_adjustment()
- test_adaptive_weighting()
```

**Integration Tests - 필수**
```python
# tests/retriever/test_fusion_integration.py
- test_fusion_with_real_candidates()
- test_fusion_performance()
```

#### 4.4 retriever.context_builder ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/retriever/test_context_builder.py
- test_context_package_creation()
- test_chunk_deduplication()
- test_token_budget_management()
- test_chunk_reordering()

# tests/retriever/test_context_trimming.py
- test_trim_to_token_limit()
- test_preserve_important_chunks()
```

**Integration Tests - 필수**
```python
# tests/retriever/test_context_builder_integration.py
- test_build_context_from_ranked_results()
- test_context_with_repomap_hierarchy()
```

#### 4.5 retriever.service ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/retriever/test_retriever_service.py
- test_service_initialization()
- test_service_query_handling()
- test_service_error_handling()
```

**Integration Tests - 필수**
```python
# tests/retriever/test_retriever_service_integration.py
- test_end_to_end_retrieval()
- test_service_with_all_indexes()
```

**E2E Tests - 필수**
```python
# tests/integration/test_search_e2e.py
- test_search_for_function_definition()
- test_search_for_feature_implementation()
- test_search_with_natural_language_query()
- test_search_with_error_message()
- test_search_with_code_snippet()
```

---

### 5. Infra Layer (Unit: 40%, Integration: 60%)

Infrastructure는 실제 서비스와의 통합이므로 **integration test가 더 중요합니다**.

#### 5.1 infra.storage (Postgres) ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/infra/test_postgres_store.py
- test_connection_creation()
- test_query_execution()
- test_transaction_handling()
```

**Integration Tests - 필수**
```python
# tests/infra/test_postgres_integration.py
- test_chunk_storage_retrieval()
- test_repomap_storage_retrieval()
- test_concurrent_access()
```

#### 5.2 infra.graph (Kuzu) ⭐⭐⭐ (최우선)

**Unit Tests - 필수**
```python
# tests/infra/test_kuzu.py
- test_kuzu_connection()
- test_graph_query_building()
```

**Integration Tests - 필수**
```python
# tests/infra/test_kuzu_integration.py
- test_graph_storage()
- test_graph_traversal()
- test_complex_graph_queries()
```

#### 5.3 infra.vector (Qdrant) ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/infra/test_qdrant.py
- test_qdrant_client_creation()
- test_collection_creation()
```

**Integration Tests - 필수**
```python
# tests/infra/test_qdrant_integration.py
- test_vector_storage()
- test_vector_search()
- test_hybrid_search()
```

#### 5.4 infra.search (Zoekt) ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/infra/test_zoekt.py
- test_zoekt_client_creation()
- test_query_building()
```

**Integration Tests - 필수**
```python
# tests/infra/test_zoekt_integration.py
- test_indexing()
- test_lexical_search()
- test_regex_search()
```

#### 5.5 infra.cache (Redis) ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/infra/test_redis.py
- test_redis_connection()
- test_cache_set_get()
- test_cache_expiration()
```

**Integration Tests - 선택**
```python
# tests/infra/test_redis_integration.py
- test_cache_invalidation_strategy()
```

#### 5.6 infra.llm (OpenAI) ⭐ (중간 우선순위)

**Unit Tests - 필수**
```python
# tests/infra/test_llm.py
- test_llm_client_creation()
- test_prompt_formatting()
- test_response_parsing()
```

**Integration Tests - 선택**
```python
# tests/infra/test_llm_integration.py
- test_real_llm_call() # 비용이 들므로 선택적
```

---

### 6. Server Layer (Unit: 30%, Integration: 50%, E2E: 20%)

#### 6.1 API Server ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/server/test_api_routes.py
- test_search_endpoint_validation()
- test_graph_endpoint_validation()
- test_error_response_format()
```

**Integration Tests - 필수**
```python
# tests/server/test_api_integration.py
- test_search_api_with_real_db()
- test_graph_api_with_real_db()
```

**E2E Tests - 필수**
```python
# tests/server/test_api_e2e.py
- test_full_search_flow()
- test_full_graph_query_flow()
```

#### 6.2 MCP Server ⭐⭐ (높은 우선순위)

**Unit Tests - 필수**
```python
# tests/server/test_mcp_handlers.py
- test_get_chunk_handler()
- test_search_chunks_handler()
- test_get_callers_handler()
- test_get_callees_handler()
```

**Integration Tests - 필수**
```python
# tests/server/test_mcp_integration.py
- test_mcp_server_startup()
- test_mcp_handler_execution()
```

---

## 테스트 우선순위

### P0 (최우선 - 반드시 구현)
1. **foundation.parsing** - 모든 기능의 기초
2. **foundation.ir** - 핵심 데이터 모델
3. **index.lexical** - 기본 검색 기능
4. **index.vector** - 의미 기반 검색
5. **retriever.intent** - 쿼리 라우팅
6. **retriever.context_builder** - 최종 결과 생성
7. **infra.storage (Postgres)** - 데이터 영속성
8. **integration/test_search_e2e.py** - 전체 플로우 검증

### P1 (높은 우선순위)
1. **foundation.graph** - 코드 관계 추적
2. **foundation.chunk** - 청킹 전략
3. **repomap.builder** - 프로젝트 구조
4. **repomap.pagerank** - 중요도 계산
5. **index.symbol** - 심볼 검색
6. **retriever.multi_index** - 병렬 검색
7. **retriever.fusion** - 스코어 통합
8. **infra.graph (Kuzu)** - 그래프 저장소

### P2 (중간 우선순위)
1. **foundation.dfg** - 데이터 플로우
2. **repomap.summarizer** - 요약 생성
3. **index.fuzzy** - 퍼지 검색
4. **index.domain_meta** - 문서 인덱싱
5. **infra.cache (Redis)** - 캐싱
6. **server layers** - API 엔드포인트

### P3 (낮은 우선순위)
1. **index.runtime** - 런타임 정보 (실험적)
2. **retriever.graph_runtime_expansion** - 고급 확장
3. **advanced integration tests** - 성능/부하 테스트

---

## 실행 전략

### 1. 로컬 개발 환경

**빠른 피드백 루프 (Unit Tests만)**
```bash
# 기본: Unit tests만 실행 (2-5초)
pytest

# 특정 레이어만
pytest tests/foundation/

# 특정 파일만
pytest tests/foundation/test_python_generator_basic.py
```

**전체 테스트 (Unit + Integration)**
```bash
# Integration tests 포함 (30초-1분)
pytest -m "unit or integration"

# 모든 테스트
pytest -m ""
```

### 2. CI/CD 파이프라인

**Pull Request 체크 (빠름)**
```yaml
# .github/workflows/pr-check.yml
- name: Run unit tests
  run: pytest -m "unit" --cov=src --cov-fail-under=70

- name: Run critical integration tests
  run: pytest -m "integration" tests/foundation/ tests/index/
```

**Main 브랜치 머지 후 (느림)**
```yaml
# .github/workflows/main.yml
- name: Run all tests
  run: pytest -m "" --cov=src --cov-fail-under=80

- name: Run E2E tests
  run: pytest -m "scenario"
```

### 3. Pre-commit Hook

```bash
# .pre-commit-config.yaml에 추가
- id: pytest-quick
  name: pytest-quick
  entry: pytest -m "unit" --co -q  # 빠른 체크만
  language: system
  pass_filenames: false
```

---

## 커버리지 목표

### 레이어별 커버리지 목표

| Layer | Unit Test Coverage | Integration Test Coverage | Total Coverage |
|-------|-------------------|---------------------------|----------------|
| foundation | 85% | 10% | **95%** |
| repomap | 80% | 15% | **95%** |
| index | 70% | 25% | **95%** |
| retriever | 75% | 20% | **95%** |
| infra | 60% | 35% | **95%** |
| server | 70% | 25% | **95%** |

### 전체 프로젝트 목표

- **Phase 1 (MVP)**: 60% 전체 커버리지
- **Phase 2 (Production)**: 80% 전체 커버리지
- **Phase 3 (Mature)**: 90% 전체 커버리지

---

## 테스트 작성 가이드라인

### 1. Unit Test 작성 규칙

```python
# Good: 빠르고, 독립적이며, 명확함
def test_function_ir_generation():
    # Given
    source = "def foo(): pass"
    parser = FakePythonParser()
    generator = PythonGenerator()

    # When
    ir_nodes = generator.generate(parser.parse(source))

    # Then
    assert len(ir_nodes) == 1
    assert ir_nodes[0].type == "FunctionLike"
    assert ir_nodes[0].name == "foo"

# Bad: 외부 의존성, 느림
def test_function_ir_generation_bad():
    # DB에 연결하고 실제 파일을 읽음 - Unit test에서 하면 안됨!
    db = connect_to_postgres()
    source = open("/path/to/real/file.py").read()
    ...
```

### 2. Integration Test 작성 규칙

```python
# Good: 실제 서비스와 통합, 하지만 범위는 제한적
@pytest.mark.integration
def test_chunk_storage_retrieval(postgres_container):
    # Given
    store = PostgresChunkStore(postgres_container.get_connection())
    chunk = LeafChunk(id="test", content="test content")

    # When
    store.save(chunk)
    retrieved = store.get(chunk.id)

    # Then
    assert retrieved.id == chunk.id
    assert retrieved.content == chunk.content
```

### 3. E2E Test 작성 규칙

```python
# Good: 전체 플로우, 사용자 시나리오
@pytest.mark.scenario
def test_search_for_function_definition(test_client):
    # Given: 실제 프로젝트 인덱싱됨

    # When: 사용자가 검색
    response = test_client.post("/search", json={
        "query": "authentication function",
        "type": "code_search"
    })

    # Then: 올바른 결과 반환
    assert response.status_code == 200
    results = response.json()["results"]
    assert any("authenticate" in r["content"] for r in results)
```

### 4. Fake/Mock 사용 규칙

```python
# tests/fakes/fake_llm.py
class FakeLLM:
    """Unit test용 Fake LLM - 실제 API 호출 없이 고정 응답 반환"""

    def generate(self, prompt: str) -> str:
        return "Mock LLM response"

# tests/infra/test_llm.py
def test_llm_client():
    llm = FakeLLM()  # Unit test에서는 Fake 사용
    result = llm.generate("test prompt")
    assert result == "Mock LLM response"

# tests/infra/test_llm_integration.py
@pytest.mark.integration
def test_llm_real_call():
    llm = OpenAILLM(api_key=os.getenv("OPENAI_API_KEY"))  # Integration test에서는 실제 사용
    result = llm.generate("test prompt")
    assert len(result) > 0
```

---

## 다음 단계

1. **Phase 1: P0 테스트 구현** (1-2주)
   - foundation.parsing, foundation.ir
   - index.lexical, index.vector
   - retriever.intent, retriever.context_builder
   - E2E: test_search_e2e.py

2. **Phase 2: P1 테스트 구현** (2-3주)
   - foundation.graph, foundation.chunk
   - repomap.builder, repomap.pagerank
   - index.symbol, retriever.fusion

3. **Phase 3: P2/P3 테스트 구현** (2-3주)
   - 나머지 테스트 완성
   - 커버리지 80% 달성
   - 성능 테스트 추가

---

## 참고 문서

- [pytest.ini](../../pytest.ini) - 테스트 설정
- [conftest.py](../../tests/conftest.py) - 공통 fixture
- [LAYERING_SPEC.md](../../_docs/specification/platform/LAYERING_SPEC.md) - 레이어 의존성
- [TEST_RULES.md](../../_docs/specification/platform/TEST_RULES.md) - 테스트 규칙
