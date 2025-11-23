# Lexical Schema Specification

**문서 목적:**
Meilisearch/Zoekt 스키마 MUST

**범위:**
searchable/filterable 필드

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 핵심 원칙 (MUST)

- Flatten-first: Zoekt/Meilisearch 문서는 LeafChunk의 부모 컨텍스트를 평탄화해 `repo_id/project_id/file_path/uri`를 포함한다.
- Identifier-centric: `lexical_features.identifiers`를 1급 필드로 인덱싱하고, string_literals/comments/special_tokens로 보강한다.
- Relation-aware: CALLS/TESTS/TOUCHES/DOCUMENTS 주요 관계를 필터/부스트용으로 별도 필드에 저장한다.
- Temporal-aware: `last_modified_at`/`change_frequency`를 검색 필터로 노출해 최신 변경 검색을 지원한다.
- ACL-aware: SecurityLevel을 태그로 저장해 테넌트 필터링을 강제한다.

---

## 2. 금지 규칙 (MUST NOT)

- 파일 경로만 저장하고 URI(라인 범위)를 누락하지 않는다.
- identifiers를 토큰화 없이 긴 문자열로 붙이지 않는다. 배열 형태로 저장한다.
- PR/Commit 정보를 문자열로 병합하지 않는다. `rel_touches` 필드를 별도 유지한다.
- ACL/Temporal 필드를 검색 인덱스에 누락하지 않는다.

---

## 3. 예시 (참조)

- 좋은 예시
  - `uri`: `services/api/user.py#L10-L42`
  - `identifiers`: `["get_user", "UserService", "fetch_user"]`
  - `string_literals`: `["user not found"]`
  - `rel_calls`: `["sym:user.repo.fetch_user"]`, `rel_tests`: `["sym:test_user_service"]`
  - `last_modified_at`: `2025-01-20T12:30:00Z`, `security_level`: `internal`
- 나쁜 예시
  - `identifiers`를 `"get_user UserService fetch_user"` 한 문자열로 저장
  - `rel_touches` 없이 PR 기반 델타를 식별 불가
  - `uri` 없이 file_path만 제공해 스니펫 하이라이트 불가

---

## 4. 체크리스트

- [ ] `repo_id/project_id/file_id/file_path/uri/language` 포함
- [ ] `identifiers/string_literals/comments/special_tokens` 배열로 저장
- [ ] `rel_calls/rel_tests/rel_touches/rel_documents` 필드 분리
- [ ] `last_modified_at/change_frequency/security_level` 필터 필드 포함
- [ ] `content_hash` 또는 `chunk_id`로 중복 방지 키 설정

---

## 5. 참고 자료

- `_docs_legacy/northstar/_C_03_schema_core.md` (LexicalFeatures 정의)
- `core/core/domain/context.py` (LexicalFeatures/BehavioralTags 정의)
