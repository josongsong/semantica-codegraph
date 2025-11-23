# Test Rules Specification

**문서 목적:**
Semantica 플랫폼 전체에 적용되는 테스트 계층 및 품질 기준을 강제한다.
모든 레포(codegraph 포함)는 이 스펙을 **MUST** 준수해야 한다.

**범위:**
- Unit/Integration/Scenario 3단 테스트 계층 정의
- Mocking/Fake 구현 규칙
- Golden Test 관리 정책
- Coverage 최소 기준
- CI 품질 게이트

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 테스트 계층 구조 (MUST)

Semantica는 **3단 테스트 계층**을 mandatory로 사용한다.

### 1.1 Unit Tests
**목적:** Core 로직의 정확성 검증
**범위:** Core domain, parser, chunking, graph logic, fallback, config override

**MUST:**
- 외부 IO를 사용하지 않는다
- 모든 Port는 Fake/Mock 구현을 사용한다
- 1초 이내 실행 완료한다
- GIVEN-WHEN-THEN 구조로 작성한다

**필수 테스트 영역:**
- Chunking 알고리즘
- Parser 트리 변환
- Graph edge 생성 규칙
- Hybrid scoring 로직
- Fallback level 계산
- Config + RepoConfig overlay 로직

**마커:** `@pytest.mark.unit`

---

### 1.2 Integration Tests
**목적:** Service + Adapter + DB end-to-end 연결 검증
**범위:** 전체 파이프라인 (indexing → search → graph)

**MUST:**
- `container.py` 전역 싱글톤 인스턴스를 사용한다
- `docker-compose.test.yml` 기반 실제 DB 환경을 사용한다
- 테스트 간 상태를 공유하지 않는다
- 각 테스트는 독립적으로 실행 가능해야 한다
- `clean_db` fixture로 테스트 전후 DB를 정리한다

**MUST NOT:**
- `Container()` 새 인스턴스를 생성하지 않는다
- 테스트에서 직접 Adapter/Service를 생성하지 않는다
- Mock을 사용하지 않는다 (실제 DB 사용)

**필수 경로:**
- IndexingService 전체 파이프라인
- SearchService hybrid search
- GraphService multi-hop traversal
- LLMProvider mocking 기반 semantic alignment

**마커:** `@pytest.mark.integration`

---

### 1.3 Scenario / Golden Tests
**목적:** 검색 품질 회귀 방지
**범위:** 검색 결과 순서/identity strict match

**MUST:**
- Golden 파일(JSON) 기반으로 테스트한다
- 순서(order) strict match를 검증한다
- Symbol-level / Graph-level / Hybrid-level 각각 커버한다
- Score 값이 아닌 identity/file/line만 검증한다

**필수 시나리오 세트:**
- symbol_level: 10개
- graph_dependency: 10개
- semantic_vector: 10개
- hybrid: 10개
- call/import/override chain scenarios

**Golden 파일 위치:** `tests/scenarios/*.json`

**마커:** `@pytest.mark.scenario`

---

## 2. 디렉터리 구조 (MUST)

```
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── core/                    # Unit tests (Core layer)
│   ├── __init__.py
│   └── test_*.py
├── infra/                   # Unit tests (Infra layer)
│   ├── __init__.py
│   └── test_*.py
├── integration/             # Integration tests
│   ├── __init__.py
│   └── test_*.py
├── scenarios/               # Golden tests
│   ├── __init__.py
│   ├── *.json              # Golden data
│   └── test_golden.py
└── fakes/                   # Fake implementations
    ├── __init__.py
    ├── fake_vector.py
    ├── fake_graph.py
    ├── fake_relational.py
    ├── fake_lexical.py
    ├── fake_git.py
    └── fake_llm.py
```

**MUST NOT:** E2E 테스트를 `tests/core/` 폴더에 배치하지 않는다.

---

## 3. 네이밍 규칙 (MUST)

### 3.1 파일 이름
**MUST:** `test_<module>.py` 형식을 사용한다.

```
test_chunker.py
test_graph_service.py
test_search_hybrid.py
```

### 3.2 테스트 함수 이름
**MUST:** `test_<method>_<behavior>_<case>()` 형식을 사용한다.

```python
def test_chunker_splits_large_function():
    pass

def test_graph_service_multihop_calls():
    pass

def test_search_hybrid_combines_lexical_and_vector():
    pass
```

### 3.3 Golden 파일 이름
**MUST:** `tests/scenarios/<scenario_name>.json` 형식을 사용한다.

```
symbol_search_basic.json
graph_dependency_chain.json
hybrid_ranking_complex.json
```

---

## 4. Mocking 규칙 (MUST)

### 4.1 Unit Test Mocking
**MUST:** 모든 Port는 Fake/Mock 구현을 사용한다.
**MUST:** Fake 구현은 `tests/fakes/` 폴더에 배치한다.
**MUST:** Behavior-driven mocking을 사용한다 (단순 return 값 설정 금지).
**MUST NOT:** 외부 DB/네트워크에 접근하지 않는다.

**Port → Fake 매핑:**
| Port | Fake |
|------|------|
| VectorStorePort | FakeVectorStore |
| GraphStorePort | FakeGraphStore |
| RelationalStorePort | FakeRelationalStore |
| LexicalSearchPort | FakeLexicalSearch |
| GitProviderPort | FakeGitProvider |
| LLMProviderPort | FakeLLMProvider |

**예시:**
```python
@pytest.mark.unit
def test_vector_search(fake_vector, fake_llm):
    # GIVEN
    fake_vector.upsert("collection", [{
        "id": "doc1",
        "vector": fake_llm.embed("Python function"),
        "payload": {"file": "test.py"},
    }])

    # WHEN
    query_vector = fake_llm.embed("Python")
    results = fake_vector.search(
        collection_name="collection",
        query_vector=query_vector,
        limit=10,
    )

    # THEN
    assert len(results) == 1
    assert results[0]["id"] == "doc1"
```

### 4.2 Behavior-Driven Mocking 원칙
**MUST:** Fake 구현은 실제 동작을 시뮬레이션한다.
**MUST NOT:** 단순 return 값만 설정하지 않는다.

**예시:**
```python
# ✅ MUST - Behavior-driven
class FakeVectorStore:
    def search(self, collection_name, query_vector, limit=10):
        results = []
        for point_id, vector in self.vectors.items():
            score = self._cosine_similarity(query_vector, vector)
            results.append({"id": point_id, "score": score, ...})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

# ❌ MUST NOT - 단순 return
class FakeVectorStore:
    def search(self, *args, **kwargs):
        return [{"id": "doc1", "score": 0.9}]  # 금지!
```

---

## 5. Integration Test 규칙 (MUST)

### 5.1 Container 사용
**MUST:** `container.py` 전역 싱글톤을 사용한다.
**MUST NOT:** 테스트에서 `Container()` 새 인스턴스를 생성하지 않는다.

```python
# ✅ MUST
from codegraph.container import container

@pytest.mark.integration
def test_search_integration(clean_db):
    search_service = container.search_service
    results = search_service.search("test query")
    assert len(results) > 0
```

```python
# ❌ MUST NOT
from codegraph.container import Container
my_container = Container()  # 금지!
```

### 5.2 테스트 환경
**MUST:** `docker-compose.test.yml`로 ephemeral DB를 실행한다.
**MUST:** 테스트 전용 포트를 사용한다 (본번 DB와 분리).
**MUST:** `tmpfs`를 사용해 ephemeral 스토리지를 제공한다.

**환경 시작/종료:**
```bash
# 시작
docker-compose -f docker-compose.test.yml up -d

# 테스트 실행
pytest -m integration

# 종료 및 정리
docker-compose -f docker-compose.test.yml down -v
```

### 5.3 테스트 독립성
**MUST:** 테스트 간 상태를 공유하지 않는다.
**MUST:** `clean_db` fixture로 각 테스트 전후 DB를 정리한다.
**MUST:** 필요한 repo/index는 setup 단계에서 생성한다.

---

## 6. Scenario / Golden Test 규칙 (MUST)

### 6.1 Golden 파일 스키마
**MUST:** 다음 JSON 스키마를 사용한다.

```json
{
  "query": "router.post handler 찾기",
  "description": "API route handler를 찾는 시나리오",
  "expected_nodes": [
    {
      "symbol": "search_router",
      "file": "src/api/routes.py",
      "line": 42
    }
  ],
  "expected_order": "strict"
}
```

### 6.2 검증 기준
**MUST:** 순서(order) strict match를 검증한다.
**MUST:** node identity, file, line만 검증한다.
**MUST NOT:** score 값을 검증하지 않는다.

```python
@pytest.mark.scenario
def test_symbol_search_golden(container, load_golden):
    # GIVEN
    golden = load_golden("symbol_search_basic.json")

    # WHEN
    results = search_service.search(golden["query"])

    # THEN
    for i, expected in enumerate(golden["expected_nodes"]):
        assert results[i]["symbol"] == expected["symbol"]
        assert results[i]["file"] == expected["file"]
        assert results[i]["line"] == expected["line"]
```

### 6.3 Golden 업데이트 정책
**MUST:** 다음 상황에서 golden 파일을 업데이트한다:
- Chunking 전략 변경
- Graph edge 추출 규칙 변경
- Hybrid scoring weight 변경
- Embedding/reranker 변경
- Parser/LSP 개선 적용

**MUST:** Golden 변경 시 diff를 반드시 리뷰한다.
**MUST NOT:** Golden 파일을 수동 편집하지 않는다 (자동 생성만 허용).

---

## 7. Coverage 규칙 (MUST)

### 7.1 최소 Coverage 기준
**MUST:** 다음 Coverage 기준을 충족한다:

| 영역 | 최소 Coverage |
|------|---------------|
| 전체 | 60% |
| core/services | 80% |
| parsing/chunking/graph | 90% |
| infra | 예외 가능 |

**확인 명령:**
```bash
pytest --cov=codegraph --cov-report=html --cov-fail-under=60
```

### 7.2 Coverage 제외 패턴
**허용:** 다음 패턴은 coverage에서 제외 가능:
- `pragma: no cover`
- `def __repr__`
- `raise AssertionError`
- `raise NotImplementedError`
- `if __name__ == .__main__.:
- `if TYPE_CHECKING:`
- `@abstractmethod`

---

## 8. CI 규칙 (MUST)

### 8.1 CI 품질 게이트
**MUST:** CI에서 다음을 실행하고 통과해야 한다:

```bash
# 1. Lint & Format
ruff check codegraph tests
mypy codegraph
black --check codegraph tests

# 2. Unit Tests
pytest -m unit --cov-fail-under=60

# 3. Integration Tests (main branch only)
docker-compose -f docker-compose.test.yml up -d
pytest -m integration
docker-compose -f docker-compose.test.yml down -v

# 4. Scenario Tests
pytest -m scenario
```

### 8.2 PR 승인 기준
**MUST:** PR 승인 전 다음을 확인한다:
- 모든 Unit Test 통과
- Coverage 60% 이상
- Lint/Format 통과
- Golden Test 변경 시 diff 리뷰 완료

---

## 9. 테스트 작성 규칙 (MUST)

### 9.1 필수 규칙
**MUST:** 새 서비스/기능 구현 시 최소 1개 unit test를 작성한다.
**MUST:** 검색/그래프/청킹 로직 수정 시 관련 golden test를 업데이트한다.
**MUST:** Mocking은 ports 레벨에서만 수행한다 (infra mocking 금지).
**MUST:** 테스트 하나에 하나의 behavior만 검증한다.
**MUST:** GIVEN-WHEN-THEN 구조를 사용한다.

### 9.2 금지 규칙
**MUST NOT:** 테스트에서 직접 인스턴스를 생성하지 않는다.
**MUST NOT:** `Container()` 새 인스턴스를 생성하지 않는다.
**MUST NOT:** Core에서 infra를 import하지 않는다.
**MUST NOT:** Golden 파일을 수동 편집하지 않는다.

**예시:**
```python
# ❌ MUST NOT - 직접 인스턴스 생성
from codegraph.core.services import SearchService
service = SearchService()  # 금지!

# ❌ MUST NOT - Container 새 인스턴스
from codegraph.container import Container
my_container = Container()  # 금지!
```

---

## 10. Anti-Patterns (금지)

**MUST NOT:**
- 테스트에서 `SearchService()` 직접 생성
- GraphStore 없이 그래프 검색 테스트
- In-memory dict로 vector 검색 흉내
- Golden 파일 수동 편집
- 테스트에서 container 새 인스턴스 생성
- Core에서 infra import
- Hybrid ranking을 fuzzy matching으로 대체
- E2E 테스트를 core 폴더에 배치

---

## 11. Fixtures (참조)

### 11.1 Unit Test Fixtures
```python
@pytest.fixture
def fake_vector():
    store = FakeVectorStore()
    store.create_collection("test_collection", vector_size=1536)
    yield store

@pytest.fixture
def fake_llm():
    return FakeLLMProvider(embedding_dim=1536)
```

### 11.2 Integration Test Fixtures
```python
@pytest.fixture(scope="session")
def container():
    from codegraph.container import container
    return container

@pytest.fixture
def clean_db():
    # Setup: DB 초기화
    yield
    # Teardown: DB 정리
```

### 11.3 Scenario Test Fixtures
```python
@pytest.fixture
def load_golden():
    def _load(filename):
        with open(f"tests/scenarios/{filename}") as f:
            return json.load(f)
    return _load
```

---

## 12. 참고 자료

- [DI Specification](./DI_SPEC.md)
- [Layering Specification](./LAYERING_SPEC.md)
- [Test Guide (standards)](../../standards/testing/UNIT_TEST_PATTERNS.md)
- [Golden Tests (standards)](../../standards/testing/GOLDEN_TESTS.md)
- [TEST_GUIDE.md (루트)](../../TEST_GUIDE.md)
