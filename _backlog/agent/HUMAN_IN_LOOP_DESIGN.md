# Human-in-the-Loop 설계 (SOTA급)

## 비판적 분석

### 기존 구현 확인
- ✅ `review_code` 메서드 존재 (간단한 리뷰)
- ❌ 사용자 승인/거부 기능 없음
- ❌ Hunk 단위 처리 없음
- ❌ Partial commit 없음
- ❌ Interactive UI 없음

**결론**: 전체 새로 구현 필요

---

## SOTA급 벤치마크

### 1. GitHub Copilot
```
특징:
- Inline suggestion (회색 텍스트)
- Tab to accept
- Esc to reject
- 부분 수락 (단어 단위)

장점:
- 비침투적 (non-intrusive)
- 빠른 수락/거부
- Context-aware

단점:
- 전체/부분만 가능 (hunk 단위 불가)
```

### 2. Cursor
```
특징:
- AI 편집 후 Diff view
- Apply all / Discard all
- Accept / Reject per change
- Multi-cursor 편집

장점:
- 시각적 diff
- 세밀한 제어
- 되돌리기 쉬움

단점:
- UI 의존적
```

### 3. GitLens (VSCode)
```
특징:
- Hunk 단위 staging
- Line 단위 staging
- Interactive rebase
- Blame annotations

장점:
- Git native 통합
- 강력한 diff 도구
- 히스토리 추적

단점:
- Git에만 특화
```

### 4. Aider
```
특징:
- CLI 기반 대화형
- /add, /drop 명령어
- Diff 출력 후 승인
- Git auto-commit

장점:
- CLI 친화적
- 간단한 워크플로우
- Git 통합

단점:
- UI 없음
- 제한적 편집 제어
```

---

## 우리 설계 (SOTA급 통합)

### 핵심 원칙
1. **Multi-level approval**: File → Hunk → Line
2. **Non-intrusive**: 기존 워크플로우 방해 안함
3. **Git-native**: Git diff/staging 활용
4. **Reversible**: 모든 작업 되돌리기 가능
5. **Async-friendly**: 비동기 작업 지원

### 아키텍처

```
┌─────────────────────────────────────────────┐
│         AgentOrchestrator                    │
│  - 코드 생성                                 │
│  - DiffManager 호출                          │
└─────────────────────────────────────────────┘
                    ▼
┌─────────────────────────────────────────────┐
│            DiffManager                       │
│  - Git diff 생성                             │
│  - Hunk 파싱                                 │
│  - File/Hunk/Line 단위 분리                  │
└─────────────────────────────────────────────┘
                    ▼
┌─────────────────────────────────────────────┐
│         ApprovalManager                      │
│  - 사용자 인터랙션                           │
│  - File/Hunk/Line 단위 승인/거부             │
│  - 승인 이력 추적                            │
└─────────────────────────────────────────────┘
                    ▼
┌─────────────────────────────────────────────┐
│       PartialCommitter                       │
│  - 승인된 것만 staging                       │
│  - Partial apply (git apply --cached)       │
│  - Commit 생성                               │
└─────────────────────────────────────────────┘
```

---

## 상세 설계

### 1. DiffManager (Git diff 관리)

```python
class DiffHunk:
    """Git diff hunk (@ ... @@ 단위)"""
    header: str  # @@ -1,5 +1,7 @@
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # +/- 포함
    context_before: list[str]  # 앞 context
    context_after: list[str]  # 뒤 context

class FileDiff:
    """파일 단위 diff"""
    file_path: str
    old_path: str | None  # rename 시
    change_type: str  # "modified", "added", "deleted", "renamed"
    hunks: list[DiffHunk]
    
    def get_hunk(self, index: int) -> DiffHunk:
        """특정 hunk 가져오기"""
    
    def apply_hunks(self, indices: list[int]) -> str:
        """선택한 hunk만 적용한 patch"""

class DiffManager:
    """Git diff 생성 및 관리 (SOTA급)"""
    
    async def generate_diff(
        self, 
        changes: list[CodeChange]
    ) -> list[FileDiff]:
        """
        코드 변경을 Git diff로 변환.
        
        - Unified diff 형식
        - Hunk 단위 파싱
        - Context lines 포함 (기본 3줄)
        """
    
    async def parse_diff(self, diff_text: str) -> list[FileDiff]:
        """Git diff 텍스트 파싱"""
    
    def format_hunk(self, hunk: DiffHunk, colorize: bool = True) -> str:
        """Hunk을 읽기 좋게 포맷팅 (color 지원)"""
```

**SOTA 포인트**:
- ✅ Unified diff 표준 (Git 호환)
- ✅ Context lines 지원 (주변 코드 표시)
- ✅ Color 지원 (CLI 가독성)
- ✅ Hunk 단위 파싱 (세밀한 제어)

### 2. ApprovalManager (승인 관리)

```python
class ApprovalDecision:
    """승인 결정"""
    file_path: str
    hunk_index: int | None  # None = 전체 파일
    action: str  # "approve", "reject", "skip", "edit"
    reason: str | None  # 거부 이유
    timestamp: datetime

class ApprovalSession:
    """승인 세션 (상태 추적)"""
    session_id: str
    file_diffs: list[FileDiff]
    decisions: list[ApprovalDecision]
    current_file_index: int
    current_hunk_index: int
    
    def get_approved_changes(self) -> list[FileDiff]:
        """승인된 변경사항만 반환"""
    
    def get_rejected_changes(self) -> list[FileDiff]:
        """거부된 변경사항만 반환"""
    
    def get_statistics(self) -> dict:
        """승인 통계 (승인/거부/스킵 수)"""

class ApprovalManager:
    """사용자 승인 관리 (SOTA급)"""
    
    async def request_approval(
        self,
        file_diffs: list[FileDiff],
        mode: str = "hunk",  # "file", "hunk", "line"
        ui_adapter: UIAdapter | None = None,
    ) -> ApprovalSession:
        """
        사용자에게 승인 요청.
        
        Mode:
        - file: 파일 단위 승인/거부
        - hunk: Hunk 단위 승인/거부 (기본, 가장 실용적)
        - line: Line 단위 승인/거부 (가장 세밀)
        
        UI Adapter:
        - CLIAdapter: 터미널 인터랙티브
        - WebAdapter: 웹 UI (미래)
        - IDEAdapter: IDE 플러그인 (미래)
        """
    
    async def auto_approve(
        self,
        file_diffs: list[FileDiff],
        criteria: ApprovalCriteria,
    ) -> ApprovalSession:
        """
        자동 승인 (규칙 기반).
        
        예: 
        - 테스트 파일만 자동 승인
        - 100줄 이하만 자동 승인
        - 특정 패턴만 자동 승인
        """
```

**SOTA 포인트**:
- ✅ Multi-level (File/Hunk/Line)
- ✅ 승인 이력 추적
- ✅ 통계 제공
- ✅ 자동 승인 규칙 (효율성)
- ✅ UI Adapter 패턴 (확장성)

### 3. PartialCommitter (부분 커밋)

```python
class PartialCommitter:
    """부분 커밋 (SOTA급)"""
    
    async def apply_partial(
        self,
        session: ApprovalSession,
        repo_path: str,
    ) -> PartialCommitResult:
        """
        승인된 변경사항만 적용.
        
        Git 명령어:
        1. git apply --cached <patch>  # Staged만
        2. git apply <patch>            # Working tree
        
        Rollback 지원:
        - Shadow branch 생성
        - 실패 시 자동 복원
        """
    
    async def create_commit(
        self,
        session: ApprovalSession,
        commit_message: str,
        author: str | None = None,
    ) -> str:
        """
        승인된 것만 커밋.
        
        Returns:
            commit_sha
        """
    
    async def create_pr(
        self,
        commit_sha: str,
        title: str,
        body: str,
    ) -> str:
        """
        PR 생성 (GitHub API).
        
        Returns:
            PR URL
        """
```

**SOTA 포인트**:
- ✅ Git native (git apply --cached)
- ✅ Atomic operations (전체 성공 or 전체 실패)
- ✅ Rollback 지원 (Shadow branch)
- ✅ PR 통합 (GitHub API)

### 4. UIAdapter (인터페이스 추상화)

```python
class UIAdapter(Protocol):
    """UI Adapter 인터페이스"""
    
    async def show_diff(self, file_diff: FileDiff) -> None:
        """Diff 표시"""
    
    async def ask_approval(
        self,
        prompt: str,
        options: list[str],
    ) -> str:
        """사용자 선택 요청"""
    
    async def show_message(self, message: str, level: str) -> None:
        """메시지 표시"""

class CLIAdapter(UIAdapter):
    """CLI 인터랙티브 (SOTA급)"""
    
    - Rich library 사용 (color, formatting)
    - Syntax highlighting (Pygments)
    - Progress bar
    - Keyboard shortcuts (y/n/s/e/q)
    
    Commands:
    - y: Yes (approve)
    - n: No (reject)
    - s: Skip (나중에)
    - e: Edit (inline 편집)
    - q: Quit (종료)
    - a: Approve all remaining
    - r: Reject all remaining

class WebAdapter(UIAdapter):
    """Web UI (미래)"""
    
    - FastAPI + React
    - Visual diff viewer
    - Inline comments
    - Real-time collaboration
```

**SOTA 포인트**:
- ✅ Adapter 패턴 (확장성)
- ✅ Rich CLI (사용자 경험)
- ✅ Syntax highlighting (가독성)
- ✅ 키보드 shortcut (효율성)
- ✅ 미래 확장 (Web, IDE)

---

## 워크플로우 예시

### 시나리오: "container.py에 새 메서드 추가"

```bash
# 1. AI가 코드 생성
Agent: "v7_incremental_workflow 메서드를 추가했습니다."

# 2. Diff 생성
╭─ container.py ──────────────────────────────────────╮
│ @@ -507,6 +507,15 @@ class Container:                    │
│      def v7_experience_store(self):                  │
│          ...                                         │
│                                                      │
│ +    @cached_property                               │ <- 추가
│ +    def v7_incremental_workflow(self):             │
│ +        """v7 Incremental Workflow Manager"""       │
│ +        from src.agent.domain import ...           │
│ +        return IncrementalWorkflow(...)             │
│ +                                                     │
│      @cached_property                                │
│      def v7_agent_orchestrator(self):                │
╰─────────────────────────────────────────────────────╯

# 3. Hunk 단위 승인
> Approve this change? [y/n/s/e/q] y

# 4. 다음 hunk (다른 파일)
╭─ src/agent/orchestrator/v7_orchestrator.py ─────────╮
│ @@ -64,6 +64,7 @@ class AgentOrchestrator:            │
│          llm_provider: ILLMProvider,                 │
│          ...                                         │
│ +        incremental_workflow=None,                 │ <- 추가
│      ):                                              │
╰─────────────────────────────────────────────────────╯

> Approve this change? [y/n/s/e/q] y

# 5. 최종 확인
╭─ Summary ──────────────────────────────────────────╮
│ Approved: 2/2 hunks                                 │
│ Rejected: 0/2 hunks                                 │
│ Files changed: 2                                    │
│ +15 lines, -0 lines                                 │
╰────────────────────────────────────────────────────╯

> Commit approved changes? [y/n] y

# 6. 커밋 생성
✓ Changes applied to working tree
✓ Changes staged
✓ Commit created: abc123def
✓ Branch: agent/add-incremental-workflow

> Create PR? [y/n] n
```

---

## 비판적 검증 포인트

### 1. 안전성
- ✅ Shadow branch (원본 보호)
- ✅ Atomic operations (부분 실패 방지)
- ✅ Rollback 지원 (언제든 되돌리기)

### 2. 사용성
- ✅ 직관적 UI (y/n/s/e/q)
- ✅ Visual diff (color, syntax highlighting)
- ✅ Progress tracking (몇 개 남았는지)

### 3. 성능
- ✅ 비동기 작업 (blocking 없음)
- ✅ Lazy parsing (필요할 때만)
- ✅ Caching (반복 작업 최소화)

### 4. 확장성
- ✅ UI Adapter 패턴 (CLI → Web → IDE)
- ✅ Approval rules (자동 승인)
- ✅ Plugin system (커스텀 로직)

### 5. Git 통합
- ✅ Native commands (git apply, git commit)
- ✅ PR 지원 (GitHub API)
- ✅ Conflict handling (자동 해결 시도)

---

## 구현 순서 (점진적)

### Phase 1: Core (1-2일)
1. DiffManager (diff 생성/파싱)
2. FileDiff, DiffHunk 모델
3. 기본 승인 플로우

### Phase 2: Approval (1-2일)
4. ApprovalManager
5. ApprovalSession (상태 관리)
6. Auto-approval rules

### Phase 3: Committer (1일)
7. PartialCommitter
8. Git apply --cached
9. Rollback 메커니즘

### Phase 4: UI (1-2일)
10. CLIAdapter (Rich, Pygments)
11. Interactive prompts
12. Syntax highlighting

### Phase 5: 통합 (1일)
13. Orchestrator 통합
14. E2E 테스트
15. 문서화

---

## 성공 기준

### Must Have
- ✅ Hunk 단위 승인/거부
- ✅ 승인된 것만 커밋
- ✅ Git native 통합
- ✅ Rollback 지원
- ✅ CLI UI

### Nice to Have
- ⚠️ Line 단위 승인 (너무 세밀할 수 있음)
- ⚠️ Web UI (미래)
- ⚠️ IDE 플러그인 (미래)
- ⚠️ AI 자동 승인 추천 (신뢰도 기반)

### 측정 지표
- 승인 시간: < 30초 per hunk
- False positive: < 5% (잘못 승인)
- Rollback 성공률: > 99%
- UI 반응 시간: < 100ms

---

## 다음 단계

1. DiffManager 구현 (꼼꼼하게)
2. 단위 테스트 (각 hunk 파싱 검증)
3. ApprovalManager 구현
4. CLI UI 구현 (Rich)
5. 통합 및 E2E 테스트
6. 비판적 검증
