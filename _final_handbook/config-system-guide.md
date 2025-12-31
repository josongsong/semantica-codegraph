# Configuration System Guide

**RFC-001: SOTA Configuration System for Codegraph IR**

## Overview

The Codegraph IR configuration system provides a 3-tier architecture designed for **progressive disclosure**:

- **Level 1: Preset** (90% users) - One-liner configuration
- **Level 2: Stage Override** (9% users) - Selective customization
- **Level 3: YAML/Advanced** (1% users) - Complete control

This design ensures simplicity for most users while providing power-user capabilities for advanced scenarios.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Stage Configurations](#stage-configurations)
5. [Performance Profiles](#performance-profiles)
6. [YAML Schema](#yaml-schema)
7. [Validation](#validation)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Level 1: Simple Preset (90% Use Case)

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

// Fast mode: Minimal analysis for quick feedback
let config = PipelineConfig::preset(Preset::Fast).build()?;

// Balanced mode: Default for most use cases
let config = PipelineConfig::preset(Preset::Balanced).build()?;

// Thorough mode: Maximum analysis depth
let config = PipelineConfig::preset(Preset::Thorough).build()?;
```

### Level 2: Override Specific Stages (9% Use Case)

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c
        .max_depth(50)
        .max_paths(1000)
        .field_sensitive(true))
    .pta(|c| c
        .mode(PTAMode::FlowInsensitive)
        .max_iterations(10))
    .build()?;
```

### Level 3: Complete Control via YAML (1% Use Case)

```rust
use codegraph_ir::config::PipelineConfig;

let config = PipelineConfig::from_yaml("config/security-focused.yaml")?;
```

---

## Architecture

### 3-Tier Design Philosophy

The config system follows the **principle of progressive disclosure**:

1. **Simple by default** - Presets cover 90% of use cases
2. **Flexible when needed** - Builder API for selective overrides
3. **Complete control available** - YAML for power users

### Merge Precedence (5 Layers)

Configuration values are merged with the following priority (highest to lowest):

```
5. StageControl (on/off switches)
   ↓
4. Builder API (dynamic overrides)
   ↓
3. Environment Variables (runtime config)
   ↓
2. YAML File (team standards)
   ↓
1. Preset (base configuration)
```

Example:
```rust
// Layer 1: Start with Fast preset
let config = PipelineConfig::preset(Preset::Fast)
    // Layer 4: Override taint depth
    .taint(|c| c.max_depth(50))
    .build()?;

// Layer 5: Disable taint entirely (highest priority)
config.stages().disable_taint();
```

### Field-Level Provenance

Every configuration field tracks its **source**:

```rust
pub enum ConfigSource {
    Preset,          // From base preset
    YamlFile,        // From YAML config
    EnvVar,          // From environment variable
    Builder,         // From builder API
    StageControl,    // From on/off switches
}
```

Access provenance:
```rust
let config = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c.max_depth(100))
    .build()?;

// Check where taint.max_depth came from
let source = config.provenance().get_source("taint.max_depth");
assert_eq!(source, ConfigSource::Builder);
```

### Validation Modes

The system supports two validation policies:

- **Lenient** (default): Warnings for misconfigurations
- **Strict**: Errors for any validation failure

```rust
// Lenient mode (default)
let config = PipelineConfig::preset(Preset::Fast)
    .strict_mode(false)
    .build()?;

// Strict mode (fail fast)
let config = PipelineConfig::preset(Preset::Fast)
    .strict_mode(true)
    .build()?;
```

---

## API Reference

### Core Types

#### `PipelineConfig`

Main configuration builder with fluent API.

**Methods:**

- `preset(Preset) -> Self` - Start with a preset
- `from_yaml(path: &str) -> Result<ValidatedConfig>` - Load from YAML
- `build() -> Result<ValidatedConfig>` - Finalize and validate
- `strict_mode(bool) -> Self` - Set validation policy

**Stage Override Methods:**

- `taint<F>(F) -> Self` where `F: FnOnce(TaintConfig) -> TaintConfig`
- `pta<F>(F) -> Self` where `F: FnOnce(PTAConfig) -> PTAConfig`
- `clone<F>(F) -> Self` where `F: FnOnce(CloneConfig) -> CloneConfig`
- `chunking<F>(F) -> Self` where `F: FnOnce(ChunkingConfig) -> ChunkingConfig`
- `lexical<F>(F) -> Self` where `F: FnOnce(LexicalConfig) -> LexicalConfig`
- `parallel<F>(F) -> Self` where `F: FnOnce(ParallelConfig) -> ParallelConfig`
- `cache<F>(F) -> Self` where `F: FnOnce(CacheConfig) -> CacheConfig`
- `pagerank<F>(F) -> Self` where `F: FnOnce(PageRankConfig) -> PageRankConfig`

#### `ValidatedConfig`

Immutable, validated configuration.

**Methods:**

- `taint() -> Option<TaintConfig>` - Get taint config
- `pta() -> Option<PTAConfig>` - Get PTA config
- `clone() -> Option<CloneConfig>` - Get clone detection config
- `chunking() -> Option<ChunkingConfig>` - Get chunking config
- `lexical() -> Option<LexicalConfig>` - Get lexical search config
- `parallel() -> Option<ParallelConfig>` - Get parallel config
- `cache() -> CacheConfig` - Get cache config (always returns default)
- `pagerank() -> PageRankConfig` - Get PageRank config (always returns default)
- `stages() -> &StageControl` - Get stage on/off switches
- `provenance() -> &ConfigProvenance` - Get field provenance
- `to_yaml() -> Result<String>` - Export to YAML
- `describe() -> String` - Human-readable description
- `performance_profile() -> PerformanceProfile` - Get performance bands

#### `Preset`

Predefined configuration templates.

**Variants:**

- `Preset::Fast` - Quick feedback, minimal analysis
- `Preset::Balanced` - Default for most use cases
- `Preset::Thorough` - Maximum depth and accuracy

#### `StageControl`

Pipeline stage on/off switches.

**Fields:**

- L1-L8 stages (parsing, chunking, cross-file, graphs, inference, etc.)
- Advanced analysis stages (taint, pta, clone, etc.)

**Methods:**

- `enable_taint()` - Enable taint analysis
- `disable_taint()` - Disable taint analysis
- `enable_pta()` - Enable points-to analysis
- `disable_pta()` - Disable points-to analysis
- `is_enabled(stage: &str) -> bool` - Check if stage is enabled

---

## Stage Configurations

### Taint Analysis

**Purpose**: Track data flow from sources to sinks for security vulnerabilities.

```rust
pub struct TaintConfig {
    pub max_depth: usize,           // Max recursion depth (default: 20)
    pub max_paths: usize,           // Max paths to explore (default: 100)
    pub use_points_to: bool,        // Use PTA for precision (default: false)
    pub field_sensitive: bool,      // Track struct fields (default: false)
    pub use_ssa: bool,              // Use SSA form (default: false)
    pub detect_sanitizers: bool,    // Detect sanitization (default: false)
    pub enable_interprocedural: bool, // Cross-function analysis (default: false)
    pub worklist_max_iterations: usize, // Worklist limit (default: 100)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c
        .max_depth(50)
        .max_paths(1000)
        .field_sensitive(true)
        .detect_sanitizers(true))
    .build()?;
```

**Performance Impact**:
- Fast preset: O(n) per function
- Balanced preset: O(n²) interprocedural
- Thorough preset: O(n³) with PTA

### Points-to Analysis (PTA)

**Purpose**: Determine what heap objects a pointer may reference.

```rust
pub struct PTAConfig {
    pub mode: PTAMode,              // Analysis precision
    pub max_iterations: usize,      // Worklist limit (default: 100)
    pub field_sensitive: bool,      // Track fields separately (default: false)
    pub context_sensitive: usize,   // Call-string depth (default: 1)
    pub enable_cycle_elimination: bool, // Break SCC cycles (default: true)
    pub use_cache: bool,            // Cache function summaries (default: true)
}

pub enum PTAMode {
    FlowInsensitive,    // Andersen's (O(n³))
    FlowSensitive,      // IFDS-based (expensive)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Thorough)
    .pta(|c| c
        .mode(PTAMode::FlowSensitive)
        .field_sensitive(true)
        .context_sensitive(2))
    .build()?;
```

**Cost Classes**:
- FlowInsensitive: High (O(n³))
- FlowSensitive: Extreme (O(n⁴))

### Clone Detection

**Purpose**: Find duplicate or similar code fragments.

```rust
pub struct CloneConfig {
    pub type1: Option<Type1Config>,  // Exact clones
    pub type2: Option<Type2Config>,  // Renamed clones
    pub type3: Option<Type3Config>,  // Near-miss clones
    pub type4: Option<Type4Config>,  // Semantic clones
    pub min_tokens: usize,           // Min clone size (default: 50)
    pub min_lines: usize,            // Min line count (default: 6)
}

pub enum CloneType {
    Type1,  // Exact match
    Type2,  // Renamed identifiers
    Type3,  // Gapped (near-miss)
    Type4,  // Semantic (embedding-based)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .clone(|c| c
        .min_tokens(100)
        .min_lines(10)
        .type3(Type3Config {
            max_gap_ratio: 0.3,
            enable_gapped_detection: true,
        }))
    .build()?;
```

### Chunking

**Purpose**: Split code into semantic chunks for indexing.

```rust
pub struct ChunkingConfig {
    pub max_chunk_tokens: usize,    // Max tokens per chunk (default: 512)
    pub overlap_tokens: usize,      // Overlap between chunks (default: 64)
    pub enable_semantic_split: bool, // Use AST boundaries (default: true)
    pub min_chunk_tokens: usize,    // Min chunk size (default: 50)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Fast)
    .chunking(|c| c
        .max_chunk_tokens(1024)
        .overlap_tokens(128))
    .build()?;
```

### Lexical Search

**Purpose**: Full-text search configuration (Tantivy).

```rust
pub struct LexicalConfig {
    pub enable_fuzzy: bool,         // Fuzzy matching (default: true)
    pub fuzzy_distance: u8,         // Levenshtein distance (default: 2)
    pub enable_ngram: bool,         // N-gram indexing (default: true)
    pub ngram_size: usize,          // N-gram size (default: 3)
    pub boost_exact_match: f32,     // Exact match boost (default: 2.0)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .lexical(|c| c
        .enable_fuzzy(true)
        .fuzzy_distance(2)
        .boost_exact_match(3.0))
    .build()?;
```

### Parallel Processing

**Purpose**: Control parallelization strategy.

```rust
pub struct ParallelConfig {
    pub workers: usize,             // Thread pool size (default: num_cpus)
    pub batch_size: usize,          // Files per batch (default: 100)
    pub enable_rayon: bool,         // Use Rayon (default: true)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Fast)
    .parallel(|c| c
        .workers(8)
        .batch_size(200))
    .build()?;
```

### Cache System

**Purpose**: 3-tier cache for watch mode and incremental builds.

```rust
pub struct CacheConfig {
    pub l0: SessionCacheConfig,     // In-memory (DashMap)
    pub l1: AdaptiveCacheConfig,    // Adaptive (Moka)
    pub l2: DiskCacheConfig,        // Persistent (rkyv + mmap)
    pub enable_background_l2_writes: bool,
}

pub struct SessionCacheConfig {
    pub max_entries: usize,         // Max items (default: 10,000)
    pub enable_bloom_filter: bool,  // Fast negative lookup (default: true)
    pub expected_items: usize,      // Bloom filter size hint (default: 100,000)
    pub false_positive_rate: f64,   // Bloom FP rate (default: 0.01)
}

pub struct AdaptiveCacheConfig {
    pub max_entries: usize,         // Max items (default: 1,000)
    pub max_bytes: usize,           // Max memory (default: 512MB)
    pub ttl_seconds: Duration,      // TTL (default: 1 hour)
}

pub struct DiskCacheConfig {
    pub cache_dir: PathBuf,         // Disk location (default: .cache/codegraph)
    pub max_disk_bytes: usize,      // Max disk usage (default: 10GB)
    pub enable_compression: bool,   // Compress entries (default: true)
    pub enable_mmap: bool,          // Memory-mapped I/O (default: true)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Fast)
    .cache(|mut c| {
        c.l0.max_entries = 20_000;
        c.l1.max_bytes = 1024 * 1024 * 1024; // 1GB
        c.l2.enable_compression = false; // Disable for speed
        c
    })
    .build()?;
```

### PageRank

**Purpose**: Compute node importance for RepoMap.

```rust
pub struct PageRankConfig {
    pub damping_factor: f64,        // Probability of random jump (default: 0.85)
    pub max_iterations: usize,      // Convergence limit (default: 100)
    pub convergence_threshold: f64, // Delta threshold (default: 1e-6)
    pub enable_personalization: bool, // Personalized PageRank (default: false)
}
```

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Thorough)
    .pagerank(|c| c
        .damping_factor(0.90)
        .max_iterations(200))
    .build()?;
```

---

## Performance Profiles

Every configuration has an associated **performance profile**:

```rust
pub struct PerformanceProfile {
    pub overall_cost: CostClass,    // Low/Medium/High/Extreme
    pub latency_band: LatencyBand,  // <1s / 1-10s / 10-60s / >60s
    pub memory_band: MemoryBand,    // <100MB / 100MB-1GB / 1GB-10GB / >10GB
}
```

### Cost Classes

- **Low**: Fast preset, minimal analysis
- **Medium**: Balanced preset, standard analysis
- **High**: Thorough preset, deep analysis
- **Extreme**: Custom configs with expensive algorithms (e.g., flow-sensitive PTA)

### Latency Bands

- **Sub-second** (<1s): Fast preset, small repos
- **Interactive** (1-10s): Balanced preset, medium repos
- **Batch** (10-60s): Thorough preset, large repos
- **Long-running** (>60s): Extreme configs or very large repos

### Memory Bands

- **Low** (<100MB): Fast preset, small files
- **Medium** (100MB-1GB): Balanced preset, typical repos
- **High** (1GB-10GB): Thorough preset, large codebases
- **VeryHigh** (>10GB): Extreme configs or monorepos

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Thorough).build()?;
let profile = config.performance_profile();

println!("Cost: {:?}", profile.overall_cost);  // High
println!("Latency: {:?}", profile.latency_band);  // Batch
println!("Memory: {:?}", profile.memory_band);  // High
```

---

## YAML Schema

### Schema Version 1

All YAML configs must specify `version: 1`.

```yaml
version: 1
preset: balanced

stages:
  taint: true
  pta: true
  clone: false

overrides:
  taint:
    max_depth: 50
    max_paths: 1000
    field_sensitive: true

  pta:
    mode: flow_insensitive
    max_iterations: 100

  cache:
    l0:
      max_entries: 20000
    l1:
      max_entries: 2000
      max_bytes: 1073741824  # 1GB
```

### Loading YAML

```rust
use codegraph_ir::config::PipelineConfig;

// Load from file
let config = PipelineConfig::from_yaml("config.yaml")?;

// Export to YAML
let yaml_str = config.to_yaml()?;
```

### YAML Validation

YAML loading performs:
1. Schema validation (deny_unknown_fields)
2. Version check (only v1 supported)
3. Range validation (min/max bounds)
4. Cross-stage validation (dependencies)

**Error Handling:**
```rust
match PipelineConfig::from_yaml("bad.yaml") {
    Ok(config) => { /* use config */ },
    Err(ConfigError::UnsupportedVersion { version }) => {
        eprintln!("Unsupported version: {}", version);
    },
    Err(ConfigError::InvalidYaml { message }) => {
        eprintln!("YAML error: {}", message);
    },
    Err(e) => {
        eprintln!("Config error: {}", e);
    }
}
```

---

## Validation

### Range Validation

Every numeric field has **min/max bounds**:

```rust
// Taint depth must be 1..=1000
config.taint(|c| c.max_depth(2000));  // ❌ Error in strict mode

// PTA iterations must be 1..=10000
config.pta(|c| c.max_iterations(0));  // ❌ Error
```

### Cross-Stage Validation

Some stages have **dependencies**:

- **Taint with PTA**: If `taint.use_points_to = true`, PTA must be enabled
- **Clone Type 4**: Requires chunking enabled for embeddings
- **Cache**: No dependencies

**Example:**
```rust
let config = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c.use_points_to(true))
    .build()?;  // ❌ Error: PTA not enabled

// Fix: Enable PTA
let config = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c.use_points_to(true))
    .pta(|c| c.mode(PTAMode::FlowInsensitive))
    .build()?;  // ✅ OK
```

### Strict vs Lenient Mode

- **Lenient** (default): Warnings only, auto-correction
- **Strict**: Fail fast on any violation

```rust
// Lenient: Warnings logged, config auto-corrected
let config = PipelineConfig::preset(Preset::Fast)
    .strict_mode(false)
    .taint(|c| c.max_depth(2000))  // ⚠️  Warning: clamped to 1000
    .build()?;

// Strict: Errors thrown
let config = PipelineConfig::preset(Preset::Fast)
    .strict_mode(true)
    .taint(|c| c.max_depth(2000))  // ❌ Error
    .build()?;
```

---

## Troubleshooting

### Common Issues

#### 1. "PTA required but not enabled"

**Problem**: Taint analysis uses PTA but PTA stage is disabled.

**Solution**:
```rust
// Add PTA config
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.use_points_to(true))
    .pta(|c| c.mode(PTAMode::FlowInsensitive))  // Add this
    .build()?;
```

#### 2. "YAML version not supported"

**Problem**: Using `version: 2` or missing version field.

**Solution**:
```yaml
# Always use version 1
version: 1
preset: balanced
```

#### 3. "Unknown field in YAML"

**Problem**: Typo or invalid field name.

**Solution**:
```yaml
# ❌ Wrong
overrides:
  taint:
    max_deth: 50  # Typo

# ✅ Correct
overrides:
  taint:
    max_depth: 50
```

#### 4. "Value out of range"

**Problem**: Numeric value exceeds bounds.

**Solution**:
```rust
// ❌ max_depth must be 1..=1000
config.taint(|c| c.max_depth(2000));

// ✅ Use valid range
config.taint(|c| c.max_depth(500));
```

#### 5. "Duration serialization error"

**Problem**: Trying to serialize Duration directly in YAML.

**Solution**: Duration is automatically handled as seconds (u64) by the config system. No manual conversion needed.

### Debug Tips

#### 1. Inspect Configuration

```rust
let config = PipelineConfig::preset(Preset::Balanced).build()?;

// Human-readable description
println!("{}", config.describe());

// Check specific stage
if let Some(taint) = config.taint() {
    println!("Taint depth: {}", taint.max_depth);
}

// Check performance profile
let profile = config.performance_profile();
println!("{:?}", profile);
```

#### 2. Check Provenance

```rust
let config = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c.max_depth(100))
    .build()?;

// Where did max_depth come from?
let source = config.provenance().get_source("taint.max_depth");
println!("Source: {:?}", source);  // ConfigSource::Builder
```

#### 3. Export to YAML

```rust
// Export current config to YAML for review
let config = PipelineConfig::preset(Preset::Balanced).build()?;
let yaml = config.to_yaml()?;
std::fs::write("debug-config.yaml", yaml)?;
```

### Performance Tuning

#### For Fast Feedback (<1s)

```rust
let config = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c
        .max_depth(10)
        .enable_interprocedural(false))
    .parallel(|c| c.workers(num_cpus::get()))
    .build()?;
```

#### For Security Analysis (Thorough)

```rust
let config = PipelineConfig::preset(Preset::Thorough)
    .taint(|c| c
        .max_depth(100)
        .field_sensitive(true)
        .detect_sanitizers(true)
        .use_points_to(true))
    .pta(|c| c
        .mode(PTAMode::FlowSensitive)
        .field_sensitive(true))
    .build()?;
```

#### For Large Codebases (Memory Constrained)

```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .cache(|mut c| {
        c.l1.max_bytes = 256 * 1024 * 1024;  // 256MB limit
        c.l2.max_disk_bytes = 2 * 1024 * 1024 * 1024;  // 2GB disk
        c
    })
    .parallel(|c| c.workers(4))  // Limit parallelism
    .build()?;
```

---

## Migration Guide

### From Old Config System

**Before** (ad-hoc settings):
```rust
let mut settings = TaintSettings::default();
settings.max_depth = 50;
settings.max_paths = 1000;
```

**After** (new config system):
```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50).max_paths(1000))
    .build()?;
```

### Adding New Stage Configs

1. Define config struct in `stage_configs.rs`:
```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MyStageConfig {
    pub setting1: usize,
    pub setting2: bool,
}

impl Default for MyStageConfig {
    fn default() -> Self {
        Self {
            setting1: 100,
            setting2: true,
        }
    }
}
```

2. Add field to `PipelineConfig`:
```rust
pub struct PipelineConfig {
    pub(crate) my_stage: Option<MyStageConfig>,
    // ...
}
```

3. Add builder method:
```rust
impl PipelineConfig {
    pub fn my_stage<F>(mut self, f: F) -> Self
    where F: FnOnce(MyStageConfig) -> MyStageConfig {
        let base = MyStageConfig::default();
        self.my_stage = Some(f(base));
        self.provenance.track_field("my_stage.*", ConfigSource::Builder);
        self
    }
}
```

4. Add getter in `ValidatedConfig`:
```rust
impl ValidatedConfig {
    pub fn my_stage(&self) -> Option<MyStageConfig> {
        self.0.my_stage.clone()
    }
}
```

---

## References

- RFC-001: Configuration System Design
- [Config Examples](config-examples.md)
- [YAML Examples](examples/)
- Source: `packages/codegraph-ir/src/config/`
