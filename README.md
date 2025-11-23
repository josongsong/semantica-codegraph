# Semantica Codegraph v4

LLM이 코드 레포지토리를 개발자 수준으로 이해·탐색·수정·생성할 수 있는 코드 RAG 엔진

## 개요

Semantica Codegraph v4는 다음을 제공합니다:

- **하이브리드 검색**: Lexical (Zoekt) + Semantic (Qdrant) + Graph (Kùzu) 검색
- **GraphRAG**: 코드 구조, 호출 관계, 의존성을 그래프로 모델링
- **Git 친화적**: 증분 인덱싱, 브랜치/PR 네임스페이스, overlay 워킹트리
- **멀티채널**: CLI / MCP / HTTP API / IDE 플러그인
- **Fallback 계층**: 장애 상황에서도 best-effort 응답 제공

## 빠른 시작

### 사전 요구사항

- Docker & Docker Compose
- Python 3.10 이상
- OpenAI API Key

### 1. 초기 설정

```bash
# 저장소 클론
git clone <repository-url>
cd codegraph

# 환경 설정 및 서비스 시작
make docker-dev
```

위 명령어가 자동으로 수행하는 작업:
1. `.env` 파일 생성 (`.env.example`에서 복사)
2. 필요한 디렉토리 생성 (`repos/`, `logs/`)
3. Docker 서비스 시작 (Postgres, Redis, Qdrant, Zoekt, API)
4. 서비스 상태 확인
5. 로그 스트리밍

### 2. 환경 변수 설정

서비스를 중지한 후 `.env` 파일을 편집:

```bash
# Ctrl+C로 로그 중지
# 서비스는 백그라운드에서 계속 실행됨

# .env 파일 편집
nano .env
```

**필수**: `OPENAI_API_KEY` 설정

```bash
OPENAI_API_KEY=sk-your-api-key-here
```

### Justfile 사용 (선택)

이 저장소는 `Justfile`을 포함하여 자주 사용하는 개발 작업을 짧은 명령으로 실행할 수 있습니다. macOS에서 `just` 를 설치하려면:

```bash
brew install just
```

일반적으로 사용되는 몇 가지 작업:

- `just docker-dev` — 전체 개발 환경 시작 (`Makefile`을 위임합니다)
- `just run-api` — 로컬에서 API 서버 실행 (`uvicorn`)
- `just coverage-html` — 테스트 실행 및 HTML 커버리지 리포트 생성

모든 작업 목록 확인:

```bash
just --list
```


### 3. 서비스 재시작

```bash
# API 서버만 재시작 (환경 변수 적용)
make docker-restart-api

# 또는 모든 서비스 재시작
make docker-restart
```

### 4. API 확인

브라우저에서 다음 URL 접속:

- **API 문서**: http://localhost:7200/docs
- **Health Check**: http://localhost:7200/health
- **Qdrant Dashboard**: http://localhost:7203/dashboard

## 아키텍처

### 기술 스택

| 컴포넌트 | 기술 | 용도 |
|----------|------|------|
| 코드 파싱 | Tree-sitter | 다중 언어 AST 파싱 |
| 코드 그래프 | Kùzu (embedded) | 그래프 + 컬럼 스토어 |
| 벡터 검색 | Qdrant | Dense embedding + payload filter |
| Lexical 검색 | Zoekt | BM25 + substring + regex |
| 세션/캐시 | Redis | 협업, 세션 관리 |
| 메타데이터 | PostgreSQL | 영구 저장소 |
| LLM | OpenAI / Claude | 임베딩 & 생성 |

### 서비스 구성

```
┌─────────────────────────────────────────────────┐
│              API Server (FastAPI)               │
│  - HTTP API, Tool Set, Agent, Planner           │
└────────────┬───────────────────────────┬────────┘
             │                           │
    ┌────────▼────────┐         ┌────────▼────────┐
    │  Search Layer   │         │  Graph Layer    │
    │  - Hybrid       │         │  - GraphRAG     │
    │  - Ranking      │         │  - Call Chain   │
    └────┬─────┬─────┘         └────────┬────────┘
         │     │                         │
    ┌────▼─┐ ┌▼────┐              ┌─────▼─────┐
    │Zoekt │ │Qdrant│              │   Kùzu    │
    │(BM25)│ │(Vec) │              │  (Graph)  │
    └──────┘ └──────┘              └───────────┘
                                          │
                                   ┌──────▼──────┐
                                   │  PostgreSQL │
                                   │   (Meta)    │
                                   └─────────────┘
                                          │
                                   ┌──────▼──────┐
                                   │    Redis    │
                                   │  (Session)  │
                                   └─────────────┘
```

## 사용 방법

### Make 명령어

```bash
# 도움말 보기
make help

# Python 개발
make dev              # 개발 의존성 설치
make test             # 테스트 실행
make lint             # 린트 검사
make format           # 코드 포맷팅

# Docker 관리
make docker-dev       # 개발 환경 시작 (권장)
make docker-up        # 서비스 시작
make docker-down      # 서비스 중지
make docker-logs      # 로그 확인
make docker-ps        # 상태 확인
make docker-health    # 헬스체크

# 컨테이너 접근
make docker-shell     # API 서버 쉘
make docker-shell-db  # PostgreSQL 쉘
make docker-shell-redis  # Redis CLI

# 데이터 관리
make docker-backup-db    # DB 백업
make docker-restore-db FILE=backup.sql  # DB 복원
```

### API 사용 예시

```bash
# Health check
curl http://localhost:7200/health

# 코드 검색 (예시)
curl -X POST http://localhost:7200/search/code \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication middleware",
    "limit": 10
  }'

# 호출 체인 조회 (예시)
curl -X GET http://localhost:7200/graph/call-chain?symbol_id=123
```

자세한 API 문서는 http://localhost:7200/docs 참조

## 프로젝트 구조

```
codegraph/
├── codegraph/              # 핵심 라이브러리
│   ├── core/              # 도메인 로직 & 포트
│   ├── infra/             # 어댑터 (Qdrant, Postgres, etc.)
│   ├── parsers/           # Tree-sitter 파서
│   ├── graph/             # 그래프 모델
│   ├── chunking/          # 청킹 전략
│   ├── storage/           # 스토리지 추상화
│   ├── schema/            # 데이터 스키마
│   └── interfaces/        # 인터페이스 정의
├── apps/
│   ├── api_server/        # HTTP API 서버
│   └── mcp_server/        # MCP 서버
├── infra/
│   ├── config/            # 인프라 설정
│   └── db/                # 데이터베이스 스크립트
├── tests/                 # 테스트
├── .docs/                 # 문서
│   └── northstar/         # 요구사항 문서
├── docker-compose.yml     # Docker 구성
├── Dockerfile.api         # API 서버 Dockerfile
├── .env.example           # 환경 변수 템플릿
├── Makefile              # 개발 명령어
└── pyproject.toml        # Python 프로젝트 설정
```

## 개발 가이드

### 로컬 개발 (Docker 없이)

```bash
# 의존성 설치
make dev

# 서비스는 Docker로 실행
make docker-up

# API 서버만 로컬에서 실행
export SEMANTICA_OPENAI_API_KEY=sk-...
export SEMANTICA_VECTOR_HOST=localhost
export SEMANTICA_DB_CONNECTION_STRING=postgresql://codegraph:codegraph_dev@localhost:5432/codegraph
export SEMANTICA_REDIS_HOST=localhost
export SEMANTICA_ZOEKT_HOST=http://localhost

uvicorn apps.api_server.main:app --reload --port 7200
```

### 테스트 실행

```bash
# 모든 테스트
make test

# 특정 테스트
pytest tests/test_search.py -v

# 커버리지 확인
pytest tests/ --cov=codegraph --cov-report=html
open htmlcov/index.html
```

### DB 마이그레이션 (Alembic)

```bash
# 새 리비전 생성 (모델 연결 전이라면 수동 작성)
alembic revision -m "init schema"

# 적용
SEMANTICA_DB_CONNECTION_STRING=postgresql://user:pass@localhost:5432/codegraph \
  alembic upgrade head

# 롤백
alembic downgrade -1
```

### 코드 품질

```bash
# 린트 & 타입 체크
make lint

# 자동 포맷팅
make format

# Pre-commit 훅 실행
pre-commit run --all-files
```

## 문서

- **[Docker Setup Guide](DOCKER_SETUP.md)**: Docker 상세 가이드
- **[DI Guide](DI_GUIDE.md)**: Dependency Injection 패턴 및 사용 규칙
- **[요구사항 문서](.docs/northstar/_A_01_requirements.md)**: 전체 요구사항 및 설계
- **[API 문서](http://localhost:7200/docs)**: OpenAPI/Swagger UI

## 주요 기능

### 1. 하이브리드 검색

- **Lexical**: Zoekt (BM25, substring, regex)
- **Semantic**: Qdrant (dense embeddings)
- **Graph**: Kùzu (구조적 관계)

### 2. GraphRAG

- 코드 구조, 호출 관계, 의존성 그래프
- ROUTE/ENTRYPOINT → handler → service → store 플로우
- 멀티홉 탐색

### 3. Git 통합

- 증분 인덱싱 (git diff 기반)
- 브랜치/PR별 네임스페이스
- Overlay 워킹트리 반영

### 4. Fallback 계층

- Level 0: Full Structure-RAG
- Level 1-3: 부분 기능 강등
- Level 4-5: LLM reasoning fallback

### 5. 보안 & ACL

- security_level 기반 필터링
- tenant_id 기반 멀티테넌시
- 라이선스/저작권 추적

## 트러블슈팅

### 포트 충돌

```bash
# .env 파일에서 포트 변경
API_PORT=7210
POSTGRES_PORT=7211
REDIS_PORT=7212
```

### 서비스 재시작

```bash
# 특정 서비스만 재시작
docker-compose restart api-server

# 모든 서비스 재시작
make docker-restart
```

### 로그 확인

```bash
# 모든 로그
make docker-logs

# API 서버만
make docker-logs-api

# 에러만 필터링
docker-compose logs api-server | grep ERROR
```

### 데이터 초기화

```bash
# ⚠️ 주의: 모든 데이터 삭제
make docker-clean

# 새로 시작
make docker-up
```

자세한 문제 해결 방법은 [DOCKER_SETUP.md](DOCKER_SETUP.md) 참조

## 라이선스

[라이선스 정보 추가 필요]

## 기여

[기여 가이드 추가 필요]

## 지원

- 이슈: [GitHub Issues](링크)
- 문서: `.docs/` 디렉토리
- API 문서: http://localhost:7200/docs
