# RFC-039: Tiered IR Cache - Usage Guide

## Quick Start

### Watch Mode (274x faster)

```python
from src.contexts.code_foundation.infrastructure.ir.pipeline import IRPipeline

pipeline = IRPipeline(project_root)

# First build (cold) - 10s
result1 = await pipeline.build_incremental(files)

# Watch mode (hot) - 0.05s (200x faster!)
result2 = await pipeline.build_incremental(files)
result3 = await pipeline.build_incremental(files)
```

---

## Architecture

### 3-Tier Cache

```
L0 (Builder State): 2000 files, Fast Path (mtime+size)
  ↓ miss
L1 (MemoryCache): 500 entries, 512MB, ~0.1ms
  ↓ miss
L2 (DiskCache): Persistent, ~1-5ms
  ↓ miss
Build from source
```

---

## Configuration

### L0 Cache (Builder State)

```python
from src.contexts.code_foundation.infrastructure.ir.layered_ir_builder import (
    LayeredIRBuilder,
    LayeredIRConfig,
)

config = LayeredIRConfig(
    l0_max_files=2000,  # Max files in L0 (default: 2000)
)

builder = LayeredIRBuilder(project_root, config=config)
```

### L1/L2 Cache (TieredCache)

```python
# layered_ir_builder.py:__init__
from src.contexts.code_foundation.infrastructure.ir.cache import TieredCache

self._tiered_cache = TieredCache(
    l1_max_size=500,              # Max entries
    l1_max_bytes=512*1024*1024,   # 512MB
    l2_cache_dir=Path("~/.cache/codegraph/ir"),
)
```

---

## Monitoring

### Cache Telemetry

```python
telemetry = await builder.get_l0_telemetry()

print(f"L0 Hits: {telemetry['l0_hits']}")
print(f"L0 Fast Hits: {telemetry['l0_fast_hits']}")  # mtime+size
print(f"L0 Hash Hits: {telemetry['l0_hash_hits']}")  # content hash
print(f"L1 Hit Rate: {telemetry['l1_hit_rate']:.1%}")
print(f"L2 Hit Rate: {telemetry['l2_hit_rate']:.1%}")
print(f"L1 Size: {telemetry['l1_bytes']/1024/1024:.1f} MB")
```

### Prometheus Metrics (P0.2)

```python
from src.contexts.code_foundation.infrastructure.monitoring.cache_metrics import (
    record_cache_telemetry,
    get_cache_summary,
)

# Record to Prometheus
telemetry = await builder.get_l0_telemetry()
record_cache_telemetry(telemetry, build_duration=5.2)

# Human-readable summary
print(get_cache_summary(telemetry))
```

---

## Performance Tuning

### Scenario 1: OOM (Out of Memory)

**증상:** 메모리 사용량 계속 증가

**해결:**
```python
# Reduce L0 size
config = LayeredIRConfig(l0_max_files=1000)  # Default: 2000

# Reduce L1 size
builder._tiered_cache._l1._max_bytes = 256*1024*1024  # 256MB (default: 512MB)
```

### Scenario 2: Slow Watch Mode

**증상:** Watch mode가 예상보다 느림 (>100ms)

**진단:**
```python
telemetry = await builder.get_l0_telemetry()

# Check Fast Path ratio
fast_ratio = telemetry['l0_fast_hits'] / telemetry['l0_hits']
if fast_ratio < 0.9:
    print("⚠️ Too many hash checks (Slow Path)")
    print("   Possible causes:")
    print("   - File timestamps unstable (network drive?)")
    print("   - Touch commands changing mtime")
```

**해결:**
- 로컬 디스크 사용 (network drive 회피)
- Build tool이 mtime 변경하지 않도록 설정

### Scenario 3: Low Hit Rate

**증상:** L0/L1/L2 hit rate < 50%

**진단:**
```python
telemetry = await builder.get_l0_telemetry()

if telemetry['l1_hit_rate'] < 0.5:
    print(f"⚠️ Low L1 hit rate: {telemetry['l1_hit_rate']:.1%}")
    print(f"   L1 evictions: {telemetry['l1_evictions']}")
    print(f"   L1 size: {telemetry['l1_bytes']/1024/1024:.1f} MB")
```

**해결:**
- L1 크기 증가: `l1_max_bytes=1024*1024*1024` (1GB)
- L1 항목 수 증가: `l1_max_size=1000`

---

## Troubleshooting

### Clear Cache

```python
# Clear L0 only (fast)
await builder.clear_l0()

# Clear all tiers
builder._tiered_cache.clear()  # L1 + L2
await builder.clear_l0()        # L0
```

### Debug Mode

```python
import logging

logging.getLogger('src.contexts.code_foundation.infrastructure.ir.layered_ir_builder').setLevel(logging.DEBUG)

# Will log:
# - L0 check results
# - L0 purge operations
# - L0 evictions
# - Environmental context
```

---

## Best Practices

### 1. Reuse Builder Instance

❌ **Bad:**
```python
for _ in range(10):
    builder = LayeredIRBuilder(project_root)  # New instance!
    await builder.build(files, config)
```

✅ **Good:**
```python
builder = LayeredIRBuilder(project_root)  # Reuse!
for _ in range(10):
    await builder.build(files, config)  # L0 cache works
```

### 2. Use IRPipeline for Automatic Reuse

✅ **Best:**
```python
pipeline = IRPipeline(project_root)

# Pipeline automatically reuses builder
await pipeline.build_incremental(files)
await pipeline.build_incremental(files)  # L0 cache hit!
```

### 3. Monitor in Production

```python
# After each build
telemetry = await builder.get_l0_telemetry()

if telemetry['l1_hit_rate'] < 0.3:
    alert("Low cache hit rate!")

if telemetry['l1_bytes'] > 1024*1024*1024:  # 1GB
    alert("High memory usage!")
```

---

## Migration Guide

### From Old Code

**Before (RFC-038):**
```python
from src.contexts.code_foundation.infrastructure.ir.cache import get_global_cache

cache = get_global_cache()  # Only L2 (DiskCache)
```

**After (RFC-039):**
```python
from src.contexts.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

builder = LayeredIRBuilder(project_root)  # L0 + L1 + L2!
await builder.build(files, config)
```

### From IncrementalStrategy

**Before:**
```python
strategy = IncrementalStrategy(max_cache_size=1000)
strategy.clear_cache()
```

**After:**
```python
# IncrementalStrategy now uses Builder's L0
pipeline = IRPipeline(project_root)
await pipeline.clear_incremental_cache()  # Clears L0
```

---

## Performance Targets

| Scenario | Target | Achieved |
|----------|--------|----------|
| Cold build (200 files) | <15s | 10.6s ✅ |
| Warm build (L2) | <5s | 3.4s ✅ |
| Watch mode (L0) | <50ms | ~10ms ✅ |
| L0 check (10K files) | <10ms | ~10ms ✅ |

---

## FAQ

### Q: L0 vs L1 vs L2 차이?

**A:**
- **L0**: Builder instance memory (fastest, volatile)
- **L1**: Process memory (fast, volatile)
- **L2**: Disk (persistent, slower)

### Q: ProcessPool worker는 어떤 캐시 사용?

**A:** Worker는 L2만 사용 (Main은 L0+L1+L2)

### Q: 캐시 무효화는 언제?

**A:**
1. 파일 내용 변경 (content hash)
2. Python 버전 변경 (environmental hash)
3. Schema 버전 변경 (자동)

### Q: 메모리 부족 시?

**A:** L0/L1 자동 LRU eviction (OOM 방지)

---

## References

- RFC-039: Tiered IR Cache Architecture
- RFC-038: Semantic IR Cache
- RFC-029: Pyright Result Caching

