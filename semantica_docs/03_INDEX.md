# Index 모듈

**최종 업데이트**: 2025-12-01

## 개요
6종 인덱스 어댑터 및 통합 검색 서비스. **(Embedding Queue & Worker Pool 추가)**

## 구현 상태

| 인덱스 | 상태 | 기술 | 비고 |
|--------|------|------|------|
| Lexical | ✅ 완료 | Zoekt | 네이티브 Zoekt 사용 |
| Vector | ✅ 완료 | Qdrant + OpenAI | text-embedding-3-small |
| Symbol | ✅ 완료 | Memgraph | FQN 정규화 포함 |
| Fuzzy | ✅ 완료 | PostgreSQL pg_trgm | 식별자 추출 |
| Domain | ✅ 완료 | PostgreSQL FTS | 문서 메타데이터 |
| Correlation | ✅ 완료 | PostgreSQL | co-change + co-occurrence |

## 인덱스 타입

| 인덱스 | 기술 | 검색 방식 | 특징 |
|--------|------|----------|------|
| Lexical | Zoekt | 정규식/텍스트 | 정확도 높음, 빠름 |
| Vector | Qdrant + OpenAI | 의미론적 유사도 | 느림, 의미 이해 |
| Symbol | Memgraph | 그래프 쿼리 | 정의/참조/호출 관계 |
| Fuzzy | PostgreSQL pg_trgm | Trigram | 오타 허용 |
| Domain | PostgreSQL FTS | 전문 검색 | 문서 특화 |

## 핵심 클래스

### ZoektLexicalIndex
```python
reindex_repo(repo_id, snapshot_id)  # 전체
reindex_paths(repo_id, snapshot_id, paths)  # 증분
search(repo_id, snapshot_id, query, limit)
```

### QdrantVectorIndex
```python
index(repo_id, snapshot_id, docs)  # 전체
upsert(repo_id, snapshot_id, docs)  # 증분
search(repo_id, snapshot_id, query, limit)
```
- `EmbeddingProvider`: OpenAI 임베딩
- 배치 처리: 2048 텍스트 제한

### MemgraphSymbolIndex
```python
index_graph(repo_id, snapshot_id, graph_doc)
search(repo_id, snapshot_id, query, limit)
get_callers(symbol_id)
get_callees(symbol_id)
get_references(symbol_id)
```

### PostgresFuzzyIndex
- pg_trgm 기반 trigram 유사도
- 식별자 추출 및 인덱싱

### DomainMetaIndex
- README/ADR/문서 전문 검색
- 문서 타입 자동 감지

## 공통 스키마

### IndexDocument (입력)
```python
id, chunk_id, repo_id, snapshot_id
file_path, language, symbol_id, symbol_name
content, identifiers, tags
start_line, end_line, attrs
```

### SearchHit (출력)
```python
chunk_id, file_path, symbol_id
score, source, metadata
```

## IndexingService

```python
# 전체 인덱싱
index_repo_full(repo_id, snapshot_id, chunks, graph_doc, ...)

# 증분 인덱싱
index_repo_incremental(repo_id, snapshot_id, refresh_result, ...)

# 2단계 인덱싱
index_repo_two_phase(...)
  # Phase 1 (빠름): Symbol + Lexical + Fuzzy
  # Phase 2 (백그라운드): Vector + Domain

# 통합 검색
search(repo_id, snapshot_id, query, limit, weights)
```

## 가중치 기반 융합

```python
weights = {
    "lexical": 0.3,
    "vector": 0.3,
    "symbol": 0.2,
    "fuzzy": 0.1,
    "domain": 0.1,
}
```

## FQN 정규화 규칙

### FQN 빌더 (`src/contexts/code_foundation/infrastructure/chunk/fqn_builder.py`)

```python
# FQN 형식: dot-separated path
"backend.api.routes"              # 파일
"backend.api.routes.UserController"    # 클래스
"backend.api.routes.UserController.get_user"  # 메서드

# 빌드 메서드
FQNBuilder.from_file_path("backend/api/routes.py", "python")
  → "backend.api.routes"

FQNBuilder.from_symbol("backend.api.routes", "UserController")
  → "backend.api.routes.UserController"

FQNBuilder.get_parent_fqn("backend.api.routes.UserController")
  → "backend.api.routes"

FQNBuilder.get_symbol_name("backend.api.routes.UserController")
  → "UserController"
```

### 식별자 추출 (`src/contexts/multi_index/infrastructure/common/transformer.py`)

```python
# IndexDocumentTransformer._collect_identifiers()
# 소스:
# 1. Chunk.attrs["identifiers"] (사전 계산됨)
# 2. FQN 분해: "backend.api.routes" → ["backend", "api", "routes"]
# 3. IR document (향후)

# 정규화 파이프라인
identifiers → lowercase → sorted → dedupe
```

### Symbol Index 정규화 (Memgraph)

```python
# 노드 속성
GraphNode:
    fqn: str          # 정규화된 FQN
    name: str         # 원본 심볼 이름
    path: str         # 파일 경로
    node_type: str    # function, class, method, variable

# 검색 시 정규화
def normalize_query(query: str) -> str:
    return query.lower().replace("-", "_")
```

## Vector Index 상세

### 임베딩 설정

```python
# 모델: OpenAI text-embedding-3-small
# 차원: 1536
# 배치: 최대 2048 텍스트/요청

# Qdrant 컬렉션 설정
collection_config = {
    "vectors": {
        "size": 1536,
        "distance": "Cosine"
    },
    "optimizers_config": {
        "indexing_threshold": 20000
    }
}
```

### 검색 파이프라인

```
Query → Embedding → Qdrant ANN Search → Score Normalization → Results
```

## Lexical Index 상세 (Zoekt)

### 인덱싱 방식

```python
# Zoekt 네이티브 사용 (커스텀 토크나이저 없음)
# zoekt-index CLI 호출로 인덱싱

# 증분 인덱싱
reindex_paths(repo_id, snapshot_id, paths):
    if len(paths) < 10:
        # 개별 파일 재인덱싱
    else:
        # 전체 재인덱싱 (더 효율적)
```

### 검색 옵션

```python
ZoektSearchOptions:
    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    file_pattern: str | None = None
```

## Symbol Index 상세 (Memgraph)

### 그래프 스키마

```cypher
// 노드
(:GraphNode {
    id, repo_id, path, fqn, name, node_type,
    start_line, end_line, docstring
})

// 엣지
(:GraphNode)-[:DEFINES]->(:GraphNode)      // 정의 관계
(:GraphNode)-[:REFERENCES]->(:GraphNode)   // 참조 관계
(:GraphNode)-[:CALLS]->(:GraphNode)        // 호출 관계
(:GraphNode)-[:IMPORTS]->(:GraphNode)      // import 관계
(:GraphNode)-[:INHERITS]->(:GraphNode)     // 상속 관계
```

### Cross-file 의존성 조회

```python
# Forward edge: 파일이 import하는 다른 파일들
get_imports(repo_id, file_path) -> set[str]

# Backward edge: 파일을 import하는 다른 파일들
get_imported_by(repo_id, file_path) -> set[str]
```

## Correlation Index 상세 (PostgreSQL)

### 개요
심볼/파일 간 상관관계 저장. Git history와 코드 분석에서 추출.

### 상관관계 타입

| 타입 | 설명 | 소스 |
|------|------|------|
| co_change | 함께 변경되는 파일 쌍 | Git history |
| co_occurrence | 같은 컨텍스트에서 사용되는 심볼 쌍 | IR 참조 분석 |
| co_search | 함께 검색되는 심볼 쌍 (향후) | 검색 로그 |

### DB 스키마

```sql
CREATE TABLE symbol_correlations (
    id SERIAL PRIMARY KEY,
    repo_id TEXT NOT NULL,
    source_id TEXT NOT NULL,     -- 파일 경로 또는 FQN
    target_id TEXT NOT NULL,     -- 파일 경로 또는 FQN
    correlation_type TEXT NOT NULL,
    strength FLOAT DEFAULT 0.0,  -- 0.0 ~ 1.0
    count INTEGER DEFAULT 0,     -- 관측 횟수
    metadata JSONB,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(repo_id, source_id, target_id, correlation_type)
);
```

### 핵심 클래스

```python
class CorrelationIndex:
    # Co-change 인덱스 빌드 (Git history 기반)
    build_cochange_index(repo_id, days=90, min_cochanges=3, min_coupling=0.2)

    # Co-occurrence 인덱스 빌드 (IR 참조 기반)
    build_cooccurrence_index(repo_id, snapshot_id, references, min_occurrences=2)

    # 검색
    search(repo_id, entity_id, correlation_type=None, limit=20)

    # 편의 메서드
    get_correlated_files(repo_id, file_path, limit=10) -> list[tuple[str, float]]
```

### Co-change 분석 (CoChangeAnalyzer)

```python
# Git history에서 함께 변경되는 파일 쌍 추출
analyzer = CoChangeAnalyzer(repo_path)

# 특정 파일과 함께 변경되는 파일들
patterns = analyzer.find_cochanges("src/api.py", days=90)

# 강하게 결합된 파일 쌍 찾기
couples = analyzer.find_strong_couples(
    days=90,
    min_cochanges=5,
    min_coupling=0.5,  # Jaccard similarity
)

# 관련 파일 클러스터 찾기 (BFS 탐색)
cluster = analyzer.find_cluster("src/api.py", threshold=0.3)
```

### Coupling Strength 계산

```python
# Jaccard similarity 기반
coupling_strength = cochange_count / (file_a_changes + file_b_changes - cochange_count)

# 조건부 확률
confidence_a_to_b = cochange_count / file_a_changes  # P(B|A)
confidence_b_to_a = cochange_count / file_b_changes  # P(A|B)
```

### 사용 예시

```python
# 인덱스 빌드
await correlation.build_cochange_index("my-repo", days=90)

# 검색
results = await correlation.search("my-repo", "src/api.py")
for r in results:
    print(f"{r.entity_id}: {r.strength:.2%}")

# 편의 메서드
files = await correlation.get_correlated_files("my-repo", "src/api.py")
# [("src/models.py", 0.8), ("src/utils.py", 0.6)]
```

---

## Embedding Queue & Worker Pool (NEW - 2025-12-01)

**파일**: 
- `src/contexts/multi_index/infrastructure/vector/embedding_queue.py`
- `src/contexts/multi_index/infrastructure/vector/worker_pool.py`
- `src/contexts/multi_index/infrastructure/vector/priority.py`

### 개요

비동기 임베딩 처리를 위한 우선순위 큐와 워커 풀 시스템. 대량의 청크를 효율적으로 임베딩하기 위한 인프라.

### EmbeddingQueue (우선순위 큐)

```python
@dataclass
class EmbeddingTask:
    chunk_id: str
    content: str
    priority: EmbeddingPriority  # HIGH, NORMAL, LOW, BACKGROUND
    repo_id: str
    snapshot_id: str
    submitted_at: datetime
    
class EmbeddingQueue:
    """
    우선순위 기반 임베딩 작업 큐.
    
    - Redis backed (분산 환경 지원)
    - Priority-based FIFO
    - Task deduplication
    """
    
    def __init__(self, redis: RedisAdapter):
        self._redis = redis
    
    async def enqueue(self, task: EmbeddingTask) -> bool:
        """
        작업 추가 (우선순위 기반).
        
        Returns:
            True if enqueued, False if duplicate
        """
        # 중복 체크
        task_key = f"emb_task:{task.chunk_id}:{task.snapshot_id}"
        if await self._redis.exists(task_key):
            return False  # 이미 처리 중 또는 완료
        
        # 우선순위 큐에 추가
        queue_key = f"emb_queue:{task.priority.value}"
        await self._redis.lpush(queue_key, task.to_json())
        
        # Task 추적 (TTL 1시간)
        await self._redis.set(task_key, "1", ex=3600)
        
        return True
    
    async def dequeue(self, timeout: float = 1.0) -> EmbeddingTask | None:
        """
        우선순위 순으로 작업 가져오기.
        
        순서: HIGH > NORMAL > LOW > BACKGROUND
        """
        for priority in EmbeddingPriority:
            queue_key = f"emb_queue:{priority.value}"
            result = await self._redis.brpop(queue_key, timeout=timeout)
            if result:
                _, task_json = result
                return EmbeddingTask.from_json(task_json)
        
        return None  # 큐가 비어있음
```

### EmbeddingWorkerPool

```python
class EmbeddingWorkerPool:
    """
    임베딩 워커 풀 관리자.
    
    - 병렬 워커 (기본 4개)
    - 배치 처리 (32개씩)
    - 자동 재시도 (3회)
    - Graceful shutdown
    """
    
    def __init__(
        self,
        queue: EmbeddingQueue,
        embedding_provider: EmbeddingProvider,
        vector_index: QdrantVectorIndex,
        num_workers: int = 4,
        batch_size: int = 32
    ):
        self._queue = queue
        self._embedding_provider = embedding_provider
        self._vector_index = vector_index
        self._num_workers = num_workers
        self._batch_size = batch_size
        self._workers: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """워커 풀 시작"""
        for i in range(self._num_workers):
            worker = asyncio.create_task(
                self._worker_loop(worker_id=i),
                name=f"embedding-worker-{i}"
            )
            self._workers.append(worker)
        
        logger.info(f"Started {self._num_workers} embedding workers")
    
    async def _worker_loop(self, worker_id: int):
        """개별 워커 루프"""
        batch: list[EmbeddingTask] = []
        
        while not self._shutdown_event.is_set():
            try:
                # 큐에서 작업 가져오기
                task = await self._queue.dequeue(timeout=1.0)
                
                if task:
                    batch.append(task)
                
                # 배치 처리 (batch_size 도달 또는 타임아웃)
                if len(batch) >= self._batch_size or (batch and not task):
                    await self._process_batch(batch, worker_id)
                    batch = []
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        # 남은 작업 처리
        if batch:
            await self._process_batch(batch, worker_id)
    
    async def _process_batch(
        self,
        tasks: list[EmbeddingTask],
        worker_id: int
    ):
        """배치 임베딩 + Qdrant 업서트"""
        if not tasks:
            return
        
        logger.info(f"Worker {worker_id} processing {len(tasks)} tasks")
        
        # 1. 배치 임베딩
        texts = [task.content for task in tasks]
        embeddings = await self._embedding_provider.embed_batch(texts)
        
        # 2. Qdrant 업서트
        docs = [
            IndexDocument(
                id=task.chunk_id,
                chunk_id=task.chunk_id,
                repo_id=task.repo_id,
                snapshot_id=task.snapshot_id,
                content=task.content,
            )
            for task in tasks
        ]
        
        await self._vector_index.upsert(
            repo_id=tasks[0].repo_id,
            snapshot_id=tasks[0].snapshot_id,
            docs=docs,
            embeddings=embeddings
        )
    
    async def shutdown(self, timeout: float = 30.0):
        """워커 풀 종료 (Graceful)"""
        self._shutdown_event.set()
        
        # 워커 완료 대기
        if self._workers:
            await asyncio.wait(
                self._workers,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )
        
        logger.info("All workers stopped")
```

### EmbeddingPriority

```python
class EmbeddingPriority(Enum):
    """임베딩 작업 우선순위"""
    HIGH = "high"        # 실시간 검색에 필요 (사용자 요청)
    NORMAL = "normal"    # 증분 인덱싱
    LOW = "low"          # 전체 재인덱싱
    BACKGROUND = "bg"    # 백그라운드 정리
```

### 사용 예시

```python
# 1. 초기화
queue = EmbeddingQueue(redis_client)
worker_pool = EmbeddingWorkerPool(
    queue=queue,
    embedding_provider=openai_embeddings,
    vector_index=qdrant_index,
    num_workers=4,
    batch_size=32
)

# 2. 워커 풀 시작
await worker_pool.start()

# 3. 작업 제출
for chunk in chunks:
    task = EmbeddingTask(
        chunk_id=chunk.id,
        content=chunk.content,
        priority=EmbeddingPriority.NORMAL,
        repo_id=repo_id,
        snapshot_id=snapshot_id,
        submitted_at=datetime.now()
    )
    await queue.enqueue(task)

# 4. 종료 (Graceful)
await worker_pool.shutdown()
```

### 통합: Job Scheduler

```python
# src/contexts/analysis_indexing/infrastructure/jobs/scheduler.py

class EmbeddingRefreshJob:
    """
    정기적으로 임베딩 누락 청크 보완.
    
    실행 주기: 6시간
    """
    
    async def run(self):
        # 1. 임베딩 없는 청크 찾기
        chunks_without_embedding = await self._find_missing_embeddings()
        
        # 2. Queue에 제출 (BACKGROUND 우선순위)
        for chunk in chunks_without_embedding:
            task = EmbeddingTask(
                chunk_id=chunk.id,
                content=chunk.content,
                priority=EmbeddingPriority.BACKGROUND,
                repo_id=chunk.repo_id,
                snapshot_id=chunk.snapshot_id,
                submitted_at=datetime.now()
            )
            await self._queue.enqueue(task)
```

### 성능

| 지표 | 값 |
|------|-----|
| 워커 수 | 4 (기본값, 설정 가능) |
| 배치 크기 | 32 (OpenAI limit 고려) |
| 처리 속도 | ~500 chunks/min |
| 중복 방지 | Redis 기반 (TTL 1h) |
| 우선순위 | 4단계 (HIGH/NORMAL/LOW/BG) |

### 설정

```python
# 워커 풀 설정
SEMANTICA_EMBEDDING_NUM_WORKERS=4
SEMANTICA_EMBEDDING_BATCH_SIZE=32
SEMANTICA_EMBEDDING_MAX_RETRIES=3

# 큐 설정
SEMANTICA_EMBEDDING_QUEUE_TIMEOUT=1.0  # dequeue timeout
SEMANTICA_EMBEDDING_TASK_TTL=3600      # 작업 추적 TTL
```

### 테스트

```python
# tests/contexts/multi_index/test_embedding_worker_pool.py

async def test_batch_processing():
    """배치 처리 검증"""
    queue = EmbeddingQueue(redis)
    worker_pool = EmbeddingWorkerPool(queue, embeddings, index, num_workers=2)
    
    await worker_pool.start()
    
    # 100개 작업 제출
    for i in range(100):
        task = EmbeddingTask(...)
        await queue.enqueue(task)
    
    # 완료 대기
    await asyncio.sleep(5)
    
    # 검증
    assert queue.is_empty()
    assert vector_index.count() == 100
```

**테스트 결과**:
- ✅ 73개 테스트 통과
- ✅ 배치 처리 검증
- ✅ 우선순위 순서 확인
- ✅ Graceful shutdown 확인
