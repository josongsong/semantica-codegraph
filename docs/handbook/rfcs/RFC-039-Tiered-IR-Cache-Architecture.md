# RFC-039: Tiered IR Cache Architecture (Final)

| Field | Value |
|-------|-------|
| **Status** | Final Draft |
| **Created** | 2025-12-22 |
| **Updated** | 2025-12-22 |
| **Author** | CodeGraph Team |
| **Priority** | P0 (Critical Path) |
| **Estimated Effort** | 16-20 hours total |

---

## 1. Executive Summary

Structural IR 빌드 파이프라인에 3-Tier 캐시 아키텍처를 도입하여 Watch mode에서 **274x 성능 향상**을 달성한다.

**핵심 변경사항:**
- `LayeredIRBuilder`를 Stateful로 전환 (L0 캐시)
- `MemoryCache`에 메모리 크기 제한 추가 (L1)
- `TieredCache` Facade 도입 (L0→L1→L2 통합)
- `IncrementalStrategy` dead code 제거 (~50줄)
- **L0 메모리 제한 및 Purge 로직** (NEW)
- **Fast Path 변경 감지** (mtime + size) (NEW)
- **Cache Telemetry** (NEW)

---

## 2. Background & Motivation

### 2.1 현재 문제점

```
현재 상태: 캐시 시스템이 분산되어 있고, L0 레이어가 없음

┌─────────────────────────────────────────────────────────────┐
│ IncrementalStrategy                                         │
│   ._ir_cache: dict          ← 자체 L0 캐시 (Strategy 내부)   │
│   ._change_tracker          ← 자체 변경 추적                 │
│             ↓                                                │
│   await builder.build()     ← 매번 새 Builder 생성!          │
│                               (L0 상태 유실)                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ LayeredIRBuilder (Stateless)                                │
│   _parse_file_worker()                                       │
│             ↓                                                │
│   get_global_cache() → DiskCache (L2만 사용)                 │
└─────────────────────────────────────────────────────────────┘
```

**문제점:**
1. `IncrementalStrategy`가 매번 새 `LayeredIRBuilder` 생성 → L0 상태 유실
2. `MemoryCache`가 L1으로 사용되지 않음 (DiskCache만 사용)
3. 메모리 크기 제한 없음 (OOM 위험)
4. `IncrementalStrategy._ir_cache`와 `DiskCache` 중복
5. `ChangeTracker`와 `GlobalContext.dependencies` 중복

### 2.2 성능 목표

| Scenario | Current | Target | Improvement |
|----------|---------|--------|-------------|
| First build (cold) | 5.02s | 5.02s | - |
| Second build (warm L2) | 3.43s | 3.43s | 31.7% |
| Watch mode (warm L0) | 3.43s | <0.05s | **274x** |
| Memory limit (L0) | Unlimited | 2000 files | OOM 방지 |
| Memory limit (L1) | Unlimited | 512MB | OOM 방지 |
| L0 check (10K files) | ~100ms+ | <10ms | **Fast Path** |

---

## 3. Proposed Architecture

### 3.1 3-Tier Cache Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          IRPipeline (Entry Point)                            │
│                                                                               │
│  _builder: LayeredIRBuilder  ← 재사용 (Stateful)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   LayeredIRBuilder (Stateful) [NEW]                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ L0: Builder Instance State (0ms)                                     │    │
│  │                                                                       │    │
│  │  _l0_cache: dict[str, IRDocument]   ← 현재 빌드 세션의 IR             │    │
│  │  _l0_metadata: dict[str, FileMetadata]  ← mtime, size, hash [NEW]    │    │
│  │  _l0_max_files: int = 2000          ← 메모리 제한 [NEW]              │    │
│  │  _change_tracker: ChangeTracker     ← 공유 인스턴스                   │    │
│  │                                                                       │    │
│  │  Features:                                                            │    │
│  │    - Fast Path: mtime+size 먼저 체크 [NEW]                           │    │
│  │    - Purge: 현재 files에 없는 항목 제거 [NEW]                        │    │
│  │    - LRU Eviction: max_files 초과 시 [NEW]                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                          │
│                                    ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ TieredCache (L1 + L2 Facade) [NEW]                                   │    │
│  │                                                                       │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │ L1: MemoryCache (Process Memory)                               │  │    │
│  │  │                                                                 │  │    │
│  │  │  - OrderedDict (O(1) LRU)                                      │  │    │
│  │  │  - max_size: 500 entries                                       │  │    │
│  │  │  - max_bytes: 512MB [NEW]                                      │  │    │
│  │  │  - Thread-safe (threading.Lock)                                │  │    │
│  │  │  - IRDocument.estimated_size property [NEW]                    │  │    │
│  │  │  - Access: ~0.1ms                                              │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  │                                    │                                  │    │
│  │                                    ▼                                  │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │ L2: DiskCache (Persistent)                                     │  │    │
│  │  │                                                                 │  │    │
│  │  │  - msgpack serialization (5-10x faster than pickle)            │  │    │
│  │  │  - xxhash (필수 종속성) [UPDATED]                               │  │    │
│  │  │  - struct header (26 bytes, quick validation)                  │  │    │
│  │  │  - Atomic write (tmp + os.replace)                             │  │    │
│  │  │  - fcntl locking (multiprocess-safe)                           │  │    │
│  │  │  - Access: ~1-5ms                                              │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Cache Telemetry [NEW]                                                │    │
│  │                                                                       │    │
│  │  - L0/L1/L2 hit rate                                                 │    │
│  │  - Serialization time                                                │    │
│  │  - Eviction count                                                    │    │
│  │  - Build summary report                                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Cache Flow (Fast Path 포함)

```
build(files) 호출
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ L0 Fast Path Check [NEW]                                  │
│                                                           │
│  for file in files:                                       │
│    1. stat = os.stat(file)  ← 1회 시스템 콜              │
│    2. if (mtime, size) == L0_metadata[file]:             │
│         → L0 Hit (해시 계산 없음!)                        │
│    3. else:                                               │
│         → L0 Miss (content hash 계산 필요)               │
│                                                           │
│  Performance: 10,000 files → <10ms (vs 100ms+ 해시 방식)  │
└──────────────────────────────────────────────────────────┘
       │
       ├─── All Hit → 즉시 반환 + Purge orphans
       │
       ▼ Partial/Full Miss
┌──────────────────┐
│ L1 Check         │ ← ~0.1ms (OrderedDict)
│ (MemoryCache)    │
└──────────────────┘
       │
       ├─── Hit → L0 업데이트 후 반환
       │
       ▼ Miss
┌──────────────────┐
│ L2 Check         │ ← ~1-5ms (Disk I/O)
│ (DiskCache)      │
└──────────────────┘
       │
       ├─── Hit → L0, L1 업데이트 후 반환
       │
       ▼ Miss
┌──────────────────┐
│ Worker Pool      │ ← ProcessPoolExecutor
│ (Parallel Parse) │
│                  │
│ Worker는 L2만   │
│ 접근 가능!       │ ← Main L0/L1 격리 [명확화]
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Main Process:    │
│ - Collect results│
│ - Update L0/L1   │ ← Worker 결과를 Main에서 업데이트
│ - Log telemetry  │
└──────────────────┘
```

### 3.3 Worker-Main 캐시 전파 (명확화)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Multi-processing Cache Flow                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Main Process                           Worker Processes                     │
│  ─────────────────                      ───────────────────                  │
│                                                                              │
│  1. L0/L1 Check                                                              │
│     ↓                                                                        │
│  2. Cache Miss 파일 목록                                                     │
│     ↓                                                                        │
│  3. ProcessPool.submit(parse_file_worker, files)  ──────────────────────→   │
│                                                                     │        │
│                                                    ┌────────────────▼──────┐ │
│                                                    │ Worker:              │ │
│                                                    │  - L2 Check (Disk)   │ │
│                                                    │  - Parse if miss     │ │
│                                                    │  - L2 Write          │ │
│                                                    │  - Return: IR dict   │ │
│                                                    │    (serialized)      │ │
│                                                    └────────────────┬──────┘ │
│                                                                     │        │
│  4. Collect results  ←──────────────────────────────────────────────┘        │
│     ↓                                                                        │
│  5. Update L0 cache (Main memory)                                            │
│     ↓                                                                        │
│  6. Update L1 cache (Main memory)                                            │
│     ↓                                                                        │
│  7. Sync GlobalContext                                                       │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Key Point:                                                                  │
│  - Worker는 L2(Disk)만 접근 가능                                             │
│  - L0/L1는 Main Process 메모리에만 존재                                       │
│  - IPC 비용: IR dict는 pickle 직렬화 필요                                    │
│                                                                              │
│  최적화 옵션 (P0.2):                                                         │
│  - Worker가 IR 대신 cache_key만 반환                                         │
│  - Main이 L2에서 lazy load                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 GlobalContext 동기화 (명확화)

```python
# L0에서 IR 반환 시 GlobalContext 동기화 필수

async def build(self, files: list[Path], config: BuildConfig) -> BuildResult:
    # 1. L0 check
    changed_files, unchanged_irs = self._check_l0(files)
    
    # 2. Build changed files
    new_irs = await self._build_changed_files(changed_files, config)
    
    # 3. Merge all IRs
    all_irs = {**unchanged_irs, **new_irs}
    
    # 4. [CRITICAL] GlobalContext 재구축
    #    L0 cached IR도 GlobalContext에 반영되어야 함
    global_ctx = self._rebuild_global_context(all_irs)
    
    # 5. Sync ChangeTracker dependencies
    for path, ir in all_irs.items():
        deps = self._extract_dependencies(ir)
        self._change_tracker.update_dependencies(path, deps)
    
    return BuildResult(ir_documents=all_irs, global_ctx=global_ctx, ...)
```

---

## 4. Critical Improvements (Review Feedback)

### 4.1 우선순위별 개선사항

| Priority | Feature | Phase | Impact |
|----------|---------|-------|--------|
| 🔴 P0.1 필수 | L0 메모리 제한 (max_files) | Phase 3 | OOM 방지 |
| 🔴 P0.1 필수 | L0 Fast Path (mtime+size) | Phase 3 | 10x 빠른 체크 |
| 🔴 P0.1 필수 | L0 Purge 로직 | Phase 3 | 메모리 누수 방지 |
| 🔴 P0.1 필수 | Worker-Main 격리 명확화 | Phase 3 | 정확성 |
| 🔴 P0.1 필수 | GlobalContext 동기화 | Phase 3 | 후속 분석 정확성 |
| 🟠 P0.1 권장 | IRDocument.estimated_size | Phase 1 | 캡슐화 |
| 🟠 P0.1 권장 | Cache Telemetry | Phase 3 | 디버깅 |
| 🟠 P0.1 권장 | xxhash 필수 종속성 | Phase 1 | 성능 |
| 🟡 P0.2 | Negative Caching (실패 캐싱) | - | 안정성 |
| 🟡 P0.2 | Environmental Context Hash | - | 정확성 |
| 🟡 P0.2 | Worker → cache_key only | - | IPC 최적화 |
| 🟢 P0.5 | Signature Hash (public API) | - | Fine-grained |
| 🟢 P0.5 | Priority-based Eviction | - | 효율성 |
| 🔵 P1 | State Snapshotting (Warm Start) | - | 재시작 최적화 |
| 🔵 P1 | Structural Sharing (Flyweight) | - | 메모리 40-60% ↓ |
| ⚪ P2+ | CAS Storage | - | 충돌 방지 |

### 4.2 L0 메모리 관리 (P0.1 필수)

```python
@dataclass
class FileMetadata:
    """Fast path 메타데이터."""
    mtime: float
    size: int
    content_hash: str  # 최초 계산 후 저장


class LayeredIRBuilder:
    def __init__(self, ...):
        # L0 캐시
        self._l0_cache: dict[str, IRDocument] = {}
        self._l0_metadata: dict[str, FileMetadata] = {}
        
        # [NEW] L0 제한
        self._l0_max_files = 2000  # 설정 가능
        self._l0_access_order: list[str] = []  # LRU tracking
    
    def _check_l0(self, files: list[Path]) -> tuple[list[Path], dict[str, IRDocument]]:
        """L0 체크 with Fast Path."""
        changed: list[Path] = []
        unchanged: dict[str, IRDocument] = {}
        current_files = set(str(f) for f in files)
        
        for file_path in files:
            path_str = str(file_path)
            
            try:
                # [NEW] Fast Path: mtime + size 먼저 체크
                stat = file_path.stat()
                current_mtime = stat.st_mtime
                current_size = stat.st_size
                
                if path_str in self._l0_metadata:
                    meta = self._l0_metadata[path_str]
                    
                    # Fast Path Hit: mtime+size 동일하면 해시 스킵
                    if meta.mtime == current_mtime and meta.size == current_size:
                        unchanged[path_str] = self._l0_cache[path_str]
                        self._update_l0_access(path_str)
                        continue
                
                # Slow Path: 내용이 바뀌었거나 새 파일
                content = file_path.read_text(encoding="utf-8")
                content_hash = self._compute_hash(content)
                
                # Hash 비교 (mtime은 다르지만 내용은 같을 수 있음)
                if path_str in self._l0_metadata:
                    if self._l0_metadata[path_str].content_hash == content_hash:
                        # 내용 동일, 메타데이터만 업데이트
                        self._l0_metadata[path_str].mtime = current_mtime
                        self._l0_metadata[path_str].size = current_size
                        unchanged[path_str] = self._l0_cache[path_str]
                        continue
                
                changed.append(file_path)
                
            except Exception as e:
                self.logger.warning(f"L0 check failed for {file_path}: {e}")
                changed.append(file_path)
        
        # [NEW] Purge: 현재 파일 목록에 없는 항목 제거
        self._purge_orphans(current_files)
        
        return changed, unchanged
    
    def _purge_orphans(self, current_files: set[str]) -> None:
        """현재 파일 목록에 없는 L0 캐시 제거."""
        orphans = set(self._l0_cache.keys()) - current_files
        for path in orphans:
            self._l0_cache.pop(path, None)
            self._l0_metadata.pop(path, None)
            if path in self._l0_access_order:
                self._l0_access_order.remove(path)
        
        if orphans:
            self.logger.debug(f"L0 purged {len(orphans)} orphan entries")
    
    def _update_l0(self, new_irs: dict[str, IRDocument], file_stats: dict[str, tuple]) -> None:
        """L0 업데이트 with LRU eviction."""
        for path_str, ir_doc in new_irs.items():
            mtime, size = file_stats.get(path_str, (0, 0))
            content_hash = self._compute_hash_from_ir(ir_doc)  # 또는 저장된 값 사용
            
            # [NEW] LRU eviction
            if len(self._l0_cache) >= self._l0_max_files and path_str not in self._l0_cache:
                oldest = self._l0_access_order.pop(0)
                self._l0_cache.pop(oldest, None)
                self._l0_metadata.pop(oldest, None)
            
            self._l0_cache[path_str] = ir_doc
            self._l0_metadata[path_str] = FileMetadata(
                mtime=mtime,
                size=size,
                content_hash=content_hash,
            )
            self._update_l0_access(path_str)
    
    def _update_l0_access(self, path: str) -> None:
        """LRU access order 업데이트."""
        if path in self._l0_access_order:
            self._l0_access_order.remove(path)
        self._l0_access_order.append(path)
```

### 4.3 IRDocument.estimated_size (P0.1 권장)

```python
# models/document.py

@dataclass
class IRDocument:
    nodes: list[Node]
    edges: list[Edge]
    occurrences: list[Occurrence]
    # ...
    
    @property
    def estimated_size(self) -> int:
        """
        메모리 크기 추정 (bytes).
        
        Used by MemoryCache for size-based eviction.
        
        Estimation:
            - Node: ~200 bytes (name, type, location, metadata)
            - Edge: ~100 bytes (source, target, kind)
            - Occurrence: ~50 bytes (symbol, location)
        """
        node_size = len(self.nodes) * 200
        edge_size = len(self.edges) * 100
        occurrence_size = len(self.occurrences) * 50
        base_overhead = 1000  # dataclass overhead
        
        return node_size + edge_size + occurrence_size + base_overhead
```

### 4.4 Cache Telemetry (P0.1 권장)

```python
@dataclass
class CacheTelemetry:
    """빌드 캐시 통계."""
    
    # Hit counts
    l0_hits: int = 0
    l0_fast_hits: int = 0  # mtime+size로 판정
    l0_hash_hits: int = 0  # hash 비교로 판정
    l1_hits: int = 0
    l2_hits: int = 0
    misses: int = 0
    
    # Performance
    l0_check_time_ms: float = 0.0
    l1_check_time_ms: float = 0.0
    l2_check_time_ms: float = 0.0
    parse_time_ms: float = 0.0
    serialization_time_ms: float = 0.0
    
    # Memory
    l0_entries: int = 0
    l1_entries: int = 0
    l1_bytes: int = 0
    evictions: int = 0
    purged: int = 0
    
    def report(self) -> str:
        """Build summary report."""
        total_requests = self.l0_hits + self.l1_hits + self.l2_hits + self.misses
        
        return f"""
        Cache Report:
        ─────────────────────────────────────
        L0 Hits:     {self.l0_hits:>6} ({self.l0_hits/total_requests*100:.1f}%)
          - Fast:    {self.l0_fast_hits:>6}
          - Hash:    {self.l0_hash_hits:>6}
        L1 Hits:     {self.l1_hits:>6} ({self.l1_hits/total_requests*100:.1f}%)
        L2 Hits:     {self.l2_hits:>6} ({self.l2_hits/total_requests*100:.1f}%)
        Misses:      {self.misses:>6} ({self.misses/total_requests*100:.1f}%)
        ─────────────────────────────────────
        L0 Check:    {self.l0_check_time_ms:.1f}ms
        Parse Time:  {self.parse_time_ms:.1f}ms
        ─────────────────────────────────────
        L0 Entries:  {self.l0_entries}
        L1 Entries:  {self.l1_entries} ({self.l1_bytes/1024/1024:.1f}MB)
        Evictions:   {self.evictions}
        Purged:      {self.purged}
        """
```

---

## 5. Implementation Plan

### Phase 0: Preparation (0.5h)

| Task | Description | Time |
|------|-------------|------|
| 0.1 | 기존 테스트 실행 및 baseline 확보 | 15m |
| 0.2 | 브랜치 생성 (`feat/rfc-039-tiered-cache`) | 5m |
| 0.3 | xxhash 필수 종속성 추가 | 10m |

---

### Phase 1: MemoryCache Enhancement (1.5h) 🔥

**목표**: L1 캐시에 메모리 크기 제한 추가

**파일**: `src/contexts/code_foundation/infrastructure/ir/cache.py`

```python
class MemoryCache(IRCacheBackend):
    def __init__(
        self,
        max_size: int = 500,
        max_bytes: int = 512 * 1024 * 1024,  # [NEW] 512MB
    ):
        self._max_bytes = max_bytes
        self._current_bytes = 0

    def set(self, key: CacheKey, value: Any) -> None:
        with self._lock:
            # [NEW] IRDocument.estimated_size 사용
            if hasattr(value, 'estimated_size'):
                obj_size = value.estimated_size
            else:
                obj_size = len(value.nodes) * 200 + len(value.edges) * 100
            
            # 메모리 크기 기반 eviction
            while self._current_bytes + obj_size > self._max_bytes and self._cache:
                _, evicted = self._cache.popitem(last=False)
                evicted_size = getattr(evicted, 'estimated_size', 1000)
                self._current_bytes -= evicted_size
                self._evictions += 1
            
            # 항목 수 기반 eviction
            while len(self._cache) >= self._max_size and self._cache:
                _, evicted = self._cache.popitem(last=False)
                evicted_size = getattr(evicted, 'estimated_size', 1000)
                self._current_bytes -= evicted_size
                self._evictions += 1
            
            self._cache[key.to_string()] = value
            self._current_bytes += obj_size
```

**추가 작업**:
- `IRDocument.estimated_size` property 추가
- xxhash 필수 종속성으로 변경 (pyproject.toml)

---

### Phase 2: TieredCache Implementation (1.5h) 🔥

**목표**: L1 + L2 통합 Facade 구현

**파일**: `src/contexts/code_foundation/infrastructure/ir/cache.py`

```python
class TieredCache:
    """L1 (Memory) + L2 (Disk) 통합 캐시."""
    
    def __init__(
        self,
        l1_max_size: int = 500,
        l1_max_bytes: int = 512 * 1024 * 1024,
        l2_cache_dir: Path | None = None,
    ):
        self._l1 = MemoryCache(max_size=l1_max_size, max_bytes=l1_max_bytes)
        self._l2 = DiskCache(cache_dir=l2_cache_dir)
        
        # Telemetry
        self._l1_hits = 0
        self._l2_hits = 0
        self._misses = 0
    
    def get(self, file_path: str, content: str) -> Any | None:
        """L1 → L2 순차 조회."""
        key = CacheKey.from_content(file_path, content)
        
        # L1 체크
        result = self._l1.get(key)
        if result is not None:
            self._l1_hits += 1
            return result
        
        # L2 체크
        result = self._l2.get(key)
        if result is not None:
            self._l2_hits += 1
            self._l1.set(key, result)  # Promote to L1
            return result
        
        self._misses += 1
        return None
    
    def set(self, file_path: str, content: str, value: Any) -> None:
        """L1 + L2 동시 저장."""
        key = CacheKey.from_content(file_path, content)
        self._l1.set(key, value)
        self._l2.set(key, value)
    
    def get_telemetry(self) -> dict[str, Any]:
        """Telemetry 데이터 반환."""
        l1_stats = self._l1.stats()
        l2_stats = self._l2.stats()
        
        return {
            "l1_hits": self._l1_hits,
            "l2_hits": self._l2_hits,
            "misses": self._misses,
            "l1_entries": l1_stats.get("size", 0),
            "l1_bytes": l1_stats.get("current_bytes", 0),
            "l1_evictions": l1_stats.get("evictions", 0),
            "l2_entries": l2_stats.get("size", 0),
        }
```

---

### Phase 3: LayeredIRBuilder Stateful Conversion (3h) 🔥

**목표**: L0 캐시 추가 및 Stateful 전환

**핵심 변경**:
1. L0 캐시 + 메타데이터 추가
2. Fast Path (mtime + size) 구현
3. LRU eviction (max_files)
4. Purge orphans 로직
5. GlobalContext 동기화
6. Cache Telemetry 통합
7. Worker-Main 격리 명확화

**파일**: `src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py`

(상세 구현은 Section 4.2 참조)

---

### Phase 4: IncrementalStrategy Cleanup (1h) 🗑️

**삭제 목록**:

| Line | Code | Reason |
|------|------|--------|
| 50 | `DEFAULT_MAX_CACHE_SIZE = 1000` | TieredCache로 대체 |
| 52-56 | `__init__` 캐시 초기화 | L0/L1/L2로 대체 |
| 202-216 | `_update_cache()` | TieredCache로 대체 |
| 218-222 | `clear_cache()` | Builder의 clear_l0()로 대체 |

**약 50줄 삭제**

---

### Phase 5: IRPipeline Integration (0.5h)

**파일**: `src/contexts/code_foundation/infrastructure/ir/pipeline.py`

```python
class IRPipeline:
    def __init__(self, project_root: Path, ...):
        # 공유 Builder (Stateful)
        self._builder: LayeredIRBuilder | None = None
    
    def _get_builder(self) -> LayeredIRBuilder:
        if self._builder is None:
            self._builder = LayeredIRBuilder(project_root=self.project_root)
        return self._builder
```

---

### Phase 6: Test Suite (2.5h)

**테스트 커버리지**:

```python
# Unit Tests
class TestL0Cache:
    def test_fast_path_mtime_size(self): ...
    def test_slow_path_hash_comparison(self): ...
    def test_lru_eviction_max_files(self): ...
    def test_purge_orphans(self): ...

class TestMemoryCacheSizeLimit:
    def test_eviction_on_bytes_limit(self): ...
    def test_estimated_size_usage(self): ...

class TestTieredCache:
    def test_l1_hit(self): ...
    def test_l2_promotion(self): ...
    def test_telemetry(self): ...

# Integration Tests
class TestStatefulBuilder:
    def test_l0_cache_hit_watch_mode(self): ...
    def test_global_context_sync(self): ...
    def test_worker_main_isolation(self): ...
    def test_incremental_on_change(self): ...
```

---

### Phase 7: Documentation & Cleanup (0.5h)

- Handbook 업데이트
- API 문서 (docstrings)
- 미사용 import 제거

---

## 6. Future Work

### P0.1.5: Common Cache Infrastructure (2-3h) [NEW]

공용 캐시 인프라 분리 - Structural IR, Semantic IR 캐시 공통 코드 추출

**목표:**
- 중복 코드 ~120줄 제거
- 재사용 가능한 캐시 프리미티브 제공
- 향후 Remote Cache (Redis/S3) 확장 용이

**디렉토리 구조:**
```
src/contexts/code_foundation/infrastructure/
├── cache/                           # 🆕 공용 캐시 인프라
│   ├── __init__.py
│   ├── core.py                      # BaseDiskCache, BaseCacheStats, CachePort
│   ├── atomic_io.py                 # atomic_write_file, read_with_retry
│   ├── serialization.py             # MsgpackSerializer, PickleSerializer
│   └── checksum.py                  # compute_checksum (xxhash/sha256)
│
└── ir/
    ├── structural_cache.py          # 🔄 StructuralIRCache (extends BaseDiskCache)
    └── semantic_cache.py            # 🔄 SemanticIRCache (extends BaseDiskCache)
```

**공용 모듈:**

| 파일 | 내용 | 추출 원본 |
|------|------|-----------|
| `core.py` | `BaseDiskCache`, `BaseCacheStats`, `CachePort` Protocol | cache.py, semantic_cache.py |
| `atomic_io.py` | `atomic_write_file()`, `read_with_retry()` | 두 캐시의 atomic write 로직 |
| `serialization.py` | `MsgpackSerializer`, `PickleSerializer` wrapper | msgpack/pickle 분기 로직 |
| `checksum.py` | `compute_checksum()`, `compute_hash()` | xxhash/sha256 분기 로직 |

**코드 예시:**

```python
# cache/core.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar, Generic

T = TypeVar("T")

@dataclass
class BaseCacheStats:
    """공용 캐시 통계."""
    hits: int = 0
    misses: int = 0
    write_fails: int = 0
    corrupt_entries: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

class BaseDiskCache(ABC, Generic[T]):
    """공용 디스크 캐시 베이스."""
    
    MAX_RETRIES: int = 3
    RETRY_DELAY_MS: int = 20
    
    @abstractmethod
    def pack(self, value: T) -> bytes: ...
    
    @abstractmethod
    def unpack(self, data: bytes) -> T: ...
    
    def _atomic_write(self, path: Path, data: bytes) -> bool:
        from .atomic_io import atomic_write_file
        return atomic_write_file(path, data, self._cache_dir)
    
    def _read_with_retry(self, path: Path) -> bytes | None:
        from .atomic_io import read_with_retry
        return read_with_retry(path, self.MAX_RETRIES, self.RETRY_DELAY_MS)
```

```python
# cache/atomic_io.py
def atomic_write_file(target: Path, data: bytes, temp_dir: Path) -> bool:
    """Atomic write: tmp file + os.replace."""
    import os, tempfile
    
    tmp_fd, tmp_path = tempfile.mkstemp(dir=temp_dir, prefix=".tmp_")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
        return True
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False
```

**리팩토링 매핑:**

| 기존 (cache.py) | 기존 (semantic_cache.py) | 신규 (cache/) |
|-----------------|-------------------------|---------------|
| `DiskCache._atomic_write` | `DiskSemanticCache.set` atomic 부분 | `atomic_io.atomic_write_file()` |
| `DiskCache.get` retry 없음 | `DiskSemanticCache.get` retry 있음 | `atomic_io.read_with_retry()` |
| `HAS_MSGPACK` 분기 | `HAS_MSGPACK` 분기 | `serialization.MsgpackSerializer` |
| `HAS_XXHASH` 분기 | `HAS_XXHASH` 분기 | `checksum.compute_checksum()` |
| `IRCacheBackend(ABC)` | `SemanticCachePort(ABC)` | `core.BaseDiskCache(ABC)` |

**파일 변경:**

| 파일 | 작업 | 라인 |
|------|------|------|
| `cache/__init__.py` | New | +10 |
| `cache/core.py` | New | +80 |
| `cache/atomic_io.py` | New | +50 |
| `cache/serialization.py` | New | +40 |
| `cache/checksum.py` | New | +30 |
| `ir/cache.py` → `ir/structural_cache.py` | Refactor | -100, +30 |
| `ir/semantic_cache.py` | Refactor | -80, +20 |
| **Total** | | **+260, -180 = net +80** |

---

### P0.2: Advanced Optimizations (4-6h)

| Feature | Description | Impact |
|---------|-------------|--------|
| **Negative Caching** | 분석 실패/빈 파일도 캐싱 | 안정성 |
| **Environmental Context Hash** | Python 버전, config 해싱 | 정확성 |
| **Worker → cache_key only** | IPC 비용 최소화 | 성능 |
| **Async L2 Write** | Background 디스크 쓰기 | 성능 |

### P0.5: Semantic IR Cache (8-10h)

| Feature | Description | Impact |
|---------|-------------|--------|
| **Signature Hash** | Public API만 해싱 (fine-grained) | 연쇄 재분석 방지 |
| **Priority-based Eviction** | 참조 수 기반 LRU | 효율성 |
| **Dependency-aware Invalidation** | 의존성 그래프 기반 | 정확성 |

### P1: Production Hardening (6-8h)

| Feature | Description | Impact |
|---------|-------------|--------|
| **State Snapshotting** | L1 핫 데이터 스냅샷 | Warm start |
| **Structural Sharing** | Flyweight 패턴 | 메모리 40-60% ↓ |
| **Crash Recovery** | WAL 기반 복구 | 안정성 |
| **FileWatcher 연동** | 실시간 캐시 무효화 | 반응성 |

### P2+: Enterprise Features

| Feature | Description | Impact |
|---------|-------------|--------|
| **CAS Storage** | Content-Addressable Storage | 충돌 방지 |
| **Remote Cache** | S3/Redis 백엔드 | 팀 공유 |
| **Lazy Deserialization** | 필요 시 로드 | 초기 로딩 |

---

## 7. Metrics & Success Criteria

### 7.1 Performance Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Cold build | 5.02s | 5.02s | First run |
| Warm L2 build | 3.43s | 3.43s | Second run |
| Watch mode (L0) | 3.43s | <0.05s | No changes |
| L0 check (10K files) | ~100ms+ | <10ms | Fast path |
| Memory (L0) | Unlimited | 2000 files | max_files |
| Memory (L1) | Unlimited | 512MB | max_bytes |

### 7.2 Code Quality Metrics

| Metric | Target |
|--------|--------|
| Dead code removed | ~50 lines |
| Test coverage | >90% |
| Lint errors | 0 |
| Type errors | 0 |

---

## 8. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| L0 메모리 무한 증가 | OOM | High → Low | max_files + Purge |
| L0 check 느림 | 성능 저하 | High → Low | Fast Path (mtime+size) |
| GlobalContext 불일치 | 분석 오류 | Medium | 명시적 동기화 |
| Worker-Main 격리 혼란 | 버그 | Medium | 문서화 + 테스트 |
| L2 캐시 corruption | 빌드 실패 | Low | Checksum + 자동 재생성 |

---

## 9. Appendix

### A. File Changes Summary

**P0.1: Tiered Cache Core**

| File | Action | Lines |
|------|--------|-------|
| `cache.py` | Modify | +150 |
| `layered_ir_builder.py` | Modify | +150 |
| `models/document.py` | Modify | +15 |
| `incremental.py` | Modify | -50 |
| `pipeline.py` | Modify | +20 |
| `test_tiered_cache.py` | New | +200 |
| `test_stateful_builder.py` | New | +150 |
| **Subtotal** | | **+635, -50** |

**P0.1.5: Common Cache Infrastructure**

| File | Action | Lines |
|------|--------|-------|
| `cache/__init__.py` | New | +10 |
| `cache/core.py` | New | +80 |
| `cache/atomic_io.py` | New | +50 |
| `cache/serialization.py` | New | +40 |
| `cache/checksum.py` | New | +30 |
| `ir/cache.py` → `structural_cache.py` | Refactor | +30, -100 |
| `ir/semantic_cache.py` | Refactor | +20, -80 |
| `tests/cache/test_common_infra.py` | New | +100 |
| **Subtotal** | | **+360, -180** |

**Grand Total: +995, -230 = net +765**

### B. Dependencies

```toml
# pyproject.toml
[project.dependencies]
xxhash = ">=3.0.0"  # 필수 (성능)
msgpack = ">=1.0.0"  # 필수 (직렬화)
```

### C. Configuration

```python
# 기본 설정
L0_MAX_FILES = 2000      # 파일 수 제한
L1_MAX_SIZE = 500        # 항목 수 제한
L1_MAX_BYTES = 512 * 1024 * 1024  # 512MB
```

---

## 10. Approval

| Reviewer | Status | Date |
|----------|--------|------|
| Architecture | Pending | |
| Performance | Pending | |
| Security | Pending | |
