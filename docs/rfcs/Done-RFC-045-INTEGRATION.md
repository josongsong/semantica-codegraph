# RFC-045 Integration Guide

## ShadowFS EventBus → Incremental Orchestrator 연결

### Architecture

```
codegraph-agent (RFC-060)
  ↓ 파일 수정
  ↓ ShadowFS.commit()
  ↓
codegraph-runtime/shadowfs/event_bus.py
  ↓ EventBus.emit("commit")
  ↓
codegraph-engine/incremental/orchestrator.py
  ↓ IncrementalOrchestrator.on_event()
  ↓ IncrementalIRBuilder.build_incremental()
  ↓ IndexUpdater.update_ir()
```

---

## Setup (초기화 코드)

### 1. EventBus 초기화
```python
# codegraph-runtime/shadowfs/event_bus.py
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.event_bus import EventBus

event_bus = EventBus()
```

### 2. IncrementalOrchestrator 생성 및 등록
```python
# Application startup
from pathlib import Path
from codegraph_engine.code_foundation.infrastructure.incremental import (
    IncrementalOrchestrator,
)

orchestrator = IncrementalOrchestrator(
    repo_id="my-repo",
    workspace_root=Path("/path/to/repo"),
    index_updater=my_index_service,  # IIndexUpdater 구현체
)

# EventBus에 등록
event_bus.register(orchestrator)
```

### 3. ShadowFS 생성 (EventBus 주입)
```python
from codegraph_runtime.codegen_loop.infrastructure.shadowfs import UnifiedShadowFS

shadowfs = UnifiedShadowFS(
    workspace_root=Path("/path/to/repo"),
    event_bus=event_bus,  # ← EventBus 주입
)
```

---

## Event Flow

### Write Event
```python
# Agent가 파일 수정
await shadowfs.write("src/main.py", new_content)

# EventBus 자동 발행:
# → type="write", path="src/main.py", new_content=..., txn_id="..."

# IncrementalOrchestrator 수신:
# → _pending[txn_id]에 수집
```

### Commit Event
```python
# Agent가 커밋
await shadowfs.commit()

# EventBus 자동 발행:
# → type="commit", txn_id="..."

# IncrementalOrchestrator 수신:
# → _process_changes() 실행
# → IncrementalIRBuilder.build_incremental()
# → IndexUpdater.update_ir()
```

### Rollback Event
```python
# 오류 발생 시 롤백
await shadowfs.rollback()

# EventBus 자동 발행:
# → type="rollback", txn_id="..."

# IncrementalOrchestrator 수신:
# → _pending[txn_id] 폐기
```

---

## IIndexUpdater 구현 예시

```python
from codegraph_engine.code_foundation.infrastructure.incremental.orchestrator import (
    IIndexUpdater,
)

class MyIndexService(IIndexUpdater):
    async def update_ir(
        self,
        file_path: str,
        ir_document: object,
    ) -> bool:
        # IR 문서를 DB/인덱스에 저장
        await self.db.save(file_path, ir_document)
        await self.search_index.update(file_path, ir_document)
        return True
    
    async def remove_file(self, file_path: str) -> bool:
        # 파일을 인덱스에서 제거
        await self.db.delete(file_path)
        await self.search_index.delete(file_path)
        return True
```

---

## Testing

### Unit Test
```python
def test_incremental_orchestrator():
    orchestrator = IncrementalOrchestrator(
        repo_id="test",
        workspace_root=Path("/tmp/test"),
    )
    
    # Write 이벤트
    event = MockEvent(type="write", path="test.py", txn_id="tx1")
    await orchestrator.on_event(event)
    
    assert orchestrator.get_pending_count("tx1") == 1
    
    # Commit 이벤트
    event = MockEvent(type="commit", txn_id="tx1")
    await orchestrator.on_event(event)
    
    assert orchestrator.get_pending_count("tx1") == 0
```

---

## Deployment Checklist

- [ ] EventBus 초기화
- [ ] IncrementalOrchestrator 생성
- [ ] EventBus.register() 호출
- [ ] ShadowFS에 EventBus 주입
- [ ] IIndexUpdater 구현 및 주입
- [ ] 통합 테스트 실행

