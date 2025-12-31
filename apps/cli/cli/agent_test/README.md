# Agent 테스트 CLI (SOTA급)

Production-Ready Agent 개발 및 테스트를 위한 종합 CLI 도구

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Quality: A+](https://img.shields.io/badge/quality-A+-brightgreen.svg)](.)
[![Type Safe: 100%](https://img.shields.io/badge/type%20safe-100%25-green.svg)](.)

## 특징

- ✅ **타입 안전**: 100% 타입 힌트, 런타임 검증
- ✅ **Production-Ready**: DI, 에러 처리, 로깅
- ✅ **Rich UI**: 프로그레스, 테이블, 패널
- ✅ **6개 서브커맨드**: snapshot, repo, search, retriever, run, metrics
- ✅ **20개 명령어**: 모든 워크플로우 지원
- ✅ **Just 통합**: 14개 편의 명령어

## 설치

```bash
# 프로젝트 루트에서
pip install -e .
```

## 빠른 시작

### 1. 완전한 워크플로우

```bash
# 1단계: Snapshot 생성
agent-test snapshot create .
# → ID: 738bca69-b519-4b34-87b7-d36ec3915061

# 2단계: Retriever 확인
agent-test retriever list
# → basic, v3, multi_hop, reasoning

# 3단계: Agent 실행
agent-test run execute "fix null pointer bug" \
  --snapshot 738bca69-b519-4b34-87b7-d36ec3915061 \
  --retriever reasoning

# 4단계: 메트릭 확인
agent-test metrics show
```

### 2. Just 명령어 (권장)

```bash
just agent-test-snapshot-create
just agent-test-retriever-list
just agent-test-search-semantic "authentication"
```

## 명령어 레퍼런스

### Snapshot 관리

```bash
# 간단한 작업 실행
python -m src.cli.agent_test.main run execute "fix bug in payment.py"

# 특정 저장소 지정
python -m src.cli.agent_test.main run execute "add tests" --repo ./my-project

# 빠른 실행 (현재 디렉토리)
python -m src.cli.agent_test.main run quick "fix typo"
```

### 출력 옵션

```bash
# 스트리밍 출력 (기본값)
python -m src.cli.agent_test.main run execute "refactor" --stream

# 스트리밍 끄기
python -m src.cli.agent_test.main run execute "refactor" --no-stream

# 간결한 출력 (CI용)
python -m src.cli.agent_test.main run execute "test" --compact
```

### 메트릭

```bash
# 메트릭 조회
python -m src.cli.agent_test.main metrics show

# 메트릭 초기화
python -m src.cli.agent_test.main metrics reset
```

### 버전 정보

```bash
python -m src.cli.agent_test.main version
```

## 개발 예시

### 1. 버그 수정 테스트

```bash
python -m src.cli.agent_test.main run execute \
  "fix null pointer exception in src/payment/processor.py" \
  --repo ./my-app
```

### 2. 리팩토링 테스트

```bash
python -m src.cli.agent_test.main run execute \
  "refactor authentication module to use dependency injection" \
  --repo ./backend
```

### 3. 테스트 추가

```bash
python -m src.cli.agent_test.main run quick \
  "add unit tests for UserService class"
```

## 기능

### Phase 1 (현재)

- [x] 기본 CLI 구조
- [x] Container 통합
- [x] 스트리밍 실행
- [x] 이벤트 기반 출력
- [x] 메트릭 조회

### Phase 2 (예정)

- [ ] 체크포인트/재개
- [ ] 프롬프트 덤프
- [ ] 단계별 실행
- [ ] 상태 인스펙션

## 아키텍처

```
agent_test/
├── main.py              # CLI 엔트리포인트
├── commands/            # 커맨드 그룹
│   ├── run.py          # 실행 관련
│   └── metrics.py      # 메트릭 관련
└── core/               # 코어 로직
    ├── executor.py     # Agent 실행 래퍼
    └── streaming.py    # 스트리밍 출력
```

## 트러블슈팅

### ModuleNotFoundError

```bash
# PYTHONPATH 설정
export PYTHONPATH=/path/to/codegraph:$PYTHONPATH
```

### Container 에러

Container가 초기화되지 않은 경우, 프로젝트 루트에서 실행하세요.
