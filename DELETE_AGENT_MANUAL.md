# agent_automation 수동 삭제 가이드

## 🗑️ 다음 명령어를 터미널에서 실행해주세요:

```bash
# 1. agent_automation context 삭제
rm -rf src/contexts/agent_automation

# 2. agent 테스트 삭제  
rm -rf tests/agent

# 3. 이 가이드 파일도 삭제
rm DELETE_AGENT_MANUAL.md
```

## 📝 Container 수정 필요

`src/container.py`에서 다음 부분을 주석 처리하거나 삭제:

### Line 27 근처
```python
# from src.contexts.agent_automation.infrastructure.di import AgentContainer, IndexingContainerFactory
```

### Line 37 근처 (TYPE_CHECKING 블록)
```python
# if TYPE_CHECKING:
#     from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator
```

### Line 478-483 근처
```python
# @cached_property
# def incremental_indexing_adapter(self):
#     return self.contexts.agent_automation.incremental_indexing_adapter
#
# @cached_property  
# def repo_registry(self):
#     return self.contexts.agent_automation.repo_registry
```

### Line 704-707 근처 (ContextsContainer 내부)
```python
# @cached_property
# def agent_automation(self):
#     from src.contexts.agent_automation.di import agent_automation_container
#     return agent_automation_container
```

---

완료 후 `rm DELETE_AGENT_MANUAL.md`로 이 파일도 삭제하세요.

