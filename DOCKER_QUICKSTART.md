# Docker Quickstart Guide

## 초기 설정

1. 환경 변수 파일 생성:
```bash
cp .env.example .env
```

2. `.env` 파일에서 필요한 값 수정:
```bash
# 최소한 OpenAI API Key는 설정 필요
OPENAI_API_KEY=sk-your-actual-key-here
```

## 서비스 시작

### 전체 서비스 시작
```bash
docker-compose up -d
```

### 개별 서비스만 시작
```bash
# Redis만 시작
docker-compose up -d redis

# Postgres + Redis
docker-compose up -d postgres redis

# 핵심 인프라만 (Postgres, Redis, Qdrant)
docker-compose up -d postgres redis qdrant
```

### 로그 확인
```bash
# 전체 서비스 로그
docker-compose logs -f

# Redis 로그만
docker-compose logs -f redis

# 최근 100줄만
docker-compose logs --tail=100 -f redis
```

## 포트 규칙 (7200번대)

| 서비스 | 호스트 포트 | 컨테이너 포트 | 설명 |
|--------|------------|--------------|------|
| API Server | 7200 | 8000 | FastAPI HTTP API |
| Postgres | 7201 | 5432 | 관계형 DB |
| **Redis** | **7202** | **6379** | **캐시/세션 스토어** |
| Qdrant HTTP | 7203 | 6333 | 벡터 검색 (HTTP) |
| Qdrant gRPC | 7204 | 6334 | 벡터 검색 (gRPC) |
| Zoekt | 7205 | 6070 | Lexical 검색 |

## Redis 접속 테스트

### 1. Docker 컨테이너 내부에서
```bash
docker exec -it codegraph-redis redis-cli -a codegraph_redis
```

### 2. 로컬에서 (redis-cli 설치된 경우)
```bash
redis-cli -h localhost -p 7202 -a codegraph_redis
```

### 3. Python으로 테스트
```python
import asyncio
from redis.asyncio import Redis

async def test_redis():
    client = Redis(
        host="localhost",
        port=7202,
        password="codegraph_redis",
        db=0,
        decode_responses=True
    )

    # Set
    await client.set("test_key", "Hello Redis!")

    # Get
    value = await client.get("test_key")
    print(f"Value: {value}")

    # Ping
    pong = await client.ping()
    print(f"Ping: {pong}")

    await client.aclose()

asyncio.run(test_redis())
```

## 서비스 상태 확인

### Health Check
```bash
# 모든 서비스 상태
docker-compose ps

# Redis 상태만
docker-compose ps redis
```

### 컨테이너 내부 확인
```bash
# Redis 컨테이너 내부 접속
docker exec -it codegraph-redis sh

# Redis 정보 확인
docker exec codegraph-redis redis-cli -a codegraph_redis INFO
```

## 서비스 중지

```bash
# 전체 중지
docker-compose down

# 볼륨까지 삭제 (데이터 완전 삭제)
docker-compose down -v

# Redis만 중지
docker-compose stop redis
```

## 트러블슈팅

### Redis 연결 안됨
```bash
# 1. 컨테이너 상태 확인
docker-compose ps redis

# 2. 로그 확인
docker-compose logs redis

# 3. 포트 충돌 확인
lsof -i :7202

# 4. 재시작
docker-compose restart redis
```

### 데이터 초기화
```bash
# Redis 데이터만 삭제
docker-compose down
docker volume rm codegraph_redis_data
docker-compose up -d redis
```

### 비밀번호 변경
1. `.env` 파일에서 `REDIS_PASSWORD` 변경
2. 재시작:
```bash
docker-compose down redis
docker-compose up -d redis
```

## 개발 팁

### 로컬 개발 시 비밀번호 없이 사용하려면
docker-compose.yml 수정:
```yaml
redis:
  command: redis-server --appendonly yes  # --requirepass 제거
```

### Redis Desktop Manager 연결
- Host: localhost
- Port: 7202
- Auth: codegraph_redis
- Name: Codegraph Dev

### 메모리 사용량 확인
```bash
docker exec codegraph-redis redis-cli -a codegraph_redis INFO memory
```

### 캐시 전체 삭제 (개발용)
```bash
docker exec codegraph-redis redis-cli -a codegraph_redis FLUSHALL
```
