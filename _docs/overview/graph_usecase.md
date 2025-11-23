| 카테고리 | 유즈케이스 | 필요한 그래프 타입 | 설명 |
| 코드 이해 | 함수 콜트리(forward) | calls | 특정 함수가 내부적으로 호출하는 전체 함수 흐름 추적 |
| 코드 이해 | 함수 called-by 트리(backward) | called_by | 어떤 함수가 어디에서 호출되는지 역방향으로 탐색 |
| 코드 이해 | 엔드투엔드 요청 플로우 | calls, imports, route→handler | route → handler → service → repo → DB 전체 흐름 분석 |
| 코드 이해 | 계층 간 흐름(UI/CLI→도메인→DB) | calls, contains | 복합 계층 구조에서 요청·데이터 흐름 추적 |
| 코드 이해 | 타입 구조 분석 | inherits, implements, overrides | 클래스/인터페이스 계층 구조 파악 |
| 코드 이해 | 객체 생성 경로 | instantiates | new/DI/팩토리에서 어떤 객체가 생성되는지 추적 |
| 코드 이해 | 데코레이터/어노테이션 연결 | decorates, annotates | 데코레이터 체인/메타정보 적용 경로 |
| 리팩토링 | rename 영향 분석 | calls, implements, overrides | 이름 변경 시 깨지는 경로 전체 추적 |
| 리팩토링 | 시그니처 변경 영향 | calls | 파라미터 변경 시 연쇄적으로 영향받는 호출자 찾기 |
| 리팩토링 | dead code 탐지 | reachability | entrypoint로부터 도달 불가능한 코드 탐색 |
| 리팩토링 | 모듈 분리/MSA 전환 | imports, package graph | 모듈 의존도·순환의존 탐지 → 분리 여부 판단 |
| 리팩토링 | 패키지 복잡도 분석 | in-degree/out-degree | 특정 모듈이 과도하게 의존되거나 의존하는 구조 파악 |
| 리팩토링 | enum/constant 사용 경로 | reads, writes | enum 값 제거 영향 경로 전체 탐색 |
| 테스트/품질 | Test Impact Analysis | calls, contains | 특정 테스트가 커버하는 함수·경로 분석 |
| 테스트/품질 | 테스트 미도달 코드 찾기 | reverse reachability | 테스트 entrypoint → 도달하지 않는 코드 탐지 |
| 테스트/품질 | mock 필요 지점 식별 | instantiates, calls | 외부 의존 호출 경로 파악 |
| 테스트/품질 | 커버리지 구멍 자동 발견 | calls | 테스트 경로가 끊기는 지점 자동 식별 |
| 안정성/보안 | 취약점 전파 경로 | calls, dataflow | 위험 API 호출이 어디로 propagate 되는지 확인 |
| 안정성/보안 | 비동기/스레드 흐름 추적 | calls, spawns | goroutine/thread spawn·join 구조 분석 |
| 안정성/보안 | 예외 전파 흐름 | throws, catches | 예외가 퍼지는 전체 경로를 그래프로 표현 |
| 안정성/보안 | 외부 API 호출 경로 | calls, imports | 외부 서비스 호출이 어디서 발생하는지 전체 추적 |
| 구조 분석 | 시스템 아키텍처 자동 추출 | module graph, calls | 코드에서 아키텍처 구조를 역으로 재구성 |
| 구조 분석 | 도메인/팀 경계 식별 | package graph | 실제 의존성 기반 DDD 바운더리 자동 발견 |
| 구조 분석 | 계층 규칙 위반 탐지 | contains, imports | Controller → Repo 직접 호출 같은 계층 위반 자동 검출 |
| AI/자동화 | 자동 리팩토링 경로 계획 | calls | “이 함수 바꾸면 이 경로부터 수정하세요” 자동 추천 |
| AI/자동화 | agent reasoning 강화 | calls, imports, inherits | 에이전트가 코드 문맥을 더 정확히 이해하도록 그래프 제공 |
| AI/자동화 | GraphRAG 기반 검색 | hybrid (lexical+graph) | 자연어 → 관련 코드 심볼로 정확한 매핑 |
| AI/자동화 | 자동 문서/다이어그램 생성 | contains, calls | 코드 흐름 기반 기술 문서/시퀀스 다이어그램 생성 |
V. 코드 진단 및 통계 (Code Diagnostics & Metrics)이 유즈케이스들은 그래프 구조를 통해 코드의 상태와 품질을 측정하고 추적합니다.유즈케이스설명그래프 요소16. 복잡도 및 품질 측정 (Complexity Metrics)함수의 복잡도(예: Cyclomatic Complexity)나 모듈의 응집도/결합도(Coupling/Cohesion)를 그래프 구조 분석으로 계산.함수/모듈 노드, 제어 흐름 에지17. 코드 핫스팟 탐지 (Code Hotspots)가장 자주 변경되거나 버그가 많이 발생하는 파일/함수 노드와 그 주변 의존성을 식별하여 리팩토링 우선순위를 설정.심볼 노드, 커밋/이슈 메타데이터 에지18. 코드 중복 탐지 (Code Duplication)구조적으로 동일하거나 유사한 코드 블록(노드) 그룹을 그래프 패턴 매칭을 통해 탐지.코드 블록 노드, 유사성 에지VI. 코드 변경 및 정책 (Code Change & Policy Enforcement)이 유즈케이스들은 코드 변경 과정과 정책 준수 여부를 그래프로 관리합니다.유즈케이스설명그래프 요소19. 레거시 코드 격리 (Legacy Isolation)특정 레거시 모듈/함수가 새로운 서비스에서 호출되는 것을 막거나, 레거시 API의 사용을 정책적으로 모니터링.모듈 노드, 금지된 호출 에지20. 버전 간 차이 분석 (Version Diff Analysis)두 커밋 또는 버전 사이의 코드 그래프 차이(심볼의 추가, 삭제, 관계 변경)를 분석하여 변경의 실제 규모와 영향을 정량화.심볼 노드, 버전 에지21. 코드 오너십 추적 (Code Ownership)특정 함수나 파일이 어떤 팀이나 개발자에게 속하는지 매핑하고, 변경 사항의 PR 검토자 추천에 사용.심볼 노드, 오너 메타데이터 에지VII. 디버깅 및 버그 분석 (Debugging & Bug Analysis)콜 그래프와 데이터 흐름 그래프를 조합하여 버그 분석을 지원합니다.유즈케이스설명그래프 요소22. 에러 트레이스 분석 (Error Trace Analysis)런타임 에러 스택 트레이스 정보를 코드 그래프에 매핑하여, 에러가 발생한 지점부터 원인이 되는 함수 호출까지의 경로를 시각화.함수 노드, 런타임 호출 스택 에지23. 제어 흐름 분석 (Control Flow Analysis)함수 내에서 조건문, 루프 등에 따른 코드 실행 경로를 그래프로 나타내어 로직 오류를 탐지.코드 블록 노드, 분기 에지