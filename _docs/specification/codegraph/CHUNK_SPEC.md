# Chunk Specification

**문서 목적:**
LeafChunk/CanonicalChunk MUST

**범위:**
boundary/필드/token_estimate

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 핵심 원칙 (MUST)

- Canonical Leaf Chunk는 엔진 내부의 Rich Representation이다. content_hash로 브랜치 간 중복을 제거하고, canonical_commit으로 기원을 추적한다.
- Chunk는 Symbol/Repo/Project/File 계층을 모두 보유해 부모 컨텍스트 없이도 독립적으로 식별·검색 가능해야 한다.
- Agent-First: `behavioral_tags`(side effect, io/db/network, is_test 등)와 `error_context`(raises/handles)를 포함해 계획 수립에 활용한다.
- Dynamic Layering: GitContext(시간/작성자/빈도), SecurityContext(ACL) 등 정적/동적 신호를 함께 담는다.
- Lexical + Semantic 병행: `lexical_features`(identifiers/strings/comments)와 `semantic_features.embedding_text`를 동시에 유지한다.

---

## 2. 금지 규칙 (MUST NOT)

- 파일 파싱 불가 시에도 Chunk를 누락하지 않는다. (binary 등은 내용 없이 메타데이터만)
- 부모 노드로만 추론 가능한 필드(언어, 파일 경로 등)를 비워두지 않는다.
- behavioral_tags를 수동 조립하거나 생략하지 않는다. 기본값이라도 항상 채운다.
- change_frequency/last_modified_at 없는 GitContext로 덮어써서 Temporal 신호를 잃지 않는다.

---

## 3. 예시 (참조)

- 좋은 예시
  - `node_id`: `chunk:services/api/user.py:10-42`
  - `code_range`: `{start_line: 10, end_line: 42}`
  - `behavioral_tags`: `{is_test: false, has_side_effect: true, db_call: true, io_call: false, ...}`
  - `relationships`: `[{"type": "calls", "target_id": "sym:user.repo.fetch_user"}]`
- 나쁜 예시
  - `content_hash` 없이 Chunk를 생성
  - `behavioral_tags`/`error_context`를 빈 객체로 제거
  - `lexical_features.identifiers` 없이 semantic_text만 채움

---

## 4. 체크리스트

- [ ] `node_id`, `repo_id`, `project_id`, `file_id`, `file_path` 필수
- [ ] `language`, `code_range`, `content_hash`, `canonical_commit` 채움
- [ ] `lexical_features`와 `semantic_features.embedding_text` 모두 존재
- [ ] `behavioral_tags`, `error_context` 포함 (기본값이라도)
- [ ] Git/Security 컨텍스트가 있으면 바인딩했고, 없으면 None으로 명시
- [ ] 부모 컨텍스트 없이도 URI 및 호출 관계를 구성 가능

---

## 5. 참고 자료

- `_docs_legacy/northstar/_C_03_schema_core.md` (CanonicalLeafChunk 정의)
- `core/core/domain/chunks.py` (CanonicalLeafChunk/VectorChunkPayload)
