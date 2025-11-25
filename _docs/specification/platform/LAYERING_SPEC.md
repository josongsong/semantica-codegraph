# Layering Specification

본 문서는 Semantica 기반 레포의 **레이어 구조와 의존성 규칙**을 정의한다.

---

## 목적

- Core 중심의 의존 역전 패턴 유지
- 모듈 간 경계 명확화
- import 방향을 강제하여 변경 비용 감소

---

## 레이어 정의

1. **Core**
   - domain / ports / services
   - 비즈니스 규칙·유즈케이스·추상 인터페이스

2. **Infra (Adapters)**
   - vector store, graph store, relational DB, git, search 등
   - ports 인터페이스 구현체

3. **Interfaces**
   - API / MCP / CLI 외부 인터페이스 계층
   - transport 로직, serialization, route mapping

---

## MUST 규칙

1. Core는 **어느 레이어도 import할 수 없다.**
2. Services는 Ports interface만 import할 수 있다.
3. Infra는 반드시 Ports 인터페이스를 구현해야 한다.
4. Interfaces는 Services를 통해서만 Core를 호출할 수 있다.
5. layer → upper layer import 금지.
   - Infra → Interfaces : 금지
   - Interfaces → Infra : 금지
   - Core → Infra/Interfaces : 금지
6. 순환 import 발생 시 규칙 위반

---

## 금지 규칙

1. Core에서 외부 라이브러리 클라이언트 직접 호출
2. Infra에서 Core 서비스 직접 호출
3. Interfaces에서 Adapter 직접 생성
4. Graph/DB/Git 구현체를 Core에 import

---

## 문서 간 경계

- DI 주입 규칙은 DI_SPEC.md
- Repo 구조는 REPO_STRUCTURE_SPEC.md 참고
