# CodeGen Loop 완전 분석

> 2024.12.13 | `/src/contexts/codegen_loop` + Agent 동시편집

---

# Part 1. Architecture

## 디렉토리 구조 (53 files)

```
src/contexts/codegen_loop/
├── api.py                          # CodeGenLoopAPI (Facade)
├── application/
│   ├── codegen_loop.py             # 8-Step Pipeline
│   ├── testgen_loop.py             # Test Generation Loop
│   ├── ports.py                    # LLMPort, HCGPort, SandboxPort...
│   └── shadowfs/
│       ├── shadowfs_port.py        # ShadowFS Port
│       ├── transaction_port.py     # Transaction Port
│       └── plugin_port.py          # Plugin Port
├── domain/
│   ├── models.py                   # Budget, LoopState
│   ├── patch.py                    # Patch, FileChange
│   ├── convergence.py              # ConvergenceCalculator
│   ├── oscillation.py              # OscillationDetector
│   ├── rename.py                   # RenameValidator
│   ├── dependency.py               # DependencyAnalyzer
│   ├── semantic_contract.py        # ContractValidator
│   ├── test_path.py                # TestPath, PathType
│   ├── test_adequacy.py            # TestAdequacy
│   ├── generated_test.py           # GeneratedTest
│   ├── specs/
│   │   ├── arch_spec.py            # ArchSpec (Layer Violations)
│   │   ├── security_spec.py        # SecuritySpec (Taint)
│   │   └── integrity_spec.py       # IntegritySpec (Resource Leak)
│   └── shadowfs/
│       ├── models.py               # FilePatch, Hunk, ChangeType
│       ├── transaction.py          # TransactionState, FileSnapshot
│       └── events.py               # ShadowFSEvent, ConflictError
└── infrastructure/
    ├── config.py                   # BUDGETS, THRESHOLDS
    ├── llm_adapter.py              # ClaudeAdapter (LiteLLM)
    ├── hcg_adapter.py              # HCGAdapter (Query DSL)
    ├── sandbox_adapter.py          # DockerSandboxAdapter
    ├── adapters/
    │   └── unified_shadowfs_adapter.py
    ├── test_coverage/
    │   └── coverage_adapter.py     # CoverageAdapter
    ├── test_gen/
    │   └── test_gen_adapter.py     # TestGenAdapter
    └── shadowfs/
        ├── core.py                 # ShadowFSCore v1
        ├── core_v2.py              # ShadowFSCore v2 (MVCC)
        ├── unified_shadowfs.py     # UnifiedShadowFS
        ├── ir_transaction_manager.py
        ├── event_bus.py            # EventBus
        ├── detectors.py            # GeneratedFileDetector, GitLFSDetector
        ├── path_canonicalizer.py   # PathCanonicalizer
        ├── errors.py               # 6종 예외
        ├── stub_ir.py              # StubIRDocument (임시)
        └── plugins/
            ├── incremental_plugin.py
            └── language_detector.py
```

## Hexagonal Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CodeGenLoopAPI (Facade)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  CodeGenLoop (8-Step)     │    TestGenLoop (Test Generation)           │
├─────────────────────────────────────────────────────────────────────────┤
│                            PORTS (Interfaces)                           │
│  LLMPort │ HCGPort │ SandboxPort │ ShadowFSPort │ TransactionPort      │
│  TestCoveragePort │ TestGenPort │ ShadowFSPlugin                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                         DOMAIN LAYER (Pure)                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Models              │ Logic                   │ Specs                  │
│  ────────────────    │ ─────────────────────   │ ────────────────────   │
│  Patch, FileChange   │ ConvergenceCalculator   │ SecuritySpec (Taint)   │
│  Budget, LoopState   │ OscillationDetector     │ ArchSpec (Layer)       │
│  TestPath            │ RenameValidator         │ IntegritySpec (Leak)   │
│  TestAdequacy        │ DependencyAnalyzer      │                        │
│  GeneratedTest       │ PathExplosionDetector   │                        │
├─────────────────────────────────────────────────────────────────────────┤
│                        DOMAIN/SHADOWFS                                  │
│  TransactionState │ FileSnapshot │ FilePatch │ Hunk │ ShadowFSEvent    │
│  ConflictError │ CommitError                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE LAYER                               │
├─────────────────────────────────────────────────────────────────────────┤
│  ADAPTERS                                                               │
│  ClaudeAdapter │ HCGAdapter │ DockerSandboxAdapter                     │
│  UnifiedShadowFSAdapter │ CoverageAdapter │ TestGenAdapter             │
├─────────────────────────────────────────────────────────────────────────┤
│  SHADOWFS (3-Layer)                                                     │
│  Layer 1: ShadowFSCore (File Overlay + Tombstone)                      │
│  Layer 2: IRTransactionManager (IR Cache + Symbol Table)               │
│  Layer 3: UnifiedShadowFS (Orchestration)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  UTILITIES                                                              │
│  GeneratedFileDetector │ GitLFSDetector │ PathCanonicalizer            │
│  EventBus │ IncrementalUpdatePlugin │ LanguageDetector                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2. 8-Step Pipeline (ADR-011)

## Pipeline 흐름

```python
async def run(self, task_id: str, task_description: str) -> LoopState:
    state = LoopState.initial(task_id, budget)
    txn_id = await self.shadowfs.begin_transaction()

    while not state.should_stop():
        result = await self._run_pipeline(task_description, feedback, txn_id)
        state = state.with_patch(result.patch)

        if result.success:
            # 수렴 체크
            if self.convergence.is_converged(state.patches[-2:]):
                await self.shadowfs.commit_transaction(txn_id)
                break

            # 진동 체크
            if self.oscillation.is_oscillating(state.patches):
                await self.shadowfs.rollback_transaction(txn_id)
                break

            # Accept 시 종료
            if result.patch.status == PatchStatus.ACCEPTED:
                await self.shadowfs.commit_transaction(txn_id)
                break

        feedback = self._generate_feedback(result)
```

## Step 상세

| Step | 이름 | Port 메서드 | 실패시 동작 | Budget |
|------|------|-------------|------------|--------|
| 1 | Scope Selection | `HCGPort.query_scope()` | 빈 리스트 → 실패 | - |
| 2 | Safety Filters | 내부 로직 | 금지패턴/50+파일 → reject | - |
| 3 | LLM Patch Gen | `LLMPort.generate_patch()` | Exception → 실패 | llm_calls++ |
| 4 | Lint/Build/Type | `SandboxPort.validate_*` | score<0.8 → reject | - |
| 5 | Semantic Contract | **TODO** | 항상 통과 | - |
| 6 | HCG Update | `HCGPort.incremental_update()` | Warning only | - |
| 7 | GraphSpec | `HCGPort.verify_*()` | violations → reject | - |
| 8 | Test Execution | `SandboxPort.execute_tests()` | pass_rate<1.0 → 재시도 | test_runs++ |

---

# Part 3. ShadowFS 3-Layer Architecture

## Layer 1: ShadowFSCore (File Layer)

```python
class ShadowFSCore:
    """
    File-level overlay filesystem

    References:
        - Union Filesystems (Pendry & McKusick, 1995)
        - Copy-on-Write (Rosenblum & Ousterhout, 1992)
    """

    overlay: dict[str, str]     # path → content
    deleted: set[str]           # tombstone
    _lock: threading.RLock      # thread safety
```

| 기능 | 구현 | 성능 |
|------|------|------|
| read | deleted → overlay → disk | O(1) |
| write | overlay[path] = content | O(1) |
| delete | deleted.add(path) | O(1) |
| list_files | disk ∪ overlay - deleted | O(N) |
| get_diff | difflib.unified_diff | O(M * L) |
| materialize | symlink + copy | O(N) |

## Layer 2: IRTransactionManager (IR Layer)

```python
class IRTransactionManager:
    """
    IR Transaction with 23 Edge Cases

    References:
        - MVCC (Bernstein & Goodman, 1983)
        - STM (Herlihy & Moss, 1993)
    """

    transactions: dict[str, TransactionState]
    config: IRConfig  # max_file_size=5MB, parse_timeout=5s
```

| Edge Case | 처리 |
|-----------|------|
| Unicode NFD→NFC | 정규화 |
| CRLF→LF | 정규화 |
| File > 5MB | Opaque blob |
| Generated file | Placeholder |
| Git LFS pointer | Placeholder |
| Syntax error | Partial parse |
| Parse timeout | Error document |

## Layer 3: UnifiedShadowFS (Orchestration)

```python
class UnifiedShadowFS:
    """
    Integrates ShadowFSCore + IRTransactionManager

    Workflow:
        1. begin_transaction() → File + IR transaction
        2. write_file() → Update file + parse IR
        3. commit() → Persist both
        4. rollback() → Revert both
    """
```

---

# Part 4. ShadowFS v2 (RFC-018)

## 핵심 특징

```python
class ShadowFSCore:  # core_v2.py
    """
    RFC-018 Implementation

    Features:
        - Multi-transaction support
        - Optimistic concurrency control
        - Event-driven plugin integration
        - Symlink-optimized materialize

    Performance:
        - write(): <
        - commit(): <
        - materialize(10GB): <1s (symlinks)

    References:
        - MVCC (Bernstein & Goodman, 1983)
        - OverlayFS (Linux Kernel, 2014)
    """
```

## Multi-Transaction 상태

```python
_txn_overlays: dict[str, dict[str, str]]       # txn_id → overlay
_txn_deleted: dict[str, set[str]]              # txn_id → deleted
_txn_base_revisions: dict[str, dict[str, str]] # txn_id → {path: hash}
_txn_created_at: dict[str, float]              # txn_id → timestamp
```

## Optimistic Concurrency

```python
async def commit(self, txn_id: str) -> None:
    # 1. Conflict detection
    conflicts = await self._detect_conflicts(txn_id)
    if conflicts:
        raise ConflictError(conflicts=conflicts)

    # 2. Atomic write
    await self._atomic_write(txn_id)

    # 3. Event emission
    await self._event_bus.emit(ShadowFSEvent(type="commit", ...))
```

## Materialize (Symlink 최적화)

```python
async def materialize(self, txn_id: str) -> MaterializeLease:
    """
    Strategy (RFC-018 Section 10):
        1. Symlink dependencies (node_modules, .venv)
        2. Symlink unchanged source files
        3. Copy changed files only

    Performance: <1s for 10GB workspace
    """
```

---

# Part 5. Event System

## ShadowFSEvent

```python
@dataclass(frozen=True)
class ShadowFSEvent:
    type: Literal["write", "delete", "commit", "rollback"]
    path: str
    txn_id: str
    old_content: str | None
    new_content: str | None
    timestamp: float
```

## EventBus

```python
class EventBus:
    """
    Parallel event distribution

    Features:
        - asyncio.gather for parallel execution
        - Error isolation (plugin failure doesn't affect Core)
        - ValidationError propagation (can block commit)
    """

    async def emit(self, event: ShadowFSEvent) -> None:
        tasks = [self._call_plugin(p, event) for p in self._plugins]
        await asyncio.gather(*tasks, return_exceptions=True)
```

## IncrementalUpdatePlugin

```python
class IncrementalUpdatePlugin:
    """
    Automates incremental IR updates and indexing

    Event Handlers:
        - write → track for batch processing
        - commit → IR delta + batch indexing
        - rollback → discard tracked changes

    Performance:
        - write: < (dict operations)
        - commit: < (batch processing)

    Integration:
        - code_foundation.IncrementalIRBuilder
        - multi_index.IncrementalIndexer
    """
```

---

# Part 6. Domain Models

## Patch Lifecycle

```python
class PatchStatus(str, Enum):
    GENERATED = "generated"      # Step 3 완료
    VALIDATED = "validated"      # Step 4 완료
    TESTED = "tested"            # Step 8 완료
    ACCEPTED = "accepted"        # 최종 승인
    FAILED = "failed"            # 실패

@dataclass(frozen=True)
class FileChange:
    file_path: str
    old_content: str
    new_content: str
    diff_lines: list[str]

@dataclass(frozen=True)
class Patch:
    id: str
    iteration: int
    files: list[FileChange]
    status: PatchStatus
    test_results: dict | None
```

## Budget & LoopState

```python
@dataclass(frozen=True)
class Budget:
    max_iterations: int = 10
    max_tokens: int = 100_000
    max_llm_calls: int = 50
    max_test_runs: int = 20
    # + current_* 필드들

    def is_exceeded(self) -> bool: ...
    def with_usage(...) -> Budget: ...  # immutable update

class LoopStatus(str, Enum):
    RUNNING = "running"
    CONVERGED = "converged"
    OSCILLATING = "oscillating"
    BUDGET_EXCEEDED = "budget_exceeded"
    FAILED = "failed"
    ABORTED = "aborted"
```

## Convergence & Oscillation

```python
class ConvergenceCalculator:
    """
    조건: pass_rate >= 1.0 AND change_ratio < 5%
    change_ratio = |curr_diff - prev_diff| / prev_diff
    """

    def is_converged(self, patches: list[Patch]) -> bool: ...

class OscillationDetector:
    """
    조건: 최근 window개와 이전 window개의 유사도 >= 0.85
    유사도 = Jaccard(diff_lines 집합)
    """

    def is_oscillating(self, patches: list[Patch]) -> bool: ...
```

---

# Part 7. GraphSpec Validation (Step 7)

## SecuritySpec (Taint Analysis)

```python
class CWECategory(str, Enum):
    XSS = "CWE-79"
    SQL_INJECTION = "CWE-89"
    OS_COMMAND = "CWE-78"
    PATH_TRAVERSAL = "CWE-22"

@dataclass
class SecuritySpec:
    sources: list[TaintSource]   # request.args, sys.argv...
    sinks: list[TaintSink]       # execute, eval, os.system...
    sanitizers: list[Sanitizer]  # escape, shlex.quote...

    def get_vulnerable_paths(self) -> list[DataflowPath]: ...
```

| CWE | Sources | Sinks | Sanitizers |
|-----|---------|-------|------------|
| XSS | request.args/form/json | render_template_string | escape, bleach |
| SQL Injection | request.*, sys.argv | execute, raw | parameterize |
| OS Command | os.environ, sys.argv | os.system, eval | shlex.quote |
| Path Traversal | request.args/files | open, Path | os.path.abspath |

## ArchSpec (Layer Violations)

```python
class Layer(str, Enum):
    UI = "ui"
    APPLICATION = "application"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    DATABASE = "database"

FORBIDDEN_DEPENDENCIES:
    UI → Infrastructure (bypass)
    UI → Database (bypass)
    Domain → Infrastructure (DDD violation)
    Domain → Database (DDD violation)
```

## IntegritySpec (Resource Leak)

```python
class ResourceType(str, Enum):
    FILE = "file"
    CONNECTION = "connection"
    LOCK = "lock"
    SOCKET = "socket"
    TRANSACTION = "transaction"

# Pattern: open() → ... → close() 경로에서 close 없으면 violation
# Severity: FILE/CONNECTION/TRANSACTION = critical
```

---

# Part 8. Rename Handling (ADR-011 Section 4)

## RenameType

```python
class RenameType(str, Enum):
    SIMPLE = "simple"           # 단순 rename
    OVERLOAD = "overload"       # 오버로드 중 일부
    NAMESPACE = "namespace"     # 네임스페이스 변경
    SCOPE_AWARE = "scope_aware" # 같은 이름, 다른 스코프
    CHAIN = "chain"             # A→B→C
    SWAP = "swap"               # A↔B
```

## 감지 알고리즘

```
1. deleted functions 추출 (diff의 - 라인)
2. added functions 추출 (diff의 + 라인)
3. body similarity 계산 (Jaccard >= 0.85)
4. signature 비교 (arity, param_types, return_type)
5. 조건 만족시 RenameMapping 생성
```

## 검증

```python
class RenameValidator:
    def validate(self, rename: RenameMapping, patch: Patch) -> RenameValidationResult:
        # 1. 모든 caller 파일이 patch에 포함?
        # 2. caller 내부에서 실제로 rename 되었는지?
        # 3. signature 호환성?
```

---

# Part 9. TestGen Loop (ADR-011 Section 12)

## Path 추출 우선순위

| PathType | Priority | Query DSL 패턴 |
|----------|----------|----------------|
| SECURITY | 100 | `Q.Source("request") >> Q.Sink("execute")` |
| EXCEPTION | 50 | `Q.Func(name) >> Q.Block("exception")` |
| NEW_CODE | 30 | Git diff에서 새 함수 감지 |
| UNCOVERED | 20 | Coverage 미달 브랜치 |

## TestAdequacy 기준

```python
MIN_BRANCH_COVERAGE = {
    "default": 0.60,
    "payment": 0.90,
    "auth": 1.00,
}

MAX_FLAKINESS_RATIO = 0.30

# MC/DC: 모든 condition True/False 각 1회
```

---

# Part 10. Errors & Exceptions

## ShadowFS Errors (6종)

```python
class ShadowFSError(Exception): ...

class ExternalDriftError(ShadowFSError):
    """File modified externally during transaction"""

class GeneratedFileError(ShadowFSError):
    """Attempt to modify generated file"""

class SecurityError(ShadowFSError):
    """Path outside project root / symlink jail escape"""

class DiskFullError(ShadowFSError):
    """Insufficient disk space"""

class CyclicSymlinkError(ShadowFSError):
    """Circular symlink detected"""

class ParseTimeout(ShadowFSError):
    """Parse exceeded timeout"""
```

## Transaction Errors

```python
class ConflictError(Exception):
    """Optimistic concurrency conflict"""
    conflicts: list[str]
    txn_id: str

class CommitError(Exception):
    """Commit failed"""
    recoverable: bool
    cause: Exception
```

---

# Part 11. Path Canonicalizer

## TOCTOU 방지

```python
class PathCanonicalizer:
    """
    Security:
        - TOCTOU prevention: O_NOFOLLOW for atomic symlink detection
        - Jail escape prevention: Check AFTER symlink resolution
        - Race condition protection: Atomic file operations

    Pipeline:
        1. Unicode NFC (Mac NFD → Linux NFC)
        2. Path separator (\ → /)
        3. Symlink resolution (ATOMIC with O_NOFOLLOW)
        4. Case normalization (if case-insensitive FS)
        5. Jail check (AFTER resolution)
    """

    def normalize(self, path: str, must_exist: bool = False, check_jail: bool = True) -> str:
        # O_NOFOLLOW로 symlink 원자적 감지
        fd = os.open(str(full_path), os.O_RDONLY | os.O_NOFOLLOW)
```

---

# Part 12. Language Detector

## 지원 언어 (20+)

```python
_EXTENSION_MAP = {
    # Python
    ".py": "python", ".pyi": "python",
    # TypeScript
    ".ts": "typescript", ".tsx": "typescript",
    # JavaScript
    ".js": "javascript", ".jsx": "javascript",
    # Java
    ".java": "java",
    # Kotlin
    ".kt": "kotlin", ".kts": "kotlin",
    # Rust
    ".rs": "rust",
    # Go
    ".go": "go",
    # C/C++
    ".c": "c", ".cpp": "cpp",
    # ... 기타
}
```

---

# Part 13. Agent 동시 편집

## Multi-Agent Models

```python
class AgentType(str, Enum):
    USER = "user"      # 사용자 직접 편집
    AI = "ai"          # AI Agent
    SYSTEM = "system"  # 시스템 Agent

class LockType(str, Enum):
    READ = "read"
    WRITE = "write"

class ConflictType(str, Enum):
    CONCURRENT_EDIT = "concurrent_edit"
    HASH_DRIFT = "hash_drift"
    LOCK_TIMEOUT = "lock_timeout"

class MergeStrategy(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    ABORT = "abort"
    ACCEPT_OURS = "accept_ours"
    ACCEPT_THEIRS = "accept_theirs"
```

## SoftLockManager

```python
class SoftLockManager:
    """
    Redis 기반 분산 Lock

    기능:
        - Soft Lock 획득/해제
        - 충돌 감지
        - Hash Drift 감지
    """

    async def acquire_lock(self, agent_id: str, file_path: str) -> LockAcquisitionResult:
        # 기존 Lock 확인
        existing = await self.get_lock(file_path)
        if existing and existing.agent_id != agent_id:
            return LockAcquisitionResult(
                success=False,
                conflict=Conflict(conflict_type=ConflictType.CONCURRENT_EDIT)
            )

        # Lock 생성 (file hash 저장)
        lock = SoftLock(file_path=file_path, agent_id=agent_id, file_hash=hash)
        await self._store_lock(lock)

    async def detect_drift(self, file_path: str) -> DriftDetectionResult:
        # Lock 시점 hash vs 현재 hash 비교
```

## ConflictResolver (3-Way Merge)

```python
class ConflictResolver:
    """
    Git 3-way merge 기반 충돌 해결

    Merge Strategies:
        - AUTO: git merge-file 자동 merge
        - ACCEPT_OURS: Agent A 채택
        - ACCEPT_THEIRS: Agent B 채택
        - MANUAL: 수동 해결
    """

    async def resolve_3way_merge(self, conflict: Conflict) -> MergeResult:
        # git merge-file 사용
        result = subprocess.run([
            "git", "merge-file", "-p",
            str(ours_file), str(base_file), str(theirs_file)
        ])

        conflicts = self._extract_conflict_regions(result.stdout)

        if not conflicts:
            return MergeResult(success=True, strategy=MergeStrategy.AUTO)
        else:
            return MergeResult(success=False, conflicts=conflicts, strategy=MergeStrategy.MANUAL)
```

---

# Part 14. Diff Management

## DiffManager

```python
class DiffManager:
    """
    Git unified diff 생성/파싱

    기능:
        - Unified diff 생성 (Git 호환)
        - Hunk 단위 파싱
        - Context lines 지원
        - Color 지원 (CLI)
    """

    @dataclass
    class DiffHunk:
        header: str           # "@@ -10,5 +10,7 @@"
        old_start: int
        old_count: int
        new_start: int
        new_count: int
        lines: list[str]      # [" context", "-old", "+new"]

    @dataclass
    class FileDiff:
        file_path: str
        change_type: str      # added, deleted, modified, renamed
        hunks: list[DiffHunk]

        def get_hunks_patch(self, indices: list[int]) -> str:
            """선택한 hunk만 patch 생성"""
```

---

# Part 15. Approval Manager

## 승인 모드

| Mode | 단위 | 설명 |
|------|------|------|
| file | 파일 | 파일 전체 승인/거부 |
| hunk | Hunk | Hunk 단위 선택 승인 |
| line | 라인 | 라인 단위 선택 (TODO) |

## ApprovalSession

```python
class ApprovalSession:
    session_id: str
    file_diffs: list[FileDiff]
    decisions: list[ApprovalDecision]

    def get_approved_file_diffs(self) -> list[FileDiff]:
        """승인된 변경사항만 반환"""

    def get_statistics(self) -> dict:
        """승인률, 소요시간 등"""

class ApprovalCriteria:
    auto_approve_tests: bool      # 테스트 파일 자동 승인
    auto_approve_docs: bool       # 문서 파일 자동 승인
    max_lines_auto: int           # 이 라인 이하면 자동 승인
    allowed_patterns: list[str]
    blocked_patterns: list[str]
```

---

# Part 16. Fuzzy Patcher

## FuzzyPatcherAdapter

```python
class FuzzyPatcherAdapter:
    """
    git apply 실패 시 유연한 패칭

    Algorithm:
        1. git apply 시도
        2. 실패시 → fuzzy matching
        3. SequenceMatcher로 유사 블록 찾기
        4. 앵커 포인트 기반 위치 조정
    """

    async def apply_patch(self, file_path: str, diff: str) -> PatchResult:
        git_result = await self._try_git_apply(file_path, diff)
        if git_result.is_success():
            return git_result

        return await self._fuzzy_apply(file_path, diff)

    async def fuzzy_match(self, anchor: DiffAnchor, file_content: str, threshold: float = 0.8) -> int:
        """
        Similarity = 0.7 * line_sim + 0.3 * context_sim
        """

class PatchStatus(str, Enum):
    SUCCESS = "success"
    FUZZY_APPLIED = "fuzzy_applied"
    CONFLICT = "conflict"
    FAILED = "failed"
```

---

# Part 17. PartialCommitter (Git 연동)

## PartialCommitter

```python
class PartialCommitter:
    """
    승인된 변경사항만 Git에 적용

    기능:
        1. Partial staging (git apply --cached)
        2. Atomic operations (전체 성공 or 전체 실패)
        3. Rollback 지원 (Shadow branch)
        4. CASCADE Fuzzy Patcher 통합
    """

    async def apply_partial(
        self,
        approved_file_diffs,
        commit_message: str,
        branch_name: str | None = None,
        create_shadow: bool = True,
    ) -> PartialCommitResult:
        # 1. Shadow branch 생성 (rollback용)
        rollback_sha = await self._create_shadow_branch()

        # 2. 브랜치 생성/전환
        if branch_name:
            await self._checkout_or_create_branch(branch_name)

        # 3. Patch 적용 (git apply → fuzzy fallback)
        for file_path, patch in patches:
            try:
                await self._apply_patch(patch, file_path)
            except:
                # CASCADE Fuzzy Patcher 시도
                if self.fuzzy_patcher:
                    await self.fuzzy_patcher.apply_patch(file_path, patch)

        # 4. Staging + Commit
        await self._stage_files(applied_files)
        commit_sha = await self._create_commit(commit_message)
```

## Shadow Branch 흐름

```
                    HEAD
                      │
     ┌────────────────┼────────────────┐
     │                │                │
     ▼                ▼                ▼
 shadow-abc123    feature-x     (rollback point)
     │                │
     │           ┌────┴────┐
     │           │ PATCH   │
     │           └────┬────┘
     │                │
     │                ▼
     │          new commit
     │                │
     └─── git reset --hard (on failure)
```

## PartialCommitResult

```python
@dataclass
class PartialCommitResult:
    success: bool
    commit_sha: str | None
    branch_name: str | None
    applied_files: list[str]
    errors: list[str]
    rollback_sha: str | None  # Shadow branch SHA
```

## PR 생성 (GitHub CLI)

```python
async def create_pr(
    self,
    branch_name: str,
    title: str,
    body: str,
    base_branch: str = "main",
) -> str | None:
    result = subprocess.run([
        "gh", "pr", "create",
        "--base", base_branch,
        "--head", branch_name,
        "--title", title,
        "--body", body,
    ])
    return result.stdout.strip()  # PR URL
```

---

# Part 18. IGitRepository Port

```python
class IGitRepository(ABC):
    """
    Git Repository Port (Hexagonal Architecture)

    Domain이 정의, Infrastructure가 구현
    """

    @abstractmethod
    async def apply_partial(
        self,
        approved_file_diffs,
        commit_message: str,
        branch_name: str | None = None,
        create_shadow: bool = True,
    ) -> PartialCommitResult: ...

    @abstractmethod
    async def rollback_to_shadow(self, shadow_sha: str) -> None: ...

    @abstractmethod
    async def create_pr(
        self,
        branch_name: str,
        title: str,
        body: str,
        base_branch: str = "main",
    ) -> str | None: ...

    @abstractmethod
    def get_current_branch(self) -> str: ...

    @abstractmethod
    def has_uncommitted_changes(self) -> bool: ...
```

---

# Part 19. AgentCoordinator

```python
class AgentCoordinator:
    """
    Multi-Agent 조율

    기능:
        - Agent 생성/관리 (spawn/shutdown)
        - Task 분배 (Round-robin)
        - 상태 동기화
        - 충돌 감지/해결
    """

    def __init__(
        self,
        lock_manager: SoftLockManager,
        conflict_resolver: ConflictResolver,
    ):
        self._sessions: dict[str, AgentSession] = {}

    async def spawn_agent(self, agent_id: str, agent_type: AgentType) -> AgentSession:
        """새 Agent 생성"""

    async def distribute_tasks(self, tasks: list, num_agents: int = 2) -> dict[str, AgentSession]:
        """Task를 Agent들에게 Round-robin 분배"""

    async def detect_conflicts(self) -> list[Conflict]:
        """동일 파일 2+ Lock → Conflict"""

    async def resolve_all_conflicts(self, conflicts: list[Conflict]) -> dict:
        """3-way merge 시도, 실패시 manual"""

    async def shutdown_agent(self, agent_id: str) -> bool:
        """Lock 해제 + 세션 정리"""
```

---

# Part 20. CASCADE Ports

## IFuzzyPatcher

```python
class IFuzzyPatcher(Protocol):
    async def apply_patch(self, file_path: str, diff: str, fallback_to_fuzzy: bool = True) -> PatchResult: ...
    async def find_anchors(self, file_content: str, target_block: str) -> list[DiffAnchor]: ...
    async def fuzzy_match(self, anchor: DiffAnchor, file_content: str, threshold: float = 0.8) -> int | None: ...
```

## IReproductionEngine (Reproduction-First)

```python
class IReproductionEngine(Protocol):
    """
    TDD Cycle:
        1. generate_reproduction_script() → 버그 재현 스크립트 생성
        2. verify_failure() → 실패 확인 (버그 재현)
        3. Code 수정
        4. verify_fix() → 성공 확인
    """

    async def generate_reproduction_script(
        self, issue_description: str, context_files: list[str], tech_stack: dict
    ) -> ReproductionScript: ...

    async def verify_failure(self, script: ReproductionScript) -> ReproductionResult: ...
    async def verify_fix(self, script: ReproductionScript) -> ReproductionResult: ...
```

## IProcessManager (Zombie Killer)

```python
class IProcessManager(Protocol):
    async def scan_processes(self, sandbox_id: str) -> list[ProcessInfo]: ...
    async def kill_zombies(self, sandbox_id: str, force: bool = False) -> list[int]: ...
    async def cleanup_ports(self, sandbox_id: str, port_range: tuple[int, int] = (8000, 9000)) -> list[int]: ...
```

## IGraphPruner (PageRank)

```python
class IGraphPruner(Protocol):
    """
    Context Token 최적화

    Strategy:
        - Top 20% 노드: 본문 포함
        - 나머지: 시그니처만
        - 토큰 예산 내에서 최적화
    """

    async def calculate_pagerank(
        self, nodes: list[GraphNode], edges: list[tuple[str, str]], damping: float = 0.85
    ) -> dict[str, float]: ...

    async def prune_context(
        self, nodes: list[GraphNode], max_tokens: int = 8000, top_k_full: int = 20
    ) -> PrunedContext: ...
```

## ICascadeOrchestrator

```python
class ICascadeOrchestrator(Protocol):
    async def execute_tdd_cycle(
        self, issue_description: str, context_files: list[str], max_retries: int = 3
    ) -> dict: ...

    async def optimize_context(
        self, repo_path: str, query: str, max_tokens: int = 8000
    ) -> PrunedContext: ...
```

---

# Part 21. LockManagerProtocol

```python
@runtime_checkable
class LockManagerProtocol(Protocol):
    """
    Multi-Agent Lock 관리 Protocol

    구현체:
        - SoftLockManager (메모리 기반)
        - 향후: RedisLockManager, PostgresLockManager
    """

    async def acquire_lock(
        self, agent_id: str, file_path: str, lock_type: str
    ) -> LockAcquisitionResultProtocol: ...

    async def release_lock(self, agent_id: str, file_path: str) -> bool: ...

    async def get_lock(self, file_path: str) -> SoftLockProtocol | None: ...

@runtime_checkable
class SoftLockProtocol(Protocol):
    agent_id: str
    file_path: str

@runtime_checkable
class LockAcquisitionResultProtocol(Protocol):
    success: bool
    message: str
    existing_lock: SoftLockProtocol | None
```

---

# Part 22. GitPython VCS Adapter

```python
class GitPythonVCSAdapter(IVCSApplier):
    """
    GitPython 기반 VCS 어댑터

    기능:
        - Branch 생성/checkout
        - 파일 변경 적용 (create, modify, delete)
        - Commit
        - Conflict resolution (Ours 전략)
    """

    async def apply_changes(
        self,
        repo_path: str,
        changes: list[CodeChange],
        branch_name: str,
    ) -> CommitResult:
        repo = self._get_repo()

        # 1. Branch checkout/create
        repo.git.checkout(branch_name)

        # 2. 파일 변경 적용
        for change in changes:
            if change.change_type == "create":
                file_path.write_text("\n".join(change.new_lines))
            elif change.change_type == "modify":
                # 라인 교체
            elif change.change_type == "delete":
                file_path.unlink()

        # 3. git add + commit
        repo.index.add(files_changed)
        commit = repo.index.commit(commit_message)

    async def resolve_conflict(self, repo_path: str, conflict_data: str) -> ConflictResolutionResult:
        # Conflict markers 파싱 후 ours 선택

class StubVCSApplier(IVCSApplier):
    """테스트용 Stub (Git 없이 파일만 수정)"""
```

---

# Part 23. CASCADE Orchestrator

```python
class CascadeOrchestratorAdapter(ICascadeOrchestrator):
    """
    Reproduction-First TDD 사이클 전체 조율

    Dependencies:
        - fuzzy_patcher: IFuzzyPatcher
        - reproduction_engine: IReproductionEngine
        - process_manager: IProcessManager
        - graph_pruner: IGraphPruner
        - code_generator: DeepReasoningOrchestrator
    """

    async def execute_tdd_cycle(
        self, issue_description: str, context_files: list[str], max_retries: int = 3
    ) -> dict:
        """
        Phase 1: Reproduction Script 생성
        Phase 2: Verify Failure (버그 재현)
        Phase 3: Code 수정 (Fuzzy Patch + 재시도)
            3-1. Sandbox 정리 (Zombie Killer)
            3-2. DeepReasoningOrchestrator로 수정 생성
            3-3. FuzzyPatcher로 적용
            3-4. Verify Pass
        Phase 4: Final Cleanup
        """

    async def optimize_context(self, repo_path: str, query: str, max_tokens: int = 8000) -> PrunedContext:
        """
        Graph RAG 기반 컨텍스트 최적화

        1. Graph 구축 (GraphBuilder + IR Analyzer)
        2. PageRank 계산
        3. Pruning (Top 20% full, 나머지 signature)
        """
```

---

# Part 24. Infrastructure Adapters

## IFileSystem (PathlibAdapter)

```python
class PathlibAdapter(IFileSystem):
    """pathlib 기반 파일시스템"""

    async def read_text(self, path: str, encoding: str = "utf-8") -> str: ...
    async def write_text(self, path: str, content: str) -> None: ...
    async def exists(self, path: str) -> bool: ...
    async def get_info(self, path: str) -> FileSystemEntry: ...
    async def create_temp_file(self, suffix: str, content: str | None) -> str: ...
    async def delete(self, path: str) -> None: ...
```

## ICommandExecutor (AsyncSubprocessAdapter)

```python
class AsyncSubprocessAdapter(ICommandExecutor):
    """asyncio.subprocess 기반"""

    async def execute(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        proc = await asyncio.create_subprocess_exec(*command, ...)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)

@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    status: CommandStatus  # SUCCESS, FAILED, TIMEOUT

class SyncSubprocessAdapter(ICommandExecutor):
    """subprocess.run 기반 (sync → async 래핑)"""
```

---

# Part 25. Foundation Layer Ports (src/ports.py)

## Index Ports

| Port | 백엔드 | 용도 |
|------|--------|------|
| LexicalIndexPort | Zoekt | 텍스트/identifier/regex 검색 |
| VectorIndexPort | Qdrant | 시맨틱/임베딩 검색 |
| SymbolIndexPort | Kuzu | go-to-def, find-refs, call graph |
| FuzzyIndexPort | PostgreSQL pg_trgm | Typo 허용 검색 |
| DomainMetaIndexPort | - | README/ADR/Docs 검색 |
| RuntimeIndexPort | - | Hot path, error 기반 검색 |
| RepoMapPort | PostgreSQL | RepoMap 스냅샷 쿼리 |

## Agent Execution Ports

```python
class IWorkflowEngine(Protocol):
    """LangGraph/Temporal/Prefect 추상화"""
    async def execute(self, steps: list[WorkflowStep], initial_state) -> WorkflowResult: ...

class ISandboxExecutor(Protocol):
    """E2B/Firecracker/Docker/K8s 추상화"""
    async def create_sandbox(self, config) -> SandboxHandle: ...
    async def execute_code(self, handle, code, language) -> ExecutionResult: ...
    async def destroy_sandbox(self, handle) -> None: ...

class ILLMProvider(Protocol):
    """LiteLLM/LangChain 추상화"""
    async def complete(self, messages, model_tier="medium") -> str: ...
    async def complete_with_schema(self, messages, schema: type) -> Any: ...
    async def get_embedding(self, text) -> list[float]: ...

class IGuardrailValidator(Protocol):
    """Guardrails AI/Pydantic 검증"""
    async def validate(self, data, policies, level="repo") -> ValidationResult: ...

class IVCSApplier(Protocol):
    """GitPython/libgit2 추상화"""
    async def apply_changes(self, changes, branch_name) -> CommitResult: ...
    async def create_pr(self, branch_name, title, body) -> PRResult: ...
    async def resolve_conflict(self, conflict, strategy="llm") -> ConflictResolution: ...

class IMetricsCollector(Protocol):
    """Prometheus/DataDog 추상화"""
    def record_counter(self, name, value=1.0, labels=None) -> None: ...
    def record_gauge(self, name, value, labels=None) -> None: ...
    def record_histogram(self, name, value) -> None: ...

class IHealthChecker(Protocol):
    async def check_health(self) -> dict[str, bool]: ...
    async def check_component(self, component: str) -> bool: ...

class IVisualValidator(Protocol):
    """Playwright/Selenium 추상화"""
    async def capture_screenshot(self, url, selector=None) -> Screenshot: ...
    async def compare_screenshots(self, before, after, use_vision_model=True) -> VisualDiff: ...
```

## Agent Service Protocols

```python
class IAnalyzeService(Protocol):
    async def analyze_task(self, task: AgentTask) -> dict: ...

class IPlanService(Protocol):
    async def plan_changes(self, task, analysis) -> dict: ...

class IGenerateService(Protocol):
    async def generate_code(self, task, plan) -> list[CodeChange]: ...

class ICriticService(Protocol):
    async def review_code(self, changes) -> list[str]: ...  # 문제 리스트

class ITestService(Protocol):
    async def run_tests(self, changes) -> list[ExecutionResult]: ...

class IHealService(Protocol):
    async def suggest_fix(self, errors, changes) -> list[CodeChange]: ...
```

---

# Part 26. Configuration (기존 Part 17)

```python
# config.py
BUDGETS = {
    "max_iterations": 10,
    "max_tokens_per_request": 4096,
    "total_token_budget": 50000,
}

THRESHOLDS = {
    "convergence": 0.95,
    "oscillation_similarity": 0.9,
    "test_pass_rate": 1.0,
}

LLM_CONFIG = {
    "model": "claude-3-5-sonnet-20241022",
    "temperature": 0.3,
}

# IRConfig
max_file_size = 5 * 1024 * 1024  # 5MB
parse_timeout = 5.0              # seconds

# CoreConfig (v2)
max_file_size = 10 * 1024 * 1024 # 10MB
materialize_use_symlinks = True
txn_ttl = 3600.0                 # 1 hour
```

---

# Part 27. LATS (Language Agent Tree Search)

## LATSNode (MCTS Tree Node)

```python
class LATSNode:
    """
    MCTS 기반 트리 탐색 노드

    References:
        - MCTS (Coulom, 2006)
        - UCT (Kocsis & Szepesvari, 2006)
        - LATS (Zhou et al., 2023)
    """

    # Tree Structure
    node_id: str
    parent: LATSNode | None
    children: list[LATSNode]
    depth: int

    # State
    partial_thought: str      # 중간 단계
    thought_diff: str         # 부모 대비 변화량 (Context 경량화)
    completed_strategy: CodeStrategy | None

    # MCTS Values
    visit_count: int = 0
    total_value: float = 0.0
    q_value: float = 0.0      # Q(s,a) = avg reward

    # Reflection
    thought_score: float = 0.0
    is_promising: bool = True
    is_terminal: bool = False
    rejected_reasons: list[str]

    def ucb(self, c: float = 1.4) -> float:
        """
        UCT (Upper Confidence Bound for Trees)

        UCB1 = Q(s,a) + c * sqrt(ln(N_parent) / N_child)
        """
        if self.visit_count == 0:
            return float("inf")  # 미방문 우선

        exploitation = self.q_value
        exploration = c * math.sqrt(math.log(self.parent.visit_count) / self.visit_count)
        return exploitation + exploration

    def update_q_value(self, reward: float):
        """Q(s,a) = (Q * N + reward) / (N + 1)"""
        self.visit_count += 1
        self.total_value += reward
        self.q_value = self.total_value / self.visit_count
```

## MCTSConfig

```python
@dataclass
class MCTSConfig:
    # MCTS Parameters
    max_iterations: int = 100
    max_depth: int = 5
    exploration_constant: float = 1.4   # UCT c 값
    early_stop_threshold: float = 0.9

    # Dynamic Temperature (Phase별)
    temperature_expansion: float = 0.8    # 확장 (다양성)
    temperature_evaluation: float = 0.2   # 평가 (안정성)
    temperature_simulation: float = 0.0   # 시뮬레이션 (결정론)
    temperature_final: float = 0.3        # 최종 (품질)

    # Budget Limits
    max_total_tokens: int = 50_000
    max_cost_usd: float = 5.0

    # Early Give-up
    early_giveup_iterations: int = 10
    early_giveup_threshold: float = 0.3

    # Cross-Model Strategy
    generator_model: str = "gpt-4o"        # 생성
    verifier_model: str = "claude-3.5-sonnet"  # 검증
```

## LATSPhase

| Phase | Temperature | 목적 |
|-------|-------------|------|
| EXPANSION | 0.8 | 다양성 (여러 자식 노드 생성) |
| EVALUATION | 0.2 | 안정성 (Thought 평가) |
| SIMULATION | 0.0 | 정확성 (결정론적 실행) |
| FINAL_GENERATION | 0.3 | 품질 (최종 코드 생성) |

## WinningPath (Data Flywheel)

```python
@dataclass
class WinningPath:
    """Fine-tuning & Distillation용 데이터"""

    problem_description: str
    thought_sequence: list[str]  # Root → Leaf 경로
    final_code_changes: dict[str, str]
    final_q_value: float
    reflection_verdict: str  # ACCEPT/REVISE/ROLLBACK

    def to_jsonl(self) -> str:
        """Fine-tuning용 JSONL 형태"""
```

---

# Part 28. ToT (Tree of Thought)

## CodeStrategy

```python
class StrategyType(Enum):
    DIRECT_FIX = "direct_fix"          # 직접 수정
    REFACTOR_THEN_FIX = "refactor_fix" # 리팩토링 후 수정
    TEST_DRIVEN = "test_driven"        # TDD 접근
    DEFENSIVE = "defensive"            # 방어적 코딩
    PATTERN_BASED = "pattern_based"    # 디자인 패턴

@dataclass
class CodeStrategy:
    strategy_id: str
    strategy_type: StrategyType
    title: str
    description: str
    rationale: str
    file_changes: dict[str, str]  # {path: new_content}
    llm_confidence: float
```

## Multi-Criteria Scoring (MCDM)

```python
class ScoringWeights:
    """SOTA: Multi-Criteria Decision Making"""

    CORRECTNESS = 0.40      # 정확성 (테스트 통과)
    QUALITY = 0.25          # 코드 품질 (복잡도, lint)
    SECURITY = 0.20         # 보안
    MAINTAINABILITY = 0.10  # 유지보수성
    PERFORMANCE = 0.05      # 성능

@dataclass
class StrategyScore:
    correctness_score: float    # 0.0 ~ 1.0
    quality_score: float
    security_score: float
    maintainability_score: float
    performance_score: float
    total_score: float          # Weighted sum

    def is_acceptable(self, threshold: float = 0.6) -> bool:
        return self.total_score >= threshold
```

## ExecutionResult

```python
@dataclass
class ExecutionResult:
    # Compilation
    compile_success: bool
    compile_errors: list[str]

    # Testing
    tests_run: int
    tests_passed: int
    test_pass_rate: float

    # Static Analysis
    lint_errors: int
    type_errors: int

    # Security
    security_issues: int
    security_severity: "none" | "low" | "medium" | "high" | "critical"

    # Code Quality
    complexity_delta: float  # Negative is better

    # Graph Impact (CFG/DFG)
    cfg_nodes_added: int
    dfg_edges_changed: int
```

---

# Part 29. Reflection (Self-Reflection)

## ReflectionVerdict

```python
class ReflectionVerdict(Enum):
    ACCEPT = "accept"       # 승인 (배포 가능)
    REVISE = "revise"       # 수정 필요
    ROLLBACK = "rollback"   # 롤백 (원복)
    RETRY = "retry"         # 다른 전략 재시도
```

## GraphImpact (CFG/DFG/PDG 분석)

```python
@dataclass
class GraphImpact:
    """SOTA: CFG/DFG/PDG 변화 분석"""

    # CFG (Control Flow Graph)
    cfg_nodes_added: int
    cfg_nodes_removed: int
    cfg_edges_changed: int

    # DFG (Data Flow Graph)
    dfg_edges_changed: int

    # PDG (Program Dependence Graph)
    pdg_impact_radius: int  # BFS 영향 노드 수

    def calculate_impact_score(self) -> float:
        """
        Impact = 0.4*CFG + 0.3*DFG + 0.3*PDG
        Returns 0.0 (minimal) ~ 1.0 (massive)
        """

class StabilityLevel(Enum):
    STABLE = "stable"       # < 0.2
    MODERATE = "moderate"   # 0.2 ~ 0.5
    UNSTABLE = "unstable"   # 0.5 ~ 0.8
    CRITICAL = "critical"   # >= 0.8
```

## ReflectionRules

```python
class ReflectionRules:
    MIN_TEST_PASS_RATE = 0.8    # 80%
    MAX_GRAPH_IMPACT = 0.6      # 60% 미만
    MIN_CONFIDENCE = 0.7        # 70%

    # Weights
    EXECUTION_WEIGHT = 0.4
    GRAPH_WEIGHT = 0.3
    TRACE_WEIGHT = 0.2
    HISTORICAL_WEIGHT = 0.1
```

---

# Part 30. Safety System

## SafetyOrchestrator

```python
class SafetyOrchestrator:
    """
    Multi-layer validation pipeline

    Dependencies:
        - SecretScannerPort
        - LicenseCheckerPort
        - ActionGatePort
    """

    def validate_pipeline(self, ctx: ValidationContext) -> list[ValidationResult]:
        """
        Stage 1: Secret scanning (API keys, PII)
        Stage 2: License checking (GPL/AGPL block)
        Stage 3: Action gating (dangerous ops approval)
        """
```

## ScrubberConfig

```python
class ScrubberConfig(BaseModel):
    enable_pattern_detection: bool = True   # Regex patterns
    enable_entropy_detection: bool = True   # High entropy strings
    enable_pii_detection: bool = True       # PII (email, SSN...)
    entropy_threshold: float = 4.5
    min_secret_length: int = 8
```

## LicensePolicy

```python
class LicensePolicy(BaseModel):
    # Auto-pass
    allowed: list[LicenseType] = [MIT, APACHE_2, BSD_2, BSD_3, ISC]

    # Manual review
    review_required: list[LicenseType] = [LGPL_2, LGPL_3, MPL_2]

    # Blocked (viral copyleft)
    blocked: list[LicenseType] = [GPL_2, GPL_3, AGPL_3]
```

## GateConfig

```python
class GateConfig(BaseModel):
    auto_approve_low_risk: bool = True
    auto_approve_medium_risk: bool = False
    default_timeout_seconds: int = 300

    # Blacklist (absolute block)
    file_delete_blacklist: ["*.db", ".git/*", ".env"]
    command_blacklist: ["rm -rf /", "dd if=", "mkfs"]
```

---

# Part 31. Optimized LLM Adapter

## Token Bucket Rate Limiting

```python
@dataclass
class TokenBucket:
    """
    초당 요청 수 제한 + Burst 허용
    Thread-safe (asyncio.Lock)
    """

    capacity: int           # 버킷 용량
    refill_rate: float      # 초당 토큰 생성 수

    async def acquire(self, tokens: int = 1) -> bool:
        # Refill
        elapsed = now - self.last_refill
        self.tokens = min(capacity, tokens + elapsed * refill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        # 부족하면 대기
        await asyncio.sleep(wait_time)
```

## Circuit Breaker

```python
class CircuitState(Enum):
    CLOSED = "closed"       # 정상 (요청 통과)
    OPEN = "open"           # 차단 (요청 즉시 실패)
    HALF_OPEN = "half_open" # 복구 시도

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5    # 실패 N회 → OPEN
    recovery_timeout: float = 30.0
    half_open_requests: int = 3   # HALF_OPEN에서 성공해야 CLOSED
```

## OptimizedLLMAdapter 기능

| 기능 | 설명 |
|------|------|
| Batch 처리 | 여러 요청 한 번에 |
| 병렬 처리 | asyncio.gather |
| Token Bucket | Rate Limiting |
| Circuit Breaker | 장애 격리 |
| Redis 캐싱 | LRU 캐시 |
| Retry | Exponential Backoff |
| Cost Tracking | 토큰/비용 추적 |

---

# Part 32. FIM (Fill-in-the-Middle)

## FIMEngine

```python
class FIMEngine(str, Enum):
    OPENAI = "openai"       # GPT-4/3.5
    ANTHROPIC = "anthropic" # Claude
    CODESTRAL = "codestral" # Mistral (코드 특화)
    DEEPSEEK = "deepseek"   # DeepSeek Coder
```

## FIMRequest

```python
@dataclass
class FIMRequest:
    prefix: str             # 커서 이전 코드
    suffix: str             # 커서 이후 코드
    file_path: str
    language: str           # python, typescript...
    max_tokens: int = 500   # 1 ~ 4096
    temperature: float = 0.7
    num_completions: int = 3  # 1 ~ 5
    context_files: list[str]
    engine: FIMEngine | None
```

## Completion & FIMResult

```python
@dataclass
class Completion:
    text: str
    score: float            # 0.0 ~ 1.0
    reasoning: str
    tokens_used: int
    finish_reason: str      # stop, length

    def is_high_quality(self) -> bool:
        return self.score >= 0.8 and self.finish_reason == "stop"

@dataclass
class FIMResult:
    completions: list[Completion]  # 점수 내림차순 정렬됨
    execution_time_ms: float
    total_tokens: int
    engine_used: FIMEngine
```

---

# Part 33. E2B Sandbox Adapter

```python
class E2BSandboxAdapter(ISandboxExecutor):
    """
    E2B Sandbox (Docker 격리)

    Features:
        - Docker 격리
        - 보안 정책 (SecurityLevel)
        - 비밀 관리 (SecretManager)
        - 감사 로그 (AuditLogger)
        - 자동 복구
        - 성능 최적화
    """

    def __init__(
        self,
        config: E2BSandboxConfig,
        secret_manager: SecretManager,
        audit_logger: AuditLogger,
    ): ...

@dataclass
class E2BSandboxConfig:
    api_key: str | None
    template: str = "base"    # Docker template
    timeout_sec: int = 30
    max_retries: int = 3
    security_policy: SecurityPolicy

class SecurityLevel(Enum):
    LOW = "low"       # 개발/테스트
    MEDIUM = "medium" # 기본
    HIGH = "high"     # 프로덕션
    STRICT = "strict" # 금융/의료
```

---

# Part 34. CodeContext (AST 분석)

```python
@dataclass
class CodeContext:
    """
    코드 파일의 구조와 복잡도 표현

    Pure Domain Model - Infrastructure 의존성 없음
    """

    file_path: str
    language: LanguageSupport  # PYTHON (future: TS, GO, RUST)

    # AST Analysis
    ast_depth: int              # 트리 최대 깊이 (중첩 수준)
    complexity_score: float     # 순환 복잡도 (0.0~1.0)
    loc: int                    # Lines of code

    # Symbols
    classes: list[str]
    functions: list[str]
    imports: list[str]

    # Dependencies
    depends_on: set[str]        # 이 파일이 의존하는 파일들
    depended_by: set[str]       # 이 파일을 의존하는 파일들

    @property
    def is_simple(self) -> bool:
        """System 1 적합 (complexity < 0.3, depth < 5, loc < 200)"""

    @property
    def is_complex(self) -> bool:
        """System 2 필요 (complexity > 0.6 or depth > 10 or loc > 500)"""
```

## ImpactReport

```python
@dataclass
class ImpactReport:
    """코드 변경의 영향 분석 결과"""

    changed_files: set[str]
    directly_affected: set[str]       # 직접 영향
    transitively_affected: set[str]   # 간접 영향 (전파)
    risk_score: float                 # 0.0 (safe) ~ 1.0 (risky)
    max_impact_depth: int             # 최대 영향 전파 깊이

    @property
    def is_safe(self) -> bool:
        return self.risk_score < 0.2 and self.max_impact_depth < 3

    @property
    def is_risky(self) -> bool:
        return self.risk_score > 0.6 or self.max_impact_depth > 5
```

---

# Part 35. Experience (경험 학습)

```python
class ProblemType(Enum):
    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    SECURITY = "security"

@dataclass
class AgentExperience:
    """과거 문제 해결 경험 저장"""

    session_id: str
    problem_description: str
    problem_type: ProblemType

    strategy_id: str
    strategy_type: str

    # Code References
    code_chunk_ids: list[str]   # Qdrant chunk IDs
    file_paths: list[str]

    # Results
    success: bool
    tot_score: float
    reflection_verdict: str     # ACCEPT/REVISE/ROLLBACK

    # Metrics
    test_pass_rate: float
    graph_impact: float

    # Context
    similar_to_ids: list[int]   # 유사 경험 ID

@dataclass
class ExperienceQuery:
    """경험 검색 쿼리"""

    problem_type: ProblemType | None
    strategy_type: str | None
    min_score: float
    success_only: bool
    session_id: str | None      # Session 기반 검색
    limit: int = 10
```

---

# Part 36. WorkflowStep (6단계 Workflow)

```
LangGraph Node는 Orchestration만!
Business Logic은 WorkflowStep.execute()에 집중

Analyze → Plan → Generate → Critic → Test → Heal
                    ↑                      ↓
                    └──────────────────────┘
```

## 각 Step 역할

| Step | 역할 | 다음 Step |
|------|------|-----------|
| AnalyzeStep | Task 이해, 복잡도 추정, Context 선택 | Plan |
| PlanStep | 변경 대상 파일 선정, 순서 결정, 리스크 평가 | Generate |
| GenerateStep | LLM 코드 생성, Diff 생성 | Critic |
| CriticStep | 코드 품질 체크, 에러 분류 | Test (OK) / Generate (Error) |
| TestStep | Sandbox 테스트 실행 | None (Pass) / Heal / Plan (Replan) |
| HealStep | 테스트 실패 원인 분석, 자동 수정 | Generate |

## WorkflowStep Interface

```python
class WorkflowStep(ABC):
    @abstractmethod
    async def execute(self, state: WorkflowState) -> WorkflowState:
        """비즈니스 로직 실행"""

    def can_execute(self, state: WorkflowState) -> bool:
        """사전 조건 체크 (max iteration 등)"""
        return state.iteration < state.max_iterations

    def get_next_step_name(self, state: WorkflowState) -> str | None:
        """조건부 전이"""
```

---

# Part 37. PromptManager (중앙 프롬프트 관리)

```python
class PromptManager:
    """
    모든 Agent 프롬프트 중앙 관리

    장점:
        - 버전 관리 용이
        - A/B 테스트 가능
        - 코드 변경 없이 프롬프트 튜닝
        - DB/파일 분리 가능
    """

    INTENT_CLASSIFICATION = """..."""  # FIX_BUG, ADD_FEATURE, REFACTOR...
    CODE_GENERATION = """..."""        # Plan + Context → Code
    CODE_REVIEW = """..."""            # Diff → Issues, Suggestions

    @classmethod
    def get_intent_prompt(cls, user_input: str) -> str: ...

    @classmethod
    def get_code_gen_prompt(cls, context, plan, task, language) -> str: ...

    @classmethod
    def get_review_prompt(cls, file_path, diff) -> str: ...
```

---

# Part 38. Incremental Workflow

```python
@dataclass
class IncrementalContext:
    """Incremental 실행 컨텍스트"""

    is_incremental: bool
    changed_files: list[str]    # 변경된 파일
    impacted_files: list[str]   # 영향받는 파일
    rerun_files: list[str]      # 재실행할 파일

    # Symbol 레벨 (SOTA)
    changed_symbols: list[str]
    impacted_symbols: list[str]

    cache_hits: int
    cache_misses: int

    def get_speedup_ratio(self, total_files: int) -> float:
        """속도 향상 배수 (e.g., 10.0 = 10배 빠름)"""
        return total_files / len(self.rerun_files)
```

## IncrementalCache

```python
class IncrementalCache:
    """Redis 기반 Incremental 캐시"""

    def __init__(self, redis_client=None):
        self._cache: dict[str, Any] = {}
        self.redis_client = redis_client  # SOTA급

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int = 3600): ...
    def invalidate(self, key: str): ...
```

---

# Part 39. AtomicEdit (Multi-file 트랜잭션)

## IsolationLevel

```python
class IsolationLevel(str, Enum):
    READ_UNCOMMITTED = "read_uncommitted"  # Dirty Read 허용
    READ_COMMITTED = "read_committed"       # Committed만 읽기
    SERIALIZABLE = "serializable"           # 완전 격리
```

## TransactionState

```python
class TransactionState(str, Enum):
    PENDING = "pending"           # 시작 전
    LOCKED = "locked"             # Lock 획득됨
    APPLIED = "applied"           # 변경 적용됨
    COMMITTED = "committed"       # 커밋 완료
    ROLLED_BACK = "rolled_back"   # 롤백됨
    FAILED = "failed"             # 실패
```

## ConflictType

```python
class ConflictType(str, Enum):
    HASH_MISMATCH = "hash_mismatch"   # 파일 내용 변경됨
    LOCK_HELD = "lock_held"           # 다른 에이전트가 Lock
    FILE_DELETED = "file_deleted"     # 파일 삭제됨
    FILE_MOVED = "file_moved"         # 파일 이동됨
```

## AtomicEditRequest/Result

```python
@dataclass
class AtomicEditRequest:
    edits: list[FileEdit]
    isolation_level: IsolationLevel = READ_COMMITTED
    dry_run: bool = False
    timeout_seconds: float = 30.0
    agent_id: str

@dataclass
class AtomicEditResult:
    success: bool
    transaction_state: TransactionState
    committed_files: list[str]
    conflicts: list[ConflictInfo]
    rollback_info: RollbackInfo | None
    execution_time_ms: float
```

## FileEdit with Hash

```python
@dataclass
class FileEdit:
    file_path: str
    original_content: str
    new_content: str
    expected_hash: str | None  # Auto-computed if None

    def verify_hash(self, actual_content: str) -> bool:
        """충돌 감지"""
```

---

# Part 40. Refactoring Models

## RefactoringType

```python
class RefactoringType(str, Enum):
    RENAME = "rename"                    # Symbol 이름 변경
    EXTRACT_METHOD = "extract_method"    # 메서드 추출
    EXTRACT_FUNCTION = "extract_function"
    INLINE_VARIABLE = "inline_variable"
    MOVE_TO_FILE = "move_to_file"
```

## SymbolInfo (LSP 기반)

```python
class SymbolKind(str, Enum):
    VARIABLE = "variable"    # x = 1
    FUNCTION = "function"    # def func():
    CLASS = "class"          # class MyClass:
    METHOD = "method"        # def method(self):
    MODULE = "module"        # import math
    PROPERTY = "property"
    CONSTANT = "constant"

@dataclass
class SymbolInfo:
    name: str
    kind: SymbolKind
    location: SymbolLocation  # (file_path, line, column)
    scope: str                # module, class name
    type_annotation: str | None
    docstring: str | None

    @property
    def is_private(self) -> bool:
        return self.name.startswith("_")
```

## Refactoring Requests

```python
@dataclass
class RenameRequest:
    symbol: SymbolInfo
    new_name: str
    dry_run: bool = False

@dataclass
class ExtractMethodRequest:
    file_path: str
    start_line: int
    end_line: int
    new_function_name: str
    target_scope: str = "module"
```

---

# Part 41. Secret Scanner (Pattern + Entropy)

```python
class SecretScrubberAdapter:
    """
    Enterprise-grade secret/PII scrubber

    Features:
        - Pattern-based detection (API keys, passwords, tokens)
        - Entropy-based detection (high-entropy strings)
        - Named entity recognition for PII
        - Whitelist/blacklist management
        - Auto-redaction
    """

    PATTERNS = [
        # AWS
        SecretPattern("AWS Access Key ID", r"AKIA[A-Z0-9]{16}", SecretType.AWS_KEY, 0.95),
        SecretPattern("AWS Secret Key", r"aws.{0,20}[0-9a-zA-Z/+]{40}", SecretType.AWS_KEY, 0.90),

        # GitHub
        SecretPattern("GitHub Token", r"gh[pousr]_[A-Za-z0-9_]{36,255}", SecretType.GITHUB_TOKEN, 0.95),

        # Slack
        SecretPattern("Slack Token", r"xox[baprs]-([0-9a-zA-Z]{10,48})", SecretType.SLACK_TOKEN, 0.90),
        SecretPattern("Slack Webhook", r"https://hooks.slack.com/services/...", SecretType.SLACK_TOKEN, 0.95),

        # Generic
        SecretPattern("API Key", r"api[_-]?key.{32,}", SecretType.API_KEY, 0.80),
        SecretPattern("Password in URL", r"[a-z]+://user:pass@...", SecretType.PASSWORD, 0.85),
    ]
```

## Entropy 기반 탐지

```python
def calculate_entropy(self, text: str) -> float:
    """Shannon entropy 계산 (threshold: 4.5)"""
    # H = -sum(p * log2(p))
    # 무작위 문자열은 entropy가 높음 → 비밀 가능성

def detect_high_entropy_strings(self, content: str) -> list[DetectionResult]:
    """Entropy > threshold인 문자열 탐지"""
```

---

# Part 42. Dynamic Reasoning Router (System 1/2)

```
           ┌──────────────────────────────────────────┐
           │        DynamicReasoningRouter            │
           │                                          │
  Query ──>│  Complexity < 0.3 && Risk < 0.4?       │
           │                                          │
           │     YES ──> System 1 (Fast Path)        │
           │              - v7 Linear Engine          │
           │              - $0.01, 5초               │
           │                                          │
           │     NO ──> System 2 (Slow Path)         │
           │              - v8 ReAct + ToT Engine    │
           │              - $0.15, 45초              │
           └──────────────────────────────────────────┘
```

## QueryFeatures

```python
@dataclass
class QueryFeatures:
    # Code Complexity
    file_count: int
    impact_nodes: int
    cyclomatic_complexity: float

    # Risk Factors
    has_test_failure: bool
    touches_security_sink: bool   # Security → 무조건 System 2
    regression_risk: float

    # Historical
    similar_success_rate: float
    previous_attempts: int

    def calculate_complexity_score(self) -> float:
        """0.2*file + 0.3*impact + 0.5*cyclomatic"""

    def calculate_risk_score(self) -> float:
        """regression*0.5 + test_fail*0.3 + security*0.2"""
```

## ReasoningDecision

```python
class ReasoningPath(Enum):
    SYSTEM_1 = "fast"   # Linear, v7 Engine
    SYSTEM_2 = "slow"   # ReAct + ToT, v8 Engine

@dataclass
class ReasoningDecision:
    path: ReasoningPath
    confidence: float
    reasoning: str
    complexity_score: float
    risk_score: float
    estimated_cost: float   # USD
    estimated_time: float   # seconds
```

---

# Part 43. LATSSearchEngine (MCTS 4단계)

```python
class LATSSearchEngine:
    """
    MCTS (Monte Carlo Tree Search) 4단계

    1. Selection: UCT로 유망한 노드 선택
    2. Expansion: LLM으로 자식 노드 생성
    3. Simulation: Sandbox에서 전략 실행
    4. Backpropagation: 결과를 Root까지 전파
    """

    async def search(
        self,
        problem: str,
        context: dict,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToTResult:
        """MCTS 탐색 실행"""

    # Selection
    def _select(self, node: LATSNode) -> LATSNode:
        """UCT 기반 노드 선택"""
        return max(node.children, key=lambda c: c.ucb(self.config.exploration_constant))

    # Expansion
    async def _expand(self, node: LATSNode, problem: str, context: dict):
        """LLM으로 다음 Thought 생성"""
        thoughts = await self.executor.generate_next_thoughts(...)
        for thought in thoughts:
            child = LATSNode(node_id=..., partial_thought=thought)
            node.add_child(child)

    # Backpropagation
    def _backpropagate(self, node: LATSNode, reward: float):
        """결과를 Root까지 전파"""
        while node:
            node.update_q_value(reward)
            node = node.parent
```

---

# Part 44. LATSReflexion (Verbal Feedback)

```python
class LATSReflexion:
    """
    실패 이유 전파 (SOTA)

    효과: 탐색 효율 3배 향상

    원리:
        - 숫자(Q-value) → 텍스트(이유)로 변환
        - 실패 이유를 부모/형제 노드에 전파
        - 같은 실수 반복 방지
    """

    def extract_failure_reason(self, node: LATSNode, execution_error: str | None) -> str:
        """실행 에러 또는 Q-value/Thought Score 기반 이유 추출"""

    def propagate_to_parent(self, failed_node: LATSNode, failure_reason: str):
        """부모 노드에 실패 이유 추가"""
        failed_node.parent.add_rejection_reason(failure_reason)

    def get_sibling_hints(self, node: LATSNode) -> list[str]:
        """형제 노드 생성 시 활용할 힌트"""
        return node.parent.rejected_reasons
```

---

# Part 45. Reasoning Ports

## IComplexityAnalyzer

```python
class IComplexityAnalyzer(Protocol):
    """Radon / AST 기반 복잡도 분석"""

    def analyze_cyclomatic(self, code: str) -> float: ...
    def analyze_cognitive(self, code: str) -> float: ...
    def count_impact_nodes(self, file_path: str) -> int: ...
```

## IRiskAssessor

```python
class IRiskAssessor(Protocol):
    """경험 기반 / 정적 분석 위험도 평가"""

    def assess_regression_risk(self, problem: str, files: list[str]) -> float: ...
    def check_security_sink(self, code: str) -> bool: ...
    def check_test_failure(self, files: list[str]) -> bool: ...
```

## IGraphAnalyzer

```python
class IGraphAnalyzer(Protocol):
    """Memgraph / NetworkX 기반 그래프 분석"""

    def analyze_graph_impact(self, file_changes: dict[str, str]) -> GraphImpact: ...
    def calculate_impact_radius(self, changed_files: list[str]) -> int: ...
    def analyze_execution_trace(self, before: str, after: str) -> ExecutionTrace: ...
```

## ILATSExecutor (extends IToTExecutor)

```python
class ILATSExecutor(IToTExecutor, Protocol):
    # ToT 메서드
    async def generate_strategies(self, problem, context, count=3) -> list[CodeStrategy]: ...
    async def execute_strategy(self, strategy, timeout=60) -> ExecutionResult: ...

    # LATS 전용 메서드
    async def generate_next_thoughts(self, current_state, problem, context, k=3) -> list[str]: ...
    async def evaluate_thought(self, partial_thought) -> float: ...
    async def generate_complete_strategy(self, thought_path, problem, context) -> CodeStrategy: ...
```

---

# Part 46. Code Editing Ports (ISP 준수)

```python
# ISP (Interface Segregation Principle) 분리

@runtime_checkable
class FIMPort(Protocol):
    """Fill-in-the-Middle"""
    async def complete(self, request: FIMRequest) -> FIMResult: ...
    async def complete_streaming(self, request: FIMRequest) -> AsyncIterator[Completion]: ...

@runtime_checkable
class SymbolFinderPort(Protocol):
    """Jedi 기반 Symbol 찾기"""
    async def find_symbol(self, file_path: str, symbol_name: str) -> SymbolInfo | None: ...

@runtime_checkable
class CodeTransformerPort(Protocol):
    """AST 기반 코드 변환"""
    async def rename_symbol(self, request: RenameRequest) -> RefactoringResult: ...
    async def extract_method(self, request: ExtractMethodRequest) -> RefactoringResult: ...

@runtime_checkable
class TypeHintGeneratorPort(Protocol):
    """Python 타입 힌트 자동 생성"""
    async def generate_type_hints(self, file_path: str) -> RefactoringResult: ...

@runtime_checkable
class RefactoringPort(SymbolFinderPort, CodeTransformerPort, TypeHintGeneratorPort, Protocol):
    """Facade (기존 호환성)"""
    pass

@runtime_checkable
class AtomicEditPort(Protocol):
    """Multi-file atomic transaction"""
    async def execute(self, request: AtomicEditRequest) -> AtomicEditResult: ...
    async def rollback(self, rollback_id: str) -> AtomicEditResult: ...
    async def check_conflicts(self, request: AtomicEditRequest) -> list[str]: ...
```

---

# Part 47. ToTScoringEngine (Multi-Criteria Scoring)

```python
class ToTScoringEngine:
    """
    SOTA: MCDM (Multi-Criteria Decision Making)

    Weighted Sum Model:
        total = 0.4*correctness + 0.25*quality + 0.2*security
              + 0.1*maintainability + 0.05*performance
    """

    def score_strategy(self, strategy: CodeStrategy, result: ExecutionResult) -> StrategyScore:
        correctness = self._score_correctness(result)   # 컴파일 + 테스트 통과율
        quality = self._score_quality(result)           # lint, type, 복잡도
        security = self._score_security(result)         # 보안 심각도
        maintainability = self._score_maintainability(result)  # CFG/DFG 변경량
        performance = self._score_performance(result)   # 실행 시간, 메모리

        # Security Veto: Critical/High → max 0.4
        if result.security_severity in ("critical", "high"):
            total_score = min(total_score, 0.4)
```

## Individual Scoring

| 항목 | 점수 산정 |
|------|-----------|
| Correctness | 컴파일 성공 0.3 + test_pass_rate * 0.7 |
| Quality | 1.0 - lint_errors*0.05 - warnings*0.02 - type_errors*0.1 +/- complexity_delta |
| Security | critical=0.0, high=0.2, medium=0.5, low=0.8, none=1.0 |
| Maintainability | 1.0 - CFG변경*0.01 - DFG변경*0.01 |
| Performance | 1.0 - (time>10s)*penalty - (memory>100MB)*penalty |

## Recommendation

| Score / Confidence | 추천 |
|--------------------|------|
| >= 0.8 / >= 0.7 | 강력 추천 |
| >= 0.6 / >= 0.5 | 조건부 추천 (약점 보완) |
| >= 0.4 | 재검토 필요 |
| < 0.4 | 비추천 |

---

# Part 48. Reasoning Adapters

## RadonComplexityAnalyzer

```python
class RadonComplexityAnalyzer:
    """
    Radon 라이브러리 기반 복잡도 분석
    구현: IComplexityAnalyzer Port
    """

    def analyze_cyclomatic(self, code: str) -> float:
        """radon.complexity.cc_visit 사용"""
        results = cc_visit(code)
        return sum(r.complexity for r in results) / len(results)

    def analyze_cognitive(self, code: str) -> float:
        """MI (Maintainability Index) 기반"""
        mi = mi_visit(code, multi=True)
        return max(0, (100 - mi) / 2)  # MI 낮을수록 복잡

    def count_impact_nodes(self, file_path: str) -> int:
        """Code Foundation CFGBuilder 사용"""
        cfg = CFGBuilder().build(file_path)
        return len(cfg.nodes)

    # Fallback: if/for/while/except 개수 기반
```

## HistoricalRiskAssessor

```python
class HistoricalRiskAssessor:
    """
    경험 기반 위험도 평가
    구현: IRiskAssessor Port
    """

    SECURITY_SINKS = [
        r"os\.system\(",
        r"subprocess\.",
        r"eval\(",
        r"exec\(",
        r"__import__\(",
        r'open\(.+[\'"]w',  # write mode
    ]

    def assess_regression_risk(self, problem: str, files: list[str]) -> float:
        """Experience Store에서 유사 케이스 실패율 기반"""

    def check_security_sink(self, code: str) -> bool:
        """정규표현식으로 위험 패턴 감지"""
        for pattern in self.SECURITY_SINKS:
            if re.search(pattern, code):
                return True
        return False

    def _estimate_risk_from_files(self, files: list[str]) -> float:
        """
        파일 기반 위험도 추정
        - 파일 수가 많으면 위험
        - models/services/core/domain 포함 시 위험
        - 테스트만 있으면 안전 (risk *= 0.3)
        """
```

## LangGraphToTExecutor

```python
class ToTState(TypedDict):
    problem: str
    context: dict
    strategies: list[CodeStrategy]
    strategy_count: int
    current_index: int
    errors: list[str]

class LangGraphToTExecutor:
    """
    LangGraph StateGraph 기반 ToT 실행

    특징:
        - StateGraph로 전략 생성 흐름 관리
        - Parallel Strategy Generation
        - Structured Output (Pydantic)
        - Retry Logic
    """

    def _build_langgraph(self) -> StateGraph:
        """
        generate_node → evaluate_node → select_node
        """
```

---

# Part 49. LATS Advanced Components

## LATSDeduplicator (AST 기반 중복 제거)

```python
class LATSDeduplicator:
    """
    AST Normalization 기반 의미론적 중복 제거

    방식:
        1. AST 파싱
        2. ast.dump(tree, annotate_fields=False)로 정규화
        3. MD5 해시 계산
        4. 중복 감지
    """

    def normalize_code(self, code: str) -> str:
        """변수명, 들여쓰기 무시하고 정규화"""
        tree = ast.parse(code)
        return ast.dump(tree, annotate_fields=False)

    def is_duplicate(self, code: str) -> bool:
        hash_value = self.get_semantic_hash(code)
        if hash_value in self.seen_hashes:
            return True
        self.seen_hashes.add(hash_value)
        return False
```

## LATSThoughtEvaluator (Heuristic + LLM)

```python
class LATSThoughtEvaluator:
    """
    평가 전략:
        - Heuristic Rule: 40%
        - LLM Self-Reflection: 60%
    """

    async def evaluate(self, partial_thought, verifier_model=None) -> float:
        heuristic_score = self._heuristic_evaluation(partial_thought)
        llm_score = await self._llm_evaluation(partial_thought, verifier_model)
        return 0.4 * heuristic_score + 0.6 * llm_score

    def _heuristic_evaluation(self, thought: str) -> float:
        """
        1. 길이 체크 (5~50 words)
        2. 구체성 체크 (키워드: 파일, 함수, 클래스...)
        3. AST Parsing (코드 블록)
        4. 순서 표현 (1., 먼저, then...)
        """
```

## LATSTreePersistence (Crash Recovery)

```python
class LATSTreePersistence:
    """
    JSON 기반 Tree 저장/복원

    효과:
        - Pause & Resume
        - Crash Recovery
        - Time-Travel Debugging
    """

    def save_tree(self, root: LATSNode, search_id: str, metrics: LATSSearchMetrics) -> str:
        tree_data = {
            "search_id": search_id,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics.to_dict(),
            "tree": self._serialize_node(root),  # 재귀 직렬화
        }

    def load_tree(self, search_id: str) -> tuple[LATSNode, LATSSearchMetrics]:
        """Tree 복원 (재귀 역직렬화)"""
```

---

# Part 50. TestAdequacy (MC/DC)

```python
@dataclass(frozen=True)
class TestAdequacy:
    """
    테스트 적정성 (ADR-011 Section 6)

    Thresholds:
        - branch_coverage >= 60%
        - condition_coverage: MC/DC (True/False 각 1회)
        - error_path_count >= 1
        - flakiness_ratio < 30%
    """

    branch_coverage: float      # 0.0 ~ 1.0
    condition_coverage: dict    # {condition_id: {True: bool, False: bool}}
    error_path_count: int
    flakiness_ratio: float

    def is_adequate(self, domain: str = "default") -> bool:
        """
        도메인별 기준:
            - payment: branch >= 90%, mutation >= 85%
            - auth: branch >= 100%
            - default: branch >= 60%
        """

    def _has_mc_dc_coverage(self) -> bool:
        """모든 condition에 대해 True/False 각 1회 이상 실행"""
```

---

# Part 51. SecuritySpec (CWE Taint Analysis)

## CWE Categories

```python
class CWECategory(Enum):
    XSS = "CWE-79"              # Cross-Site Scripting
    SQL_INJECTION = "CWE-89"   # SQL Injection
    OS_COMMAND = "CWE-78"      # OS Command Injection
    PATH_TRAVERSAL = "CWE-22"  # Path Traversal
    XXE = "CWE-611"            # XML External Entity
    CSRF = "CWE-352"           # Cross-Site Request Forgery
    HARDCODED_SECRET = "CWE-798"
```

## Taint Analysis Models

```python
@dataclass(frozen=True)
class TaintSource:
    cwe: CWECategory
    source_patterns: set[str]  # {"request.args", "request.form", ...}

@dataclass(frozen=True)
class TaintSink:
    cwe: CWECategory
    sink_patterns: set[str]    # {"execute", "os.system", "eval", ...}

@dataclass(frozen=True)
class Sanitizer:
    cwe: CWECategory
    sanitizer_patterns: set[str]  # {"escape", "shlex.quote", ...}

@dataclass
class DataflowPath:
    source: str
    sink: str
    path_nodes: list[str]
    has_sanitizer: bool

    @property
    def is_vulnerable(self) -> bool:
        return not self.has_sanitizer
```

## Default Patterns

| CWE | Sources | Sinks | Sanitizers |
|-----|---------|-------|------------|
| XSS | request.args/form/json | render_template_string, Markup | escape, bleach.clean |
| SQL Injection | request.args, sys.argv | execute, cursor.execute | parameterize, prepared_statement |
| OS Command | os.environ, sys.argv | os.system, subprocess.* | shlex.quote |
| Path Traversal | request.files | open, Path | os.path.abspath, secure_filename |

## Severity Calculation

```python
def _calculate_severity(self, path, cwe) -> str:
    base = {
        SQL_INJECTION: "critical",
        OS_COMMAND: "critical",
        XSS: "high",
        PATH_TRAVERSAL: "high",
    }
    # 경로 길이 <= 2 이고 high → critical 승격
```

---

# Part 52. GraphSpec 상세 (ArchSpec + IntegritySpec)

## ArchSpec (Layer Violation Detection)

```python
class Layer(Enum):
    UI = "ui"
    APPLICATION = "application"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    DATABASE = "database"

class ArchSpec:
    """
    ADR-011 FORBIDDEN Dependencies:
        - UI → Infrastructure
        - UI → Database
        - Domain → Infrastructure
        - Domain → Database
    """

    def is_dependency_allowed(self, from_layer: Layer, to_layer: Layer) -> bool:
        return (from_layer, to_layer) not in self.forbidden_dependencies

    def validate_dependency(...) -> ImportViolation | None:
        """Import 문 검증"""
```

## IntegritySpec (Resource Leak Detection)

```python
class ResourceType(Enum):
    FILE = "file"
    CONNECTION = "connection"
    LOCK = "lock"
    SOCKET = "socket"
    TRANSACTION = "transaction"

class IntegritySpec:
    """모든 path에서 open/close 쌍 검증"""

    # Default Patterns
    FILE:        open → close, __exit__
    CONNECTION:  connect → close, disconnect, dispose
    LOCK:        acquire → release
    SOCKET:      socket → close, shutdown
    TRANSACTION: begin → commit, rollback

    def validate_resource_path(self, path: ResourcePath) -> ResourceLeakViolation | None:
        if path.is_leaked:
            return ResourceLeakViolation(...)

# Severity
FILE, CONNECTION, TRANSACTION → critical
LOCK, SOCKET → high
```

---

# Part 53. LATSIntentPredictor (Predictive User Modeling)

```python
class LATSIntentPredictor:
    """
    사용자 의도 예측 (SINGULARITY-ADDENDUM P2)

    책임:
        1. 과거 경험 분석
        2. 다음 요청 예측
        3. 사전 탐색 (Proactive)

    ROI: 매우 높음
    """

    async def predict_next_request(self, session_history: list[str]) -> dict:
        """
        Returns:
            {
                "predicted_intent": str,
                "confidence": float,
                "suggested_solutions": list,
            }
        """

        # 1. Full-Text Search로 유사 세션 검색 (PostgreSQL GIN, <)
        similar_sessions = await self._find_similar_sessions(session_history)

        # 2. 패턴 분석 (예: "파일 읽기" 다음에 "파일 쓰기" 70%)
        patterns = self._analyze_patterns(similar_sessions)

        # 3. 다음 단계 예측
        return self._predict_from_patterns(patterns)

    async def should_expand_solution(self, current_solution, session_history) -> bool:
        """현재 솔루션을 확장 가능하게 만들어야 하는가?"""
        prediction = await self.predict_next_request(session_history)
        return prediction["confidence"] > 0.7
```

---

# Part 54. ConvergenceCalculator + TestPath

## ConvergenceCalculator

```python
class ConvergenceCalculator:
    """
    패치 시퀀스 수렴 판정

    기준:
        1. 마지막 패치가 모든 테스트 통과
        2. 변경량이 임계값(95%) 이하
    """

    def is_converged(self, patches: list[Patch]) -> bool:
        if not self._all_tests_passed(last_patch):
            return False

        change_ratio = self._calculate_change_ratio(patches[-2], patches[-1])
        return change_ratio < (1.0 - self.threshold)

    def _calculate_change_ratio(self, prev: Patch, curr: Patch) -> float:
        """Multi-file diff 길이 기반"""
        prev_total = sum(len(f.diff_lines) for f in prev.files)
        curr_total = sum(len(f.diff_lines) for f in curr.files)
        return abs(curr_total - prev_total) / prev_total
```

## TestPath (테스트 생성 우선순위)

```python
class PathType(Enum):
    SECURITY = "security"     # Priority: 100
    EXCEPTION = "exception"   # Priority: 50
    NEW_CODE = "new_code"     # Priority: 30
    UNCOVERED = "uncovered"   # Priority: 20

@dataclass(frozen=True)
class TestPath:
    path_result: PathResult
    path_type: PathType
    target_function: str
    context: dict

    @property
    def priority(self) -> int:
        return PATH_PRIORITY[self.path_type]
```

---

# Part 55. SelfReflectionJudge

```python
class SelfReflectionJudge:
    """
    Accept/Revise/Rollback 판정 (MCDM)

    Decision Flow:
        1. Critical Issues Check → 즉시 Rollback
        2. Graph Stability Analysis → CRITICAL이면 Rollback
        3. Execution Trace Validation → Regression이면 Revise
        4. Multi-Criteria Scoring
        5. Verdict 결정
    """

    def judge(self, input: ReflectionInput) -> ReflectionOutput:
        # Fast Fail
        critical_issues = self._check_critical_issues(input)
        if critical_issues:
            return _create_rollback_output(...)

        # Graph Stability
        if graph_impact.stability_level == StabilityLevel.CRITICAL:
            return _create_rollback_output(...)

        # Execution Trace
        if execution_trace.has_regressions():
            return _create_revise_output(...)

        # Scoring
        score = self._calculate_confidence_score(input)
        verdict = self._determine_verdict(input, score)
        return _create_output(input, verdict, score)
```

---

# Part 56. TestGenAdapter + CoverageAdapter

## TestGenAdapter (LLM 기반 테스트 생성)

```python
class TestGenAdapter(TestGenPort):
    """
    ADR-011 명세:
        - Input synthesis (boundary, invalid)
        - Mock integrity 검증
        - pytest 템플릿 사용
    """

    async def generate_test(self, target_function: str, path_description: str) -> str:
        """LLM 프롬프트 → pytest 코드"""
        prompt = self._build_prompt(target_function, path_description, "pytest")
        patch = await self.llm.generate_patch(task_description=prompt, ...)
        return patch.files[0].new_content

    async def synthesize_inputs(self, param_types: dict[str, str]) -> list[dict]:
        """
        Input 합성 (ADR-011 Section 12)

        예: {"n": "int"} →
            [{"n": 0}, {"n": -1}, {"n": MAX_INT}, {"n": None}]
        """
```

## CoverageAdapter (pytest-cov 연동)

```python
class CoverageAdapter(TestCoveragePort):
    """
    Production-Grade pytest-cov 연동

    ADR-011:
        - branch_coverage >= 60%
        - condition_coverage (MC/DC)
        - uncovered_branches 탐지
    """

    async def measure_branch_coverage(self, test_code: str, target_function: str) -> float:
        """
        subprocess로 실제 pytest 실행

        pytest --cov=. --cov-branch --cov-report=term-missing

        Returns:
            0.0 ~ 1.0
        """

    async def detect_uncovered_branches(self, target_function: str) -> list[int]:
        """커버되지 않은 브랜치 라인 번호"""
```

---

# Part 57. SuccessEvaluator

```python
@dataclass
class SuccessEvaluation:
    success: bool
    confidence: float        # 0.0 ~ 1.0
    reason: str
    level: "perfect" | "good" | "acceptable" | "poor" | "failed"

class SuccessEvaluator:
    """
    단순 pass/fail이 아닌 다차원 평가

    1. Compilation
    2. Tests (if available)
    3. Code Quality (lint, complexity)
    4. Security
    """

    def evaluate(self, result: ExecutionResult) -> SuccessEvaluation:
        # 1. Compilation 실패 → 무조건 failed
        if not result.compile_success:
            return SuccessEvaluation(success=False, level="failed")

        # 2. Tests 있으면 → Test 결과 우선
        if result.tests_run > 0:
            return self._evaluate_with_tests(result)

        # 3. Tests 없으면 → Compile + Quality 기반
        return self._evaluate_without_tests(result)
```

## Level 판정 기준

| Level | Tests 있을 때 | Tests 없을 때 |
|-------|--------------|---------------|
| perfect | 100% pass + lint 0 | - |
| good | >= 90% pass | - |
| acceptable | >= 50% pass | score >= 0.8 |
| poor | > 0 pass | score >= 0.6 |
| failed | 0% pass 또는 compile fail | score < 0.6 |

---

# Part 58. SemanticContract + DependencyAnalyzer + OscillationDetector

## SemanticContract (계약 검증)

```python
@dataclass(frozen=True)
class SemanticContract:
    """함수의 의미적 계약"""
    function_name: str
    preconditions: list[str]   # 사전 조건
    postconditions: list[str]  # 사후 조건
    invariants: list[str]      # 불변식

    def validate(self) -> bool:
        """계약 유효성 검증"""
```

## DependencyAnalyzer (Cross-file 의존성 분석)

```python
class DependencyAnalyzer:
    """
    ADR-011 Section 5: Cross-file Dependency Rewrite Detection
    """

    def compute_impact_zone(self, changed_functions, callers, callees) -> ImpactZone:
        """
        영향 범위 계산 (depth만큼 반복 확장)

        Returns:
            ImpactZone(changed_functions, affected_files, affected_functions, depth)
        """

    def validate_patch_completeness(self, patch_files, impact_zone) -> DependencyValidationResult:
        """패치에 영향받는 모든 파일 포함되었는지 검증"""
        uncovered = impact_zone.affected_files - patch_files
        if uncovered:
            return failure("INCOMPLETE_PATCH")

class PathExplosionDetector:
    """ADR-011: PATH_EXPLOSION_LIMIT = 10000"""

    def is_exploded(self, impact_zone) -> bool:
        return impact_zone.total_impact > self.limit
```

## OscillationDetector (진동 감지)

```python
class OscillationDetector:
    """
    패치가 반복적으로 같은 패턴인지 감지

    Jaccard Similarity로 diff 유사도 계산
    """

    def is_oscillating(self, patches: list[Patch]) -> bool:
        recent = patches[-window_size:]
        prev = patches[-window_size*2:-window_size]
        similarity = self._calculate_similarity(recent, prev)
        return similarity >= self.similarity_threshold  # default 0.9
```

---

# Part 59. TestGenLoop (테스트 생성 파이프라인)

```python
class TestGenLoop:
    """
    ADR-011 Section 12 기반 테스트 생성

    Pipeline:
        1. Extract paths (Query DSL)
        2. Prioritize (security > exception > new > uncovered)
        3. Generate tests (LLM)
        4. Validate mock integrity
        5. Execute tests (Sandbox)
        6. Measure coverage
        7. Detect flakiness (10회)
        8. Check adequacy (>=60% branch)
    """

    async def run(self, target_function: str, domain: str = "default") -> list[GeneratedTest]:
        # 1. Extract paths
        paths = await self._extract_paths(target_function)

        # 2. Prioritize
        prioritized = sorted(paths, key=lambda p: p.priority, reverse=True)

        # 3-8. Generate & Validate
        for test_path in prioritized[:max_tests]:
            test = await self._generate_and_validate_test(test_path, domain)
            if test and test.is_valuable():
                generated_tests.append(test)

    async def _extract_paths(self, target_function) -> list[TestPath]:
        """
        Query DSL로 Path 추출

        Security:  Q.Source("request") >> Q.Sink("execute")
        Exception: Q.Func >> Q.Block("exception")
        New Code:  Git diff로 감지
        Uncovered: coverage.detect_uncovered_branches()
        """
```

---

# Part 60. Multi-Agent Models 상세

```python
class AgentType(str, Enum):
    USER = "user"      # 사용자 직접 편집
    AI = "ai"          # AI Agent
    SYSTEM = "system"  # 시스템 Agent

class AgentStateType(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"    # Lock 대기
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"

@dataclass
class AgentSession:
    """여러 Agent 동시 실행 상태 추적"""
    session_id: str
    agent_id: str
    agent_type: AgentType
    locked_files: set[str]
    state: AgentStateType

@dataclass
class SoftLock:
    """Soft Lock (편집 중 추적, Hard Lock 아님)"""
    file_path: str
    agent_id: str
    file_hash: str | None    # Lock 시점 파일 해시
    ttl_seconds: int = 1800  # 30분

@dataclass
class Conflict:
    """동시 편집 충돌"""
    conflict_id: str
    file_path: str
    agent_a_id: str
    agent_b_id: str
    agent_a_changes: str
    agent_b_changes: str
    base_content: str
    conflict_type: ConflictType  # CONCURRENT_EDIT, HASH_DRIFT, LOCK_TIMEOUT
```

---

# Part 61. ASTAnalyzer (실제 AST 기반 분석)

```python
class ASTAnalyzer:
    """
    순환 복잡도, 심볼 추출, Import 분석

    SOTA Features:
        - LRU Cache (동일 코드 재분석 방지)
        - Security limits (max 10MB, AST depth 100)
        - Hash-based cache key
    """

    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
    MAX_AST_DEPTH = 100

    def analyze(self, code: str, file_path: str, language: LanguageSupport) -> CodeContext:
        # Security checks
        if len(code.encode()) > MAX_FILE_SIZE_BYTES:
            raise ValueError("File too large")

        tree = ast.parse(code)

        if self._calculate_ast_depth(tree) > MAX_AST_DEPTH:
            raise ValueError("AST too deep - possible malicious code")

        return CodeContext(
            file_path=file_path,
            ast_depth=ast_depth,
            complexity_score=complexity / 50.0,  # normalize to [0, 1]
            classes=self._extract_classes(tree),
            functions=self._extract_functions(tree),
            imports=self._extract_imports(tree),
        )

    def _calculate_complexity(self, node: ast.AST) -> int:
        """
        Cyclomatic Complexity

        Decision points:
            - if/elif, for/while
            - except
            - and/or
            - comprehensions
            - match/case (Python 3.10+)
        """
```

---

# Part 62. GraphPrunerAdapter (PageRank 기반 Context Pruning)

```python
class GraphPrunerAdapter(IGraphPruner):
    """
    Graph RAG PageRank Pruner
    토큰 예산 내 컨텍스트 최적화
    """

    async def calculate_pagerank(self, nodes, edges, damping=0.85) -> dict[str, float]:
        """
        Power Iteration 방식 PageRank

        M = Transition Matrix (adjacency)
        pr_new = damping * M @ pr + (1 - damping) / n

        max_iter=100, tolerance=1e-6
        """

    async def prune_context(self, nodes, max_tokens=8000, top_k_full=20) -> PrunedContext:
        """
        1. PageRank로 정렬
        2. Top-K 노드는 본문 포함
        3. 나머지는 시그니처만 (10%)
        4. 압축률 계산

        Returns:
            PrunedContext(full_nodes, signature_only_nodes, total_tokens, compression_ratio)
        """
```

---

# Part 63. ReproductionEngineAdapter (Reproduction-First TDD)

```python
class ReproductionEngineAdapter(IReproductionEngine):
    """
    버그 재현 스크립트 생성 및 검증 (TDD)

    테스트 프레임워크 템플릿:
        - pytest (Python)
        - jest (JavaScript)
        - unittest (Python)
    """

    async def generate_reproduction_script(self, issue_description, context_files, tech_stack) -> ReproductionScript:
        """
        1. 테스트 프레임워크 감지
        2. LLM으로 테스트 코드 생성
        3. 예상 실패 패턴 추출 (AttributeError, TypeError 등)
        4. 템플릿 적용
        """

    async def verify_failure(self, script) -> ReproductionResult:
        """버그 재현 확인 (exit_code != 0 && failure_pattern match)"""

    async def verify_fix(self, script) -> ReproductionResult:
        """수정 후 테스트 성공 확인"""
```

---

# Part 64. GuardrailsAIAdapter (정책 기반 검증)

```python
class PolicyLevel(str, Enum):
    LOW = "low"         # 개발: 기본 검증만
    MEDIUM = "medium"   # 일반: 품질 + 보안
    HIGH = "high"       # 민감: 품질 + 보안 + 호환성
    CRITICAL = "critical"  # 프로덕션: 모든 정책 + LLM

class GuardrailsAIAdapter(IGuardrailValidator):
    """
    Features:
        - 정책 기반 검증 (4단계)
        - LLM 기반 검증 (CRITICAL만)
        - 비밀/PII 탐지
        - Breaking Changes 감지
        - Pydantic Fallback
        - 캐싱

    검증:
        - code_quality: 코드 길이, 복잡도
        - security: 비밀, PII, SQL Injection
        - breaking_changes: Public API 변경

    비밀 탐지 패턴:
        - sk-[a-zA-Z0-9]{20,}  → OpenAI API Key
        - ghp_[a-zA-Z0-9]{36}  → GitHub Token
        - AKIA[0-9A-Z]{16}     → AWS Access Key
    """
```

---

# Part 65. DangerousActionGateAdapter (위험 행동 게이트)

```python
class RiskClassifier:
    """
    Risk 분류 패턴

    CRITICAL:
        - rm -rf /
        - curl | bash
        - DROP DATABASE

    HIGH:
        - sudo
        - chmod 777
        - http:// (non-HTTPS)

    MEDIUM:
        - .py, .js 파일 쓰기
        - 코드 생성
    """

class DangerousActionGateAdapter:
    """
    Implements: ActionGatePort

    Features:
        - Risk classification (Low/Med/High/Critical)
        - Human approval workflow
        - Auto-approval rules (whitelist)
        - Blacklist blocking
        - Timeout handling
        - Audit trail
    """

    def request_approval(self, action_type, target, description) -> (ApprovalStatus, reason):
        risk_level = RiskClassifier.classify(action_type, target)

        # Auto-approval check
        if auto_approved:
            return (AUTO_APPROVED, "rule: {rule}")

        # Blacklist check
        if blacklisted:
            return (REJECTED, "Blacklisted")

        # Human approval required
        return (PENDING, "Awaiting approval")
```

---

# Part 66. LicenseComplianceCheckerAdapter

```python
class LicenseComplianceCheckerAdapter:
    """
    SPDX 라이선스 감지 및 정책 시행

    License Categories:
        PERMISSIVE:      MIT, Apache, BSD, ISC
        WEAK_COPYLEFT:   LGPL, MPL
        STRONG_COPYLEFT: GPL
        NETWORK_COPYLEFT: AGPL (viral over network)

    Detection Patterns (SPDX):
        MIT:     "MIT License", "Permission is hereby granted"
        Apache:  "Apache License.*Version 2\.0"
        GPL-3:   "GNU GENERAL PUBLIC LICENSE.*Version 3"
        AGPL-3:  "AGPL-3\.0"
    """

    def detect_license(self, text: str) -> LicenseInfo | None:
        """SPDX 패턴 매칭"""

    def check_compliance(self, license: LicenseInfo) -> LicenseViolation | None:
        """
        정책 위반 검사

        - blocked: BLOCK
        - review_required: REQUIRE_REVIEW
        - unknown + block_unknown: BLOCK
        - allowed: None
        - 기타: WARN
        """

    def scan_dependencies(self, dependencies: dict[str, str]) -> list[LicenseViolation]:
        """의존성 라이선스 일괄 스캔"""
```

---

# Part 67. LangGraphWorkflowAdapter

```python
class LangGraphWorkflowAdapter(IWorkflowEngine):
    """
    LangGraph StateGraph를 사용한 Workflow Orchestration

    원칙:
        - Node에 business logic 직접 작성 금지
        - Node는 WorkflowStep.execute만 호출
        - Domain Model ↔ DTO 변환만 담당
    """

    def _build_graph(self):
        """
        Workflow: Analyze → Plan → Generate → Critic → Test → Heal

        Conditional Edges:
            critic → test/regenerate/done
            test → heal/replan/done
            heal → generate (재시도)
        """

        graph.set_entry_point("analyze")
        graph.add_edge("analyze", "plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "critic")

        graph.add_conditional_edges("critic", _should_test, {...})
        graph.add_conditional_edges("test", _handle_test_result, {...})
        graph.add_edge("heal", "generate")
```

---

# Part 68. PrometheusMetricsAdapter + StrategyGeneratorLLM

## PrometheusMetricsAdapter

```python
class AgentMetrics:
    """Agent 시스템 메트릭"""

    # Agent 실행
    AGENT_TASKS_TOTAL = "agent_tasks_total"
    AGENT_TASK_DURATION_MS = "agent_task_duration_ms"

    # Multi-Agent
    MULTI_AGENT_LOCKS_TOTAL = "multi_agent_locks_total"
    MULTI_AGENT_CONFLICTS_TOTAL = "multi_agent_conflicts_total"
    MULTI_AGENT_HASH_DRIFTS_TOTAL = "multi_agent_hash_drifts_total"

    # Human-in-the-loop
    HITL_APPROVALS_TOTAL = "hitl_approvals_total"
    HITL_REJECTIONS_TOTAL = "hitl_rejections_total"

    # LLM API
    LLM_CALLS_TOTAL = "llm_calls_total"
    LLM_TOKENS_TOTAL = "llm_tokens_total"
    LLM_COST_USD = "llm_cost_usd"
    LLM_LATENCY_MS = "llm_latency_ms"

    # Guardrails / VCS / Workflow
    ...
```

## StrategyGeneratorLLM

```python
class StrategyGeneratorLLM:
    """
    OpenAI Structured Output으로 ToT 전략 생성

    - 실제 코드 포함 (file_changes)
    - JSON 파싱 + Fallback
    - Sample Code 생성 (Null check, SQL Injection 패턴)
    """

    async def generate_strategy(self, problem, context, strategy_type) -> CodeStrategy:
        """
        Prompt → LLM → JSON 파싱 → CodeStrategy

        JSON format:
        {
            "title": "...",
            "description": "...",
            "rationale": "...",
            "confidence": 0.8,
            "file_changes": {
                "path/to/file.py": "COMPLETE file content"
            }
        }
        """
```

---

# Part 69. Safety Domain Models

```python
class SecretType(str, Enum):
    API_KEY, PASSWORD, TOKEN, PRIVATE_KEY, AWS_KEY, GITHUB_TOKEN,
    SLACK_TOKEN, JWT, DATABASE_URL, CREDIT_CARD, SSN, EMAIL, PHONE,
    IP_ADDRESS, HIGH_ENTROPY, CUSTOM

class PIIType(str, Enum):
    NAME, EMAIL, PHONE, SSN, CREDIT_CARD, ADDRESS, DOB, IP_ADDRESS

class LicenseType(str, Enum):
    MIT, APACHE_2, BSD_2, BSD_3, GPL_2, GPL_3, LGPL_2, LGPL_3,
    AGPL_3, MPL_2, EPL_2, ISC, UNLICENSE, PROPRIETARY, UNKNOWN

class RiskLevel(str, Enum):
    LOW, MEDIUM, HIGH, CRITICAL

class ActionType(str, Enum):
    FILE_DELETE, FILE_WRITE, FILE_EXECUTE, NETWORK_REQUEST,
    DATABASE_WRITE, DATABASE_DELETE, SHELL_COMMAND, CODE_GENERATION,
    DEPENDENCY_INSTALL, CREDENTIAL_ACCESS, SYSTEM_CONFIG

class ApprovalStatus(str, Enum):
    PENDING, APPROVED, REJECTED, TIMEOUT, AUTO_APPROVED

class ValidationStage(str, Enum):
    SECRET_SCAN, LICENSE_CHECK, ACTION_GATE
```

---

# Part 70. Beam Search Engine

```python
class BeamSearchEngine:
    """
    병렬 후보 탐색 + top-k 유지

    Args:
        config: BeamConfig(beam_width, max_depth, diversity_penalty, ...)

    Algorithm:
        1. 초기 후보 생성
        2. depth만큼 반복:
            2.1 각 후보를 expand_fn으로 확장 (LLM)
            2.2 evaluate_fn으로 평가 (실행+테스트)
            2.3 top-k 선택 (BeamRanker)
            2.4 조기 종료 조건 확인
        3. 최고 후보 반환
    """

    async def search(self, initial_prompt, expand_fn, evaluate_fn) -> BeamSearchResult:
        for depth in range(max_depth):
            for candidate in current_beam:
                expanded = expand_fn(candidate)  # LLM 호출

            next_beam = self.ranker.select_top_k(next_candidates, evaluate_fn)

            if self._check_early_termination(next_beam):
                break
```

---

# Part 71. Constitutional AI (안전성 규칙)

```python
class Constitution:
    """
    헌법 (규칙 모음)

    Default Rules:
        SEC-001: No hardcoded secrets (CRITICAL)
        SEC-002: No SQL injection (CRITICAL)
        SEC-003: No command injection (CRITICAL)
        QUAL-001: No debug code in production (MEDIUM)
        ...
    """

    @dataclass
    class Rule:
        rule_id: str
        name: str
        description: str
        severity: RuleSeverity  # CRITICAL, HIGH, MEDIUM, LOW
        check_fn: Callable[[str], bool]  # True = 위반

    # 하드코딩 비밀 탐지 (os.getenv는 제외)
    def check_hardcoded_secrets(content: str) -> bool:
        if "os.getenv" in content:
            return False
        patterns = ['password = "', 'api_key = "', 'secret = "']
        return any(p in content.lower() for p in patterns)

    # SQL Injection 탐지
    def check_sql_injection(content: str) -> bool:
        # execute("SELECT * FROM " + user_input) 패턴 감지
```

---

# Part 72. Reward Model + Critic

```python
class RewardModel:
    """
    RL 기반 보상 모델

    보상 계산:
        - compile_success: +0.3
        - test_pass_rate: +0.4 * rate
        - quality_score: +0.3 * score

    범위: [0.0, 1.0]
    """

    def calculate_reward(self, candidate) -> float:
        reward = 0.0
        if candidate.compile_success:
            reward += 0.3
        reward += candidate.test_pass_rate * 0.4
        reward += candidate.quality_score * 0.3
        return max(0.0, min(reward, 1.0))

class PreferenceLearning:
    """Preference 학습 (RLHF 스타일)"""
```

---

# Part 73. Debate Orchestrator (Multi-Agent)

```python
class DebateOrchestrator:
    """
    Multi-Agent 토론 오케스트레이션

    Config:
        num_proposers: 제안자 수
        max_rounds: 최대 라운드

    Flow:
        1. Proposer 에이전트들 생성
        2. 각 라운드: 각 에이전트가 Position 생성
        3. ConsensusBuilder로 합의 도출
        4. 최종 Position 반환
    """

    async def debate_async(self, problem, generate_fn) -> DebateResult:
        for round_num in range(max_rounds):
            for agent in agents:
                position = await agent.generate_position(problem, all_positions)
                round_positions.append(position)

        consensus = self.consensus_builder.build(all_positions)
        return DebateResult(rounds, final_position)
```

---

# Part 74. DeepReasoningOrchestrator (System 2)

```python
class DeepReasoningOrchestrator:
    """
    System 2 깊은 추론 엔진 (~45초)

    Multi-Candidate Strategies:
        - ToT (Tree of Thought)
        - Beam Search
        - o1-style (단일 긴 사고)
        - Debate (Multi-Agent)
        - AlphaCode (대량 샘플링)

    Constitutional AI:
        - 다층 안전 검증
        - Severity-aware checks

    Experience Store v2:
        - 유사 경험 검색
        - 성공률 기반 전략 선택
    """

    @dataclass
    class DeepReasoningRequest:
        task: AgentTask
        config: V8Config
        strategy: ReasoningStrategy | None  # None이면 auto routing

    # Priority: strategy > force_system_2 > auto routing
```

---

# Part 75. UnifiedRouter (LLM 호출 없는 라우팅)

```python
class UnifiedRouter:
    """
    Agent + Retrieval 통합 라우터

    특징:
        - LLM 호출 없음 (Rule 기반)
        -  미만
        - Budget-aware routing

    Ports:
        - IQueryAnalyzer: 복잡도 분석
        - ITopKSelector: Top-K 선택
        - IBudgetSelector: Budget-aware
    """

    @dataclass
    class RoutingPlan:
        intent: str
        complexity: str  # simple/medium/complex
        strategy_path: list[str]
        adaptive_k: int
        budget_ms: int

        # Advanced features
        use_hyde: bool
        use_self_rag: bool
        use_multi_query: bool
        use_cross_encoder: bool

        workflow_mode: str  # fast/standard/deep
```

---

# Part 76. Advanced Cache (Multi-tier + Bloom Filter)

```python
class BloomFilter:
    """
    Bloom Filter (캐시 존재 확인)

    특징:
        - False Positive 가능
        - False Negative 불가능
        - 메모리 효율적
    """

class AdvancedCache:
    """
    SOTA 캐싱 레이어

    Features:
        1. Multi-tier Cache (L1: Local, L2: Redis)
        2. Cache Aside Pattern
        3. TTL & LRU Eviction
        4. Cache Warming
        5. Cache Invalidation
        6. Bloom Filter (False Positive 감소)
        7. Compression (큰 데이터)
        8. Metrics & Monitoring
    """
```

---

# Part 77. Experience Repository (PostgreSQL)

```python
class ExperienceRepository:
    """
    PostgreSQL 기반 경험 저장/검색

    Table: agent_experience
        - problem_description, problem_type
        - strategy_id, strategy_type
        - success, tot_score, reflection_verdict
        - test_pass_rate, graph_impact
        - search_vector (TSVECTOR for Full-Text Search)

    Indexes:
        - idx_exp_problem_type
        - idx_exp_success
        - idx_exp_score
        - GIN index on search_vector
    """

    def search_by_text(self, search_text, limit, lookback_days) -> list[AgentExperience]:
        """Full-Text Search (PostgreSQL TSVECTOR)"""
```

---

# Part 78. Intent Classifier + Task Graph Planner

## Intent Classifier

```python
class IntentClassifier:
    """LLM 기반 Intent 분류"""

    async def classify(self, user_input: str) -> IntentResult:
        prompt = self.prompts.get_intent_prompt(user_input)
        response = await self.llm.complete(prompt, model="gpt-4o-mini", temperature=0.0)
        return IntentResult(intent, confidence, reasoning)
```

## Task Graph Planner

```python
class TaskGraphPlanner:
    """
    ADR-004: Task Decomposition Graph

    책임:
        1. User request → Task 분해
        2. Task 의존성 분석
        3. 실행 계획 생성 (순차/병렬)

    Risk Assessment:
        CRITICAL: Production DB drop, production data deletion
        HIGH: bulk deletion (delete all, rm -rf)
        MEDIUM: Large-scale changes (>10 files)
    """

    DANGEROUS_PATTERNS = [
        "drop", "delete", "remove", "truncate", "destroy",
        "production", "prod", "live", "rm -rf", "format", "wipe"
    ]
```

---

# Part 79. EventBus + CancellationToken

```python
class CancellationToken:
    """
    취소 토큰 (E-4)

    - cancel(): 취소 요청
    - is_cancelled(): 취소 여부
    - on_cancel(callback): 취소 시 콜백 등록
    - check_cancelled(): 취소 시 CancelledError 발생
    """

class EventBus:
    """
    이벤트 버스 (E-2)

    Methods:
        - emit(event): 이벤트 발행
        - stream(): 이벤트 스트리밍 (AsyncIterator)
        - subscribe(callback): 구독자 등록
    """
```

---

# Part 80. Profiler (CPU/Memory/Async)

```python
class Profiler:
    """
    SOTA급 Profiler

    Features:
        1. CPU Profiling (cProfile)
        2. Memory Profiling (tracemalloc)
        3. Async Profiling (asyncio 추적)
        4. Bottleneck Detection (자동 감지)
        5. Flame Graph 생성
        6. Performance Report

    @dataclass
    class ProfileResult:
        function: str
        total_time: float
        calls: int
        cumulative_time: float
        memory_usage: int
        bottleneck_score: float  # 0-100
    """
```

---

# Part 81. LATS Prompts (Generator/Verifier)

```python
class LATSPrompts:
    """
    LATS 프롬프트 모음

    Generator Prompts (창의성 중시):
        GENERATE_NEXT_THOUGHTS: k가지 다른 접근 방법 제안
        GENERATE_COMPLETE_STRATEGY: 완전한 코드 변경 생성

    Verifier Prompts (비판적 평가):
        EVALUATE_THOUGHT: 구체성, 실현 가능성, 논리성, 완전성
        EVALUATE_THOUGHT_STRICT: Devil's Advocate (환각 의심)

    Cross-Model Verification:
        Generator: creative model
        Verifier: critical model (다른 모델)
    """
```

---

# Part 82. FailSafeLayer (Graceful Degradation)

```python
class FailSafeLayer:
    """
    System 2 실패 시 자동 복구

    책임:
        1. 연속 실패 감지 (MAX_CONSECUTIVE_FAILURES = 3)
        2. System 1 강제 폴백
        3. HITL 에스컬레이션
        4. 복구 전략 제안

    원칙:
        - 시스템이 완전히 멈추지 않도록
        - 점진적 복구 (graceful degradation)
        - 명확한 알림 및 로깅

    Cooldown:
        COOLDOWN_PERIOD_MINUTES = 30
    """

    @dataclass
    class FailureHistory:
        consecutive_failures: int
        last_failure_time: datetime
        failure_reasons: list[str]  # 최근 10개
        total_failures: int
        total_attempts: int
```

---

# Part 83. LiteLLMFIMAdapter (Multi-Provider)

```python
class LiteLLMFIMAdapter:
    """
    LiteLLM 기반 FIM Adapter

    지원 엔진:
        - OpenAI: gpt-4o, gpt-4o-mini
        - Codestral: mistral-codestral-latest (코드 특화)
        - DeepSeek: deepseek-coder (코드 특화)
        - Anthropic: claude-* (prefix+suffix concatenation)

    Features:
        - 스트리밍 지원
        - 다중 후보 생성
        - 점수 계산 (log_prob 기반)
        - Fallback 엔진 체인
    """

    ENGINE_MODEL_MAP = {
        FIMEngine.OPENAI: "gpt-4o-mini",
        FIMEngine.CODESTRAL: "codestral-latest",
        FIMEngine.DEEPSEEK: "deepseek/deepseek-coder",
        FIMEngine.ANTHROPIC: "claude-3-5-sonnet-20241022",
    }
```

---

# Part 84. AST Code Transformer (Rename + Extract)

```python
class ASTCodeTransformer:
    """
    AST 기반 코드 변환

    Strategies (OCP 준수):
        1. ASTRenameStrategy: AST + regex 기반 (기본)
        2. RopeRenameStrategy: Rope 기반 (고급)

    Rope Features:
        - 다중 파일 지원
        - Import 자동 업데이트
        - 스코프 인식 rename

    SOLID:
        - S: 코드 변환만 담당
        - O: Strategy Pattern으로 새 변환 추가 용이
        - D: RenameStrategyProtocol 주입
    """
```

---

# Part 85. O1 Engine + Deep Reasoning

```python
class O1Engine:
    """
    OpenAI o1 스타일 추론 엔진

    Components:
        - ReasoningChain: Chain-of-Thought 구축
        - ThoughtDecomposer: 복잡한 문제 분해
        - VerificationLoop: 검증 및 개선

    Flow:
        1. Chain-of-Thought 구축 (answer_fn)
        2. 각 단계 검증 및 개선 (verify_fn, refine_fn)
        3. 최종 답변 합성
    """

    async def reason(self, problem, answer_fn, verify_fn, refine_fn) -> DeepReasoningResult:
        steps = await self.chain_builder.build_chain(problem, answer_fn)

        for step in steps:
            verified_step, verifications = await self.verifier.verify_and_refine(
                step, verify_fn, refine_fn
            )
            verified_steps.append(verified_step)

        return DeepReasoningResult(final_answer, final_code, verified_steps)

class ThoughtDecomposer:
    """
    사고 분해기

    복잡한 문제 → 하위 사고 (재귀적)
    max_depth까지 분해
    """

class VerificationLoop:
    """
    검증 루프

    max_attempts까지 반복:
        1. 답변 생성
        2. 검증 (verify_fn)
        3. 통과 시 반환
        4. 실패 시 개선 (refine_fn)
    """
```

---

# Part 86. TODO / 미구현

| 심각도 | 영역 | 현재 상태 | 필요 작업 |
|--------|------|-----------|-----------|
| **Critical** | Step 5 Semantic Contract | 항상 통과 | Rename 감지 + caller 업데이트 검증 |
| **Critical** | HCGAdapter.query_scope | 빈 리스트 | Query DSL 연동 |
| **High** | ImplicitRenameDetector | AST 파싱 미구현 | deleted/added 함수 추출 |
| **High** | DockerSandboxAdapter | Docker 미구현 | Docker 격리 실행 |
| **Medium** | IRTransactionManager | StubIRBuilder 사용 | LayeredIRBuilder 연동 |
| **Medium** | Oscillation 감지 | diff_lines Jaccard | AST 구조적 비교 |
| **Low** | CoverageAdapter.MC/DC | .coverage 파싱 미구현 | 조건별 True/False 추적 |

---

# Part 87. Agent 연동 현황

```
Agent 모듈 (src/agent)
    │
    ├── domain/
    │   ├── SoftLockManager         # 동시 편집 Lock (Redis/메모리)
    │   ├── ConflictResolver        # 3-Way Merge (git merge-file)
    │   ├── DiffManager             # Unified Diff 생성/파싱
    │   ├── ApprovalManager         # 사용자 승인 (File/Hunk/Line)
    │   ├── PartialCommitter        # Git 부분 커밋 + Shadow Branch
    │   └── AgentCoordinator        # Multi-Agent 조율
    │
    ├── ports/
    │   ├── IGitRepository          # Git 작업 Port
    │   ├── LockManagerProtocol     # Lock 관리 Protocol
    │   └── CASCADE Ports           # IFuzzyPatcher, IReproductionEngine...
    │
    └── contexts/agent_code_editing/
        └── FuzzyPatcherAdapter     # CASCADE Fuzzy Patcher

    ↓ (TODO: 직접 연동 없음)

codegen_loop (src/contexts/codegen_loop)
    │
    ├── ShadowFS (v1/v2)        # 파일 오버레이
    ├── IRTransactionManager    # IR 트랜잭션
    ├── EventBus                # 이벤트 분배
    └── 8-Step Pipeline         # 코드 생성 루프
```

## 통합 흐름 (예상)

```
User Request
    │
    ▼
AgentCoordinator.spawn_agent()
    │
    ├─── SoftLockManager.acquire_lock()
    │
    ▼
CodeGenLoop.run()  (8-Step Pipeline)
    │
    ├─── ShadowFS 트랜잭션 내에서 작업
    │
    ▼
ApprovalManager.request_approval()  (Hunk 단위)
    │
    ▼
PartialCommitter.apply_partial()
    │
    ├─── Shadow branch 생성
    ├─── git apply (→ FuzzyPatcher fallback)
    ├─── git commit
    │
    ▼
ConflictResolver.resolve_3way_merge()  (충돌 시)
    │
    ▼
SoftLockManager.release_lock()
```

---

# Part 88. 참조 알고리즘/논문

| 알고리즘 | 출처 | 사용 위치 |
|----------|------|-----------|
| MVCC | Bernstein & Goodman (1983) | IRTransactionManager, ShadowFS v2 |
| Copy-on-Write | Rosenblum & Ousterhout (1992) | ShadowFSCore |
| Union FS | Pendry & McKusick (1995) | ShadowFSCore |
| OverlayFS | Linux Kernel (2014) | ShadowFS v2 |
| STM | Herlihy & Moss (1993) | IRTransactionManager |
| Git 3-Way Merge | git merge-file | ConflictResolver |
| SequenceMatcher | difflib | FuzzyPatcher, Oscillation |
| Jaccard Similarity | - | OscillationDetector, Rename |
| TOCTOU Prevention | OWASP | PathCanonicalizer |
| **MCTS** | Coulom (2006) | LATS |
| **UCT** | Kocsis & Szepesvari (2006) | LATSNode.ucb() |
| **LATS** | Zhou et al. (2023) | LATSSearchEngine |
| **ToT** | Yao et al. (2023) | ToT Models |
| **Reflexion** | Shinn et al. (2023) | ReflectionJudge |
| **MCDM** | Multi-Criteria Decision Making | ScoringWeights, ReflectionRules |
| **Token Bucket** | Rate Limiting | TokenBucket |
| **Circuit Breaker** | Fowler (2014) | CircuitBreaker |
| **FIM** | Fill-in-the-Middle | FIMRequest/Result |
| **PageRank** | Page & Brin (1998) | IGraphPruner |

---

**문서 최종 업데이트**: 2024-12-13
