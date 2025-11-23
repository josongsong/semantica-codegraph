# Dependency Injection 가이드

Semantica Codegraph의 의존성 관리 패턴 및 사용 규칙

## 핵심 원칙

> **"모든 의존성을 container.py 하나에서 @cached_property 기반 Lazy Singleton으로 생성하고, API/MCP/CLI/Agent는 해당 container에서 서비스/어댑터를 가져다 쓰며, Core는 container/infra/settings에 직접 의존하지 않는다."**

## 아키텍처 레이어

```
┌─────────────────────────────────────────┐
│   Interfaces (API/MCP/CLI/Agent)        │
│   - container만 import                   │
│   - container.service 사용               │
└──────────────┬──────────────────────────┘
               │ uses
┌──────────────▼──────────────────────────┐
│   Container (container.py)              │
│   - @cached_property로 lazy singleton   │
│   - Settings + Adapters + Services      │
└──────────────┬──────────────────────────┘
               │ creates
         ┌─────┴─────┐
         │           │
    ┌────▼───┐  ┌───▼────┐
    │ Core   │  │ Infra  │
    │Services│  │Adapters│
    └────────┘  └────────┘
         │
         │ uses (ports only)
    ┌────▼───┐
    │ Ports  │
    └────────┘
```

## DI 패턴

### 1. Settings (Eager Loading)

```python
# codegraph/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    vector_host: str = "localhost"
    vector_port: int = 6333
    # ...

settings = Settings()  # 즉시 생성 (eager)
```

### 2. Container (Lazy Singleton)

```python
# codegraph/container.py
from functools import cached_property
from .config import Settings

settings = Settings()

class Container:
    @cached_property
    def qdrant(self):
        """Lazy import + lazy initialization"""
        from .infra.vector.qdrant import QdrantAdapter
        return QdrantAdapter(
            host=settings.vector_host,
            port=settings.vector_port,
        )

    @cached_property
    def search_service(self):
        from .core.services.search_service import SearchService
        return SearchService(
            vector_store=self.qdrant,  # lazy 체인
            llm_provider=self.llm,
        )

container = Container()
```

### 3. Core Services (Constructor Injection)

```python
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

    def search(self, query: str):
        # container, settings, infra를 직접 import하지 않음
        embedding = self.llm_provider.embed(query)
        return self.vector_store.search(embedding)
```

## 사용 규칙

### ✅ DO: Container 사용

#### API 엔드포인트

```python
# apps/api_server/routes/search.py
from codegraph.container import container

@app.get("/search")
def search(q: str):
    return container.search_service.search(q)
```

#### MCP Tool

```python
# apps/mcp_server/tools/search_tool.py
from codegraph.container import container

class HybridSearchTool:
    def __init__(self):
        self.search_service = container.search_service

    def run(self, query: str):
        return self.search_service.search(query)
```

#### CLI

```python
# apps/cli/commands/index.py
from codegraph.container import container

def reindex_command(repo_path: str):
    container.indexing_service.reindex_repo(repo_path)
```

#### Agent

```python
# apps/agents/code_agent.py
from codegraph.container import container

class CodeAgent:
    def __init__(self):
        self.search = container.search_service
        self.graph = container.graph_service

    def analyze(self, query: str):
        results = self.search.search(query)
        graph = self.graph.get_call_chain(results[0])
        return self.synthesize(results, graph)
```

### ❌ DON'T: Anti-Patterns

#### 직접 인스턴스 생성 (금지)

```python
# ❌ 잘못된 예시
from codegraph.core.services import SearchService
from codegraph.infra.vector import QdrantAdapter

# 이렇게 하면 안 됨!
qdrant = QdrantAdapter(host="localhost", port=6333)
service = SearchService(vector_store=qdrant, ...)
```

#### Container 재생성 (금지)

```python
# ❌ 잘못된 예시
from codegraph.container import Container

# 이렇게 하면 안 됨! (singleton 패턴 위반)
my_container = Container()
```

#### Core에서 Infra Import (금지)

```python
# ❌ 잘못된 예시
# codegraph/core/services/search_service.py
from codegraph.infra.vector import QdrantAdapter  # 금지!
from codegraph.container import container  # 금지!
from codegraph.config import settings  # 금지!

class SearchService:
    def __init__(self):
        self.qdrant = QdrantAdapter(...)  # 금지!
```

## Lazy Loading 정책

### Lazy Loading 대상 (최초 접근 시 생성)

- ✅ Qdrant client
- ✅ Kùzu graph store
- ✅ Zoekt client
- ✅ Postgres connection
- ✅ Redis client
- ✅ Git provider
- ✅ LLM provider
- ✅ Parser / Chunker
- ✅ GraphRAG
- ✅ 모든 heavy compute / IO dependency

### Eager Loading 대상 (즉시 생성)

- ✅ Settings
- ✅ Logging 초기화
- ✅ 환경 검증

## Available Services & Adapters

### Adapters

| Property | Type | Description |
|----------|------|-------------|
| `container.qdrant` | QdrantAdapter | 벡터 검색 |
| `container.kuzu` | KuzuGraphStore | 그래프 DB (TODO) |
| `container.postgres` | PostgresAdapter | 관계형 DB |
| `container.redis` | RedisAdapter | 캐시/세션 (TODO) |
| `container.zoekt` | ZoektAdapter | Lexical 검색 (TODO) |
| `container.git` | GitCLIAdapter | Git 작업 |
| `container.llm` | OpenAIAdapter | LLM 호출 |

### Services

| Property | Type | Description |
|----------|------|-------------|
| `container.search_service` | SearchService | 하이브리드 검색 |
| `container.indexing_service` | IndexingService | 인덱싱 파이프라인 |
| `container.graph_service` | GraphService | 그래프 쿼리 |
| `container.git_service` | GitService | Git 작업 |

### Backward Compatibility Aliases

기존 코드 호환성을 위한 별칭:

```python
container.vector_store    # = container.qdrant
container.graph_store     # = container.kuzu
container.relational_store # = container.postgres
container.lexical_search  # = container.zoekt
container.git_provider    # = container.git
container.llm_provider    # = container.llm
```

## Testing

### Mock 사용

```python
# tests/test_search.py
from unittest.mock import Mock
from codegraph.core.services import SearchService

def test_search():
    # Mock adapter 생성
    mock_vector = Mock()
    mock_llm = Mock()

    # Constructor injection으로 mock 주입
    service = SearchService(
        vector_store=mock_vector,
        llm_provider=mock_llm,
    )

    # 테스트 실행
    service.search("query")

    # Mock 검증
    mock_llm.embed.assert_called_once()
    mock_vector.search.assert_called_once()
```

### Integration Test

```python
# tests/integration/test_container.py
from codegraph.container import container

def test_container_lazy_loading():
    # 아직 생성되지 않음
    assert "qdrant" not in container.__dict__

    # 최초 접근 시 생성
    qdrant = container.qdrant
    assert qdrant is not None

    # 같은 인스턴스 반환
    assert container.qdrant is qdrant
```

## Troubleshooting

### 순환 import 문제

```python
# ❌ 문제
# container.py에서 모든 import를 최상단에 하면 순환 import 발생 가능

# ✅ 해결
# @cached_property 내부에서 lazy import 사용
@cached_property
def qdrant(self):
    from .infra.vector.qdrant import QdrantAdapter  # 여기서 import
    return QdrantAdapter(...)
```

### Settings 값이 반영되지 않음

```python
# ❌ 문제
# Settings는 모듈 로드 시 한 번만 생성됨
# .env 파일 변경 후에도 재시작 필요

# ✅ 해결
# 개발 환경: API 서버 재시작
make docker-restart-api

# 또는 환경 변수로 직접 설정
export SEMANTICA_VECTOR_HOST=new-host
```

### 어댑터가 None

```python
# ❌ 문제
container.redis  # NotImplementedError

# ✅ 확인
# container.py에서 TODO 확인
# 구현되지 않은 어댑터는 NotImplementedError 발생

# ✅ 해결
# 해당 어댑터 구현 후 container.py 수정
```

## 확장 전략

### 새로운 Adapter 추가

```python
# 1. Infra 레이어에 adapter 구현
# codegraph/infra/cache/redis.py
class RedisAdapter:
    def __init__(self, host: str, port: int, password: str):
        # ...

# 2. Container에 @cached_property 추가
# codegraph/container.py
@cached_property
def redis(self):
    from .infra.cache.redis import RedisAdapter
    return RedisAdapter(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
    )

# 3. 사용
from codegraph.container import container
cache = container.redis
```

### 새로운 Service 추가

```python
# 1. Core 레이어에 service 구현
# codegraph/core/services/cache_service.py
class CacheService:
    def __init__(self, redis_adapter, settings):
        self.redis = redis_adapter
        self.settings = settings

# 2. Container에 @cached_property 추가
@cached_property
def cache_service(self):
    from .core.services.cache_service import CacheService
    return CacheService(
        redis_adapter=self.redis,
        settings=settings,
    )
```

### Workspace 단위 Container (Advanced)

```python
# Multi-repo, multi-session 환경
from codegraph.container import Container
from codegraph.config import Settings

workspace_settings = Settings(
    vector_collection="workspace_123",
    kuzu_db_path="./data/workspace_123/kuzu",
)

workspace_container = Container()
# workspace_settings를 사용하도록 확장 필요
```

## 체크리스트

구현 시 다음을 확인하세요:

- [ ] Container에서만 의존성 생성
- [ ] @cached_property 사용
- [ ] Lazy import 패턴 적용
- [ ] Core에서 container/infra import 금지
- [ ] Constructor injection만 사용
- [ ] 전역 container 인스턴스 사용
- [ ] Settings는 eager loading
- [ ] Heavy dependency는 lazy loading

## 참고 자료

- [DI 규칙 문서](.docs/northstar/_B_10_di_rule)
- [Container 소스](codegraph/container.py)
- [Config 소스](codegraph/config.py)
