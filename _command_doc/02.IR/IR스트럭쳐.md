{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Semantica IR v4 Document (draft)",
  "type": "object",

  "properties": {
    "repo_id": {
      "type": "string",
      "$comment": "[필수] 레포 식별자. 예: 'semantica-codegraph'"
    },
    "snapshot_id": {
      "type": "string",
      "$comment": "[필수] 스냅샷 식별자. 예: 'commit:abc123', 'branch:main@abc123', 'workspace:soingnin@local-dirty'"
    },
    "schema_version": {
      "type": "string",
      "$comment": "[필수] IR 스키마 버전. 예: '4.0.0-draft'"
    },

    "nodes": {
      "type": "array",
      "items": { "$ref": "#/definitions/Node" },
      "$comment": "[필수] 구조/심볼 중심 Node 레이어"
    },

    "edges": {
      "type": "array",
      "items": { "$ref": "#/definitions/Edge" },
      "$comment": "[필수] 모든 관계(그래프) 정보. CONTAINS 포함"
    },

    "types": {
      "type": "array",
      "items": { "$ref": "#/definitions/TypeEntity" },
      "$comment": "[선택] 타입 시스템 엔티티. 없으면 타입 분석 미사용 스냅샷"
    },

    "signatures": {
      "type": "array",
      "items": { "$ref": "#/definitions/SignatureEntity" },
      "$comment": "[선택] 함수/메서드 시그니처 엔티티"
    },

    "control_flow_graphs": {
      "type": "array",
      "items": { "$ref": "#/definitions/ControlFlowGraph" },
      "$comment": "[선택] 함수/메서드 단위 Control Flow Graph 모음"
    },

    "meta": {
      "type": "object",
      "$comment": "[선택] 인덱싱/환경 메타데이터",
      "properties": {
        "index_time": {
          "type": "string",
          "$comment": "IR 생성 시간 (ISO8601)"
        },
        "engine_version": {
          "type": "string",
          "$comment": "엔진/파이프라인 버전. 예: 'semantica-engine-1.3.0'"
        },
        "index_run_id": {
          "type": "string",
          "$comment": "인덱싱 러닝/세대 ID. 예: 'idx_20251123T120001_main'"
        }
      },
      "additionalProperties": true
    }
  },

  "required": ["repo_id", "snapshot_id", "schema_version", "nodes", "edges"],

  "definitions": {
    "Span": {
      "type": "object",
      "properties": {
        "start_line": { "type": "integer" },
        "start_col":  { "type": "integer" },
        "end_line":   { "type": "integer" },
        "end_col":    { "type": "integer" }
      },
      "required": ["start_line", "start_col", "end_line", "end_col"],
      "$comment": "소스 코드 내 위치 정보. 편집/하이라이트/청킹 기준"
    },

    "Node": {
      "type": "object",
      "$comment": "언어 불문 공통·불변 Node 구조. 관계/타입/시그니처/CFG/DFG는 전부 다른 레이어에 둔다.",
      "properties": {
        "id": {
          "type": "string",
          "$comment": "[필수] 전역 고유 Node ID. 예: 'method:semantica:src/retriever/plan.py:HybridRetriever.plan'"
        },

        "kind": {
          "type": "string",
          "enum": [
            "File",
            "Module",
            "Class",
            "Interface",
            "Function",
            "Method",
            "Lambda",
            "Variable",   // 지역 변수, 파라미터 등
            "Field",      // 클래스/인터페이스 멤버
            "Import",
            "Export",
            "Block",
            "Condition",
            "Loop",
            "TryCatch"
          ],
          "$comment": "[필수] Node 종류 (언어 공통 enum). Variable = 지역/로컬, Field = 멤버."
        },

        "name": {
          "type": ["string", "null"],
          "$comment": "[선택] 심볼 이름. File/Block 등 이름 없는 노드는 null"
        },

        "fqn": {
          "type": "string",
          "$comment": "[필수] Fully Qualified Name. 예: 'semantica.retriever.plan.HybridRetriever.plan'"
        },

        "file_path": {
          "type": "string",
          "$comment": "[필수] 레포 루트 기준 경로. 예: 'src/semantica/retriever/plan.py'"
        },

        "span": {
          "$ref": "#/definitions/Span",
          "$comment": "[필수] Node 전체 범위 (헤더+바디 포함)"
        },

        "body_span": {
          "anyOf": [
            { "$ref": "#/definitions/Span" },
            { "type": "null" }
          ],
          "$comment": "[선택] 바디만 커버하는 범위 (함수/클래스 시그니처 제외)"
        },

        "language": {
          "type": "string",
          "$comment": "[필수] 언어. 예: 'python', 'typescript', 'javascript', 'go', 'java'"
        },

        "module_path": {
          "type": ["string", "null"],
          "$comment": "[선택] import/name resolution용 모듈 경로. 예: 'semantica.retriever.plan'"
        },

        "parent_id": {
          "type": ["string", "null"],
          "$comment": "[선택] IR 트리 상 부모 Node ID (CONTAINS Edge로도 표현되며, parent_id는 편의용 anchor)"
        },

        "content_hash": {
          "type": ["string", "null"],
          "$comment": "[선택] Node 범위 코드에 대한 해시 (sha256 등). 증분 인덱싱/변경 감지"
        },

        "docstring": {
          "type": ["string", "null"],
          "$comment": "[선택] docstring/JSDoc/KDoc. LLM 요약·검색용"
        },

        "role": {
          "type": ["string", "null"],
          "$comment": "[선택] semantic role. 예: 'controller', 'service', 'repo', 'router', 'dto', 'entity', 'component', 'hook', 'test', 'util', 'infra'"
        },

        "is_test_file": {
          "type": ["boolean", "null"],
          "$comment": "[선택] 테스트 코드 여부 (파일 패턴/경로로 추론)"
        },

        "signature_id": {
          "type": ["string", "null"],
          "$comment": "[선택] Function/Method/Lambda가 참조하는 SignatureEntity ID. 예: 'sig:HybridRetriever.plan(Query,int)->RetrievalPlan'"
        },

        "declared_type_id": {
          "type": ["string", "null"],
          "$comment": "[선택] Variable/Field/Parameter 등 '값을 보유하는 심볼'의 선언 타입 TypeEntity ID. File/Class 등에는 사용하지 않음."
        }
      },

      "required": [
        "id",
        "kind",
        "fqn",
        "file_path",
        "span",
        "language"
      ]
    },

    "Edge": {
      "type": "object",
      "$comment": "그래프 관계의 1급 엔티티. Node에는 관계 정보를 직접 넣지 않는다.",
      "properties": {
        "id": {
          "type": "string",
          "$comment": "[필수] Edge ID. 예: 'edge:call:plan→_search_vector@1'"
        },

        "kind": {
          "type": "string",
          "enum": [
            // 구조/정의
            "CONTAINS",   // 구조적 포함 (File→Class, Class→Method, Method→Block, Method→Variable 등)
            "DEFINES",    // 정의(Definition) 관계 (Scope→Symbol)

            // 호출/사용
            "CALLS",      // 함수/메서드를 호출
            "READS",      // 값 읽기 (변수/필드/프로퍼티 사용)
            "WRITES",     // 값 쓰기 (할당/수정)

            // 타입/비데이터 참조
            "REFERENCES", // 타입/클래스/인터페이스/심볼 정의 참조 (extends/implements/annotation 등 데이터 흐름이 아닌 참조)

            // 타입/상속/구현
            "IMPORTS",
            "INHERITS",
            "IMPLEMENTS",

            // 구조/패턴
            "DECORATES",
            "INSTANTIATES",
            "OVERRIDES",

            // 리소스/상태
            "USES",
            "READS_RESOURCE",
            "WRITES_RESOURCE",

            // 예외/제어
            "THROWS",
            "ROUTE_TO",
            "USES_REPO"
          ],
          "$comment": "[필수] 관계 타입. 값 레벨 데이터 흐름은 READS/WRITES, 타입/클래스 참조는 REFERENCES로 한정."
        },

        "source_id": {
          "type": "string",
          "$comment": "[필수] Edge 출발 Node ID (Caller, Referrer, Owner 등)"
        },

        "target_id": {
          "type": "string",
          "$comment": "[필수] Edge 도착 Node ID (Callee, Referenced, Imported 등)"
        },

        "span": {
          "anyOf": [
            { "$ref": "#/definitions/Span" },
            { "type": "null" }
          ],
          "$comment": "[선택] 이 관계가 코드 상에 등장하는 위치 (Call/Reference/Import/Read/Write 등)"
        },

        "attrs": {
          "type": "object",
          "$comment": "[선택] 관계별 확장 메타. 예: arg_count, syntax, import_type, within_condition 등",
          "additionalProperties": true
        }
      },

      "required": ["id", "kind", "source_id", "target_id"]
    },

    "TypeEntity": {
      "type": "object",
      "$comment": "타입 시스템 표현 전용 엔티티. Node는 TypeEntity ID만 참조한다.",
      "properties": {
        "id": {
          "type": "string",
          "$comment": "[필수] Type 엔티티 ID. 예: 'type:RetrievalPlan', 'type:List[Candidate]'"
        },

        "raw": {
          "type": "string",
          "$comment": "[필수] 코드 상 타입 표현. 예: 'RetrievalPlan', 'List[Candidate]'"
        },

        "resolved_target": {
          "type": ["string", "null"],
          "$comment": "[선택] 이 타입이 가리키는 Node ID (Class/Interface/TypeAlias 등). 외부/프리미티브면 null"
        },

        "flavor": {
          "type": "string",
          "enum": ["primitive", "builtin", "user", "external", "typevar", "generic"],
          "$comment": "[필수] 타입 분류"
        },

        "is_nullable": {
          "type": "boolean",
          "$comment": "[필수] null/None/undefined 허용 여부"
        },

        "generic_param_ids": {
          "type": "array",
          "items": { "type": "string" },
          "$comment": "[필수] 제네릭 타입 인자로 참조하는 TypeEntity ID 목록"
        }
      },

      "required": ["id", "raw", "flavor", "is_nullable", "generic_param_ids"]
    },

    "SignatureEntity": {
      "type": "object",
      "$comment": "함수/메서드 시그니처 전용 엔티티. 인터페이스 변경 감지/LLM-safe refactor에 사용.",
      "properties": {
        "id": {
          "type": "string",
          "$comment": "[필수] Signature ID. 예: 'sig:HybridRetriever.plan(Query,int)->RetrievalPlan'"
        },

        "owner_node_id": {
          "type": "string",
          "$comment": "[필수] 이 시그니처가 속한 Node ID (Function/Method/Lambda)"
        },

        "name": {
          "type": "string",
          "$comment": "[필수] 함수/메서드 이름"
        },

        "raw": {
          "type": "string",
          "$comment": "[필수] 시그니처 문자열. 예: 'plan(query: Query, max_results: int = 20) -> RetrievalPlan'"
        },

        "parameter_type_ids": {
          "type": "array",
          "items": { "type": "string" },
          "$comment": "[필수] 파라미터 타입 TypeEntity ID 목록 (순서 보장)"
        },

        "return_type_id": {
          "type": ["string", "null"],
          "$comment": "[선택] 반환 타입 TypeEntity ID"
        },

        "visibility": {
          "type": ["string", "null"],
          "enum": ["public", "protected", "private", "internal", null],
          "$comment": "[선택] 접근 제어자 (언어별 매핑)"
        },

        "is_async": {
          "type": "boolean",
          "$comment": "[필수] async 여부"
        },

        "is_static": {
          "type": "boolean",
          "$comment": "[필수] static/class method 여부"
        },

        "throws_type_ids": {
          "type": "array",
          "items": { "type": "string" },
          "$comment": "[필수] 던질 수 있는 예외 타입 TypeEntity ID 목록 (언어별 매핑, 없으면 빈 배열)"
        },

        "signature_hash": {
          "type": "string",
          "$comment": "[필수] 시그니처 해시. 예: 'sha1:abc123'. 인터페이스 변경 감지 기준"
        }
      },

      "required": [
        "id",
        "owner_node_id",
        "name",
        "raw",
        "parameter_type_ids",
        "is_async",
        "is_static",
        "throws_type_ids",
        "signature_hash"
      ]
    },

    "ControlFlowBlock": {
      "type": "object",
      "$comment": "Control Flow Graph 상의 Basic Block",
      "properties": {
        "id": {
          "type": "string",
          "$comment": "[필수] 블록 ID. 예: 'cfg:plan:block:1'"
        },
        "kind": {
          "type": "string",
          "enum": [
            "Entry",
            "Exit",
            "Block",
            "Condition",
            "LoopHeader",
            "Try",
            "Catch",
            "Finally"
          ],
          "$comment": "[필수] 블록 종류"
        },
        "span": {
          "anyOf": [
            { "$ref": "#/definitions/Span" },
            { "type": "null" }
          ],
          "$comment": "[선택] 이 블록이 커버하는 코드 범위"
        },

        "defined_variable_ids": {
          "type": "array",
          "items": { "type": "string" },
          "$comment": "[필수] 이 블록 안에서 '정의'되는 Variable/Field Node ID 목록 (assignment, declaration 등). Data Flow Graph용."
        },

        "used_variable_ids": {
          "type": "array",
          "items": { "type": "string" },
          "$comment": "[필수] 이 블록 안에서 '사용(읽기)'되는 Variable/Field Node ID 목록. READS/WRITES Edge와 함께 DFG 구성에 사용."
        }
      },
      "required": ["id", "kind", "defined_variable_ids", "used_variable_ids"]
    },

    "ControlFlowEdge": {
      "type": "object",
      "$comment": "Control Flow Graph 블록 간 제어 흐름 Edge",
      "properties": {
        "source_block_id": {
          "type": "string",
          "$comment": "[필수] 출발 블록 ID"
        },
        "target_block_id": {
          "type": "string",
          "$comment": "[필수] 도착 블록 ID"
        },
        "kind": {
          "type": "string",
          "enum": ["NORMAL", "TRUE_BRANCH", "FALSE_BRANCH", "EXCEPTION", "LOOP_BACK"],
          "$comment": "[필수] 제어 흐름 타입"
        }
      },
      "required": ["source_block_id", "target_block_id", "kind"]
    },

    "ControlFlowGraph": {
      "type": "object",
      "$comment": "단일 함수/메서드에 대한 Control Flow Graph",
      "properties": {
        "id": {
          "type": "string",
          "$comment": "[필수] CFG ID. 예: 'cfg:HybridRetriever.plan'"
        },
        "function_node_id": {
          "type": "string",
          "$comment": "[필수] 이 CFG가 대응하는 Function/Method Node ID"
        },
        "entry_block_id": {
          "type": "string",
          "$comment": "[필수] Entry 블록 ID"
        },
        "exit_block_id": {
          "type": "string",
          "$comment": "[필수] Exit 블록 ID"
        },
        "blocks": {
          "type": "array",
          "items": { "$ref": "#/definitions/ControlFlowBlock" },
          "$comment": "[필수] CFG 블록 목록 (각 블록에 def/use 정보 포함)"
        },
        "edges": {
          "type": "array",
          "items": { "$ref": "#/definitions/ControlFlowEdge" },
          "$comment": "[필수] CFG 블록 간 제어 흐름"
        }
      },
      "required": [
        "id",
        "function_node_id",
        "entry_block_id",
        "exit_block_id",
        "blocks",
        "edges"
      ]
    }
  }
}





B. IR 변경시 시나리오

1. 최초 인덱싱 시나리오

1-1. Tree-sitter → AST 생성
1-2. AST → IR(Node/Edge/Type) 전환
1-3. 스냅샷 JSON 생성
1-4. DB 테이블(ir_nodes/ir_edges/ir_types) 저장
1-5. 인메모리 IRStore 로딩

핵심

“작업 시작 기준” 스냅샷 생성

모든 구조는 JSON + DB + 메모리 3중 구조로 준비됨

2. 파일 저장/변경 발생 (실시간 워크스페이스)

2-1. 변경 파일 감지
2-2. 변경 파일만 AST → IR 재생성
2-3. 기존 IR과 diff 계산 (추가/수정/삭제)
2-4. IRStore(메모리) 즉시 업데이트
2-5. 비동기로 DB upsert
2-6. 스냅샷은 필요 시에만(주기적으로) 생성

핵심

실시간 기능은 항상 메모리 기준

DB/JSON 반영은 비동기

3. Git 이벤트 (checkout/pull/rebase)

3-1. git HEAD 변경 감지
3-2. 변경 파일만 diff 기반 재인덱싱
3-3. 새로운 snapshot_id 생성 (commit 기반)
3-4. 이 스냅샷을 IRStore로 교체(리프레시)
3-5. DB 저장 + 스냅샷 JSON 저장(이벤트 트리거 시)

핵심

git commit 단위로 “불변 스냅샷” 생성

워크스페이스 메모리는 항상 최신 HEAD 또는 local-dirty

4. 전체 재인덱싱 (CI/CD 또는 브랜치 main 정식 빌드)

4-1. repo 전체 AST/IR 재생성
4-2. 새로운 snapshot_id = branch:main@{commit}
4-3. ir_nodes/edges/types 전량 덮어쓰기 방식 upsert
4-4. 정식 스냅샷 JSON 생성
4-5. 기존 IRStore는 필요 시 교체

핵심

브랜치 단위 “공식 스냅샷”

재현성/테스트/프로덕션 기준점 역할

5. LLM 도구 호출 시 (검색/그래프/리팩터링)

5-1. IRStore(메모리)에서 즉시 조회
5-2. 인덱스(BM25/vector/symbol)도 메모리 diff 반영된 최신 상태를 기준
5-3. 필요 시 DB/과거 스냅샷에서 읽어서 비교

핵심

LLM API는 “항상 메모리 IRStore”가 기준

스냅샷/DB는 보조 상태 저장소

최종 요약 (한 줄씩)

최초 인덱싱 → JSON + DB + IRStore 3중 생성

파일 변경 → IRStore 즉시 갱신, DB는 비동기

git 이동 → 새 snapshot 만들고 IRStore 교체

전체 재인덱싱 → 공식 스냅샷 생성

LLM 도구는 항상 IRStore 기준으로 검색/탐색