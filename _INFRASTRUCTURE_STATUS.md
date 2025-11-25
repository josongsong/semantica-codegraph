# Infrastructure 구현 완료 현황

## ✅ 완료된 Infrastructure 컴포넌트

### 1. PostgresStore (완전 구현)
**파일**: [src/infra/storage/postgres.py](src/infra/storage/postgres.py)

**기능**:
- ✅ asyncpg 기반 connection pool
- ✅ Lazy initialization (`_ensure_pool()`)
- ✅ 모든 기본 쿼리 메서드 (execute, fetch, fetchrow, fetchval)
- ✅ Health check
- ✅ Async context manager 지원

**사용처**:
- Fuzzy Index (PostgresFuzzyIndex)
- Domain Meta Index (DomainMetaIndex)

**특징**:
- Fuzzy/Domain adapter의 `_ensure_schema()`에서 자동으로 pool 초기화
- min_pool_size=2, max_pool_size=10 기본값

---

### 2. ZoektAdapter (완전 구현)
**파일**: [src/infra/search/zoekt.py](src/infra/search/zoekt.py)

**기능**:
- ✅ httpx.AsyncClient 기반 HTTP 클라이언트
- ✅ async search 메서드
- ✅ Pydantic 모델로 응답 파싱 (ZoektFileMatch, ZoektMatch, etc.)

**사용처**:
- Lexical Index (ZoektLexicalIndex)

**특징**:
- 30초 timeout
- regex/literal query 지원
- repo filter 지원

---

### 3. ChunkStore 구현체 (완전 구현)

#### InMemoryChunkStore
**파일**: [src/foundation/chunk/store.py](src/foundation/chunk/store.py:112-247)

**기능**:
- ✅ In-memory storage (dict + set 기반)
- ✅ file+line → Chunk 매핑 (우선순위: function > class > file)
- ✅ O(1) 중복 체크
- ✅ 완전 동기 인터페이스

**용도**: 테스트 및 개발

#### PostgresChunkStore
**파일**: [src/foundation/chunk/store.py](src/foundation/chunk/store.py:249-610)

**기능**:
- ✅ asyncpg 기반 PostgreSQL 저장소
- ✅ Batch UPSERT (save_chunks)
- ✅ file+line → Chunk 매핑 with SQL optimization
- ✅ Soft delete 지원
- ✅ 완전 async 인터페이스

**필요 인덱스**:
```sql
idx_chunks_file_span: (repo_id, file_path, start_line, end_line)
idx_chunks_repo_snapshot: (repo_id, snapshot_id)
idx_chunks_symbol: (symbol_id)
idx_chunks_content_hash: (repo_id, file_path, content_hash)
```

---

## 🔧 Container 연결 상태

모든 Infrastructure 컴포넌트가 Container에 올바르게 연결됨:

```python
# src/container.py

@cached_property
def postgres(self):
    """PostgreSQL database adapter."""
    from src.infra.storage.postgres import PostgresStore

    return PostgresStore(
        connection_string=settings.database_url,
        min_pool_size=settings.postgres_min_pool_size,
        max_pool_size=settings.postgres_max_pool_size,
    )

@cached_property
def chunk_store(self):
    """Chunk storage (PostgreSQL)."""
    from src.foundation.chunk import InMemoryChunkStore

    return InMemoryChunkStore()
    # TODO: Switch to PostgresChunkStore for production

@cached_property
def lexical_index(self):
    """Lexical search index (Zoekt)."""
    zoekt_adapter = ZoektAdapter(
        host=settings.zoekt_host,
        port=settings.zoekt_port,
    )
    repo_resolver = RepoPathResolver(...)
    return ZoektLexicalIndex(
        zoekt_adapter=zoekt_adapter,
        chunk_store=self.chunk_store,
        repo_resolver=repo_resolver,
    )

@cached_property
def fuzzy_index(self):
    """Fuzzy search index (PostgreSQL trigram)."""
    return PostgresFuzzyIndex(postgres_store=self.postgres)

@cached_property
def domain_index(self):
    """Domain/documentation search index."""
    return DomainMetaIndex(postgres_store=self.postgres)
```

---

## 📊 전체 시스템 구조

```
┌─────────────────────────────────────────────────────────┐
│                   Index Layer (5 Adapters)               │
├─────────────────────────────────────────────────────────┤
│ Lexical  │ Vector  │ Symbol  │ Fuzzy   │ Domain         │
│ (Zoekt)  │(Qdrant) │ (Kuzu)  │(pg_trgm)│ (pg FTS)      │
└────┬─────┴────┬────┴────┬────┴────┬────┴────┬──────────┘
     │          │         │         │         │
     ▼          ▼         ▼         ▼         ▼
┌────────────────────────────────────────────────────────┐
│             Infrastructure Layer                        │
├────────────────────────────────────────────────────────┤
│ ZoektAdapter │ AsyncQdrant │ KuzuDB │ PostgresStore    │
│   (httpx)    │  (qdrant)   │ (kuzu) │  (asyncpg)      │
└──────────────┴─────────────┴────────┴──────────────────┘
```

---

## 🎯 Production 체크리스트

### ✅ 완료
1. PostgresStore 구현 (asyncpg pool)
2. ZoektAdapter 구현 (httpx async)
3. ChunkStore 구현 (In-memory + Postgres)
4. Lazy pool initialization
5. Container 연결

### ⚠️ Production 전 필요 작업

1. **Database Schema Migration**
   - Fuzzy index: `fuzzy_identifiers` 테이블
   - Domain index: `domain_documents` 테이블
   - Chunk store: `chunks` 테이블 + 인덱스

2. **ChunkStore 전환**
   - Container에서 InMemoryChunkStore → PostgresChunkStore
   - Connection string 설정

3. **Health Check 구현**
   - PostgresStore.health_check() 활용
   - Container.health_check() 완성

4. **Graceful Shutdown**
   - Application shutdown시 모든 pool close
   - `await postgres.close()`, `await qdrant.close()` 등

---

## 📝 다음 단계

1. **통합 테스트 작성**
   - 각 adapter별 integration test
   - Full indexing flow test

2. **Database Migration Script**
   - Alembic 또는 raw SQL로 schema 생성

3. **Server Layer 구현**
   - API Server (FastAPI)
   - MCP Server
