# Codegraph IR Configuration System - Final Handbook

**RFC-001: SOTA Configuration System Documentation**

This handbook provides comprehensive documentation for the Codegraph IR configuration system, a production-ready 3-tier configuration architecture designed for maximum extensibility with progressive disclosure.

## 📚 Documentation Structure

### 1. [Config System Guide](config-system-guide.md)
**Complete API reference and technical documentation**

Contents:
- Quick Start (Presets, Builder API, YAML)
- Architecture (3-tier design, merge precedence, provenance)
- API Reference (all types, methods, parameters)
- Stage Configurations (detailed reference for each stage)
- Performance Profiles (cost classes, latency bands, memory bands)
- YAML Schema (v1 specification)
- Validation (range checks, cross-stage dependencies)
- Troubleshooting (common issues, debug tips)
- Migration Guide (from old config system)

**Target audience**: Developers, power users, contributors

---

### 2. [Config Examples](config-examples.md)
**25+ practical, real-world usage examples**

Contents:
- Basic Usage (presets, overrides, YAML loading)
- Security Analysis (SQL injection, XSS, vulnerability detection)
- Performance Optimization (CI mode, watch mode, memory limits)
- CI/CD Integration (GitHub Actions, pre-commit, nightly scans)
- Watch Mode / Development (LSP, file watcher, incremental)
- Large Codebase Scenarios (monorepos, microservices, legacy)
- Custom Workflows (hybrid search, code review, refactoring)
- Python Bindings (future API examples)
- Testing Configurations (unit tests, integration tests)
- Best Practices (dos and don'ts)

**Target audience**: All users (beginners to advanced)

---

### 3. [Example YAML Files](examples/)
**Production-ready configuration templates**

Available configurations:
- [fast-preset.yaml](examples/fast-preset.yaml) - IDE, pre-commit (<1s, <100MB)
- [balanced-preset.yaml](examples/balanced-preset.yaml) - Daily builds (10-60s, 1-5GB)
- [thorough-preset.yaml](examples/thorough-preset.yaml) - Nightly scans (>60s, >10GB)
- [security-focused.yaml](examples/security-focused.yaml) - Security audits (Extreme cost)
- [performance-focused.yaml](examples/performance-focused.yaml) - Clone detection
- [ci-fast.yaml](examples/ci-fast.yaml) - CI/CD pipelines (<10s, <500MB)
- [watch-mode.yaml](examples/watch-mode.yaml) - LSP, file watcher (<100ms)
- [monorepo.yaml](examples/monorepo.yaml) - Large repositories (>1M LOC)

See [examples/README.md](examples/README.md) for detailed descriptions and usage.

**Target audience**: All users (copy-paste ready)

---

## 🚀 Quick Start

### For 90% of Users: Use a Preset

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

// Fast mode: Quick feedback
let config = PipelineConfig::preset(Preset::Fast).build()?;

// Balanced mode: Default for most cases
let config = PipelineConfig::preset(Preset::Balanced).build()?;

// Thorough mode: Maximum analysis
let config = PipelineConfig::preset(Preset::Thorough).build()?;
```

### For 9% of Users: Override Specific Stages

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50).max_paths(1000))
    .pta(|c| c.mode(PTAMode::FlowInsensitive))
    .build()?;
```

### For 1% of Users: Complete Control via YAML

```yaml
# config/team-standard.yaml
version: 1
preset: balanced

stages:
  taint: true
  pta: true

overrides:
  taint:
    max_depth: 50
    max_paths: 1000
    field_sensitive: true
```

```rust
let config = PipelineConfig::from_yaml("config/team-standard.yaml")?;
```

---

## 📖 Learning Path

### Beginner
1. Read [Quick Start](#quick-start) above
2. Browse [Config Examples](config-examples.md) Examples 1-4
3. Copy [examples/balanced-preset.yaml](examples/balanced-preset.yaml)

### Intermediate
1. Read [Config System Guide](config-system-guide.md) Sections 1-3
2. Review [Config Examples](config-examples.md) Examples 5-15
3. Customize YAML for your team

### Advanced
1. Study [Config System Guide](config-system-guide.md) complete reference
2. Review all [Config Examples](config-examples.md)
3. Implement custom presets or validation rules

---

## 🎯 Use Case Index

Find the right configuration for your scenario:

| Use Case | Preset | YAML Template | Example Code |
|----------|--------|---------------|--------------|
| **IDE Integration** | Fast | [watch-mode.yaml](examples/watch-mode.yaml) | [Example 15](config-examples.md#example-15-lsp-server-integration) |
| **Pre-commit Hook** | Fast | [ci-fast.yaml](examples/ci-fast.yaml) | [Example 12](config-examples.md#example-12-pre-commit-hook) |
| **Daily Build** | Balanced | [balanced-preset.yaml](examples/balanced-preset.yaml) | [Example 4](config-examples.md#example-4-load-from-yaml) |
| **Code Review** | Fast | [ci-fast.yaml](examples/ci-fast.yaml) | [Example 20](config-examples.md#example-20-code-review-assistant) |
| **Security Audit** | Thorough | [security-focused.yaml](examples/security-focused.yaml) | [Example 5](config-examples.md#example-5-security-focused-configuration) |
| **Nightly Scan** | Thorough | [thorough-preset.yaml](examples/thorough-preset.yaml) | [Example 13](config-examples.md#example-13-nightly-security-scan) |
| **Clone Detection** | Balanced | [performance-focused.yaml](examples/performance-focused.yaml) | [Example 18](config-examples.md#example-18-legacy-codebase-migration) |
| **Monorepo** | Balanced | [monorepo.yaml](examples/monorepo.yaml) | [Example 16](config-examples.md#example-16-monorepo-configuration) |
| **CI/CD** | Fast | [ci-fast.yaml](examples/ci-fast.yaml) | [Example 11](config-examples.md#example-11-github-actions) |
| **Watch Mode** | Fast | [watch-mode.yaml](examples/watch-mode.yaml) | [Example 14](config-examples.md#example-14-file-watcher-integration) |

---

## 🔧 Configuration by Environment

### Development
```bash
# Use fast preset for quick feedback
cp examples/fast-preset.yaml config/dev.yaml
```

### Staging
```bash
# Use balanced preset for validation
cp examples/balanced-preset.yaml config/staging.yaml
```

### Production
```bash
# Use thorough preset for comprehensive analysis
cp examples/thorough-preset.yaml config/prod.yaml
```

### CI/CD
```bash
# Use CI-optimized preset
cp examples/ci-fast.yaml .github/workflows/config.yaml
```

---

## 📊 Performance Comparison

| Preset | Latency | Memory | Cost | Precision |
|--------|---------|--------|------|-----------|
| **Fast** | <1s | <100MB | Low | 70% |
| **Balanced** | 10-60s | 1-5GB | Medium | 85% |
| **Thorough** | >60s | >10GB | High | 95% |
| **Security** | >60s | >10GB | Extreme | 99% |

**Legend**:
- **Latency**: Time to analyze medium-sized repository
- **Memory**: Peak RAM usage
- **Cost**: Computational complexity
- **Precision**: Bug detection accuracy (approximate)

---

## 🛠️ Common Tasks

### Task 1: Enable Taint Analysis

```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50).detect_sanitizers(true))
    .build()?;
```

### Task 2: Optimize for CI

```rust
let config = PipelineConfig::from_yaml("examples/ci-fast.yaml")?;
```

### Task 3: Configure Watch Mode

```rust
let config = PipelineConfig::from_yaml("examples/watch-mode.yaml")?;
```

### Task 4: Deep Security Scan

```rust
let config = PipelineConfig::from_yaml("examples/security-focused.yaml")?;
```

### Task 5: Clone Detection

```rust
let config = PipelineConfig::from_yaml("examples/performance-focused.yaml")?;
```

---

## 🧪 Testing Your Configuration

### Validate YAML Syntax

```rust
use codegraph_ir::config::PipelineConfig;

let config = PipelineConfig::from_yaml("config/team.yaml")?;
println!("{}", config.describe());
```

### Check Performance Profile

```rust
let config = PipelineConfig::preset(Preset::Balanced).build()?;
let profile = config.performance_profile();

println!("Cost: {:?}", profile.overall_cost);
println!("Latency: {:?}", profile.latency_band);
println!("Memory: {:?}", profile.memory_band);
```

### Export to YAML

```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50))
    .build()?;

let yaml = config.to_yaml()?;
std::fs::write("debug-config.yaml", yaml)?;
```

---

## 🐛 Troubleshooting

### Common Issues

1. **"YAML version not supported"**
   - Ensure `version: 1` is present
   - See [Config System Guide - Troubleshooting](config-system-guide.md#troubleshooting)

2. **"PTA required but not enabled"**
   - Enable PTA when using `use_points_to: true`
   - See [Example 5](config-examples.md#example-5-security-focused-configuration)

3. **"Value out of range"**
   - Check numeric bounds (e.g., `max_depth: 1..=1000`)
   - Use strict mode to catch issues early

4. **Performance issues**
   - Start with Fast preset
   - Profile with `performance_profile()`
   - See [Performance Optimization](config-examples.md#performance-optimization)

See full [Troubleshooting Guide](config-system-guide.md#troubleshooting) for more details.

---

## 📚 Additional Resources

### Documentation
- [Config System Guide](config-system-guide.md) - Complete API reference
- [Config Examples](config-examples.md) - 25+ code examples
- [YAML Examples](examples/) - Production-ready templates

### Source Code
- `packages/codegraph-ir/src/config/` - Configuration system implementation
- `packages/codegraph-ir/src/features/cache/config.rs` - Cache configuration
- `packages/codegraph-ir/src/features/repomap/infrastructure/mod.rs` - PageRank configuration

### Related RFCs
- RFC-001: Configuration System Design
- RFC-CONFIG-SYSTEM: Tiered Cache Integration
- RFC-078: Lexical Search Configuration

---

## 🤝 Contributing

### Adding New Stage Configurations

See [Migration Guide](config-system-guide.md#migration-guide) for adding new stage configs.

### Adding New Examples

1. Create `examples/my-use-case.yaml`
2. Add documentation to [examples/README.md](examples/README.md)
3. Add example code to [config-examples.md](config-examples.md)
4. Update this index

### Reporting Issues

If you find bugs or have suggestions:
- Check [Troubleshooting](#troubleshooting) first
- Review existing examples for solutions
- Consult [Config System Guide](config-system-guide.md)

---

## 📝 Document History

- **v1.0** (2025-01-29): Initial release
  - Config System Guide (complete API reference)
  - Config Examples (25+ practical examples)
  - 8 production-ready YAML templates
  - Complete troubleshooting guide

---

## 🎓 Summary

This handbook provides:

✅ **Complete API Reference** - Every type, method, and parameter documented
✅ **25+ Real-World Examples** - From basic to advanced use cases
✅ **8 Production Templates** - Copy-paste ready YAML configs
✅ **Progressive Disclosure** - Simple for beginners, powerful for experts
✅ **Troubleshooting Guide** - Solutions to common issues
✅ **Best Practices** - Dos and don'ts from SOTA research

**Get Started**:
1. Pick a [preset](#quick-start) or [YAML template](examples/)
2. Read [Config Examples](config-examples.md) for your use case
3. Consult [Config System Guide](config-system-guide.md) for details

**Questions?** See [Troubleshooting](#troubleshooting) or review [Config Examples](config-examples.md).
