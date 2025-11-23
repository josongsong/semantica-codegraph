# Repository Structure Specification

**문서 목적:**
Semantica Codegraph 레포지토리의 표준 폴더 구조 및 아키텍처 레이어 정의

**범위:**
- Hexagonal Architecture 기반 디렉터리 구조 MUST
- 레이어별 의존성 규칙 MUST
- 파일/모듈 배치 규칙 MUST

**최종 수정:** 2025-01-23

---

## 1. 아키텍처 원칙 (MUST)

### 1.1 Modern Hexagonal Architecture

Semantica Codegraph는 **Modern Hexagonal Architecture (Clean Architecture)**를 따라야 한다.

**목표:**
- Business Logic (Core)을 External Interfaces (API/MCP)와 분리
- Infrastructure (DB/Git)를 Core로부터 분리
- 테스트 가능성 극대화

### 1.2 의존성 규칙 (Strict MUST)

```
Core.Domain ← Core.Ports ← Core.Services ← Apps (API/MCP)
                                        ← Core.Infra (Adapters)
```

**MUST:**
1. `apps/api_server`, `apps/mcp_server`는 `core/core/services`에 의존 가능
2. `core/infra/*`는 `core/core/ports`를 구현
3. `core/core/*`는 **외부 프레임워크에 의존하지 않음** (표준 라이브러리/Pydantic만)

**MUST NOT:**
- Core는 Infra(어댑터)를 import 금지
- Core는 Apps(API/MCP)를 import 금지
- Core는 외부 프레임워크(FastAPI, SQLAlchemy 등) import 금지

---

## 2. 디렉터리 구조 (MUST)

### 2.1 최상위 구조

```
codegraph/
├── core/                        # Python 패키지 루트 (엔진 + 어댑터 + 인터페이스 헬퍼)
│   ├── core/                    # [Business Logic Layer] Codegraph 엔진
│   ├── infra/                   # [Adapter Layer] Port 구현체
│   ├── interfaces/              # API/MCP 의존성 주입 헬퍼
│   ├── config.py                # 전역 설정 (Pydantic Settings)
│   └── container.py             # DI 컨테이너 (포트↔어댑터 바인딩)
├── apps/                        # [Presentation Layer] 외부 인터페이스 엔트리
│   ├── api_server/              # FastAPI 엔트리포인트 + 라우터
│   └── mcp_server/              # MCP 엔트리포인트 + 핸들러
├── infra/                       # [Ops/DB] 스키마/설정 (코드 어댑터 아님)
├── scripts/                     # 유틸/운영 스크립트
└── tests/                       # 테스트
```

### 2.2 Apps (Interfaces) Layer 구조

```
apps/
├── api_server/
│   ├── main.py                  # FastAPI app 엔트리포인트
│   └── routes/                  # /health, /search, /graph ...
└── mcp_server/
    ├── __init__.py
    └── handlers/                # MCP 핸들러 구현
```

**MUST:**
- API 엔드포인트는 `apps/api_server/routes/`에 배치
- MCP 핸들러는 `apps/mcp_server/handlers/`에 배치
- FastAPI/MCP 의존성 주입 헬퍼는 `core/interfaces/api` 등 공용 인터페이스 헬퍼를 사용

### 2.3 Core Layer 구조

```
core/core/
├── domain/                      # 1) 순수 도메인 모델 (로직 없음)
│   ├── nodes.py                 # BaseNode, Repo/Project/File/Symbol 노드
│   ├── chunks.py                # CanonicalLeafChunk, VectorPayload
│   ├── graph.py                 # RelationshipType, Relationship
│   └── context.py               # GitContext, SecurityContext, RuntimeStats
├── ports/                       # 2) Ports (추상 인터페이스)
│   ├── vector_store.py          # Vector DB 인터페이스
│   ├── graph_store.py           # Graph/관계 저장 인터페이스
│   ├── relational_store.py      # RDB (Node/Chunk 메타) 인터페이스
│   ├── git_provider.py          # Git (diff/log/blame/branch) 인터페이스
│   ├── llm_provider.py          # LLM/Embedding 인터페이스
│   └── lexical_search_port.py   # Meili/Zoekt 등 텍스트 검색 인터페이스
└── services/                    # 3) Application Services (유즈케이스)
    ├── ingestion/               # 파싱 + 청킹 파이프라인
    │   ├── parser.py            # Tree-sitter 기반 파서
    │   └── chunker.py           # 코드 청킹 전략
    ├── indexing_service.py      # 리포/브랜치 인덱싱 유즈케이스
    ├── search_service.py        # Hybrid Code Search + Rerank
    ├── graph_service.py         # GraphRAG 탐색/이웃 찾기
    └── git_service.py           # Git 히스토리/브랜치/PR 뷰
```

**MUST:**
1. `core/core/domain/`: 데이터 구조만 정의 (로직 메서드 금지)
2. `core/core/ports/`: ABC(Abstract Base Class)만 정의 (구현 금지)
3. `core/core/services/`: 비즈니스 로직 흐름 정의 (parsing, indexing, searching)

**MUST NOT:**
- Core 내부에서 FastAPI, SQLAlchemy, Qdrant 등 외부 라이브러리 import 금지

### 2.4 Infra Layer 구조

```
core/infra/                      # Adapter 구현체
├── vector/qdrant.py             # VectorStorePort 구현
├── vector/mock.py               # 테스트용 인메모리 구현
├── storage/postgres.py          # relational_store 구현
├── search/meilisearch.py        # lexical_search_port 구현
├── git/git_cli.py               # git_provider 구현
└── llm/openai.py                # llm_provider 구현

infra/                           # Ops/DB (코드 어댑터 아님)
├── config/                      # compose/env 템플릿
└── db/                          # schema.sql, seed.sql
```

**MUST:**
- `core/infra/`의 각 어댑터는 `core/core/ports/`의 인터페이스를 구현
- 어댑터는 외부 라이브러리 의존 가능 (Qdrant, SQLAlchemy 등)

### 2.5 Scripts & Tests 구조

```
scripts/
├── __init__.py
├── reindex_all.py               # 모든 리포 재인덱싱
└── debug_search.py              # 검색 디버깅/프로파일링

tests/
├── __init__.py
├── unit/                        # 순수 유닛 테스트
├── core/                        # Core 서비스/도메인 테스트
├── infra/                       # 어댑터 테스트
├── interfaces/                  # API/MCP 테스트
├── integration/                 # 통합 테스트
└── scenarios/                   # 엔드투엔드/골든 시나리오
```

**MUST:**
- 테스트는 소스 코드 레이어 구조와 동일하게 배치

---

## 3. 레이어 책임 (MUST)

### 3.1 Core Layer (The Brain)

**책임:**
- 비즈니스 로직 구현 (프레임워크/DB 무관)
- 데이터 구조 정의 (domain)
- 계약 정의 (ports)
- 유즈케이스 오케스트레이션 (services)

**MUST:**
- `core/core/domain/`: 데이터 형태 정의만 (로직 메서드 없음)
- `core/core/ports/`: ABC 정의만 (구현 없음)
- `core/core/services/`: 흐름과 규칙 정의 (parsing, indexing, searching 로직)

### 3.2 Infra Layer (The Tools)

**책임:**
- 외부 도구의 구체적인 구현

**MUST:**
- `core/infra/vector/`: `core.core.ports.vector_store` 구현
- `core/infra/git/`: `core.core.ports.git_provider` 구현
- `core/infra/storage/`: `core.core.ports.relational_store` 구현

### 3.3 Interfaces Layer (The Doors)

**책임:**
- 사용자 또는 에이전트를 위한 진입점

**MUST:**
- `apps/api_server/`: REST API 컨트롤러
- `apps/mcp_server/`: MCP 핸들러

---

## 4. 워크플로우 시나리오별 파일 위치 (MUST)

### 4.1 데이터 구조 수정

**시나리오:** "Pull Request 노드에 `review_status` 필드 추가"

1. **Domain 수정**: `core/core/domain/nodes.py`의 `PullRequestNode` 수정
2. **Port 확인**: `graph_store.py`가 특정 필드에 의존하는지 확인
3. **Infra 업데이트**: SQL 사용 시 `core/infra/storage/postgres.py` 모델 업데이트

### 4.2 파싱 로직 개선

**시나리오:** "Rust 파일에서 함수 추출 실패"

1. **위치**: `core/core/services/ingestion/parser.py`
2. **작업**: `_visit_rust_node` 메서드 또는 Tree-sitter 쿼리 로직 수정

### 4.3 검색 알고리즘 튜닝

**시나리오:** "Hybrid search의 Lexical vs Semantic 가중치 변경"

1. **위치**: `core/core/services/search_service.py`
2. **작업**: `search` 메서드에서 vector score와 BM25 score 조합 로직 수정

### 4.4 새로운 Agent Tool 추가

**시나리오:** "파일 최종 수정자를 찾는 툴 추가"

1. **Service 메서드 생성**: `core/core/services/git_service.py`에 `get_file_authors` 추가
2. **MCP 노출**: `apps/mcp_server/handlers/`에 새 핸들러 생성
3. **등록**: MCP 라우팅 테이블(`apps/mcp_server/__init__.py` 등)에 핸들러 등록

### 4.5 Vector DB 마이그레이션

**시나리오:** "Qdrant → Weaviate 전환"

1. **어댑터 생성**: `core/infra/vector/weaviate.py`에 `VectorStorePort` 구현
2. **Wiring 업데이트**: `core/container.py`에서 `WeaviateAdapter` 초기화
3. **검증**: Core 로직은 변경 없음

### 4.6 Reranking 개선

**시나리오:** "Cross-Encoder reranker 사용"

1. **인터페이스 정의**: `core/core/ports/llm_provider.py` 또는 별도 `RerankerPort` 생성
2. **Infra 구현**: `core/infra/llm/cohere_reranker.py` 또는 `huggingface_reranker.py` 추가
3. **통합**: `core/core/services/search_service.py`에서 initial retrieval 후 reranker 호출

### 4.7 새로운 Relationship Type 추가

**시나리오:** "Test Code → Target Code 링크 추가"

1. **Enum 업데이트**: `core/core/domain/graph.py`의 `RelationshipType`에 `TESTS` 추가
2. **로직 업데이트**: `core/core/services/ingestion/parser.py`에서 테스트 파일 패턴 감지 및 관계 엣지 생성
3. **Mapper 업데이트**: `core/core/domain/chunks.py`의 `canonical_leaf_to_vector_payload`가 새 관계 타입 처리하도록 수정

---

## 5. Wiring & Dependency Injection (MUST)

### 5.1 container.py 역할

`container.py`는 **중앙 와이어링 허브**이다.

**MUST:**
- DI 프레임워크를 사용하여 어댑터(`core/infra/*`) 초기화
- 초기화된 어댑터를 Core services(`core/core/services`)에 주입
- 새로운 Service 또는 Adapter 생성 시 반드시 `core/container.py`에 등록

**예시 구조:**
```python
# core/container.py
from dependency_injector import containers, providers
from core.services import SearchService, IndexingService
from infra.vector.qdrant import QdrantAdapter
from infra.storage.postgres import PostgresAdapter

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Infra adapters
    vector_store = providers.Singleton(QdrantAdapter, ...)
    relational_store = providers.Singleton(PostgresAdapter, ...)

    # Core services
    search_service = providers.Factory(
        SearchService,
        vector_store=vector_store,
        relational_store=relational_store,
    )
```

### 5.2 신규 컴포넌트 등록 규칙

**MUST:**
1. 새로운 Service 생성 시 `container.py`에 provider 등록
2. 새로운 Adapter 생성 시 `container.py`에 singleton/factory 등록
3. API/MCP에서 접근 가능하도록 wiring 설정

---

## 6. 금지 규칙 (MUST NOT)

### 6.1 Import 금지

**MUST NOT:**
- Core에서 FastAPI import 금지
- Core에서 SQLAlchemy import 금지
- Core에서 Qdrant SDK import 금지
- Core에서 Interfaces 레이어 import 금지
- Core에서 Infra 레이어 import 금지

### 6.2 구조 위반 금지

**MUST NOT:**
- `core/core/domain/`에 비즈니스 로직 메서드 구현 금지
- `core/core/ports/`에 구체적인 구현 코드 금지
- `infra/`에서 다른 `infra/` 모듈 직접 의존 금지 (port를 통해서만)

### 6.3 순환 의존 금지

**MUST NOT:**
- Core ← Interfaces 순환 의존 금지
- Core ← Infra 순환 의존 금지
- Service 간 순환 의존 금지

---

## 7. 파일 네이밍 규칙 (MUST)

### 7.1 Service 파일

**MUST:**
- `*_service.py` 형식 사용
- 예: `search_service.py`, `indexing_service.py`, `graph_service.py`

### 7.2 Port 파일

**MUST:**
- `*_port.py` 또는 `*_provider.py` 형식 사용
- 예: `vector_store.py`, `git_provider.py`, `llm_provider.py`

### 7.3 Adapter 파일

**MUST:**
- 기술 스택 이름 사용
- 예: `qdrant.py`, `postgres.py`, `meilisearch.py`, `openai.py`

### 7.4 Schema 파일

**MUST:**
- `*_schema.py` 형식 사용
- 예: `search_schema.py`, `index_schema.py`

---

## 8. 체크리스트

새로운 기능 추가 시:

- [ ] 도메인 모델이 필요한가? → `core/core/domain/`에 추가
- [ ] 외부 시스템 연동이 필요한가? → `core/core/ports/`에 인터페이스 정의
- [ ] 구체적인 구현이 필요한가? → `core/infra/`에 어댑터 구현
- [ ] 유즈케이스 로직이 필요한가? → `core/core/services/`에 서비스 추가
- [ ] API 엔드포인트가 필요한가? → `apps/api_server/routes/`에 라우터 추가
- [ ] MCP 툴이 필요한가? → `apps/mcp_server/handlers/`에 핸들러 추가
- [ ] DI 등록했는가? → `core/container.py`에 등록
- [ ] 테스트 작성했는가? → `tests/` 해당 레이어에 테스트 추가

---

## 9. 참고 자료

- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [DI_SPEC.md](DI_SPEC.md)
- [LAYERING_SPEC.md](LAYERING_SPEC.md)
- [TEST_RULES.md](TEST_RULES.md)

---

## 10. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2025-01-23 | 2.0 | _B_01_repo_structure.md 기반 전면 개편 | - |
| 2025-01-23 | 1.0 | 초안 작성 | - |
