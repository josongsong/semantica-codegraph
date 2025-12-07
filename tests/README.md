# 테스트 가이드

## 디렉토리 구조

```
tests/
├── unit/              # 70% - 단위 테스트 (빠름)
├── integration/       # 20% - 통합 테스트 (중간)
├── e2e/              # 10% - E2E 테스트 (느림)
├── performance/       # 성능/벤치마크
├── security/          # 보안 테스트
├── contract/          # API 계약
├── fixtures/          # 테스트 픽스처
└── helpers/           # 테스트 헬퍼
```

## 테스트 레벨

### Unit (70%)
격리된 단위 테스트. 외부 의존성 없이 빠르게 실행.

**위치**: `tests/unit/`
- `domain/`: 도메인 로직 (code_graph, analysis, indexing, retrieval)
- `infrastructure/`: 인프라 (parsers, generators, storage, cache)
- `application/`: 애플리케이션 서비스

**실행**:
```bash
pytest tests/unit/ -v
pytest tests/unit/domain/code_graph/  # 특정 도메인만
```

### Integration (20%)
모듈 간 상호작용 테스트. DB, 외부 서비스 포함.

**위치**: `tests/integration/`
- `database/`: DB 통합 (postgres, redis, kuzu)
- `external_services/`: 외부 서비스 (llm, git, lsp)
- `workflows/`: 워크플로우 (indexing/search/analysis pipeline)
- `api/`: API 통합 (rest, mcp)

**실행**:
```bash
pytest tests/integration/ -v
pytest tests/integration/workflows/  # 워크플로우만
```

### E2E (10%)
실제 사용자 시나리오 검증. 전체 시스템.

**위치**: `tests/e2e/`
- `user_scenarios/`: 사용자 시나리오 (java/python/multi-language)
- `critical_paths/`: 크리티컬 경로
- `system_verification/`: 시스템 검증

**실행**:
```bash
pytest tests/e2e/ -v --slow
```

### Performance
성능/벤치마크 테스트.

**위치**: `tests/performance/`
- `benchmarks/`: 벤치마크
- `load/`: 부하 테스트
- `profiling/`: 프로파일링
- `stress/`: 스트레스 테스트

**실행**:
```bash
pytest tests/performance/benchmarks/ --benchmark-only
```

### Security
보안 테스트.

**위치**: `tests/security/`
- `taint_analysis/`: Taint 분석
- `vulnerability/`: 취약점 탐지
- `compliance/`: 컴플라이언스

**실행**:
```bash
pytest tests/security/ -v
```

## 네이밍 컨벤션

### Unit
```python
test_<component>_<aspect>.py

# 예시
test_ir_builder_basic.py
test_cfg_builder_control_flow.py
test_parser_syntax_errors.py
```

### Integration
```python
test_<workflow>_integration.py

# 예시
test_indexing_pipeline_integration.py
test_search_workflow_integration.py
test_postgres_kuzu_integration.py
```

### E2E
```python
test_<scenario>_e2e.py

# 예시
test_java_project_e2e.py
test_incremental_update_e2e.py
test_multi_language_e2e.py
```

### Performance
```python
test_<component>_benchmark.py

# 예시
test_indexing_benchmark.py
test_search_benchmark.py
```

### Security
```python
test_<vulnerability>_security.py

# 예시
test_sql_injection_security.py
test_xss_security.py
```

## 실행 전략

### 개발 중 (빠른 피드백)
```bash
pytest tests/unit/ --maxfail=5
# 또는
./scripts/test_fast.sh
```

### PR 검증
```bash
pytest tests/unit/ tests/integration/
```

### Merge/Deploy
```bash
pytest tests/  # 전체
```

### Nightly
```bash
pytest tests/ --slow --benchmark-only
# 또는
./scripts/test_slow.sh
```

## 느린 테스트 감지

### 자동 감지 (conftest.py)
모든 테스트는 자동으로 실행 시간이 추적됩니다:
- **>5초**: ⚠️ SLOW TEST 경고 (최적화 권장)
- **>2초**: ⏱️ Slow 알림

### 실행 시 자동 표시
```bash
pytest tests/

# 출력 예시:
test_example.py::test_slow_query 
⚠️ SLOW TEST (7.32s): test_example.py::test_slow_query
   Consider marking with @pytest.mark.slow or optimizing

========= slowest 10 durations =========
7.32s call     test_example.py::test_slow_query
2.15s call     test_other.py::test_medium
```

### 성능 분석
```bash
# 전체 성능 분석
./scripts/test_watch.sh

# 느린 테스트만 실행
./scripts/test_slow.sh

# 빠른 테스트만 실행 (unit)
./scripts/test_fast.sh
```

### 느린 테스트 마킹
```python
import pytest

@pytest.mark.slow
def test_heavy_computation():
    """5초 이상 걸리는 테스트는 @pytest.mark.slow 추가"""
    ...

# 실행 시 제외
pytest tests/ -m "not slow"
```

### 타임아웃 설정
```python
@pytest.mark.timeout(10)  # 10초 타임아웃
def test_with_timeout():
    ...
```

### 권장 기준
- **Unit**: <0.5초
- **Integration**: <5초
- **E2E**: <30초
- **>5초**: `@pytest.mark.slow` 추가

## 테스트 작성 가이드

### 1. 적절한 레벨 선택
- 외부 의존성 없음 → **Unit**
- DB/API 필요 → **Integration**
- 전체 시나리오 → **E2E**

### 2. 위치 결정
```python
# IR 빌더 테스트
tests/unit/domain/code_graph/test_ir_builder.py

# Postgres 통합
tests/integration/database/postgres/test_store.py

# Java 프로젝트 시나리오
tests/e2e/user_scenarios/java_project/test_indexing.py
```

### 3. Fixtures 활용
```python
from tests.fixtures.repos.java import sample_java_project
from tests.helpers.builders import IRDocumentBuilder

def test_something():
    repo = sample_java_project()
    ir = IRDocumentBuilder().with_repo(repo).build()
```

### 4. 명확한 이름
```python
# Good
def test_ir_builder_handles_nested_classes():
    ...

# Bad
def test_builder():
    ...
```

## 마이그레이션 중

일부 테스트는 아직 이동 중입니다:
- `foundation/` → `unit/domain/` 또는 `unit/infrastructure/`
- `v6/` → `unit/`, `integration/`, `e2e/` 적절히 분산
- 루트 테스트 → 적절한 위치로 이동

상세: `docs/TEST_STRUCTURE_REFACTORING.md`
