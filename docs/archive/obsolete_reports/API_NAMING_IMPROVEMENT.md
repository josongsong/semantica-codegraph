# API Naming Improvement - `scheduled_index()`

**Date**: 2025-12-29
**Priority**: P1 (User Feedback)
**Status**: ✅ Complete

---

## 📋 Summary

Improved the `scheduled_index()` API parameter naming based on user feedback. The previous `enable_expensive_analysis` boolean was confusing; replaced with clearer `with_full_analysis` naming.

---

## 🎯 User Feedback

**Original Complaint**:
> "scheduled_index(true) 이름이 이상한데 analysis mode 이런게 낫지않나"
>
> Translation: "The name scheduled_index(true) is strange, wouldn't something like 'analysis mode' be better?"

**Problem**:
- Parameter name `enable_expensive_analysis` was too technical and confusing
- Boolean `true`/`false` doesn't clearly indicate what it does
- User suggested "analysis mode" as clearer alternative

---

## ✅ Changes Made

### Before (Confusing ❌)
```python
# Rust API
pub fn scheduled_index(
    &self,
    repo_root: PathBuf,
    repo_name: String,
    enable_expensive_analysis: bool,  # ❌ Technical jargon
) -> Result<IndexingResult, CodegraphError>

# Python API
result = codegraph_ir.scheduled_index(
    "/workspace/repo",
    "repo",
    enable_expensive_analysis=True  # ❌ What does "expensive" mean?
)
```

### After (Clear ✅)
```python
# Rust API
pub fn scheduled_index(
    &self,
    repo_root: PathBuf,
    repo_name: String,
    with_full_analysis: bool,  # ✅ Clear intent
) -> Result<IndexingResult, CodegraphError>

# Python API
result = codegraph_ir.scheduled_index(
    "/workspace/repo",
    "repo",
    with_full_analysis=True  # ✅ Clear: enables L6, L14, L16
)
```

---

## 📝 Files Modified

### 1. Rust Usecase Layer
**File**: `packages/codegraph-ir/src/usecases/indexing_service.rs`

**Changes**:
- Line 394: Parameter name changed
- Line 420: Parameter name changed
- Lines 399-415: Updated documentation with clearer examples
- Lines 423-441: Improved inline comments

**Before**:
```rust
pub fn scheduled_index(
    &self,
    repo_root: PathBuf,
    repo_name: String,
    enable_expensive_analysis: bool,
) -> Result<IndexingResult, CodegraphError> {
    if enable_expensive_analysis {
        // Enable expensive stages...
    }
}
```

**After**:
```rust
pub fn scheduled_index(
    &self,
    repo_root: PathBuf,
    repo_name: String,
    with_full_analysis: bool,
) -> Result<IndexingResult, CodegraphError> {
    if with_full_analysis {
        // Enable L6, L14, L16 at night
    } else {
        // Basic stages only (L1-L5)
    }
}
```

### 2. PyO3 Bindings
**File**: `packages/codegraph-ir/src/lib.rs`

**Changes**:
- Line 2185: Parameter documentation updated
- Line 2210: PyO3 signature updated
- Line 2215: Function parameter changed
- Line 2228: Function call updated
- Lines 2190-2207: Improved Python examples

**Before**:
```rust
#[pyo3(signature = (repo_root, repo_name, enable_expensive_analysis = false))]
fn scheduled_index(
    py: Python,
    repo_root: String,
    repo_name: String,
    enable_expensive_analysis: bool,
) -> PyResult<Py<PyDict>> {
    service.scheduled_index(
        PathBuf::from(&repo_root),
        repo_name,
        enable_expensive_analysis,
    )
}
```

**After**:
```rust
#[pyo3(signature = (repo_root, repo_name, with_full_analysis = false))]
fn scheduled_index(
    py: Python,
    repo_root: String,
    repo_name: String,
    with_full_analysis: bool,
) -> PyResult<Py<PyDict>> {
    service.scheduled_index(
        PathBuf::from(&repo_root),
        repo_name,
        with_full_analysis,
    )
}
```

### 3. Benchmark Tool
**File**: `packages/codegraph-ir/examples/benchmark_large_repos.rs`

**Changes**:
- Line 320: Updated inline comment
- Line 444: Updated help text
- Line 450: Updated example description
- Line 500: Updated mode display text

**Before**:
```rust
service.scheduled_index(
    repo_path.clone(),
    repo_name.clone(),
    true,  // enable_expensive_analysis
)?

// Help text
println!("  --all-stages    Enable all pipeline stages (L1-L37, includes expensive analysis)");
println!("Mode: ALL STAGES (L1-L37 + Expensive Analysis)");
```

**After**:
```rust
service.scheduled_index(
    repo_path.clone(),
    repo_name.clone(),
    true,  // with_full_analysis = true (L1-L37 with L6, L14, L16)
)?

// Help text
println!("  --all-stages    Enable full analysis (L1-L37 with L6 PTA, L14 Taint, L16 RepoMap)");
println!("Mode: FULL ANALYSIS (L1-L37 with L6, L14, L16)");
```

---

## 🧪 Testing

### Test Results
```bash
$ RUST_LOG=warn python test_scheduled_api.py

🧪 Testing scheduled_index() API naming improvements
============================================================

1️⃣  Test: Basic Indexing (with_full_analysis=False)
------------------------------------------------------------
✅ Basic indexing complete!
   Files: 619
   Duration: 102ms
   LOC/s: 276,271

2️⃣  Test: Full Analysis (with_full_analysis=True)
------------------------------------------------------------
✅ Full analysis complete!
   Files: 619
   Duration: 7,784ms
   LOC/s: 3,650
   Stage count: 8

📊 Stage Durations (Full Analysis):
   - L1_IR_Build: 57ms
   - L2_Chunking: 20ms
   - L3_CrossFile: 19ms
   - L4_Occurrences: 0ms
   - L5_Symbols: 0ms
   - L6_PointsTo: 7,614ms  ← Expensive
   - L14_TaintAnalysis: 25ms
   - L16_RepoMap: 101ms

============================================================
✅ All tests passed! New API naming is working correctly.

🎯 API Improvement Summary:
   ❌ Old: enable_expensive_analysis=True  (confusing)
   ✅ New: with_full_analysis=True         (clear)
```

---

## 🎯 Impact

### User Experience Improvement
- ✅ **Clarity**: `with_full_analysis` clearly indicates what happens
- ✅ **Intent**: Boolean value now has obvious meaning
- ✅ **Documentation**: Inline comments explain what "full analysis" means (L6, L14, L16)

### Code Quality
- ✅ **Consistency**: Parameter naming now matches typical Rust conventions (`with_*`)
- ✅ **Maintainability**: Clearer parameter name makes code self-documenting
- ✅ **Examples**: Updated all documentation with better examples

### Performance
- ✅ **No performance impact**: Pure naming change, same underlying logic
- ✅ **Compilation verified**: `cargo build --lib --release` successful
- ✅ **Python bindings verified**: `maturin build --release` successful

---

## 📚 Related Documentation

- **Trigger API Docs**: [docs/TRIGGER_API_COMPLETE.md](./TRIGGER_API_COMPLETE.md)
- **Python Usage Example**: [examples/trigger_api_usage.py](../examples/trigger_api_usage.py)
- **Benchmark Tool**: [packages/codegraph-ir/examples/benchmark_large_repos.rs](../packages/codegraph-ir/examples/benchmark_large_repos.rs)

---

## ✅ Completion Checklist

- [x] Rust usecase method parameter renamed
- [x] PyO3 binding parameter updated
- [x] Benchmark tool usage updated
- [x] Documentation examples updated
- [x] Inline comments improved
- [x] Help text clarified
- [x] Compilation verified (Rust)
- [x] Python extension built
- [x] API tested with both modes
- [x] User feedback addressed

---

**Status**: ✅ **Complete**
**User Satisfaction**: Feedback incorporated and verified
