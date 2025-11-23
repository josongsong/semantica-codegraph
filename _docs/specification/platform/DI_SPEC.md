# Dependency Injection Specification

**문서 목적:**
Semantica 플랫폼 전체에 적용되는 의존성 주입(DI) 패턴 및 생성 규칙을 강제한다.
모든 레포(codegraph 포함)는 이 스펙을 **MUST** 준수해야 한다.

**범위:**
- DI 컨테이너 구조 및 생성 방식
- 레이어별 의존성 접근 규칙
- Settings 및 Adapter/Service 초기화 정책
- 테스트 환경 DI 전략

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 핵심 원칙 (MUST)

### 1.1 Container 유일성
**MUST:** 모든 의존성은 단일 `container.py` 파일에서만 생성한다.
**MUST:** Container는 모듈 레벨 전역 싱글톤으로 존재한다.
**MUST NOT:** 애플리케이션 코드에서 `Container()` 인스턴스를 새로 생성하지 않는다.

```python
# codegraph/container.py
from functools import cached_property

class Container:
    @cached_property
    def search_service(self):
        from .core.services.search_service import SearchService
        return SearchService(
            vector_store=self.qdrant,
            llm_provider=self.llm,
        )

# 모듈 레벨 전역 싱글톤
container = Container()
```

### 1.2 Lazy Singleton 패턴
**MUST:** 모든 Adapter/Service는 `@cached_property`를 사용해 Lazy Singleton으로 생성한다.
**MUST:** 최초 접근 시에만 인스턴스화되고, 이후 동일 인스턴스를 반환한다.
**MUST:** Heavy I/O dependency(DB client, LLM provider 등)는 반드시 lazy loading한다.

**예외:**
- `Settings`는 eager loading (모듈 로드 시 즉시 생성)
- Logging 초기화, 환경 검증은 eager loading 허용

### 1.3 Lazy Import
**MUST:** Container 내부에서 `@cached_property` 메서드 안에서만 import 수행한다.
**MUST NOT:** Container 파일 최상단에서 모든 adapter/service를 import하지 않는다.
**이유:** 순환 import 방지 및 lazy loading 보장

```python
# ✅ MUST
@cached_property
def qdrant(self):
    from .infra.vector.qdrant import QdrantAdapter  # 여기서 import
    return QdrantAdapter(...)

# ❌ MUST NOT
from .infra.vector.qdrant import QdrantAdapter  # 파일 최상단 import 금지
```

---

## 2. 레이어별 의존성 접근 규칙 (MUST)

### 2.1 Interfaces (API/MCP/CLI/Agent)
**MUST:** `from codegraph.container import container` 만 import한다.
**MUST:** container에서 필요한 service/adapter를 가져다 사용한다.
**MUST NOT:** Core/Infra 레이어를 직접 import하지 않는다.

```python
# ✅ MUST
from codegraph.container import container

@app.get("/search")
def search(q: str):
    return container.search_service.search(q)
```

### 2.2 Core Services
**MUST:** Constructor Injection 패턴만 사용한다.
**MUST:** 의존성은 Port 인터페이스 타입으로 받는다.
**MUST NOT:** Core에서 `container`, `settings`, `infra` 모듈을 직접 import하지 않는다.
**MUST NOT:** Core에서 인스턴스를 직접 생성하지 않는다.

```python
# ✅ MUST
# codegraph/core/services/search_service.py
from ..ports import VectorStorePort, LLMProviderPort

class SearchService:
    def __init__(
        self,
        vector_store: VectorStorePort,
        llm_provider: LLMProviderPort,
    ):
        self.vector_store = vector_store
        self.llm_provider = llm_provider
```

```python
# ❌ MUST NOT
from codegraph.infra.vector import QdrantAdapter  # 금지!
from codegraph.container import container  # 금지!
from codegraph.config import settings  # 금지!
```

### 2.3 Infra Adapters
**MUST:** Settings에서 필요한 config 값을 Constructor로 받는다.
**MUST:** Port 인터페이스를 구현한다.
**MUST NOT:** Container를 직접 참조하지 않는다.

---

## 3. Settings 관리 (MUST)

### 3.1 Settings 정의
**MUST:** `codegraph/config.py`에서 `pydantic_settings.BaseSettings` 기반으로 정의한다.
**MUST:** 모듈 레벨에서 즉시 생성한다 (eager loading).
**MUST:** 환경 변수 prefix는 `SEMANTICA_`를 사용한다.

```python
# codegraph/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    vector_host: str = "localhost"
    vector_port: int = 6333
    # ...

settings = Settings()  # Eager loading
```

### 3.2 Settings 사용
**MUST:** Container에서만 settings를 참조한다.
**MUST NOT:** Service/Adapter에서 직접 settings를 import하지 않는다.
**예외:** Infra adapter는 constructor parameter로 받은 config 값만 사용

---

## 4. Available Services & Adapters (참조)

Container에서 제공하는 표준 서비스/어댑터 목록:

### Adapters
| Property | Type | 설명 |
|----------|------|------|
| `container.qdrant` | QdrantAdapter | 벡터 검색 |
| `container.kuzu` | KuzuGraphStore | 그래프 DB |
| `container.postgres` | PostgresAdapter | 관계형 DB |
| `container.redis` | RedisAdapter | 캐시/세션 |
| `container.zoekt` | ZoektAdapter | Lexical 검색 |
| `container.git` | GitCLIAdapter | Git 작업 |
| `container.llm` | OpenAIAdapter | LLM 호출 |

### Services
| Property | Type | 설명 |
|----------|------|------|
| `container.search_service` | SearchService | 하이브리드 검색 |
| `container.indexing_service` | IndexingService | 인덱싱 파이프라인 |
| `container.graph_service` | GraphService | 그래프 쿼리 |
| `container.git_service` | GitService | Git 작업 |

---

## 5. 테스트 환경 DI (MUST)

### 5.1 Unit Test
**MUST:** Mock/Fake 구현을 사용해 Port를 주입한다.
**MUST:** Constructor Injection으로 mock을 전달한다.
**MUST NOT:** Container를 사용하지 않는다.

```python
# ✅ MUST
from unittest.mock import Mock
from codegraph.core.services import SearchService

def test_search():
    mock_vector = Mock()
    mock_llm = Mock()

    service = SearchService(
        vector_store=mock_vector,
        llm_provider=mock_llm,
    )

    service.search("query")
    mock_llm.embed.assert_called_once()
```

### 5.2 Integration Test
**MUST:** 전역 `container` 인스턴스를 사용한다.
**MUST:** `docker-compose.test.yml` 환경에서 실행한다.
**MUST NOT:** 테스트에서 `Container()` 새 인스턴스를 생성하지 않는다.

```python
# ✅ MUST
from codegraph.container import container

def test_search_integration(clean_db):
    search_service = container.search_service
    results = search_service.search("test query")
    assert len(results) > 0
```

---

## 6. 금지 규칙 (MUST NOT)

### 6.1 직접 인스턴스 생성 금지
**MUST NOT:** 애플리케이션 코드에서 Service/Adapter를 직접 생성하지 않는다.

```python
# ❌ MUST NOT
from codegraph.core.services import SearchService
from codegraph.infra.vector import QdrantAdapter

qdrant = QdrantAdapter(host="localhost", port=6333)
service = SearchService(vector_store=qdrant, ...)
```

### 6.2 Container 재생성 금지
**MUST NOT:** Container 클래스를 직접 인스턴스화하지 않는다.

```python
# ❌ MUST NOT
from codegraph.container import Container
my_container = Container()  # 금지!
```

### 6.3 Core에서 Infra Import 금지
**MUST NOT:** Core 레이어에서 Infra 레이어를 직접 import하지 않는다.

```python
# ❌ MUST NOT - Core Service에서
from codegraph.infra.vector import QdrantAdapter  # 금지!
from codegraph.container import container  # 금지!
```

---

## 7. Lazy Loading 정책 (MUST)

### 7.1 Lazy Loading 대상
**MUST:** 다음 항목은 반드시 lazy loading한다:
- Qdrant client
- Kùzu graph store
- Zoekt client
- Postgres connection
- Redis client
- Git provider
- LLM provider
- Parser / Chunker
- GraphRAG
- 모든 heavy compute / IO dependency

### 7.2 Eager Loading 대상
**허용:** 다음 항목은 eager loading 가능:
- Settings
- Logging 초기화
- 환경 검증

---

## 8. 확장 가이드 (참조)

### 8.1 새 Adapter 추가
1. `codegraph/infra/<category>/<adapter>.py`에 구현
2. Port 인터페이스 구현
3. `container.py`에 `@cached_property` 추가
4. Lazy import 사용

```python
# container.py
@cached_property
def redis(self):
    from .infra.cache.redis import RedisAdapter
    return RedisAdapter(
        host=settings.redis_host,
        port=settings.redis_port,
    )
```

### 8.2 새 Service 추가
1. `codegraph/core/services/<service>.py`에 구현
2. Constructor Injection으로 의존성 정의
3. `container.py`에 `@cached_property` 추가

```python
# container.py
@cached_property
def cache_service(self):
    from .core.services.cache_service import CacheService
    return CacheService(
        redis_adapter=self.redis,
    )
```

---

## 9. Troubleshooting

### 9.1 순환 Import
**문제:** Container 파일 최상단에서 모든 import 수행 시 순환 import 발생
**해결:** `@cached_property` 내부에서 lazy import 사용

### 9.2 Settings 값 미반영
**문제:** `.env` 파일 변경 후에도 값이 반영되지 않음
**해결:** Settings는 모듈 로드 시 한 번만 생성되므로 서버 재시작 필요

### 9.3 Adapter가 None
**문제:** `container.redis` 접근 시 NotImplementedError
**해결:** Container에 해당 adapter @cached_property 구현 확인

---

## 10. 체크리스트

구현 시 다음을 확인하세요:

- [ ] Container에서만 의존성 생성
- [ ] @cached_property 사용
- [ ] Lazy import 패턴 적용
- [ ] Core에서 container/infra import 금지
- [ ] Constructor injection만 사용
- [ ] 전역 container 인스턴스 사용
- [ ] Settings는 eager loading
- [ ] Heavy dependency는 lazy loading

---

## 11. 참고 자료

- [Layering Specification](./LAYERING_SPEC.md)
- [Test Rules](./TEST_RULES.md)
- [Container 구현](../../codegraph/container.py)
- [DI Guide (standards)](../../standards/architecture/DEPENDENCY_GUIDE.md)
