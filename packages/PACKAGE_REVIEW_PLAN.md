# Packages 전체 리뷰 계획

**Date:** 2025-12-29
**Scope:** packages/ 아래 모든 패키지 체계적 리뷰
**Goal:** SOLID + Hexagonal Architecture + DDD 준수, 코드 품질 개선

---

## Executive Summary

### 패키지 현황 (13개)

| # | 패키지 | 언어 | 파일 수 | 역할 | 우선순위 |
|---|--------|------|---------|------|----------|
| 1 | **codegraph-shared** | Python | 107 | 기반 인프라 (config, storage, jobs) | P0 |
| 2 | **codegraph-ir** | Rust | 653 | 핵심 분석 엔진 (IR, CFG, PTA) | P0 ✅ |
| 3 | **codegraph-storage** | Rust | ? | 데이터 저장 백엔드 | P0 |
| 4 | **codegraph-engine** | Python | ? | 분석 엔진 (IR, chunking, graphs) | P1 |
| 5 | **codegraph-trcr** | Python | ? | TRCR 규칙 엔진 | P1 |
| 6 | **codegraph-parsers** | Python | ? | 언어 파서 | P1 |
| 7 | **codegraph-search** | Python | ? | 검색 (lexical, semantic, graph) | P2 |
| 8 | **codegraph-analysis** | Python | ? | 코드 분석 기능 | P2 |
| 9 | **codegraph-orchestration** | Rust | ? | 오케스트레이션 | P2 |
| 10 | **codegraph-runtime** | Python | ? | 런타임 컴포넌트 | P2 |
| 11 | **codegraph-ml** | Python | ? | ML 모델 | P3 |
| 12 | **codegraph-agent** | Python | ? | 자율 에이전트 | P3 |
| 13 | **codegraph-reasoning** | Python | ? | 추론 엔진 | P3 |

**범례:**
- ✅ = 이미 완료 (codegraph-ir)
- P0 = 최우선 (인프라/핵심)
- P1 = 높음 (핵심 기능)
- P2 = 중간 (보조 기능)
- P3 = 낮음 (고급 기능)

---

## Phase 0: 사전 조사 (1일)

### 목표
모든 패키지의 현황 파악 및 의존성 그래프 작성

### 작업
1. ✅ 패키지 목록 확인 (13개)
2. ⏳ 각 패키지 파일 수 집계
3. ⏳ 의존성 그래프 작성
4. ⏳ 아키텍처 위반 사전 탐지
5. ⏳ 중복 코드 추정

### 측정 지표
```bash
# 각 패키지별 측정
- 파일 수 (Python, Rust)
- LOC (Lines of Code)
- 순환 의존성 개수
- unwrap() 호출 (Rust)
- Type hints 커버리지 (Python)
- 테스트 커버리지
```

---

## Phase 1: Foundation Layer (Week 1)

### 1.1 codegraph-shared (P0, 3일)

**현황:**
- 107 Python 파일
- 역할: 기반 인프라 (config, storage, jobs, container)
- 의존성: 없음 (base layer)

**리뷰 항목:**
1. **아키텍처 준수**
   - [ ] 순환 의존성 확인 (shared는 다른 패키지에 의존하면 안됨)
   - [ ] Hexagonal: Domain/Ports/Infrastructure 분리
   - [ ] DDD: Aggregates, Entities, Value Objects

2. **코드 품질**
   - [ ] Type hints 커버리지 (목표: 90%+)
   - [ ] Docstring 커버리지 (목표: 80%+)
   - [ ] God classes 식별 (>500 LOC)
   - [ ] 코드 중복 (>20% 유사도)

3. **SOLID 준수**
   - [ ] SRP: 단일 책임 (각 모듈 하나의 책임)
   - [ ] OCP: 확장 가능성 (플러그인 구조)
   - [ ] LSP: 상속 관계 검증
   - [ ] ISP: 인터페이스 분리
   - [ ] DIP: 추상화 의존

4. **성능**
   - [ ] Database 쿼리 최적화
   - [ ] Job scheduler 효율성
   - [ ] 캐싱 전략

**산출물:**
- `codegraph-shared/ARCHITECTURE_REVIEW.md`
- `codegraph-shared/IMPROVEMENTS.md`
- `codegraph-shared/REFACTORING_PLAN.md`

---

### 1.2 codegraph-storage (P0, 2일)

**현황:**
- Rust 패키지
- 역할: SQLite/PostgreSQL 저장 백엔드
- 최근 개선: SQLite ChunkStore 구현 완료

**리뷰 항목:**
1. **아키텍처**
   - [ ] Port traits 정의 (StorageBackend)
   - [ ] PostgreSQL/SQLite 구현 분리
   - [ ] Transaction 관리

2. **코드 품질**
   - [ ] unwrap() 제거 (목표: 0개)
   - [ ] Error handling (Result<T>)
   - [ ] 테스트 커버리지 (목표: 80%+)

3. **성능**
   - [ ] Bulk insert 최적화
   - [ ] Index 전략
   - [ ] Connection pooling

**산출물:**
- `codegraph-storage/ARCHITECTURE_REVIEW.md`
- Port trait 정의 (if missing)

---

### 1.3 codegraph-ir (P0, ✅ 완료)

**현황:**
- ✅ 653 Rust 파일
- ✅ 역할: 핵심 분석 엔진 (IR, CFG, DFG, PTA, Taint)
- ✅ 최근 개선: 순환 의존성 제거, BaseExtractor, ChunkRepository

**완료 사항:**
- ✅ 순환 의존성 0개
- ✅ Parser 중복 제거 인프라 (BaseExtractor)
- ✅ DIP 준수 시작 (ChunkRepository)
- ✅ 벤치마크 정확도 개선
- ✅ 성능 목표 1,350% 달성

**향후 작업 (Optional):**
- ⏳ Parser migration (Python → BaseExtractor)
- ⏳ 15개 Port traits 추가
- ⏳ unwrap() 제거 (998 → <50)

---

## Phase 2: Core Engine Layer (Week 2)

### 2.1 codegraph-engine (P1, 3일)

**예상 현황:**
- Python 패키지
- 역할: 분석 엔진 (IR 빌드, chunking, graphs)
- 의존성: codegraph-shared, codegraph-ir (via PyO3)

**리뷰 항목:**
1. **Python → Rust 마이그레이션 검증**
   - [ ] 어떤 로직이 Python에 남아있는지 확인
   - [ ] Rust로 이동 가능한 로직 식별
   - [ ] PyO3 바인딩 최적화

2. **아키텍처**
   - [ ] Hexagonal 준수
   - [ ] DDD Aggregates
   - [ ] 순환 의존성

3. **코드 품질**
   - [ ] Type hints
   - [ ] Docstrings
   - [ ] 테스트 커버리지

**산출물:**
- `codegraph-engine/RUST_MIGRATION_PLAN.md`
- `codegraph-engine/ARCHITECTURE_REVIEW.md`

---

### 2.2 codegraph-trcr (P1, 2일)

**예상 현황:**
- Python 패키지
- 역할: TRCR (Taint Rule Checking) 규칙 엔진
- 특징: YAML 규칙 200개 (최근 확장)

**리뷰 항목:**
1. **규칙 엔진 설계**
   - [ ] 규칙 로딩 메커니즘
   - [ ] 규칙 검증 (syntax, semantics)
   - [ ] 성능 (200개 규칙 처리)

2. **코드 품질**
   - [ ] 규칙 파서 중복 제거
   - [ ] 에러 핸들링
   - [ ] 테스트 (규칙별 테스트)

**산출물:**
- `codegraph-trcr/RULE_ENGINE_REVIEW.md`
- 규칙 검증 자동화 개선

---

### 2.3 codegraph-parsers (P1, 2일)

**예상 현황:**
- Python 패키지
- 역할: 언어 파서 (Python, TypeScript, Java, Kotlin, Rust, Go)
- 중복 가능성: 높음 (각 언어별 파서)

**리뷰 항목:**
1. **중복 코드 분석**
   - [ ] 파서 간 공통 패턴 추출
   - [ ] BaseParser 추상 클래스 필요성
   - [ ] Tree-sitter 통합

2. **아키텍처**
   - [ ] Plugin 구조 (각 언어 독립)
   - [ ] Registry pattern

**산출물:**
- `codegraph-parsers/DEDUPLICATION_PLAN.md`

---

## Phase 3: Service Layer (Week 3)

### 3.1 codegraph-search (P2, 2일)

**예상 현황:**
- Python 패키지
- 역할: Lexical/Semantic/Graph 검색
- 특징: Hybrid search (RRF fusion)

**리뷰 항목:**
1. **검색 알고리즘**
   - [ ] Lexical (Tantivy)
   - [ ] Semantic (Embedding)
   - [ ] Graph (Dependency)
   - [ ] Fusion (RRF)

2. **성능**
   - [ ] 인덱스 최적화
   - [ ] 캐싱
   - [ ] 병렬 처리

---

### 3.2 codegraph-analysis (P2, 2일)

**예상 현황:**
- Python 패키지
- 역할: 코드 분석 기능 (complexity, duplication, etc.)

**리뷰 항목:**
1. **분석 알고리즘**
   - [ ] Cyclomatic complexity
   - [ ] Code duplication
   - [ ] Dead code detection

---

### 3.3 codegraph-orchestration (P2, 2일)

**예상 현황:**
- Rust 패키지
- 역할: 파이프라인 오케스트레이션

**리뷰 항목:**
1. **오케스트레이션 로직**
   - [ ] Stage 의존성 관리
   - [ ] 병렬 처리
   - [ ] 에러 복구

---

### 3.4 codegraph-runtime (P2, 2일)

**예상 현황:**
- Python 패키지
- 역할: 런타임 컴포넌트

**리뷰 항목:**
1. **런타임 관리**
   - [ ] Process 관리
   - [ ] 리소스 모니터링

---

## Phase 4: Advanced Features (Week 4)

### 4.1 codegraph-ml (P3, 2일)

**예상 현황:**
- Python 패키지
- 역할: ML 모델 (embeddings, etc.)

**리뷰 항목:**
1. **ML 파이프라인**
   - [ ] 모델 로딩
   - [ ] Inference 최적화
   - [ ] 배치 처리

---

### 4.2 codegraph-agent (P3, 2일)

**예상 현황:**
- Python 패키지
- 역할: 자율 코딩 에이전트

**리뷰 항목:**
1. **에이전트 설계**
   - [ ] LLM 통합
   - [ ] Tool use
   - [ ] Memory management

---

### 4.3 codegraph-reasoning (P3, 2일)

**예상 현황:**
- Python 패키지
- 역할: 추론 엔진

**리뷰 항목:**
1. **추론 메커니즘**
   - [ ] Symbolic reasoning
   - [ ] Constraint solving

---

## 리뷰 체크리스트 (공통)

### 아키텍처 (Hexagonal + DDD)

- [ ] **Hexagonal Architecture 준수**
  - [ ] Domain layer (pure business logic)
  - [ ] Ports layer (abstractions/interfaces)
  - [ ] Infrastructure layer (external dependencies)
  - [ ] Application layer (use cases)

- [ ] **DDD 패턴**
  - [ ] Aggregates (일관성 경계)
  - [ ] Entities (식별자 있는 객체)
  - [ ] Value Objects (불변 값 객체)
  - [ ] Domain Events

- [ ] **의존성 방향**
  - [ ] 순환 의존성 0개
  - [ ] Domain → 외부 의존 없음
  - [ ] Infrastructure → Domain (DIP)

### SOLID 원칙

- [ ] **SRP (Single Responsibility)**
  - [ ] 각 클래스/모듈 하나의 책임
  - [ ] God classes 제거 (>500 LOC)

- [ ] **OCP (Open/Closed)**
  - [ ] 확장 가능 (Plugin, Strategy)
  - [ ] 수정 불필요

- [ ] **LSP (Liskov Substitution)**
  - [ ] 상속 관계 올바름
  - [ ] 서브타입 치환 가능

- [ ] **ISP (Interface Segregation)**
  - [ ] 인터페이스 분리
  - [ ] 불필요한 메서드 의존 없음

- [ ] **DIP (Dependency Inversion)**
  - [ ] 추상화 의존
  - [ ] Port traits 정의

### 코드 품질

**Python:**
- [ ] Type hints 커버리지 ≥ 90%
- [ ] Docstrings 커버리지 ≥ 80%
- [ ] Pylint score ≥ 8.0
- [ ] Black formatting
- [ ] Ruff linting
- [ ] Pyright strict mode

**Rust:**
- [ ] unwrap() calls = 0
- [ ] clippy::all 통과
- [ ] rustfmt 적용
- [ ] Error handling (Result<T>)
- [ ] Documentation comments

### 테스트

- [ ] 단위 테스트 커버리지 ≥ 80%
- [ ] 통합 테스트 존재
- [ ] 벤치마크 테스트 (성능 critical)
- [ ] E2E 테스트 (주요 시나리오)

### 성능

- [ ] 병목 구간 식별
- [ ] 최적화 기회 분석
- [ ] 메모리 프로파일링
- [ ] 벤치마크 결과

### 문서화

- [ ] README.md (패키지 개요)
- [ ] ARCHITECTURE.md (아키텍처 설명)
- [ ] API 문서 (함수/클래스)
- [ ] 예제 코드

---

## 산출물 템플릿

### 각 패키지별 생성 문서

1. **`ARCHITECTURE_REVIEW.md`**
   ```markdown
   # {Package} Architecture Review

   ## Executive Summary
   - 아키텍처 점수: X/10
   - 주요 이슈: N개
   - 권장 개선: M개

   ## Hexagonal Architecture
   ## SOLID Principles
   ## Code Quality
   ## Performance
   ## Recommendations
   ```

2. **`IMPROVEMENTS.md`**
   ```markdown
   # {Package} Improvements

   ## Phase 1: Quick Wins (1 week)
   ## Phase 2: Structural (2 weeks)
   ## Phase 3: Advanced (1 month)
   ```

3. **`REFACTORING_PLAN.md`**
   ```markdown
   # {Package} Refactoring Plan

   ## Scope
   ## Before/After
   ## Migration Strategy
   ## Testing Plan
   ```

---

## 실행 계획

### Week 1: Foundation (P0)
- Day 1-3: codegraph-shared
- Day 4-5: codegraph-storage
- Day 6-7: Summary & docs

### Week 2: Core (P1)
- Day 1-3: codegraph-engine
- Day 4-5: codegraph-trcr
- Day 6-7: codegraph-parsers

### Week 3: Service (P2)
- Day 1-2: codegraph-search
- Day 3-4: codegraph-analysis
- Day 5-6: codegraph-orchestration + codegraph-runtime
- Day 7: Summary

### Week 4: Advanced (P3)
- Day 1-2: codegraph-ml
- Day 3-4: codegraph-agent
- Day 5-6: codegraph-reasoning
- Day 7: Final summary

---

## 성공 지표

### 정량적
- [ ] 순환 의존성: 0개
- [ ] unwrap() (Rust): <50 total
- [ ] Type hints (Python): >90%
- [ ] Test coverage: >80%
- [ ] God classes: 0개 (>500 LOC)
- [ ] Code duplication: <10%

### 정성적
- [ ] Hexagonal Architecture 100% 준수
- [ ] SOLID 원칙 100% 준수
- [ ] DDD 패턴 적용
- [ ] 명확한 레이어 분리
- [ ] 테스트 가능한 구조
- [ ] 확장 가능한 설계

---

## 다음 단계

### Immediate (오늘)
1. ✅ 리뷰 계획 수립 (이 문서)
2. ⏳ Phase 0: 사전 조사 시작
   - 파일 수 집계
   - 의존성 그래프
   - 중복 코드 추정

### Week 1 (시작)
- codegraph-shared 리뷰 시작
- 기반 레이어 개선
- 템플릿 검증

---

**Date:** 2025-12-29
**Status:** 📋 계획 수립 완료
**Next:** Phase 0 사전 조사

