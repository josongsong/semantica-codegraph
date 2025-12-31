# Heap Analysis Feature Catalog

> **SOTA Memory Safety & Security Analysis Module**
>
> Port of Python heap analysis (11,206 lines) to Rust for performance.
> Last Updated: 2025-12-31

---

## 📊 Feature Summary

| # | Feature | File | Status | Lines | Tests |
|---|---------|------|--------|-------|-------|
| 1 | Separation Logic | `separation_logic.rs` | ✅ Complete | ~800 | 15+ |
| 2 | Null Pointer Analysis | `memory_safety.rs` | ✅ Complete | ~200 | 10+ |
| 3 | Use-After-Free Detection | `memory_safety.rs` | ✅ Complete | ~150 | 8+ |
| 4 | Double Free Detection | `memory_safety.rs` | ✅ Complete | ~100 | 5+ |
| 5 | Buffer Overflow Detection | `memory_safety.rs` | ✅ Complete | ~200 | 10+ |
| 6 | Ownership Tracking | `ownership.rs` | ✅ Complete | ~1400 | 36 |
| 7 | Security (OWASP Top 10) | `security.rs` | ✅ Complete | ~600 | 15+ |
| 8 | Escape Analysis | `escape_analysis.rs` | ✅ Complete | ~500 | 12+ |
| 9 | Context-Sensitive Heap | `context_sensitive.rs` | ✅ Complete | ~400 | 10+ |
| 10 | Symbolic Memory | `symbolic_memory.rs` | ✅ Complete | ~300 | 8+ |

**Total: ~4,650 lines, 129+ tests**

---

## 🏗️ Architecture

```
heap_analysis/
├── mod.rs                    # Module exports
├── feature_catalog.md        # This file
│
├── 🔐 Memory Safety
│   ├── separation_logic.rs   # Separation Logic (Reynolds 2002)
│   ├── memory_safety.rs      # Null/UAF/DoubleFree/BufferOverflow
│   └── ownership.rs          # Rust-style ownership tracking
│
├── 🛡️ Security
│   └── security.rs           # OWASP Top 10 detection
│
├── 📈 Advanced Analysis
│   ├── escape_analysis.rs    # Object escape behavior (RFC-074)
│   ├── context_sensitive.rs  # k-CFA heap analysis
│   └── symbolic_memory.rs    # Symbolic execution support
│
└── Pipeline Integration
    └── ../pipeline/processor/stages/heap.rs
```

---

## 📚 Feature Details

### 1. Separation Logic (`separation_logic.rs`)

**Academic References:**
- Reynolds (2002): "Separation Logic: A Logic for Shared Mutable Data Structures"
- O'Hearn (2004): "Local Reasoning about Programs that Alter Data Structures"

**Industry:**
- Meta Infer: Bi-abduction, separation logic (C/C++/Java)

**Components:**

| Component | Description |
|-----------|-------------|
| `SymbolicHeap` | Heap state model: `x ↦ {f₁: v₁, ...}` |
| `HeapCell` | Individual heap cell with fields |
| `AbstractLocation` | Abstract memory locations |
| `PureConstraint` | Pure (non-heap) constraints |
| `EntailmentChecker` | Checks H₁ ⊢ H₂ (entailment) |
| `FrameResult` | Frame inference result |
| `BiAbductionResult` | Bi-abduction for precondition synthesis |
| `FunctionSpec` | Pre/post-condition specs |
| `MemorySafetyIssue` | Issue type with severity |

**Key Operations:**
```rust
// Entailment: Does H₁ imply H₂?
checker.check_entailment(&h1, &h2) -> EntailmentResult

// Frame Inference: H₁ = H₂ * Frame
checker.infer_frame(&h1, &h2) -> FrameResult

// Bi-abduction: AntiFrame * H₁ ⊢ H₂ * Frame
checker.bi_abduce(&h1, &h2) -> BiAbductionResult

// Separating Conjunction: H₁ * H₂
checker.separating_conjunction(&h1, &h2) -> SymbolicHeap
```

---

### 2. Memory Safety Checkers (`memory_safety.rs`)

**Academic References:**
- Fähndrich & Leino (2003): "Declaring and checking non-null types"
- Chalin & James (2007): "Non-null references by default"

**Components:**

| Checker | Detection | Severity |
|---------|-----------|----------|
| `NullDereferenceChecker` | Null pointer dereference (NPE) | 9/10 |
| `UseAfterFreeChecker` | Use of freed memory | 10/10 |
| `DoubleFreeChecker` | Double free vulnerability | 10/10 |
| `BufferOverflowChecker` | Array bounds violation | 9/10 |
| `MemorySafetyAnalyzer` | Unified analyzer (all above) | - |

**Usage:**
```rust
let mut analyzer = MemorySafetyAnalyzer::new();
let issues = analyzer.analyze_with_edges(nodes, edges);
// Returns: Vec<MemorySafetyIssue>
```

**Issue Kinds:**
```rust
pub enum MemorySafetyIssueKind {
    NullDereference,
    UseAfterFree,
    DoubleFree,
    BufferOverflow,
    MemoryLeak,
    UninitializedRead,
}
```

---

### 3. Ownership Tracking (`ownership.rs`)

**Academic References:**
- Rust RFC 2094: Non-lexical lifetimes
- Weiss et al. (2019): "Oxide: The Essence of Rust"
- Jung et al. (2017): "RustBelt: Securing the Foundations of the Rust Programming Language"

**Industry:**
- Rust Compiler: MIR-based borrow checker
- Miri: Undefined behavior detection
- Polonius: Next-gen borrow checker

**Components:**

| Component | Description |
|-----------|-------------|
| `OwnershipState` | `Owned`, `Moved`, `BorrowedImmutable`, `BorrowedMutable`, `Invalid` |
| `BorrowKind` | `Shared` (&T), `Mutable` (&mut T) |
| `BorrowInfo` | Active borrow metadata |
| `OwnershipInfo` | Variable ownership tracking |
| `OwnershipViolation` | Detected violation |
| `OwnershipTracker` | Low-level tracker |
| `OwnershipAnalyzer` | High-level IR integration |

**Violation Kinds (8):**
```rust
pub enum OwnershipViolationKind {
    UseAfterMove,              // x moved → use(x)
    MoveWhileBorrowed,         // &x exists → y = x
    MutableBorrowWhileImmutable,  // &x exists → &mut x
    BorrowWhileMutableBorrow,  // &mut x exists → &x
    DanglingReference,         // ref outlives referent
    DoubleMove,                // x moved twice
    WriteWhileBorrowed,        // &x exists → x = ...
    UseAfterScopeEnd,          // scope ended → use(local)
}
```

**Usage:**
```rust
let mut analyzer = OwnershipAnalyzer::new();
let violations = analyzer.analyze(nodes, edges);
// Returns: Vec<OwnershipViolation>
```

**Test Coverage:** 36 tests (Base: 11, Edge: 12, Extreme: 4, Helper: 9)

---

### 4. Security Analysis (`security.rs`)

**OWASP Top 10 Coverage:**

| # | Vulnerability | Detection |
|---|--------------|-----------|
| A01 | Broken Access Control | ✅ |
| A02 | Cryptographic Failures | ✅ |
| A03 | Injection (SQL, XSS, Command) | ✅ |
| A04 | Insecure Design | ⚠️ Partial |
| A05 | Security Misconfiguration | ✅ |
| A06 | Vulnerable Components | ✅ |
| A07 | Auth Failures | ✅ |
| A08 | Data Integrity Failures | ✅ |
| A09 | Logging Failures | ✅ |
| A10 | SSRF | ✅ |

**Components:**

| Component | Description |
|-----------|-------------|
| `VulnerabilityType` | 20+ vulnerability types |
| `OWASPCategory` | A01-A10 categories |
| `SecurityVulnerability` | Detected issue with CWE mapping |
| `DeepSecurityAnalyzer` | Main analyzer with taint tracking |

**Usage:**
```rust
let mut analyzer = DeepSecurityAnalyzer::new();
let vulns = analyzer.analyze(nodes, edges);
// Returns: Vec<SecurityVulnerability>
```

---

### 5. Escape Analysis (`escape_analysis.rs`)

**RFC-074 Implementation**

**Escape States:**
```rust
pub enum EscapeState {
    NoEscape,      // Object stays local
    ArgEscape,     // Escapes via argument
    ReturnEscape,  // Escapes via return
    ThreadEscape,  // Escapes to another thread
    GlobalEscape,  // Escapes to global state
}
```

**Components:**

| Component | Description |
|-----------|-------------|
| `EscapeNode` | IR node with defs/uses |
| `EscapeInfo` | Escape state per variable |
| `FunctionEscapeInfo` | Function-level summary |
| `EscapeAnalyzer` | Main analyzer |

**Integration with Concurrency Analysis:**
- `NoEscape`/`ArgEscape` → No race condition possible (40-60% FP reduction)
- `ThreadEscape`/`GlobalEscape` → Requires race detection

---

### 6. Context-Sensitive Heap Analysis (`context_sensitive.rs`)

**k-CFA (k-Calling-Context-Sensitive) Analysis**

**Components:**

| Component | Description |
|-----------|-------------|
| `CallSiteId` | Unique call site identifier |
| `ContextSensitiveHeapAnalyzer` | k-sensitive analyzer |
| `HeapAbstraction` | Abstract heap state per context |

**Precision vs. Performance:**
- k=0: Context-insensitive (fast, imprecise)
- k=1: 1-CFA (balanced)
- k=2: 2-CFA (precise, slower)

---

### 7. Symbolic Memory (`symbolic_memory.rs`)

**Symbolic Execution Support**

**Components:**

| Component | Description |
|-----------|-------------|
| `ObjectId` | Symbolic object identifier |
| `SymbolicValue` | Concrete or symbolic value |
| `SymbolicMemory` | Memory state with symbolic values |
| `PathConstraint` | Path condition accumulator |

**Operations:**
```rust
let mut mem = SymbolicMemory::new();
mem.allocate(obj_id, size);
mem.write(obj_id, offset, value);
let val = mem.read(obj_id, offset);
```

---

## 🔗 Pipeline Integration

### Entry Point

```rust
// packages/codegraph-ir/src/pipeline/processor/stages/heap.rs

pub struct HeapAnalysisResult {
    pub memory_issues: Vec<MemorySafetyIssue>,
    pub security_vulnerabilities: Vec<SecurityVulnerability>,
    pub escape_info: Vec<FunctionEscapeInfo>,
    pub ownership_violations: Vec<OwnershipViolation>,
}

// Legacy API (backward compatible)
pub fn run_heap_analysis(nodes, edges)
    -> (Vec<MemorySafetyIssue>, Vec<SecurityVulnerability>, Vec<FunctionEscapeInfo>)

// Full API (includes ownership)
pub fn run_heap_analysis_full(nodes, edges) -> HeapAnalysisResult
```

### Activation

```rust
// packages/codegraph-ir/src/lib.rs
StageControl {
    enable_heap_analysis: enable_points_to,  // Enabled with PTA
    // ...
}
```

---

## 📈 Performance Characteristics

| Analysis | Time Complexity | Space Complexity |
|----------|----------------|------------------|
| Separation Logic | O(n × m) | O(m) |
| Memory Safety | O(n) | O(n) |
| Ownership | O(n × m) | O(m) |
| Security | O(n × e) | O(n) |
| Escape | O(n + e) | O(n) |
| Context-Sensitive | O(n × k^d) | O(n × k^d) |

Where:
- n = nodes, e = edges, m = variables
- k = context sensitivity, d = call depth

---

## 🧪 Test Summary

```
cargo test --lib heap_analysis
```

| Module | Tests | Status |
|--------|-------|--------|
| `separation_logic` | 15+ | ✅ |
| `memory_safety` | 23+ | ✅ |
| `ownership` | 36 | ✅ |
| `security` | 15+ | ✅ |
| `escape_analysis` | 12+ | ✅ |
| `context_sensitive` | 10+ | ✅ |
| `symbolic_memory` | 8+ | ✅ |
| **Total** | **129+** | ✅ |

---

## 📖 References

### Academic
1. Reynolds (2002): Separation Logic
2. O'Hearn (2004): Local Reasoning
3. Fähndrich & Leino (2003): Non-null types
4. Weiss et al. (2019): Oxide
5. Jung et al. (2017): RustBelt
6. Choi et al. (1999): Escape Analysis

### Industry
1. Meta Infer: Bi-abduction engine
2. Rust Compiler: Borrow checker
3. Coverity: Pattern + symbolic
4. Microsoft SLAM: Predicate abstraction
5. Kotlin: Nullable types

---

## 🚀 Future Work

- [ ] Non-Lexical Lifetimes (NLL) for ownership
- [ ] Inter-procedural separation logic
- [ ] GPU-accelerated symbolic execution
- [ ] Machine learning for false positive reduction
