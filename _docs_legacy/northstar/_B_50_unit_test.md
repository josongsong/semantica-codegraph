# Semantica Codegraph – Test Rules (SOTA Version)

**Purpose:**  
Semantica Codegraph 개발 시 테스트 품질을 SOTA 수준으로 유지하기 위한 공식 테스트 규칙이다.  
모든 개발자 및 AI 에이전트는 이 문서의 규칙을 반드시 준수해야 한다.

---

# 1. 테스트 계층 구조

Semantica는 아래 3단 테스트 계층을 mandatory로 사용한다.

## 1-1. Unit Tests  
**목표:** Core 로직의 정확성 검증  
**특징:**  
- Core domain / parser / chunking / fallback / config override 등  
- 외부 IO 없음  
- Ports는 mock/fake 이용  
- 빠른 실행

**필수 테스트 영역:**  
- Chunking 알고리즘  
- Parser 트리 변환  
- Graph edge 생성 규칙  
- Hybrid scoring  
- Fallback level 계산  
- Config + RepoConfig overlay 로직  

---

## 1-2. Integration Tests  
**목표:** Service + Adapter + DB 간 end-to-end 연결 검증  
**특징:**  
- container.py의 lazy singleton 사용  
- Qdrant / Kùzu / Meili / Postgres 실제 기동  
- docker-compose.test.yml 기반 환경 사용  
- indexing → search → graph 흐름 검증

**필수 경로:**  
- IndexingService 전체 파이프라인  
- SearchService hybrid search  
- GraphService multi-hop traversal  
- LLMProvider mocking 기반 semantic alignment  

---

## 1-3. Scenario / Golden Tests  
**목표:** 검색 품질 회귀 방지  
**특징:**  
- 질문 → expected retrieval 세트 유지  
- Symbol-level / Graph-level / Hybrid-level  
- 순서(order) strict match  
- golden 파일(JSON) 기반

**필수 시나리오 세트:**  
- symbol_level: 10  
- graph_dependency: 10  
- semantic_vector: 10  
- hybrid: 10  
- call/import/override chain scenarios  

---

# 2. 테스트 구조 및 네이밍 규칙

## 2-1. 디렉터리
tests/
core/
infra/
interfaces/
scenarios/

shell
Copy code

## 2-2. 파일 이름  
test_<module>.py

shell
Copy code

## 2-3. 테스트 함수 이름  
test_<method><behavior><case>()

markdown
Copy code

예:  
`test_chunker_splits_large_function()`  
`test_graph_service_multihop_calls()`  
`test_search_hybrid_combines_lexical_and_vector()`  

## 2-4. Golden Test 파일 구조  
tests/scenarios/<scenario_name>.json

pgsql
Copy code

JSON 스키마:
```json
{
  "query": "router.post handler 찾기",
  "expected_nodes": [
    { "symbol": "search_router", "file": "...", "line": 42 }
  ]
}
3. Mocking 규칙
3-1. Unit Test Mocking
모든 Ports(XxxPort)는 Fake/Mock 구현 사용

외부 DB/네트워크 접근 금지

Fake 구현은 tests/fakes/ 폴더에 배치

Ports 예:

VectorStorePort → FakeVectorStore

GraphStorePort → FakeGraphStore

RelationalStorePort → FakeRelational

LexicalSearchPort → FakeLexical

GitProvider → FakeGit

LLMProvider → FakeLLM

3-2. Mock 원칙
behavior-driven mocking

단순 return 값 설정 금지

그래프 테스트에서는 minimal viable graph 구조 제공

4. Integration Test 규칙
4-1. container.py 사용
Integration Test는 반드시 container.py lazy 인스턴스를 사용

adapter/service wiring 동일하게 유지

4-2. Test 환경
docker-compose.test.yml

ephemeral DB(Qdrant, Postgres, Meilisearch, Kùzu)

CI에서도 동일 환경 실행

4-3. 독립성
테스트 간 상태 공유 금지

필요한 repo/index는 setup 단계에서 생성

5. Scenario / Golden Test 규칙
5-1. Snapshot 업데이트 정책
아래 상황에서 golden 파일 업데이트 필요:

chunking 전략 변경

graph edge 추출 규칙 변경

hybrid scoring weight 변경

embedding/reranker 변경

parser/LSP 개선 적용

5-2. 검사 기준
순서(order) strict match

node identity/file/line만 검증

score 값은 비교하지 않음

6. Coverage 규칙
전체 커버리지 최소: 60%

core/services/domain: 80%

parsing/chunking/graph logic: 90%

infra adapters는 커버리지 예외 가능

7. CI 규칙
pytest -q → must pass

integration tests(-m integration) → main branch에서 must pass

golden tests → must pass

coverage fail-under=60 적용

lint/format/mypy 반드시 실행

8. 테스트 작성 규칙 (AI + 사람 공통)
새 서비스/기능 구현 시 최소 1개 unit test 필수

검색/그래프/청킹 로직 수정 시 관련 golden test 업데이트 필수

mocking은 ports 레벨에서만 (infra mocking 금지)

테스트 하나에 하나의 behavior만 검증

GIVEN-WHEN-THEN 구조 권장

container.py에서 새 인스턴스 생성 금지

golden snapshot 변경 시 diff를 반드시 리뷰

Settings/RepoConfig override도 독립 테스트 필요

9. Anti-Patterns (금지)
테스트에서 SearchService() 직접 생성

GraphStore 없이 그래프 검색 테스트

in-memory dict로 vector 검색 흉내

golden 파일 수동 편집

test에서 container 새 인스턴스 생성

Core에서 infra import

hybrid ranking을 fuzzy matching으로 대체

E2E 테스트를 core 폴더에 배치

