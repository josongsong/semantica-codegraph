# Packages 전체 현황 조사

**Date:** 2025-12-29
**Phase:** Phase 0 - Pre-Review Survey
**Status:** ✅ 완료

---

## Executive Summary

### 전체 현황

| Metric | Value |
|--------|-------|
| **총 패키지 수** | 13개 |
| **총 파일 수** | 1,779개 |
| **총 LOC** | 213,298 LOC |
| **Python 패키지** | 10개 (76.9%) |
| **Rust 패키지** | 3개 (23.1%) |
| **평균 파일당 LOC** | 119 LOC |

### 규모별 분류

**대형 (>50,000 LOC):**
- codegraph-ir: 104,605 LOC (49.0% of total) 🔥
- codegraph-engine: 53,226 LOC (24.9% of total) 🔥

**중형 (10,000-50,000 LOC):**
- codegraph-runtime: 13,804 LOC (6.5%)
- codegraph-search: 11,030 LOC (5.2%)

**소형 (<10,000 LOC):**
- codegraph-shared: 9,421 LOC (4.4%)
- codegraph-reasoning: 7,243 LOC (3.4%)
- codegraph-trcr: 5,656 LOC (2.7%)
- codegraph-orchestration: 3,311 LOC (1.6%)
- codegraph-parsers: 1,797 LOC (0.8%)
- codegraph-analysis: 1,530 LOC (0.7%)
- codegraph-agent: 1,184 LOC (0.6%)
- codegraph-ml: 374 LOC (0.2%)
- codegraph-storage: 117 LOC (0.1%)

---

## 패키지별 상세 통계

### 1. codegraph-ir (Rust) - 최대 규모 🔥

| Metric | Value |
|--------|-------|
| **파일 수** | 534 (531 Rust + 3 Python) |
| **LOC** | 104,605 (49.0% of total) |
| **평균 LOC/파일** | 195 |
| **역할** | 핵심 분석 엔진 (IR, CFG, DFG, PTA, Taint) |
| **의존성** | codegraph-storage (Rust) |
| **최근 개선** | ✅ 순환 의존성 제거, BaseExtractor, ChunkRepository |

**특징:**
- 전체 코드베이스의 절반을 차지하는 핵심 엔진
- Rust로 구현되어 고성능
- 최근 구조적 개선 완료 (SOLID, Hexagonal)
- 성능: 목표의 1,350% 달성

**우선순위:** ✅ P0 (완료)

---

### 2. codegraph-engine (Python) - 두 번째 규모 🔥

| Metric | Value |
|--------|-------|
| **파일 수** | 569 |
| **LOC** | 53,226 (24.9% of total) |
| **평균 LOC/파일** | 93 |
| **역할** | 분석 엔진 (IR 빌드, chunking, graphs) |
| **의존성** | ? (조사 필요) |
| **특징** | Python 구현, Rust로 마이그레이션 진행 중? |

**특징:**
- 두 번째로 큰 패키지
- Python 구현 (성능 이슈 가능성)
- codegraph-ir과 역할 중복 가능성 조사 필요
- Rust 마이그레이션 대상일 가능성

**우선순위:** P1 (높음)

**주요 의문:**
- codegraph-ir과 역할 중복? (둘 다 "분석 엔진")
- Python → Rust 마이그레이션 진행 상황?
- 어떤 로직이 Python에 남아야 하는가?

---

### 3. codegraph-runtime (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 151 |
| **LOC** | 13,804 (6.5% of total) |
| **평균 LOC/파일** | 91 |
| **역할** | 런타임 컴포넌트 |
| **의존성** | codegraph-analysis, codegraph-ir, codegraph-parsers, codegraph-shared |

**특징:**
- 많은 의존성 (4개)
- 런타임 관리 역할

**우선순위:** P2 (중간)

---

### 4. codegraph-search (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 147 |
| **LOC** | 11,030 (5.2% of total) |
| **평균 LOC/파일** | 75 |
| **역할** | Lexical/Semantic/Graph 검색, Hybrid search (RRF) |
| **의존성** | codegraph-engine, codegraph-shared |

**특징:**
- 검색 기능 (Tantivy, Embedding, Graph)
- Hybrid search (RRF fusion)

**우선순위:** P2 (중간)

---

### 5. codegraph-shared (Python) - 기반 레이어

| Metric | Value |
|--------|-------|
| **파일 수** | 107 |
| **LOC** | 9,421 (4.4% of total) |
| **평균 LOC/파일** | 88 |
| **역할** | 공유 인프라 (config, storage, jobs, container) |
| **의존성** | ⚠️ codegraph-ir, codegraph-parsers (문제!) |

**특징:**
- 기반 레이어여야 하는데 다른 패키지에 의존
- ⚠️ **아키텍처 위반**: shared는 다른 패키지에 의존하면 안됨
- DI Container 구현

**우선순위:** P0 (최우선)

**주요 이슈:**
- ⚠️ shared → ir 의존성 (역전되어야 함)
- ⚠️ shared → parsers 의존성 (역전되어야 함)

---

### 6. codegraph-reasoning (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 95 |
| **LOC** | 7,243 (3.4% of total) |
| **평균 LOC/파일** | 76 |
| **역할** | 추론 엔진 |
| **의존성** | codegraph-shared |

**우선순위:** P3 (낮음)

---

### 7. codegraph-trcr (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 73 |
| **LOC** | 5,656 (2.7% of total) |
| **평균 LOC/파일** | 77 |
| **역할** | TRCR 규칙 엔진 (200+ YAML rules) |
| **의존성** | 없음 |

**특징:**
- YAML 기반 taint 규칙 200개
- 최근 확장 완료

**우선순위:** P1 (높음)

---

### 8. codegraph-orchestration (Rust)

| Metric | Value |
|--------|-------|
| **파일 수** | 15 |
| **LOC** | 3,311 (1.6% of total) |
| **평균 LOC/파일** | 220 (높음!) |
| **역할** | 파이프라인 오케스트레이션 |
| **의존성** | codegraph-ir |

**특징:**
- 평균 LOC/파일이 높음 (220)
- God classes 가능성

**우선순위:** P2 (중간)

---

### 9. codegraph-parsers (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 20 |
| **LOC** | 1,797 (0.8% of total) |
| **평균 LOC/파일** | 89 |
| **역할** | 언어 파서 |
| **의존성** | 없음 |

**특징:**
- 6개 언어 파서
- codegraph-ir의 BaseExtractor와 관계?

**우선순위:** P1 (높음)

**주요 의문:**
- codegraph-ir의 Rust parsers와 관계?
- 중복 가능성?

---

### 10. codegraph-analysis (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 38 |
| **LOC** | 1,530 (0.7% of total) |
| **평균 LOC/파일** | 40 |
| **역할** | 코드 분석 기능 |
| **의존성** | codegraph-ir |

**우선순위:** P2 (중간)

---

### 11. codegraph-agent (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 18 |
| **LOC** | 1,184 (0.6% of total) |
| **평균 LOC/파일** | 65 |
| **역할** | 자율 코딩 에이전트 |
| **의존성** | 없음 |

**우선순위:** P3 (낮음)

---

### 12. codegraph-ml (Python)

| Metric | Value |
|--------|-------|
| **파일 수** | 7 |
| **LOC** | 374 (0.2% of total) |
| **평균 LOC/파일** | 53 |
| **역할** | ML 모델 (embeddings) |
| **의존성** | codegraph-shared |

**우선순위:** P3 (낮음)

---

### 13. codegraph-storage (Rust)

| Metric | Value |
|--------|-------|
| **파일 수** | 5 |
| **LOC** | 117 (0.1% of total) |
| **평균 LOC/파일** | 23 |
| **역할** | SQLite/PostgreSQL 저장 백엔드 |
| **의존성** | 없음 (base layer) ✅ |

**특징:**
- 최근 SQLite ChunkStore 구현 완료
- 기반 레이어로 올바른 위치

**우선순위:** P0 (최우선)

---

## 의존성 분석

### Layer 구조 (이상적)

```
Layer 3 (Application):
  codegraph-ml, codegraph-reasoning, codegraph-runtime, codegraph-search

Layer 2 (Domain Services):
  codegraph-analysis, codegraph-orchestration

Layer 1 (Core):
  codegraph-engine, codegraph-ir, codegraph-parsers, codegraph-trcr

Layer 0 (Foundation):
  codegraph-shared, codegraph-storage
```

### 현재 의존성 (pyproject.toml 기준)

**⚠️ 발견된 문제:**

1. **codegraph-shared → codegraph-ir** (역전!)
   - shared는 기반 레이어인데 상위 레이어 의존
   - ❌ 아키텍처 위반

2. **codegraph-shared → codegraph-parsers** (역전!)
   - shared가 parsers에 의존
   - ❌ 아키텍처 위반

3. **codegraph-engine ↔ codegraph-ir** 관계 불명확
   - 둘 다 "분석 엔진" 역할
   - 역할 중복 가능성
   - 조사 필요

### 의존성 레이어 (실제)

```
Layer 0:
  - codegraph-storage ✅ (base layer, no dependencies)

Layer 1:
  - codegraph-ir (depends on: codegraph-storage)
  - codegraph-parsers (standalone)
  - codegraph-trcr (standalone)

Layer 2:
  - codegraph-analysis (depends on: codegraph-ir)
  - codegraph-orchestration (depends on: codegraph-ir)
  - codegraph-shared ⚠️ (depends on: codegraph-ir, codegraph-parsers) ← WRONG!

Layer 3:
  - codegraph-ml (depends on: codegraph-shared)
  - codegraph-reasoning (depends on: codegraph-shared)
  - codegraph-runtime (depends on: analysis, ir, parsers, shared)
  - codegraph-search (depends on: engine, shared)
```

---

## 주요 발견 사항

### 1. 아키텍처 위반 🔴

**Critical (P0):**
- ⚠️ **codegraph-shared → codegraph-ir** (기반 레이어가 상위 의존)
- ⚠️ **codegraph-shared → codegraph-parsers** (기반 레이어가 상위 의존)

**설명:**
- `shared`는 기반 인프라 레이어여야 함
- 다른 모든 패키지가 `shared`에 의존해야 함
- 현재는 역전되어 있음 (shared → 상위 레이어)

**해결 방법:**
1. shared에서 ir, parsers import 제거
2. DI Container 사용해서 런타임에 주입
3. 또는 ir, parsers를 shared로 이동 (비현실적)

---

### 2. 역할 중복 의심 🔶

**codegraph-engine vs codegraph-ir:**
- 둘 다 "분석 엔진" 역할
- codegraph-engine: 53,226 LOC (Python)
- codegraph-ir: 104,605 LOC (Rust)

**가설:**
1. **마이그레이션 진행 중**: Python engine → Rust ir
2. **역할 분리**: engine = orchestration, ir = core analysis
3. **레거시**: engine은 deprecated 예정?

**조사 필요:**
- engine과 ir의 정확한 역할 구분
- 중복 코드 존재 여부
- 마이그레이션 진행 상황

---

### 3. 규모 불균형 📊

**LOC 분포:**
- codegraph-ir (49.0%) + codegraph-engine (24.9%) = **73.9%**
- 나머지 11개 패키지 = 26.1%

**의미:**
- 2개 패키지가 전체의 3/4 차지
- Monolithic 구조 경향
- 모듈화 개선 가능성

---

### 4. 파일당 LOC 편차 📈

**높은 평균 (>150 LOC/파일):**
- codegraph-orchestration: 220 LOC/파일 🔴 (God class 의심)
- codegraph-ir: 195 LOC/파일 ⚠️

**낮은 평균 (<50 LOC/파일):**
- codegraph-analysis: 40 LOC/파일 ✅
- codegraph-storage: 23 LOC/파일 ✅

**의미:**
- orchestration, ir에 God classes 가능성
- 리팩토링 대상

---

## 코드 품질 추정

### Python 패키지 (10개)

**예상 이슈:**
- Type hints 커버리지 낮을 가능성
- Docstring 부족 가능성
- God classes (특히 engine)
- 코드 중복 (parsers 간)

**측정 필요:**
```bash
# Type hints coverage
mypy --strict packages/codegraph-{shared,engine,runtime}

# Pylint scores
pylint packages/codegraph-{shared,engine,runtime}

# Code duplication
pylint --disable=all --enable=duplicate-code packages/
```

---

### Rust 패키지 (3개)

**codegraph-ir (✅ 최근 개선):**
- ✅ 순환 의존성 0개
- ⏳ unwrap() 998개 (제거 필요)
- ✅ BaseExtractor (중복 제거 인프라)
- ✅ ChunkRepository (DIP 준수)

**codegraph-orchestration (⚠️ 조사 필요):**
- ⚠️ 평균 220 LOC/파일 (God class 의심)
- unwrap() 개수 측정 필요
- 아키텍처 검증 필요

**codegraph-storage (✅ 우수):**
- ✅ 최근 SQLite ChunkStore 구현
- ✅ 작고 명확한 책임
- 평균 23 LOC/파일 (적절)

---

## 리뷰 우선순위 재조정

### Phase 1: Critical Foundation (Week 1) - P0

**1. codegraph-shared (3일) 🔴**
- **이유:** 아키텍처 위반 (shared → ir, parsers)
- **목표:** 의존성 역전 제거, DI Container 재설계
- **Impact:** High (모든 패키지에 영향)

**2. codegraph-storage (1일) ✅**
- **이유:** Base layer, 최근 개선 완료
- **목표:** Port traits 검증, 문서화
- **Impact:** Low (이미 우수)

**3. codegraph-ir (1일) ✅**
- **이유:** 이미 개선 완료
- **목표:** unwrap() 제거 계획 수립
- **Impact:** Medium (선택적)

---

### Phase 2: Core Analysis (Week 2) - P1

**4. codegraph-engine (3일) 🔶**
- **이유:** 53K LOC, 역할 중복 의심
- **목표:** codegraph-ir과 관계 명확화, Rust 마이그레이션 계획
- **Impact:** Very High (24.9% of codebase)

**5. codegraph-trcr (2일)**
- **이유:** 규칙 엔진, 최근 확장
- **목표:** 규칙 검증 자동화, 성능 측정
- **Impact:** Medium

**6. codegraph-parsers (2일)**
- **이유:** codegraph-ir parsers와 관계 불명확
- **목표:** 중복 제거, 역할 명확화
- **Impact:** Medium

---

### Phase 3: Services (Week 3) - P2

**7. codegraph-orchestration (2일) ⚠️**
- **이유:** God class 의심 (220 LOC/파일)
- **목표:** SRP 준수, 리팩토링
- **Impact:** Medium

**8. codegraph-runtime (2일)**
- **이유:** 많은 의존성 (4개)
- **목표:** 의존성 정리, 역할 명확화
- **Impact:** Medium

**9. codegraph-search (2일)**
- **이유:** 검색 엔진, 성능 critical
- **목표:** 인덱스 최적화, 벤치마크
- **Impact:** Medium

**10. codegraph-analysis (1일)**
- **이유:** 작고 명확 (1,530 LOC)
- **목표:** 빠른 리뷰, 개선 사항 식별
- **Impact:** Low

---

### Phase 4: Advanced (Week 4) - P3

**11. codegraph-reasoning (2일)**
- **이유:** 추론 엔진, 복잡도 높음
- **목표:** 알고리즘 검증

**12. codegraph-agent (2일)**
- **이유:** 자율 에이전트, 고급 기능
- **목표:** LLM 통합 검증

**13. codegraph-ml (1일)**
- **이유:** 작고 독립적 (374 LOC)
- **목표:** 빠른 리뷰

---

## 다음 단계

### Immediate (오늘)

1. ✅ 패키지 현황 조사 완료 (이 문서)
2. ⏳ 실제 import 기반 의존성 그래프 작성
   - pyproject.toml 외에 실제 import 문 분석
   - 정확한 의존성 관계 파악
3. ⏳ 주요 이슈 요약 문서 작성

### Week 1 시작 (월요일)

**Day 1-3: codegraph-shared 리뷰 🔴**
- 아키텍처 위반 수정 (shared → ir, parsers)
- DI Container 재설계
- Port traits 정의

**Day 4: codegraph-storage 리뷰 ✅**
- Port traits 검증
- 문서화 개선

**Day 5-7: Summary**
- Foundation layer 개선 요약
- 다음 주 준비

---

## 측정 지표 요약

| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| **순환 의존성** | 2개 (shared → ir, parsers) | 0개 | P0 🔴 |
| **평균 LOC/파일** | 119 | <100 | P2 |
| **God classes** | 조사 필요 | 0개 | P1 |
| **Type hints (Py)** | 조사 필요 | >90% | P1 |
| **unwrap() (Rust)** | ~1000+ | <50 | P1 |
| **Test coverage** | 조사 필요 | >80% | P2 |
| **Code duplication** | 조사 필요 | <10% | P1 |

---

## 종합 평가

### 강점 ✅

1. **codegraph-ir 최근 개선**: 구조적 개선 완료, 목표 성능 1,350% 달성
2. **codegraph-storage 우수**: 작고 명확, 최근 SQLite 구현 완료
3. **명확한 역할**: 대부분 패키지가 명확한 책임
4. **Rust 마이그레이션**: 성능 critical한 부분 Rust 전환 진행

### 약점 ⚠️

1. **아키텍처 위반** 🔴: shared → ir, parsers (Critical!)
2. **역할 중복 의심** 🔶: engine vs ir (조사 필요)
3. **규모 불균형**: 2개 패키지가 74% 차지
4. **God classes 가능성**: orchestration (220 LOC/파일)
5. **의존성 복잡도**: runtime이 4개 패키지 의존

### 기회 💡

1. **Python → Rust 마이그레이션**: engine 일부 이동 가능
2. **코드 중복 제거**: parsers, engine 내부
3. **아키텍처 정리**: shared 의존성 역전 해결
4. **모듈화**: 대형 패키지 분할 가능

### 위협 ⚡

1. **마이그레이션 혼란**: engine vs ir 역할 불명확
2. **기술 부채**: 아키텍처 위반 누적
3. **유지보수 부담**: 규모 불균형

---

**Date:** 2025-12-29
**Status:** ✅ Phase 0 Complete
**Next:** Week 1 - codegraph-shared review
**Critical Issue:** shared → ir, parsers dependency (P0 🔴)

