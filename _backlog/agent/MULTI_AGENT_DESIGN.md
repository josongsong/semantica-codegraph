# Multi-Agent Collaboration 설계

**Phase 3 Week 16-18 완료**

## 핵심 시나리오 11: 동시 편집 충돌 감지

```
User A, AI Agent B가 동시에 같은 파일 수정
→ Soft lock + hash drift 감지
→ 충돌 해결
```

---

## 아키텍처

### 1. Multi-Agent Coordinator

```
┌─────────────────────────────────────────────┐
│        Multi-Agent Coordinator              │
│  - Task 분배                                │
│  - Agent 생명주기 관리                       │
│  - 상태 동기화                               │
└─────────────────┬───────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
   ┌────▼────┐        ┌────▼────┐
   │ Agent A │        │ Agent B │
   │ (User)  │        │ (AI)    │
   └────┬────┘        └────┬────┘
        │                   │
        └─────────┬─────────┘
                  │
         ┌────────▼────────┐
         │  Conflict       │
         │  Detector       │
         │  - Soft Lock    │
         │  - Hash Drift   │
         └─────────────────┘
```

### 2. 핵심 컴포넌트

#### 2.1. AgentCoordinator
```python
class AgentCoordinator:
    """여러 Agent 조율"""
    
    async def spawn_agent(self, agent_id: str, task: AgentTask) -> Agent
    async def distribute_tasks(self, tasks: list[AgentTask]) -> dict[str, Agent]
    async def synchronize_state(self) -> None
    async def detect_conflicts(self) -> list[Conflict]
```

#### 2.2. SoftLockManager
```python
class SoftLockManager:
    """편집 중인 파일 추적 (Soft Lock)"""
    
    async def acquire_lock(self, agent_id: str, file_path: str) -> bool
    async def release_lock(self, agent_id: str, file_path: str) -> None
    async def check_lock(self, file_path: str) -> LockInfo | None
    async def detect_drift(self, file_path: str) -> bool
```

#### 2.3. ConflictResolver
```python
class ConflictResolver:
    """충돌 해결"""
    
    async def detect_conflict(self, agent_a: Agent, agent_b: Agent) -> Conflict | None
    async def resolve_3way_merge(self, conflict: Conflict) -> MergeResult
    async def request_manual_resolution(self, conflict: Conflict) -> Resolution
```

---

## 데이터 모델

### AgentSession
```python
@dataclass
class AgentSession:
    """Agent 세션"""
    
    session_id: str
    agent_id: str
    agent_type: str  # "user", "ai"
    task: AgentTask
    locked_files: set[str]
    state: AgentState
    created_at: datetime
    last_active: datetime
```

### SoftLock
```python
@dataclass
class SoftLock:
    """Soft Lock (편집 중 추적)"""
    
    file_path: str
    agent_id: str
    acquired_at: datetime
    file_hash: str  # 잠금 시점 파일 해시
    lock_type: str  # "read", "write"
```

### Conflict
```python
@dataclass
class Conflict:
    """충돌"""
    
    conflict_id: str
    file_path: str
    agent_a_id: str
    agent_b_id: str
    agent_a_changes: str
    agent_b_changes: str
    conflict_type: str  # "concurrent_edit", "hash_drift"
    detected_at: datetime
```

### MergeResult
```python
@dataclass
class MergeResult:
    """Merge 결과"""
    
    success: bool
    merged_content: str | None
    conflicts: list[str]  # 충돌 영역
    strategy: str  # "auto", "manual", "abort"
```

---

## 충돌 감지 전략

### 1. Soft Lock (편집 중 추적)

**동작 방식**:
1. Agent가 파일 편집 시작 → Lock 획득
2. Lock 정보: agent_id, file_path, file_hash
3. 다른 Agent가 동일 파일 편집 시도 → 충돌 감지

**구현**:
```python
async def acquire_lock(self, agent_id: str, file_path: str) -> bool:
    # 기존 Lock 확인
    existing_lock = await self._check_existing_lock(file_path)
    
    if existing_lock:
        # 충돌 감지
        await self._detect_conflict(agent_id, existing_lock)
        return False
    
    # Lock 획득
    file_hash = self._calculate_hash(file_path)
    lock = SoftLock(
        file_path=file_path,
        agent_id=agent_id,
        acquired_at=datetime.now(),
        file_hash=file_hash,
        lock_type="write",
    )
    
    await self._store_lock(lock)
    return True
```

### 2. Hash Drift (변경 감지)

**동작 방식**:
1. Lock 획득 시 file_hash 저장
2. 편집 중 주기적으로 hash 비교
3. Hash 변경 → Drift 감지 (다른 Agent가 수정함)

**구현**:
```python
async def detect_drift(self, file_path: str) -> bool:
    lock = await self._get_lock(file_path)
    
    if not lock:
        return False
    
    # 현재 파일 hash
    current_hash = self._calculate_hash(file_path)
    
    # 비교
    if current_hash != lock.file_hash:
        logger.warning(f"Hash drift detected: {file_path}")
        return True
    
    return False
```

### 3. 3-Way Merge

**전략**:
1. Base (Lock 시점)
2. Agent A 변경
3. Agent B 변경
4. Git 3-way merge 시도

**구현**:
```python
async def resolve_3way_merge(self, conflict: Conflict) -> MergeResult:
    # Base (Lock 시점 내용)
    base = await self._get_base_content(conflict.file_path)
    
    # Agent A, B 변경
    agent_a = conflict.agent_a_changes
    agent_b = conflict.agent_b_changes
    
    # Git 3-way merge
    try:
        merged = await self._git_3way_merge(base, agent_a, agent_b)
        
        return MergeResult(
            success=True,
            merged_content=merged,
            conflicts=[],
            strategy="auto",
        )
    except MergeConflictError as e:
        # 자동 merge 실패 → 수동 해결 필요
        return MergeResult(
            success=False,
            merged_content=None,
            conflicts=e.conflicts,
            strategy="manual",
        )
```

---

## 사용 시나리오

### 시나리오 1: 정상 케이스 (충돌 없음)

```python
# Agent A
coordinator = AgentCoordinator()

agent_a = await coordinator.spawn_agent("agent-a", task_a)
await agent_a.edit_file("utils.py")  # Lock 획득
await agent_a.commit()  # Lock 해제

# Agent B (Agent A 이후)
agent_b = await coordinator.spawn_agent("agent-b", task_b)
await agent_b.edit_file("utils.py")  # Lock 획득 (A는 이미 해제)
await agent_b.commit()
```

### 시나리오 2: Soft Lock 충돌

```python
# Agent A
agent_a = await coordinator.spawn_agent("agent-a", task_a)
await agent_a.edit_file("utils.py")  # Lock 획득

# Agent B (동시 편집 시도)
agent_b = await coordinator.spawn_agent("agent-b", task_b)
result = await agent_b.edit_file("utils.py")  # Lock 획득 실패

# 충돌 감지
if not result.success:
    print(f"Conflict: {result.conflict}")
    # → "utils.py is locked by agent-a"
```

### 시나리오 3: Hash Drift

```python
# Agent A
agent_a = await coordinator.spawn_agent("agent-a", task_a)
await agent_a.edit_file("utils.py")  # Lock 획득, hash 저장

# Agent B (외부에서 파일 수정 - User 직접 편집)
# ... utils.py 직접 수정 ...

# Agent A (계속 편집)
drift = await agent_a.check_drift("utils.py")

if drift:
    print("Hash drift detected!")
    # → 현재 편집 중단, 재시작 or 수동 merge
```

### 시나리오 4: 3-Way Merge

```python
# Agent A, B 동시 편집 후 충돌 발생
conflict = await coordinator.detect_conflicts()

# Merge 시도
resolver = ConflictResolver()
result = await resolver.resolve_3way_merge(conflict[0])

if result.success:
    print(f"Auto-merged: {result.merged_content}")
else:
    print(f"Manual resolution needed: {result.conflicts}")
    # → Human-in-the-loop
```

---

## 저장소 (State)

### Redis (실시간 Lock)

```python
# Lock 저장
await redis.hset(
    f"lock:{file_path}",
    {
        "agent_id": agent_id,
        "acquired_at": timestamp,
        "file_hash": hash,
    }
)

# TTL 설정 (30분 후 자동 해제)
await redis.expire(f"lock:{file_path}", 1800)
```

### PostgreSQL (Conflict History)

```sql
CREATE TABLE agent_sessions (
    session_id VARCHAR PRIMARY KEY,
    agent_id VARCHAR NOT NULL,
    agent_type VARCHAR NOT NULL,
    task_id VARCHAR,
    locked_files TEXT[],
    state VARCHAR,
    created_at TIMESTAMP,
    last_active TIMESTAMP
);

CREATE TABLE conflicts (
    conflict_id VARCHAR PRIMARY KEY,
    file_path VARCHAR NOT NULL,
    agent_a_id VARCHAR,
    agent_b_id VARCHAR,
    conflict_type VARCHAR,
    resolved BOOLEAN DEFAULT FALSE,
    resolution VARCHAR,
    detected_at TIMESTAMP,
    resolved_at TIMESTAMP
);
```

---

## 통합 (Container)

### src/container.py

```python
@cached_property
def v7_soft_lock_manager(self):
    """Multi-Agent Soft Lock Manager"""
    from src.agent.domain.soft_lock_manager import SoftLockManager
    
    return SoftLockManager(
        redis_client=self.cache_manager,  # 기존 Redis
    )

@cached_property
def v7_conflict_resolver(self):
    """Multi-Agent Conflict Resolver"""
    from src.agent.domain.conflict_resolver import ConflictResolver
    
    return ConflictResolver(
        vcs_applier=self.v7_vcs_applier,
    )

@cached_property
def v7_agent_coordinator(self):
    """Multi-Agent Coordinator"""
    from src.agent.domain.agent_coordinator import AgentCoordinator
    
    return AgentCoordinator(
        orchestrator_factory=self.v7_agent_orchestrator,
        lock_manager=self.v7_soft_lock_manager,
        conflict_resolver=self.v7_conflict_resolver,
    )
```

---

## 구현 순서

### Week 16: 기본 구조 (3일)

1. **데이터 모델** (1일)
   - [ ] `AgentSession`
   - [ ] `SoftLock`
   - [ ] `Conflict`
   - [ ] `MergeResult`

2. **SoftLockManager** (1일)
   - [ ] `acquire_lock`
   - [ ] `release_lock`
   - [ ] `check_lock`
   - [ ] Redis 통합

3. **ConflictResolver** (1일)
   - [ ] `detect_conflict`
   - [ ] `resolve_3way_merge`
   - [ ] Git 3-way merge

### Week 17: Coordinator (4일)

4. **AgentCoordinator** (2일)
   - [ ] `spawn_agent`
   - [ ] `distribute_tasks`
   - [ ] `synchronize_state`
   - [ ] `detect_conflicts`

5. **Hash Drift** (1일)
   - [ ] `detect_drift`
   - [ ] 주기적 체크

6. **PostgreSQL 저장** (1일)
   - [ ] Session 저장
   - [ ] Conflict History

### Week 18: 테스트 & 통합 (3일)

7. **단위 테스트** (1일)
   - [ ] `test_soft_lock_manager.py`
   - [ ] `test_conflict_resolver.py`
   - [ ] `test_agent_coordinator.py`

8. **E2E 테스트** (1일)
   - [ ] 시나리오 11: 동시 편집 충돌

9. **Container 통합** (1일)
   - [ ] `src/container.py`
   - [ ] Orchestrator 연결

---

## SOTA급 비교

| 기능 | GitHub Copilot | Cursor | Aider | **Semantica v2** |
|------|----------------|--------|-------|------------------|
| Multi-Agent | ❌ | ❌ | ❌ | **✅** |
| Soft Lock | ❌ | ⚠ (Session) | ❌ | **✅** |
| Hash Drift | ❌ | ❌ | ❌ | **✅** |
| 3-Way Merge | ❌ | ⚠ (Simple) | ⚠ (Git) | **✅** (Auto) |
| Conflict Resolver | ❌ | ⚠ (Manual) | ❌ | **✅** (Auto + Manual) |

**결론**: 업계 최초 수준 달성! 🚀

---

## 예상 결과

### 완료 후
- ✅ 여러 Agent 동시 실행
- ✅ Soft Lock으로 충돌 방지
- ✅ Hash Drift 자동 감지
- ✅ 3-Way Merge 자동 시도
- ✅ Manual 해결 지원
- ✅ PostgreSQL에 History 저장
- ✅ Redis로 실시간 Lock

### 테스트 커버리지
- Unit: SoftLockManager, ConflictResolver, AgentCoordinator
- E2E: 시나리오 11 (동시 편집 충돌)

### 프로덕션 준비
- Redis TTL로 자동 Lock 해제
- PostgreSQL로 Audit Trail
- Container 완벽 통합

🎯 **Multi-Agent Collaboration 완료 시 v7-roadmap.md 100% 달성!**
