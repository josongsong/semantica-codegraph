# Search Logging for ML Tuning

검색 로그 수집 인프라. Late Interaction 튜닝, Chunk 품질 학습 등에 활용.

## 설치

### 1. Migration 실행

```bash
just up          # Start PostgreSQL
just migrate     # Run migrations (includes 025_create_search_logs)
```

### 2. Container에서 사용

```python
from src.container import container

# Search logger 접근
logger = container.search_logger
```

## 사용법

### 기본 로깅

```python
from src.retriever.logging import SearchLogger

logger = SearchLogger(db_pool)

# 검색 실행 시
log_id = await logger.log_search(
    query="find authentication logic",
    repo_id="my-repo",
    intent="symbol",
    results=[
        {"chunk_id": "chunk1", "score": 0.95},
        {"chunk_id": "chunk2", "score": 0.87},
    ],
    fusion_strategy="rrf",
    late_interaction_scores={"max_sims": [0.9, 0.8, 0.7]},
    user_id="user123",
    session_id="session456",
)

# 사용자 피드백 시
await logger.log_feedback(
    log_id=log_id,
    clicked_rank=1,          # 1-indexed
    clicked_chunk_id="chunk1",
    was_helpful=True,
)
```

### RetrieverV3 통합 (예정)

```python
# src/retriever/v3/orchestrator.py에 통합 예정
class RetrieverV3Orchestrator:
    def __init__(self, ..., search_logger=None):
        self.search_logger = search_logger
    
    async def search(self, query, ...):
        # ... 검색 로직 ...
        
        if self.search_logger:
            log_id = await self.search_logger.log_search(
                query=query,
                repo_id=repo_id,
                results=final_results,
                # ...
            )
        
        return context
```

## 데이터 추출

### Golden Set 구축

```bash
# Chunk quality golden set 생성
python scripts/build_chunk_golden_set.py \
    --min-impressions 10 \
    --positive-limit 100 \
    --negative-limit 100 \
    --output data/chunk_golden_set.json

# 또는
just ml-build-chunk-golden
```

### 학습 데이터 추출 (SQL)

```sql
-- 클릭율 높은 chunk (positive samples)
SELECT 
    chunk_id,
    COUNT(*) as impressions,
    SUM(CASE WHEN clicked_rank IS NOT NULL THEN 1 ELSE 0 END) as clicks,
    SUM(CASE WHEN clicked_rank IS NOT NULL THEN 1 ELSE 0 END)::float / COUNT(*) as ctr
FROM search_logs
GROUP BY chunk_id
HAVING COUNT(*) >= 10
ORDER BY ctr DESC
LIMIT 100;

-- Late Interaction 학습 데이터
SELECT 
    log_id,
    query,
    max_sim_scores,
    result_chunk_ids,
    clicked_rank,
    was_helpful
FROM search_logs
WHERE 
    late_interaction_enabled = true
    AND (clicked_rank IS NOT NULL OR was_helpful IS NOT NULL)
ORDER BY timestamp DESC
LIMIT 1000;
```

## 스키마

```sql
CREATE TABLE search_logs (
    log_id VARCHAR(64) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Query context
    query TEXT NOT NULL,
    intent VARCHAR(20),
    repo_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255),
    session_id VARCHAR(64),
    
    -- Retrieval details
    candidate_count INTEGER,
    fusion_strategy VARCHAR(50),
    
    -- Late Interaction
    late_interaction_enabled BOOLEAN DEFAULT false,
    max_sim_scores JSONB,
    
    -- Results
    top_k INTEGER,
    result_chunk_ids TEXT[],
    result_scores FLOAT[],
    
    -- User feedback
    clicked_rank INTEGER,
    clicked_chunk_id VARCHAR(64),
    dwell_time FLOAT,
    was_helpful BOOLEAN,
    
    -- Metadata
    metadata JSONB
);
```

## 성능

- **버퍼링**: 기본 100개 쌓일 때마다 flush
- **비동기**: `enable_async=True`로 버퍼 활성화
- **수동 flush**: `await logger.close()` 호출

```python
# 즉시 저장 (테스트용)
logger = SearchLogger(db_pool, enable_async=False)

# 버퍼링 (프로덕션)
logger = SearchLogger(db_pool, enable_async=True, buffer_size=100)

# 종료 시 flush
await logger.close()
```

## 다음 단계

1. ✅ Migration 생성 (`025_create_search_logs`)
2. ✅ SearchLogger 구현
3. ✅ Container 통합
4. ⏳ RetrieverV3Orchestrator 통합
5. ⏳ MCP 서버 피드백 엔드포인트
6. ⏳ 로그 1000+ 수집
7. ⏳ Token importance 모델 학습

자세한 계획: `.temp/ML_튜닝_진행계획_2025-11-29.md`

