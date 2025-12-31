# CLAUDE.md - Semantica v2 Codegraph

**CRITICAL: Always respond in Korean (한국어). Code/comments in English, explanations in Korean.**

---

## Onboarding & Code Discovery

### CRITICAL: Use Serena MCP for Symbol Search

**Serena MCP is connected and ready** - Always prefer Serena tools over manual grep:

```bash
# ❌ AVOID manual search (slow, incomplete)
rg "class ChunkStore"
rg "fn main"

# ✅ USE Serena MCP tools (fast, precise, LSP-powered)
# Serena provides:
# - find_symbol: Global/local symbol search with type filtering
# - find_referencing_symbols: Find all references to a symbol
# - get_symbols_overview: Get file structure overview
# - find_referencing_code_snippets: Find usage examples
```

**Serena MCP Status**:
- ✅ **Connected**: `claude mcp list` shows `serena: ✓ Connected`
- ✅ **Language Servers**: Python LSP active
- ✅ **Project Config**: `.serena/project.yml` configured

**When to use Serena**:
1. **Symbol search**: Finding classes, functions, variables
2. **Reference tracking**: Who calls this function?
3. **Code structure**: What's in this file/module?
4. **Refactoring prep**: Before renaming, find all usages

**When to use grep/rg**:
1. **Text patterns**: Regex search in comments/docs
2. **Config files**: YAML/TOML content search
3. **Error messages**: String literal search

**Example Workflow**:
```bash
# 1. Find symbol with Serena (LSP-aware, accurate)
claude "Serena로 ChunkStore 클래스 찾아줘"

# 2. Get all references with Serena
claude "ChunkStore의 모든 참조 위치 찾아줘"

# 3. Only then use rg for text patterns if needed
rg "# TODO.*chunk" packages/
```

### First-Time Repository Exploration

When encountering unfamiliar code or outdated documentation:

1. **Documentation is Outdated**: Assume docs are stale until proven otherwise
2. **Code is SSOT**: Source code is the Single Source of Truth
3. **Verify Before Acting**: Always check actual implementation
4. **Use Serena First**: Symbol search via MCP > manual grep

**Discovery Process** (Serena-first approach):
```bash
# 1. Find entry points (Serena MCP preferred)
claude "Serena로 main 함수들 찾아줘"
# Fallback: rg "fn main" packages/codegraph-ir/src/

# 2. Find key classes/structs (Serena MCP)
claude "Orchestrator 관련 클래스 모두 찾아줘"
# Fallback: rg "class.*Orchestrator" packages/

# 3. Trace dependencies (manual - not symbol-based)
rg "use.*::" packages/codegraph-ir/src/lib.rs
rg "from.*import" packages/codegraph-shared/

# 4. Find recent changes (git)
git log --oneline --since="1 month ago" -- packages/codegraph-ir/src/pipeline/

# 5. Check config structures (Serena for symbols, rg for grep)
claude "Config로 끝나는 struct 모두 찾아줘"
# Fallback: rg "pub struct.*Config" packages/codegraph-ir/src/

# 6. Verify function signatures (Serena MCP)
claude "analyze 함수들 시그니처 보여줘"
# Fallback: rg "pub fn.*analyze" packages/codegraph-ir/src/features/
```

### SSOT Verification Checklist

Before relying on documentation:

- [ ] Check `Cargo.toml` / `pyproject.toml` for actual dependencies
- [ ] Read `src/lib.rs` or `__init__.py` for public API
- [ ] Verify struct/class definitions in source files
- [ ] Check tests for actual usage patterns (`tests/**/*.rs`, `tests/**/*.py`)
- [ ] Review recent commits (`git log -p --since="1 week ago"`)
- [ ] Look for deprecation warnings in code comments

**Example: Verifying Config System**:
```bash
# Doc says "TaintConfig has 8 fields" - verify:
rg "pub struct TaintConfig" -A 20 packages/codegraph-ir/src/

# Doc says "use PipelineConfig::preset()" - verify:
rg "impl PipelineConfig" -A 50 packages/codegraph-ir/src/config/

# Find actual tests to see real usage:
rg "PipelineConfig::preset" packages/codegraph-ir/tests/
```

### Understanding Codebase Architecture

**Key Discovery Commands** (Serena-first):
```bash
# Find all public APIs (Serena MCP preferred for symbols)
claude "Serena로 public API 심볼 리스트 보여줘"
# Fallback: rg "^pub (fn|struct|enum|trait)" packages/codegraph-ir/src/ | head -50

# Find all test files (fd for file search - not symbol-based)
fd -e rs -e py test packages/

# Find configuration files (fd for file patterns)
fd -e toml -e yaml -e json . | grep -v target | grep -v node_modules

# Find documentation (fd for file search)
fd README.md
fd ".*\.md$" docs/

# Check for recent architectural changes (git)
git log --all --grep="ADR\|RFC" --oneline
```

### When Documentation Conflicts with Code

**Resolution Priority** (highest to lowest):
1. **Source code** (`packages/*/src/`)
2. **Tests** (`packages/*/tests/`)
3. **Type definitions** (`*.rs` structs, Python type hints)
4. **Recent commits** (`git log -p`)
5. **RFCs/ADRs** (`docs/RFC-*.md`, `docs/adr/`)
6. **README/Handbook** (`docs/handbook/`)
7. **Comments** (inline code comments)

**Action**: If doc conflicts with code, trust code and update doc.

---

## Project Overview

Semantica v2 is a SOTA-level code analysis and autonomous coding agent system:
- **Semantic Code Search**: Embedding-based similar code search
- **Lexical Search**: Full-text search (Tantivy)
- **Graph Search**: Dependency graph analysis
- **Hybrid Search**: RRF Fusion combining multiple search methods
- **Autonomous Coding Agent**: Bug fixing, refactoring, test generation

---

## Architecture (ADR-072)

**Rust = Analysis Engine, Python = Consumer**

```
Python Layer (API/MCP/CLI)
    ↓ import codegraph_ir
Rust Engine (IR, CFG, DFG, Taint, PTA)
```

**Key Principles**:
- ✅ Rust: All analysis logic (IR, CFG, DFG, Taint, PTA, Clone Detection)
- ✅ Python: Application layer (API, MCP, orchestration)
- ✅ Single direction: Python → Rust (PyO3 bindings)
- ❌ No Python in Rust (except Language Plugin interface)

See: [docs/CLEAN_ARCHITECTURE_SUMMARY.md](docs/CLEAN_ARCHITECTURE_SUMMARY.md)

---

## Configuration System (RFC-001)

**3-tier hierarchy: Preset → Stage Override → YAML**

```rust
// Level 1: Preset (90% use cases)
let config = PipelineConfig::preset(Preset::Fast).build()?;

// Level 2: Stage Override (9% use cases)
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50))
    .build()?;

// Level 3: YAML (1% use cases)
let config = PipelineConfig::from_yaml("config.yaml")?;
```

**59 settings 100% externalized**:
- L14 Taint (8), L6 PTA (7), L10 Clone (12), L16 PageRank (5)
- L2 Chunking (5), Lexical (6), Cache (12), Parallel (4)

**Presets**:
- `Fast`: CI/CD (1x baseline, 5s target)
- `Balanced`: Development (2.5x baseline, 30s target)
- `Thorough`: Full analysis (10x baseline, no time limit)

See: [docs/RFC-CONFIG-SYSTEM.md](docs/RFC-CONFIG-SYSTEM.md)

---

## 문서 관리 원칙

### 임시 문서 관리

**원칙**: 모든 임시/작업 중 문서는 `docs/_temp/`에 보관

**임시 문서 정의**:
- 작업 중인 초안 (draft)
- 실험적 분석 결과
- 일시적 메모/노트
- 검증 전 보고서
- 버전 v1, v2 등 중간 버전

**디렉토리 구조**:
```
docs/
├── _temp/              ← 임시 문서 (진행 중)
│   ├── drafts/        작업 중 초안
│   ├── experiments/   실험 결과
│   └── notes/         일시적 메모
│
├── archive/            ← 완료된 구 문서
│   └── obsolete_reports/
│
└── [최종 문서들]       ← 검증된 최신 문서만
```

**파일명 규칙**:
```bash
# 임시 파일 (docs/_temp/)
DRAFT_FEATURE_NAME.md
EXPERIMENT_ANALYSIS_20251229.md
NOTES_MEETING.md
RFC_XXX_V1.md
ANALYSIS_REPORT_V2.md

# 최종 파일 (docs/)
FEATURE_NAME.md
RFC-XXX-FINAL.md
ANALYSIS_REPORT.md  # 버전 번호 없음
```

**작업 흐름**:
```bash
# 1. 임시 파일 생성
docs/_temp/drafts/DRAFT_SOTA_GAP_ANALYSIS.md

# 2. 검증 완료 후 최종 위치로 이동
mv docs/_temp/drafts/DRAFT_SOTA_GAP_ANALYSIS.md \
   docs/SOTA_GAP_ANALYSIS_FINAL.md

# 3. 임시 파일 정리 (주간)
rm -rf docs/_temp/drafts/*
```

**금지 사항**:
- ❌ `docs/` 루트에 `*_V1.md`, `*_V2.md` 생성
- ❌ `DRAFT_*`, `TEMP_*`, `WIP_*` 파일을 루트에 방치
- ❌ 검증 안 된 문서를 최종 위치에 배치

**정리 주기**:
- **일일**: 사용 완료한 임시 파일 삭제
- **주간**: `_temp/` 전체 검토 및 정리
- **월간**: 최종 문서 검증 및 archive 이동

---

## Engineering Standards (Stanford/BigTech L11)

### 1. No Hardcoding
- ❌ Magic numbers, hardcoded paths, embedded constants
- ✅ All config values externalized (RFC-001)
- ✅ Compile-time (Rust) + Runtime (Python) validation

### 2. No Stub, No Fake
- ❌ `raise NotImplementedError`, `pass`, TODO-only functions
- ❌ Dummy data, fake implementations
- ✅ Fully implemented + tested code only
- ✅ Exception: Explicitly tagged "Prototype" or "Experimental"

### 3. SOLID Principles
- **Rust**: Trait-based abstraction + Dependency Injection
- **Python**: Protocol/ABC + DI Container

### 4. Type Safety
```rust
// Rust: Type system guarantees
pub struct ValidatedConfig(PipelineConfig);  // newtype pattern

// Python: Strict type hints + runtime validation
from pydantic import BaseModel, validator
```

### 5. Error Handling
```rust
// Rust: Result<T, E> - no panic in library code
pub fn analyze(path: &Path) -> Result<IRNode, AnalysisError>

// Python: Typed exceptions
class AnalysisError(Exception):
    category: ErrorCategory
    code: ErrorCode
```

**Never**:
- `unwrap()` in Rust library code (tests OK)
- Bare `except:` in Python
- Silent `return None` without error message

### 6. Performance Awareness
```rust
/// Time: O(n * log n) where n = number of symbols
/// Space: O(n) for hash table storage
pub fn build_index(symbols: &[Symbol]) -> Index
```
- ✅ Document Big-O complexity (non-trivial algorithms)
- ✅ Provide performance profile (`performance_profile()`)
- ❌ No premature optimization

### 7. Testing
- **Unit tests**: All public functions/methods
- **Integration tests**: Major workflows
- **Property-based tests**: Complex logic (hypothesis)
- **Benchmark tests**: Prevent performance regression
- **Target**: 80%+ coverage

### 8. Documentation
```rust
/// Brief description.
///
/// # Algorithm
/// 1. Step-by-step explanation
///
/// # Performance
/// - Time: O(E + V)
/// - Space: O(V)
///
/// # Example
/// ```rust
/// let result = analyze(&ir, &config)?;
/// ```
pub fn analyze(ir: &IR, config: &Config) -> Result<Output>
```

**Required**:
- Algorithm explanation (non-trivial logic)
- Performance characteristics (Big-O)
- Usage examples (doctest)
- Error cases

### 9. SSOT Verification Habit

**Always verify documentation against code**:

```bash
# Before implementing based on docs, verify:
# 1. Check struct/class actually exists
rg "pub struct ConfigName" packages/

# 2. Verify field names and types
rg "pub struct ConfigName" -A 20 packages/

# 3. Check actual function signature
rg "pub fn function_name" -A 5 packages/

# 4. Find real usage in tests
rg "function_name" tests/

# 5. Check for recent changes
git log -p --since="2 weeks ago" -- path/to/file.rs
```

**When to distrust docs**:
- Doc older than 1 month without verification
- No corresponding test cases
- Conflicting information in code comments
- Recent git commits modify mentioned APIs

**Action**: If uncertain, inspect source code first, docs second.

### 10. Code Review Checklist
Before submitting code:

- [ ] No hardcoded values
- [ ] No stub/fake implementations
- [ ] SOLID principles followed
- [ ] Type-safe (compile-time + runtime)
- [ ] Explicit error handling
- [ ] Performance complexity documented
- [ ] 80%+ test coverage
- [ ] Complete API documentation
- [ ] Backward compatibility considered
- [ ] Security vulnerabilities reviewed
- [ ] **SSOT verified**: Implementation matches actual code, not outdated docs

---

## Repository Structure

```
codegraph/
├── packages/
│   ├── codegraph-ir/        # Rust analysis engine
│   ├── codegraph-storage/   # Rust storage layer
│   ├── codegraph-shared/    # Python shared infra
│   ├── codegraph-search/    # Python search
│   └── codegraph-analysis/  # Python analysis
├── server/
│   ├── api_server/          # FastAPI REST API
│   └── mcp_server/          # MCP server
├── tests/                   # Test suites
├── docs/                    # Documentation
│   ├── RFC-*.md            # Design proposals
│   └── handbook/           # System handbook
└── tools/                   # Dev tools
```

---

## CRITICAL: AI Auto-Test System (Claude MUST Follow)

### When to Run Tests

**ALWAYS run tests after**:
- ✅ Code changes (`.rs` or `.py` files)
- ✅ Bug fixes, refactoring
- ✅ User request

### 🎯 Test Command Selection Guide (Justfile-based)

**Recommended commands by situation**:

| Situation | Command | Duration |
|-----------|---------|----------|
| 🔥 TDD / Quick check | `just rust-test-unit` | ~10s |
| ✅ Daily development (default) | `just rust-test` | ~30s |
| 🔗 Integration tests | `just rust-test-integration` | ~1min |
| 🌐 E2E tests | `just rust-test-e2e` | ~2min |
| 📊 Performance benchmarks | `just rust-test-perf` | ~5min+ |
| 💪 Stress tests | `just rust-test-stress` | ~10min+ |
| 🐢 All slow tests | `just rust-test-slow` | ~15min+ |
| 🚀 Full CI suite | `just rust-test-all` | ~20min+ |

**⚠️ Important Rules**:
1. **Daily development**: Use `just rust-test` or `just rust-test-unit`
2. **Before PR**: Also run `just rust-test-integration`
3. **Performance changes**: Run `just rust-test-perf`
4. **NEVER**: Run `rust-test-all` every time (waste of time)

**Test Structure**:
```
tests/
├── unit/           # Fast unit tests → rust-test-unit
├── integration/    # Integration tests → rust-test-integration
├── e2e/            # E2E tests → rust-test-e2e
├── performance/    # Benchmarks (#[ignore]) → rust-test-perf
└── stress/         # Stress tests (#[ignore]) → rust-test-stress
```

### Quick Commands

```bash
# 🔥 Fastest check (for TDD)
just rust-test-unit

# ✅ Daily development (default, recommended)
just rust-test

# 📦 Specific test only
just rust-test-one test_name

# 🐍 Python tests
pytest tests/ -v
```

### Troubleshooting

```bash
# If slow: kill zombie processes
pkill -9 -f "cargo test"

# Specific test with debug output
cargo nextest run test_name --nocapture
```

---

## Key Commands

**Install**:
```bash
uv pip install -e ".[dev]"
pre-commit install
```

**Test**:
```bash
# Rust (auto-detected, 16코어)
cd packages/codegraph-ir && just test-parallel

# Python
pytest tests/ -v
```

**Build & Lint**:
```bash
# Rust - 빠른 체크/빌드
just check         # 가장 빠름 (컴파일만)
just build         # 증분 빌드
just build-release # 릴리즈 (최적화)

# Lint
cargo clippy  # Rust
just format   # Python
just lint     # Python
```

---

## Quick Reference

**코드 탐색** (Serena MCP 우선):
- Serena로 심볼 검색 → 실제 코드 확인 → 테스트 패턴 파악

**새 기능 추가**:
1. Trait 정의 (`packages/codegraph-ir/src/features/`)
2. 구현 + 테스트
3. Config 추가 (RFC-001)
4. Pipeline 통합

**성능 최적화**:
- Benchmark → Profile → 알고리즘 개선 → 병렬화 → 캐시

---

## Key Files

- `packages/codegraph-ir/src/lib.rs`: Rust main entry point
- `packages/codegraph-ir/src/pipeline/`: Pipeline orchestration
- `packages/codegraph-ir/src/features/`: Analysis features (taint, pta, clone)
- `packages/codegraph-shared/`: Python shared infrastructure
- `docs/RFC-CONFIG-SYSTEM.md`: Configuration system spec
- `docs/CLEAN_ARCHITECTURE_SUMMARY.md`: Rust-Python boundary design

---

## Documentation

- **System Handbook**: `docs/handbook/system-handbook/`
- **RFCs**: `docs/RFC-*.md` (design proposals)
- **ADRs**: `docs/adr/` (architecture decisions)

---

## MCP Integration Status

### Serena MCP (✅ Active)
**Purpose**: LSP-powered code navigation and symbol search

**Connection**: `claude mcp list` → `serena: ✓ Connected`

**Available Tools**:
- `find_symbol`: Search for symbols (classes, functions, variables)
- `find_referencing_symbols`: Find who calls/uses a symbol
- `get_symbols_overview`: Get file/module structure
- `find_referencing_code_snippets`: Find usage examples
- Full LSP capabilities (go-to-definition, find references)

**Usage**:
```bash
# Symbol search
claude "Serena로 ChunkStore 클래스 찾아줘"

# Find references
claude "analyze_cost 함수의 모든 호출처 찾아줘"

# File structure
claude "main.py의 구조 보여줘"
```

**Project Config**: `.serena/project.yml` - Codegraph context loaded automatically

### Codegraph MCP (⚠️ Pending)
**Purpose**: Semantic search and analysis tools

**Status**: ❌ Connection failed (Python→Rust migration in progress)

**Planned Tools** (when fixed):
- `search`: Hybrid chunk + symbol search
- `get_context`: Symbol context with callers/callees
- `graph_slice`: Semantic slicing for bug analysis
- Taint analysis, PTA integration

**Fix Required**: Import compatibility layer for migrated Rust modules

---

**Remember**:
- ✅ **Use Serena MCP first** for symbol search/navigation
- ⚠️ Fall back to `rg`/`fd` only for text patterns
- 🎯 SOTA Engineering = No Shortcuts + No Technical Debt + Sustainable Design
