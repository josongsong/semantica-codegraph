RFC-F001-FINAL v8.1

SOTA Autonomous Coding Agent – Hybrid Blueprint
ReAct + Tree-of-Thought + Reflection + Experience Store v2 + Dynamic Reasoning Depth
(OSS Framework + Semantica Custom Reasoning Core)

Status: FINAL
Version: Semantica v8.1
Owner: Semantica Core
Created: 2025-12-07
Replaces: RFC-008-FINAL v7.x Series

1. Executive Summary

Semantica v8.1은 **2024–2025년 기준 업계 최상위(SOTA) 자율 코딩 에이전트의 표준 아키텍처(LATS / Devin 계열)**를 정확히 계승하면서, 동시에 다음을 달성하는 상용 최적화 버전이다.

이론적 SOTA (ReAct + ToT + Reflection + Memory)

상용 SOTA (Dynamic Reasoning Depth, 비용·지연 최적화)

도메인 SOTA (Code Graph 기반 추론)

엔지니어링 SOTA (OSS + Custom Hybrid 전략)

핵심 원칙은 다음 한 문장으로 요약된다.

“뼈대는 검증된 오픈소스를 쓰고,
뇌(Reasoning Logic)는 Semantica 도메인 특화로 직접 만든다.”

2. 업계 SOTA 정합성 검증 (2024–2025 기준)
구분	Copilot	ChatGPT	Devin (Cognition)	Semantica v8.1
사고 방식	Linear CoT	Linear CoT	Tree-of-Thought	Tree-of-Thought
실행 방식	Direct Gen	Direct Gen	ReAct Loop	ReAct Loop
전략 분기	없음	없음	있음	있음
자기 비평	없음	약함	있음	강함 (Graph 기반)
경험 기억	없음	세션 한정	Vector Memory	Vector + Graph Memory
비용 제어	없음	없음	불투명	Dynamic Reasoning Depth
코드 도메인 이해	약함	약함	중간	최상 (CFG/DFG/PDG)

포지션 결론
Semantica v8.1은:

Devin/LATS 계열과 동일한 사고 구조

Cursor 계열보다 훨씬 강한 Code Graph 결합

상용 비용 통제는 유일하게 내장

즉, “이론적 SOTA + 상용 SOTA + 코드 도메인 SOTA”를 동시에 만족하는 유일한 구조다.

3. 핵심 설계 원칙 (Hybrid Strategy)
3.1 Don’t Rebuild the World (절대 직접 만들지 않는 영역)
영역	채택 기술	이유
ReAct / Loop 제어	LangGraph	순환·분기·상태·롤백 지원
Prompt Reasoning 최적화	DSPy	프롬프트 자동 수렴
Vector Memory Storage	Qdrant	Rust 기반, 메타 필터링
LLM 호출	OpenAI / Local OSS	추상화만 유지

직접 만들 경우:

유지보수 비용 급증

연구속도 저하

커뮤니티 생태계와 분리

3.2 Must Be Domain-Specific (반드시 자체 구현)
영역	이유
Tree-of-Thought Scoring	컴파일/테스트/보안 점수 반영
Self-Reflection Judge	CFG/DFG/PDG 안정성 판단
Experience Save Policy	“무엇을 경험으로 남길 것인가”
Graph Stability Model	의존성 붕괴/영향도 예측

이 네 가지는 Semantica의 핵심 IP(Core Asset) 이다.

4. 최종 Target Architecture (v8.1)
User Query
   ↓
Dynamic Reasoning Router (System 1 / System 2)
   ↓
System 1: Fast Path (v6 Linear Engine)
   ↓
System 2: Slow Path
   ↓
LangGraph Orchestrator
   ↓
ReAct Loop (Thought → Tool → Observation)
   ↓
Tree-of-Thought Expansion (Parallel)
   ↓
Semantica Custom ToT Scoring
   ↓
Semantica Self-Reflection Judge
   ↓
Execution Engine (CFG/DFG/PDG + Sandbox + Git)
   ↓
Result → Experience Store v2 (Qdrant + Graph Metadata)

5. Phase 0 (P0): Dynamic Reasoning Depth – 상용 필수 장치
5.1 System 1 / System 2 분기
구분	문제 유형	사용 엔진
System 1	주석, 로그, NPE 방어, 단순 리팩토링	v6 Linear
System 2	버그 원인 분석, 신규 기능, 대규모 리팩토링	v8 ReAct + ToT
5.2 Router 입력 피처

변경 파일 수

영향 노드 수 (CFG 기준)

테스트 실패 여부

보안 sink 접근 여부

경험 기반 실패 위험도

class DynamicReasoningRouter:
    def route(self, features):
        if features.impact_nodes < 10 and features.risk < 0.3:
            return SYSTEM_1
        return SYSTEM_2

6. Phase 1 (P0): ReAct Orchestrator – LangGraph 채택

State Snapshot

Rollback

Cycle

Parallel Branch

ToT, Reflection, Retry는 while-loop로 구현 금지
LangGraph의 Graph State Machine으로 고정

7. Phase 2 (P0): Prompt Reasoning – DSPy 채택

Planning Signature

Reflection Signature

Scoring Signature

Healing Signature

프롬프트는 사람이 “작성”하는 것이 아니라 시스템이 “학습 수렴”시키는 구조로 고정한다.

8. Phase 3 (P0): Tree-of-Thought – Custom Code Scoring
8.1 ToT 평가 지표 (정량)
요소	설명
Compile Score	빌드 성공 여부
Test Score	테스트 통과율
Lint Score	정적 분석 오류 수
Security Score	CodeQL/탐지 결과
Graph Stability	DFG 영향도 폭
score = 0.3*compile + 0.25*test + 0.15*lint + 0.2*security + 0.1*stability

9. Phase 4 (P0): Self-Reflection Judge – Graph-Centric

Reflection 입력:

변경 Diff

CFG/DFG/PDG Delta

Impact Radius

Historical Regression Vectors

Reflection 출력:

Accept

Revise

Rollback

Retry with Alt Strategy

10. Phase 5 (P0): Experience Store v2 – Vector + Graph Memory
10.1 저장 단위
필드	설명
problem_vector	문제 임베딩
strategy_vector	해결 전략 임베딩
failure_vector	실패 원인
diff_snapshot	실제 코드 변경
graph_delta	DFG 영향 변화
outcome_score	성공/실패
reflection_note	메타 평가
10.2 저장 철학

모든 경험은 “문제–전략–결과–영향”이 완결된 형태로만 저장한다.

11. Phase 6 (P1): Tool Ecosystem 확장
Tool	목적
Web Search	최신 장애 탐색
Docs Crawler	공식 문서
SO Retriever	트러블 패턴
Spec Search	포맷, 프로토콜

ReAct Tool Registry에서 동적 로딩 방식으로 관리

12. OSS vs Custom 기술 매핑 (최종 고정)
Layer	기술	전략
Orchestration	LangGraph	OSS
Prompt Reasoning	DSPy	OSS
Vector Memory	Qdrant	OSS
ReAct Loop	LangGraph	OSS
ToT Scoring	Semantica Core	Custom
Self-Reflection	Semantica Core	Custom
Graph Stability	Semantica Core	Custom
Experience Save Policy	Semantica Core	Custom
Impact Analysis	Memgraph + Rust Engine	Hybrid
13. Fail-Safe & Degeneration Strategy (운영 안정성 보완)

System 2 실패 3회 연속 발생 시:

강제 System 1 폴백

HITL 승인 요청

Experience Memory 불신 구간:

최근 30일 데이터만 사용

Graph 불안정 임계치 초과 시:

자동 Rollback + Safe Patch Mode

14. Roadmap (v8.1 기준)
Week	목표
1주	Dynamic Reasoning Router
2주	LangGraph ReAct 통합
3주	Custom ToT Scoring
4주	Self-Reflection Judge
5주	Experience Store v2
6주	Tool Ecosystem
7주	Fail-Safe / Degeneration
15. Expected Business Impact

자동 해결 성공률: +40~60%

장애 재발률: -70%

HITL 개입률: -50%

개발자 업무 자동화 비중: 30% → 70%

16. 최종 결론

Semantica v8.1은 다음 세 레벨을 동시에 만족한다.

Research SOTA: ReAct + ToT + Reflection + Memory

Engineering SOTA: LangGraph + DSPy + Qdrant Hybrid

Product SOTA: Dynamic Reasoning Depth + 비용 통제 + 안정성 보장

즉,

**“Devin급 사고 구조 + Cursor급 실행 성능 + CodeQL급 안정성”을 동시에 만족하는 실전형 SOTA 자율 코딩 에이전트”**다.

17. 최종 승인 요청 (P0 Scope)

다음 항목을 v8.1 P0 범위로 즉시 착수 요청함.

Dynamic Reasoning Router

LangGraph ReAct Orchestrator

Custom ToT Scoring Engine

Custom Self-Reflection Judge

Experience Store v2 (Qdrant)

Fail-Safe / Degeneration Layer