1. 초기 인덱싱 시나리오

1-1. 최초 레포 인덱싱

전체 파일 AST → IR(Node/Edge/Type) 생성

스냅샷 JSON 생성

DB(ir_nodes/ir_edges/ir_types) 저장

IRStore(메모리) 로딩

1-2. 브랜치 첫 인덱싱

branch:xxx@commit 형태 snapshot 생성

baseline으로 저장

2. 실시간 개발 워크스페이스 시나리오

2-1. 파일 저장/변경

변경 파일만 AST/IR 재생성

diff 계산

IRStore 즉시 갱신

DB 비동기 반영

2-2. 다중 파일 리팩터링(rename/move/extract)

모든 변경 파일 묶어서 트랜잭션 처리

IRStore에 한 번에 적용

실패 시 rollback

2-3. Multi-editor / Multi-client 동시 작업

이벤트를 IndexingDispatcher에 직렬화

snapshot_id 증가

IRStore 정합성 유지

2-4. git merge conflict

충돌 파일 AST INVALID

노드 상태 VALID|INVALID|PARTIAL 관리

Edge 생성은 VALID만

LLM에게 상태를 명확히 알려줄 수 있음

3. Git 기반 변경 시나리오

3-1. checkout / pull / rebase

changed files만 인덱싱

새 snapshot_id (commit 기준) 생성

IRStore 교체(refresh)

3-2. PR 비교/diff

과거 스냅샷을 메모리에 임시 로드

현재 워크스페이스와 비교

분석 후 unload

3-3. branch merge 후 정식 스냅샷

“branch:main@{commit}” 스냅샷 생성

DB/JSON 업데이트

4. 전체 재인덱싱 시나리오

4-1. 대규모 변경 또는 엔진 업데이트

repo 전체 AST/IR 재생성

snapshot 새로 생성

DB 전체 upsert

기존 인덱스들(BM25/vector/symbol) 재빌드 가능

4-2. Monorepo multi-module

module 단위 snapshot

IRStore module별 분리 가능

5. 스냅샷/버전 관리 시나리오

5-1. 불변 스냅샷(JSON) 생성

재현성

회귀 테스트

버전 비교

장애 복구

5-2. Freeze / Archive

오래된 snapshot을 장기 보관(S3 등)

압축 + 검증 해시 포함

5-3. Timetravel / rewind

특정 스냅샷을 IRStore에 임시 로딩

분석 후 unload

워크스페이스 상태는 그대로 유지

5-4. Experimental snapshot

실험용 파서/청커 적용

repo 상태 오염 없이 별도 snapshot 생성

6. 인덱스 연동 시나리오 (Chunk/BM25/Vector/Symbol 등)

6-1. IR diff 기반 인덱스 부분 업데이트

changed nodes → changed chunks

changed chunks → BM25/vector 부분 upsert

6-2. 전체 인덱싱 → 전체 index rebuild

브랜치 main 혹은 nightly 빌드에서만 수행

6-3. 실시간 인덱서 반영

IRStore 업데이트 후,
각 인덱서가 변경 파일 단위로 수신해 미니 업데이트

7. 외부 의존성 시나리오 (node_modules, site-packages 등)

7-1. Partial IR 생성

클래스/함수 signature 수준만

Node/Edge 최소 세트만 기록

7-2. 참조 해석

IMPORTS, REFERENCES만 파싱

unresolved 심볼은 external 타입 처리

8. 성능/운영 시나리오

8-1. IRStore cold start 최적화

sharded preload

필요 파일만 즉시 로딩

나머지는 백그라운드 로딩

8-2. 병렬 인덱싱

파일 단위 sharding

병렬 AST/IR 생성

merge 단계에서 Node/Edge sync

8-3. 메모리 압축/eviction

오래 접근하지 않은 파일 단위 unload

DB/JSON에서 필요 시 다시 로딩

9. 에이전트/LLM 시나리오

9-1. LLM toolcall → IRStore 즉시 접근

find-def, find-refs, call graph

file/module/class 단위 구조 탐색

9-2. 과거 스냅샷 요청

해당 스냅샷을 임시 IRStore로 로딩

작업 후 삭제

9-3. 리팩터링 적용

LLM-generated patch → IR diff 적용 → index diff 반영

일관성 확보

10. 장애/복구 시나리오

10-1. DB 손상

스냅샷 JSON 기반으로 전체 복원

10-2. 인덱스(BM25/vector) 손상

IRStore → 재생성

또는 JSON/DB 기반 재생성

10-3. IRStore crash

마지막 valid snapshot 로딩

변경 파일만 incremental apply
