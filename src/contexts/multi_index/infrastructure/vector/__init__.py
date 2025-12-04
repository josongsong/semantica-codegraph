"""
Vector Index Infrastructure

구성:
- adapter_qdrant.py: Qdrant vector index 구현
- priority.py: Chunk 우선순위 규칙
- embedding_queue.py: Priority queue (PostgreSQL)
- worker_pool.py: Event-driven worker pool
- scheduler.py: Legacy polling scheduler (deprecated)

패키지 구조:
```
vector/
├── adapter_qdrant.py      # VectorIndexPort 구현
├── priority.py            # 우선순위 규칙 (재사용 가능)
├── embedding_queue.py     # Queue 관리 (DB 작업)
├── worker_pool.py         # Event-driven workers (권장)
└── scheduler.py           # Polling scheduler (deprecated)
```

사용:
```python
from src.contexts.multi_index.infrastructure.vector import (
    QdrantVectorIndex,
    EmbeddingQueue,
    EmbeddingWorkerPool,
)

# 생성
queue = EmbeddingQueue(postgres, provider, vector_index, chunk_store)
pool = EmbeddingWorkerPool(queue, worker_count=3)

# 시작
await pool.start()

# enqueue 시 자동 notify
await queue.enqueue(chunks, repo_id, snapshot_id)
# → pool.notify() 자동 호출 → worker 즉시 처리
```
"""

from src.contexts.multi_index.infrastructure.vector.adapter_qdrant import (
    OpenAIEmbeddingProvider,
    QdrantVectorIndex,
)
from src.contexts.multi_index.infrastructure.vector.embedding_queue import EmbeddingQueue
from src.contexts.multi_index.infrastructure.vector.priority import (
    CHUNK_PRIORITY,
    HIGH_PRIORITY_THRESHOLD,
    get_chunk_priority,
    is_high_priority,
    partition_by_priority,
)
from src.contexts.multi_index.infrastructure.vector.worker_pool import EmbeddingWorkerPool

__all__ = [
    # Core
    "QdrantVectorIndex",
    "OpenAIEmbeddingProvider",
    # Priority
    "CHUNK_PRIORITY",
    "HIGH_PRIORITY_THRESHOLD",
    "get_chunk_priority",
    "is_high_priority",
    "partition_by_priority",
    # Queue + Worker Pool (Event-driven)
    "EmbeddingQueue",
    "EmbeddingWorkerPool",
]
