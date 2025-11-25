{
  "IRDocument": {
    "$comment": "스냅샷 단위 IR 덩어리. 엔티티들의 컨테이너.",
    "repo_id": {
      "source_data": ["CLI 인자", "config 파일 (semantica.toml 등)", "실행 컨텍스트"],
      "inference": ["없음"],
      "external_data": ["git remote URL 기반 논리 이름 매핑"],
      "$comment": "레포 논리 ID. 예: 'semantica-codegraph'"
    },
    "snapshot_id": {
      "source_data": ["git HEAD 정보 (commit SHA, branch 이름)", "워크스페이스 세션 ID"],
      "inference": [
        "패턴 조합: 'commit:<sha>'",
        "또는 'branch:<name>@<sha>'",
        "또는 'workspace:<user-or-session>@<local-sha-or-dirty>'"
      ],
      "external_data": ["libgit2 / git CLI 결과"],
      "$comment": "어떤 시점/브랜치/워크스페이스의 스냅샷인지 식별"
    },
    "schema_version": {
      "source_data": ["엔진 코드에 상수로 정의된 버전"],
      "inference": ["없음"],
      "external_data": ["릴리즈 시스템의 semver 정보와 동기화 가능"],
      "$comment": "IR 포맷 버전. 예: '4.1.0-draft'"
    },
    "meta.index_time": {
      "source_data": ["인덱싱 작업 시작/종료 시각"],
      "inference": ["ISO8601 포맷으로 직렬화"],
      "external_data": ["없음"],
      "$comment": "IR 생성 시각"
    },
    "meta.engine_version": {
      "source_data": ["엔진 코드 내 버전 상수"],
      "inference": ["없음"],
      "external_data": ["CI/CD 빌드 버전과 연동 가능"],
      "$comment": "사용된 Semantica 엔진 버전"
    },
    "meta.index_run_id": {
      "source_data": ["인덱싱 작업 실행 ID (UUID/타임스탬프)"],
      "inference": ["'idx_<timestamp>_<branch>' 형식 등으로 포맷팅"],
      "external_data": ["없음"],
      "$comment": "인덱싱 러닝/세대 식별자"
    }
  },

  "Node": {
    "$comment": "언어 불문 공통 구조 Node. 관계/타입/CFG는 전부 다른 엔티티가 담당.",
    "id": {
      "source_data": [],
      "inference": [
        "repo_id, file_path, kind, fqn, span, content_hash 등을 조합한 해시",
        "또는 사람이 읽기 좋은 논리 ID (예: 'method:...HybridRetriever.plan')와 함께 관리"
      ],
      "external_data": [],
      "$comment": "전역 고유 Node ID (논리 + 해시 조합 권장)"
    },
    "kind": {
      "source_data": ["Tree-sitter AST 노드 타입", "언어별 파서의 노드 카테고리"],
      "inference": [
        "AST → IR 매핑 규칙:",
        "  function_definition → 'Function'",
        "  class_definition → 'Class'",
        "  method_definition → 'Method'",
        "  for_statement / while_statement → 'Loop'",
        "  try_statement → 'TryCatch' 등"
      ],
      "external_data": [],
      "$comment": "File / Class / Method / Variable / Field / Loop / TryCatch 등 공통 enum"
    },
    "name": {
      "source_data": ["AST 상 identifier 토큰 (함수명, 클래스명 등)"],
      "inference": [
        "언어별 규칙 적용:",
        "  Python: 'def foo' → 'foo'",
        "  TS: 'class Foo<T>' → 'Foo'",
        "  이름 없는 블록/파일은 null"
      ],
      "external_data": [],
      "$comment": "심볼 이름. 이름이 없는 Node는 null"
    },
    "fqn": {
      "source_data": ["file_path", "상위 스코프 이름들(Module/Class 등)", "module_path"],
      "inference": [
        "module_path + 상위 클래스/모듈명 + 자기 name을 '.'으로 조합",
        "예: 'semantica.retriever.plan.HybridRetriever.plan'"
      ],
      "external_data": [
        "tsconfig.json (baseUrl, paths)",
        "pyproject.toml / setup.cfg (패키지 루트)"
      ],
      "$comment": "Fully Qualified Name. cross-file 링크의 기준"
    },
    "file_path": {
      "source_data": ["파일 시스템 경로 (repo root 기준)"],
      "inference": ["절대경로에서 repo root 기준 상대 경로 계산"],
      "external_data": ["git working tree / repo root"],
      "$comment": "예: 'src/semantica/retriever/plan.py'"
    },
    "span": {
      "source_data": ["Tree-sitter AST 노드의 start_byte / end_byte"],
      "inference": [
        "파일 전체 텍스트에서 byte offset → (line, col)로 변환",
        "start_line, start_col, end_line, end_col 계산"
      ],
      "external_data": [],
      "$comment": "Node 전체 범위 (헤더+바디 포함) 위치"
    },
    "body_span": {
      "source_data": ["AST 내 body 블록의 위치 정보"],
      "inference": [
        "함수/클래스 header 부분을 제외한 내부 블록 범위를 계산",
        "없으면 null"
      ],
      "external_data": [],
      "$comment": "바디만 커버하는 범위 (컨텍스트 추출용)"
    },
    "language": {
      "source_data": ["파일 확장자", "ParserRegistry에서 선택한 언어"],
      "inference": [
        "'.py' → 'python'",
        "'.ts' → 'typescript'",
        "'.js' → 'javascript' 등 매핑"
      ],
      "external_data": ["프로젝트 설정에서 언어 override 가능"],
      "$comment": "python / typescript / javascript / go / java ..."
    },
    "module_path": {
      "source_data": ["file_path", "언어별 모듈 시스템 설정"],
      "inference": [
        "src/semantica/retriever/plan.py → semantica.retriever.plan",
        "디렉토리 구조 + 패키지 설정에 따라 계산"
      ],
      "external_data": [
        "tsconfig.json (baseUrl, paths)",
        "PYTHONPATH, pyproject.toml 패키지 설정"
      ],
      "$comment": "import / name resolution용 모듈 경로"
    },
    "parent_id": {
      "source_data": ["AST parent-child 관계 (상위 노드)"],
      "inference": [
        "AST 트리 순회 시 IR Node 생성과 동시에 부모 Node의 id를 기록",
        "예: Class의 parent = File, Method의 parent = Class"
      ],
      "external_data": [],
      "$comment": "IR 트리 상 부모 Node. CONTAINS Edge와 중복되지만 앵커용으로 사용"
    },
    "content_hash": {
      "source_data": ["해당 Node.span 범위의 소스 코드 텍스트"],
      "inference": [
        "SHA-256 등으로 해시 계산",
        "파일 이동/리네임에도 코드가 같으면 동일 해시"
      ],
      "external_data": [],
      "$comment": "증분 인덱싱/변경 감지용 코드 해시"
    },
    "docstring": {
      "source_data": ["AST 상 docstring / JSDoc / KDoc 노드"],
      "inference": [
        "언어별 docstring 추출 규칙 적용:",
        "  Python: 첫 statement가 문자열 literal인 경우",
        "  TS/JS: /** ... */ JSDoc 블록 등"
      ],
      "external_data": [],
      "$comment": "LLM 요약/검색/설명에 사용되는 문서 문자열"
    },
    "role": {
      "source_data": ["file_path", "디렉토리/파일 이름 패턴", "import 대상"],
      "inference": [
        "Heuristic 규칙:",
        "  *Controller / *Service / *Repository 네이밍",
        "  'tests/' 디렉토리면 test",
        "  특정 프레임워크 import 시 controller/router로 태깅 등"
      ],
      "external_data": ["프로젝트별 role 규칙 설정 파일 (예: semantica-role-rules.yaml)"],
      "$comment": "controller / service / repo / router / dto / entity / test / util 등"
    },
    "is_test_file": {
      "source_data": ["file_path"],
      "inference": [
        "패턴 매칭:",
        "  'tests/**', '__tests__/**', '*_test.py', 'test_*.py' 등",
        "룰에 맞으면 true, 아니면 false"
      ],
      "external_data": ["사용자 설정으로 특정 경로를 test로 강제 지정 가능"],
      "$comment": "테스트 코드 여부"
    },
    "signature_id": {
      "source_data": [],
      "inference": [
        "Node.kind가 Function/Method/Lambda인 경우:",
        "  SignatureEntity 생성 후 그 id를 여기 연결",
        "  예: 'sig:HybridRetriever.plan(Query,int)->RetrievalPlan'"
      ],
      "external_data": ["LSP/타입체커에서 제공한 시그니처를 기반으로 생성할 수도 있음"],
      "$comment": "함수/메서드에 대응하는 시그니처 엔티티 참조"
    },
    "declared_type_id": {
      "source_data": ["AST 상 타입 애노테이션 (변수, 필드, 파라미터)"],
      "inference": [
        "타입 표현(raw)을 파싱해 TypeEntity 생성",
        "그 TypeEntity.id를 연결",
        "타입 정보 없으면 null"
      ],
      "external_data": [
        "LSP/SCIP/타입체커(mypy, pyright, TS compiler)가 infer한 타입을 사용해 보정 가능"
      ],
      "$comment": "값을 보유하는 심볼(Variable/Field/Parameter)의 선언 타입"
    }
  },

  "Edge": {
    "$comment": "Node 간 관계(그래프)를 나타내는 1급 엔티티.",
    "id": {
      "source_data": [],
      "inference": [
        "kind, source_id, target_id, span 등을 조합해 해시 생성",
        "또는 사람이 읽기 좋은 패턴: 'edge:call:plan→_search_vector@1'"
      ],
      "external_data": [],
      "$comment": "Edge 고유 ID"
    },
    "kind": {
      "source_data": ["AST 패턴", "IR 분석 결과"],
      "inference": [
        "호출 표현식 → CALLS",
        "import 문 → IMPORTS",
        "클래스 상속 → INHERITS",
        "implements 구문 → IMPLEMENTS",
        "데코레이터 → DECORATES",
        "변수 읽기/쓰기 → READS/WRITES",
        "파일/클래스/함수 포함 관계 → CONTAINS",
        "타입/클래스 참조 → REFERENCES"
      ],
      "external_data": [
        "StackGraphs, LSP, SCIP 등에서 제공하는 call graph / reference graph를 반영해 보정 가능"
      ],
      "$comment": "CONTAINS / CALLS / READS / WRITES / IMPORTS / INHERITS / IMPLEMENTS / DECORATES / THROWS 등"
    },
    "source_id": {
      "source_data": ["Edge 생성 시점의 출발 Node (caller / referrer / owner)"],
      "inference": [
        "AST를 순회하면서 현재 context Node를 source로 사용",
        "예: Method.plan 안의 호출 → source_id = plan Node.id"
      ],
      "external_data": [],
      "$comment": "관계의 시작 노드"
    },
    "target_id": {
      "source_data": [],
      "inference": [
        "Name Resolution / Symbol Resolution 결과:",
        "  호출/참조된 이름이 어떤 Node.id를 가리키는지 찾음",
        "  실패 시 null target을 잠정적으로 기록하거나 Edge 생성 스킵"
      ],
      "external_data": [
        "StackGraphs / LSP / SCIP가 제공하는 '참조 → 정의' 매핑을 직접 사용해 더 정확히 해석 가능"
      ],
      "$comment": "관계의 도착 노드"
    },
    "span": {
      "source_data": ["관계가 발생한 AST 위치 (호출식, import 구문, 상속 선언 등)"],
      "inference": [
        "해당 표현식의 byte offset → (line, col) 변환",
        "없는 경우 null"
      ],
      "external_data": [],
      "$comment": "이 관계가 코드 상 어디에 적혀 있는지"
    },
    "attrs": {
      "source_data": [
        "AST에서 추가로 얻을 수 있는 정보:",
        "  CALLS: 인자 개수, raw 호출 문자열",
        "  IMPORTS: from/import 종류, alias 이름",
        "  INHERITS/IMPLEMENTS: extends/implements 키워드 위치 등"
      ],
      "inference": [
        "문자열 조합(syntax), bool flag(within_condition 등) 계산",
        "필요 시 간단한 요약 필드 추가"
      ],
      "external_data": [
        "추후 Runtime/Trace 정보를 여기에 붙일 수도 있음 (예: 호출 빈도, 예외 발생 여부)"
      ],
      "$comment": "Edge 타입별 확장 메타데이터"
    }
  },

  "TypeEntity": {
    "$comment": "타입 시스템 표현. Node는 TypeEntity ID만 참조.",
    "id": {
      "source_data": [],
      "inference": [
        "raw, flavor, is_nullable, generic_param_ids 조합으로 해시 생성",
        "예: 'type:RetrievalPlan', 'type:List[Candidate]' 등"
      ],
      "external_data": [],
      "$comment": "타입 엔티티 고유 ID"
    },
    "raw": {
      "source_data": [
        "AST 상 타입 애노테이션 문자열",
        "또는 LSP/타입체커가 제공하는 타입 문자열"
      ],
      "inference": [
        "언어별 AST 노드를 pretty-print하여 문자열 재구성 가능"
      ],
      "external_data": [
        "mypy/pyright/TS compiler 등에서 제공하는 정제된 타입명 사용 가능"
      ],
      "$comment": "코드 상 타입 표현 그대로"
    },
    "resolved_target": {
      "source_data": [],
      "inference": [
        "해당 타입명이 어떤 Class/Interface/TypeAlias Node를 가리키는지 Name Resolution 수행",
        "프로젝트 외부 타입, 프리미티브면 null"
      ],
      "external_data": [
        "LSP/SCIP/타입체커가 직접 알려주는 심볼 ID 매핑 사용 가능"
      ],
      "$comment": "이 타입이 가리키는 심볼(Node) ID. 없으면 null"
    },
    "flavor": {
      "source_data": ["raw 타입 문자열"],
      "inference": [
        "primitive (int, str, bool 등)",
        "builtin (list, dict, Promise 등)",
        "user (프로젝트 내 정의)",
        "external (라이브러리)",
        "typevar, generic 등으로 분류"
      ],
      "external_data": ["언어 런타임/표준 라이브러리 목록"],
      "$comment": "primitive / builtin / user / external / typevar / generic"
    },
    "is_nullable": {
      "source_data": ["타입 표현식 (Optional, T | None, T?)"],
      "inference": [
        "언어별 nullable 표현 파싱:",
        "  Optional[T], T | None, T? 등",
        "nullable이면 true, 아니면 false"
      ],
      "external_data": ["타입체커에서 null 허용 여부를 제공하는 경우 덮어쓰기 가능"],
      "$comment": "null/None/undefined 허용 여부"
    },
    "generic_param_ids": {
      "source_data": ["타입 표현식의 제네릭 인자 부분"],
      "inference": [
        "예: List[Candidate] → Candidate 부분을 파싱",
        "각 인자에 대해 별도 TypeEntity 생성 후 그 ID를 배열로 저장"
      ],
      "external_data": ["타입체커/LSP가 구체 타입 인자를 직접 제공하는 경우 사용할 수 있음"],
      "$comment": "제네릭 타입 인자들의 TypeEntity ID 목록"
    }
  },

  "SignatureEntity": {
    "$comment": "함수/메서드 시그니처. 인터페이스 변경 감지/LLM-safe refactor의 기준.",
    "id": {
      "source_data": [],
      "inference": [
        "owner_node_id + raw 또는 signature_hash 조합으로 생성",
        "예: 'sig:HybridRetriever.plan(Query,int)->RetrievalPlan'"
      ],
      "external_data": [],
      "$comment": "시그니처 고유 ID"
    },
    "owner_node_id": {
      "source_data": ["해당 시그니처가 속한 Function/Method/Lambda Node.id"],
      "inference": ["Node.kind가 함수 계열인 것과 매핑"],
      "external_data": [],
      "$comment": "이 시그니처의 소유 Node"
    },
    "name": {
      "source_data": ["Node.name"],
      "inference": ["없음 (복사)"],
      "external_data": [],
      "$comment": "함수/메서드 이름"
    },
    "raw": {
      "source_data": ["AST에서 파라미터/리턴 타입 정보를 읽어옴"],
      "inference": [
        "언어별 포맷팅 규칙으로 문자열 조립:",
        "  plan(query: Query, max_results: int = 20) -> RetrievalPlan"
      ],
      "external_data": ["LSP/타입체커가 주는 시그니처 문자열을 그대로 쓸 수도 있음"],
      "$comment": "시그니처 전체 문자열 표현"
    },
    "parameter_type_ids": {
      "source_data": ["파라미터 AST 노드의 타입 애노테이션"],
      "inference": [
        "각 타입 표현을 TypeEntity로 승격",
        "해당 TypeEntity.id를 파라미터 순서대로 배열에 저장"
      ],
      "external_data": ["LSP/타입체커에서 파라미터 타입 리스트를 받아 활용 가능"],
      "$comment": "파라미터 타입 TypeEntity ID 목록 (순서 중요)"
    },
    "return_type_id": {
      "source_data": ["함수/메서드 선언의 return annotation"],
      "inference": [
        "TypeEntity 생성 후 ID 연결",
        "리턴 타입 없으면 null"
      ],
      "external_data": ["LSP/타입체커에서 infer된 리턴 타입으로 보정 가능"],
      "$comment": "반환 타입 TypeEntity ID"
    },
    "visibility": {
      "source_data": ["언어 문법의 접근 제어자 키워드", "Python의 이름 패턴(_foo, __bar)"],
      "inference": [
        "언어별 visibility 매핑:",
        "  public/protected/private/internal",
        "Python은 heuristic 기반으로 추정"
      ],
      "external_data": [],
      "$comment": "public / protected / private / internal / null"
    },
    "is_async": {
      "source_data": ["AST 상 async 키워드 (Python) / async function (TS/JS)"],
      "inference": ["존재 여부에 따라 boolean 설정"],
      "external_data": [],
      "$comment": "async 여부"
    },
    "is_static": {
      "source_data": [
        "Python: @staticmethod / @classmethod 데코레이터",
        "TS/Java: static 키워드"
      ],
      "inference": [
        "decorator/키워드 분석으로 static/class method 여부 결정"
      ],
      "external_data": [],
      "$comment": "static / class method 여부"
    },
    "throws_type_ids": {
      "source_data": ["TS/Java의 throws 구문", "주석 기반 예외 명시(선택)"],
      "inference": [
        "각 예외 타입 표현 → TypeEntity 생성 → ID 배열 저장",
        "명시된 예외가 없으면 빈 배열"
      ],
      "external_data": ["정적 분석기에서 '던질 수 있는 예외 타입' 분석 결과를 반영 가능"],
      "$comment": "던질 수 있는 예외 타입 TypeEntity ID 목록"
    },
    "signature_hash": {
      "source_data": [
        "raw, parameter_type_ids, return_type_id, visibility, is_async, is_static, throws_type_ids"
      ],
      "inference": [
        "위 필드들을 정규화한 뒤 해시 계산 (예: SHA-1)",
        "이 값이 바뀌면 '인터페이스 변경'으로 간주"
      ],
      "external_data": [],
      "$comment": "인터페이스 변경 감지용 시그니처 해시"
    }
  },

  "ControlFlowSummary": {
    "$comment": "CFG 전체는 나중 단계. 우선 Node 수준 요약만 사용한다면 이런 필드 구성을 가정.",
    "cyclomatic_complexity": {
      "source_data": ["AST 내 조건/루프/try-catch 구조"],
      "inference": [
        "표준 cyclomatic complexity 공식으로 계산:",
        "  E - N + 2P 또는 '분기 수 + 1' 방식",
        "함수/메서드 단위로 값 산출"
      ],
      "external_data": ["외부 정적 분석기에서 제공하는 복잡도 값을 덮어쓸 수 있음"],
      "$comment": "복잡도 지표. 리팩토링 후보/리스크 분석에 사용"
    },
    "has_loop": {
      "source_data": ["AST 내 for / while / foreach 등 loop 노드"],
      "inference": ["루프 노드가 하나라도 있으면 true, 없으면 false"],
      "external_data": [],
      "$comment": "루프 존재 여부"
    },
    "has_try": {
      "source_data": ["AST 내 try/except, try/catch 블록"],
      "inference": ["try 블록이 하나라도 있으면 true, 없으면 false"],
      "external_data": [],
      "$comment": "예외 처리 블록 존재 여부"
    },
    "branches": {
      "source_data": ["if / elif / switch / match 등 조건식"],
      "inference": [
        "조건 표현식을 간단한 문자열로 추출/정규화:",
        "  예: 'if query.is_symbol_search', 'if user is None' 등"
      ],
      "external_data": [],
      "$comment": "주요 분기 조건 요약 리스트 (선택)"
    }
  }
}
