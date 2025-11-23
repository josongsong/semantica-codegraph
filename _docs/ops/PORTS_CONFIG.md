# 포트 설정 및 관리

**문서 목적:**
Semantica Codegraph v4의 서비스별 포트 매핑 및 관리 가이드

**범위:**
- 서비스별 포트 매핑
- 포트 충돌 해결
- 보안 설정
- 개발 환경 최적화

**최종 수정:** 2025-01-23

---

## 1. 개요

Semantica Codegraph v4는 모든 서비스 포트를 **72xx** 형태로 통일하여 관리합니다.

### 1.1 포트 범위 정책

- **7200번대**: Codegraph 전용 포트
- **순차적 번호**: 서비스별로 순차 할당
- **충돌 최소화**: 일반적으로 사용되지 않는 범위 선택

---

## 2. 서비스별 포트 매핑

### 2.1 포트 목록

| 포트 | 서비스 | 설명 | 프로토콜 |
|------|--------|------|---------|
| **7200** | API Server | FastAPI HTTP API 서버 | HTTP |
| **7201** | PostgreSQL | 메타데이터, 세션, 협업 정보 저장소 | TCP |
| **7202** | Redis | 세션, 캐시, 협업 메타데이터 | TCP |
| **7203** | Qdrant HTTP | 벡터 검색 (HTTP API) | HTTP |
| **7204** | Qdrant gRPC | 벡터 검색 (gRPC) | gRPC |
| **7205** | Zoekt | Lexical 검색 (BM25 + substring + regex) | HTTP |

### 2.2 접속 URL

#### API Server
- **API 문서**: http://localhost:7200/docs
- **Health Check**: http://localhost:7200/health
- **Redoc**: http://localhost:7200/redoc

#### Qdrant
- **대시보드**: http://localhost:7203/dashboard
- **API**: http://localhost:7203
- **gRPC**: localhost:7204

#### Zoekt
- **검색 인터페이스**: http://localhost:7205

#### PostgreSQL
```bash
psql -h localhost -p 7201 -U codegraph -d codegraph
```

#### Redis
```bash
redis-cli -h localhost -p 7202 -a codegraph_redis
```

---

## 3. 환경 변수 설정

### 3.1 기본 설정

`.env` 파일에서 포트를 설정합니다:

```bash
# 기본 포트 설정
API_PORT=7200
POSTGRES_PORT=7201
REDIS_PORT=7202
QDRANT_HTTP_PORT=7203
QDRANT_GRPC_PORT=7204
ZOEKT_PORT=7205
```

### 3.2 포트 충돌 시 변경

```bash
# 포트 충돌 시 변경 예시 (7210번대로 이동)
API_PORT=7210
POSTGRES_PORT=7211
REDIS_PORT=7212
QDRANT_HTTP_PORT=7213
QDRANT_GRPC_PORT=7214
ZOEKT_PORT=7215
```

---

## 4. 포트 확인 및 관리

### 4.1 사용 중인 포트 확인

#### macOS/Linux
```bash
# 특정 포트 확인
lsof -i :7200

# 범위 확인
lsof -i :7201-7205

# netstat 사용
netstat -an | grep 720
```

#### Windows
```powershell
# 특정 포트 확인
netstat -ano | findstr :7200

# 프로세스 확인
Get-Process -Id (Get-NetTCPConnection -LocalPort 7200).OwningProcess
```

### 4.2 Docker 컨테이너 포트 확인

```bash
# 모든 컨테이너 포트 확인
docker-compose ps

# 특정 컨테이너 포트 상세 확인
docker port codegraph-api
docker port codegraph-postgres
docker port codegraph-redis
docker port codegraph-qdrant
docker port codegraph-zoekt-web
```

---

## 5. 포트 충돌 해결

### 5.1 진단 절차

1. **포트 사용 확인**
   ```bash
   lsof -i :7200
   ```

2. **프로세스 식별**
   - PID 확인
   - 프로세스 이름 확인
   - 프로세스 소유자 확인

3. **해결 방법 선택**
   - 기존 프로세스 종료
   - 포트 변경
   - Docker 재시작

### 5.2 프로세스 종료

```bash
# PID 확인
lsof -i :7200

# 프로세스 종료 (PID 확인 후)
kill -9 <PID>

# 또는 서비스 중지
docker-compose down
```

### 5.3 포트 변경 후 재시작

```bash
# 1. .env 파일 수정
# API_PORT=7210

# 2. Docker 재시작
make docker-restart

# 또는
docker-compose down && docker-compose up -d
```

---

## 6. 보안 설정

### 6.1 프로덕션 환경 설정

프로덕션 환경에서는 외부 접근을 제한하세요:

```yaml
# docker-compose.yml
services:
  postgres:
    ports:
      - "127.0.0.1:7201:5432"  # localhost만 허용

  redis:
    ports:
      - "127.0.0.1:7202:6379"  # localhost만 허용

  qdrant:
    ports:
      - "127.0.0.1:7203:6333"  # localhost만 허용
      - "127.0.0.1:7204:6334"  # localhost만 허용
```

### 6.2 방화벽 설정

#### macOS
```bash
# Docker 허용 (필요시)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/local/bin/docker
```

#### Linux (ufw)
```bash
# 개발 환경: 포트 범위 허용
sudo ufw allow 7200:7205/tcp

# 프로덕션: 필요한 포트만 허용
sudo ufw allow 7200/tcp  # API Server만
```

### 6.3 네트워크 분리

민감한 서비스는 별도 네트워크로 분리:

```yaml
# docker-compose.yml
networks:
  frontend:
    # API Server만 노출
  backend:
    # DB, Redis, Qdrant 등은 내부망
    internal: true

services:
  api:
    networks:
      - frontend
      - backend

  postgres:
    networks:
      - backend  # 외부 접근 불가
```

---

## 7. 개발 환경 최적화

### 7.1 포트 기억 팁

- **7200**: API Server (시작점) - "API는 첫 번째"
- **7201**: PostgreSQL - "데이터베이스는 두 번째"
- **7202**: Redis - "캐시는 세 번째"
- **7203/7204**: Qdrant - "벡터는 3-4번"
- **7205**: Zoekt - "검색은 마지막"

### 7.2 쉘 Alias 설정

개발 효율성을 위한 alias 추가:

```bash
# ~/.bashrc 또는 ~/.zshrc
alias cg-api="curl http://localhost:7200/health"
alias cg-api-docs="open http://localhost:7200/docs"
alias cg-db="psql -h localhost -p 7201 -U codegraph -d codegraph"
alias cg-redis="redis-cli -h localhost -p 7202 -a codegraph_redis"
alias cg-qdrant="open http://localhost:7203/dashboard"
alias cg-zoekt="open http://localhost:7205"
alias cg-ports="docker-compose ps"
```

### 7.3 헬스체크 스크립트

모든 서비스 상태를 한번에 확인:

```bash
#!/bin/bash
# scripts/health-check.sh

echo "🔍 Checking Codegraph service health..."
echo ""

# API Server
if curl -sf http://localhost:7200/health > /dev/null 2>&1; then
  echo "✅ API Server (7200)"
else
  echo "❌ API Server (7200)"
fi

# PostgreSQL
if pg_isready -h localhost -p 7201 -U codegraph > /dev/null 2>&1; then
  echo "✅ PostgreSQL (7201)"
else
  echo "❌ PostgreSQL (7201)"
fi

# Redis
if redis-cli -h localhost -p 7202 -a codegraph_redis ping > /dev/null 2>&1; then
  echo "✅ Redis (7202)"
else
  echo "❌ Redis (7202)"
fi

# Qdrant
if curl -sf http://localhost:7203/ > /dev/null 2>&1; then
  echo "✅ Qdrant HTTP (7203)"
else
  echo "❌ Qdrant HTTP (7203)"
fi

# Zoekt
if curl -sf http://localhost:7205/ > /dev/null 2>&1; then
  echo "✅ Zoekt (7205)"
else
  echo "❌ Zoekt (7205)"
fi

echo ""
echo "🏁 Health check complete"
```

사용법:
```bash
chmod +x scripts/health-check.sh
./scripts/health-check.sh
```

---

## 8. 트러블슈팅

### 8.1 일반적인 문제

#### "Port already in use" 오류
```bash
# 1. 포트 사용 프로세스 확인
lsof -i :7200

# 2. Docker 컨테이너 확인
docker ps

# 3. 해결책
# - Docker 컨테이너 재시작: docker-compose restart
# - 포트 변경: .env 파일 수정
# - 충돌 프로세스 종료: kill <PID>
```

#### 서비스 연결 실패
```bash
# 1. 서비스 실행 확인
docker-compose ps

# 2. 로그 확인
docker-compose logs <service-name>

# 3. 네트워크 확인
docker network ls
docker network inspect codegraph_default
```

#### 방화벽 차단
```bash
# macOS: 방화벽 상태 확인
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# Linux: ufw 상태 확인
sudo ufw status
```

### 8.2 체크리스트

서비스 시작 전 확인사항:

- [ ] `.env` 파일에 포트 설정이 올바른가?
- [ ] 포트가 이미 사용 중이지 않은가?
- [ ] Docker 데몬이 실행 중인가?
- [ ] 방화벽 설정이 올바른가?
- [ ] 네트워크 설정이 올바른가?

---

## 9. 참고 자료

- [Docker Compose 설정](../../docker-compose.yml)
- [환경 변수 템플릿](../../.env.example)
- [Docker 설정 가이드](../../DOCKER_SETUP.md)
- [배포 가이드](DEPLOYMENT_GUIDE.md)

---

## 10. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2025-01-23 | 1.0 | 초안 작성 | - |
