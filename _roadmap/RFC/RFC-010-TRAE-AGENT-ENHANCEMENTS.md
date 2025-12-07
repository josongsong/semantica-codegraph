# RFC-010: TRAE Agent 기술 도입

**Status**: Draft  
**Created**: 2025-01-07  
**Priority**: P0-P2  
**Reference**: P5-TRAE-REFERENCE.md, Refact.ai Analysis

---

## 1. 개요

TRAE Agent (SWE-bench 75.2%) 및 Refact.ai 오픈소스 분석 결과를 바탕으로,
Semantica v8.1에 도입할 핵심 기술 5가지를 정의합니다.

---

## 2. 현재 상태 분석

### 2.1 에이전트 루프 (`WorkflowStateMachine`)

```python
# src/agent/workflow/state_machine.py:59-106
class WorkflowStateMachine:
    def __init__(self, max_iterations: int = 3, ...):
        self.max_iterations = max_iterations  # 반복 한계만 존재
    
    def run(self, initial_state: WorkflowState) -> WorkflowState:
        while state.iteration < self.max_iterations:
            for step in self.steps:
                # 단계별 실행
                step_result = self._execute_step(state, step)
            state.iteration += 1
            if self._should_exit_early(state):
                break
```

**Gap**: 토큰 한계 종료 없음, Wrap-up 프롬프트 없음

### 2.2 전략 생성 (`StrategyGeneratorLLM`)

```python
# src/agent/adapters/llm/strategy_generator.py:88-95
response = self.client.chat.completions.create(
    model=self.model,
    temperature=0.7,  # 고정값
    max_tokens=1000,
)
```

**Gap**: Temperature 다양성 없음 (고정 0.7)

### 2.3 ToT + Sandbox 분리

```python
# ToTScoringEngine: src/agent/domain/reasoning/tot_scorer.py
# E2BSandboxAdapter: src/agent/adapters/sandbox/e2b_adapter.py
```

**Gap**: ToT → Test 자동 검증 루프 없음

### 2.4 ShadowFS

```python
# src/execution/shadowfs/core.py:22-229
class ShadowFS:
    self.overlay: dict[str, str] = {}  # in-memory only
    self.original: dict[str, str] = {}
```

**Gap**: Git 기반 체크포인트 없음, 세션 간 히스토리 없음

---

## 3. 도입 기술 (우선순위별)

### P0-1: Subchat 3중 종료 + Wrap-up

**목적**: 에이전트 루프 안정성 강화

**현재 문제**:
- `max_iterations`만 체크
- 토큰 폭주 시 비용 급증
- 마무리 요약 없음

**도입 방안**:

```python
# src/agent/workflow/state_machine.py 수정

class WorkflowStateMachine:
    def __init__(
        self,
        max_iterations: int = 3,
        max_tokens: int = 8000,      # NEW: 토큰 한계
        wrap_up_prompt: str = None,  # NEW: Wrap-up 프롬프트
    ):
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.wrap_up_prompt = wrap_up_prompt or "지금까지 작업을 요약해줘."
        self._total_tokens = 0

    def run(self, initial_state: WorkflowState) -> WorkflowState:
        while True:
            for step in self.steps:
                step_result = self._execute_step(state, step)
                
                # NEW: 토큰 누적
                self._total_tokens += step_result.tokens_used
                
                # 종료 조건 1: 실패
                if not step_result.success:
                    break
            
            state.iteration += 1
            
            # 종료 조건 2: 반복 한계
            if state.iteration >= self.max_iterations:
                state.exit_reason = WorkflowExitReason.MAX_ITERATIONS
                break
            
            # 종료 조건 3: 토큰 한계 (NEW)
            if self._total_tokens >= self.max_tokens:
                state.exit_reason = WorkflowExitReason.TOKEN_LIMIT
                break
            
            # 종료 조건 4: 작업 완료 (tool_calls 없음)
            if self._should_exit_early(state):
                state.exit_reason = WorkflowExitReason.SUCCESS
                break
        
        # NEW: Wrap-up 요청
        if self.wrap_up_prompt:
            wrap_up_result = self._request_wrap_up(state)
            state.summary = wrap_up_result
        
        return state
    
    def _request_wrap_up(self, state: WorkflowState) -> str:
        """Wrap-up 요약 요청 (Refact 스타일)"""
        # LLM에 마무리 요청
        return "작업 요약..."
```

**변경 파일**:
- `src/agent/workflow/state_machine.py`
- `src/agent/workflow/models.py` (WorkflowExitReason에 TOKEN_LIMIT 추가)

**예상 효과**:
- 무한 루프 방지
- 토큰 비용 제어
- 일관된 출력 형식

---

### P0-2: 테스트 검증 루프 (ToT + Test)

**목적**: 생성 전략의 자동 검증

**현재 문제**:
- ToT로 전략 생성 → 점수 계산 → 끝
- 실제 테스트 실행과 연동 없음
- 실패 시 재시도 없음

**도입 방안**:

```python
# src/agent/application/use_cases/execute_tot_with_test.py (NEW)

class ExecuteToTWithTestUseCase:
    """
    ToT + Test 검증 루프
    
    Flow:
    1. ToT로 전략 N개 생성
    2. 점수순 정렬
    3. Top 전략부터 ShadowFS에 적용
    4. Sandbox에서 테스트 실행
    5. 성공 → commit, 실패 → rollback 후 다음 전략
    """
    
    def __init__(
        self,
        strategy_generator: StrategyGeneratorLLM,
        tot_scorer: ToTScoringEngine,
        sandbox: E2BSandboxAdapter,
        shadow_fs: ShadowFS,
        max_attempts: int = 3,
    ):
        self.strategy_generator = strategy_generator
        self.tot_scorer = tot_scorer
        self.sandbox = sandbox
        self.shadow_fs = shadow_fs
        self.max_attempts = max_attempts

    async def execute(
        self,
        problem: str,
        context: dict,
        test_command: str = "pytest -v",
    ) -> ToTWithTestResult:
        """
        ToT + Test 실행
        
        Args:
            problem: 문제 설명
            context: 코드 컨텍스트
            test_command: 테스트 명령어
        
        Returns:
            ToTWithTestResult
        """
        # 1. 전략 생성
        strategies = await self._generate_strategies(problem, context)
        
        # 2. 점수 계산 및 정렬
        scored = self._score_and_rank(strategies)
        
        # 3. 검증 루프
        for i, (strategy, score) in enumerate(scored[:self.max_attempts]):
            logger.info(f"Trying strategy {i+1}/{self.max_attempts}: {strategy.strategy_id}")
            
            # 3.1 ShadowFS에 적용
            for file_path, content in strategy.file_changes.items():
                self.shadow_fs.write_file(file_path, content)
            
            # 3.2 테스트 실행
            sandbox_id = await self.sandbox.create_sandbox()
            test_result = await self.sandbox.execute_code(
                sandbox_id,
                test_command,
                language="bash",
            )
            
            # 3.3 결과 확인
            if test_result.exit_code == 0:
                # 성공 → commit
                self.shadow_fs.commit()
                await self.sandbox.destroy_sandbox(sandbox_id)
                
                return ToTWithTestResult(
                    success=True,
                    selected_strategy=strategy,
                    selected_score=score,
                    attempts=i + 1,
                    test_output=test_result.stdout,
                )
            
            # 실패 → rollback 후 다음 시도
            logger.warning(f"Test failed: {test_result.stderr[:200]}")
            self.shadow_fs.rollback()
            await self.sandbox.destroy_sandbox(sandbox_id)
        
        # 모든 시도 실패
        return ToTWithTestResult(
            success=False,
            selected_strategy=None,
            selected_score=0.0,
            attempts=self.max_attempts,
            error="All strategies failed tests",
        )
```

**변경 파일**:
- `src/agent/application/use_cases/execute_tot_with_test.py` (NEW)
- `src/agent/domain/reasoning/tot_models.py` (ToTWithTestResult 추가)

**예상 효과**:
- 검증된 코드만 적용
- 자동 롤백으로 안전성 보장
- 성공률 +40% (AutoCodeRover 기준)

---

### P1-1: Temperature 다양성

**목적**: 전략 다양성 확보

**현재 문제**:
- `temperature=0.7` 고정
- 유사한 전략만 생성
- TRAE의 Multi-LLM × Temperature 미활용

**도입 방안**:

```python
# src/agent/adapters/llm/strategy_generator.py 수정

class StrategyGeneratorLLM:
    # 다양성 설정 (NEW)
    TEMPERATURES = [0.2, 0.5, 0.7, 0.9, 1.0]
    
    async def generate_diverse_strategies(
        self,
        problem: str,
        context: dict,
        strategy_type: StrategyType,
        count: int = 5,
    ) -> list[CodeStrategy]:
        """
        다양한 온도로 전략 생성 (TRAE 스타일)
        
        Args:
            problem: 문제 설명
            context: 컨텍스트
            strategy_type: 전략 타입
            count: 생성할 전략 수
        
        Returns:
            CodeStrategy 리스트
        """
        strategies = []
        temperatures = self.TEMPERATURES[:count]
        
        # 병렬 생성
        tasks = [
            self._generate_one(problem, context, strategy_type, temp, i)
            for i, temp in enumerate(temperatures)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, CodeStrategy):
                strategies.append(result)
            else:
                logger.warning(f"Strategy generation failed: {result}")
        
        return strategies
    
    async def _generate_one(
        self,
        problem: str,
        context: dict,
        strategy_type: StrategyType,
        temperature: float,
        index: int,
    ) -> CodeStrategy:
        """단일 전략 생성 (지정 온도)"""
        prompt = self._build_prompt(problem, context, strategy_type)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[...],
            temperature=temperature,  # 동적 온도
            max_tokens=1000,
        )
        
        strategy = self._parse_response(...)
        strategy.temperature = temperature  # 온도 기록
        strategy.strategy_id = f"llm_t{int(temperature*10)}_{index}"
        
        return strategy
```

**변경 파일**:
- `src/agent/adapters/llm/strategy_generator.py`
- `src/agent/domain/reasoning/tot_models.py` (CodeStrategy에 temperature 필드 추가)

**예상 효과**:
- 전략 다양성 증가
- 최적 해 발견 확률 향상

---

### P1-2: Trajectory Compression (대화 압축)

**목적**: 긴 세션 지원

**현재 문제**:
- `ContextualCompressor`는 검색 결과용
- 대화 히스토리 압축 없음
- 긴 세션에서 컨텍스트 손실

**도입 방안**:

```python
# src/agent/infrastructure/trajectory_compressor.py (NEW)

COMPRESSION_TEMPLATE = """
다음 대화를 구조화된 요약으로 압축해주세요:

## 요약 형식
1. **원래 요청**: 사용자가 원래 요청한 것
2. **핵심 개념**: 논의된 기술/개념들
3. **수정된 파일**:
   - file1.py: [변경 내용]
   - file2.py: [변경 내용]
4. **현재 상태**: 진행 상황
5. **다음 단계**: 해야 할 작업

## 대화 내용
{conversation}
"""

class TrajectoryCompressor:
    """
    대화 히스토리 압축 (Refact 스타일)
    
    긴 대화를 구조화된 요약으로 압축하여
    토큰 사용량을 줄이고 컨텍스트를 유지
    """
    
    def __init__(
        self,
        llm_adapter: ILLMAdapter,
        threshold_turns: int = 20,
        threshold_tokens: int = 10000,
    ):
        self.llm_adapter = llm_adapter
        self.threshold_turns = threshold_turns
        self.threshold_tokens = threshold_tokens
    
    async def maybe_compress(
        self,
        messages: list[dict],
    ) -> list[dict]:
        """
        필요시 대화 압축
        
        Args:
            messages: 대화 히스토리
        
        Returns:
            압축된 메시지 (또는 원본)
        """
        # 압축 필요 여부 확인
        if len(messages) < self.threshold_turns:
            return messages
        
        total_tokens = sum(
            self._estimate_tokens(m.get("content", ""))
            for m in messages
        )
        
        if total_tokens < self.threshold_tokens:
            return messages
        
        # 압축 실행
        logger.info(f"Compressing {len(messages)} messages ({total_tokens} tokens)")
        
        conversation_text = self._format_conversation(messages)
        prompt = COMPRESSION_TEMPLATE.format(conversation=conversation_text)
        
        summary = await self.llm_adapter.generate(
            prompt=prompt,
            temperature=0,  # 일관성
            max_tokens=2000,
        )
        
        # 압축된 메시지로 교체
        compressed_messages = [
            {
                "role": "system",
                "content": f"[이전 대화 요약]\n{summary}\n\n---\n이 요약을 바탕으로 계속 진행합니다. 필요한 파일은 다시 요청하세요."
            }
        ]
        
        logger.info(f"Compressed to ~{self._estimate_tokens(summary)} tokens")
        
        return compressed_messages
    
    def _format_conversation(self, messages: list[dict]) -> str:
        """대화를 텍스트로 포맷"""
        lines = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")[:500]  # 잘라서 토큰 절약
            lines.append(f"[{role}]: {content}")
        return "\n\n".join(lines)
    
    def _estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (간단히 4자당 1토큰)"""
        return len(text) // 4
```

**변경 파일**:
- `src/agent/infrastructure/trajectory_compressor.py` (NEW)
- `src/agent/workflow/state_machine.py` (압축 호출 추가)

**예상 효과**:
- 긴 세션 지원
- 토큰 비용 70% 절감 (긴 대화 시)
- 컨텍스트 일관성 유지

---

### P2: Shadow Git Checkpoint

**목적**: 완전한 프로젝트 상태 롤백

**현재 문제**:
- `ShadowFS`는 in-memory overlay
- 세션 간 히스토리 없음
- 원본 Git과 분리 안됨

**도입 방안**:

```python
# src/execution/shadowfs/git_checkpoint.py (NEW)

class ShadowGitCheckpoint:
    """
    Shadow Git 체크포인트 (Refact 스타일)
    
    원본 .git을 건드리지 않고 별도 Shadow 저장소에서
    체크포인트 생성/복원
    
    구조:
    ~/.semantica/shadow_git/{project_hash}/
    ├─ .git/
    └─ refs/heads/agent-{chat_id}
    """
    
    def __init__(
        self,
        project_path: Path,
        cache_dir: Path | None = None,
    ):
        self.project_path = project_path
        self.cache_dir = cache_dir or Path.home() / ".semantica" / "shadow_git"
        
        # 프로젝트 해시 (경로 기반)
        self.project_hash = hashlib.md5(
            str(project_path).encode()
        ).hexdigest()[:8]
        
        self.shadow_path = self.cache_dir / self.project_hash
    
    def init_shadow_repo(self) -> git.Repo:
        """Shadow 저장소 초기화"""
        self.shadow_path.mkdir(parents=True, exist_ok=True)
        
        git_path = self.shadow_path / ".git"
        
        if not git_path.exists():
            # 새 저장소 생성
            repo = git.Repo.init(self.shadow_path)
            
            # worktree를 원본 프로젝트로 설정
            repo.config_writer().set_value(
                "core", "worktree", str(self.project_path)
            ).release()
        else:
            repo = git.Repo(self.shadow_path)
        
        return repo
    
    def create_checkpoint(self, chat_id: str) -> str:
        """
        현재 상태 체크포인트 생성
        
        Args:
            chat_id: 채팅 ID
        
        Returns:
            commit_hash
        """
        repo = self.init_shadow_repo()
        branch_name = f"agent-{chat_id}"
        
        # 브랜치 생성/전환
        if branch_name not in [h.name for h in repo.heads]:
            repo.create_head(branch_name)
        
        repo.heads[branch_name].checkout()
        
        # 모든 변경사항 스테이징
        repo.git.add(A=True)
        
        # 커밋
        commit = repo.index.commit(
            f"Checkpoint for chat {chat_id} at {datetime.now().isoformat()}"
        )
        
        logger.info(f"Created checkpoint: {commit.hexsha[:8]}")
        
        return commit.hexsha
    
    def list_checkpoints(self, chat_id: str) -> list[dict]:
        """체크포인트 목록 조회"""
        repo = self.init_shadow_repo()
        branch_name = f"agent-{chat_id}"
        
        if branch_name not in [h.name for h in repo.heads]:
            return []
        
        branch = repo.heads[branch_name]
        commits = list(repo.iter_commits(branch, max_count=10))
        
        return [
            {
                "hash": c.hexsha,
                "message": c.message,
                "timestamp": c.committed_datetime.isoformat(),
            }
            for c in commits
        ]
    
    def restore_checkpoint(self, commit_hash: str):
        """
        체크포인트로 복원
        
        Args:
            commit_hash: 복원할 커밋 해시
        """
        repo = self.init_shadow_repo()
        
        # 강제 체크아웃
        repo.git.checkout(commit_hash, force=True)
        
        logger.info(f"Restored to checkpoint: {commit_hash[:8]}")
    
    def cleanup(self, chat_id: str):
        """채팅 관련 브랜치 정리"""
        repo = self.init_shadow_repo()
        branch_name = f"agent-{chat_id}"
        
        if branch_name in [h.name for h in repo.heads]:
            repo.delete_head(branch_name, force=True)
            logger.info(f"Deleted branch: {branch_name}")
```

**변경 파일**:
- `src/execution/shadowfs/git_checkpoint.py` (NEW)
- `src/execution/shadowfs/__init__.py` (export 추가)

**예상 효과**:
- 완전한 프로젝트 상태 롤백
- 세션 간 히스토리 유지
- 원본 Git 히스토리 보존

---

## 4. 구현 로드맵

```
Phase 1 (Week 1-2): P0 구현
├─ Subchat 3중 종료 + Wrap-up
└─ ToT + Test 검증 루프

Phase 2 (Week 3): P1 구현
├─ Temperature 다양성
└─ Trajectory Compression

Phase 3 (Week 4): P2 구현
└─ Shadow Git Checkpoint

Phase 4 (Week 5): 통합 테스트
├─ E2E 테스트
└─ 성능 벤치마크
```

---

## 5. 리스크 및 완화

| 리스크 | 완화 방안 |
|--------|----------|
| 토큰 한계 오탐 | 단계별 토큰 추적, 여유 버퍼 (10%) |
| 테스트 실행 느림 | 병렬 실행, 빠른 테스트만 우선 |
| 압축 품질 저하 | 압축 전후 핵심 정보 검증 |
| Shadow Git 충돌 | 원본 Git과 완전 분리, 격리된 경로 |

---

## 6. 성공 지표

| 지표 | 현재 | 목표 |
|------|------|------|
| 에이전트 루프 안정성 | 80% | 95% |
| 전략 검증률 | 0% (수동) | 100% (자동) |
| 긴 세션 지원 | 20턴 | 100턴+ |
| 롤백 안전성 | 파일 레벨 | 프로젝트 레벨 |

---

## 7. 참고 자료

- P5-TRAE-REFERENCE.md
- Refact.ai (https://github.com/smallcloudai/refact)
- AutoCodeRover (NUS, 2024)
- OpenHands (All-Hands-AI)

---

**Author**: Semantica Team  
**Reviewers**: TBD
