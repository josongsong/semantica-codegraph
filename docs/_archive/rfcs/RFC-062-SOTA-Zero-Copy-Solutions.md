# RFC-062 Addendum: SOTA Zero-Copy Solutions

## 문제 진단

**msgpack이 느린 근본 원인:**
- 14.24 MB 데이터를 4번 복사 (Python→msgpack→Rust→msgpack→Python)
- 중복 데이터 2.8 MB (19.4%)
- 총 56.96 MB 메모리 이동

**PyDict API도 한계:**
- Python interop overhead 71%
- Symbol table PyDict 변환 37%
- 완전한 zero-copy 불가능

---

## SOTA Solution 1: Apache Arrow IPC ⭐ 최고 추천

### 개요
- **Zero-copy binary columnar format**
- Pandas, Polars, Spark가 사용하는 업계 표준
- Language-agnostic memory layout

### 아키텍처

```
Python (PyArrow)              Rust (arrow-rs)
┌─────────────────┐          ┌─────────────────┐
│ Arrow Table     │          │ Arrow RecordBatch│
│  ┌───────────┐  │   IPC    │  ┌───────────┐  │
│  │Column Data│──┼──────────┼─→│Column Data│  │
│  └───────────┘  │  Stream  │  └───────────┘  │
│  (Memory Map)   │          │  (Memory Map)   │
└─────────────────┘          └─────────────────┘
       ↑                              ↑
       └──────── Shared Memory ───────┘
              (Zero-copy!)
```

### 구현 예시

```python
# Python side
import pyarrow as pa

# Define schema (한 번만)
schema = pa.schema([
    ('id', pa.string()),
    ('fqn', pa.string()),
    ('kind', pa.uint8()),           # Enum (0-255)
    ('file_id', pa.uint16()),       # File index (중복 제거!)
    ('start_line', pa.uint32()),
    ('start_col', pa.uint16()),
    ('end_line', pa.uint32()),
    ('end_col', pa.uint16()),
])

# Convert to Arrow Table (columnar)
table = pa.table({
    'id': ['node_0_0', 'node_0_1', ...],
    'fqn': ['module.func_0', ...],
    'kind': [0, 0, 0, ...],          # function = 0
    'file_id': [0, 0, 0, 1, 1, ...], # 중복 제거!
    'start_line': [0, 10, 20, ...],
    ...
}, schema=schema)

# Serialize to Arrow IPC format
sink = pa.BufferOutputStream()
with pa.ipc.new_stream(sink, schema) as writer:
    writer.write_table(table)

arrow_bytes = sink.getvalue()

# Send to Rust
result = codegraph_ir.build_global_context_arrow(arrow_bytes)
```

```rust
// Rust side (arrow-rs)
use arrow::ipc::reader::StreamReader;
use arrow::array::*;

#[pyfunction]
fn build_global_context_arrow(py: Python, arrow_bytes: &[u8]) -> PyResult<Vec<u8>> {
    py.allow_threads(|| {
        // Zero-copy read
        let reader = StreamReader::try_new(Cursor::new(arrow_bytes), None)?;

        for batch in reader {
            let batch = batch?;

            // Zero-copy column access
            let ids = batch.column(0).as_any().downcast_ref::<StringArray>().unwrap();
            let fqns = batch.column(1).as_any().downcast_ref::<StringArray>().unwrap();
            let kinds = batch.column(2).as_any().downcast_ref::<UInt8Array>().unwrap();
            let file_ids = batch.column(3).as_any().downcast_ref::<UInt16Array>().unwrap();

            // Process without copying
            for i in 0..batch.num_rows() {
                let symbol = Symbol {
                    id: ids.value(i).to_string(),    // Only copy when needed
                    fqn: fqns.value(i).to_string(),
                    kind: NodeKind::from(kinds.value(i)),
                    file_id: file_ids.value(i),
                    ...
                };
                // Process symbol
            }
        }

        // Return Arrow IPC result (also zero-copy)
        Ok(result_arrow_bytes)
    })
}
```

### 성능 예상

```
100,000 symbols:

데이터 크기:
- msgpack: 14.24 MB (중복 포함)
- Arrow: ~4 MB (columnar + 중복 제거)

처리 시간:
- PyDict API: 274ms (baseline)
- msgpack: 299ms (4번 복사)
- Arrow IPC: ~50ms (zero-copy!) ← 5.5x faster!

메모리 복사:
- msgpack: 56.96 MB (4번 복사)
- Arrow: 0 MB (zero-copy!)
```

### 장점
- ✅ **Zero-copy**: 메모리 복사 없음
- ✅ **Columnar format**: 중복 자동 제거
- ✅ **업계 표준**: Pandas/Polars 호환
- ✅ **Language agnostic**: Python ↔ Rust ↔ C++ ↔ Java

### 단점
- 새로운 의존성 (pyarrow, arrow-rs)
- Schema 정의 필요
- Columnar format 변환 비용 (한 번만)

---

## SOTA Solution 2: Cap'n Proto / FlatBuffers

### 개요
- **Zero-copy binary protocol**
- Google (FlatBuffers), Cloudflare (Cap'n Proto) 사용
- Random access without parsing

### 특징

```
Traditional (msgpack):
├─ Parse entire message
├─ Deserialize to structs
├─ Random access
└─ Time: O(n)

FlatBuffers:
├─ Memory map binary
├─ Random access directly
├─ No deserialization
└─ Time: O(1)
```

### 구현 예시

```rust
// schema.fbs
table Symbol {
    id: string;
    fqn: string;
    kind: ubyte;
    file_id: ushort;
    span: Span;
}

table Span {
    start_line: uint;
    start_col: ushort;
    end_line: uint;
    end_col: ushort;
}

table SymbolTable {
    symbols: [Symbol];
    files: [string];  // File path dictionary
}

root_type SymbolTable;
```

```rust
// Rust side
use flatbuffers::FlatBufferBuilder;

#[pyfunction]
fn build_global_context_flatbuf(py: Python, fb_bytes: &[u8]) -> PyResult<Vec<u8>> {
    py.allow_threads(|| {
        // Zero-copy access
        let symbol_table = root_as_symbol_table(fb_bytes)?;

        for symbol in symbol_table.symbols()?.iter() {
            // Direct access without deserialization
            let id = symbol.id();
            let fqn = symbol.fqn();
            let kind = NodeKind::from(symbol.kind());
            let file_path = symbol_table.files()?.get(symbol.file_id() as usize);

            // Process...
        }

        // Build result (also zero-copy)
        Ok(result_fb_bytes)
    })
}
```

### 성능 예상

```
100,000 symbols:

데이터 크기: ~3 MB (dictionary encoding)
처리 시간: ~40ms (zero-copy + random access)
메모리: 0 복사
```

### 장점
- ✅ **Zero-copy**: 직접 메모리 접근
- ✅ **Random access**: O(1) lookup
- ✅ **Compact**: dictionary encoding

### 단점
- Schema 컴파일 필요 (`.fbs` → code generation)
- 새로운 의존성
- Python 생태계 지원 제한적

---

## SOTA Solution 3: Shared Memory + Lock-free Queue

### 개요
- **Ultimate zero-copy**: Python과 Rust가 같은 메모리 공유
- Linux: shm_open, mmap
- Lock-free queue로 동기화

### 아키텍처

```
┌─────────────────────────────────────────────────────┐
│            Shared Memory Region                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  Ring Buffer (Lock-free Queue)                │  │
│  │  ┌──────┬──────┬──────┬──────┬──────┐         │  │
│  │  │Symbol│Symbol│Symbol│Symbol│Symbol│  ...    │  │
│  │  └──────┴──────┴──────┴──────┴──────┘         │  │
│  │     ↑ Producer (Python)                       │  │
│  │     ↓ Consumer (Rust)                         │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
       ↑                                    ↑
   Python Process                      Rust Thread
```

### 구현 예시

```python
# Python side
import mmap
import os
import struct

# Create shared memory
shm_fd = os.shm_open('/codegraph_symbols', os.O_CREAT | os.O_RDWR, 0o600)
os.ftruncate(shm_fd, 100 * 1024 * 1024)  # 100 MB

# Memory-map
shm = mmap.mmap(shm_fd, 100 * 1024 * 1024)

# Write symbols (no serialization!)
offset = 0
for symbol in symbols:
    # Write binary directly
    shm[offset:offset+4] = struct.pack('I', len(symbol.id))
    offset += 4
    shm[offset:offset+len(symbol.id)] = symbol.id.encode()
    offset += len(symbol.id)
    # ...

# Notify Rust
result = codegraph_ir.build_global_context_shm('/codegraph_symbols')
```

```rust
// Rust side
use memmap2::MmapOptions;
use std::fs::OpenOptions;

#[pyfunction]
fn build_global_context_shm(py: Python, shm_path: &str) -> PyResult<...> {
    py.allow_threads(|| {
        // Open shared memory
        let file = OpenOptions::new()
            .read(true)
            .open(shm_path)?;

        // Memory-map (zero-copy!)
        let mmap = unsafe { MmapOptions::new().map(&file)? };

        // Read directly from shared memory
        let mut offset = 0;
        while offset < mmap.len() {
            let id_len = u32::from_le_bytes([mmap[offset], mmap[offset+1], mmap[offset+2], mmap[offset+3]]);
            offset += 4;

            let id = std::str::from_utf8(&mmap[offset..offset+id_len as usize])?;
            offset += id_len as usize;

            // Process symbol (zero-copy string view!)
        }

        Ok(result)
    })
}
```

### 성능 예상

```
100,000 symbols:

처리 시간: ~20ms (ultimate zero-copy!)
메모리: 0 복사 (완전 공유)
```

### 장점
- ✅ **Ultimate zero-copy**: 메모리 공유
- ✅ **최고 성능**: 복사 0, 직렬화 0
- ✅ **Low latency**: 메모리 속도

### 단점
- ❌ 복잡도 높음
- ❌ 플랫폼 의존적 (Linux/macOS)
- ❌ 동기화 복잡 (lock-free queue 필요)
- ❌ 메모리 관리 어려움

---

## 권장 사항

### 즉시 적용 가능 + 최대 효과: **Apache Arrow IPC** ⭐

```bash
# Install dependencies
pip install pyarrow
cargo add arrow arrow-ipc

# Expected improvement
274ms (PyDict) → ~50ms (Arrow IPC)
5.5x speedup!
```

### 구현 순서

1. **Phase 1: Arrow Schema 정의** (1일)
   - Symbol, Span, Import 스키마
   - File path dictionary

2. **Phase 2: Python → Arrow 변환** (1일)
   - PyArrow table 생성
   - IPC serialization

3. **Phase 3: Rust Arrow 처리** (2일)
   - arrow-rs 통합
   - Zero-copy 처리
   - Arrow IPC 결과 반환

4. **Phase 4: 벤치마크** (1일)
   - 성능 측정
   - PyDict vs Arrow 비교

**총 예상: 5일**

### 예상 최종 성능

```
100,000 symbols:

PyDict API:   274ms (baseline)
Arrow IPC:    ~50ms (5.5x faster) ← Target!
Shared Memory: ~20ms (13.7x faster, 복잡도 높음)
```

---

## Appendix: 산업계 사례

### Apache Arrow 사용 예
- **Pandas 2.0**: 기본 백엔드
- **Polars**: 전체 엔진
- **Spark**: Columnar format
- **DuckDB**: Zero-copy integration

### FlatBuffers 사용 예
- **Google**: Protocol Buffers v2
- **Unity**: Game engine serialization
- **NVIDIA**: CUDA data exchange

### Shared Memory 사용 예
- **Redis**: In-memory database
- **Chrome**: Multi-process IPC
- **PostgreSQL**: Buffer pool
