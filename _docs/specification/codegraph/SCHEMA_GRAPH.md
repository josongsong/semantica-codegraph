# Graph Schema Specification

**문서 목적:**
Kùzu node/rel 스키마 MUST

**범위:**
CodeNode/Calls/Defines

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 핵심 원칙 (MUST)

- Logical Tree 유지: Repository → Project → Module → File → Symbol → LeafChunk 계층을 그래프 노드로 보존한다.
- Polymorphic Asset: 코드/테스트/문서/설정/바이너리 모든 파일을 `file`/`symbol` 노드로 수용하고 `category`/`attrs`로 구분한다.
- Generic Edge: 관계는 `RelationshipType` Enum 확장으로 추가 가능해야 하며, 스키마 변경 없이 attrs/metadata에 저장한다.
- Dynamic Context Layering: TOUCHES(Relationship), ORIGIN_COMMIT, Security/Git 컨텍스트를 노드에 보유해 시계열/ACL 그래프 탐색을 지원한다.
- Agent-First: SymbolNode에 `interface_contract`(시그니처/visibility/parameters)와 `behavioral_tags`가 연결된 Chunk를 매핑한다.

---

## 2. 금지 규칙 (MUST NOT)

- Graph 스키마 확장 시 기존 노드/관계를 삭제하거나 재정의하지 않는다. 새 타입은 Enum 확장/attrs로 표현한다.
- File → Symbol → Chunk 경로를 우회하거나 건너뛰어 직접 Chunk만 연결하지 않는다.
- PR/Commit을 물리적 복제본으로 저장하지 않는다. TOUCHES/ORIGIN_COMMIT 관계로 참조만 둔다.
- Binary/Doc 등을 별도 타입으로 분기하지 않는다. 공통 노드 스키마를 유지하고 파싱 불가 시 내용을 비워둔다.

---

## 3. 예시 (참조)

- 좋은 예시
  - `repository (repo:codegraph)` → `project (proj:api)` → `file (file:services/api/user.py)` → `symbol (sym:user.service.get_user)` → `leaf_chunk (chunk:user.py:10-42)`
  - 관계: `CALLS(sym:user.repo.fetch_user)`, `TESTS(sym:test_user_service)`, `TOUCHES(pr:1234)`, `DOCUMENTS(sym:docs.user.md)`
- 나쁜 예시
  - Chunk만 노드로 두고 File/Symbol 노드를 생성하지 않음
  - PR을 별도 파일 노드로 복제해 변경분을 저장
  - 관계 타입을 자유 문자열로 저장해 쿼리 불가능

---

## 4. 체크리스트

- [ ] Repository/Branch/Commit/PR/Tag 노드 정의했고 hash/id 필수 필드를 채웠는가
- [ ] Project/Module/File/Symbol/LeafChunk 노드에 node_type, 계층 부모 식별자를 포함했는가
- [ ] RelationshipType Enum(CALLS/TESTS/TOUCHES/DOCUMENTS/IMPORTS/DEFINES/INHERITS/IMPLEMENTS/DEPENDS_ON/RELATED_CVE/GENERATED_FROM/ORIGIN_COMMIT 등) 확장을 수용하도록 설계했는가
- [ ] TOUCHES/ORIGIN_COMMIT 관계로 델타를 표현하고 중복 노드를 만들지 않는가
- [ ] attrs/metadata로 스키마 없는 확장을 허용했는가

---

## 5. 참고 자료

- `_docs_legacy/northstar/_C_03_schema_core.md` (Node/Relationship 모델)
- `core/core/domain/graph.py` (RelationshipType/BaseSemanticaNode)
- `core/core/domain/nodes.py` (Git/Logical 노드 정의)
