# RFC-060: SOTA급 Agent Code Editing 완성

> **Status**: Draft (v5 - Final Master Plan)
> **Created**: 2025-12-26
> **Updated**: 2025-12-26
> **Author**: Claude Opus 4.5
> **Target**: SWE-Bench Verified 50%+ (현재 SOTA: 80.9%)
> **Related**: [RFC-045](../adr/RFC-045-unified-incremental-system.md) (Unified Incremental System)

---

## Executive Summary

Semantica v4는 **두 가지 모드**를 지원하는 SOTA급 코드 에디팅 시스템입니다:

| 모드 | 사용 시나리오 | 특징 |
|------|-------------|------|
| **🤖 Autonomous Mode** | 복잡한 버그 수정, 리팩토링 | 전체 TDD 사이클, 장기 실행 (분~시간) |
| **⚡ Assistant Mode** | 단발성 수정, 빠른 질의응답 | Cursor처럼 빠른 응답 (초~분) |

**v5 핵심 변경**:
1. **두 모드 아키텍처 분리** - 공통 인프라 + 모드별 확장
2. **Git 통합 추가** (P0) - 실제 워크플로우 필수
3. **DirtyIndexManager P2 격하** - ROI 대비 복잡도 높음
4. **Safety Guardrail 범위 조정** - 실용적 수준으로

### 구현 상태 요약 (2025-12-26 검증)

```
┌─────────────────────────────────────────────────────────────────┐
│                    구현 상태 (v5 검증)                          │
├─────────────────────────────────────────────────────────────────┤
│  ✅ 완료 (인프라 65%)                                           │
│  ├── RetrieverV3Orchestrator (Hybrid Search)                    │
│  ├── RRFNormalizer (RRF Fusion)                                 │
│  ├── PyrightAdapter (타입 체크)                                  │
│  ├── Session Memory (3-tier)                                    │
│  ├── ShadowFS (트랜잭션 + 이벤트 버스)                           │
│  ├── Reasoning 10+ (LATS, ToT, Debate, O1/R1 등)                │
│  ├── FuzzyPatcher (git apply + fuzzy matching)                  │
│  └── CodeGenLoop 골격 (8-Step)                                  │
├─────────────────────────────────────────────────────────────────┤
│  ⚠️ 부분 구현 (15%)                                             │
│  ├── HCGAdapter.query_scope() → return []                       │
│  ├── CodeGenLoop Step 5 → return {"valid": True}                │
│  └── DockerSandboxAdapter → 기본 실행만                          │
├─────────────────────────────────────────────────────────────────┤
│  ❌ 미구현 (통합 20%)                                            │
│  ├── ICascadeOrchestrator (TDD 오케스트레이션)                   │
│  ├── SBFL Analyzer (Tarantula)                                  │
│  ├── Static Analysis Gate (Ruff+Pyright+Self-Correct)           │
│  ├── Git Integration (커밋/브랜치/PR)                            │
│  └── LocalCommandAdapter (로컬 터미널)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 두 가지 모드 아키텍처

### 1.1 공통 인프라 (Core)

두 모드가 공유하는 기반 컴포넌트:

```
┌─────────────────────────────────────────────────────────────────┐
│                       Core Infrastructure                        │
├─────────────────────────────────────────────────────────────────┤
│  [Search Layer]                                                  │
│  ├── RetrieverV3Orchestrator (Hybrid: BM25+Vector+Symbol+Graph)  │
│  ├── RRFNormalizer                                               │
│  └── HCGAdapter (query_scope 수정 필요)                          │
├─────────────────────────────────────────────────────────────────┤
│  [Edit Layer]                                                    │
│  ├── FuzzyPatcher                                                │
│  ├── ShadowFS (파일 트랜잭션)                                    │
│  └── Static Analysis Gate (Ruff + Pyright)                       │
├─────────────────────────────────────────────────────────────────┤
│  [Memory Layer]                                                  │
│  ├── Session Memory (Working/Episodic/Semantic)                  │
│  └── Git Integration (커밋 히스토리)                              │
├─────────────────────────────────────────────────────────────────┤
│  [Execution Layer]                                               │
│  ├── LocalCommandAdapter (로컬 터미널)                           │
│  ├── DockerSandboxAdapter (격리 실행)                            │
│  └── CoverageAdapter (pytest-cov)                                │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Autonomous Mode (자율 코딩)

**사용 시나리오**: SWE-Bench 스타일 이슈 해결, 복잡한 리팩토링

```
┌─────────────────────────────────────────────────────────────────┐
│                    Autonomous Mode Pipeline                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Phase 0: Environment Setup (0th Step)                      │ │
│  │  ├── IEnvironmentProvisioner (venv/Docker)                  │ │
│  │  ├── Dependency Conflict Auto-Healing                       │ │
│  │  └── Snapshot for Rollback                                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Phase 1: Localization (버그 위치 특정)                     │ │
│  │  ├── Hybrid Search (RetrieverV3)                            │ │
│  │  ├── SBFL Analyzer (Tarantula 공식)                         │ │
│  │  └── Suspicious Lines 순위화                                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Phase 2: Reproduction (버그 재현)                          │ │
│  │  ├── IReproductionEngine (재현 스크립트 생성)               │ │
│  │  ├── Verify Failure (실패 확인)                             │ │
│  │  └── Expected Failure Pattern 저장                          │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Phase 3: Patch + Verify (수정 + 검증) ← 반복               │ │
│  │  ├── Patch Generation (Temperature 증가)                   │ │
│  │  ├── Static Gate (Ruff → Pyright → Self-Correct)           │ │
│  │  ├── FuzzyPatcher.apply()                                   │ │
│  │  ├── Run Reproduction Script → Pass?                        │ │
│  │  ├── Impact Test Selection (영향 테스트만)                  │ │
│  │  └── Reflexion (실패 시 반성 + 재시도)                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Phase 4: Finalize                                          │ │
│  │  ├── Patch Minimization (불필요 라인 제거)                  │ │
│  │  ├── Git Commit + Branch                                    │ │
│  │  └── PR Draft (선택)                                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Autonomous 전용 컴포넌트**:
- ICascadeOrchestrator (전체 사이클 조율)
- IReproductionEngine (버그 재현)
- SBFL Analyzer (Tarantula)
- IEnvironmentProvisioner (환경 자동 구축)
- Patch Minimization (최소 수정)

### 1.3 Assistant Mode (Cursor-like)

**사용 시나리오**: 빠른 코드 수정, 설명 요청, 단발성 리팩토링

```
┌─────────────────────────────────────────────────────────────────┐
│                    Assistant Mode Pipeline                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request: "이 함수에서 None 체크 추가해줘"                   │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Step 1: Context Retrieval (1-2초)                          │ │
│  │  ├── Hybrid Search (관련 코드)                               │ │
│  │  ├── HCG Query (Callers/Callees)                            │ │
│  │  └── Recent Edit History                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Step 2: Patch Generation (2-5초)                           │ │
│  │  ├── LLM Generate Patch                                     │ │
│  │  ├── Static Gate (Ruff + Pyright)                           │ │
│  │  └── Diff Preview 생성                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Step 3: User Approval                                      │ │
│  │  ├── Diff 표시 (Terminal/IDE)                               │ │
│  │  ├── [Y] Apply / [N] Reject / [E] Edit                      │ │
│  │  └── 승인 시 → FuzzyPatcher.apply()                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Step 4: Post-Apply (선택)                                  │ │
│  │  ├── Quick Test Run (관련 테스트만)                         │ │
│  │  └── RFC-045 트리거 (인덱스 갱신)                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Assistant 핵심 원칙**:
1. **빠른 응답**: 5초 이내 Diff 표시
2. **사용자 승인**: 항상 적용 전 확인
3. **최소 오버헤드**: SBFL, Reproduction 생략
4. **선택적 검증**: 테스트 실행은 옵션

---

## 2. SOTA 워크플로우 상세 (Autonomous Mode)

### 2.1 Phase 1: Localization (버그 위치 특정)

#### 2.1.1 Hybrid Search (기존 인프라 활용)

```python
# RetrieverV3Orchestrator 호출
search_results, intent, metrics, _ = await retriever.search(
    repo_id="local",
    snapshot_id="HEAD",
    query=issue_description,
    limit=20,
)
```

#### 2.1.2 SBFL Analyzer (Tarantula 공식)

```python
class SBFLAnalyzer:
    """
    Spectrum-Based Fault Localization

    Tarantula 공식:
    Suspiciousness(s) = (failed(s)/total_failed) /
                        ((failed(s)/total_failed) + (passed(s)/total_passed))
    """

    async def analyze(
        self,
        failing_tests: list[str],
        passing_tests: list[str],
    ) -> list[SuspiciousLine]:
        # 1. 각 테스트 실행 + 커버리지 수집
        failed_cov = await self._collect_coverage(failing_tests)
        passed_cov = await self._collect_coverage(passing_tests)

        # 2. 라인별 의심도 계산
        suspicious = []
        for file_path, lines in self._merge(failed_cov, passed_cov).items():
            for line in lines:
                ef = self._count(failed_cov, file_path, line)  # 실패 테스트 실행 횟수
                ep = self._count(passed_cov, file_path, line)  # 성공 테스트 실행 횟수

                if ef > 0:
                    susp = self._tarantula(ef, len(failing_tests),
                                           ep, len(passing_tests))
                    suspicious.append(SuspiciousLine(file_path, line, susp))

        return sorted(suspicious, key=lambda x: x.suspiciousness, reverse=True)

    def _tarantula(self, ef, tf, ep, tp) -> float:
        if tf == 0:
            return 0.0
        failed_ratio = ef / tf
        passed_ratio = ep / tp if tp > 0 else 0
        denom = failed_ratio + passed_ratio
        return failed_ratio / denom if denom > 0 else 0.0
```

### 2.2 Phase 2: Static Analysis Gate

```python
class StaticAnalysisGate:
    """
    패치 검증 파이프라인: Ruff → Pyright → LLM Self-Correct

    테스트 실행 전 0.1초 만에 문법/타입 오류 차단
    """

    async def validate_and_fix(
        self,
        file_path: str,
        content: str,
        max_attempts: int = 2,
    ) -> tuple[str, bool]:
        current = content

        for attempt in range(max_attempts + 1):
            # 1. Ruff (Linter) - 0.05초
            ruff_result = await self._run_ruff(file_path, current)
            if ruff_result.has_fixes:
                current = ruff_result.fixed_content

            # 2. Pyright (Type Check) - 0.1초
            pyright_result = await self.pyright.check(file_path, current)
            if pyright_result.passed:
                return current, True

            # 3. LLM Self-Correct (실패 시)
            if attempt < max_attempts:
                current = await self._self_correct(current, pyright_result.errors)

        return current, False
```

### 2.3 Phase 3: Impact Test Selection

```python
class ImpactTestSelector:
    """
    Code Graph 기반 영향 테스트 선택

    전체 테스트 대신 영향받는 테스트만 실행하여 시간 절약
    """

    async def select(
        self,
        modified_files: list[str],
        hcg: HCGAdapter,
    ) -> list[str]:
        affected_tests = set()

        for file_path in modified_files:
            # 1. 수정된 함수의 Callers 조회
            callers = await hcg.query_callers(file_path)

            # 2. Caller 중 테스트 파일 식별
            for caller in callers:
                if self._is_test_file(caller.file_path):
                    affected_tests.add(caller.file_path)

            # 3. 직접 import하는 테스트 추가
            importers = await hcg.query_importers(file_path)
            for imp in importers:
                if self._is_test_file(imp.file_path):
                    affected_tests.add(imp.file_path)

        return list(affected_tests)

    def _is_test_file(self, path: str) -> bool:
        return "test" in path.lower() or path.endswith("_test.py")
```

### 2.4 Phase 4: Patch Minimization (Occam's Razor)

```python
class PatchMinimizer:
    """
    테스트 통과를 유지하는 최소 패치 추출

    불필요한 스타일 수정, 리팩토링 제거 → PR 승인률 상승
    """

    async def minimize(
        self,
        patch: dict[str, str],
        test_script: str,
        sandbox: ISandboxPort,
    ) -> dict[str, str]:
        minimized = {}

        for file_path, diff in patch.items():
            hunks = self._parse_hunks(diff)
            essential = []

            # 각 hunk를 제거해보고 테스트 통과 확인
            for i, hunk in enumerate(hunks):
                test_patch = self._without_hunk(hunks, i)
                await self._apply_temp(file_path, test_patch)

                result = await sandbox.run(test_script)
                await self._rollback()

                if result.failed:
                    # 이 hunk 없으면 실패 → 필수
                    essential.append(hunk)

            minimized[file_path] = self._combine(essential)

        return minimized
```

---

## 3. RFC-045 (증분 업데이트) 연동 전략

### 3.1 연동 방식 분류

| 유형 | 트리거 | 설명 | 우선순위 |
|------|--------|------|----------|
| **A. Post-Commit** | ShadowFS 커밋 후 | 패치 완료 → FileChangedEvent → 인덱스 갱신 | **P0** |
| **B. External Event** | Git Pull, 사용자 수정 | FileWatcher → RFC-045 트리거 | **P1** |
| **C. Dirty Indexing** | 패치 도중 | 임시 변경사항 가상 인덱싱 | **P2** (복잡도 높음) |

### 3.2 Post-Commit 연동 (P0)

```
RFC-060 (Agent Code Editing)
    │
    ├── FuzzyPatcher.apply_patch()
    │       │
    │       ▼
    └── ShadowFS.commit_transaction()
                │
                ▼ (FileChangedEvent)
RFC-045 (Unified Incremental System)
    │
    ├── ChangeTracker.detect_changes()
    ├── FingerprintManager.prune()
    ├── IncrementalOrchestrator.build()
    │       │
    │       ▼
    └── AtomicChunkSwapper.swap()
```

**구현**: ShadowFS 이벤트 버스 이미 존재 → 연결만 필요

### 3.3 Dirty Indexing (P2 - 선택적)

```python
class DirtyIndexManager:
    """
    [P2] 패치 도중 가상 인덱스 업데이트

    복잡한 리팩토링 시 수정 중간에도 변경된 구조 검색 가능
    """

    def __init__(self, base_index: Index):
        self.base = base_index
        self.dirty_overlay: dict[str, IRDocument] = {}

    def apply_dirty(self, file_path: str, new_content: str):
        """임시 변경사항 가상 적용"""
        ir = self._parse_to_ir(new_content)
        self.dirty_overlay[file_path] = ir

    def search(self, query: str) -> list[SearchResult]:
        """Base + Dirty Overlay 통합 검색"""
        base_results = self.base.search(query)

        # Dirty된 파일은 오버레이에서 검색
        for path, ir in self.dirty_overlay.items():
            if self._matches(ir, query):
                # Base 결과 대체
                base_results = self._replace(base_results, path, ir)

        return base_results

    def commit(self):
        """트랜잭션 커밋 → RFC-045로 전달"""
        for path, ir in self.dirty_overlay.items():
            emit(FileChangedEvent(path, ir))
        self.dirty_overlay.clear()
```

**결론**: P2로 격하. 대부분의 패치는 1-2개 파일이므로 Post-Commit으로 충분.

---

## 4. 로컬 콘솔 실행 인프라

### 4.1 LocalCommandAdapter

```python
class LocalCommandAdapter(ICommandExecutor):
    """
    사용자의 실제 쉘(zsh, bash)에서 명령 실행

    Safety:
    - 블랙리스트 기반 위험 명령 차단
    - 위험 점수 표시 (사용자 판단)
    - 파괴적 작업 전 승인 요청
    """

    BLACKLIST = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r"dd\s+if=.*of=/dev/",
        r"mkfs\.",
        r">\s*/dev/sd",
    ]

    APPROVAL_REQUIRED = [
        r"rm\s+-rf",
        r"git\s+push\s+.*--force",
        r"git\s+reset\s+--hard",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM.*WHERE\s+1=1",
    ]

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 60.0,
        require_approval: bool | None = None,
    ) -> CommandResult:
        # 1. 블랙리스트 체크
        if self._is_blacklisted(command):
            raise DangerousCommandError(f"차단된 명령: {command}")

        # 2. 승인 필요 여부 체크
        if require_approval is None:
            require_approval = self._needs_approval(command)

        if require_approval:
            approved = await self._request_approval(command)
            if not approved:
                return CommandResult(status="rejected", message="사용자가 거부함")

        # 3. 실행
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )

        return CommandResult(
            exit_code=proc.returncode,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
        )

    async def _request_approval(self, command: str) -> bool:
        """터미널에서 사용자 승인 요청"""
        print(f"\n⚠️  위험한 명령 감지:")
        print(f"   {command}")
        response = input("실행하시겠습니까? [y/N]: ")
        return response.lower() == "y"
```

### 4.2 Git Integration (P0)

```python
class GitAdapter:
    """
    Git 작업 통합

    - 커밋 생성
    - 브랜치 관리
    - PR 초안 생성 (gh CLI)
    """

    async def commit(
        self,
        files: list[str],
        message: str,
        auto_stage: bool = True,
    ) -> str:
        if auto_stage:
            await self.executor.execute(f"git add {' '.join(files)}")

        result = await self.executor.execute(
            f'git commit -m "{message}"'
        )
        return self._parse_commit_hash(result.stdout)

    async def create_branch(self, name: str, checkout: bool = True) -> None:
        cmd = f"git checkout -b {name}" if checkout else f"git branch {name}"
        await self.executor.execute(cmd)

    async def create_pr_draft(
        self,
        title: str,
        body: str,
        base: str = "main",
    ) -> str:
        """gh CLI로 PR 초안 생성"""
        result = await self.executor.execute(
            f'gh pr create --draft --title "{title}" --body "{body}" --base {base}'
        )
        return self._parse_pr_url(result.stdout)
```

### 4.3 Undo/Rollback 메커니즘

```python
class RollbackManager:
    """
    패치 롤백 관리

    1. ShadowFS 트랜잭션 롤백 (커밋 전)
    2. Git revert (커밋 후)
    3. Snapshot restore (환경 전체)
    """

    async def rollback_patch(self, patch_id: str) -> bool:
        """최근 패치 롤백"""
        patch = self.history.get(patch_id)

        if not patch.committed:
            # ShadowFS 트랜잭션 롤백
            await self.shadowfs.rollback_transaction(patch.txn_id)
        else:
            # Git revert
            await self.git.revert(patch.commit_hash)

        return True

    async def rollback_to_snapshot(self, snapshot_id: str) -> bool:
        """환경 전체 스냅샷 복원"""
        return await self.env_provisioner.restore(snapshot_id)
```

---

## 5. 우선순위 분류 (v5 Final)

### 5.1 P0 (Critical - 2주)

| 항목 | 작업 내용 | 공수 |
|------|----------|------|
| **HCGAdapter.query_scope** | IR 기반 키워드 매칭 | 2-3일 |
| **Static Analysis Gate** | Ruff + Pyright + Self-Correct | 3-4일 |
| **ICascadeOrchestrator** | TDD 사이클 통합 | 4-5일 |
| **Git Integration** | 커밋/브랜치/기본 롤백 | 2-3일 |
| **CodeGenLoop Step 5** | Semantic Contract 검증 | 2-3일 |

### 5.2 P1 (High - 4주)

| 항목 | 작업 내용 | 공수 |
|------|----------|------|
| **SBFL Analyzer** | Tarantula 공식, CoverageAdapter 확장 | 3-4일 |
| **IReproductionEngine** | 버그 재현 스크립트 | 3-4일 |
| **LocalCommandAdapter** | 로컬 터미널 + Safety | 3일 |
| **ImpactTestSelector** | 영향 테스트 선별 | 2-3일 |
| **IEnvironmentProvisioner** | venv/Docker 환경 | 4-5일 |
| **Progress Streaming** | 장기 실행 진행률 | 2일 |

### 5.3 P2 (Medium - 선택적)

| 항목 | 작업 내용 |
|------|----------|
| Patch Minimization | 불필요 라인 제거 |
| DirtyIndexManager | 가상 증분 인덱싱 |
| Multi-Candidate Patches | Temperature 증가 + Early Exit |
| PR Draft 자동 생성 | gh CLI 연동 |
| Cost Tracking | LLM API 비용 표시 |

---

## 6. 마일스톤 (v5 Final)

| Phase | 기간 | 산출물 | 모드 |
|-------|------|--------|------|
| **Phase 0** | 2주 | Core: HCGAdapter, StaticGate, Git, CascadeOrchestrator | 공통 |
| **Phase 1** | 2주 | Autonomous: SBFL, Reproduction, EnvProvisioner | Autonomous |
| **Phase 1.5** | 1주 | Assistant: LocalCommandAdapter, Progress Streaming | Assistant |
| **Phase 2** | 2주 | Optimization: ImpactTestSelector, Patch Minimization | 공통 |

**총 예상 기간**:
- **MVP (Assistant Mode)**: 3주
- **Full (Autonomous Mode)**: 6-7주

---

## 7. 성공 지표

### 7.1 기능 완성도

| 지표 | 현재 | MVP 후 | Full 후 |
|------|------|--------|---------|
| Core Port 구현율 | 14% | 85% | 100% |
| Autonomous Pipeline | 0% | 30% | 100% |
| Assistant Response Time | N/A | < 5초 | < 3초 |
| Git Integration | 없음 | 기본 | 완전 |

### 7.2 벤치마크

| 지표 | MVP 목표 | Full 목표 |
|------|----------|----------|
| SWE-Bench Lite | 25%+ | 40%+ |
| 평균 비용 | < $2.00/이슈 | < $1.00/이슈 |
| Assistant 응답 시간 | < 5초 | < 3초 |

---

## 8. 리스크 및 완화

| 리스크 | 영향 | 완화 방안 |
|--------|------|----------|
| HCG Query DSL 미숙 | 중간 | 단순 키워드 매칭으로 시작 |
| 로컬 환경 다양성 | 높음 | Docker 우선 + 점진적 로컬 지원 |
| SBFL 테스트 의존성 | 높음 | 테스트 없으면 Hybrid Search fallback |
| Safety 완벽성 불가 | 중간 | 블랙리스트 + 사용자 신뢰 기반 |
| LLM 비용 | 중간 | Early Exit + 모델 라우팅 |

---

## 9. 결론

### Semantica v4가 특별한 이유

1. **두 가지 모드**: Autonomous (복잡한 문제) + Assistant (빠른 수정)
2. **실제 환경 기반**: 로컬 콘솔에서 실제 문제 해결
3. **TDD 워크플로우**: 재현 → 정적 검증 → 패치 → 영향 테스트
4. **실시간 동기화**: 수정 후 즉시 인덱스 갱신 (RFC-045)
5. **최소 침습**: Patch Minimization으로 프로덕션 품질

### 다음 단계

1. **P0 시작**: HCGAdapter.query_scope 구현 (2-3일)
2. **Static Gate**: Ruff + Pyright 통합 (3-4일)
3. **Git Integration**: 기본 커밋/롤백 (2-3일)
4. **ICascadeOrchestrator**: TDD 사이클 통합 (4-5일)

---

## Appendix A: 패키지 구조 및 의존 관계

### A.1 현재 패키지 구조

```
packages/
├── codegraph-shared/      # 공통 유틸, 설정 (의존성 없음)
├── codegraph-engine/      # IR, 파싱, 인덱싱 (tree-sitter, tantivy)
├── codegraph-search/      # 검색 파이프라인 (→ engine, shared)
├── codegraph-analysis/    # 코드 분석 (→ engine)
├── codegraph-runtime/     # LLM, CodeGen, Session (→ engine, analysis)
├── codegraph-ml/          # ML 배치 작업
├── codegraph-taint/       # Taint 분석
└── codegraph-rust/        # Rust 확장 (codegraph-ir, codegraph-core)
```

### A.2 현재 의존 관계

```
                    ┌─────────────────┐
                    │ codegraph-shared│  ← 의존성 없음 (Base)
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────────┐ ┌────────────┐ ┌────────────┐
     │codegraph-engine│ │   (외부)   │ │   (외부)   │
     │ IR, Parser     │ │ tree-sitter│ │  tantivy   │
     └───────┬────────┘ └────────────┘ └────────────┘
             │
    ┌────────┴────────┬─────────────────┐
    ▼                 ▼                 ▼
┌──────────┐   ┌────────────┐   ┌────────────────┐
│ analysis │   │   search   │   │    runtime     │
│ 코드분석  │   │ Hybrid검색 │   │ LLM, CodeGen   │
└──────────┘   └────────────┘   └────────────────┘
```

### A.3 제안: Agent 패키지 신설 vs Runtime 확장

**Option 1: codegraph-runtime 확장 (현재 방식)**

```
codegraph-runtime/
├── agent_code_editing/     # 자율 코딩 (기존)
│   ├── adapters/cascade/   # FuzzyPatcher
│   └── ...
├── codegen_loop/           # CodeGen Pipeline
├── session_memory/         # 3-tier Memory
└── llm_arbitration/        # LLM 라우팅
```

- **장점**: 기존 구조 유지, 추가 패키지 불필요
- **단점**: runtime이 비대해짐

**Option 2: codegraph-agent 신설 (권장)**

```
codegraph-agent/            # 🆕 신규 패키지
├── autonomous/             # Autonomous Mode
│   ├── cascade_orchestrator.py
│   ├── reproduction_engine.py
│   ├── sbfl_analyzer.py
│   └── patch_minimizer.py
├── assistant/              # Assistant Mode
│   ├── quick_edit.py
│   └── progress_streamer.py
├── shared/                 # 공통
│   ├── static_gate.py
│   ├── git_adapter.py
│   └── local_command.py
└── ports/                  # Port 정의
    └── cascade.py          # apps/orchestrator에서 이동
```

- **장점**: 책임 분리, 독립 배포 가능
- **단점**: 새 패키지 생성 필요

### A.4 권장 의존 관계 (Option 2)

```
                    ┌─────────────────┐
                    │ codegraph-shared│
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────────┐ ┌────────────┐ ┌────────────┐
     │codegraph-engine│ │ analysis   │ │   search   │
     └───────┬────────┘ └─────┬──────┘ └─────┬──────┘
             │                │              │
             └────────────────┼──────────────┘
                              ▼
                    ┌─────────────────┐
                    │ codegraph-runtime│  (LLM, Session, CodeGen)
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
           ┌────────────────┐ ┌────────────────┐
           │ codegraph-agent│ │codegraph-incr  │  ← 🆕 RFC-045
           │ (RFC-060)      │ │(증분 업데이트)  │
           └────────────────┘ └────────────────┘
```

### A.5 증분 업데이트 (RFC-045) 위치

**핵심 질문**: 증분 업데이트는 어디에?

| 위치 | 장점 | 단점 |
|------|------|------|
| `codegraph-engine` | 인덱싱 로직과 가까움 | Engine이 비대해짐 |
| `codegraph-shared` | 모든 패키지에서 접근 | 공유 패키지 오염 |
| **`codegraph-incremental`** (신설) | 독립성, 명확한 책임 | 새 패키지 |
| `codegraph-runtime` | 기존 ShadowFS와 연계 | Runtime 비대 |

**권장**: `codegraph-incremental` 신설 또는 `codegraph-engine/incremental/` 서브모듈

```
codegraph-engine/
├── code_foundation/        # 기존 IR, Parser
├── multi_index/            # 기존 인덱싱
└── incremental/            # 🆕 RFC-045
    ├── change_tracker.py
    ├── fingerprint_manager.py
    ├── incremental_orchestrator.py
    └── atomic_swapper.py
```

### A.6 Agent ↔ Incremental 연동

```
┌─────────────────────────────────────────────────────────────────┐
│                    codegraph-agent (RFC-060)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CascadeOrchestrator                                             │
│       │                                                          │
│       ├── FuzzyPatcher.apply_patch()                             │
│       │       │                                                  │
│       │       ▼                                                  │
│       └── ShadowFS.commit()  ──────────────────────┐             │
│                                                    │             │
└────────────────────────────────────────────────────│─────────────┘
                                                     │
                                                     ▼ (이벤트)
┌─────────────────────────────────────────────────────────────────┐
│                codegraph-engine/incremental (RFC-045)            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  IncrementalOrchestrator.on_file_changed(event)                  │
│       │                                                          │
│       ├── ChangeTracker.detect()                                 │
│       ├── FingerprintManager.prune()                             │
│       ├── IRBuilder.rebuild_affected()                           │
│       └── AtomicSwapper.commit()                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**의존 방향**: `agent` → (이벤트) → `engine/incremental`
- Agent는 Incremental을 직접 import 안 함
- ShadowFS 이벤트 버스로 느슨한 결합

---

## Appendix B: 기존 구현 위치

| 컴포넌트 | 경로 | 상태 |
|----------|------|------|
| RetrieverV3Orchestrator | `packages/codegraph-search/.../v3/orchestrator.py` | ✅ |
| RRFNormalizer | `packages/codegraph-search/.../v3/rrf_normalizer.py` | ✅ |
| PyrightAdapter | `packages/codegraph-engine/.../external_analyzers/pyright_adapter.py` | ✅ |
| FuzzyPatcher | `packages/codegraph-runtime/.../agent_code_editing/.../fuzzy_patcher.py` | ✅ |
| ShadowFS | `packages/codegraph-runtime/.../shadowfs/` | ✅ |
| Session Memory | `packages/codegraph-runtime/.../session_memory/` | ✅ |
| HCGAdapter | `packages/codegraph-runtime/.../hcg_adapter.py` | ⚠️ TODO |
| CoverageAdapter | `packages/codegraph-runtime/.../coverage_adapter.py` | ⚠️ SBFL 확장 필요 |
| CASCADE Ports | `apps/orchestrator/.../ports/cascade.py` | Port만 정의 |

---

## Appendix C: 모드별 컴포넌트 요약

```
┌─────────────────────────────────────────────────────────────────┐
│                        Component Map                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [공통 Core]                                                     │
│  ├── RetrieverV3 (✅)                                            │
│  ├── FuzzyPatcher (✅)                                           │
│  ├── ShadowFS (✅)                                               │
│  ├── Static Gate (P0)                                           │
│  ├── HCGAdapter (P0 수정)                                        │
│  └── Git Integration (P0)                                       │
│                                                                  │
│  [Autonomous 전용]                                               │
│  ├── ICascadeOrchestrator (P0)                                  │
│  ├── SBFL Analyzer (P1)                                         │
│  ├── IReproductionEngine (P1)                                   │
│  ├── IEnvironmentProvisioner (P1)                               │
│  ├── ImpactTestSelector (P2)                                    │
│  └── Patch Minimization (P2)                                    │
│                                                                  │
│  [Assistant 전용]                                                │
│  ├── LocalCommandAdapter (P1)                                   │
│  ├── Progress Streaming (P1)                                    │
│  └── Quick Test Runner (P2)                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix D: Indexing Pipeline Rust Optimization

### D.1 현재 상태 (2025-12-26 벤치마크)

**벤치마크 결과** (Pydantic 129,434 LOC):

```
Repository: pydantic (393 files, 129,434 LOC)
총 소요 시간: 10.25s
처리량: 12,622 LOC/sec

Phase Breakdown:
  Phase 1 (L1 ∥ L3): 8.21s (80.0%)  ← 병렬 실행
  Phase 2 (L2):      2.05s (20.0%)
  Phase 3 (L4):      0.00s (skipped)

결과:
  - 노드: 41,897개
  - 엣지: 127,333개
  - 청크: 16,501개
```

**리포트 위치**:
- `benchmark/artifacts/reports/pydantic/2025-12-26/031157_dag_report.txt`
- 전체 성능 분석: `tools/benchmark/artifacts/INDEXING_PIPELINE_BENCHMARK.md`

### D.2 아키텍처 전환

```
┌────────────────────────────────────────────────────────────────┐
│              OLD: LayeredIRBuilder (Monolithic)                │
├────────────────────────────────────────────────────────────────┤
│  구조: Monolithic                                               │
│  실행: 순차 (L1 → L2 → L3 → L4)                                 │
│  속도: ~17.78s (small repo 추정)                                │
│  최적화: 제한적 (전체를 한 번에 최적화해야 함)                     │
└────────────────────────────────────────────────────────────────┘

                          ⬇️  전환 완료 ✅

┌────────────────────────────────────────────────────────────────┐
│            NEW: Task-Engine DAG (Microservices)                │
├────────────────────────────────────────────────────────────────┤
│  구조: Microservices ✅                                         │
│  실행: 병렬 DAG (L1 ∥ L3) → L2 → L4 ✅                          │
│  속도: 10.25s (129k LOC 실측) ✅                                │
│  최적화: Job별 독립 최적화 가능 ✅                               │
│                                                                │
│  Handlers:                                                     │
│  ├── IRBuildHandler      (L1: IR Build)                        │
│  ├── ChunkBuildHandler   (L2: Chunk)                           │
│  ├── LexicalIndexHandler (L3: Lexical)                         │
│  └── VectorIndexHandler  (L4: Vector)                          │
└────────────────────────────────────────────────────────────────┘
```

### D.3 Rust 최적화 로드맵

#### Phase 1: IRBuildHandler → Rust IR Adapter (P0)

**현재 구현**:

```python
# packages/codegraph-shared/.../handlers/ir_handler.py
async def execute(self, payload: dict[str, Any]) -> JobResult:
    builder = LayeredIRBuilder(project_root=repo_path, profiler=None)
    result = await builder.build(files=files, config=config)
    # ↑ Python LayeredIRBuilder (느림)
```

**최적화 후**:

```python
# RustIRAdapter로 직접 호출
async def execute(self, payload: dict[str, Any]) -> JobResult:
    from codegraph_ir import process_python_files_parallel
    
    # Rust로 직접 병렬 처리 (PyO3)
    ir_documents = process_python_files_parallel(
        files=[str(f) for f in files],
        repo_id=repo_id,
        num_workers=parallel_workers,
        semantic_tier=semantic_tier.value,
    )
    # ↑ Rust (Rayon parallel) 직접 호출
```

**예상 효과**:
- L1 Phase: 8.21s → **~1.5s** (5.5x faster)
- GIL 제거로 완전한 병렬화
- PyDict 변환 오버헤드 제거

#### Phase 2: ChunkBuildHandler → Rust Chunk (P0)

**현재 구현**:

```python
# packages/codegraph-shared/.../handlers/chunk_handler.py
async def execute(self, payload: dict[str, Any]) -> JobResult:
    builder = ChunkBuilder()
    for file_path, ir_doc in ir_documents.items():
        for node in ir_doc.nodes:
            chunk = builder.create_chunk(node)  # Python loop
            chunks.append(chunk)
```

**최적화 후**:

```python
# Rust Chunk Generator
async def execute(self, payload: dict[str, Any]) -> JobResult:
    from codegraph_core import generate_chunks_parallel
    
    chunks = generate_chunks_parallel(
        ir_documents=ir_documents,  # Rust struct로 전달
        num_workers=parallel_workers,
    )
    # ↑ Rust (Rayon) parallel chunk generation
```

**예상 효과**:
- L2 Phase: 2.05s → **~0.3s** (6.8x faster)
- Python loop → Rust parallel iteration
- hashlib (C) → Rust crypto (native)

#### Phase 3: 전체 DAG 최적화 (P1)

```
┌─────────────────────────────────────────────────────────────┐
│              Optimized DAG Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1 (Parallel): 1.7s                                   │
│  ├── L1 (Rust IR):     1.5s  ← Rust parallel              │
│  └── L3 (Tantivy):     0.2s  ← Already Rust               │
│                                                             │
│  Phase 2 (Sequential): 0.3s                                 │
│  └── L2 (Rust Chunk):  0.3s  ← Rust parallel              │
│                                                             │
│  Phase 3 (Sequential): 0.5s                                 │
│  └── L4 (msgpack):     0.5s  ← Already C/Rust             │
│                                                             │
│  Total: ~2.5s (from 10.25s)  🚀 4.1x faster!               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### D.4 구현 우선순위

| 우선순위 | 작업 | 예상 시간 | 예상 효과 |
|---------|------|----------|----------|
| **P0** | IRBuildHandler → Rust IR | 2-3일 | 5.5x (8.21s → 1.5s) |
| **P0** | ChunkBuildHandler → Rust Chunk | 1-2일 | 6.8x (2.05s → 0.3s) |
| **P1** | 전체 DAG 프로파일링 | 1일 | 병목 식별 |
| **P1** | PyO3 바인딩 최적화 | 2일 | 데이터 복사 최소화 |
| **P2** | Zero-copy 전략 | 3일 | 메모리 효율 |

### D.5 기술 스택

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline.rs
use rayon::prelude::*;
use pyo3::prelude::*;

#[pyfunction]
pub fn process_python_files_parallel(
    files: Vec<String>,
    repo_id: String,
    num_workers: usize,
    semantic_tier: String,
) -> PyResult<PyObject> {
    // Rayon ThreadPool 설정
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(num_workers)
        .build()
        .unwrap();
    
    // 병렬 IR 생성 (GIL 없음!)
    let ir_docs: Vec<IRDocument> = pool.install(|| {
        files.par_iter()
            .map(|file| build_ir_for_file(file, &semantic_tier))
            .collect()
    });
    
    // PyO3로 Python 반환 (최소 복사)
    Python::with_gil(|py| {
        Ok(ir_docs.into_py(py))
    })
}
```

### D.6 성능 목표

**129k LOC 레포지토리 기준**:

| 단계 | 현재 | 목표 | 개선율 |
|------|------|------|--------|
| L1 IR Build | 8.21s | 1.5s | 5.5x ⚡ |
| L2 Chunk | 2.05s | 0.3s | 6.8x ⚡ |
| L3 Lexical | 0.2s | 0.2s | 1.0x (이미 Rust) |
| L4 Vector | ~0.5s | 0.5s | 1.0x (이미 C/Rust) |
| **Total** | **10.25s** | **~2.5s** | **4.1x** 🚀 |

**처리량**:
- 현재: 12,622 LOC/sec
- 목표: **~52,000 LOC/sec** (4.1x faster)

### D.7 참고 자료

- **벤치마크 스크립트**: `tools/benchmark/bench_indexing_dag.py`
- **성능 문서**: `tools/benchmark/artifacts/INDEXING_PIPELINE_BENCHMARK.md`
- **Handler 위치**: `packages/codegraph-shared/codegraph_shared/infra/jobs/handlers/`
- **Rust 코어**: `packages/codegraph-rust/codegraph-core/`

**핵심 교훈**:
1. ✅ **DAG 전환 완료** - Microservices 패턴 적용
2. ✅ **병렬화 성공** - L1 ∥ L3 동시 실행
3. 🚀 **Rust 최적화 대기** - 각 Handler를 Rust로 교체하면 4.1x 향상 예상
4. 📊 **실측 기반** - 129k LOC에서 검증된 수치
