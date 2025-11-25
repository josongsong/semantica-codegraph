# Test Gap Analysis - 테스트 누락 분석

## 개요

현재 117개의 소스 파일 대비 38개의 테스트 파일이 존재합니다.
테스트 커버리지를 분석하여 누락된 부분을 정리합니다.

**Date**: 2025-01-24

---

## ✅ 현재 테스트된 모듈

### Foundation Layer (21개 테스트)
- ✅ **Chunk** (9개) - boundary, builder, incremental, mapping, models, partial_updates, redundancy, graph_integration
- ✅ **DFG** (2개) - builder, advanced
- ✅ **Graph** (3개) - builder, extended, dfg_integration
- ✅ **Semantic IR** (1개) - builder
- ✅ **Generators** (1개) - python_generator_basic
- ✅ **Parsing** (1개) - incremental_parsing
- ✅ **Storage** (2개) - kuzu_store, postgres_chunk_store
- ✅ **기타** (2개) - git_loader, pyright_integration, bfg_builder

### Index Layer (5개 테스트)
- ✅ **Domain Adapter** - 완전한 테스트
- ✅ **Fuzzy Adapter** - 완전한 테스트
- ✅ **Symbol Index** - 기본 테스트
- ✅ **Service** - 에러 처리 테스트
- ✅ **Transformer** - 변환 테스트

### Infrastructure Layer (1개 테스트)
- ✅ **Storage** - PostgreSQL store

### RepoMap Layer (6개 테스트)
- ✅ **Builder** - orchestrator
- ✅ **Models** - 데이터 모델
- ✅ **PageRank** - 랭킹 엔진
- ✅ **Summarizer** - LLM 요약
- ✅ **Incremental** - 증분 업데이트
- ✅ **Storage** - PostgreSQL 저장소

### Retriever Layer (1개 테스트)
- ✅ **Integration** - 기본 통합 테스트

### Server Layer (2개 테스트)
- ✅ **API Server** (12개) - 모든 엔드포인트
- ✅ **MCP Server** (13개) - 모든 tool 핸들러

### Integration (1개 테스트)
- ✅ **Search E2E** - 검색 통합 테스트

---

## ❌ 누락된 테스트 (우선순위별)

### 🔴 Critical - 즉시 필요 (서버 운영 필수)

#### 1. **migrations/** - 마이그레이션 테스트
- 파일: `migrations/test_migrations.py` (이미 존재하지만 tests/ 밖에 있음)
- 상태: ✅ 존재함 (tests/ 디렉토리에는 없음)
- 액션: 필요 없음 (이미 완전함)

#### 2. **src/container.py** - DI Container
- 현재: 테스트 없음
- 필요: Container 초기화, 서비스 생성, 의존성 주입 테스트
- 중요도: **High** (모든 서버가 의존)

#### 3. **src/infra/config/** - 설정 관리
```
❌ src/infra/config/settings.py
```
- 현재: 테스트 없음
- 필요: 환경변수 로딩, 기본값, 검증 테스트
- 중요도: **High** (설정 오류 방지)

#### 4. **src/infra/db/** - 데이터베이스 어댑터
```
❌ src/infra/db/postgres.py
```
- 현재: 테스트 없음
- 필요: 연결 풀, 쿼리 실행, 트랜잭션 테스트
- 중요도: **High** (DB 연결 필수)

---

### 🟠 High Priority - 핵심 기능

#### 5. **src/foundation/parsing/** - 파서 인프라
```
❌ src/foundation/parsing/parser_registry.py
❌ src/foundation/parsing/source_file.py
❌ src/foundation/parsing/ast_tree.py
❌ src/foundation/parsing/tree_sitter_parser.py
```
- 현재: incremental_parsing만 테스트됨
- 필요: 파서 등록, 소스 파일 처리, AST 생성 테스트
- 중요도: **High** (모든 파싱의 기반)

#### 6. **src/foundation/generators/** - IR 생성기
```
✅ src/foundation/generators/python_generator.py (기본 테스트 있음)
❌ src/foundation/generators/base.py
❌ src/foundation/generators/scope_stack.py
❌ src/foundation/generators/python/signature_builder.py
❌ src/foundation/generators/python/call_analyzer.py
❌ src/foundation/generators/python/variable_analyzer.py
```
- 현재: python_generator_basic만 있음
- 필요: 전체 generator 로직, 스코프 관리, 시그니처 분석 테스트
- 중요도: **High** (IR 생성 핵심)

#### 7. **src/foundation/semantic_ir/** - Semantic IR (부분적)
```
✅ src/foundation/semantic_ir/builder.py (테스트 있음)
❌ src/foundation/semantic_ir/cfg/builder.py (CFG)
❌ src/foundation/semantic_ir/cfg/models.py
❌ src/foundation/semantic_ir/typing/builder.py (타입 추론)
❌ src/foundation/semantic_ir/typing/resolver.py
❌ src/foundation/semantic_ir/signature/builder.py (시그니처)
❌ src/foundation/semantic_ir/context.py
```
- 현재: builder만 테스트됨
- 필요: CFG 생성, 타입 추론, 시그니처 분석 테스트
- 중요도: **High** (고급 분석 기능)

---

### 🟡 Medium Priority - 인프라

#### 8. **src/infra/cache/** - 캐시
```
❌ src/infra/cache/redis.py
```
- 필요: Redis 연결, 캐시 읽기/쓰기, TTL 테스트
- 중요도: **Medium** (성능 최적화)

#### 9. **src/infra/llm/** - LLM 클라이언트
```
❌ src/infra/llm/openai.py
```
- 필요: API 호출, 임베딩 생성, 에러 처리 테스트
- 중요도: **Medium** (RepoMap 요약에 사용)

#### 10. **src/infra/git/** - Git 인프라
```
❌ src/infra/git/repository.py
```
- 필요: Git 저장소 조작, diff, 커밋 이력 테스트
- 중요도: **Medium** (증분 인덱싱)

#### 11. **src/infra/graph/** - 그래프 DB
```
❌ src/infra/graph/kuzu.py
```
- 현재: test_kuzu_store는 있지만 어댑터 테스트 없음
- 필요: Kuzu 연결, 쿼리, 그래프 조작 테스트
- 중요도: **Medium** (Symbol 검색)

#### 12. **src/infra/vector/** - 벡터 DB
```
❌ src/infra/vector/qdrant.py
```
- 필요: Qdrant 연결, 벡터 검색, 컬렉션 관리 테스트
- 중요도: **Medium** (Vector 검색)

#### 13. **src/infra/search/** - 검색 인프라
```
❌ src/infra/search/zoekt.py
```
- 필요: Zoekt 연결, 검색 쿼리 테스트
- 중요도: **Medium** (Lexical 검색)

---

### 🟢 Low Priority - 고급 기능 (Retriever)

#### 14. **src/retriever/** - 대부분 미테스트
```
❌ src/retriever/context_builder/ (4 files)
❌ src/retriever/feedback/ (2 files)
❌ src/retriever/fusion/ (4 files)
❌ src/retriever/hybrid/ (2 files)
❌ src/retriever/intent/ (5 files)
❌ src/retriever/multi_index/ (5 files)
❌ src/retriever/observability/ (3 files)
❌ src/retriever/query/ (3 files)
❌ src/retriever/reasoning/ (2 files)
❌ src/retriever/scope/ (3 files)
```
- 현재: test_retriever_integration만 있음
- 필요: 각 서브모듈별 상세 테스트
- 중요도: **Low** (고급 검색 기능, 나중에 추가 가능)

---

## 📊 테스트 커버리지 통계

### 모듈별 커버리지

| 모듈 | 소스 파일 | 테스트 파일 | 커버리지 | 상태 |
|------|-----------|-------------|----------|------|
| **foundation/** | ~44 | 21 | ~48% | 🟡 부분적 |
| **index/** | ~8 | 5 | ~63% | 🟢 양호 |
| **infra/** | ~9 | 1 | ~11% | 🔴 매우 낮음 |
| **repomap/** | ~9 | 6 | ~67% | 🟢 양호 |
| **retriever/** | ~33 | 1 | ~3% | 🔴 매우 낮음 |
| **server/** | ~8 | 2 | 100% | ✅ 완전 |
| **최상위** | ~6 | 1 | ~17% | 🔴 낮음 |
| **Total** | **~117** | **38** | **~32%** | 🟡 부족 |

### 레이어별 우선순위

1. **Infrastructure (infra)** - 11% 커버리지 → **즉시 개선 필요**
   - config, db는 Critical
   - cache, llm, git, graph, vector는 Medium

2. **Foundation** - 48% 커버리지 → **핵심 부분 개선 필요**
   - parsing, generators, semantic_ir 하위 모듈들

3. **Retriever** - 3% 커버리지 → **나중에 개선**
   - 고급 기능이므로 우선순위 낮음

---

## 🎯 권장 액션 플랜

### Phase 1: Critical (즉시) - 1-2일

1. **Container 테스트** (`tests/test_container.py`)
   - Container 초기화
   - 서비스 생성 및 DI
   - 싱글톤 패턴 검증

2. **Config 테스트** (`tests/infra/test_config.py`)
   - 환경변수 로딩
   - 기본값 검증
   - 필수 설정 확인

3. **DB 테스트** (`tests/infra/test_db.py`)
   - PostgreSQL 연결 풀
   - 쿼리 실행
   - 트랜잭션 처리

### Phase 2: High Priority - 3-5일

4. **Parsing 테스트** (`tests/foundation/test_parsing_*.py`)
   - Parser registry
   - Source file handling
   - AST tree operations

5. **Generators 테스트** (`tests/foundation/test_generators_*.py`)
   - Scope stack
   - Signature builder
   - Call/variable analyzer

6. **Semantic IR 테스트** (`tests/foundation/test_semantic_ir_*.py`)
   - CFG builder
   - Type resolver
   - Signature builder

### Phase 3: Medium Priority - 5-7일

7. **Infra 테스트** (`tests/infra/test_*.py`)
   - Cache (Redis)
   - LLM (OpenAI)
   - Git
   - Graph (Kuzu)
   - Vector (Qdrant)
   - Search (Zoekt)

### Phase 4: Low Priority - 필요시

8. **Retriever 테스트** (`tests/retriever/test_*.py`)
   - 각 서브모듈별 테스트 추가

---

## 💡 테스트 작성 가이드

### 우선순위 결정 기준

1. **Critical**: 서버 실행에 필수적인 모듈
2. **High**: 핵심 기능 (파싱, IR 생성, 인덱싱)
3. **Medium**: 인프라 (캐시, LLM, DB 어댑터)
4. **Low**: 고급 기능 (고급 검색, 피드백)

### 테스트 작성 원칙

1. **단순성**: 복잡한 mocking 피하기
2. **실용성**: 실제 사용 케이스 중심
3. **빠른 실행**: 1초 이내 완료
4. **독립성**: 테스트 간 의존성 없음

### 테스트 템플릿

```python
"""
Module Tests

Simple unit tests for [module_name].
"""

import pytest

from src.path.to.module import MyClass


@pytest.fixture
def instance():
    """Create instance for testing."""
    return MyClass()


def test_basic_functionality(instance):
    """Test basic operation."""
    result = instance.do_something()
    assert result is not None


def test_error_handling(instance):
    """Test error handling."""
    with pytest.raises(ValueError):
        instance.do_invalid_operation()
```

---

## 📝 결론

### 현재 상태
- ✅ **Server Layer**: 100% 커버리지 (완전)
- ✅ **Index Layer**: 63% 커버리지 (양호)
- ✅ **RepoMap Layer**: 67% 커버리지 (양호)
- 🟡 **Foundation Layer**: 48% 커버리지 (부분적)
- 🔴 **Infrastructure Layer**: 11% 커버리지 (매우 낮음)
- 🔴 **Retriever Layer**: 3% 커버리지 (매우 낮음)

### 즉시 필요한 테스트 (Critical)
1. Container DI 테스트
2. Config 설정 테스트
3. PostgreSQL DB 테스트

### 다음 단계 (High Priority)
4. Parsing 인프라 테스트
5. Generators 전체 테스트
6. Semantic IR 상세 테스트

**권장**: Phase 1 (Critical)부터 시작하여 순차적으로 테스트 커버리지 향상
