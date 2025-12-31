# Configuration System Examples

This document provides practical, real-world examples of using the Codegraph IR configuration system.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Security Analysis](#security-analysis)
3. [Performance Optimization](#performance-optimization)
4. [CI/CD Integration](#cicd-integration)
5. [Watch Mode / Development](#watch-mode--development)
6. [Large Codebase Scenarios](#large-codebase-scenarios)
7. [Custom Workflows](#custom-workflows)
8. [Python Bindings (Future)](#python-bindings-future)

---

## Basic Usage

### Example 1: Quick Start with Defaults

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Simplest possible usage
    let config = PipelineConfig::preset(Preset::Balanced).build()?;

    // Use config with orchestrator
    // let orchestrator = IRIndexingOrchestrator::new(config);
    // orchestrator.execute()?;

    Ok(())
}
```

### Example 2: Fast Mode for Interactive Development

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Fast mode: <1s latency for quick feedback
    let config = PipelineConfig::preset(Preset::Fast).build()?;

    println!("Performance profile: {:?}", config.performance_profile());
    // Output: CostClass::Low, LatencyBand::SubSecond

    Ok(())
}
```

### Example 3: Override Single Setting

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Start with balanced, increase taint depth
    let config = PipelineConfig::preset(Preset::Balanced)
        .taint(|c| c.max_depth(50))
        .build()?;

    let taint = config.taint().unwrap();
    assert_eq!(taint.max_depth, 50);

    Ok(())
}
```

### Example 4: Load from YAML

```rust
use codegraph_ir::config::PipelineConfig;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load team configuration from YAML
    let config = PipelineConfig::from_yaml("config/team-standard.yaml")?;

    // Inspect loaded config
    println!("{}", config.describe());

    Ok(())
}
```

---

## Security Analysis

### Example 5: Security-Focused Configuration

```rust
use codegraph_ir::config::{PipelineConfig, Preset, PTAMode};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config = PipelineConfig::preset(Preset::Thorough)
        // Deep taint analysis
        .taint(|c| c
            .max_depth(100)
            .max_paths(5000)
            .field_sensitive(true)
            .detect_sanitizers(true)
            .use_points_to(true)
            .enable_interprocedural(true))

        // Precise points-to analysis
        .pta(|c| c
            .mode(PTAMode::FlowSensitive)
            .field_sensitive(true)
            .context_sensitive(2))

        .build()?;

    // Performance: Extreme cost, >60s latency, >10GB memory
    let profile = config.performance_profile();
    println!("Cost: {:?}", profile.overall_cost);  // Extreme

    Ok(())
}
```

**YAML Equivalent:**
```yaml
# config/security-focused.yaml
version: 1
preset: thorough

stages:
  taint: true
  pta: true

overrides:
  taint:
    max_depth: 100
    max_paths: 5000
    field_sensitive: true
    detect_sanitizers: true
    use_points_to: true
    enable_interprocedural: true
    use_ssa: false
    worklist_max_iterations: 100

  pta:
    mode: flow_sensitive
    max_iterations: 100
    field_sensitive: true
    context_sensitive: 2
    enable_cycle_elimination: true
    use_cache: true
```

### Example 6: SQL Injection Detection

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Optimized for SQL injection detection
    let config = PipelineConfig::preset(Preset::Balanced)
        .taint(|c| c
            .max_depth(30)              // Moderate depth for DB queries
            .detect_sanitizers(true)    // Detect prepared statements
            .field_sensitive(true)      // Track object properties
            .enable_interprocedural(true)) // Cross-function tracking
        .build()?;

    // Use with security scanner
    // scanner.detect_sql_injection(config)?;

    Ok(())
}
```

### Example 7: XSS Detection

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Optimized for XSS detection
    let config = PipelineConfig::preset(Preset::Balanced)
        .taint(|c| c
            .max_depth(20)              // Shallow (UI layer)
            .detect_sanitizers(true)    // Detect escaping functions
            .field_sensitive(false)     // Less precision needed
            .enable_interprocedural(true))
        .build()?;

    Ok(())
}
```

---

## Performance Optimization

### Example 8: Fast Mode for CI

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Fast mode for CI checks (<10s for medium repos)
    let config = PipelineConfig::preset(Preset::Fast)
        .parallel(|c| c.workers(num_cpus::get()))
        .cache(|mut c| {
            c.enable_background_l2_writes = true;
            c.l1.max_bytes = 256 * 1024 * 1024;  // 256MB
            c
        })
        .build()?;

    // Disable expensive analyses
    config.stages().disable_clone();

    Ok(())
}
```

### Example 9: Incremental Analysis (Watch Mode)

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Optimized for watch mode with aggressive caching
    let config = PipelineConfig::preset(Preset::Fast)
        .cache(|mut c| {
            // Large L0 cache for recent files
            c.l0.max_entries = 50_000;
            c.l0.enable_bloom_filter = true;

            // Large L1 for hot paths
            c.l1.max_entries = 5_000;
            c.l1.max_bytes = 1024 * 1024 * 1024;  // 1GB
            c.l1.ttl_seconds = std::time::Duration::from_secs(3600);  // 1 hour

            // Fast L2 writes
            c.enable_background_l2_writes = true;
            c.l2.enable_compression = false;  // Trade space for speed
            c.l2.enable_mmap = true;

            c
        })
        .build()?;

    Ok(())
}
```

### Example 10: Memory-Constrained Environment

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Limit memory usage to <500MB
    let config = PipelineConfig::preset(Preset::Fast)
        .cache(|mut c| {
            c.l0.max_entries = 5_000;
            c.l1.max_entries = 500;
            c.l1.max_bytes = 256 * 1024 * 1024;  // 256MB
            c.l2.max_disk_bytes = 1024 * 1024 * 1024;  // 1GB disk
            c
        })
        .parallel(|c| c.workers(2))  // Limit parallelism
        .taint(|c| c.max_depth(10).max_paths(100))
        .build()?;

    // Disable memory-intensive analyses
    config.stages().disable_pta();
    config.stages().disable_clone();

    Ok(())
}
```

---

## CI/CD Integration

### Example 11: GitHub Actions

```rust
use codegraph_ir::config::{PipelineConfig, Preset};
use std::env;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Detect CI environment
    let is_ci = env::var("CI").is_ok();

    let config = if is_ci {
        // CI mode: Fast feedback, limited resources
        PipelineConfig::preset(Preset::Fast)
            .parallel(|c| c.workers(2))  // GitHub Actions has 2 cores
            .cache(|mut c| {
                c.l1.max_bytes = 512 * 1024 * 1024;  // 512MB
                c
            })
            .build()?
    } else {
        // Local development: Balanced
        PipelineConfig::preset(Preset::Balanced).build()?
    };

    Ok(())
}
```

**GitHub Actions Workflow:**
```yaml
# .github/workflows/analysis.yml
name: Code Analysis

on: [push, pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Analysis
        run: |
          cargo run --bin analyze -- --config ci-fast.yaml
```

### Example 12: Pre-commit Hook

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Pre-commit: Ultra-fast mode for changed files only
    let config = PipelineConfig::preset(Preset::Fast)
        .taint(|c| c
            .max_depth(5)
            .max_paths(50)
            .enable_interprocedural(false))
        .build()?;

    // Analyze only staged files
    // let staged_files = get_staged_files()?;
    // analyzer.analyze_files(staged_files, config)?;

    Ok(())
}
```

### Example 13: Nightly Security Scan

```rust
use codegraph_ir::config::{PipelineConfig, Preset, PTAMode};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Nightly: Thorough analysis, no time constraints
    let config = PipelineConfig::preset(Preset::Thorough)
        .taint(|c| c
            .max_depth(100)
            .max_paths(10_000)
            .field_sensitive(true)
            .detect_sanitizers(true)
            .use_points_to(true))
        .pta(|c| c
            .mode(PTAMode::FlowSensitive)
            .field_sensitive(true))
        .clone(|c| c
            .min_tokens(100)
            .min_lines(10))
        .build()?;

    // Full repository scan
    // scanner.full_scan("/repo", config)?;

    Ok(())
}
```

---

## Watch Mode / Development

### Example 14: File Watcher Integration

```rust
use codegraph_ir::config::{PipelineConfig, Preset};
use notify::{Watcher, RecursiveMode, watcher};
use std::sync::mpsc::channel;
use std::time::Duration;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Watch mode configuration
    let config = PipelineConfig::preset(Preset::Fast)
        .cache(|mut c| {
            c.l0.max_entries = 20_000;
            c.l1.ttl_seconds = Duration::from_secs(1800);  // 30 min
            c.enable_background_l2_writes = true;
            c
        })
        .parallel(|c| c.workers(num_cpus::get()))
        .build()?;

    // Setup file watcher
    let (tx, rx) = channel();
    let mut watcher = watcher(tx, Duration::from_secs(1))?;
    watcher.watch("src/", RecursiveMode::Recursive)?;

    // Watch loop
    loop {
        match rx.recv() {
            Ok(event) => {
                // Incremental analysis on file change
                println!("File changed: {:?}", event);
                // analyzer.incremental_update(event, &config)?;
            }
            Err(e) => println!("Watch error: {:?}", e),
        }
    }
}
```

### Example 15: LSP Server Integration

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // LSP server: Ultra-low latency (<100ms)
    let config = PipelineConfig::preset(Preset::Fast)
        .cache(|mut c| {
            c.l0.max_entries = 100_000;  // Large cache for IDE
            c.l1.max_entries = 10_000;
            c.l1.ttl_seconds = std::time::Duration::from_secs(7200);  // 2 hours
            c
        })
        .taint(|c| c
            .max_depth(3)               // Very shallow
            .enable_interprocedural(false))
        .build()?;

    // Disable heavy analyses for LSP
    config.stages().disable_clone();
    config.stages().disable_pta();

    Ok(())
}
```

---

## Large Codebase Scenarios

### Example 16: Monorepo Configuration

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Monorepo: Balanced depth, high parallelism
    let config = PipelineConfig::preset(Preset::Balanced)
        .parallel(|c| c
            .workers(16)                // High CPU count
            .batch_size(500))           // Large batches
        .cache(|mut c| {
            c.l1.max_bytes = 4 * 1024 * 1024 * 1024;  // 4GB
            c.l2.max_disk_bytes = 50 * 1024 * 1024 * 1024;  // 50GB
            c.l2.enable_compression = true;
            c
        })
        .chunking(|c| c
            .max_chunk_tokens(1024)
            .overlap_tokens(128))
        .build()?;

    Ok(())
}
```

### Example 17: Microservices Repository

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Microservices: Per-service analysis
    let config = PipelineConfig::preset(Preset::Balanced)
        .taint(|c| c
            .max_depth(30)              // Cross-service calls
            .enable_interprocedural(true))
        .chunking(|c| c
            .max_chunk_tokens(512)      // Smaller services
            .enable_semantic_split(true))
        .build()?;

    // Analyze each service separately
    // for service in services {
    //     analyzer.analyze_service(service, &config)?;
    // }

    Ok(())
}
```

### Example 18: Legacy Codebase Migration

```rust
use codegraph_ir::config::{PipelineConfig, Preset, CloneType};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Legacy codebase: Focus on duplication detection
    let config = PipelineConfig::preset(Preset::Balanced)
        .clone(|c| c
            .min_tokens(50)             // Detect smaller clones
            .min_lines(6)
            .type3(crate::config::Type3Config {
                max_gap_ratio: 0.3,
                enable_gapped_detection: true,
            }))
        .build()?;

    // Focus on clone detection
    config.stages().disable_taint();
    config.stages().disable_pta();

    Ok(())
}
```

---

## Custom Workflows

### Example 19: Hybrid Search Configuration

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Optimize for hybrid search (lexical + semantic + graph)
    let config = PipelineConfig::preset(Preset::Balanced)
        .lexical(|c| c
            .enable_fuzzy(true)
            .fuzzy_distance(2)
            .enable_ngram(true)
            .boost_exact_match(3.0))
        .chunking(|c| c
            .max_chunk_tokens(512)
            .overlap_tokens(64)
            .enable_semantic_split(true))
        .pagerank(|c| c
            .damping_factor(0.85)
            .max_iterations(100))
        .build()?;

    Ok(())
}
```

### Example 20: Code Review Assistant

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Code review: Diff-based analysis
    let config = PipelineConfig::preset(Preset::Fast)
        .taint(|c| c
            .max_depth(20)
            .detect_sanitizers(true))
        .clone(|c| c
            .min_tokens(30)             // Detect copy-paste
            .min_lines(5))
        .build()?;

    // Analyze only diff files
    // let diff_files = get_pr_diff()?;
    // analyzer.analyze_diff(diff_files, config)?;

    Ok(())
}
```

### Example 21: Refactoring Analysis

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Refactoring: Focus on graph structure
    let config = PipelineConfig::preset(Preset::Balanced)
        .pagerank(|c| c
            .damping_factor(0.85)
            .enable_personalization(true))
        .build()?;

    // Enable all graph stages
    config.stages().enable_cfg();
    config.stages().enable_dfg();
    config.stages().enable_pdg();

    Ok(())
}
```

---

## Python Bindings (Future)

### Example 22: Python API Usage (Planned)

```python
# Future Python bindings (via PyO3)
from codegraph_ir import PipelineConfig, Preset

# Simple preset
config = PipelineConfig.preset(Preset.BALANCED)

# Override with patch (since Python doesn't have closures)
from codegraph_ir import TaintConfigPatch

taint_patch = TaintConfigPatch(
    max_depth=50,
    max_paths=1000,
    field_sensitive=True
)

config = PipelineConfig.preset(Preset.BALANCED).apply_taint_patch(taint_patch)

# Load from YAML
config = PipelineConfig.from_yaml("config.yaml")

# Use with orchestrator
orchestrator = IRIndexingOrchestrator(config)
result = orchestrator.execute()
```

### Example 23: Environment Variable Override (Planned)

```python
import os
from codegraph_ir import PipelineConfig, Preset

# Set environment variables
os.environ['CODEGRAPH_TAINT_MAX_DEPTH'] = '100'
os.environ['CODEGRAPH_PARALLEL_WORKERS'] = '8'

# Load config with env overrides
config = PipelineConfig.preset(Preset.BALANCED)

# Env vars override preset values
assert config.taint().max_depth == 100
assert config.parallel().workers == 8
```

---

## Testing Configurations

### Example 24: Unit Test Configuration

```rust
#[cfg(test)]
mod tests {
    use codegraph_ir::config::{PipelineConfig, Preset};

    #[test]
    fn test_with_minimal_config() {
        let config = PipelineConfig::preset(Preset::Fast)
            .taint(|c| c.max_depth(5))
            .build()
            .unwrap();

        // Use minimal config for fast tests
        assert_eq!(config.taint().unwrap().max_depth, 5);
    }
}
```

### Example 25: Integration Test Configuration

```rust
#[cfg(test)]
mod integration_tests {
    use codegraph_ir::config::{PipelineConfig, Preset};

    #[test]
    fn test_with_thorough_config() {
        let config = PipelineConfig::preset(Preset::Thorough).build().unwrap();

        // Use thorough config for comprehensive integration tests
        // analyzer.full_analysis(test_repo, config).unwrap();
    }
}
```

---

## Comparison Table

| Use Case | Preset | Taint Depth | PTA Mode | Parallel Workers | Latency | Memory |
|----------|--------|-------------|----------|------------------|---------|--------|
| **IDE LSP** | Fast | 3 | Disabled | num_cpus | <100ms | <100MB |
| **Pre-commit** | Fast | 5 | Disabled | 2 | <1s | <200MB |
| **CI/CD** | Fast | 10 | Disabled | 2-4 | <10s | <500MB |
| **Code Review** | Fast | 20 | Disabled | 4 | 1-10s | 100-500MB |
| **Watch Mode** | Fast | 10 | Disabled | num_cpus | <1s | 100MB-1GB |
| **Daily Build** | Balanced | 20 | FlowInsensitive | 8 | 10-60s | 1-5GB |
| **Nightly Scan** | Thorough | 100 | FlowSensitive | 16 | >60s | >10GB |
| **Security Audit** | Thorough | 100 | FlowSensitive | 16 | >60s | >10GB |

---

## Best Practices

### 1. Start Simple

```rust
// ✅ Good: Start with preset
let config = PipelineConfig::preset(Preset::Balanced).build()?;

// ❌ Bad: Over-configure from the start
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50).max_paths(1000))
    .pta(|c| c.mode(PTAMode::FlowSensitive))
    .clone(|c| c.min_tokens(100))
    .build()?;  // Too complex for initial setup
```

### 2. Use YAML for Team Standards

```rust
// ✅ Good: Team config in version control
let config = PipelineConfig::from_yaml("config/team.yaml")?;

// ❌ Bad: Hardcoded configs scattered in code
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50))  // Hardcoded value
    .build()?;
```

### 3. Profile Before Optimizing

```rust
// ✅ Good: Check performance profile first
let config = PipelineConfig::preset(Preset::Balanced).build()?;
let profile = config.performance_profile();
println!("{:?}", profile);  // Understand baseline

// Then optimize
let config = PipelineConfig::preset(Preset::Fast)
    .parallel(|c| c.workers(8))
    .build()?;
```

### 4. Use Strict Mode in CI

```rust
// ✅ Good: Fail fast in CI
let config = PipelineConfig::preset(Preset::Fast)
    .strict_mode(true)  // Errors for any violation
    .build()?;

// ❌ Bad: Lenient mode hides issues
let config = PipelineConfig::preset(Preset::Fast)
    .strict_mode(false)  // Warnings only
    .build()?;
```

### 5. Cache Aggressively for Watch Mode

```rust
// ✅ Good: Large caches for watch mode
let config = PipelineConfig::preset(Preset::Fast)
    .cache(|mut c| {
        c.l0.max_entries = 50_000;
        c.l1.max_bytes = 1024 * 1024 * 1024;  // 1GB
        c
    })
    .build()?;
```

---

## Environment-Specific Configs

### Development
```rust
let config = PipelineConfig::preset(Preset::Fast)
    .cache(|mut c| {
        c.l1.ttl_seconds = std::time::Duration::from_secs(1800);  // 30 min
        c
    })
    .build()?;
```

### Staging
```rust
let config = PipelineConfig::preset(Preset::Balanced).build()?;
```

### Production
```rust
let config = PipelineConfig::preset(Preset::Thorough)
    .taint(|c| c
        .max_depth(100)
        .field_sensitive(true)
        .detect_sanitizers(true))
    .build()?;
```

---

## Summary

This document provides 25+ practical examples covering:

- ✅ **Basic usage** (presets, overrides, YAML)
- ✅ **Security analysis** (taint, PTA, vulnerability detection)
- ✅ **Performance** (fast mode, memory limits, parallelism)
- ✅ **CI/CD** (GitHub Actions, pre-commit, nightly scans)
- ✅ **Watch mode** (file watcher, LSP, incremental)
- ✅ **Large codebases** (monorepos, microservices, legacy)
- ✅ **Custom workflows** (hybrid search, code review, refactoring)
- ✅ **Future Python bindings** (planned API)

**Next Steps:**
- See [Config System Guide](config-system-guide.md) for detailed API reference
- See [examples/](examples/) for YAML configuration files
- Explore source: `packages/codegraph-ir/src/config/`
