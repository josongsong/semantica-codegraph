## Core Roadmap: AI 코드 파악 엔진 (Execution Roadmap)

**문서 목적**
- **AI가 코드 파악을 잘하게 만드는 엔진 기능**을 단계적으로 완성하는 실행 로드맵을 고정한다.
- 보안분석/코드스멜/리팩토링 자동화를 **동일 기반(Query/Summary/Slice/Evidence)** 위에서 확장 가능하게 만든다.

**원칙**
- **기반 먼저**: Query 실행, Summary, Slice, Evidence를 먼저 고정
- **확장 나중**: 도메인(보안/Auth, 스멜, 리팩토링)은 기반 위에 규칙/모델로 얹기
- **검증 우선**: 모든 단계는 “테스트로 ✅ 승격” 기준을 통과해야 다음 단계로 진행

---

## Current State (프로젝트 기준 현 상태)

**정적분석 커버리지(coverage matrix)**
- 기준 문서: `_docs/system-handbook/static-analysis-coverage.md`
- 총계: **111개 항목 중 ~91% 커버리지(완전 87 / 일부 12 / 미구현 12)**
- 약점 영역(갭이 명확): **동시성(20%) / 수치·값 분석(20%) / 문자열 분석(0%)**

**기법 구현 상태(techniques 120개 체크리스트)**
- 기준 문서: `_docs/system-handbook/static-analysis-techniques.md`
- 현재 기준: **✅ 73 / ⚠️ 11 / ❌ 36**
- ⚠️→✅ 승격은 “문구/설정 존재”가 아니라 **입력→출력 재현 가능한 테스트**로만 인정

**이미 고정된 P0 계약**
- QueryDSL Contract: `_docs/_backlog/ADR-002: Queryengine.md` (v3.3, breaking 금지)

---

## Target State (AI 코드 파악 능력의 정의)

AI가 “파일 전체” 없이도 아래를 **결정적으로 재현**할 수 있어야 한다.
- **Query**: 경로/흐름/호출/영향을 질의로 실행한다.
- **Evidence**: 모든 finding은 증거(경로/노드/엣지)로 설명 가능하다.
- **Slice**: LLM 입력용 Mini IRDoc(슬라이스)가 자동 생성된다.
- **Summary(FSG)**: 함수/모듈 단위 요약 그래프가 캐시/증분 갱신된다.
- **Change Impact(CIG)**: diff → 영향 심볼/경로/테스트가 재현 가능하게 산출된다.

---

## 최상위 아키텍처 로드맵 (Layer 0~2)

### Layer 0: 공통 기반 계층 (P0)
- Evidence/Claim Contract
- Unified Graph View API
- QueryDSL Execution Engine
- Slice Materialization (Mini IRDoc)
- Summary Graph(FSG) + Cache
- Change Impact Graph(CIG)

### Layer 1: 분석 정확도 계층 (P1)
- Typed Expression IR 확장(DFG/expr “실측 0” 현상 개선)
- Context Sensitivity ✅ 승격
- Object Sensitivity 최소 정통 구현
- Exceptional CFG 정밀화
- IFDS/IDE Solver 적용 범위 확장(공용 기반)

### Layer 2: 제품 기능 계층(도메인) (P2)
- 보안: AuthN/AuthZ/Session 모델 + Principal Flow
- 코드스멜: 증거 기반 스코어링 + change coupling
- 리팩토링: Safety Harness + pattern-to-patch

---

## Phased Roadmap (Phase 0~4)

### Phase 0. 로드맵/스펙 고정 (Contract-First)
**산출물**
- 본 문서(`_docs/_backlog/core_roadmap.md`)
- 공통 Contract 문서 4종(별도 파일로 분리 가능):
  - Evidence/Claim
  - QueryDSL Execution Contract (기존 ADR-002에 “Execution/Result 안정성” 부록 추가)
  - Graph View Contract
  - Summary Contract

**완료 기준(✅ 승격)**
- 각 Contract에 대해 **입력/출력/버전/호환 정책** 확정
- 최소 10개 대표 질의가 Contract로 표현됨(예: Golden Query Suite로 고정)

### Phase 1. Query + Evidence 기반 완성 (Execution First)
**핵심 작업**
- QueryDSL Full Execution Engine 구현(경로 실행→paths 산출)
- Evidence/Claim 파이프라인 연결(모든 finding 표준 출력)
- Unified Graph View(단일 진입점으로 CFG/DFG/PDG/Taint 접근)
- Slice Materialization(Mini IRDoc 생성)

**완료 기준(✅ 승격)**
- QueryDSL로 “경로”가 실제로 실행되어 **paths**가 산출됨
- 핵심 쿼리 회귀 테스트 통과(최소 20개)
- Claim에 Evidence path가 **항상** 포함됨

### Phase 2. Summary + Change Impact 완성 (Determinism First)
**핵심 작업**
- Function Summary Graph(FSG) 생성/저장/증분 invalidation
- Change Impact Graph(CIG): diff → 영향 심볼/경로/테스트 산출
- 캐시 전략: summary cache + slice cache

**완료 기준(✅ 승격)**
- “변경 1줄” 입력 시 영향 범위가 **결정적으로 동일 출력**
- AI가 파일 전체 없이 **summary+slice로** 문제 설명 가능

### Phase 3. 정확도 상향(고급 분석)
**핵심 작업**
- Typed Expression IR 확장(표현식/DFG 변수 “0” 현상 개선)
- Context Sensitivity ✅ 승격(테스트 포함)
- Object Sensitivity 최소 정통 구현(객체/할당지점 기준 분리 재현)
- Exceptional CFG 정밀화
- IFDS/IDE Solver 적용 범위 확장(보안/스멜 공용)

**완료 기준(✅ 승격)**
- “call-site별 결과 차이”가 테스트로 재현됨
- object별 alias/taint 분리가 테스트로 재현됨
- 예외 경로에서 false negative 감소를 회귀로 확인

### Phase 4. 도메인 기능 확장(보안/스멜/리팩토링)
**보안**
- AuthN/AuthZ/Session 모델 + Principal Flow
- Guard 패턴 인식(allowlist/denylist/early return)
- Sanitizer semantics를 ESCAPES edge로 모델링

**코드스멜**
- 증거 기반 스멜 스코어링(복잡도+effect+change coupling)
- API misuse 최소 세트(타입+effect 기반)

**리팩토링**
- Refactor Safety Harness(영향/동치/회귀 검증)
- pattern-to-patch(스멜/보안 finding → 패치 템플릿)

**완료 기준(✅ 승격)**
- 보안: Auth 관련 3개 대표 시나리오 end-to-end 재현
- 스멜: 10개 스멜이 evidence 포함 finding으로 출력
- 리팩토링: 3개 자동 리팩토링이 “안전장치+회귀 검증”과 함께 동작

---

## 우선순위 매트릭스 (P0/P1/P2)

### P0 (즉시 고정)
- QueryDSL Execution
- Evidence/Claim
- Unified Graph View
- Slice Materialization
- Summary Graph(FSG)
- Change Impact Graph(CIG)

### P1 (정확도 투자)
- Typed Expression IR 확장
- Context Sensitivity ✅ 승격
- Object Sensitivity 정통 최소
- Exceptional CFG
- IFDS/IDE Solver

### P2 (제품 기능 확장)
- AuthN/AuthZ/Session 모델 범위 확대
- 스멜 rule 세트 확장
- 리팩토링 템플릿 라이브러리 확대

---

## ✅승격 기준: 테스트/fixture 레퍼런스 (현재 구현 기반)

“대표 질의/회귀 팩”을 지금 있는 fixture 스타일로 고정한다.

**기존 fixture / golden 레퍼런스**
- 전역 pytest fixture: `tests/conftest.py` (`temp_dir`, `mock_repo_path`)
- Integration Golden Query Suite(딕셔너리 기반): `tests/integration/conftest.py::golden_queries`
- Integration 환경 핸들(session fixtures): `tests/integration/conftest.py` (`symbol_index`, `vector_index`, `lexical_index`, `graph_store`)
- Infra 설정 fixture: `tests/unit/infra/conftest.py::mock_settings`
- 파서 테스트 헬퍼: `tests/helpers/tree_sitter_helpers.py`
- (스펙만 존재) 파일 기반 golden snapshot parity: `tests/migration/test_query_engine_parity.py`
  - 현재 `tests/fixtures/golden/*.json` 디렉토리는 미존재(없으면 빈 목록), 테스트는 skip 상태

**권장 정책(Phase 0에 고정)**
- Golden Query Suite(대표 질의 10개)는 **입력/기대 출력/정렬 규칙/안정 ID**까지 포함해서 계약화
- Phase 2의 “동일 출력”을 위해 결과는 **canonical ordering + stable id**가 필수

---

## Dependencies & Sequencing (Chronological)

- Phase 0: Contract 고정(특히 QueryDSL 실행 결과의 안정성/정렬/ID/버전)
- Phase 1: Query 실행 + Evidence + Slice를 end-to-end로 연결
- Phase 2: Summary/Impact를 “결정성” 기준으로 고정(캐시/증분 무효화 포함)
- Phase 3: 정확도 투자(특히 Context/Object/Exception/IFDS-IDE)
- Phase 4: 도메인 룰/모델은 기반 위에서만 확장

---

## Appendix

**문서 참조**
- `_docs/system-handbook/static-analysis-techniques.md`
- `_docs/system-handbook/static-analysis-coverage.md`
- `_docs/_backlog/ADR-002: Queryengine.md`


