# RFC-045: Unified Incremental Update System

| 항목 | 내용 |
|------|------|
| **상태** | Draft |
| **작성일** | 2025-12-26 |
| **작성자** | Semantica Team |
| **관련 RFC** | RFC-031 (Stable ID), RFC-039 (L0 Cache), ADR-003 (Workflow) |

## 1. Executive Summary

현재 Semantica v2의 증분 업데이트 관련 컴포넌트들은 개별적으로 SOTA급이지만, **78개의 중복 클래스**와 **패키지 간 분산**으로 인해 통합 오케스트레이션이 부족한 상태입니다.

본 RFC는 `codegraph-incremental` 패키지를 신설하여 모든 증분 관련 기술을 통합하고, **MVCC 트랜잭션 기반의 원자적 파이프라인**을 구축하는 것을 목표로 합니다.

### 핵심 목표
1. **중복 제거**: 33개 중복 클래스 통합
2. **원자성 보장**: IRTransactionManager 기반 ACID 파이프라인
3. **의미론적 가지치기**: Semantic Pruning으로 불필요한 재빌드 70% 감소
4. **자가 치유**: ConsistencyChecker 기반 드리프트 자동 복구

---

## 2. Background & Problem Statement

### 2.1 현재 상태 분석

#### 구현 완료된 SOTA급 컴포넌트

| 컴포넌트 | 위치 | 상태 |
|----------|------|------|
| FileWatcher + Debouncer | `analysis_indexing/` | ✅ Production-ready |
| IRTransactionManager (MVCC) | `runtime/shadowfs/` | ✅ SOTA |
| Body Hash Service | `semantic_ir/body_hash_service.py` | ✅ 구현됨 |
| Stable ID (RFC-031) | `ir/id_strategy.py` | ✅ 구현됨 |
| ConsistencyChecker | `multi_index/consistency_checker.py` | ✅ 구현됨 |
| GraphSimulator (Speculative) | `reasoning_engine/speculative/` | ✅ SOTA |
| Compaction Scheduler | `lexical/compaction/scheduler.py` | ✅ 구현됨 |
| Distributed Lock | `cache/distributed_lock.py` | ✅ 구현됨 |
| WorkflowStateMachine | `apps/orchestrator/workflow/` | ✅ 구현됨 |

#### 문제점

**1. 심각한 중복 (33개 클래스)**
```
CacheEntry: 8곳에 정의
LRUCache: 4곳에 정의
DiffHunk: 3곳에 정의
IncrementalIRBuilder: 2곳에 정의 (다른 역할, 같은 이름)
DistributedLock: 2곳에 정의
```

**2. apps/orchestrator ↔ packages 간 78개 중복**
- `FuzzyPatcherAdapter`, `ArbitrationEngine`, `AuditStore` 등 핵심 클래스가 복제됨

**3. 통합 오케스트레이션 부재**
- 개별 컴포넌트는 우수하나 연결하는 파이프라인 없음
- 원자적 커밋 보장 메커니즘 부족

**4. 누락된 SOTA 기능**
- Semantic Pruning (의존성 전파 중단)
- Identity Migration (심볼 이동 추적)
- Self-Healing (자동 복구) 완성
- Vector Index Compaction

---

## 3. Proposed Solution

### 3.1 신규 패키지: `codegraph-incremental`

```
packages/codegraph-incremental/
└── codegraph_incremental/
    ├── __init__.py
    │
    ├── core/                         # 도메인 모델 & 포트
    │   ├── models.py                 # ChangeSet, Delta, RebuildPlan
    │   ├── ports.py                  # IChangeDetector, IBuilder, ICache
    │   ├── events.py                 # ChangeEvent, CommitEvent, RollbackEvent
    │   └── errors.py                 # IncrementalError, TransactionError
    │
    ├── detection/                    # Stage 1: 변경 감지
    │   ├── file_watcher.py           # ← analysis_indexing/file_watcher.py
    │   ├── watcher_debouncer.py      # ← analysis_indexing/watcher_debouncer.py
    │   ├── git_detector.py           # Git diff 기반 감지
    │   ├── hash_detector.py          # Content hash 기반 감지
    │   └── composite_detector.py     # 복합 감지기
    │
    ├── semantics/                    # Stage 2: 의미론적 분석 (신규)
    │   ├── fingerprint_manager.py    # 시그니처 해시 기반 Pruning
    │   ├── identity_tracker.py       # 심볼 이동/이름 변경 추적
    │   ├── affected_calculator.py    # 영향 범위 계산
    │   └── pruning_engine.py         # 의존성 전파 중단
    │
    ├── tracking/                     # 상태 추적
    │   ├── change_tracker.py         # ← incremental/change_tracker.py
    │   ├── file_state.py             # 파일 상태 관리
    │   └── dependency_graph.py       # 의존성 그래프
    │
    ├── parsing/                      # 파싱 (중복 통합)
    │   ├── diff_parser.py            # ← 3곳 통합
    │   ├── diff_hunk.py              # DiffHunk 모델
    │   ├── edit_calculator.py        # Tree-sitter Edit 변환
    │   └── incremental_parser.py     # ← 2곳 통합
    │
    ├── builders/                     # Stage 4: 빌더
    │   ├── file_builder.py           # ← incremental/incremental_builder.py (이름 변경)
    │   ├── ir_delta_builder.py       # ← ir/incremental.py (이름 변경)
    │   ├── chunk_builder.py          # ← chunk/incremental.py
    │   ├── semantic_builder.py       # ← semantic_ir/incremental_updater.py
    │   └── protocol.py               # IIncrementalBuilder 인터페이스
    │
    ├── transaction/                  # Stage 3 & 5: 트랜잭션 (핵심)
    │   ├── manager.py                # ← shadowfs/ir_transaction_manager.py
    │   ├── state.py                  # TransactionState (MVCC)
    │   ├── snapshot.py               # FileSnapshot
    │   ├── conflict_registry.py      # ← conflict_registry.py
    │   └── graph_transaction.py      # Graph DB 트랜잭션
    │
    ├── shadowfs/                     # ShadowFS (Buffer Layer)
    │   ├── core.py                   # ← shadowfs/core.py (통합)
    │   ├── unified.py                # UnifiedShadowFS
    │   ├── event_bus.py              # 이벤트 버스
    │   └── plugins/
    │       └── incremental_plugin.py
    │
    ├── cache/                        # 캐시 계층
    │   ├── hierarchy.py              # HierarchicalCache (L0-L3)
    │   ├── l0_metadata.py            # 파일 메타데이터
    │   ├── l1_memory.py              # ← cache_global.py
    │   ├── l2_redis.py               # Redis (optional)
    │   ├── l3_disk.py                # ← semantic_cache.py
    │   └── invalidation.py           # 의존성 기반 무효화
    │
    ├── indexing/                     # 인덱싱
    │   ├── incremental_indexer.py    # ← multi_index/incremental_indexer.py
    │   ├── tombstone.py              # 삭제 추적
    │   └── batch_processor.py        # 배치 처리
    │
    ├── compaction/                   # Stage 6: 정리
    │   ├── scheduler.py              # ← lexical/compaction/scheduler.py
    │   ├── delta_merger.py           # 델타 병합
    │   ├── vector_compactor.py       # Vector DB 세그먼트 병합 (신규)
    │   └── gc.py                     # Garbage Collection
    │
    ├── consistency/                  # 일관성 관리 (신규 강화)
    │   ├── checker.py                # ← consistency_checker.py
    │   ├── drift_detector.py         # 드리프트 감지
    │   ├── self_healer.py            # 자동 복구 (신규)
    │   └── verification.py           # 검증 로직
    │
    ├── lock/                         # 분산 잠금
    │   ├── distributed_lock.py       # ← 2곳 통합
    │   ├── lock_key_generator.py
    │   └── noop_lock.py              # 테스트용
    │
    ├── jobs/                         # Job 관리
    │   ├── orchestrator.py           # ← handlers/orchestrator.py
    │   ├── models.py                 # JobState, JobStatus 통합
    │   ├── checkpoint.py             # 체크포인트
    │   └── retry.py                  # 재시도 로직
    │
    ├── pipeline/                     # 통합 파이프라인 (핵심)
    │   ├── orchestrator.py           # IncrementalOrchestrator
    │   ├── stages.py                 # 6단계 Stage 정의
    │   ├── strategies.py             # FULL/PARTIAL/MINIMAL
    │   └── metrics.py                # 성능 메트릭
    │
    └── config.py                     # 중앙화된 설정
```

### 3.2 통합 파이프라인 설계

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        IncrementalOrchestrator                              │
│                    (WorkflowStateMachine + TransactionManager)              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    ▼                                ▼                                ▼
┌─────────┐                    ┌─────────┐                      ┌─────────┐
│ Trigger │                    │ Trigger │                      │ Trigger │
│  File   │                    │ Shadow  │                      │   Git   │
│ Watcher │                    │   FS    │                      │  Event  │
└────┬────┘                    └────┬────┘                      └────┬────┘
     │                              │                                │
     └──────────────────────────────┼────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 1: DETECT (감지)                                                       │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│ │  FileWatcher    │  │  GitDetector    │  │  HashDetector   │              │
│ └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
│          └────────────────────┼────────────────────┘                        │
│                               ▼                                             │
│                    ┌─────────────────────┐                                  │
│                    │  WatcherDebouncer   │ (300ms debounce, 5s batch)       │
│                    └──────────┬──────────┘                                  │
│                               ▼                                             │
│                         ChangeSet { added, modified, deleted, renamed }     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 2: ANALYZE & PRUNE (분석 및 가지치기) ⭐ 핵심                           │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      AffectedCalculator                                 │ │
│ │  - Call Graph 기반 영향 범위 계산                                        │ │
│ │  - BFS 탐색 (depth limit)                                               │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      FingerprintManager (신규)                          │ │
│ │  - signature_hash 비교: 함수 시그니처가 같으면 전파 중단                   │ │
│ │  - body_hash 비교: 본문이 같으면 스킵                                     │ │
│ │  - 🎯 목표: 불필요한 재빌드 70% 감소                                      │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      IdentityTracker (신규)                             │ │
│ │  - 파일 이동 감지 (Git similarity + content hash)                        │ │
│ │  - 심볼 이름 변경 추적 (FQN lifecycle)                                    │ │
│ │  - ID Migration: 기존 인덱스 재사용                                       │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│                      RebuildPlan { strategy, files, symbols }               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 3: ISOLATE (격리 및 트랜잭션 시작)                                      │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      DistributedLock                                    │ │
│ │  - Redis 기반 (TTL 300s, 60s 자동 갱신)                                  │ │
│ │  - Lock key: repo_id:snapshot_id                                        │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      IRTransactionManager                               │ │
│ │  - txn_id 생성                                                          │ │
│ │  - MVCC Snapshot 캡처                                                    │ │
│ │  - TransactionState 격리                                                 │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│                         TransactionContext { txn_id, snapshot, state }      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 4: BUILD (병렬 빌드)                                                   │
│                                                                             │
│  ┌──────────────┐                                                          │
│  │ WorkerPool   │ (msgpack protocol, 5-10x faster)                         │
│  └──────┬───────┘                                                          │
│         │                                                                   │
│    ┌────┴────┬────────────┬────────────┐                                   │
│    ▼         ▼            ▼            ▼                                   │
│ ┌──────┐ ┌──────┐    ┌──────┐    ┌──────┐                                  │
│ │  L1  │ │  L2  │    │  L3  │    │  L4  │                                  │
│ │  IR  │ │Chunk │    │Lexical    │Vector│                                  │
│ │Build │ │Build │    │Index │    │Index │                                  │
│ └──┬───┘ └──┬───┘    └──┬───┘    └──┬───┘                                  │
│    │        │           │           │                                       │
│    └────────┴───────────┴───────────┘                                       │
│                    ▼                                                        │
│         TransactionState { ir_cache, chunks, indexes }                      │
│         (실제 DB에 쓰지 않고 임시 저장)                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 5: COMMIT (원자적 커밋)                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      ConflictRegistry                                   │ │
│ │  - 충돌 여부 최종 확인                                                    │ │
│ │  - Strategy: SKIP / QUEUE / CANCEL_OLD / LAST_WRITE_WINS                │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│                      ┌───────────────┐                                      │
│                      │ 충돌 없음?    │                                      │
│                      └───────┬───────┘                                      │
│                     Yes      │      No                                      │
│              ┌───────────────┴───────────────┐                              │
│              ▼                               ▼                              │
│    ┌─────────────────┐             ┌─────────────────┐                      │
│    │ txn.commit()    │             │ txn.rollback()  │                      │
│    │ - Graph DB 반영 │             │ - 상태 폐기     │                      │
│    │ - Vector DB 반영│             │ - AutoRetryLoop │                      │
│    │ - Lexical 반영  │             └─────────────────┘                      │
│    └─────────────────┘                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Stage 6: CLEANUP (정리 및 검증)                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      ConsistencyChecker                                 │ │
│ │  - 인덱스 간 일관성 검증 (샘플링)                                         │ │
│ │  - Drift 감지                                                           │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      SelfHealer (신규)                                  │ │
│ │  - 불일치 발견 시 해당 부분만 자동 재빌드                                  │ │
│ │  - 백그라운드 부분 풀 빌드                                                │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │                      Compaction (백그라운드)                            │ │
│ │  - Lexical: 세그먼트 병합                                                │ │
│ │  - Vector: Qdrant 최적화 (신규)                                          │ │
│ │  - SnapshotGC: 오래된 스냅샷 정리                                         │ │
│ └────────────────────────────┬────────────────────────────────────────────┘ │
│                              ▼                                              │
│                      CacheInvalidation + Metrics                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 핵심 구현: IncrementalOrchestrator

```python
# codegraph_incremental/pipeline/orchestrator.py

from enum import Enum
from dataclasses import dataclass
from typing import Protocol

class PipelineStage(Enum):
    DETECT = "detect"
    ANALYZE = "analyze"
    ISOLATE = "isolate"
    BUILD = "build"
    COMMIT = "commit"
    CLEANUP = "cleanup"

class RebuildStrategy(Enum):
    FULL = "full"          # 전체 재빌드 (>50 files)
    PARTIAL = "partial"    # 영향받는 파일만 (5-50 files)
    MINIMAL = "minimal"    # 변경된 심볼만 (<5 files)

@dataclass
class PipelineResult:
    success: bool
    strategy: RebuildStrategy
    files_processed: int
    files_skipped: int  # Pruning으로 스킵된 파일
    elapsed_ms: float
    metrics: dict

class IncrementalOrchestrator:
    """
    통합 증분 파이프라인 오케스트레이터.

    WorkflowStateMachine과 IRTransactionManager를 결합하여
    6단계 원자적 파이프라인을 실행합니다.
    """

    def __init__(
        self,
        # Detection
        file_watcher: IFileWatcher,
        git_detector: IGitDetector,
        debouncer: IDebouncer,
        # Semantics
        fingerprint_manager: IFingerprintManager,
        identity_tracker: IIdentityTracker,
        affected_calculator: IAffectedCalculator,
        # Transaction
        lock: IDistributedLock,
        txn_manager: ITransactionManager,
        conflict_registry: IConflictRegistry,
        # Builders
        ir_builder: IIncrementalBuilder,
        chunk_builder: IIncrementalBuilder,
        lexical_indexer: IIncrementalIndexer,
        vector_indexer: IIncrementalIndexer,
        # Cleanup
        consistency_checker: IConsistencyChecker,
        self_healer: ISelfHealer,
        compactor: ICompactor,
        # Config
        config: IncrementalConfig,
    ):
        self.watcher = file_watcher
        self.git_detector = git_detector
        self.debouncer = debouncer
        self.fingerprint = fingerprint_manager
        self.identity = identity_tracker
        self.affected = affected_calculator
        self.lock = lock
        self.txn = txn_manager
        self.conflicts = conflict_registry
        self.builders = {
            "L1_IR": ir_builder,
            "L2_CHUNK": chunk_builder,
            "L3_LEXICAL": lexical_indexer,
            "L4_VECTOR": vector_indexer,
        }
        self.checker = consistency_checker
        self.healer = self_healer
        self.compactor = compactor
        self.config = config
        self._metrics = PipelineMetrics()

    async def execute(
        self,
        trigger: TriggerEvent,
        strategy: RebuildStrategy = RebuildStrategy.PARTIAL,
    ) -> PipelineResult:
        """
        6단계 증분 파이프라인 실행.

        Args:
            trigger: 트리거 이벤트 (FileWatcher, Git, ShadowFS)
            strategy: 빌드 전략 (AUTO면 자동 결정)

        Returns:
            PipelineResult: 실행 결과
        """
        start_time = time.perf_counter()

        try:
            # Stage 1: DETECT
            change_set = await self._stage_detect(trigger)
            if change_set.is_empty():
                return PipelineResult(success=True, files_processed=0, ...)

            # Stage 2: ANALYZE & PRUNE
            rebuild_plan = await self._stage_analyze(change_set)
            self._metrics.record("files_pruned", rebuild_plan.pruned_count)

            # 전략 결정
            strategy = self._determine_strategy(rebuild_plan, strategy)

            # Stage 3: ISOLATE
            async with self.lock.acquire(rebuild_plan.repo_id, rebuild_plan.snapshot_id):
                async with self.txn.begin() as txn_ctx:
                    try:
                        # Stage 4: BUILD
                        build_results = await self._stage_build(txn_ctx, rebuild_plan, strategy)

                        # Stage 5: COMMIT
                        await self._stage_commit(txn_ctx, build_results)

                    except Exception as e:
                        await txn_ctx.rollback()
                        raise

            # Stage 6: CLEANUP (트랜잭션 외부)
            await self._stage_cleanup(rebuild_plan)

            elapsed = (time.perf_counter() - start_time) * 1000
            return PipelineResult(
                success=True,
                strategy=strategy,
                files_processed=rebuild_plan.file_count,
                files_skipped=rebuild_plan.pruned_count,
                elapsed_ms=elapsed,
                metrics=self._metrics.snapshot(),
            )

        except Exception as e:
            self._metrics.record("pipeline_error", str(e))
            raise

    async def _stage_detect(self, trigger: TriggerEvent) -> ChangeSet:
        """Stage 1: 변경 감지"""
        if trigger.type == TriggerType.FILE_WATCHER:
            raw_events = await self.watcher.get_events()
            return await self.debouncer.process(raw_events)
        elif trigger.type == TriggerType.GIT:
            return await self.git_detector.detect(trigger.base_commit, trigger.head_commit)
        elif trigger.type == TriggerType.SHADOWFS:
            return trigger.change_set
        else:
            raise ValueError(f"Unknown trigger type: {trigger.type}")

    async def _stage_analyze(self, change_set: ChangeSet) -> RebuildPlan:
        """Stage 2: 분석 및 가지치기 (핵심)"""
        # 1. 영향 범위 계산
        affected_files = await self.affected.calculate(
            changed=change_set.all_files,
            call_graph=self._get_call_graph(),
        )

        # 2. Fingerprint 기반 Pruning ⭐
        pruned_files = set()
        for file in affected_files:
            if await self.fingerprint.can_skip(file):
                pruned_files.add(file)

        rebuild_files = affected_files - pruned_files

        # 3. Identity 추적 (이동/이름변경)
        migrations = await self.identity.track_migrations(change_set.renamed)

        return RebuildPlan(
            files=rebuild_files,
            pruned_count=len(pruned_files),
            migrations=migrations,
            change_set=change_set,
        )

    async def _stage_build(
        self,
        txn_ctx: TransactionContext,
        plan: RebuildPlan,
        strategy: RebuildStrategy,
    ) -> BuildResults:
        """Stage 4: 병렬 빌드"""
        # 전략에 따른 빌드 범위 결정
        if strategy == RebuildStrategy.MINIMAL:
            # L1 (IR)만 빌드
            ir_result = await self.builders["L1_IR"].build(plan.files, txn_ctx)
            return BuildResults(ir=ir_result)

        # PARTIAL/FULL: 병렬 빌드
        async with asyncio.TaskGroup() as tg:
            ir_task = tg.create_task(self.builders["L1_IR"].build(plan.files, txn_ctx))
            lexical_task = tg.create_task(self.builders["L3_LEXICAL"].build(plan.files, txn_ctx))

        ir_result = ir_task.result()

        # L2는 L1 완료 후
        chunk_result = await self.builders["L2_CHUNK"].build(plan.files, txn_ctx, ir=ir_result)

        # L4는 L2 완료 후
        vector_result = await self.builders["L4_VECTOR"].build(plan.files, txn_ctx, chunks=chunk_result)

        return BuildResults(
            ir=ir_result,
            chunks=chunk_result,
            lexical=lexical_task.result(),
            vector=vector_result,
        )

    async def _stage_commit(self, txn_ctx: TransactionContext, results: BuildResults):
        """Stage 5: 원자적 커밋"""
        # 충돌 확인
        conflict = await self.conflicts.check(txn_ctx.txn_id)
        if conflict:
            if conflict.strategy == ConflictStrategy.CANCEL_OLD:
                await self.conflicts.cancel_old(conflict.old_job_id)
            elif conflict.strategy == ConflictStrategy.SKIP:
                raise ConflictSkipError(conflict)

        # 커밋 실행
        await txn_ctx.commit()

    async def _stage_cleanup(self, plan: RebuildPlan):
        """Stage 6: 정리 및 검증"""
        # 1. 일관성 검증 (샘플링)
        report = await self.checker.check(plan.repo_id, sample_rate=0.1)

        # 2. 드리프트 발견 시 자동 복구
        if report.has_drift:
            await self.healer.heal(report.drifted_files)

        # 3. 백그라운드 컴팩션 스케줄
        if self.compactor.should_run():
            asyncio.create_task(self.compactor.run_background())

    def _determine_strategy(
        self,
        plan: RebuildPlan,
        requested: RebuildStrategy,
    ) -> RebuildStrategy:
        """최적 전략 자동 결정"""
        if requested != RebuildStrategy.PARTIAL:
            return requested

        file_count = len(plan.files)
        if file_count < 5:
            return RebuildStrategy.MINIMAL
        elif file_count <= 50:
            return RebuildStrategy.PARTIAL
        else:
            return RebuildStrategy.FULL
```

### 3.4 신규 컴포넌트: FingerprintManager

```python
# codegraph_incremental/semantics/fingerprint_manager.py

class FingerprintManager:
    """
    Semantic Pruning을 위한 Fingerprint 관리자.

    함수의 시그니처 해시가 변경되지 않았다면,
    해당 함수를 참조하는 상위 의존성의 재빌드를 중단합니다.

    이 기술 하나로 대규모 프로젝트의 재빌드 범위를 70% 이상 줄일 수 있습니다.
    """

    def __init__(
        self,
        body_hash_service: BodyHashService,
        signature_store: ISignatureStore,
        cache: ICache,
    ):
        self.body_hash = body_hash_service
        self.signatures = signature_store
        self.cache = cache

    async def can_skip(self, file_path: str) -> bool:
        """
        해당 파일의 재빌드를 스킵할 수 있는지 판단.

        조건:
        1. 파일의 모든 함수 시그니처가 이전과 동일
        2. 또는 본문만 변경되고 시그니처는 동일 (private 함수)

        Returns:
            True if 재빌드 불필요
        """
        # 캐시 확인
        cache_key = f"fingerprint:{file_path}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached.can_skip

        # 이전 시그니처 로드
        old_signatures = await self.signatures.get(file_path)
        if not old_signatures:
            return False  # 신규 파일

        # 현재 시그니처 계산
        new_signatures = await self._compute_signatures(file_path)

        # 비교
        for func_id, new_sig in new_signatures.items():
            old_sig = old_signatures.get(func_id)
            if not old_sig:
                return False  # 신규 함수

            # 시그니처 해시 비교 (이름, 파라미터, 리턴 타입)
            if new_sig.signature_hash != old_sig.signature_hash:
                return False  # 시그니처 변경됨 → 상위 의존성 영향

        # 모든 시그니처가 동일 → 스킵 가능
        await self.cache.set(cache_key, FingerprintResult(can_skip=True))
        return True

    async def get_changed_signatures(self, file_path: str) -> set[str]:
        """시그니처가 변경된 함수 ID 반환"""
        old_signatures = await self.signatures.get(file_path)
        new_signatures = await self._compute_signatures(file_path)

        changed = set()
        for func_id, new_sig in new_signatures.items():
            old_sig = old_signatures.get(func_id)
            if not old_sig or new_sig.signature_hash != old_sig.signature_hash:
                changed.add(func_id)

        return changed
```

### 3.5 신규 컴포넌트: IdentityTracker

```python
# codegraph_incremental/semantics/identity_tracker.py

class IdentityTracker:
    """
    심볼 정체성 추적기.

    파일 이동이나 이름 변경을 '삭제 후 생성'이 아닌
    '위치 변경'으로 인식하여 기존 인덱스를 재사용합니다.
    """

    def __init__(
        self,
        content_hasher: IContentHasher,
        fqn_resolver: IFQNResolver,
        similarity_threshold: float = 0.85,
    ):
        self.hasher = content_hasher
        self.fqn = fqn_resolver
        self.threshold = similarity_threshold

    async def track_migrations(
        self,
        renamed: dict[str, str],  # {old_path: new_path}
    ) -> list[IdentityMigration]:
        """
        파일 이동/이름 변경에 대한 ID 마이그레이션 계획 생성.

        Returns:
            마이그레이션 목록 (old_id → new_id 매핑)
        """
        migrations = []

        for old_path, new_path in renamed.items():
            # 1. 파일 내용 유사도 확인
            old_hash = await self.hasher.hash(old_path)
            new_hash = await self.hasher.hash(new_path)

            if old_hash == new_hash:
                # 완전 동일 → 단순 이동
                migrations.append(IdentityMigration(
                    type=MigrationType.MOVE,
                    old_path=old_path,
                    new_path=new_path,
                    confidence=1.0,
                ))
            else:
                # 내용 변경됨 → 심볼별 매칭
                symbol_migrations = await self._match_symbols(old_path, new_path)
                migrations.extend(symbol_migrations)

        return migrations

    async def _match_symbols(
        self,
        old_path: str,
        new_path: str,
    ) -> list[IdentityMigration]:
        """심볼 레벨 매칭"""
        old_symbols = await self.fqn.get_symbols(old_path)
        new_symbols = await self.fqn.get_symbols(new_path)

        migrations = []
        matched_new = set()

        for old_sym in old_symbols:
            best_match = None
            best_score = 0.0

            for new_sym in new_symbols:
                if new_sym.id in matched_new:
                    continue

                score = self._compute_similarity(old_sym, new_sym)
                if score > best_score and score >= self.threshold:
                    best_match = new_sym
                    best_score = score

            if best_match:
                matched_new.add(best_match.id)
                migrations.append(IdentityMigration(
                    type=MigrationType.RENAME if old_sym.name != best_match.name else MigrationType.MOVE,
                    old_id=old_sym.id,
                    new_id=best_match.id,
                    confidence=best_score,
                ))

        return migrations
```

### 3.6 신규 컴포넌트: SelfHealer

```python
# codegraph_incremental/consistency/self_healer.py

class SelfHealer:
    """
    증분 드리프트 자동 복구기.

    증분 업데이트가 반복되면 물리적 인덱스(Vector DB)와
    논리적 상태(Graph) 사이에 미세한 드리프트가 발생할 수 있습니다.

    이 컴포넌트는 유휴 시간에 백그라운드로 부분 풀 빌드를 수행하여
    일관성을 복구합니다.
    """

    def __init__(
        self,
        full_builder: IFullBuilder,
        incremental_builder: IIncrementalBuilder,
        scheduler: IBackgroundScheduler,
        config: SelfHealConfig,
    ):
        self.full_builder = full_builder
        self.incremental_builder = incremental_builder
        self.scheduler = scheduler
        self.config = config

    async def heal(self, drifted_files: set[str]) -> HealResult:
        """
        드리프트된 파일들을 복구.

        전략:
        1. 파일 수가 적으면 (< threshold) 즉시 재빌드
        2. 파일 수가 많으면 백그라운드 스케줄
        """
        if len(drifted_files) <= self.config.immediate_threshold:
            return await self._heal_immediate(drifted_files)
        else:
            return await self._schedule_background_heal(drifted_files)

    async def _heal_immediate(self, files: set[str]) -> HealResult:
        """즉시 복구"""
        results = []
        for file in files:
            result = await self.incremental_builder.rebuild_full(file)
            results.append(result)

        return HealResult(
            healed_count=len(results),
            failed_count=sum(1 for r in results if not r.success),
            mode="immediate",
        )

    async def _schedule_background_heal(self, files: set[str]) -> HealResult:
        """백그라운드 스케줄"""
        job_id = await self.scheduler.schedule(
            task=BackgroundHealTask(files=files),
            priority=Priority.LOW,
            delay_seconds=self.config.background_delay,
        )

        return HealResult(
            healed_count=0,
            scheduled_job_id=job_id,
            mode="background",
        )

    async def run_periodic_verification(self):
        """
        주기적 무작위 샘플링 검증.

        전체 파일 중 일부를 무작위로 선택하여
        풀 빌드 결과와 증분 결과를 비교합니다.
        """
        while True:
            await asyncio.sleep(self.config.verification_interval)

            # 무작위 샘플링
            all_files = await self._get_all_indexed_files()
            sample = random.sample(all_files, min(len(all_files), self.config.sample_size))

            # 풀 빌드 결과와 비교
            drifted = []
            for file in sample:
                if await self._check_drift(file):
                    drifted.append(file)

            if drifted:
                await self.heal(set(drifted))
```

---

## 4. Migration Plan

### Phase 0: Dead Code 정리 (Week 1)

| 작업 | 파일 | 액션 |
|------|------|------|
| `parsing/incremental.py` | DiffHunk, DiffParser 중복 | 제거 |
| `parsing/incremental_parser.py` | 유일 구현 유지 | 리팩토링 |
| 미사용 imports | 전체 | 정리 |

### Phase 1: codegraph-core 추출 (Week 2-3)

공용 모델/예외/포트를 `codegraph-core` 패키지로 추출:

```
CacheEntry (8곳) → codegraph_core/cache/entry.py
LRUCache (4곳) → codegraph_core/cache/lru.py
DiffHunk (3곳) → codegraph_core/diff/hunk.py
Patch (5곳) → codegraph_core/patch/models.py
DistributedLock (2곳) → codegraph_core/lock/distributed.py
```

### Phase 2: codegraph-incremental 생성 (Week 4-6)

1. **패키지 생성 및 구조 설정**
2. **기존 코드 이동** (import 경로 유지하며 점진적 마이그레이션)
3. **IncrementalOrchestrator 구현**
4. **신규 컴포넌트 구현**:
   - FingerprintManager
   - IdentityTracker
   - SelfHealer

### Phase 3: 파이프라인 통합 (Week 7-8)

1. **Stage 1-6 연결**
2. **IRTransactionManager와 StateMachine 통합**
3. **테스트 작성**

### Phase 4: apps/orchestrator 정리 (Week 9-10)

1. **78개 중복 클래스 → packages import로 교체**
2. **의존성 업데이트**
3. **통합 테스트**

---

## 5. Performance Targets

| 지표 | 현재 | 목표 | 개선 |
|------|------|------|------|
| 재빌드 파일 수 | 100% 영향 범위 | 30% (Pruning) | **70% 감소** |
| 증분 빌드 시간 (100 files) | ~10s | ~3s | **3x 빠름** |
| 메모리 사용량 | 높음 (중복) | 낮음 | **40% 감소** |
| 드리프트 복구 | 수동 | 자동 | **100% 자동화** |

---

## 6. Success Criteria

1. **중복 제거**: 33개 → 0개
2. **원자성**: 모든 증분 업데이트가 ACID 보장
3. **Pruning 효율**: 불필요한 재빌드 70% 감소
4. **자가 치유**: 드리프트 자동 감지 및 복구
5. **테스트 커버리지**: 80% 이상

---

## 7. Risks & Mitigations

| 리스크 | 영향 | 완화 전략 |
|--------|------|-----------|
| 대규모 마이그레이션 | 기존 기능 파손 | 점진적 마이그레이션 + Feature flag |
| 성능 저하 | 파이프라인 오버헤드 | 벤치마크 기반 최적화 |
| 복잡성 증가 | 유지보수 어려움 | 명확한 레이어 분리 + 문서화 |

---

## 8. Open Questions

1. **Cross-repo 의존성**: 모노레포 지원 범위?
2. **Predictive Prefetch**: 구현 우선순위?
3. **Vector Compaction**: Qdrant 네이티브 기능 vs 자체 구현?

---

## 9. Advanced Features (보완 사항)

### 9.1 Incremental Lineage & Debuggability (추적 가능성)

증분 업데이트는 "왜 이 파일이 재빌드되었는가?" 혹은 "왜 스킵되었는가?"를 디버깅하기 어렵습니다.

#### DecisionLog (결정 로그)

```python
# codegraph_incremental/observability/decision_log.py

@dataclass
class PruningDecision:
    """Pruning 결정 근거 기록"""
    file_path: str
    decision: Literal["REBUILD", "SKIP", "PARTIAL"]
    reason: str  # e.g., "signature_hash_match", "body_only_change"
    old_hash: str | None
    new_hash: str | None
    affected_by: list[str]  # 어떤 파일의 변경으로 영향받았는지
    timestamp: datetime

class LineageStore:
    """
    증분 업데이트의 결정 근거를 저장하는 저장소.

    나중에 인덱싱 오류 발생 시 추적의 근거로 활용합니다.
    """

    async def record_decision(self, decision: PruningDecision) -> None:
        """결정 기록"""

    async def get_file_history(self, file_path: str, limit: int = 100) -> list[PruningDecision]:
        """특정 파일의 결정 히스토리 조회"""

    async def explain_skip(self, file_path: str, txn_id: str) -> str:
        """왜 스킵되었는지 설명 생성"""
```

#### Pipeline Tracer (OpenTelemetry 통합)

```python
# codegraph_incremental/observability/tracer.py

class PipelineTracer:
    """
    6단계 전 과정의 성능 및 결정 근거 로깅.

    OpenTelemetry Trace ID로 하나의 변경 이벤트가
    Detect부터 Cleanup까지 흘러가는 전 과정을 추적합니다.
    """

    def __init__(self, exporter: ITraceExporter):
        self.exporter = exporter

    @contextmanager
    def trace_stage(self, stage: PipelineStage, context: dict) -> TraceSpan:
        """스테이지 단위 추적"""
        span = self.exporter.start_span(
            name=f"incremental.{stage.value}",
            attributes=context,
        )
        try:
            yield span
        finally:
            span.end()

    def tag_pruning_reason(self, span: TraceSpan, file: str, reason: str):
        """Pruning 이유 태깅 (Jaeger에서 확인 가능)"""
        span.set_attribute(f"pruning.{file}", reason)
```

---

### 9.2 Resource Quota & Backpressure (자원 제어)

대규모 리팩토링(예: 폴더 이름 변경) 시 수천 개의 이벤트가 동시에 발생합니다.

#### ResourceManager (동적 병렬도 조절)

```python
# codegraph_incremental/pipeline/resource_manager.py

class ResourceManager:
    """
    시스템 자원에 따른 동적 병렬도 조절.

    CPU/Memory 부하에 따라 WorkerPool의 병렬도를 조절합니다.
    """

    def __init__(
        self,
        max_workers: int = 8,
        memory_threshold_mb: int = 4096,
        cpu_threshold_percent: float = 80.0,
    ):
        self.max_workers = max_workers
        self.memory_threshold = memory_threshold_mb
        self.cpu_threshold = cpu_threshold_percent
        self._semaphore = asyncio.Semaphore(max_workers)

    async def get_available_workers(self) -> int:
        """현재 가용 워커 수 계산"""
        memory_usage = psutil.virtual_memory().percent
        cpu_usage = psutil.cpu_percent()

        if memory_usage > 90 or cpu_usage > self.cpu_threshold:
            return max(1, self.max_workers // 4)  # 최소 1개
        elif memory_usage > 70:
            return self.max_workers // 2
        else:
            return self.max_workers

    async def throttle_if_needed(self):
        """자원 부족 시 대기"""
        while psutil.virtual_memory().percent > 95:
            await asyncio.sleep(0.5)

class PriorityScheduler:
    """
    작업 우선순위 기반 스케줄러.

    Priority Levels:
    - HIGH: 유저가 에디터에서 직접 수정한 파일 (즉시 처리)
    - MEDIUM: Git Pull/Merge로 인한 변경 (백그라운드 처리)
    - LOW: SelfHealer에 의한 자동 복구 (Idle 타임 처리)
    """

    async def schedule(self, task: BuildTask, priority: Priority) -> str:
        """우선순위 기반 스케줄링"""
```

---

### 9.3 Partial Vector Update (델타 벡터 관리)

파일 내의 특정 함수(Symbol)만 변경되었을 때, 모든 청크를 다시 임베딩하는 것은 비효율적입니다.

#### Atomic Chunk Swapping

```python
# codegraph_incremental/indexing/atomic_chunk_swap.py

class AtomicChunkSwapper:
    """
    변경된 청크만 원자적으로 교체.

    전체 파일의 모든 청크를 다시 임베딩하는 대신,
    변경된 청크만 식별하여 교체합니다.
    """

    async def swap_chunks(
        self,
        file_path: str,
        old_chunks: list[Chunk],
        new_chunks: list[Chunk],
        txn_ctx: TransactionContext,
    ) -> SwapResult:
        """
        청크 레벨 증분 업데이트.

        1. 변경된 청크 식별 (content_hash 비교)
        2. 삭제된 청크 Tombstone 처리
        3. 신규/변경된 청크만 임베딩
        4. 원자적 교체
        """
        # 1. 변경 분석
        added, removed, modified = self._diff_chunks(old_chunks, new_chunks)

        # 2. 변경된 것만 임베딩
        to_embed = added + modified
        if to_embed:
            embeddings = await self._embed_chunks(to_embed)

        # 3. Staging area에 쓰기
        await txn_ctx.stage_chunk_updates(
            add=[(c, e) for c, e in zip(to_embed, embeddings)],
            remove=[c.id for c in removed],
        )

        return SwapResult(
            added=len(added),
            removed=len(removed),
            modified=len(modified),
            skipped=len(new_chunks) - len(added) - len(modified),
        )
```

---

### 9.4 Multi-Engine Atomic Commit (분산 트랜잭션)

서로 다른 DB(Graph DB, Vector DB, Lexical Index)에 대한 업데이트를 원자적으로 처리해야 합니다.

#### Distributed Commit Coordinator (2PC 유사 패턴)

```python
# codegraph_incremental/transaction/distributed_coordinator.py

class DistributedCommitCoordinator:
    """
    분산 트랜잭션 조정자.

    2PC(Two-Phase Commit) 유사 패턴으로
    여러 저장소에 대한 원자적 커밋을 보장합니다.
    """

    def __init__(
        self,
        graph_store: IGraphStore,
        vector_store: IVectorStore,
        lexical_store: ILexicalStore,
    ):
        self.stores = {
            "graph": graph_store,
            "vector": vector_store,
            "lexical": lexical_store,
        }

    async def commit(self, txn_ctx: TransactionContext) -> CommitResult:
        """
        2PC 스타일 분산 커밋.

        Phase 1 (Prepare): 각 엔진에 Staging Area에 쓰기
        Phase 2 (Commit): 모든 엔진이 준비되면 포인터 교체
        Compensation: 실패 시 보상 트랜잭션 실행
        """
        prepared = {}

        try:
            # Phase 1: Prepare
            for name, store in self.stores.items():
                prep_result = await store.prepare(txn_ctx)
                if not prep_result.success:
                    raise PrepareFailedError(name, prep_result.error)
                prepared[name] = prep_result

            # Phase 2: Commit (모든 Prepare 성공)
            for name, store in self.stores.items():
                await store.commit(prepared[name].staging_id)

            return CommitResult(success=True)

        except Exception as e:
            # Compensation: 롤백
            for name, prep in prepared.items():
                await self.stores[name].rollback(prep.staging_id)
            raise
```

---

### 9.5 JIT Shadow Indexing (실시간성 보장)

Debouncer가 5초 배치를 기다리는 동안 사용자가 최신 코드에 대해 질문할 수 있습니다.

#### Virtual Delta View

```python
# codegraph_incremental/query/virtual_delta_view.py

class VirtualDeltaView:
    """
    실시간 검색을 위한 가상 델타 뷰.

    아직 물리적으로 인덱싱되지 않은 ShadowFS 내의
    변경 사항을 런타임에 결합하여 결과를 보정합니다.
    """

    async def query_with_delta(
        self,
        query: str,
        base_results: list[SearchResult],
        pending_changes: ChangeSet,
    ) -> list[SearchResult]:
        """
        검색 결과에 실시간 변경분 반영.

        1. 기존 검색 결과 획득
        2. 삭제된 파일의 결과 제거
        3. 변경된 파일의 결과 업데이트 (in-memory diff 적용)
        4. 신규 파일 검색 추가
        """
        # 삭제된 파일 제외
        filtered = [r for r in base_results if r.file_path not in pending_changes.deleted]

        # 변경된 파일 업데이트
        for result in filtered:
            if result.file_path in pending_changes.modified:
                result = await self._apply_in_memory_patch(result, pending_changes)

        # 신규 파일 검색 (경량 in-memory 검색)
        if pending_changes.added:
            new_results = await self._search_new_files(query, pending_changes.added)
            filtered.extend(new_results)

        return filtered
```

---

### 9.6 Partial Failure Policy (부분 실패 처리)

1,000개 파일 빌드 중 1개만 에러나도 전체 롤백하는 것은 비효율적입니다.

#### BuildErrorPolicy

```python
# codegraph_incremental/pipeline/error_policy.py

class BuildErrorPolicy(Enum):
    FAIL_ALL = "fail_all"          # 하나만 에러 나도 전체 롤백 (Critical)
    SKIP_AND_REPORT = "skip_and_report"  # 에러 파일만 제외하고 커밋
    RETRY_LATER = "retry_later"    # 에러 파일만 별도 큐로 격리

@dataclass
class PartialBuildResult:
    succeeded: list[str]
    failed: list[tuple[str, Exception]]
    policy_applied: BuildErrorPolicy

class ErrorHandler:
    """
    부분 실패 처리기.
    """

    def __init__(self, policy: BuildErrorPolicy):
        self.policy = policy

    async def handle_build_errors(
        self,
        results: list[BuildResult],
        txn_ctx: TransactionContext,
    ) -> PartialBuildResult:
        succeeded = [r.file for r in results if r.success]
        failed = [(r.file, r.error) for r in results if not r.success]

        if not failed:
            return PartialBuildResult(succeeded, failed, self.policy)

        if self.policy == BuildErrorPolicy.FAIL_ALL:
            raise BuildFailedError(f"{len(failed)} files failed")

        elif self.policy == BuildErrorPolicy.SKIP_AND_REPORT:
            # 실패한 파일은 Tombstone 처리
            for file, _ in failed:
                await txn_ctx.mark_as_stale(file)
            return PartialBuildResult(succeeded, failed, self.policy)

        elif self.policy == BuildErrorPolicy.RETRY_LATER:
            # 별도 재시도 큐에 추가
            for file, error in failed:
                await self._schedule_retry(file, error)
            return PartialBuildResult(succeeded, failed, self.policy)
```

---

### 9.7 Watcher Continuity (서비스 재시작 시 복구)

서비스 재시작 시 FileWatcher가 중단된 시점부터 현재까지의 변경사항을 놓칠 수 있습니다.

#### Checkpoint Manager (WAL 기반)

```python
# codegraph_incremental/tracking/checkpoint_manager.py

class CheckpointManager:
    """
    Watcher 연속성 보장을 위한 체크포인트 관리자.

    감지된 이벤트를 처리 전 먼저 WAL에 기록하고,
    부팅 시 마지막 체크포인트 이후 변경분을 복구합니다.
    """

    def __init__(self, wal_path: Path, snapshot_store: ISnapshotStore):
        self.wal = WriteAheadLog(wal_path)
        self.snapshots = snapshot_store

    async def record_event(self, event: FileEvent) -> None:
        """이벤트를 WAL에 기록 (처리 전)"""
        await self.wal.append(event)

    async def commit_checkpoint(self, snapshot_id: str) -> None:
        """처리 완료된 시점 기록"""
        await self.snapshots.save_checkpoint(
            snapshot_id=snapshot_id,
            timestamp=datetime.utcnow(),
            wal_position=self.wal.position,
        )

    async def recover_on_startup(self) -> ChangeSet:
        """
        부팅 시 누락된 변경분 복구.

        1. 마지막 체크포인트 로드
        2. WAL에서 미처리 이벤트 복구
        3. 파일 시스템 mtime과 비교하여 누락분 감지
        """
        last_checkpoint = await self.snapshots.get_last_checkpoint()

        # WAL 미처리 이벤트
        pending_events = await self.wal.read_after(last_checkpoint.wal_position)

        # 파일 시스템 스캔 (Range Scan)
        missed_changes = await self._scan_changes_since(last_checkpoint.timestamp)

        return ChangeSet.merge(
            ChangeSet.from_events(pending_events),
            missed_changes,
        )
```

---

### 9.8 Schema Versioning (IR 호환성)

패키지 버전이 올라가거나 IR 구조가 변경되었을 때 기존 캐시와의 호환성 문제가 발생합니다.

#### VersionController

```python
# codegraph_incremental/core/version_controller.py

class VersionController:
    """
    IR 스키마 버전 관리 및 호환성 체크.
    """

    CURRENT_SCHEMA_VERSION = "2.1.0"

    async def check_compatibility(self, cache_entry: CacheEntry) -> CompatibilityResult:
        """캐시 엔트리의 호환성 확인"""
        entry_version = cache_entry.schema_version

        if entry_version == self.CURRENT_SCHEMA_VERSION:
            return CompatibilityResult.COMPATIBLE

        if self._can_migrate(entry_version, self.CURRENT_SCHEMA_VERSION):
            return CompatibilityResult.NEEDS_MIGRATION

        return CompatibilityResult.INCOMPATIBLE

    async def migrate_if_needed(
        self,
        cache_entry: CacheEntry,
        txn_ctx: TransactionContext,
    ) -> CacheEntry | None:
        """필요시 on-the-fly 마이그레이션"""
        compat = await self.check_compatibility(cache_entry)

        if compat == CompatibilityResult.COMPATIBLE:
            return cache_entry

        if compat == CompatibilityResult.NEEDS_MIGRATION:
            migrated = await self._migrate(cache_entry)
            await txn_ctx.update_cache(migrated)
            return migrated

        # INCOMPATIBLE: 재빌드 필요
        return None
```

---

### 9.9 Differential Testing Framework (검증 자동화)

증분 업데이트의 "논리적 누락"을 검증하기 위한 자동화 프레임워크입니다.

#### Differential Verifier

```python
# codegraph_incremental/testing/differential_verifier.py

class DifferentialVerifier:
    """
    증분 vs 풀빌드 결과 비교 검증기.

    테스트 환경에서 동일한 코드 변경에 대해
    Full Build와 Incremental Build를 동시에 수행하고
    결과를 비교합니다.
    """

    async def verify(
        self,
        change_set: ChangeSet,
        full_builder: IFullBuilder,
        incremental_builder: IIncrementalBuilder,
    ) -> VerificationReport:
        """
        Dual-Path 검증.

        1. Full Build 실행
        2. Incremental Build 실행
        3. 결과 비교 (Graph edges, Vector scores 등)
        4. 오차율 계산
        """
        # 병렬 빌드
        async with asyncio.TaskGroup() as tg:
            full_task = tg.create_task(full_builder.build(change_set.all_files))
            incr_task = tg.create_task(incremental_builder.build(change_set))

        full_result = full_task.result()
        incr_result = incr_task.result()

        # 비교
        discrepancies = await self._compare_results(full_result, incr_result)

        return VerificationReport(
            full_edge_count=full_result.edge_count,
            incr_edge_count=incr_result.edge_count,
            discrepancies=discrepancies,
            parity_score=1.0 - (len(discrepancies) / max(full_result.edge_count, 1)),
        )
```

---

### 9.10 Graceful Degradation (단계적 성능 저하)

증분 시스템 실패 시 자동으로 Full 전략으로 전환합니다.

#### Fallback Strategy

```python
# codegraph_incremental/pipeline/fallback.py

class FallbackStrategy:
    """
    증분 실패 시 자동 Full 전환.

    TransactionError나 Consistency Drift가 임계치를 넘으면
    해당 파일군에 대해 FULL 전략으로 전환합니다.
    """

    def __init__(
        self,
        drift_threshold: float = 0.05,  # 5% 이상 드리프트시 전환
        error_threshold: int = 3,        # 연속 3회 에러시 전환
    ):
        self.drift_threshold = drift_threshold
        self.error_threshold = error_threshold
        self._error_counts: dict[str, int] = {}

    async def should_fallback(
        self,
        repo_id: str,
        last_result: PipelineResult | None,
    ) -> bool:
        """Full 전략으로 전환해야 하는지 판단"""
        if last_result and not last_result.success:
            self._error_counts[repo_id] = self._error_counts.get(repo_id, 0) + 1
            if self._error_counts[repo_id] >= self.error_threshold:
                return True
        else:
            self._error_counts[repo_id] = 0

        # 드리프트 비율 확인
        drift_rate = await self._get_drift_rate(repo_id)
        return drift_rate > self.drift_threshold

    def reset_on_success(self, repo_id: str):
        """성공 시 에러 카운트 리셋"""
        self._error_counts[repo_id] = 0
```

---

### 9.11 FingerprintManager 보완: Global Variable 처리

함수 시그니처는 그대로지만 참조하는 상수가 변경된 경우를 처리해야 합니다.

```python
# codegraph_incremental/semantics/fingerprint_manager.py (보완)

class FingerprintManager:
    async def can_skip(self, file_path: str) -> bool:
        # ... 기존 로직 ...

        # 추가: Global Variable/Constant 참조 확인
        referenced_globals = await self._get_referenced_globals(file_path)
        for global_ref in referenced_globals:
            if await self._is_global_changed(global_ref):
                return False  # 상수 변경됨 → 재빌드 필요

        return True

    async def _get_referenced_globals(self, file_path: str) -> list[str]:
        """Data Flow Graph에서 참조하는 상수/전역변수 추출"""

    async def _is_global_changed(self, global_ref: str) -> bool:
        """상수/전역변수 값이 변경되었는지 확인"""
```

---

## 10. Updated Package Structure

피드백을 반영한 최종 패키지 구조:

```
packages/codegraph-incremental/
└── codegraph_incremental/
    ├── core/
    │   ├── models.py
    │   ├── ports.py
    │   ├── events.py
    │   ├── errors.py
    │   └── version_controller.py       # 🆕 스키마 버전 관리
    │
    ├── detection/
    │   ├── file_watcher.py
    │   ├── watcher_debouncer.py
    │   ├── git_detector.py
    │   └── composite_detector.py
    │
    ├── semantics/
    │   ├── fingerprint_manager.py      # Global Variable 참조 추가
    │   ├── identity_tracker.py
    │   ├── affected_calculator.py
    │   └── pruning_engine.py
    │
    ├── tracking/
    │   ├── change_tracker.py
    │   ├── checkpoint_manager.py       # 🆕 WAL 기반 복구
    │   └── dependency_graph.py
    │
    ├── transaction/
    │   ├── manager.py
    │   ├── distributed_coordinator.py  # 🆕 2PC 분산 커밋
    │   ├── state.py
    │   └── conflict_registry.py
    │
    ├── builders/
    │   ├── file_builder.py
    │   ├── ir_delta_builder.py
    │   ├── chunk_builder.py
    │   └── protocol.py
    │
    ├── indexing/
    │   ├── incremental_indexer.py
    │   ├── atomic_chunk_swap.py        # 🆕 청크 레벨 증분
    │   └── tombstone.py
    │
    ├── consistency/
    │   ├── checker.py
    │   ├── self_healer.py
    │   └── drift_detector.py
    │
    ├── query/
    │   └── virtual_delta_view.py       # 🆕 실시간 검색 지원
    │
    ├── pipeline/
    │   ├── orchestrator.py
    │   ├── resource_manager.py         # 🆕 자원 제어
    │   ├── priority_scheduler.py       # 🆕 우선순위 스케줄링
    │   ├── error_policy.py             # 🆕 부분 실패 처리
    │   ├── fallback.py                 # 🆕 Graceful Degradation
    │   ├── stages.py
    │   └── strategies.py
    │
    ├── observability/
    │   ├── decision_log.py             # 🆕 결정 근거 로깅
    │   ├── lineage_store.py            # 🆕 추적 저장소
    │   ├── tracer.py                   # 🆕 OpenTelemetry 통합
    │   └── metrics.py
    │
    ├── testing/
    │   └── differential_verifier.py    # 🆕 증분 vs 풀빌드 검증
    │
    └── config.py
```

---

## 11. Updated Success Criteria

| 기준 | 목표 | 측정 방법 |
|------|------|-----------|
| 중복 제거 | 33개 → 0개 | 코드 분석 |
| 원자성 | 100% ACID | 분산 트랜잭션 테스트 |
| Pruning 효율 | 70% 감소 | 벤치마크 |
| 자가 치유 | 100% 자동 | 드리프트 테스트 |
| 부분 실패 복구 | 99% 성공 | 에러 주입 테스트 |
| 재시작 복구 | <1초 | 서비스 재시작 테스트 |
| 실시간 쿼리 | <100ms 지연 | Virtual Delta View 테스트 |
| Differential Parity | 100% 일치 | 자동화 검증 |

---

## 12. Open Questions (Updated)

1. **Cross-repo 의존성**: 초기 버전은 단일 레포에 집중. `repo_id`를 상위 필드로 두어 향후 확장 가능하게 인터페이스만 열어둠.

2. **Predictive Prefetch**: Stage 1 직후 Stage 2와 병렬로 수행. 관련 의존성 파일을 미리 L0/L1 캐시에 로드.

3. **Vector Compaction**: Qdrant 네이티브 기능 최대 활용 + Semantica의 Tombstone 관리와 동기화하는 **Compaction Coordinator**만 직접 구현.

---

## 13. Critical Considerations (실무적 제약 사항)

### 13.1 분산 트랜잭션(2PC)의 현실적 제약

9.4절의 `DistributedCommitCoordinator`는 이상적이지만, 실제 사용하는 엔진들(Qdrant, Memgraph, Tantivy)이 네이티브 XA 트랜잭션을 지원하지 않습니다.

**리스크**: Qdrant는 "Prepare" 단계에서 쓰기 잠금을 완벽히 제어하기 어렵고, 커밋 직전 네트워크 장애 시 정합성이 깨질 수 있습니다.

**해결책: Saga 패턴 + Outbox 패턴**

```python
# codegraph_incremental/transaction/saga_coordinator.py

class SagaCoordinator:
    """
    2PC 대신 Saga 패턴을 사용한 분산 트랜잭션.

    각 단계의 성공/실패를 Outbox 테이블에 기록하고,
    실패 시 보상 트랜잭션(Compensating Transaction)을 실행합니다.
    """

    async def execute_saga(self, txn_ctx: TransactionContext) -> SagaResult:
        saga_id = str(uuid4())
        steps_completed = []

        try:
            # Step 1: Graph DB
            await self._execute_step(saga_id, "graph", self.graph_store.apply, txn_ctx)
            steps_completed.append("graph")

            # Step 2: Vector DB
            await self._execute_step(saga_id, "vector", self.vector_store.apply, txn_ctx)
            steps_completed.append("vector")

            # Step 3: Lexical Index
            await self._execute_step(saga_id, "lexical", self.lexical_store.apply, txn_ctx)
            steps_completed.append("lexical")

            # 모든 단계 성공 → Outbox에 COMPLETED 기록
            await self.outbox.mark_completed(saga_id)
            return SagaResult(success=True)

        except Exception as e:
            # 실패 시 보상 트랜잭션 실행
            await self._compensate(saga_id, steps_completed, txn_ctx)
            await self.outbox.mark_failed(saga_id, str(e))
            raise

    async def _compensate(self, saga_id: str, completed: list[str], txn_ctx):
        """역순으로 보상 트랜잭션 실행"""
        for step in reversed(completed):
            store = getattr(self, f"{step}_store")
            await store.rollback(txn_ctx.snapshot_id)

    async def recover_incomplete_sagas(self):
        """서비스 재시작 시 미완료 Saga 복구"""
        incomplete = await self.outbox.get_incomplete()
        for saga in incomplete:
            if saga.should_retry:
                await self.execute_saga(saga.txn_ctx)
            else:
                await self._compensate(saga.id, saga.completed_steps, saga.txn_ctx)
```

---

### 13.2 JIT Shadow Indexing의 스코어 정규화

`VirtualDeltaView`에서 기존 Vector DB 결과와 메모리 검색 결과를 병합할 때, 유사도 점수 체계가 다릅니다.

**리스크**: Cosine Similarity와 Keyword 매칭 점수의 가중치가 달라 상위 결과가 왜곡될 수 있습니다.

**해결책: RRF(Reciprocal Rank Fusion) 기반 병합**

```python
# codegraph_incremental/query/virtual_delta_view.py (보완)

class VirtualDeltaView:
    async def query_with_delta(
        self,
        query: str,
        base_results: list[SearchResult],
        pending_changes: ChangeSet,
    ) -> list[SearchResult]:
        # ... 기존 로직 ...

        # 신규 파일 검색
        if pending_changes.added:
            new_results = await self._search_new_files(query, pending_changes.added)

            # RRF 기반 병합 (점수가 아닌 순위 기반)
            merged = self._rrf_merge(filtered, new_results, k=60)
            return merged

        return filtered

    def _rrf_merge(
        self,
        list_a: list[SearchResult],
        list_b: list[SearchResult],
        k: int = 60,
    ) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion으로 두 결과 리스트 병합.

        RRF Score = Σ 1 / (k + rank)

        점수 체계가 달라도 순위 기반으로 공정하게 병합됩니다.
        """
        scores = defaultdict(float)

        for rank, result in enumerate(list_a):
            scores[result.id] += 1 / (k + rank + 1)

        for rank, result in enumerate(list_b):
            scores[result.id] += 1 / (k + rank + 1)

        # 결과 재정렬
        all_results = {r.id: r for r in list_a + list_b}
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        return [all_results[id] for id in sorted_ids]
```

---

### 13.3 FingerprintManager의 분석 비용 최적화

Global Variable/Constant 참조 확인은 정적 분석 비용이 큽니다.

**리스크**: 모든 파일 변경마다 전체 프로젝트의 Data Flow를 계산하면 Pruning의 의미가 퇴색됩니다.

**해결책: Pre-computed Dependency Map**

```python
# codegraph_incremental/semantics/fingerprint_manager.py (보완)

class FingerprintManager:
    """
    Global Variable 의존성 맵을 Stage 6에서 미리 빌드하고,
    Stage 2에서는 Lookup만 수행하여 Critical Path 부하를 최소화합니다.
    """

    def __init__(self, global_dep_map: IGlobalDependencyMap):
        self.global_deps = global_dep_map  # Pre-computed map

    async def can_skip(self, file_path: str) -> bool:
        # ... 기존 로직 ...

        # O(1) Lookup으로 Global Variable 참조 확인
        referenced_globals = self.global_deps.get_references(file_path)
        changed_globals = self.global_deps.get_changed_since(self._last_txn_id)

        if referenced_globals & changed_globals:
            return False  # 상수 변경됨 → 재빌드 필요

        return True

class GlobalDependencyMapBuilder:
    """
    Stage 6 (Cleanup)에서 백그라운드로 의존성 맵 빌드.
    """

    async def build_incrementally(self, changed_files: set[str]) -> None:
        """변경된 파일만 분석하여 맵 업데이트"""
        for file in changed_files:
            refs = await self._analyze_global_refs(file)
            await self.map.update(file, refs)

    async def run_background(self):
        """유휴 시간에 전체 맵 최적화"""
        await self.map.compact()
```

---

### 13.4 Watcher Continuity의 Race Condition 방지

서비스 재시작 직후, 복구 스캔과 실시간 이벤트가 동시에 발생하면 중복 처리될 수 있습니다.

**해결책: LSN(Log Sequence Number) 기반 멱등성 보장**

```python
# codegraph_incremental/tracking/checkpoint_manager.py (보완)

class CheckpointManager:
    def __init__(self, ...):
        self._processed_lsn: int = 0  # 마지막 처리된 시퀀스 번호
        self._lock = asyncio.Lock()

    async def record_event(self, event: FileEvent) -> None:
        """이벤트에 LSN 부여"""
        event.lsn = await self._get_next_lsn()
        await self.wal.append(event)

    async def process_event(self, event: FileEvent) -> bool:
        """
        멱등성 보장: 이미 처리된 이벤트는 스킵.
        """
        async with self._lock:
            if event.lsn <= self._processed_lsn:
                return False  # 이미 처리됨

            # 처리 로직 ...

            self._processed_lsn = event.lsn
            return True

    async def recover_on_startup(self) -> ChangeSet:
        """복구 시 LSN 기반으로 중복 제거"""
        last_checkpoint = await self.snapshots.get_last_checkpoint()
        self._processed_lsn = last_checkpoint.lsn

        # 실시간 Watcher 시작 전에 복구 완료
        async with self._lock:
            pending_events = await self.wal.read_after(last_checkpoint.lsn)
            # Watcher가 동시에 던지는 이벤트는 LSN 체크로 자동 필터링
            return ChangeSet.from_events(pending_events)
```

---

## 14. Advanced Features (추가)

### 14.1 Semantic Garbage Collection (논리적 파편 정리)

증분 업데이트가 반복되면 Graph DB에 **고립된 심볼(Orphaned Nodes)**이나 **유령 관계(Dangling Edges)**가 남습니다.

```python
# codegraph_incremental/compaction/semantic_gc.py

class SemanticGarbageCollector:
    """
    Mark-and-Sweep 기반 Graph GC.

    Stage 6의 Compactor 내부에서 실행됩니다.
    """

    def __init__(
        self,
        graph_store: IGraphStore,
        gc_threshold_txns: int = 100,  # 100회 트랜잭션마다 GC
        retention_period: timedelta = timedelta(days=7),
    ):
        self.graph = graph_store
        self.threshold = gc_threshold_txns
        self.retention = retention_period

    async def run_gc(self, current_txn_id: int) -> GCResult:
        """
        Mark-and-Sweep GC 실행.

        1. Mark: 실제 소스코드에서 도달 가능한 심볼에 last_seen_txn_id 마킹
        2. Sweep: retention_period 동안 업데이트되지 않은 노드/엣지 삭제
        """
        if current_txn_id % self.threshold != 0:
            return GCResult(skipped=True)

        # Phase 1: Mark
        reachable_symbols = await self._collect_reachable_symbols()
        await self.graph.mark_seen(reachable_symbols, current_txn_id)

        # Phase 2: Sweep
        cutoff_txn = current_txn_id - self.threshold * 2
        orphaned = await self.graph.find_orphaned(
            last_seen_before=cutoff_txn,
            retention=self.retention,
        )

        deleted_count = 0
        for batch in chunked(orphaned, 1000):
            deleted_count += await self.graph.delete_nodes(batch)

        # Dangling edges 정리
        dangling_edges = await self.graph.find_dangling_edges()
        await self.graph.delete_edges(dangling_edges)

        return GCResult(
            deleted_nodes=deleted_count,
            deleted_edges=len(dangling_edges),
        )
```

---

### 14.2 Copy-on-Write Branch Snapshot (멀티 브랜치 지원)

브랜치를 빈번하게 전환할 때, 매번 대규모 증분 업데이트를 하는 것은 낭비입니다.

```python
# codegraph_incremental/branching/cow_index.py

class CopyOnWriteIndexManager:
    """
    Branch-aware Copy-on-Write 인덱싱.

    Git의 오브젝트 저장 방식과 유사하게,
    브랜치 전환 시 변경된 부분만 새 레이어에 기록합니다.
    """

    def __init__(self, base_index: IIndex, layer_store: ILayerStore):
        self.base = base_index
        self.layers = layer_store

    async def checkout_branch(self, branch_name: str) -> BranchIndex:
        """
        브랜치 전환 시 CoW 레이어 생성.

        1. 부모 브랜치의 스냅샷을 Read-only Layer로 고정
        2. 새 브랜치용 Writable Layer 생성
        3. 검색 시에는 레이어를 병합하여 반환
        """
        # 기존 브랜치 레이어 찾기
        existing = await self.layers.get(branch_name)
        if existing:
            return BranchIndex(
                branch=branch_name,
                base_layer=existing.parent,
                delta_layer=existing,
            )

        # 새 브랜치: 현재 상태를 부모로 고정
        parent_snapshot = await self.base.snapshot()
        new_layer = await self.layers.create(
            branch=branch_name,
            parent=parent_snapshot,
        )

        return BranchIndex(
            branch=branch_name,
            base_layer=parent_snapshot,
            delta_layer=new_layer,
        )

    async def search(self, query: str, branch: str) -> list[SearchResult]:
        """레이어 병합 검색"""
        branch_idx = await self.checkout_branch(branch)

        # 델타 레이어 우선 검색
        delta_results = await branch_idx.delta_layer.search(query)

        # 베이스 레이어 검색 (델타에서 삭제된 것 제외)
        deleted_ids = await branch_idx.delta_layer.get_deleted_ids()
        base_results = await branch_idx.base_layer.search(
            query,
            exclude=deleted_ids,
        )

        # RRF 병합
        return self._rrf_merge(delta_results, base_results)

    async def merge_branch(self, source: str, target: str) -> MergeResult:
        """
        브랜치 병합.

        소스 브랜치의 델타 레이어를 타겟에 적용합니다.
        """
        source_delta = await self.layers.get(source)
        target_idx = await self.checkout_branch(target)

        # 충돌 감지
        conflicts = await self._detect_conflicts(source_delta, target_idx)
        if conflicts:
            return MergeResult(success=False, conflicts=conflicts)

        # 델타 적용
        await target_idx.delta_layer.apply(source_delta.changes)

        return MergeResult(success=True)
```

---

### 14.3 Branch Snapshot 시각화

```
main (base snapshot)
├── feature-a (delta: +50 files, -10 files)
│   └── feature-a-fix (delta: +3 files)
└── feature-b (delta: +20 files)

검색 시:
feature-a-fix 브랜치 → feature-a-fix delta + feature-a delta + main base
```

---

## 15. Updated Package Structure (Final)

```
packages/codegraph-incremental/
└── codegraph_incremental/
    ├── core/
    │   ├── models.py
    │   ├── ports.py
    │   ├── events.py
    │   ├── errors.py
    │   └── version_controller.py
    │
    ├── detection/
    │   └── ...
    │
    ├── semantics/
    │   ├── fingerprint_manager.py      # Pre-computed map 사용
    │   ├── global_dep_map.py           # 🆕 Global Variable 의존성 맵
    │   └── ...
    │
    ├── tracking/
    │   ├── checkpoint_manager.py       # LSN 기반 멱등성
    │   └── ...
    │
    ├── transaction/
    │   ├── saga_coordinator.py         # 🆕 Saga 패턴 (2PC 대체)
    │   ├── outbox.py                   # 🆕 Outbox 패턴
    │   └── ...
    │
    ├── compaction/
    │   ├── semantic_gc.py              # 🆕 Mark-and-Sweep GC
    │   └── ...
    │
    ├── branching/                       # 🆕 멀티 브랜치 지원
    │   ├── cow_index.py                # Copy-on-Write 인덱싱
    │   ├── layer_store.py              # 레이어 저장소
    │   └── merge.py                    # 브랜치 병합
    │
    ├── query/
    │   └── virtual_delta_view.py       # RRF 병합 추가
    │
    └── ...
```

---

## 16. Final Success Criteria

| 기준 | 목표 | 측정 방법 |
|------|------|-----------|
| 중복 제거 | 33개 → 0개 | 코드 분석 |
| 원자성 (Saga) | 99.9% 성공 | Outbox 복구 테스트 |
| Pruning 효율 | 70% 감소 | 벤치마크 |
| 자가 치유 | 100% 자동 | 드리프트 테스트 |
| Semantic GC | Orphan 0% | Graph 정합성 검증 |
| 브랜치 전환 | <500ms | CoW 레이어 테스트 |
| 부분 실패 복구 | 99% 성공 | 에러 주입 테스트 |
| 재시작 복구 (LSN) | <1초, 중복 0% | 멱등성 테스트 |
| 실시간 쿼리 (RRF) | <100ms | Virtual Delta View 테스트 |
| Differential Parity | 100% 일치 | 자동화 검증 |

---

## 17. References

- RFC-031: Stable ID Generation
- RFC-039: L0 Cache Architecture
- ADR-003: Workflow State Machine
- [Tree-sitter Incremental Parsing](https://tree-sitter.github.io/tree-sitter/)
- [MVCC in Databases](https://en.wikipedia.org/wiki/Multiversion_concurrency_control)
- [Saga Pattern](https://microservices.io/patterns/data/saga.html)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Copy-on-Write Data Structures](https://en.wikipedia.org/wiki/Copy-on-write)
- [OpenTelemetry Tracing](https://opentelemetry.io/docs/concepts/signals/traces/)
