# RFC-038: Semantic IR Cache (Final)

## Status: ✅ Implemented
## Author: Semantica Team
## Created: 2025-12-21
## Completed: 2025-12-22
## Priority: P0.5
## Estimated: 2-3h → Actual: ~2h

---

## 1. Executive Summary

**한 줄 요약:**
> Semantic IR 빌드 단계의 중복 연산을 제거하고, Warm-run 시 0.2~0.4s 이내의 응답성을 확보하기 위한 파일 단위 영속성 캐싱 시스템

**핵심 원칙:**
```
Content-based Invalidation + Deterministic ID = 증분 업데이트의 정확성 + 효율성
file_path 키 제외 → Rename/Move 내성
pickle 금지 → msgpack + tuple schema = 호환성 + 속도
```

**목표:**
- 성능: Semantic IR 2.17s → 0.2~0.4s (cache hit 시)
- 안전성: Checksum 검증 + atomic write + corrupt fallback
- 증분성: 수정된 파일만 재계산 O(N)

---

## 2. Core Invariants (설계 핵심 불변식)

캐시 시스템의 신뢰성을 보장하기 위한 3가지 불변 원칙:

### 2.1 ID Determinism
동일 파일 내용 및 설정 환경에서 생성되는 모든 내부 ID(expr, block, var, fn)는 실행 시점과 무관하게 **결정론적(Deterministic)**이어야 함.

### 2.2 File-Local Scope
Semantic IR 캐시 엔트리는 **파일 내부 정보에 한정**. Cross-file resolution 결과는 별도의 병합(Merge) 단계에서 처리하며 캐시 키의 무결성을 해치지 않음.

### 2.3 Incremental O(N)
수정된 파일의 개수가 N일 때, 재계산 비용은 프로젝트 전체 크기와 무관하게 **O(N)**에 수렴.

---

## 3. 문제 정의

### 3.1 현재 상태

**P0 완료 후 (Structural IR 캐시):**
```
Total: 5.02s → 3.43s (31.7% 개선)
├─ Structural IR: 1.69s → 0.1s ✅ 캐시됨
├─ Semantic IR:   2.17s → 2.17s ❌ 캐시 안 됨
└─ Others:        1.16s → 1.16s
```

**Semantic IR 구성 요소 (2.17s):**
```
Layer 5: Semantic IR
├─ CFG (Control Flow Graph)    ~0.4s
├─ DFG (Data Flow Graph)       ~0.8s
├─ BFG (Block Flow Graph)      ~0.3s
├─ Type inference              ~0.4s
└─ Signatures                  ~0.3s
```

### 3.2 P0.5 목표

**Semantic IR 캐시 추가 후 (보수적 추정):**
```
Total: 5.02s → ~3.15s (warm)
├─ Structural IR: 0.1s ✅
├─ Semantic IR:   0.2~0.4s ✅ 캐시 추가!
└─ Others:        1.16s
```

---

## 4. 기술 세부 명세

### 4.1 캐시 키 설계 (file_path 제외)

**핵심 변경: Rename/Move 내성을 위해 file_path를 키에서 제외**

```python
def generate_cache_key(content_hash: str, structural_digest: str, config_hash: str) -> str:
    """
    RFC-038 준수: file_path를 제외한 Content-based Key 생성
    Rename/Move에도 캐시 히트를 보장함.

    $CacheKey = xxh3_128(content_hash + structural_digest + config_hash)$
    """
    combined = f"{content_hash}{structural_digest}{config_hash}"
    return xxhash.xxh3_128_hexdigest(combined)
```

**키 구성 요소:**

| 요소 | 설명 | 이유 |
|------|------|------|
| `content_hash` | 파일 내용 SHA-256/xxh3 | Primary key |
| `structural_digest` | Structural IR의 packed bytes xxh3 | AST 변경 감지 |
| `config_hash` | 결과에 영향 주는 옵션만 (whitelist) | Miss 최소화 |

**config_hash Whitelist (결과에 영향 주는 것만):**
- `semantic_mode` (QUICK/FULL)
- `dfg_threshold`
- `feature_flags`
- `python_version`

**❌ 키에서 제외:**
- `file_path` - Rename/Move 내성 확보
- `timestamp` - 불필요한 miss 유발
- `parallel_workers` - 결과에 영향 없음

### 4.2 경로 독립성 (Project-relative Path)

페이로드 내부에 저장되는 경로는 **Project Root 기준 상대 경로**로 정규화:

```python
# ✅ 올바른 저장
"src/utils.py"

# ❌ 잘못된 저장 (절대 경로)
"/Users/kim/semantica/src/utils.py"
```

**이점:**
- 레포지토리 위치 이동해도 캐시 유효
- 동료가 생성한 캐시 공유 가능

### 4.3 저장 구조 및 Binary Layout

**디렉토리 구조 (버전별 격리):**
```
~/.cache/codegraph/sem_ir/
├── v1/                    # engine_version
│   └── s1/               # schema_version
│       ├── abc123...def.sem
│       └── 789xyz...ghi.sem
└── v2/
    └── s1/
```

**Binary Layout (26-byte Header + Payload):**
```
┌─────────────────────────────────────────────────────────────┐
│ Header (26 bytes)                                           │
├─────────────┬──────────────┬───────────────┬───────────────┤
│ Magic (4B)  │ Schema (2B)  │ PayloadLen(4B)│ Checksum(16B) │
│ "SSEM"      │ 0x0001       │ uint32        │ xxh3_128      │
├─────────────┴──────────────┴───────────────┴───────────────┤
│ Payload (msgpack)                                           │
│ - relative_path: str                                        │
│ - data: tuple[tuple[int, ...], ...]                        │
└─────────────────────────────────────────────────────────────┘
```

**Header Format:**
```python
HEADER_FORMAT = ">4sH I 16s"  # big-endian: magic(4) + schema(2) + len(4) + checksum(16)
MAGIC = b"SSEM"  # Smart SEmantic Map
```

### 4.4 Pack/Unpack (tuple schema v1)

```python
import struct
import xxhash
import msgpack
from pathlib import Path

SCHEMA_VERSION = 1
HEADER_FORMAT = ">4sH I 16s"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 26 bytes
MAGIC = b"SSEM"


def pack_semantic_result(result: "SemanticResult", relative_path: str) -> bytes:
    """
    Pack semantic result to msgpack bytes with header.

    Layout (tuple schema - no dict keys):
    - cfg_blocks: [(id, start, end, kind), ...]
    - cfg_edges: [(src, dst, edge_kind), ...]
    - dfg_defs: [(var_id, def_node_id), ...]
    - dfg_uses: [(var_id, (use_node_ids...)), ...]
    - expressions: [(expr_id, kind, (operands...)), ...]
    - signatures: [(fn_id, (params...), return_type), ...]
    """
    # Payload: relative_path + data
    payload_data = {
        "p": relative_path,  # project-relative path (검증용)
        "d": (
            # CFG
            tuple((b.id, b.start, b.end, b.kind.value) for b in result.cfg_blocks),
            tuple((e.src, e.dst, e.kind.value) for e in result.cfg_edges),
            # DFG
            tuple((d.var_id, d.def_node) for d in result.dfg_defs),
            tuple((u.var_id, tuple(u.use_nodes)) for u in result.dfg_uses),
            # Expressions
            tuple((e.id, e.kind.value, tuple(e.operands)) for e in result.expressions),
            # Signatures
            tuple((s.fn_id, tuple(s.params), s.return_type) for s in result.signatures),
        ),
    }

    packed_body = msgpack.packb(payload_data, use_bin_type=True)

    # Header
    checksum = xxhash.xxh3_128_digest(packed_body)
    header = struct.pack(
        HEADER_FORMAT,
        MAGIC,
        SCHEMA_VERSION,
        len(packed_body),
        checksum,
    )

    return header + packed_body


def unpack_semantic_result(data: bytes) -> tuple[str, "SemanticResult"]:
    """
    Unpack semantic result from bytes with header validation.

    Returns:
        (relative_path, SemanticResult)

    Raises:
        CacheCorruptError: Header/checksum validation failed
        CacheSchemaVersionMismatch: Schema version mismatch
    """
    if len(data) < HEADER_SIZE:
        raise CacheCorruptError("Header too short")

    # Parse header
    magic, schema_ver, payload_len, stored_checksum = struct.unpack(
        HEADER_FORMAT, data[:HEADER_SIZE]
    )

    # Validate magic
    if magic != MAGIC:
        raise CacheCorruptError(f"Invalid magic: {magic}")

    # Validate schema version
    if schema_ver != SCHEMA_VERSION:
        raise CacheSchemaVersionMismatch(schema_ver, SCHEMA_VERSION)

    # Extract payload
    payload = data[HEADER_SIZE:HEADER_SIZE + payload_len]

    # Validate checksum
    actual_checksum = xxhash.xxh3_128_digest(payload)
    if actual_checksum != stored_checksum:
        raise CacheCorruptError("Checksum mismatch")

    # Unpack msgpack
    unpacked = msgpack.unpackb(payload, use_list=True, raw=False)
    relative_path = unpacked["p"]
    cfg_blocks, cfg_edges, dfg_defs, dfg_uses, exprs, sigs = unpacked["d"]

    # Reconstruct objects (Direct Injection to Arena)
    result = SemanticResult(
        cfg_blocks=[CFGBlock(id=b[0], start=b[1], end=b[2], kind=BlockKind(b[3]))
                    for b in cfg_blocks],
        cfg_edges=[CFGEdge(src=e[0], dst=e[1], kind=EdgeKind(e[2]))
                   for e in cfg_edges],
        # ... etc
    )

    return relative_path, result
```

---

## 5. 구현 설계

### 5.1 SemanticIRCache 클래스

```python
import os
import struct
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import msgpack
import xxhash


class SemanticEngineVersion(str, Enum):
    """Semantic IR builder version."""
    V1_0_0 = "v1"

    @classmethod
    def current(cls) -> str:
        return cls.V1_0_0.value


class SemanticSchemaVersion(str, Enum):
    """Cache payload schema version."""
    S1 = "s1"

    @classmethod
    def current(cls) -> str:
        return cls.S1.value


@dataclass
class SemanticCacheStats:
    """Cache statistics for monitoring."""
    hits: int = 0
    misses: int = 0
    write_fails: int = 0
    schema_mismatches: int = 0
    corrupt_entries: int = 0
    disk_full_errors: int = 0
    total_saved_ms: float = 0.0  # 캐시로 절약한 추정 시간

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class SemanticIRCache:
    """
    RFC-038: Semantic IR Cache.

    Features:
    - Content-based stable key (file_path 제외, Rename/Move 내성)
    - xxh3 checksum validation (26-byte header)
    - msgpack + tuple schema (no pickle)
    - Atomic write (tmp + rename)
    - Corrupt entry fallback with auto-delete
    - Version-based directory isolation
    - Retry with backoff for race conditions

    Thread-safety:
    - Read: Concurrent OK (retry on transient errors)
    - Write: Atomic (file-level)
    - Stats: Lock-protected
    """

    MAGIC = b"SSEM"
    HEADER_FORMAT = ">4sH I 16s"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 26 bytes
    SCHEMA_VERSION = 1

    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 20

    def __init__(
        self,
        base_dir: Path | None = None,
        engine_version: str | None = None,
        schema_version: str | None = None,
    ):
        if base_dir is None:
            base_dir = Path.home() / ".cache" / "codegraph" / "sem_ir"

        if engine_version is None:
            engine_version = SemanticEngineVersion.current()
        if schema_version is None:
            schema_version = SemanticSchemaVersion.current()

        # Version-isolated directory
        self._cache_dir = base_dir / engine_version / schema_version
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._stats = SemanticCacheStats()

    def generate_key(
        self,
        content_hash: str,
        structural_digest: str,
        config_hash: str,
    ) -> str:
        """
        Generate cache key (file_path excluded for Rename/Move tolerance).

        Key = xxh3_128(content_hash + structural_digest + config_hash)
        """
        combined = f"{content_hash}{structural_digest}{config_hash}"
        return xxhash.xxh3_128_hexdigest(combined)

    def get(self, key: str) -> Optional[tuple[str, "SemanticResult"]]:
        """
        Get cached semantic IR with retry for transient errors.

        Returns:
            (relative_path, SemanticResult) if hit, None if miss
        """
        cache_path = self._cache_dir / f"{key}.sem"

        if not cache_path.exists():
            with self._lock:
                self._stats.misses += 1
            return None

        # Retry with backoff for race conditions
        for attempt in range(self.MAX_RETRIES):
            try:
                data = cache_path.read_bytes()
                relative_path, result = self._unpack(data)

                with self._lock:
                    self._stats.hits += 1
                return (relative_path, result)

            except CacheSchemaVersionMismatch as e:
                with self._lock:
                    self._stats.schema_mismatches += 1
                cache_path.unlink(missing_ok=True)
                return None

            except CacheCorruptError:
                with self._lock:
                    self._stats.corrupt_entries += 1
                cache_path.unlink(missing_ok=True)
                return None

            except (PermissionError, FileNotFoundError):
                # Transient error (e.g., file being replaced)
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_MS / 1000)
                    continue
                with self._lock:
                    self._stats.misses += 1
                return None

            except Exception:
                with self._lock:
                    self._stats.corrupt_entries += 1
                cache_path.unlink(missing_ok=True)
                return None

        with self._lock:
            self._stats.misses += 1
        return None

    def set(
        self,
        key: str,
        result: "SemanticResult",
        relative_path: str,
    ) -> bool:
        """
        Cache semantic IR result with atomic write.

        Returns:
            True if stored successfully, False otherwise
        """
        cache_path = self._cache_dir / f"{key}.sem"

        # Write-once: skip if already exists
        if cache_path.exists():
            return True

        try:
            data = self._pack(result, relative_path)

            # Ensure directory exists (may have been deleted)
            self._cache_dir.mkdir(parents=True, exist_ok=True)

            # Atomic write
            tmp_fd, tmp_path = tempfile.mkstemp(
                suffix=".sem",
                prefix=".tmp_",
                dir=self._cache_dir,
            )

            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                os.replace(tmp_path, cache_path)
                return True

            except Exception:
                # Cleanup tmp on error
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

        except OSError as e:
            # Disk full or permission error
            if e.errno in (28, 13):  # ENOSPC, EACCES
                with self._lock:
                    self._stats.disk_full_errors += 1
            else:
                with self._lock:
                    self._stats.write_fails += 1
            return False

        except Exception:
            with self._lock:
                self._stats.write_fails += 1
            return False

    def _pack(self, result: "SemanticResult", relative_path: str) -> bytes:
        """Pack to msgpack with header."""
        return pack_semantic_result(result, relative_path)

    def _unpack(self, data: bytes) -> tuple[str, "SemanticResult"]:
        """Unpack from msgpack with header validation."""
        return unpack_semantic_result(data)

    def clear(self) -> None:
        """Clear all cached entries."""
        for cache_file in self._cache_dir.glob("*.sem"):
            cache_file.unlink(missing_ok=True)

        # Clean tmp files
        for tmp_file in self._cache_dir.glob(".tmp_*.sem"):
            tmp_file.unlink(missing_ok=True)

        with self._lock:
            self._stats = SemanticCacheStats()

    def stats(self) -> dict[str, int | float]:
        """Get cache statistics."""
        with self._lock:
            return {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "hit_rate": self._stats.hit_rate,
                "write_fails": self._stats.write_fails,
                "schema_mismatches": self._stats.schema_mismatches,
                "corrupt_entries": self._stats.corrupt_entries,
                "disk_full_errors": self._stats.disk_full_errors,
                "total_saved_ms": self._stats.total_saved_ms,
            }

    def get_telemetry_report(self, total_files: int) -> dict:
        """
        Get telemetry report for logging/debugging.

        Returns:
            {
                "total_files": 180,
                "cache_hits": 150,
                "cache_misses": 30,
                "hit_rate": 0.833,
                "total_saved_ms": 2500.0,
            }
        """
        stats = self.stats()
        return {
            "total_files": total_files,
            "cache_hits": stats["hits"],
            "cache_misses": stats["misses"],
            "hit_rate": stats["hit_rate"],
            "total_saved_ms": stats["total_saved_ms"],
        }


# Global cache singleton
_semantic_cache: SemanticIRCache | None = None


def get_semantic_cache() -> SemanticIRCache:
    """Get global semantic IR cache."""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticIRCache()
    return _semantic_cache


def reset_semantic_cache() -> None:
    """Reset global cache (for testing)."""
    global _semantic_cache
    _semantic_cache = None
```

### 5.2 Worker 통합

```python
# layered_ir_builder.py 수정

def _build_semantic_ir_worker(args: tuple) -> bytes:
    """
    Worker function for parallel semantic IR build.

    RFC-038: Cache integration with Fast-path bypass
    1. Generate cache key (file_path excluded)
    2. Try cache hit → Builder 로직 완전 우회
    3. If miss, build semantic IR
    4. Store in cache
    5. Return packed result
    """
    ir_doc_bytes, mode_value, config_dict, project_root = args

    # Unpack inputs
    ir_doc = unpack_ir_document(ir_doc_bytes)
    mode = SemanticIrBuildMode(mode_value)
    config = BuildConfig(**config_dict)

    # Compute relative path
    relative_path = compute_relative_path(ir_doc.file_path, project_root)

    # 1. Generate cache key (file_path EXCLUDED)
    cache = get_semantic_cache()
    key = cache.generate_key(
        content_hash=ir_doc.content_hash,
        structural_digest=compute_structural_digest(ir_doc),
        config_hash=compute_config_hash(mode, config),
    )

    # 2. Try cache - Fast-path (Builder 완전 우회)
    cached = cache.get(key)
    if cached is not None:
        cached_path, result = cached
        # Optional: path 검증 (paranoid mode)
        # if cached_path != relative_path:
        #     logger.warning(f"Path mismatch: {cached_path} vs {relative_path}")
        return pack_semantic_result(result, relative_path)

    # 3. Cache miss - build semantic IR
    t_start = time.time()
    builder = DefaultSemanticIrBuilder()
    result = builder.build(ir_doc, mode, config)
    build_time_ms = (time.time() - t_start) * 1000

    # 4. Store in cache (with build time for telemetry)
    cache.set(key, result, relative_path)

    # 5. Return result
    return pack_semantic_result(result, relative_path)


def compute_structural_digest(ir_doc: "IRDocument") -> str:
    """
    Compute stable digest over structural IR.

    SOTA: Packed bytes 직접 해싱 (정렬 오버헤드 최소화)
    """
    hasher = xxhash.xxh3_128()

    # 이미 packed된 bytes가 있으면 그대로 사용
    if hasattr(ir_doc, '_packed_bytes') and ir_doc._packed_bytes:
        hasher.update(ir_doc._packed_bytes)
    else:
        # Fallback: Sort and hash
        for node in sorted(ir_doc.nodes, key=lambda n: n.id):
            hasher.update(f"{node.id}:{node.kind.value}:{node.name}".encode())
        for edge in sorted(ir_doc.edges, key=lambda e: (e.source_id, e.target_id)):
            hasher.update(f"{edge.source_id}:{edge.target_id}:{edge.kind.value}".encode())

    return hasher.hexdigest()


def compute_config_hash(mode: "SemanticIrBuildMode", config: "BuildConfig") -> str:
    """
    Compute hash of config options that affect semantic IR result.

    Whitelist: 결과에 영향 주는 옵션만 포함
    """
    hasher = xxhash.xxh3_64()

    # Mode
    hasher.update(mode.value.encode())

    # Config options (whitelist)
    hasher.update(str(config.dfg_function_loc_threshold).encode())
    hasher.update(str(config.cfg).encode())
    hasher.update(str(config.dfg).encode())
    hasher.update(str(config.ssa).encode())
    hasher.update(str(config.expressions).encode())

    return hasher.hexdigest()
```

---

## 6. 실행 모델

### 6.1 Fast-path (Warm-run)

캐시 히트 시 **Semantic Builder 로직을 완전히 우회(Bypass)**:

```
1. PersistentResultStore에서 페이로드 로드
2. Header checksum 검증 (26 bytes만 읽어도 유효성 판별)
3. msgpack 언팩 결과를 중간 dataclass 생성 없이
   Arena 메모리에 직접 주입(Direct Injection)
4. 객체 재구성 오버헤드 최소화
```

### 6.2 증분 업데이트 (Reactive Update)

```
File-scoped Invalidation:
├─ 파일 수정 시: content_hash 변경
├─ 해당 파일만: cache miss 발생
└─ 재빌드: O(1) per file

Structural Boundary:
├─ 주석만 변경: content_hash 변경 O, structural_digest 변경 X
├─ Semantic 레이어: 불필요한 재계산 방어
└─ (Future: 주석 무시 옵션)
```

---

## 7. 테스트 전략

### 7.1 Correctness (정확성)

```python
class TestSemanticCacheCorrectness:
    """Correctness tests."""

    def test_cache_hit_produces_identical_result(self):
        """동일 입력에서 cache on/off 결과가 동일 (Determinism 핵심)."""

    def test_config_change_causes_miss(self):
        """config/mode 변경 시 miss 발생."""

    def test_content_change_causes_miss(self):
        """파일 내용 변경 시 miss 발생."""

    def test_rename_preserves_cache_hit(self):
        """파일 rename 시에도 cache hit (file_path 키 제외 검증)."""
```

### 7.2 Robustness (견고성)

```python
class TestSemanticCacheRobustness:
    """Robustness tests."""

    def test_cache_dir_deleted_auto_recovery(self):
        """캐시 디렉토리 삭제 후 자동 복구."""

    def test_corrupt_entry_graceful_fallback(self):
        """corrupted entry가 있어도 graceful fallback + 자동 삭제."""

    def test_schema_version_mismatch_invalidates(self):
        """Schema version 변경 시 자동 무효화."""

    def test_disk_full_graceful_degradation(self):
        """디스크 풀 시에도 시스템 죽지 않음."""

    def test_concurrent_access_retry(self):
        """Race condition 시 retry 동작."""
```

### 7.3 Performance (성능)

```python
class TestSemanticCachePerformance:
    """Performance tests."""

    @pytest.mark.benchmark
    def test_warm_run_semantic_phase_fast(self):
        """Warm run: 2.17s → 0.2~0.4s."""

    @pytest.mark.benchmark
    def test_header_validation_fast(self):
        """Header validation: O(1), 26 bytes만 읽음."""
```

---

## 8. 구현 계획

### 8.1 P0.5 Scope (2-3h)

```
Step 1: Core Implementation (45min)
├─ SemanticCacheKey (file_path excluded)
├─ pack_semantic_result() - tuple schema v1
├─ unpack_semantic_result() - with header validation
└─ CacheCorruptError, CacheSchemaVersionMismatch

Step 2: SemanticIRCache 클래스 (45min)
├─ get() - cache lookup with retry
├─ set() - atomic write with disk full handling
├─ stats() - telemetry
└─ Version-isolated directory structure

Step 3: Worker 통합 (30min)
├─ _build_semantic_ir_worker cache integration
├─ compute_structural_digest()
├─ compute_config_hash()
└─ Integration test

Step 4: Validation (30min)
├─ Benchmark: warm vs cold
├─ Correctness: cache on/off identical
└─ Rename tolerance test
```

### 8.2 파일 변경

```
src/contexts/code_foundation/infrastructure/ir/
├── semantic_cache.py                  (NEW, ~400 lines)
│   ├── SemanticIRCache
│   ├── pack_semantic_result()
│   ├── unpack_semantic_result()
│   └── Helper functions
│
└── layered_ir_builder.py              (+50 lines)
    ├─ _build_semantic_ir_worker cache integration
    ├─ compute_structural_digest()
    └─ compute_config_hash()

tests/unit/ir/
└── test_semantic_cache.py             (NEW, ~250 lines)
    ├── TestSemanticCacheCorrectness (6 tests)
    ├── TestSemanticCacheRobustness (5 tests)
    └── TestSemanticCachePerformance (3 tests)
```

---

## 9. 관측성 (Observability)

### 9.1 Telemetry Report

실행 종료 시점에 다음 정보를 로그/JSON으로 출력:

```json
{
  "semantic_cache": {
    "total_files": 180,
    "cache_hits": 150,
    "cache_misses": 30,
    "hit_rate": 0.833,
    "total_saved_ms": 2500.0,
    "write_fails": 0,
    "corrupt_entries": 0
  }
}
```

### 9.2 Debug Metadata

캐시 엔트리 내부에 디버깅용 메타데이터 포함:
- `codegraph_version`: 생성 시점의 버전
- `created_at`: 타임스탬프 (ISO 8601)

---

## 10. CLI Commands (Future: P1)

```bash
# 전체 캐시 삭제
codegraph cache clear --all

# 오래된 캐시만 삭제 (30일 이상)
codegraph cache clear --expired

# Semantic IR 캐시만 삭제
codegraph cache clear --semantic

# 캐시 정보 요약
codegraph cache info
# Output:
# Semantic IR Cache:
#   Location: ~/.cache/codegraph/sem_ir/v1/s1/
#   Entries: 1,234
#   Size: 45.6 MB
#   Oldest: 2025-12-01
```

---

## 11. 기대 효과

### 11.1 성능 개선 (보수적)

| Metric | Before | After | 개선 |
|--------|--------|-------|------|
| Semantic IR (cold) | 2.17s | 2.17s | 0% |
| Semantic IR (warm) | 2.17s | 0.2~0.4s | 80~90% |
| Total (warm) | 3.43s | ~3.15s | ~8% |

### 11.2 안정성

| 항목 | 방어 |
|------|------|
| Checksum 불일치 | 자동 삭제 + rebuild |
| Schema version 변경 | 디렉토리 격리 |
| Disk full | Graceful degradation (캐시 건너뜀) |
| Race condition | Retry with backoff |

---

## 12. Future Work (P1+)

### 12.1 P1: Repo-level Merge 캐싱

파일 단위 캐시 이후의 병목인 interproc/collection edge merge 증분화.

### 12.2 P1: Admission Control

빌드 시간이 5ms 미만인 작은 파일은 캐시 저장 대상에서 제외하여 I/O 오버헤드 방지.

### 12.3 P1: LZ4 압축 (Optional)

I/O Bound 환경에서 고속 압축 적용:
- Header에 `COMPRESSION_TYPE` 필드 1바이트 추가
- LZ4: 3~5배 압축, 압축/해제 속도가 디스크 I/O보다 빠름

### 12.4 P2: Eviction Policy

- mtime 기반 LRU 정리
- max_size_mb 제한

### 12.5 P2: Negative Cache

파싱 실패 등 반복적 오류 케이스에 대한 TTL 기반 캐싱.

### 12.6 P2: Remote Cache (공유 캐시)

S3/Redis 기반 팀 공유 캐시 (Bazel/Nx 스타일).

### 12.7 P3: Tiered Storage (SQLite Hybrid)

수백만 파일 대응:
- 작은 결과물(< 10KB): SQLite BLOB
- 큰 결과물: 개별 파일

---

## 13. Dependencies

### 13.1 추가 라이브러리

```toml
# pyproject.toml
[project.dependencies]
xxhash = ">=3.4.0"   # Fast non-crypto hash (이미 cache.py에서 사용)
msgpack = ">=1.0.0"  # Binary serialization (이미 cache.py에서 사용)
```

### 13.2 기존 의존성

- `src/contexts/code_foundation/infrastructure/ir/cache.py` (Structural IR cache 패턴)
- `src/contexts/code_foundation/domain/semantic_ir/` (SemanticResult 정의)

---

## 14. 결론

### 14.1 핵심 요약

| 항목 | 내용 |
|------|------|
| **목표** | Semantic IR 캐시로 2.17s → 0.2~0.4s |
| **키 설계** | file_path 제외 (Rename/Move 내성) |
| **포맷** | 26-byte header + msgpack tuple schema |
| **안전성** | xxh3 checksum + atomic write + retry |
| **예상 시간** | 2-3h |

### 14.2 Priority Matrix

| 우선순위 | 항목 | 예상 시간 | 예상 개선 |
|----------|------|-----------|-----------|
| **P0.5** | Semantic IR Cache (이 RFC) | 2-3h | -2.17s (warm) |
| P1 | Bootstrap 최적화 | 4h | -0.86s |
| P1 | Repo-level Merge 캐싱 | 4h | -0.3s |
| P1 | Admission Control | 2h | I/O 감소 |
| P2 | Eviction Policy | 2h | 디스크 관리 |
| P2 | LZ4 압축 | 2h | I/O 감소 |
| P3 | Remote Cache | 8h | 팀 공유 |

---

**Last Updated:** 2025-12-22
**Status:** ✅ Implemented

---

## 15. Implementation Summary

### 15.1 Files Created/Modified

| File | Type | Lines | Description |
|------|------|-------|-------------|
| `src/contexts/code_foundation/infrastructure/ir/semantic_cache.py` | NEW | ~1100 | Core cache implementation |
| `src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py` | MOD | +150 | Worker integration |
| `tests/unit/code_foundation/infrastructure/ir/test_semantic_cache.py` | NEW | ~1200 | 59 unit tests |

### 15.2 Test Coverage

```
=================== 59 passed in 0.35s ===================

✅ TestSemanticCacheResult (2 tests)
✅ TestSemanticCacheStats (3 tests)
✅ TestVersionEnums (3 tests)
✅ TestExceptions (3 tests)
✅ TestHeaderConstants (3 tests)
✅ TestPackUnpack (8 tests)
✅ TestCacheKeyGeneration (5 tests)
✅ TestDiskCacheBasicOperations (4 tests)
✅ TestDiskCacheRobustness (4 tests)
✅ TestDiskCacheAtomicWrite (2 tests)
✅ TestDiskCacheConcurrency (3 tests)
✅ TestGlobalSingleton (4 tests)
✅ TestRenameTolerance (2 tests)
✅ TestConfigInvalidation (2 tests)
✅ TestVersionIsolation (2 tests)
✅ TestPerformance (3 tests)
✅ TestEdgeCases (3 tests)
✅ TestRealModelIntegration (3 tests) - CFG/BFG roundtrip
```

### 15.3 Key Features Implemented

- ✅ **Content-based Key** (file_path excluded for Rename/Move tolerance)
- ✅ **26-byte Header** with xxh3_128 checksum validation
- ✅ **msgpack + tuple schema** (no pickle)
- ✅ **Atomic write** (tmp file + os.replace)
- ✅ **Retry with backoff** for race conditions
- ✅ **Version-isolated directories** (engine_version/schema_version)
- ✅ **Hexagonal Architecture** (SemanticCachePort + DiskSemanticCache adapter)
- ✅ **Thread-safe singleton** with lazy initialization
- ✅ **Observability** (SemanticCacheStats with hit_rate, saved_ms)
- ✅ **Worker Integration** (parallel + sequential paths)

### 15.4 Usage Example

```python
from src.contexts.code_foundation.infrastructure.ir.semantic_cache import (
    get_semantic_cache,
    SemanticCacheResult,
)

# Get cache singleton
cache = get_semantic_cache()

# Generate key (file_path excluded!)
key = cache.generate_key(
    content_hash="abc123...",
    structural_digest="def456...",
    config_hash="ghi789",
)

# Cache hit?
result = cache.get(key)
if result is not None:
    # Fast path: use cached CFG/BFG/Expressions
    pass
else:
    # Build semantic IR
    result = build_semantic_ir(...)
    cache.set(key, result)

# Check stats
print(cache.stats())
# {"hits": 150, "misses": 30, "hit_rate": 0.833, ...}
```
