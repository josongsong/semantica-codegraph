# Benchmark Config Migration Guide

**Date**: 2025-12-29
**Status**: Completed
**Related**: [RFC-075-INTEGRATION-PLAN.md](RFC-075-INTEGRATION-PLAN.md)

---

## 📋 Summary

`BenchmarkConfig` has been migrated from the legacy `PipelineConfig` (6 fields) to **RFC-001 ValidatedConfig** (complete config system with Preset + Stage Override support).

## 🔄 Changes

### Before (Legacy)

```rust
use codegraph_ir::benchmark::BenchmarkConfig;

// Old API
let config = BenchmarkConfig::with_preset(Preset::Balanced);
```

**Problems**:
- Used deprecated `PipelineConfig` (6 fields only)
- No access to RFC-001 advanced features (Stage Override, YAML, Provenance)
- Inconsistent with main config system

### After (RFC-001)

```rust
use codegraph_ir::benchmark::BenchmarkConfig;

// New API (recommended)
let config = BenchmarkConfig::balanced();

// Or with explicit preset
let config = BenchmarkConfig::fast();     // CI/CD (1x baseline)
let config = BenchmarkConfig::balanced(); // Development (2.5x baseline)
let config = BenchmarkConfig::thorough(); // Full analysis (10x baseline)

// Advanced: Stage override
let config = BenchmarkConfig::balanced()
    .with_stage("taint", true)
    .with_stage("pta", true);
```

**Benefits**:
- ✅ Uses RFC-001 `ValidatedConfig` (full feature set)
- ✅ Simple API: `fast()`, `balanced()`, `thorough()` presets
- ✅ Stage override support via `.with_stage()`
- ✅ Consistent with main pipeline config

---

## 📚 API Changes

### 1. Constructor Methods

| Old API | New API | Status |
|---------|---------|--------|
| `BenchmarkConfig::new()` | `BenchmarkConfig::balanced()` | ✅ Backward compatible (aliased) |
| `BenchmarkConfig::with_preset(Preset::Fast)` | `BenchmarkConfig::fast()` | ⚠️ Deprecated (still works) |
| `BenchmarkConfig::with_preset(Preset::Balanced)` | `BenchmarkConfig::balanced()` | ⚠️ Deprecated (still works) |
| `BenchmarkConfig::with_preset(Preset::Thorough)` | `BenchmarkConfig::thorough()` | ⚠️ Deprecated (still works) |

### 2. Field Changes

| Field | Before | After |
|-------|--------|-------|
| `pipeline_config` | `PipelineConfig` (6 fields) | `ValidatedConfig` (RFC-001) |
| `benchmark_opts` | `BenchmarkOptions` | `BenchmarkOptions` (unchanged) |

### 3. New Methods

```rust
impl BenchmarkConfig {
    /// Fast preset (CI/CD, 1x baseline, 5s target)
    pub fn fast() -> Self { /* ... */ }

    /// Balanced preset (Development, 2.5x baseline, 30s target)
    pub fn balanced() -> Self { /* ... */ }

    /// Thorough preset (Full analysis, 10x baseline, no time limit)
    pub fn thorough() -> Self { /* ... */ }

    /// Stage override builder (advanced usage)
    pub fn with_stage(self, stage: &str, enabled: bool) -> Self { /* ... */ }

    /// Get config name for identification
    pub fn config_name(&self) -> String { /* ... */ }
}
```

---

## 🔧 Migration Steps

### Step 1: Update Constructor Calls

**Before**:
```rust
let config = BenchmarkConfig::with_preset(Preset::Balanced);
```

**After**:
```rust
let config = BenchmarkConfig::balanced();
```

### Step 2: Update Field Access (if needed)

**Before**:
```rust
let preset = config.pipeline_config.preset;  // Direct field access
```

**After**:
```rust
let preset = config.pipeline_config.as_inner().preset;  // Via accessor
```

### Step 3: Use Stage Override (optional)

```rust
// Example: Enable Taint analysis in Balanced preset
let config = BenchmarkConfig::balanced()
    .with_stage("taint", true)
    .with_stage("pta", true);  // PTA needed for Taint
```

---

## 📝 Examples

### Basic Usage

```rust
use codegraph_ir::benchmark::{BenchmarkConfig, BenchmarkRunner, Repository};
use std::path::PathBuf;

// Simple: Use preset
let config = BenchmarkConfig::fast();
let repo = Repository::from_path(PathBuf::from("tools/benchmark/repo-test/small/typer")).unwrap();
let runner = BenchmarkRunner::new(config, repo);
let report = runner.run().unwrap();
```

### Advanced: Stage Override

```rust
// Start with Balanced, enable security analysis
let config = BenchmarkConfig::balanced()
    .with_stage("taint", true)
    .with_stage("pta", true)
    .with_stage("clone", false);  // Disable Clone detection

let repo = Repository::from_path(path).unwrap();
let runner = BenchmarkRunner::new(config, repo);
```

### Custom Options

```rust
// Combine preset with custom benchmark options
let config = BenchmarkConfig::thorough()
    .warmup_runs(2)
    .measured_runs(5)
    .skip_validation();

let runner = BenchmarkRunner::new(config, repo);
```

---

## ⚠️ Breaking Changes

### None (Backward Compatible)

All existing code will continue to work:
- `BenchmarkConfig::new()` → aliased to `balanced()`
- `BenchmarkConfig::with_preset()` → deprecated but functional
- Field access via `pipeline_config.as_inner()` (instead of direct access)

### Deprecation Warnings

```rust
#[deprecated(since = "0.1.0", note = "Use BenchmarkConfig::fast(), balanced(), or thorough() instead")]
pub fn with_preset(preset: Preset) -> Self { /* ... */ }
```

**Action**: Update to new API to avoid warnings:
```diff
- let config = BenchmarkConfig::with_preset(Preset::Fast);
+ let config = BenchmarkConfig::fast();
```

---

## 🎯 Benefits

### 1. RFC-001 Feature Access

```rust
// Access to ValidatedConfig features
let validated = config.pipeline_config;

// Get effective configs (returns None if stage disabled)
if let Some(taint_cfg) = validated.taint() {
    println!("Taint max_depth: {}", taint_cfg.max_depth);
}

// Performance profile
let profile = validated.performance_profile();
println!("Cost: {:?}, Memory: {:?}", profile.cost, profile.memory);
```

### 2. Consistent API

```rust
// Benchmark config aligns with main pipeline config
let pipeline_cfg = PipelineConfig::preset(Preset::Balanced)
    .stages(|s| s.enable(StageId::Taint))
    .build()?;

let benchmark_cfg = BenchmarkConfig::balanced()
    .with_stage("taint", true);

// Same underlying config system!
```

### 3. Future-Proof

```rust
// When RFC-001 adds new features, BenchmarkConfig gets them automatically
// Example: YAML loading (planned)
let config = BenchmarkConfig::balanced()
    .with_yaml_override("team-security.yaml")?;  // Future feature
```

---

## 📊 Impact Analysis

### Code Changes

| File | Changes | Status |
|------|---------|--------|
| `src/benchmark/config.rs` | +60 LOC (new methods) | ✅ Complete |
| `src/benchmark/runner.rs` | No changes needed | ✅ Compatible |
| `src/benchmark/mod.rs` | No changes needed | ✅ Compatible |

### Test Compatibility

All existing tests pass without modification:
```bash
cargo test --package codegraph-ir --lib benchmark
```

### Performance

No performance impact:
- `ValidatedConfig` is zero-cost wrapper
- Same memory layout
- Preset resolution at build time

---

## 🔍 Troubleshooting

### Issue 1: "method not found in `ValidatedConfig`"

**Problem**:
```rust
let preset = config.pipeline_config.preset();  // ❌ Error
```

**Solution**:
```rust
let preset = config.pipeline_config.as_inner().preset;  // ✅ Correct
```

**Reason**: `ValidatedConfig` is a newtype wrapper, use `as_inner()` to access fields.

### Issue 2: "Unknown stage 'xxx', ignoring"

**Problem**:
```rust
let config = BenchmarkConfig::balanced()
    .with_stage("taints", true);  // ❌ Typo: "taints" instead of "taint"
```

**Solution**:
```rust
let config = BenchmarkConfig::balanced()
    .with_stage("taint", true);  // ✅ Correct
```

**Valid stage names**:
- `parsing`, `chunking`, `lexical`
- `cross_file`, `clone`, `pta`
- `flow_graphs`, `type_inference`
- `symbols`, `effects`, `taint`, `repomap`

---

## 📅 Timeline

- **2025-12-29**: Migration completed
- **2026-01-15**: Deprecation warnings in all examples (planned)
- **2026-03-01**: Remove deprecated `with_preset()` (planned)

---

## 📚 References

- [RFC-001: Config System](RFC-CONFIG-SYSTEM.md)
- [RFC-075: Integration Plan](RFC-075-INTEGRATION-PLAN.md)
- [Benchmark System Guide](BENCHMARK_GROUND_TRUTH.md) (planned)

---

**Questions?** Check [RFC-075](RFC-075-INTEGRATION-PLAN.md) for integration strategy.
