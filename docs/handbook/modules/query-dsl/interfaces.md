# Query DSL - Interfaces

**
**Scope:** 외부 사용 관점의 Query DSL 인터페이스 요약  

---

## Core Concepts

- **QueryEngine**: IR/Graph 기반 질의 실행기
- **Q**: 노드/패턴 셀렉터(Var/Call/Attr/Source/Sink 등)
- **E**: 엣지 타입(DFG/CFG/CallGraph 등)
- **FlowExpr**: `Q... >> Q...` 형태의 선언식 표현 → 내부적으로 그래프 순회로 컴파일

---

## Typical Usage

- **Dataflow**: `(Q.Var("a") >> Q.Var("b")).via(E.DFG)`
- **Security**: `(Q.Source("request") >> Q.Sink("execute")).via(E.DFG)`

---

## IDs / Join

- 검색/리트리벌과 결합할 때 최종 조인은 보통 `chunk_id` (SearchHit 표준 키)

---

## Links

- 상세 아키텍처: `architecture.md`

