# Semantica v2 프로파일 설정 가이드

환경별로 최적화된 설정을 제공하는 프로파일 시스템입니다.

## 프로파일 종류

### 1. `local` - 로컬 개발 환경 (기본값)

**특징:**
- 최소 의존성
- Redis, Memgraph 선택적
- 빠른 시작
- 단일 에이전트

**사용 시나리오:**
- 로컬 개발
- 빠른 프로토타이핑
- 단위 테스트

**필수 서비스:**
- PostgreSQL
- Qdrant

**선택 서비스:**
- Redis (없으면 메모리 기반 캐시/락)
- Memgraph (없으면 경량 분석)

**설정:**
```bash
export SEMANTICA_PROFILE=local
cp .env.local.example .env
```

### 2. `cloud` - 클라우드/프로덕션 환경

**특징:**
- 모든 서비스 필수
- Multi-Agent 활성화
- 모니터링 활성화
- 분산 락 (Redis)

**사용 시나리오:**
- 프로덕션 배포
- 다중 서버 환경
- 대규모 처리

**필수 서비스:**
- PostgreSQL
- Redis
- Qdrant
- Memgraph

**설정:**
```bash
export SEMANTICA_PROFILE=cloud
cp .env.cloud.example .env
```

### 3. `dev` - 개발 서버 환경

**특징:**
- 대부분 서비스 활성화
- Multi-Agent 활성화
- 디버그 로깅
- 선택적 모니터링

**사용 시나리오:**
- 개발 서버
- 통합 테스트
- 스테이징 환경

**설정:**
```bash
export SEMANTICA_PROFILE=dev
```

### 4. `prod` - 프로덕션 환경

**특징:**
- 모든 서비스 필수
- 최고 보안
- 최소 로깅
- 모니터링 필수

**사용 시나리오:**
- 프로덕션 배포
- 엄격한 보안 요구사항

**설정:**
```bash
export SEMANTICA_PROFILE=prod
```

## 프로파일별 비교

| 기능 | local | cloud | dev | prod |
|------|-------|-------|-----|------|
| PostgreSQL | ✅ 필수 | ✅ 필수 | ✅ 필수 | ✅ 필수 |
| Redis | ⚠️  선택 | ✅ 필수 | ✅ 필수 | ✅ 필수 |
| Qdrant | ✅ 필수 | ✅ 필수 | ✅ 필수 | ✅ 필수 |
| Memgraph | ⚠️  선택 | ✅ 필수 | ✅ 필수 | ✅ 필수 |
| Multi-Agent | 🚫 비활성화 | ✅ 활성화 | ✅ 활성화 | ✅ 활성화 |
| 모니터링 | 🚫 비활성화 | ✅ 활성화 | ⚠️  선택 | ✅ 필수 |
| 로그 레벨 | DEBUG | INFO | DEBUG | WARNING |

## 사용 방법

### 1. 환경 변수로 설정

```bash
export SEMANTICA_PROFILE=local
```

### 2. .env 파일에 설정

```bash
SEMANTICA_PROFILE=local
```

### 3. 개별 서비스 제어

프로파일 기본값을 덮어쓸 수 있습니다:

```bash
# Redis를 명시적으로 비활성화
export SEMANTICA_USE_REDIS=false

# Memgraph를 명시적으로 활성화
export SEMANTICA_USE_MEMGRAPH=true
```

## 로컬 개발 빠른 시작

### 최소 구성 (PostgreSQL + Qdrant만)

```bash
# 1. 프로파일 설정
export SEMANTICA_PROFILE=local

# 2. .env 복사
cp .env.local.example .env

# 3. 필수 서비스만 실행
docker-compose up -d postgres qdrant

# 4. 실행
python -m src.cli.agent_v2 analyze
```

**동작:**
- ✅ PostgreSQL 사용
- ✅ Qdrant 사용
- 🔄 Redis → 메모리 기반 캐시/락 자동 전환
- 🔄 Memgraph → 경량 분석 모드 자동 전환

### 전체 구성 (모든 서비스)

```bash
# 1. 프로파일 설정
export SEMANTICA_PROFILE=local

# 2. Redis, Memgraph 활성화
export SEMANTICA_USE_REDIS=true
export SEMANTICA_USE_MEMGRAPH=true

# 3. 모든 서비스 실행
docker-compose up -d

# 4. 실행
python -m src.cli.agent_v2 analyze
```

## 클라우드 배포

### Docker Compose

```bash
# 1. 프로파일 설정
export SEMANTICA_PROFILE=cloud

# 2. .env 설정
cp .env.cloud.example .env
# .env 파일 편집

# 3. 배포
docker-compose -f docker-compose.agent.yml up -d
```

### Kubernetes

```bash
# 1. ConfigMap 생성
kubectl create configmap semantica-config \
  --from-literal=SEMANTICA_PROFILE=prod

# 2. Secrets 생성
kubectl create secret generic semantica-secrets \
  --from-literal=SEMANTICA_OPENAI_API_KEY=your-key

# 3. 배포
kubectl apply -f k8s/deployment.yaml
```

## 프로파일 자동 감지

시스템은 다음 순서로 프로파일을 결정합니다:

1. `SEMANTICA_PROFILE` 환경 변수
2. `.env` 파일의 `SEMANTICA_PROFILE`
3. 기본값: `local`

## 프로파일별 최적화

### Local 프로파일
- 메모리 기반 락 (Redis 불필요)
- 경량 그래프 분석 (Memgraph 불필요)
- 빠른 시작 시간
- 낮은 리소스 사용

### Cloud 프로파일
- 분산 락 (Redis)
- 완전한 그래프 분석 (Memgraph)
- Multi-Agent 협업
- Prometheus 모니터링
- 고가용성

## 문제 해결

### "Redis 연결 실패" 에러

**Local 프로파일:**
```bash
# Redis 없이도 작동 - 메모리 모드로 자동 전환
export SEMANTICA_USE_REDIS=false
```

**Cloud 프로파일:**
```bash
# Redis 필수 - 서비스 확인
docker-compose up -d redis
```

### "Memgraph 연결 실패" 에러

**Local 프로파일:**
```bash
# Memgraph 없이도 작동 - 경량 모드로 자동 전환
export SEMANTICA_USE_MEMGRAPH=false
```

**Cloud 프로파일:**
```bash
# Memgraph 필수 - 서비스 확인
docker-compose up -d memgraph
```

## 모범 사례

### 로컬 개발
```bash
# 최소 구성으로 빠르게 시작
export SEMANTICA_PROFILE=local
docker-compose up -d postgres qdrant
```

### CI/CD
```bash
# 테스트용 경량 구성
export SEMANTICA_PROFILE=local
export SEMANTICA_USE_REDIS=false
export SEMANTICA_USE_MEMGRAPH=false
```

### 스테이징
```bash
# 프로덕션과 유사하지만 디버그 가능
export SEMANTICA_PROFILE=dev
```

### 프로덕션
```bash
# 완전한 기능, 최고 보안
export SEMANTICA_PROFILE=prod
```

## 참고

- [환경 설정 가이드](./CONFIGURATION.md)
- [Docker 설정](../docker-compose.agent.yml)
- [프로덕션 배포](./PRODUCTION_DEPLOYMENT.md)
