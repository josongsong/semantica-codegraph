# 인덱싱 파이프라인 시각화 다이어그램

> Mermaid 다이어그램 모음

---

## 1. 전체 파이프라인 플로우

```mermaid
flowchart TD
    Start[변경 발생] --> Check1{어디서?}

    Check1 -->|IDE 편집| ShadowFS[ShadowFS Plugin]
    Check1 -->|외부 변경| FileWatcher[FileWatcher]
    Check1 -->|수동 실행| CLI[CLI/API]

    ShadowFS --> BatchWrite[write 이벤트 추적]
    BatchWrite --> Commit[commit 시 배치]
    Commit --> IRDelta[IR Delta 계산]
    IRDelta --> Index1[인덱싱 <]

    FileWatcher --> Debounce[ Debounce]
    Debounce --> Batch[배치 준비]
    Batch --> Index2[인덱싱 <]

    CLI --> ChangeDetect[ChangeDetector]
    ChangeDetect --> Git{git 있음?}
    Git -->|Yes| GitDiff[git diff]
    Git -->|No| Mtime[mtime + hash]
    GitDiff --> Index3[인덱싱]
    Mtime --> Index3

    Index1 --> CheckSig{시그니처 변경?}
    Index2 --> CheckSig
    Index3 --> CheckSig

    CheckSig -->|Yes| AutoDeep[자동 DEEP escalation]
    CheckSig -->|No| Done[완료]

    AutoDeep --> DeepIndex[DEEP 인덱싱]
    DeepIndex --> Done

    style ShadowFS fill:#90EE90
    style FileWatcher fill:#87CEEB
    style CLI fill:#FFD700
    style AutoDeep fill:#FF6B6B
```

---

## 2. 모드별 처리 범위

```mermaid
graph LR
    Changed[변경 파일] --> Fast[FAST: 변경만]
    Changed --> Balanced[BALANCED: 변경+1hop]
    Changed --> Deep[DEEP: 변경+2hop]

    Fast --> F1[main.py]

    Balanced --> B1[main.py]
    Balanced --> B2[import A]
    Balanced --> B3[import B]

    Deep --> D1[main.py]
    Deep --> D2[import A]
    Deep --> D3[import B]
    Deep --> D4[A imports C]
    Deep --> D5[B imports D]

    style Fast fill:#90EE90
    style Balanced fill:#FFD700
    style Deep fill:#FF6B6B
```

---

## 3. BackgroundScheduler 상태 머신

```mermaid
stateDiagram-v2
    [*] --> Idle: start()

    Idle --> WaitingJob: job_queue.get()

    WaitingJob --> Running: current_job 시작

    Running --> CheckStop: 파일 처리 중

    CheckStop --> Running: stop_event 없음
    CheckStop --> Paused: stop_event.set()
    CheckStop --> Completed: 모든 파일 완료

    Paused --> SaveProgress: JobProgress 저장
    SaveProgress --> Idle: 다음 작업 대기

    Completed --> LogComplete: 완료 로그
    LogComplete --> Idle: 다음 작업 대기

    Idle --> [*]: stop()

    note right of Paused
        Graceful stop:
        - 현재 파일 완료
        - 진행상태 저장
        - 나중에 재개 가능
    end note
```

---

## 4. 충돌 해결 우선순위

```mermaid
graph TD
    Conflict[동시 인덱싱 요청] --> Priority{우선순위 비교}

    Priority -->|FAST| Fast[FAST 실행]
    Priority -->|REPAIR| Repair[REPAIR 실행]
    Priority -->|BALANCED| Balanced[BALANCED 실행]
    Priority -->|DEEP| Deep[DEEP 실행]

    Fast --> PauseOthers[다른 작업 pause]
    Repair --> StopOthers[다른 작업 stop]
    Balanced --> WaitFast{FAST 있음?}
    Deep --> WaitFast2{FAST 있음?}

    WaitFast -->|Yes| PauseSelf[자신 pause]
    WaitFast -->|No| Continue[실행 계속]

    WaitFast2 -->|Yes| Timeout[30초 timeout 대기]
    WaitFast2 -->|No| Continue2[실행 계속]

    PauseOthers --> Done[완료]
    StopOthers --> Done
    PauseSelf --> Done
    Continue --> Done
    Timeout --> Done
    Continue2 --> Done

    style Fast fill:#90EE90
    style Repair fill:#FF6B6B
    style Balanced fill:#FFD700
    style Deep fill:#FFA500
```

---

## 5. ChangeDetector 전략

```mermaid
flowchart TD
    Start[변경 감지 시작] --> UseGit{git 사용?}

    UseGit -->|Yes| GitDiff[git diff --name-status]
    UseGit -->|No| UseMtime{mtime 사용?}

    GitDiff --> ParseGit[A/M/D/R 파싱]
    ParseGit --> GitSuccess{성공?}

    GitSuccess -->|Yes| MergeGit[ChangeSet 생성]
    GitSuccess -->|No| UseMtime

    UseMtime -->|Yes| CheckMtime[mtime 비교]
    UseMtime -->|No| UseHash{hash 사용?}

    CheckMtime --> HashVerify[hash로 검증]
    HashVerify --> MergeHash[ChangeSet 병합]

    UseHash -->|Yes| ComputeHash[content hash]
    UseHash -->|No| Empty[빈 ChangeSet]

    ComputeHash --> MergeHash

    MergeGit --> CheckRename{rename 감지?}
    MergeHash --> CheckRename

    CheckRename -->|git R100| AddRenamed[renamed dict 추가]
    CheckRename -->|similarity| Similarity[Jaccard ≥ 0.90]
    CheckRename -->|없음| Done[완료]

    Similarity --> AddRenamed
    AddRenamed --> Done

    style GitDiff fill:#90EE90
    style CheckMtime fill:#FFD700
    style ComputeHash fill:#FFA500
```

---

## 6. ScopeExpander 자동 Escalation

```mermaid
flowchart TD
    Start[expand_scope 호출] --> CheckImpact{ImpactResult 있음?}

    CheckImpact -->|No| UseMode[기존 모드 사용]
    CheckImpact -->|Yes| CheckSig{SIGNATURE_CHANGED?}

    CheckSig -->|No| UseMode
    CheckSig -->|Yes| CheckMode{현재 모드?}

    CheckMode -->|FAST| EscalateDeep1[자동 DEEP escalation]
    CheckMode -->|BALANCED| EscalateDeep2[자동 DEEP escalation]
    CheckMode -->|DEEP| UseMode

    UseMode --> ModeSwitch{모드 선택}
    EscalateDeep1 --> ModeSwitch
    EscalateDeep2 --> ModeSwitch

    ModeSwitch -->|FAST| ChangedOnly[변경 파일만]
    ModeSwitch -->|BALANCED| OneHop[변경 + 1-hop BFS]
    ModeSwitch -->|DEEP| TwoHop[변경 + 2-hop BFS]
    ModeSwitch -->|BOOTSTRAP| All[전체 레포]
    ModeSwitch -->|REPAIR| Affected[변경 + 참조된 파일]

    ChangedOnly --> Done[완료]
    OneHop --> CheckMax1{max 100개?}
    TwoHop --> CheckMax2{max 500개?}
    All --> Done
    Affected --> Done

    CheckMax1 -->|초과| Limit1[100개로 제한]
    CheckMax1 -->|이내| Done

    CheckMax2 -->|초과| Limit2[500개로 제한]
    CheckMax2 -->|이내| Done

    Limit1 --> Done
    Limit2 --> Done

    style EscalateDeep1 fill:#FF6B6B
    style EscalateDeep2 fill:#FF6B6B
    style TwoHop fill:#FFA500
```

---

## 7. FileWatcher Debouncing

```mermaid
sequenceDiagram
    participant User
    participant FS as FileSystem
    participant Watchdog
    participant Debouncer
    participant Callback

    User->>FS: Save (t=)
    FS->>Watchdog: MODIFIED event
    Watchdog->>Debouncer: push_event(main.py)
    Note over Debouncer: Timer 시작 ()

    User->>FS: Save again (t=)
    FS->>Watchdog: MODIFIED event
    Watchdog->>Debouncer: push_event(main.py)
    Note over Debouncer: Timer 리셋 ()

    User->>FS: Save again (t=)
    FS->>Watchdog: MODIFIED event
    Watchdog->>Debouncer: push_event(main.py)
    Note over Debouncer: Timer 리셋 ()

    Note over Debouncer:  경과 (t=)
    Debouncer->>Debouncer: 배치 준비
    Debouncer->>Callback: on_batch_ready(ChangeSet)
    Note over Callback: main.py 1회만 인덱싱
```

---

## 8. ShadowFS Plugin 라이프사이클

```mermaid
sequenceDiagram
    participant User
    participant ShadowFS
    participant Plugin
    participant IRBuilder
    participant Indexer

    User->>ShadowFS: write(main.py, txn-123)
    ShadowFS->>Plugin: on_event(WRITE)
    Plugin->>Plugin: 추적 (pending_ir_deltas)
    Plugin->>Plugin: 추적 (pending_changes)
    Note over Plugin: < (dict 연산만)

    User->>ShadowFS: write(utils.py, txn-123)
    ShadowFS->>Plugin: on_event(WRITE)
    Plugin->>Plugin: 추적 추가

    User->>ShadowFS: commit(txn-123)
    ShadowFS->>Plugin: on_event(COMMIT)

    Plugin->>Plugin: files_by_lang 그룹핑

    par Python 파일
        Plugin->>IRBuilder: build_incremental([main.py, utils.py])
        IRBuilder-->>Plugin: IR deltas
    and TypeScript 파일
        Plugin->>IRBuilder: build_incremental([index.ts])
        IRBuilder-->>Plugin: IR deltas
    end

    Plugin->>Indexer: index_files([main.py, utils.py, index.ts])
    Indexer-->>Plugin: 완료

    Plugin->>Plugin: cleanup (pending 삭제)
    Plugin-->>ShadowFS: 완료

    Note over Plugin: < (배치 처리)
```

---

## 9. 엣지케이스: BALANCED Pause & Resume

```mermaid
sequenceDiagram
    participant Scheduler
    participant Job as BALANCED Job
    participant Detector as IdleDetector
    participant Fast as FAST Request

    Note over Scheduler: t=0, BALANCED 시작
    Scheduler->>Job: 실행 (1000 files)

    Note over Job: t=5min, 500 files 완료 (50%)

    Detector->>Detector: 사용자 활동 감지
    Detector->>Scheduler: mark_activity()

    Fast->>Scheduler: FAST 요청
    Scheduler->>Job: pause_current_job()
    Job->>Job: stop_event.set()

    Note over Job: 현재 파일 완료 대기
    Job->>Job: JobProgress 저장
    Job-->>Scheduler: paused

    Scheduler->>Fast: FAST 실행 (<5초)
    Fast-->>Scheduler: 완료

    Note over Detector: Idle 5분 대기

    Detector->>Scheduler: is_idle() = True
    Scheduler->>Scheduler: resume_paused_job()
    Scheduler->>Job: 재스케줄 (checkpoint)

    Note over Job: 500번째부터 재개
    Job->>Job: 나머지 500 files 처리
    Job-->>Scheduler: 완료
```

---

## 10. 우선순위 큐 동작

```mermaid
graph TD
    Queue[PriorityQueue] --> Job1[DEEP priority=3]
    Queue --> Job2[BALANCED priority=2]
    Queue --> Job3[REPAIR priority=1]

    Scheduler[BackgroundScheduler] --> Pop[queue.get]

    Pop --> Sort{Priority 정렬}

    Sort --> First[REPAIR 먼저]
    First --> Second[BALANCED 다음]
    Second --> Third[DEEP 마지막]

    Third --> CheckIdle{Idle?}
    CheckIdle -->|Yes| Execute[실행]
    CheckIdle -->|No| Wait[대기]

    style Job3 fill:#FF6B6B
    style Job2 fill:#FFD700
    style Job1 fill:#FFA500
```

---

## 사용 방법

### Mermaid Live Editor
1. https://mermaid.live 방문
2. 위 코드 복사/붙여넣기
3. PNG/SVG 다운로드

### VS Code
1. Mermaid Preview 확장 설치
2. Cmd+Shift+P → "Mermaid: Preview"

### Notion/Confluence
- Mermaid 블록 생성 후 코드 붙여넣기

---

**Last 
