# Vector Schema Specification

**문서 목적:**
Qdrant payload/metadata MUST

**범위:**
embedding 버전 관리

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 핵심 원칙 (MUST)

- Logical Tree → Physical Flat: LeafChunk에서 부모 컨텍스트(Repo/Project/File/Symbol)를 모두 평탄화해 조인 없이 조회 가능해야 한다.
- Agent-First: `summary`/`embedding_source`는 에이전트 프롬프트 품질을 위해 Chunk 단위 최소 요약 또는 임베딩 텍스트를 쓴다.
- Relationship 승격: CALLS/TESTS/TOUCHES/DOCUMENTS 관계는 전용 리스트 필드에 승격하고, 나머지는 `extra`에 백업한다.
- Immutable by content: `content_hash`와 `id(Chunk ID)`로 중복을 제거하고 델타를 PR/Commit TOUCHES 관계로만 표현한다.
- Future-proof: 스키마 변경 없이 새 메타데이터를 `extra`에 수용한다.

---

## 2. 금지 규칙 (MUST NOT)

- 부모 노드를 조인해야만 이해되는 필드를 두지 않는다. (Flat payload 내에 모든 상위 식별자/URI 포함)
- 관계 타입을 하드코딩해 누락을 초래하지 않는다. 정의되지 않은 관계는 `extra.rel_*`에 반드시 백업한다.
- ACL/Temporal 컨텍스트를 비워두지 않는다. `last_modified_at`/`change_frequency`는 가능하면 항상 채운다.
- Chunk 본문 없이 임베딩 텍스트만 넣어서는 안 된다. `content`가 없으면 `summary` 최소 요약을 제공한다.

---

## 3. 예시 (참조)

- 좋은 예시
  - `uri`: `services/api/user.py#L10-L42`
  - `tags`: `{"is_test": false, "has_side_effect": true, "db_call": true, ...}`
  - `rel_calls`: `["sym:user.repo.fetch_user", "sym:auth.service.require_scope"]`
  - `rel_touches`: `["pr:1234", "commit:abc123"]`
  - `extra`: `{"attrs_owner_team": "platform", "rel_depends_on": ["sym:common.logging"]}`
- 나쁜 예시
  - `uri` 없이 file_path만 저장
  - `rel_calls`/`rel_tests`를 attrs 안에 중첩 배열로 넣어 쿼리 불가
  - `content_hash` 누락으로 중복 Chunk 다중 삽입

---

## 4. 체크리스트

- [ ] `id`, `repo_id`, `project_id`, `file_id`, `file_path`, `uri`, `language` 필수 필드 채웠는가
- [ ] `summary`는 `minimal_summary` → `embedding_text` 우선순위로 세팅했는가
- [ ] `tags`는 `behavioral_tags`를 그대로 덤프했는가
- [ ] CALLS/TESTS/TOUCHES/DOCUMENTS 관계를 승격했고 기타는 `extra.rel_*`에 백업했는가
- [ ] `last_modified_at`/`change_frequency`를 GitContext에서 가져왔는가
- [ ] `content_hash`로 idempotent upsert 가능한가

---

## 5. 참고 자료

- `_docs_legacy/northstar/_C_03_schema_core.md` (Canonical Leaf → Vector Payload 매퍼)
- `core/core/domain/chunks.py` (CanonicalLeafChunk → VectorChunkPayload 매퍼)
