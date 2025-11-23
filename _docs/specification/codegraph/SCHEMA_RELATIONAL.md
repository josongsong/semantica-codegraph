# Relational Schema Specification

**문서 목적:**
PostgreSQL 스키마 MUST

**범위:**
PK/FK/constraints

**버전:** v1.0
**최종 수정:** 2025-01-23

---

## 1. 핵심 원칙 (MUST)

- Truth of Record: Postgres는 그래프/벡터의 기준 소스이다. 모든 노드(SemanticaNode)와 관계 메타는 여기서 파생된다.
- Flattened Joins 최소화: 조회는 chunk_id/file_id/repo_id 단일 키로 가능하게 하고, 대용량 조인은 피한다.
- Delta 우선: PR/Commit/Branch는 TOUCHES 관계로만 변경분을 표현하고, 동일 Chunk의 중복 저장을 금한다.
- Future-proof: `attrs JSONB`로 스키마 변경 없이 확장한다. Enum 확장은 값만 추가하고 테이블 구조는 유지한다.
- Deduplication Layer: `branch_chunk_mapping`으로 Branch → Chunk 참조를 저장해 저장소 간 중복을 제거한다.

---

## 2. 금지 규칙 (MUST NOT)

- Chunk 본문을 Branch/PR별로 복제하지 않는다. content_hash/canonical_commit로 유일하게 유지한다.
- 필수 키(repo_id/project_id/file_id/chunk_id) 없이 외래키 무결성을 깨지 않는다.
- attrs 없이 새 컬럼을 추가하는 방식으로 확장하지 않는다. (마이그레이션 최소화)
- Temporal/Git 컨텍스트를 문자열 blob으로 넣지 않는다. 컬럼/JSONB로 질의 가능하게 저장한다.

---

## 3. 예시 (참조)

- 좋은 예시
  - `repositories(id, name, remote_url, default_branch, attrs jsonb)`
  - `commits(id, repo_id, hash, authored_at, author, parents text[], message, attrs jsonb)`
  - `leaf_chunks(id, file_id, content_hash, canonical_commit, code_range, language, git_context jsonb, security_context jsonb, attrs jsonb)`
  - `branch_chunk_mapping(repo_id, branch_name, commit_hash, chunk_id)` PK `(repo_id, branch_name, chunk_id)`
- 나쁜 예시
  - PR마다 leaf_chunks를 새로 INSERT하여 동일 content_hash가 다수 생성
  - attrs 없이 새로운 컬럼 추가를 반복해 마이그레이션 증가
  - commit.parents를 문자열 쉼표 구분으로 저장해 질의 불가

---

## 4. 체크리스트

- [ ] Repository/Branch/Commit/PR/Tag 테이블과 FK가 정의되어 있는가
- [ ] Project/Module/File/Symbol/LeafChunk 테이블에 node_id와 상위 참조 키가 있는가
- [ ] branch_chunk_mapping으로 브랜치별 Chunk 참조를 중복 없이 관리하는가
- [ ] attrs(JSONB)로 확장 필드를 수용하고 인덱스가 필요한 키는 GIN 인덱스를 갖는가
- [ ] content_hash + canonical_commit로 Chunk 유일성 제약을 갖추었는가
- [ ] TOUCHES/ORIGIN_COMMIT 등 관계를 별도 테이블 또는 JSONB로 질의 가능하게 보관하는가

---

## 5. 참고 자료

- `_docs_legacy/northstar/_C_03_schema_core.md` (Relational 노드/BranchChunkMapping 정의)
- `infra/db/schema.sql` (실제 테이블 정의)
