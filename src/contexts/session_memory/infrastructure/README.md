# Memory System

3-Tier 메모리 아키텍처로 에이전트가 과거 경험에서 학습하고 점점 똑똑해지도록 합니다.

## 📐 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      Memory System                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐                                             │
│  │ Working Memory │  ← 현재 세션 (휘발성)                       │
│  │  (Short-term)  │    - 현재 태스크 상태                       │
│  │                │    - 최근 N개 스텝 결과                     │
│  │                │    - 활성화된 컨텍스트                       │
│  └───────┬────────┘                                             │
│          │ consolidate                                           │
│          ▼                                                       │
│  ┌────────────────┐                                             │
│  │Episodic Memory │  ← 세션/태스크 단위 (영구 저장)             │
│  │  (Mid-term)    │    - 완료된 태스크 기록                     │
│  │                │    - 성공/실패 에피소드                     │
│  │                │    - 문제-해결 페어                         │
│  └───────┬────────┘                                             │
│          │ extract patterns                                      │
│          ▼                                                       │
│  ┌────────────────┐                                             │
│  │Semantic Memory │  ← 일반화된 지식 (영구 저장)                │
│  │  (Long-term)   │    - 코드 패턴                              │
│  │                │    - 프로젝트 규칙                          │
│  │                │    - 버그 패턴 → 솔루션 매핑                │
│  │                │    - 사용자 선호도                          │
│  └────────────────┘                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 🗂️ 구조

```
src/memory/
├── __init__.py              # Package exports
├── models.py                # 데이터 모델 (Episode, BugPattern, etc.)
├── working.py               # Working Memory Manager
├── episodic.py              # Episodic Memory Manager
├── semantic.py              # Semantic Memory Manager
├── retrieval.py             # Memory Retrieval System (orchestrator)
└── persistence/
    ├── __init__.py
    └── store.py             # Storage abstractions
```

## 📦 주요 컴포넌트

### 1. Working Memory (단기 기억)

현재 세션의 상태를 관리합니다.

```python
from src.memory import WorkingMemoryManager

# 세션 시작
working_memory = WorkingMemoryManager()
working_memory.init_task({
    "query": "Fix authentication bug",
    "type": "debug"
})

# 실행 추적
working_memory.track_file("src/auth/login.py", modified=True)
working_memory.add_hypothesis(
    "Token validation fails due to timezone",
    confidence=0.8
)
working_memory.record_decision(
    description="Use UTC for all token operations",
    rationale="Timezone mismatch causing validation failures"
)

# 세션 종료 시 consolidate
episode = working_memory.consolidate()
```

### 2. Episodic Memory (중기 기억)

완료된 에피소드를 저장하고 검색합니다.

```python
from src.memory import EpisodicMemoryManager, SimilarityQuery, TaskType

episodic = EpisodicMemoryManager()

# 에피소드 저장
await episodic.store(episode)

# 유사한 에피소드 검색
similar = await episodic.find_similar(
    SimilarityQuery(
        task_type=TaskType.DEBUG,
        files=["src/auth/login.py"],
        limit=5
    )
)

# 에러 패턴으로 검색
error_episodes = await episodic.find_by_error_pattern(
    error_type="TokenValidationError"
)
```

### 3. Semantic Memory (장기 기억)

일반화된 패턴과 지식을 학습합니다.

```python
from src.memory import SemanticMemoryManager

semantic = SemanticMemoryManager()

# 에피소드에서 학습
await semantic.learn_from_episode(episode)

# 버그 패턴 매칭
patterns = await semantic.match_bug_pattern(
    error_type="TokenValidationError",
    error_message="Token validation failed"
)

# 프로젝트 지식 조회
knowledge = semantic.get_or_create_project_knowledge("my-project")
print(f"Success rate: {knowledge.success_rate:.1%}")
print(f"Bug-prone files: {knowledge.bug_prone}")
```

### 4. Memory Retrieval System (통합 시스템)

모든 메모리 레이어를 조율합니다.

```python
from src.memory import create_memory_system

# 전체 시스템 생성
memory = create_memory_system()

# 태스크 시작 시 관련 메모리 로드
memories = await memory.load_relevant_memories(
    task_description="Fix database timeout",
    task_type=TaskType.DEBUG,
    project_id="my-project",
    error_type="TimeoutError"
)

# Guidance 활용
guidance = memories["guidance"]
print(f"Suggested approach: {guidance.suggested_approach}")
print(f"Things to try: {guidance.things_to_try}")
print(f"Things to avoid: {guidance.things_to_avoid}")

# 실행 중 쿼리
error_solutions = await memory.query_similar_error(
    error_type="TimeoutError"
)

# 세션 종료 시 학습
await memory.learn_from_session(episode)
```

## 🔌 Agent Orchestrator 통합

메모리 기능을 추가한 Orchestrator를 사용합니다:

```python
from src.agent.orchestrator_with_memory import MemoryEnhancedOrchestrator
from src.agent.types import Task

# 메모리 통합 Orchestrator 생성
orchestrator = MemoryEnhancedOrchestrator(
    project_id="my-project",
    enable_memory=True
)

# 태스크 실행 (자동으로 메모리 로드/저장)
task = Task(query="Fix authentication bug", intent="debug")
result = await orchestrator.execute_task(task)

# 메모리 통계
stats = await orchestrator.get_memory_statistics()
print(f"Total episodes: {stats['episodic']['total_episodes']}")
print(f"Bug patterns: {stats['semantic']['bug_patterns']}")
```

## 💾 Persistence

### In-Memory (개발/테스트)

```python
from src.memory.persistence import InMemoryStore

store = InMemoryStore()
await store.save("episode-123", episode)
loaded = await store.load("episode-123")
```

### File-Based (로컬 저장)

```python
from src.memory.persistence import FileStore

store = FileStore(base_path=".memory")
await store.save("episode-123", episode)
loaded = await store.load("episode-123")
```

### 향후 확장

- PostgreSQL Store
- Redis Store
- Vector DB 통합 (Qdrant)

## 📊 메트릭 & 분석

```python
# Episodic memory 통계
episodic_stats = episodic.get_statistics()
print(f"Total episodes: {episodic_stats['total_episodes']}")
print(f"Success rate: {episodic_stats['success_rate']:.1%}")
print(f"By type: {episodic_stats['by_type']}")

# Semantic memory 통계
semantic_stats = semantic.get_statistics()
print(f"Bug patterns: {semantic_stats['bug_patterns']}")
print(f"Code patterns: {semantic_stats['code_patterns']}")

# 전체 시스템 통계
memory_stats = memory.get_memory_statistics()
```

## 🧪 예제

전체 사용 예제는 `examples/memory_system_example.py`를 참고하세요:

```bash
PYTHONPATH=. python examples/memory_system_example.py
```

## 🎯 주요 기능

### ✅ 현재 구현됨

1. **Working Memory**
   - 세션 상태 추적
   - Hypothesis/Decision 관리
   - 파일/심볼 추적
   - 에피소드 consolidation

2. **Episodic Memory**
   - 에피소드 저장/검색
   - 유사도 검색 (속성 기반)
   - 에러 패턴 검색
   - 유용성 피드백

3. **Semantic Memory**
   - 버그 패턴 학습
   - 프로젝트 지식 추적
   - 사용자 선호도 학습
   - 패턴 매칭

4. **Memory Retrieval**
   - 태스크별 메모리 로드
   - 런타임 쿼리
   - Guidance 생성
   - 통합 학습

5. **Persistence**
   - In-memory storage
   - File-based storage
   - 확장 가능한 인터페이스

6. **보안 & 안정성** (2025-11-25 업데이트)
   - Path injection 방어 (base64 encoding + validation)
   - Circular reference 감지 (직렬화)
   - Race condition 방지 (asyncio locks)
   - Division by zero 방어
   - Transaction 패턴 (rollback 지원)
   - Memory leak 방지 (자동 trimming)
   - Type safety (Enum validation)
   - 복잡도 최적화 (함수 분리)

### 🚧 향후 개선

1. **벡터 검색**
   - Embedding 기반 유사도 검색
   - Qdrant/Pinecone 통합

2. **패턴 인식**
   - AST 기반 코드 패턴 매칭
   - 정규표현식 에러 메시지 매칭
   - Stack trace signature 매칭

3. **LLM 통합**
   - 자동 지식 추출
   - 패턴 요약 생성
   - 자연어 가이던스

4. **고급 저장소**
   - PostgreSQL adapter
   - Redis cache layer
   - 분산 저장소 지원

## 📚 설계 문서

상세한 설계는 [`_command_doc/E.에이전트/memory.md`](../../_command_doc/E.에이전트/memory.md)를 참고하세요.

## 🤝 기여

메모리 시스템은 아직 초기 단계입니다. 개선 사항이나 버그 리포트는 환영합니다!
