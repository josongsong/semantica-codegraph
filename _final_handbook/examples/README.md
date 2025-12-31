# Configuration Examples

This directory contains example YAML configurations for various use cases.

## Quick Reference

| File | Use Case | Latency | Memory | Cost |
|------|----------|---------|--------|------|
| [fast-preset.yaml](fast-preset.yaml) | IDE, pre-commit | <1s | <100MB | Low |
| [balanced-preset.yaml](balanced-preset.yaml) | Daily builds, code review | 10-60s | 1-5GB | Medium |
| [thorough-preset.yaml](thorough-preset.yaml) | Nightly scans, audits | >60s | >10GB | High |
| [security-focused.yaml](security-focused.yaml) | Security audits | >60s | >10GB | Extreme |
| [performance-focused.yaml](performance-focused.yaml) | Clone detection | 10-60s | 1-5GB | Medium |
| [ci-fast.yaml](ci-fast.yaml) | CI/CD pipelines | <10s | <500MB | Low |
| [watch-mode.yaml](watch-mode.yaml) | LSP, file watcher | <100ms | 100MB-1GB | Low |
| [monorepo.yaml](monorepo.yaml) | Large monorepos | 10-60s | 1-10GB | High |

## Usage

### Load from YAML
```rust
use codegraph_ir::config::PipelineConfig;

let config = PipelineConfig::from_yaml("examples/balanced-preset.yaml")?;
```

### Customize YAML
```bash
# Copy example
cp examples/balanced-preset.yaml config/team.yaml

# Edit for your team
vim config/team.yaml

# Use in code
let config = PipelineConfig::from_yaml("config/team.yaml")?;
```

## Configuration by Use Case

### 1. Fast Preset - Interactive Development

**File**: [fast-preset.yaml](fast-preset.yaml)

**Use cases**:
- IDE integration (LSP, autocomplete)
- Pre-commit hooks
- Quick local checks

**Key features**:
- Minimal analysis (<1s)
- Small memory footprint (<100MB)
- Aggressive caching
- High parallelism

**Trade-offs**:
- Low precision (misses complex bugs)
- No interprocedural analysis
- Limited clone detection

---

### 2. Balanced Preset - General Development

**File**: [balanced-preset.yaml](balanced-preset.yaml)

**Use cases**:
- Daily builds
- Code review automation
- General development workflow

**Key features**:
- Moderate analysis (10-60s)
- Reasonable memory (1-5GB)
- Taint + clone detection
- Cross-function analysis

**Trade-offs**:
- Moderate precision (catches most bugs)
- Some false positives
- Medium latency

---

### 3. Thorough Preset - Comprehensive Analysis

**File**: [thorough-preset.yaml](thorough-preset.yaml)

**Use cases**:
- Nightly security scans
- Release validation
- Compliance checks

**Key features**:
- Deep analysis (>60s)
- Large memory (>10GB)
- All detection types
- Field-sensitive analysis

**Trade-offs**:
- High latency (not interactive)
- High resource usage
- Maximum precision

---

### 4. Security-Focused - Vulnerability Detection

**File**: [security-focused.yaml](security-focused.yaml)

**Use cases**:
- Security audits
- Vulnerability scanning
- Compliance validation

**Key features**:
- Flow-sensitive PTA (O(n⁴))
- Deep taint analysis (100 depth)
- Sanitizer detection
- 3-CFA context sensitivity

**Trade-offs**:
- Extreme cost (slowest)
- Very high memory (>10GB)
- Maximum precision (fewest false negatives)

**Performance warning**: This config is **very expensive**. Only use for security-critical analysis or nightly scans.

---

### 5. Performance-Focused - Code Quality

**File**: [performance-focused.yaml](performance-focused.yaml)

**Use cases**:
- Clone detection
- Refactoring analysis
- Code quality metrics

**Key features**:
- Comprehensive clone detection (Type 1-4)
- RepoMap for structure
- Semantic search
- Higher overlap for clones

**Trade-offs**:
- Moderate cost (10-60s)
- Clone detection overhead
- No security analysis

---

### 6. CI/CD Fast - Pipeline Integration

**File**: [ci-fast.yaml](ci-fast.yaml)

**Use cases**:
- GitHub Actions
- GitLab CI
- Jenkins pipelines

**Key features**:
- Fast feedback (<10s)
- Limited resources (2 cores, 512MB)
- Minimal caching
- Essential checks only

**Trade-offs**:
- Low precision (basic checks)
- No expensive analyses
- CI environment optimized

**GitHub Actions example**:
```yaml
- name: Run Analysis
  run: |
    cargo run --bin analyze -- --config examples/ci-fast.yaml
```

---

### 7. Watch Mode - Real-time Updates

**File**: [watch-mode.yaml](watch-mode.yaml)

**Use cases**:
- LSP server
- File watcher
- IDE background analysis

**Key features**:
- Ultra-fast (<100ms)
- Aggressive caching (1GB L1)
- Incremental updates
- Async L2 writes

**Trade-offs**:
- Minimal analysis (parsing only)
- Large cache memory
- No security/clone detection

**Integration example**:
```rust
use notify::{Watcher, RecursiveMode, watcher};
use codegraph_ir::config::PipelineConfig;

let config = PipelineConfig::from_yaml("examples/watch-mode.yaml")?;
let mut watcher = watcher(tx, Duration::from_secs(1))?;
watcher.watch("src/", RecursiveMode::Recursive)?;
```

---

### 8. Monorepo - Large Codebases

**File**: [monorepo.yaml](monorepo.yaml)

**Use cases**:
- Monorepos (>1M LOC)
- Microservices repositories
- Multi-project workspaces

**Key features**:
- High parallelism (16 workers)
- Large caches (4GB L1, 100GB L2)
- Large batches (500 files)
- Scalable chunking (1024 tokens)

**Trade-offs**:
- High resource usage
- Moderate depth (not exhaustive)
- Optimized for scale

**Resource requirements**:
- CPU: 16+ cores
- Memory: 8-16GB
- Disk: 100GB+ for cache

---

## Customization Guide

### Override Specific Values

```yaml
# Start with a preset
version: 1
preset: balanced

# Override only what you need
overrides:
  taint:
    max_depth: 30  # Increase from balanced default (20)
```

### Environment-Specific Configs

```bash
# Development
config/dev.yaml -> fast-preset.yaml (symlink)

# Staging
config/staging.yaml -> balanced-preset.yaml

# Production
config/prod.yaml -> thorough-preset.yaml
```

### Team Standards

```yaml
# config/team-standard.yaml
version: 1
preset: balanced

# Team-specific overrides
overrides:
  taint:
    max_depth: 25
    detect_sanitizers: true

  parallel:
    workers: 8  # Team CI has 8 cores

  cache:
    l2:
      cache_dir: "/shared/cache/codegraph"  # Shared team cache
```

## Schema Validation

All YAML files must include `version: 1`:

```yaml
# ✅ Valid
version: 1
preset: balanced

# ❌ Invalid (missing version)
preset: balanced

# ❌ Invalid (unsupported version)
version: 2
preset: balanced
```

## Field Reference

### Common Fields

- `preset`: Base configuration (`fast`, `balanced`, `thorough`)
- `stages`: On/off switches for pipeline stages
- `overrides`: Fine-grained configuration overrides

### Override Sections

- `taint`: Taint analysis configuration
- `pta`: Points-to analysis configuration
- `clone`: Clone detection configuration
- `chunking`: Code chunking configuration
- `lexical`: Lexical search configuration
- `parallel`: Parallelization configuration
- `cache`: Cache system configuration
- `pagerank`: PageRank configuration

See [Config System Guide](../config-system-guide.md) for full field reference.

## Testing Configurations

### Validate YAML

```rust
use codegraph_ir::config::PipelineConfig;

// Test loading
let config = PipelineConfig::from_yaml("examples/balanced-preset.yaml")?;

// Validate fields
assert_eq!(config.taint().unwrap().max_depth, 20);
```

### Compare Configurations

```rust
let fast = PipelineConfig::from_yaml("examples/fast-preset.yaml")?;
let balanced = PipelineConfig::from_yaml("examples/balanced-preset.yaml")?;

println!("Fast:     {:?}", fast.performance_profile());
println!("Balanced: {:?}", balanced.performance_profile());
```

## Best Practices

1. **Start with presets** - Don't over-configure initially
2. **Use YAML for teams** - Version control team standards
3. **Test before deploying** - Validate configs in staging
4. **Monitor performance** - Profile before optimizing
5. **Document overrides** - Add comments explaining why

## Troubleshooting

### "YAML parse error"
- Check YAML syntax (proper indentation)
- Ensure `version: 1` is present
- Validate field names (no typos)

### "Value out of range"
- Check numeric bounds (e.g., `max_depth: 1..=1000`)
- See guide for valid ranges

### "Stage dependency missing"
- Enable required stages (e.g., PTA for `use_points_to`)
- See guide for cross-stage dependencies

## Related Documentation

- [Config System Guide](../config-system-guide.md) - Full API reference
- [Config Examples](../config-examples.md) - Code examples
- Source: `packages/codegraph-ir/src/config/`

## Contributing

To add a new example:

1. Create `examples/my-use-case.yaml`
2. Add entry to this README
3. Test with `PipelineConfig::from_yaml()`
4. Document use case and trade-offs
