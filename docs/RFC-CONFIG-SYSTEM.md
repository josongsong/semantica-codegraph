# R001: SOTA Configuration System - Maximal Extensibility

**Status**: Draft
**Author**: Codegraph Team
**Created**: 2025-12-29
**Updated**: 2025-12-29 (P0 Revision)
**RFC Number**: R001
**Goal**: 모든 하드코딩된 상수를 외부 설정 가능하게, 업계 최고 수준 DX

---

## Executive Summary

현재 **59개의 하드코딩된 설정값**이 코드베이스에 분산되어 있어 외부에서 제어 불가능.
**3단계 계층 구조** (Preset → Stage Config → Advanced Tuning)로 **초보자부터 전문가까지** 모두 만족시키는 설정 시스템 제안.

**핵심 개선사항 (v2)**:
- ✅ 설정 병합 우선순위(Merge Precedence) 명확화
- ✅ StageControl 동작 계약 정의 + strict_mode 추가
- ✅ YAML 스키마 v1 명세화 + 버전 관리
- ✅ JSON Schema 지원으로 IDE 자동완성
- ✅ Cross-stage validation (상호 검증)
- ✅ Field-level provenance tracking (v1: path only)
- ✅ Performance bands (qualitative cost classes)

```rust
// 90% Use Case: 한 줄
let config = Config::preset(Preset::Fast);

// 9% Use Case: 특정 단계만 조정
let config = Config::preset(Preset::Balanced)
    .taint(|c| c.max_depth(50))
    .build()?;

// 1% Use Case: 완전한 제어
let config = Config::from_yaml("security-audit.yaml")?;
```

---

## Part 1: 현황 분석 - 하드코딩된 설정들

### 발견된 설정 카테고리

| Category | 설정 수 | 현재 상태 | 영향도 |
|----------|---------|----------|--------|
| **Taint Analysis** | 8개 | ❌ 하드코딩 | 🔴 Critical |
| **Points-to Analysis** | 6개 | ❌ 하드코딩 | 🔴 Critical |
| **Clone Detection** | 12개 (Type-1~4) | ❌ 하드코딩 | 🟡 High |
| **PageRank/RepoMap** | 6개 | ✅ Config 있음 | 🟢 OK |
| **Chunking** | 5개 | ❌ 하드코딩 | 🟡 Medium |
| **Cache System** | 12개 | ✅ Config 있음 | 🟢 OK |
| **Parallelism** | 4개 | ⚠️ 부분적 | 🟡 Medium |
| **Lexical/Search** | 6개 | ❌ 하드코딩 | 🟡 Medium |

**Total: 59개 설정값** (PageRank/Cache 제외 시 41개 미설정)

### 세부 설정 목록

#### 1. Taint Analysis (L14)
```rust
// 현재: packages/codegraph-ir/src/pipeline/processor/stages/advanced.rs:151
SOTAConfig {
    max_depth: 30,              // ❌ 하드코딩
    max_paths: 500,             // ❌ 하드코딩
    use_points_to: true,        // ❌ 하드코딩
    field_sensitive: true,      // ❌ 하드코딩
    use_ssa: true,              // ❌ 하드코딩
    detect_sanitizers: true,    // ❌ 하드코딩
    enable_interprocedural: true, // ❌ 하드코딩
    worklist_max_iterations: 1000, // ❌ 하드코딩
}
```

**영향**:
- `max_depth=30`: 깊은 call chain 추적 불가
- `max_paths=500`: 복잡한 흐름에서 경로 누락
- 보안 감사 시 설정 변경 불가

#### 2. Points-to Analysis (L6)
```rust
// 현재: packages/codegraph-ir/src/features/points_to/application/analyzer.rs:86
AnalysisConfig {
    mode: Auto,                 // ❌ 하드코딩
    field_sensitive: true,      // ❌ 하드코딩
    max_iterations: 0,          // ❌ 하드코딩 (unlimited)
    auto_threshold: 10000,      // ❌ 하드코딩
    enable_scc: true,           // ❌ 하드코딩
    enable_wave: true,          // ❌ 하드코딩
    enable_parallel: true,      // ❌ 하드코딩
}
```

**영향**:
- `auto_threshold=10000`: 큰 프로젝트에서 알고리즘 강제 전환
- `max_iterations=0`: 수렴 안될 때 무한 루프

#### 3. Clone Detection (L10)
```rust
// Type-1: packages/codegraph-ir/src/features/clone_detection/infrastructure/type1_detector.rs:60
Type1Detector {
    min_tokens: 50,    // ❌ 하드코딩
    min_loc: 3,        // ❌ 하드코딩
}

// Type-2
Type2Detector {
    min_tokens: 50,         // ❌ 하드코딩
    min_loc: 3,             // ❌ 하드코딩
    min_similarity: 0.8,    // ❌ 하드코딩
}

// Type-3
Type3Detector {
    min_tokens: 30,         // ❌ 하드코딩
    min_loc: 2,             // ❌ 하드코딩
    gap_threshold: 0.3,     // ❌ 하드코딩
}

// Type-4
Type4Detector {
    min_tokens: 20,         // ❌ 하드코딩
    min_loc: 1,             // ❌ 하드코딩
    semantic_threshold: 0.7, // ❌ 하드코딩
}
```

**영향**:
- `min_tokens=50`: 작은 중복 코드 놓침
- 프로젝트 특성에 맞는 threshold 조정 불가

#### 4. PageRank/RepoMap (L16) ✅
```rust
// ✅ 이미 설정 가능: packages/codegraph-ir/src/features/repomap/infrastructure/pagerank.rs:87
PageRankSettings {
    damping: 0.85,              // ✅ 설정 가능
    max_iterations: 5,          // ✅ 설정 가능
    tolerance: 1e-3,            // ✅ 설정 가능
    enable_personalized: false, // ✅ 설정 가능
    enable_hits: false,         // ✅ 설정 가능
}
```

#### 5. Chunking (L2)
```rust
// 추정: 현재 Config 구조체 없음
ChunkingConfig {
    max_chunk_size: 1000,       // ❌ 추정값
    overlap_lines: 3,           // ❌ 추정값
    min_chunk_size: 100,        // ❌ 추정값
    enable_semantic: false,     // ❌ 추정값
    respect_scope: true,        // ❌ 추정값
}
```

#### 6. Cache System ✅
```rust
// ✅ 이미 설정 가능: packages/codegraph-ir/src/features/cache/config.rs
SessionCacheConfig {
    max_entries: 10_000,
    bloom_capacity: 10_000,
    bloom_fp_rate: 0.01,
}

AdaptiveCacheConfig {
    max_entries: 1_000,
    max_bytes: 512 * 1024 * 1024,
    ttl: 3600,
}

DiskCacheConfig {
    cache_dir: "~/.cache/codegraph",
    enable_compression: true,
    enable_rocksdb: false,
}
```

#### 7. Parallelism
```rust
ParallelConfig {
    num_workers: auto,          // ⚠️ E2EPipelineConfig에 있음
    batch_size: 100,            // ⚠️ E2EPipelineConfig에 있음
    enable_rayon: true,         // ❌ 없음
    stack_size_mb: 8,           // ❌ 없음
}
```

#### 8. Lexical/Search
```rust
LexicalConfig {
    enable_fuzzy: true,         // ❌ 하드코딩 추정
    fuzzy_distance: 2,          // ❌ 하드코딩 추정
    max_results: 100,           // ❌ 하드코딩 추정
    enable_ngram: true,         // ❌ 하드코딩 추정
    ngram_size: 3,              // ❌ 하드코딩 추정
    enable_stemming: false,     // ❌ 하드코딩 추정
}
```

---

## Part 2: 설계 - 3단계 계층 구조

```
┌────────────────────────────────────────────────────────────┐
│                Level 1: Preset (90% users)                 │
│  Fast / Balanced / Thorough / Custom                       │
│  → 모든 Stage의 기본값 제공                                  │
└────────────────┬───────────────────────────────────────────┘
                 ▼
┌────────────────────────────────────────────────────────────┐
│          Level 2: Stage Override (9% users)                │
│  .taint(|c| c.max_depth(50))                               │
│  → 특정 Stage만 부분 조정                                    │
└────────────────┬───────────────────────────────────────────┘
                 ▼
┌────────────────────────────────────────────────────────────┐
│       Level 3: Advanced Tuning (1% users)                  │
│  YAML/TOML로 완전한 제어                                     │
│  → 전문가용 세밀한 조정                                       │
└────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Progressive Disclosure**: 간단한 것부터 복잡한 것까지 단계적 노출
2. **Type Safety**: 컴파일 타임 검증 (Rust)
3. **Runtime Validation**: 범위 체크 + 명확한 에러 + Cross-stage 정합성 검증
4. **Composable**: Builder 패턴으로 조합 가능
5. **Versionable**: YAML 스키마 v1 + 마이그레이션 경로
6. **Discoverable**: IDE 자동완성(JSON Schema) + 문서
7. **Performance-aware**: 성능 프로파일 제공 (qualitative bands, 보장값 아님)
8. **Traceable**: Field-level provenance (어떤 설정이 어디서 왔는지 추적)

---

## Part 2.5: Configuration Merge Contract

### 2.5.1. Merge Precedence (우선순위)

설정값은 다음 순서로 병합되며, **나중 단계가 이전 단계를 덮어씀**:

```
1. Preset Defaults        (가장 약함)
   ↓
2. YAML Overrides         (파일 기반)
   ↓
3. Environment Variables  (배포 환경별)
   ↓
4. Builder Overrides      (런타임 코드)
   ↓
5. StageControl Gate      (최종 on/off, 가장 강함)
```

**StageControl의 역할**:
- `StageControl`은 **최종 게이트**로, 해당 stage가 `disabled`면 설정 동작은 `strict_mode`에 따라 결정
- `strict_mode=true`: Disabled stage에 override가 있으면 `build()` 시점에 `ConfigError::DisabledStageOverride` 발생
- `strict_mode=false` (default): Disabled stage의 override는 **경고 후 무시**

**예시 (strict_mode=true)**:
```rust
let config = PipelineConfig::preset(Preset::Balanced)  // (1) Preset
    .from_yaml("team.yaml")?                            // (2) YAML
    .from_env()?                                        // (3) Env
    .taint(|c| c.max_depth(100))                        // (4) Builder
    .stages(|s| s.disable(StageId::Taint))              // (5) Gate: Taint 비활성화
    .strict_mode(true)                                  // (6) Strict enforcement
    .build()?;                                          // ERROR: DisabledStageOverride
```

**예시 (strict_mode=false, default)**:
```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c.max_depth(100))
    .stages(|s| s.disable(StageId::Taint))
    .build()?;  // WARNING: Taint override ignored (stage disabled)
```

### 2.5.2. StageControl 동작 계약

```rust
pub struct StageControl {
    pub taint: bool,
    pub pta: bool,
    pub clone: bool,
    // ... (all L1-L37 stages)
}

impl StageControl {
    /// Default: 기본 stages만 활성화 (L1-L3)
    pub fn default() -> Self {
        Self {
            parsing: true,       // L1
            chunking: true,      // L2
            lexical: true,       // L3
            cross_file: false,   // L4 (expensive)
            clone: false,        // L5
            pta: false,          // L6 (very expensive)
            taint: false,        // L14 (expensive)
            repomap: false,      // L16 (expensive)
            // ...
        }
    }

    /// All stages enabled
    pub fn all() -> Self { /* ... */ }

    /// Security-focused stages
    pub fn security() -> Self {
        Self {
            taint: true,
            pta: true,
            // ...
        }
    }

    /// Builder methods
    pub fn enable(mut self, stage: StageId) -> Self {
        self.set(stage, true);
        self
    }

    pub fn disable(mut self, stage: StageId) -> Self {
        self.set(stage, false);
        self
    }
}

pub struct PipelineConfig {
    // ... other fields

    /// Strict mode: error on disabled stage overrides (default: false)
    /// - true: build() fails with ConfigError::DisabledStageOverride
    /// - false: build() warns and ignores disabled stage overrides
    strict_mode: bool,
}
```

**규칙**:
1. `stage = false`이면 해당 stage는 **명시적으로 비활성화**
2. Disabled stage는:
   - `ValidatedConfig::taint()` → `None` 반환
   - YAML/Builder에서 override 있고 `strict_mode=true` → `ConfigError::DisabledStageOverride`
   - YAML/Builder에서 override 있고 `strict_mode=false` → 경고 후 무시
3. StageControl은 **성능 프로파일링**과 **분석 범위 관리**의 핵심

### 2.5.3. Unknown Field 정책 (Strict Mode)

**DX 최고 수준 = 조용히 무시 ❌, 즉시 실패 + 친절한 힌트 ✅**

```rust
// YAML 파일에 오타가 있을 경우
// team.yaml
version: 1
overrides:
  taint:
    max_depht: 50  # ❌ 오타: max_depth

// 에러 메시지
ConfigError::UnknownField {
    field: "max_depht",
    stage: "taint",
    suggestion: "Did you mean 'max_depth'?",
    valid_fields: ["max_depth", "max_paths", "use_points_to", ...],
}
```

**구현**:
- `serde(deny_unknown_fields)` 활성화
- Levenshtein distance로 "Did you mean" 제안

### 2.5.4. Config Versioning + Migration

**YAML Schema v1**:
```yaml
version: 1  # ✅ 필수 필드
preset: balanced

# Stage on/off switches
stages:
  taint: true
  pta: true
  clone: false

# Fine-grained overrides
overrides:
  taint:
    max_depth: 50
    max_paths: 1000
  pta:
    mode: precise
```

**버전 관리 계약**:
- `version` 필드 누락 → `ConfigError::MissingVersion`
- 미래 버전(v2+) → `ConfigError::UnsupportedVersion { found: 2, supported: [1] }`
- v1→v2 마이그레이션 함수: `migrate_v1_to_v2()`

**호환성 보장**:
- v1 스키마는 **최소 2년간 지원**
- Breaking change 시 마이그레이션 경로 제공
- Deprecated 필드는 경고 + 자동 변환

---

## Part 3: API Design

### 3.1. Core Types

```rust
// ============================================================================
// Preset Enum (3개 + Custom)
// ============================================================================
#[derive(Debug, Clone, Copy)]
pub enum Preset {
    /// CI/CD: 최소한의 빠른 분석
    Fast,

    /// Development: 균형잡힌 분석
    Balanced,

    /// Security Audit: 완전한 분석
    Thorough,

    /// Custom: 사용자 정의 (YAML/TOML에서만 사용)
    Custom,
}

// ============================================================================
// Stage Configs (개별 설정)
// ============================================================================

/// L14: Taint Analysis Configuration
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct TaintConfig {
    /// Maximum call chain depth (1..=1000)
    #[validate(range(min = 1, max = 1000))]
    pub max_depth: usize,

    /// Maximum taint paths to track (1..=100000)
    #[validate(range(min = 1, max = 100000))]
    pub max_paths: usize,

    /// Use points-to analysis for precision
    pub use_points_to: bool,

    /// Enable field-sensitive tracking
    pub field_sensitive: bool,

    /// Enable SSA-based analysis
    pub use_ssa: bool,

    /// Detect sanitizers (reduces false positives)
    pub detect_sanitizers: bool,

    /// Enable interprocedural analysis
    pub enable_interprocedural: bool,

    /// Worklist solver max iterations (1..=10000)
    #[validate(range(min = 1, max = 10000))]
    pub worklist_max_iterations: usize,
}

impl TaintConfig {
    // Builder methods
    pub fn max_depth(mut self, v: usize) -> Self {
        self.max_depth = v;
        self
    }

    pub fn max_paths(mut self, v: usize) -> Self {
        self.max_paths = v;
        self
    }

    // ... other builders
}

/// L6: Points-to Analysis Configuration
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct PTAConfig {
    /// Algorithm selection
    pub mode: PTAMode,  // Fast, Precise, Auto

    /// Enable field-sensitive analysis
    pub field_sensitive: bool,

    /// Max iterations for Andersen (None=unlimited, Some(n)=limit)
    /// ✅ FIXED: Option 사용으로 "0=unlimited" 함정 제거
    #[validate(custom = "validate_max_iterations")]
    pub max_iterations: Option<usize>,

    /// Auto mode threshold: use Precise below this
    #[validate(range(min = 100, max = 1000000))]
    pub auto_threshold: usize,

    /// Enable SCC optimization
    pub enable_scc: bool,

    /// Enable wave propagation
    pub enable_wave: bool,

    /// Enable parallel processing
    pub enable_parallel: bool,
}

fn validate_max_iterations(v: &Option<usize>) -> Result<(), ValidationError> {
    if let Some(n) = v {
        if *n == 0 || *n > 10000 {
            return Err(ValidationError::new("max_iterations must be 1..=10000 or None for unlimited"));
        }
    }
    Ok(())
}

/// L10: Clone Detection Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CloneConfig {
    /// Enabled clone types
    pub types_enabled: Vec<CloneType>,  // Type1, Type2, Type3, Type4

    /// Type-1: Exact clones (only min_tokens, min_loc)
    pub type1: Type1Config,

    /// Type-2: Renamed clones (+ rename similarity)
    pub type2: Type2Config,

    /// Type-3: Gapped clones (+ gap threshold)
    pub type3: Type3Config,

    /// Type-4: Semantic clones (+ semantic threshold)
    pub type4: Type4Config,
}

/// Type-1: Exact clones (character-for-character match)
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct Type1Config {
    #[validate(range(min = 5, max = 1000))]
    pub min_tokens: usize,

    #[validate(range(min = 1, max = 100))]
    pub min_loc: usize,
}

/// Type-2: Renamed clones (allow identifier renaming)
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct Type2Config {
    #[validate(range(min = 5, max = 1000))]
    pub min_tokens: usize,

    #[validate(range(min = 1, max = 100))]
    pub min_loc: usize,

    /// Token sequence similarity (0.0..=1.0)
    #[validate(range(min = 0.5, max = 1.0))]
    pub rename_similarity: f64,
}

/// Type-3: Gapped clones (allow statement insertion/deletion)
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct Type3Config {
    #[validate(range(min = 5, max = 1000))]
    pub min_tokens: usize,

    #[validate(range(min = 1, max = 100))]
    pub min_loc: usize,

    /// Maximum gap ratio (0.0..=0.5)
    #[validate(range(min = 0.0, max = 0.5))]
    pub gap_threshold: f64,

    /// Overall similarity after gaps (0.0..=1.0)
    #[validate(range(min = 0.5, max = 1.0))]
    pub similarity: f64,
}

/// Type-4: Semantic clones (functionally similar, syntactically different)
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct Type4Config {
    #[validate(range(min = 5, max = 1000))]
    pub min_tokens: usize,

    #[validate(range(min = 1, max = 100))]
    pub min_loc: usize,

    /// PDG (Program Dependence Graph) similarity (0.0..=1.0)
    #[validate(range(min = 0.3, max = 1.0))]
    pub semantic_threshold: f64,
}

/// L16: PageRank Configuration (이미 존재)
pub use crate::features::repomap::infrastructure::PageRankSettings as PageRankConfig;

/// L2: Chunking Configuration
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct ChunkingConfig {
    /// Maximum chunk size in characters (100..=10000)
    #[validate(range(min = 100, max = 10000))]
    pub max_chunk_size: usize,

    /// Minimum chunk size (50..=5000)
    #[validate(range(min = 50, max = 5000))]
    pub min_chunk_size: usize,

    /// Overlap lines between chunks (0..=10)
    #[validate(range(max = 10))]
    pub overlap_lines: usize,

    /// Enable semantic-aware chunking
    pub enable_semantic: bool,

    /// Respect scope boundaries
    pub respect_scope: bool,
}

/// Lexical/Search Configuration
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct LexicalConfig {
    /// Enable fuzzy search
    pub enable_fuzzy: bool,

    /// Fuzzy edit distance (1..=5)
    #[validate(range(min = 1, max = 5))]
    pub fuzzy_distance: usize,

    /// Maximum search results (1..=10000)
    #[validate(range(min = 1, max = 10000))]
    pub max_results: usize,

    /// Enable n-gram indexing
    pub enable_ngram: bool,

    /// N-gram size (2..=5)
    #[validate(range(min = 2, max = 5))]
    pub ngram_size: usize,

    /// Enable stemming
    pub enable_stemming: bool,
}

/// Cache Configuration (이미 존재)
pub use crate::features::cache::config::{
    TieredCacheConfig as CacheConfig,
    SessionCacheConfig,
    AdaptiveCacheConfig,
    DiskCacheConfig,
};

/// Parallelism Configuration (확장)
#[derive(Debug, Clone, Serialize, Deserialize, Validate)]
pub struct ParallelConfig {
    /// Number of workers (0=auto, 1..=256)
    #[validate(range(max = 256))]
    pub num_workers: usize,

    /// Batch size for parallel processing (1..=10000)
    #[validate(range(min = 1, max = 10000))]
    pub batch_size: usize,

    /// Enable Rayon parallel iterator
    pub enable_rayon: bool,

    /// Thread stack size in MB (1..=64)
    #[validate(range(min = 1, max = 64))]
    pub stack_size_mb: usize,
}

// ============================================================================
// Main Configuration
// ============================================================================
pub struct PipelineConfig {
    /// Base preset
    preset: Preset,

    /// Stage control (on/off switches)
    stages: StageControl,

    /// Strict mode: error on disabled stage overrides (default: false)
    strict_mode: bool,

    /// Stage-specific overrides
    taint: Option<TaintConfig>,
    pta: Option<PTAConfig>,
    clone: Option<CloneConfig>,
    pagerank: Option<PageRankConfig>,
    chunking: Option<ChunkingConfig>,
    lexical: Option<LexicalConfig>,
    cache: Option<CacheConfig>,
    parallel: Option<ParallelConfig>,

    /// Provenance tracking (field-level)
    provenance: ConfigProvenance,
}

// ============================================================================
// Field-Level Provenance (출처 추적)
// ============================================================================
#[derive(Debug, Clone)]
pub struct ConfigProvenance {
    /// Base preset used
    preset: Preset,

    /// Field-level tracking: field path → source
    /// Example: "taint.max_depth" → ConfigSource::Env("CODEGRAPH__TAINT__MAX_DEPTH")
    field_sources: HashMap<String, ConfigSource>,
}

#[derive(Debug, Clone)]
pub enum ConfigSource {
    /// From preset defaults
    Preset(Preset),

    /// From YAML file (v1: path only, no line tracking)
    Yaml { path: String },

    /// From environment variable
    Env(String),

    /// From builder API
    Builder,
}

impl ConfigProvenance {
    pub fn from_preset(preset: Preset) -> Self {
        Self {
            preset,
            field_sources: HashMap::new(),
        }
    }

    /// Record field-level override
    pub fn track_field(&mut self, field_path: &str, source: ConfigSource) {
        self.field_sources.insert(field_path.to_string(), source);
    }

    /// Get human-readable summary
    pub fn summary(&self) -> String {
        let mut lines = vec![format!("Base preset: {:?}", self.preset)];

        if !self.field_sources.is_empty() {
            lines.push("\nOverridden fields:".to_string());
            for (field, source) in &self.field_sources {
                let source_str = match source {
                    ConfigSource::Preset(p) => format!("preset {:?}", p),
                    ConfigSource::Yaml { path } => format!("{}", path),
                    ConfigSource::Env(var) => format!("env ${}", var),
                    ConfigSource::Builder => "builder API".to_string(),
                };
                lines.push(format!("  {} ← {}", field, source_str));
            }
        }

        lines.join("\n")
    }
}

// ============================================================================
// Performance Profile (Qualitative Bands)
// ============================================================================

/// Qualitative cost class (not quantitative guarantees)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CostClass {
    /// Light analysis, suitable for tight feedback loops
    Low,
    /// Moderate analysis, suitable for CI/CD
    Medium,
    /// Deep analysis, suitable for nightly scans
    High,
    /// Exhaustive analysis, may be unbounded
    Extreme,
}

/// Expected latency band (qualitative, not guaranteed)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LatencyBand {
    /// Typically completes in <5 seconds
    SubFiveSeconds,
    /// Typically completes in <30 seconds
    SubThirtySeconds,
    /// Typically completes in <5 minutes
    SubFiveMinutes,
    /// May take longer, unbounded
    Unbounded,
}

/// Expected memory band (qualitative, not guaranteed)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MemoryBand {
    /// Typically uses <200MB
    Under200MB,
    /// Typically uses <1GB
    Under1GB,
    /// Typically uses <4GB
    Under4GB,
    /// May use more, unbounded
    Unbounded,
}

/// Performance profile (qualitative bands, NOT guarantees)
#[derive(Debug, Clone)]
pub struct PerformanceProfile {
    /// Cost class: Low | Medium | High | Extreme
    pub cost_class: CostClass,

    /// Expected latency: <5s | <30s | <5m | unbounded
    pub expected_latency: LatencyBand,

    /// Expected memory: <200MB | <1GB | <4GB | unbounded
    pub expected_memory: MemoryBand,

    /// Whether recommended for production use
    pub production_ready: bool,
}

impl PerformanceProfile {
    pub fn describe(&self) -> String {
        format!(
            "Cost: {:?}, Latency: {:?}, Memory: {:?}, Production: {}",
            self.cost_class,
            self.expected_latency,
            self.expected_memory,
            if self.production_ready { "Yes ✅" } else { "No ⚠️" }
        )
    }
}

// ============================================================================
// JSON Schema Support (IDE 자동완성)
// ============================================================================
impl PipelineConfig {
    /// Generate JSON Schema for IDE autocomplete
    ///
    /// Usage:
    ///   1. Generate schema: `PipelineConfig::json_schema()`
    ///   2. Save to: `.vscode/codegraph-config.schema.json`
    ///   3. In YAML file, add: `# yaml-language-server: $schema=.vscode/codegraph-config.schema.json`
    ///   4. VS Code will now provide autocomplete + validation
    #[cfg(feature = "json-schema")]
    pub fn json_schema() -> schemars::schema::RootSchema {
        schemars::schema_for!(ConfigExportV1)
    }
}
```

### 3.2. Preset Implementations

```rust
impl Preset {
    /// Fast preset: CI/CD optimized
    pub fn taint_config(&self) -> TaintConfig {
        match self {
            Self::Fast => TaintConfig {
                max_depth: 10,
                max_paths: 100,
                use_points_to: false,  // Skip for speed
                field_sensitive: false,
                use_ssa: false,
                detect_sanitizers: false,
                enable_interprocedural: false,
                worklist_max_iterations: 100,
            },
            Self::Balanced => TaintConfig {
                max_depth: 30,
                max_paths: 500,
                use_points_to: true,
                field_sensitive: true,
                use_ssa: true,
                detect_sanitizers: true,
                enable_interprocedural: true,
                worklist_max_iterations: 1000,
            },
            Self::Thorough => TaintConfig {
                max_depth: 100,
                max_paths: 5000,
                use_points_to: true,
                field_sensitive: true,
                use_ssa: true,
                detect_sanitizers: true,
                enable_interprocedural: true,
                worklist_max_iterations: 10000,
            },
            Self::Custom => TaintConfig::default(), // User must override
        }
    }

    pub fn pta_config(&self) -> PTAConfig {
        match self {
            Self::Fast => PTAConfig {
                mode: PTAMode::Fast,  // Steensgaard only
                field_sensitive: false,
                max_iterations: Some(5),
                auto_threshold: 5000,
                enable_scc: false,
                enable_wave: false,
                enable_parallel: true,
            },
            Self::Balanced => PTAConfig {
                mode: PTAMode::Auto,
                field_sensitive: true,
                max_iterations: Some(10),
                auto_threshold: 10000,
                enable_scc: true,
                enable_wave: true,
                enable_parallel: true,
            },
            Self::Thorough => PTAConfig {
                mode: PTAMode::Precise,  // Andersen always
                field_sensitive: true,
                max_iterations: Some(50),
                auto_threshold: 100000,
                enable_scc: true,
                enable_wave: true,
                enable_parallel: true,
            },
            Self::Custom => PTAConfig::default(),
        }
    }

    pub fn clone_config(&self) -> CloneConfig {
        match self {
            Self::Fast => CloneConfig {
                types_enabled: vec![CloneType::Type1],  // Exact only
                type1: Type1Config {
                    min_tokens: 50,
                    min_loc: 5,
                },
                // ... others disabled
            },
            Self::Balanced => CloneConfig {
                types_enabled: vec![CloneType::Type1, CloneType::Type2],
                type1: Type1Config {
                    min_tokens: 30,
                    min_loc: 3,
                },
                type2: Type2Config {
                    min_tokens: 30,
                    min_loc: 3,
                    rename_similarity: 0.8,
                },
                // ...
            },
            Self::Thorough => CloneConfig {
                types_enabled: vec![
                    CloneType::Type1,
                    CloneType::Type2,
                    CloneType::Type3,
                    CloneType::Type4,
                ],
                type1: Type1Config { min_tokens: 20, min_loc: 2 },
                type2: Type2Config { min_tokens: 20, min_loc: 2, rename_similarity: 0.8 },
                type3: Type3Config { min_tokens: 15, min_loc: 2, gap_threshold: 0.3, similarity: 0.6 },
                type4: Type4Config { min_tokens: 10, min_loc: 1, semantic_threshold: 0.5 },
            },
            Self::Custom => CloneConfig::default(),
        }
    }

    // ... pagerank, chunking, lexical, cache, parallel
}

impl Preset {
    /// Get performance profile for this preset
    pub fn performance_profile(&self) -> PerformanceProfile {
        match self {
            Self::Fast => PerformanceProfile {
                cost_class: CostClass::Low,
                expected_latency: LatencyBand::SubFiveSeconds,
                expected_memory: MemoryBand::Under200MB,
                production_ready: true,
            },
            Self::Balanced => PerformanceProfile {
                cost_class: CostClass::Medium,
                expected_latency: LatencyBand::SubThirtySeconds,
                expected_memory: MemoryBand::Under1GB,
                production_ready: true,
            },
            Self::Thorough => PerformanceProfile {
                cost_class: CostClass::High,
                expected_latency: LatencyBand::SubFiveMinutes,
                expected_memory: MemoryBand::Under4GB,
                production_ready: false,
            },
            Self::Custom => PerformanceProfile {
                cost_class: CostClass::Medium,
                expected_latency: LatencyBand::SubThirtySeconds,
                expected_memory: MemoryBand::Under1GB,
                production_ready: true,
            },
        }
    }
}
```

### 3.3. Builder API (Rust Convenience + FFI Compatibility)

**Dual Approach**:
- **Rust ergonomics**: Closure-based builder for convenience
- **FFI compatibility**: Patch types for Python/C bindings

```rust
// ============================================================================
// Rust Builder API (Closures for Ergonomics)
// ============================================================================
impl PipelineConfig {
    /// Level 1: Simple preset
    pub fn preset(preset: Preset) -> Self {
        Self {
            preset,
            stages: StageControl::default(),
            strict_mode: false,  // Lenient by default
            taint: None,
            pta: None,
            clone: None,
            pagerank: None,
            chunking: None,
            lexical: None,
            cache: None,
            parallel: None,
            provenance: ConfigProvenance::from_preset(preset),
        }
    }

    /// Enable strict mode (errors on disabled stage overrides)
    pub fn strict_mode(mut self, enabled: bool) -> Self {
        self.strict_mode = enabled;
        self
    }

    /// Level 2: Override specific stage (Rust closure convenience)
    pub fn taint<F>(mut self, f: F) -> Self
    where
        F: FnOnce(TaintConfig) -> TaintConfig,
    {
        let base = self.preset.taint_config();
        self.taint = Some(f(base));
        self.provenance.track_field("taint.*", ConfigSource::Builder);
        self
    }

    pub fn pta<F>(mut self, f: F) -> Self
    where
        F: FnOnce(PTAConfig) -> PTAConfig,
    {
        let base = self.preset.pta_config();
        self.pta = Some(f(base));
        self.provenance.track_field("pta.*", ConfigSource::Builder);
        self
    }

    pub fn clone<F>(mut self, f: F) -> Self
    where
        F: FnOnce(CloneConfig) -> CloneConfig,
    {
        let base = self.preset.clone_config();
        self.clone = Some(f(base));
        self.provenance.track_field("clone.*", ConfigSource::Builder);
        self
    }

    // ... other stages

    /// Build and validate
    pub fn build(self) -> Result<ValidatedConfig, ConfigError> {
        // Step 1: Validate individual stage configs (range checks)
        if let Some(ref cfg) = self.taint {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.pta {
            cfg.validate()?;
        }
        if let Some(ref cfg) = self.clone {
            cfg.validate()?;
        }
        // ... validate all

        // Step 2: Check StageControl consistency
        self.validate_stage_control()?;

        // Step 3: Cross-stage validation (정합성 검증)
        self.cross_validate()?;

        Ok(ValidatedConfig(self))
    }

    /// StageControl 일관성 검증
    fn validate_stage_control(&self) -> Result<(), ConfigError> {
        // Disabled stage에 override가 있으면 strict_mode에 따라 처리
        if !self.stages.taint && self.taint.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "taint",
                    hint: "Remove .taint() override or enable the stage with .stages().enable(StageId::Taint)",
                });
            } else {
                eprintln!("WARNING: Taint config ignored (stage disabled). Enable strict_mode to error on this.");
            }
        }
        if !self.stages.pta && self.pta.is_some() {
            if self.strict_mode {
                return Err(ConfigError::DisabledStageOverride {
                    stage: "pta",
                    hint: "Remove .pta() override or enable the stage",
                });
            } else {
                eprintln!("WARNING: PTA config ignored (stage disabled).");
            }
        }
        // ... check all stages
        Ok(())
    }

    /// Cross-stage validation (상호 검증)
    fn cross_validate(&self) -> Result<(), ConfigError> {
        let taint = self.effective_taint();
        let pta = self.effective_pta();

        // 1. Taint가 PTA를 요구하는데 PTA가 꺼져있으면 경고
        if taint.use_points_to && !self.stages.pta {
            return Err(ConfigError::CrossStageConflict {
                issue: "Taint analysis requires Points-to analysis",
                fix: "Enable PTA with .stages().enable(StageId::Pta) or set taint.use_points_to=false",
            });
        }

        // 2. Taint가 field-sensitive인데 PTA가 Fast(Steensgaard)면 경고
        if taint.field_sensitive && pta.mode == PTAMode::Fast {
            return Err(ConfigError::CrossStageWarning {
                warning: "Taint field_sensitive=true with PTA mode=Fast may produce inaccurate results",
                recommendation: "Use PTAMode::Precise or PTAMode::Auto for field-sensitive analysis",
                severity: WarningSeverity::Medium,
            });
        }

        // 3. PTA가 field-sensitive인데 Taint가 아니면 비효율 경고
        if pta.field_sensitive && !taint.field_sensitive && self.stages.taint {
            return Err(ConfigError::CrossStageWarning {
                warning: "PTA field_sensitive=true but Taint field_sensitive=false (performance waste)",
                recommendation: "Either enable Taint field_sensitive or disable PTA field_sensitive",
                severity: WarningSeverity::Low,
            });
        }

        Ok(())
    }

    fn effective_taint(&self) -> TaintConfig {
        self.taint.clone().unwrap_or_else(|| self.preset.taint_config())
    }

    fn effective_pta(&self) -> PTAConfig {
        self.pta.clone().unwrap_or_else(|| self.preset.pta_config())
    }

    /// Level 3: Load from YAML (v1 schema)
    pub fn from_yaml(path: &str) -> Result<Self, ConfigError> {
        let content = std::fs::read_to_string(path)?;
        let export: ConfigExportV1 = serde_yaml::from_str(&content)?;

        // Version check
        if export.version != 1 {
            return Err(ConfigError::UnsupportedVersion {
                found: export.version,
                supported: vec![1],
            });
        }

        let preset = match export.preset.as_str() {
            "fast" => Preset::Fast,
            "balanced" => Preset::Balanced,
            "thorough" => Preset::Thorough,
            "custom" => Preset::Custom,
            _ => return Err(ConfigError::UnknownPreset(export.preset)),
        };

        let mut config = Self::preset(preset);

        // Apply StageControl
        if let Some(stages) = export.stages {
            config.stages = stages;
        }

        // Apply overrides with provenance tracking
        if let Some(overrides) = export.overrides {
            if let Some(taint) = overrides.taint {
                config.taint = Some(taint);
                config.provenance.track_field("taint.*", ConfigSource::Yaml {
                    path: path.to_string(),
                });
            }
            if let Some(pta) = overrides.pta {
                config.pta = Some(pta);
                config.provenance.track_field("pta.*", ConfigSource::Yaml {
                    path: path.to_string(),
                });
            }
            // ... load all overrides
        }

        config.build()
    }

    /// YAML Schema v1
    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    pub struct ConfigExportV1 {
        /// Schema version (always 1 for v1)
        pub version: u32,

        /// Base preset
        pub preset: String,

        /// Stage on/off switches
        #[serde(skip_serializing_if = "Option::is_none")]
        pub stages: Option<StageControl>,

        /// Fine-grained overrides
        #[serde(skip_serializing_if = "Option::is_none")]
        pub overrides: Option<ConfigOverrides>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    pub struct ConfigOverrides {
        #[serde(skip_serializing_if = "Option::is_none")]
        pub taint: Option<TaintConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub pta: Option<PTAConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub clone: Option<CloneConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub pagerank: Option<PageRankConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub chunking: Option<ChunkingConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub lexical: Option<LexicalConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub cache: Option<CacheConfig>,

        #[serde(skip_serializing_if = "Option::is_none")]
        pub parallel: Option<ParallelConfig>,
    }

    /// Export to YAML
    pub fn to_yaml(&self) -> Result<String, ConfigError> {
        let export = ConfigExportV1 {
            version: 1,
            preset: format!("{:?}", self.preset).to_lowercase(),
            stages: Some(self.stages.clone()),
            overrides: Some(ConfigOverrides {
                taint: self.taint.clone(),
                pta: self.pta.clone(),
                clone: self.clone.clone(),
                pagerank: self.pagerank.clone(),
                chunking: self.chunking.clone(),
                lexical: self.lexical.clone(),
                cache: self.cache.clone(),
                parallel: self.parallel.clone(),
            }),
        };

        Ok(serde_yaml::to_string(&export)?)
    }

    /// Performance profile
    pub fn performance_profile(&self) -> PerformanceProfile {
        self.preset.performance_profile()
    }
}

// ============================================================================
// FFI-Friendly Patch API (Python/C Bindings)
// ============================================================================

/// Patch type for TaintConfig (all fields optional)
/// Use for FFI where closures aren't available
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TaintConfigPatch {
    pub max_depth: Option<usize>,
    pub max_paths: Option<usize>,
    pub use_points_to: Option<bool>,
    pub field_sensitive: Option<bool>,
    pub use_ssa: Option<bool>,
    pub detect_sanitizers: Option<bool>,
    pub enable_interprocedural: Option<bool>,
    pub worklist_max_iterations: Option<usize>,
}

impl PipelineConfig {
    /// Apply taint patch (FFI-friendly alternative to closure)
    pub fn taint_patch(mut self, patch: TaintConfigPatch) -> Self {
        let mut base = self.preset.taint_config();

        if let Some(v) = patch.max_depth { base.max_depth = v; }
        if let Some(v) = patch.max_paths { base.max_paths = v; }
        if let Some(v) = patch.use_points_to { base.use_points_to = v; }
        if let Some(v) = patch.field_sensitive { base.field_sensitive = v; }
        if let Some(v) = patch.use_ssa { base.use_ssa = v; }
        if let Some(v) = patch.detect_sanitizers { base.detect_sanitizers = v; }
        if let Some(v) = patch.enable_interprocedural { base.enable_interprocedural = v; }
        if let Some(v) = patch.worklist_max_iterations { base.worklist_max_iterations = v; }

        self.taint = Some(base);
        self.provenance.track_field("taint.*", ConfigSource::Builder);
        self
    }

    // Similar patch methods for pta, clone, etc.
}

/// Example FFI usage (Python via PyO3)
/// ```python
/// config = (PipelineConfig.preset(Preset.BALANCED)
///     .taint_patch(TaintConfigPatch(max_depth=50, max_paths=1000))
///     .build())
/// ```
```

**Rationale for Dual Approach**:
- **Rust users**: Prefer closure-based `.taint(|c| c.max_depth(50))` for ergonomics
- **FFI users**: Use `.taint_patch(TaintConfigPatch { max_depth: Some(50), .. })` since closures don't cross FFI boundary
- **Implementation cost**: Low (Patch types can be generated via derive macro)
- **DX benefit**: Maximum flexibility without compromising either audience

### 3.4. Validated Configuration

```rust
/// Validated configuration (immutable, safe to use)
pub struct ValidatedConfig(PipelineConfig);

impl ValidatedConfig {
    /// Get effective config (preset + overrides)
    pub fn taint(&self) -> Option<TaintConfig> {
        if !self.0.stages.taint {
            return None;
        }
        Some(self.0.taint.clone()
            .unwrap_or_else(|| self.0.preset.taint_config()))
    }

    pub fn pta(&self) -> Option<PTAConfig> {
        if !self.0.stages.pta {
            return None;
        }
        Some(self.0.pta.clone()
            .unwrap_or_else(|| self.0.preset.pta_config()))
    }

    // ... other getters

    /// Debug: show effective values with field-level provenance
    pub fn summary(&self) -> String {
        let profile = self.0.performance_profile();
        let provenance_summary = self.0.provenance.summary();

        format!(
            r#"
Configuration Summary
=====================
{}

Performance Profile:
  - Cost class: {:?}
  - Expected latency: {:?}
  - Expected memory: {:?}
  - Production ready: {}

Effective Configuration:
├─ Taint Analysis (L14)
│  ├─ enabled: {}
│  ├─ max_depth: {}
│  ├─ max_paths: {}
│  ├─ use_points_to: {}
│  └─ field_sensitive: {}
├─ Points-to Analysis (L6)
│  ├─ enabled: {}
│  ├─ mode: {:?}
│  ├─ max_iterations: {:?}
│  └─ auto_threshold: {}
├─ Clone Detection (L10)
│  ├─ enabled: {}
│  ├─ types: {:?}
│  └─ type1_min_tokens: {}
└─ ... (other stages)

Notes:
  - Values shown are EFFECTIVE (after preset + overrides merge)
  - Performance profile is QUALITATIVE (not guaranteed)
  - Use .provenance.summary() for full field-level tracking
"#,
            provenance_summary,
            profile.cost_class,
            profile.expected_latency,
            profile.expected_memory,
            if profile.production_ready { "Yes ✅" } else { "No ⚠️" },
            self.0.stages.taint,
            self.taint().map(|c| c.max_depth).unwrap_or(0),
            self.taint().map(|c| c.max_paths).unwrap_or(0),
            self.taint().map(|c| c.use_points_to).unwrap_or(false),
            self.taint().map(|c| c.field_sensitive).unwrap_or(false),
            self.0.stages.pta,
            self.pta().map(|c| c.mode),
            self.pta().and_then(|c| c.max_iterations),
            self.pta().map(|c| c.auto_threshold).unwrap_or(0),
            self.0.stages.clone,
            self.clone().map(|c| c.types_enabled.clone()),
            self.clone().map(|c| c.type1.min_tokens).unwrap_or(0),
        )
    }
}
```

---

## Part 4: Usage Scenarios (Complete)

### Scenario 1: CI/CD Pipeline (90%)
```rust
// 목표: 빠른 분석, 필수 이슈만
let config = PipelineConfig::preset(Preset::Fast).build()?;

service.index(repo, config)?;

// Fast preset 적용값:
// - Taint: max_depth=10, max_paths=100, PTA=off
// - PTA: Steensgaard only, iterations=5
// - Clone: Type-1만 (exact)
// - PageRank: iterations=3
// - Chunking: max_size=2000, overlap=0
```

### Scenario 2: Daily Development (9%)
```rust
// 목표: 합리적 정확도
let config = PipelineConfig::preset(Preset::Balanced).build()?;

// Balanced preset 적용값:
// - Taint: max_depth=30, max_paths=500, PTA=on
// - PTA: Auto mode, iterations=10
// - Clone: Type-1 + Type-2
// - PageRank: iterations=5, personalized=on
```

### Scenario 3: Security Audit (<1%)
```rust
// 목표: 완전한 분석
let config = PipelineConfig::preset(Preset::Thorough).build()?;

// Thorough preset 적용값:
// - Taint: max_depth=100, max_paths=5000, all features on
// - PTA: Andersen always, iterations=50
// - Clone: All types (Type-1~4)
// - PageRank: iterations=20, HITS=on
```

### Scenario 4: 특정 취약점 집중 분석
```rust
// Taint만 깊게, 나머지는 빠르게
let config = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c
        .max_depth(200)      // SQL Injection 깊은 체인 추적
        .max_paths(10000)
        .detect_sanitizers(true)
    )
    .build()?;
```

### Scenario 5: 대규모 프로젝트 (1M+ LOC)
```rust
// PTA threshold 조정 + 병렬성 최대화
let config = PipelineConfig::preset(Preset::Balanced)
    .pta(|c| PTAConfig {
        auto_threshold: 50000,  // 더 큰 threshold
        enable_parallel: true,
        ..c
    })
    .parallel(|c| c.num_workers(32))  // 32 cores
    .build()?;
```

### Scenario 6: 팀 표준 설정 (YAML)
```yaml
# team-security.yaml
version: 1
preset: balanced

stages:
  taint: true
  pta: true
  clone: true

overrides:
  taint:
    max_depth: 50
    max_paths: 1000
    detect_sanitizers: true
  clone:
    types_enabled: [Type1, Type2, Type3]
    type3:
      min_tokens: 20
      similarity: 0.7
  pagerank:
    max_iterations: 10
    enable_personalized: true
```

```rust
// 팀원 모두 동일한 설정 사용
let config = PipelineConfig::from_yaml("team-security.yaml")?;
```

### Scenario 7: 환경별 설정
```bash
# Development
CODEGRAPH_PRESET=fast cargo run

# Staging
CODEGRAPH_PRESET=balanced \
CODEGRAPH__TAINT__MAX_DEPTH=50 \
cargo run

# Production (nightly security scan)
CODEGRAPH_PRESET=thorough \
CODEGRAPH__TAINT__MAX_DEPTH=200 \
CODEGRAPH__PTA__MODE=precise \
cargo run
```

### Scenario 8: 점진적 조정 (Debugging)
```rust
// 기본 설정으로 시작
let mut config = PipelineConfig::preset(Preset::Balanced);

// 성능 프로파일 확인
let profile = config.performance_profile();
println!("Cost class: {:?}", profile.cost_class);

// 너무 느리면 조정
if profile.cost_class as u8 > CostClass::Medium as u8 {
    config = config
        .taint(|c| c.max_depth(20))  // 깊이 줄이기
        .pta(|c| PTAConfig { mode: PTAMode::Fast, ..c });
}

let validated = config.build()?;
println!("{}", validated.summary());  // 최종 값 확인
```

---

## Part 5: Migration Plan

### Phase 1: 내부 리팩토링 (Week 1-2)

**1.1. Config 모듈 구조 생성**
```
packages/codegraph-ir/src/config/
├── mod.rs                  # Re-exports
├── preset.rs               # Preset enum + implementations
├── stage_configs.rs        # All stage configs
├── pipeline_config.rs      # Main PipelineConfig
├── validation.rs           # Validation logic
├── io.rs                   # YAML/Env loading
├── provenance.rs           # Config tracking
└── patch.rs                # FFI-friendly Patch types
```

**1.2. Stage Config 정의**
- [ ] `TaintConfig` (8 fields)
- [ ] `PTAConfig` (7 fields)
- [ ] `CloneConfig` (12 fields total with per-type)
- [ ] `ChunkingConfig` (5 fields)
- [ ] `LexicalConfig` (6 fields)
- [ ] `ParallelConfig` (4 fields)
- [ ] Reuse existing: `PageRankConfig`, `CacheConfig`

**1.3. Preset 구현**
```rust
impl Preset {
    fn taint_config(&self) -> TaintConfig { /* ... */ }
    fn pta_config(&self) -> PTAConfig { /* ... */ }
    // ... all 8 stages
}
```

**1.4. 하드코딩 제거**
```rust
// Before: packages/codegraph-ir/src/pipeline/processor/stages/advanced.rs:151
let sota_config = SOTAConfig {
    max_depth: 30,  // ❌
    // ...
};

// After
let sota_config = pipeline_config.effective_taint();  // ✅
```

### Phase 2: Public API (Week 3)

**2.1. IndexingService 확장**
```rust
impl IndexingService {
    // New API
    pub fn index_with_config(
        &self,
        repo: PathBuf,
        config: PipelineConfig,
    ) -> Result<IndexingResult> {
        let validated = config.build()?;
        // Use validated.taint(), validated.pta(), etc.
    }

    // Legacy API (호환성)
    pub fn full_reindex(&self, repo: PathBuf) -> Result<IndexingResult> {
        self.index_with_config(repo, PipelineConfig::preset(Preset::Balanced))
    }
}
```

**2.2. Python Bindings (PyO3)**
```python
# Python API
from codegraph_ir import PipelineConfig, Preset, TaintConfigPatch

# Simple
config = PipelineConfig.preset(Preset.FAST)

# Override (Patch API for FFI)
config = (PipelineConfig.preset(Preset.BALANCED)
    .taint_patch(TaintConfigPatch(max_depth=50, max_paths=1000))
    .build())

# YAML
config = PipelineConfig.from_yaml("config.yaml")
```

### Phase 3: Documentation (Week 4)

- [ ] RFC 문서 (이 문서)
- [ ] API 문서 (rustdoc)
- [ ] User Guide (설정 가이드)
- [ ] Migration Guide (기존 사용자용)
- [ ] Examples (10+ scenarios)

---

## Part 6: Benefits Summary

### Developer Experience

| Feature | Before | After | Impact |
|---------|--------|-------|--------|
| **간단한 사용** | N/A | `Config::preset(Fast)` | ⭐️⭐️⭐️⭐️⭐️ |
| **부분 조정** | 불가능 | `.taint(\|c\| c.max_depth(50))` | ⭐️⭐️⭐️⭐️⭐️ |
| **완전한 제어** | 불가능 | YAML 파일 | ⭐️⭐️⭐️⭐️ |
| **타입 안전** | N/A | 컴파일 타임 체크 | ⭐️⭐️⭐️⭐️⭐️ |
| **검증** | N/A | `validate()` | ⭐️⭐️⭐️⭐️⭐️ |
| **IDE 지원** | N/A | 자동완성 + 문서 | ⭐️⭐️⭐️⭐️⭐️ |
| **팀 공유** | 불가능 | YAML 버전 관리 | ⭐️⭐️⭐️⭐️ |
| **성능 투명성** | 불명확 | `performance_profile()` | ⭐️⭐️⭐️⭐️ |
| **FFI 호환성** | N/A | Patch types | ⭐️⭐️⭐️⭐️ |

### Performance Transparency

```rust
let profile = config.performance_profile();
println!("{}", profile.describe());

// Output (Balanced):
// Cost: Medium, Latency: SubThirtySeconds, Memory: Under1GB, Production: Yes ✅
```

### Validation Example

```rust
let result = PipelineConfig::preset(Preset::Fast)
    .taint(|c| c.max_depth(0))  // ❌ Invalid!
    .build();

// Error: ConfigError::Range {
//     field: "max_depth",
//     min: "1",
//     max: "1000",
//     value: "0",
//     hint: "Call chain depth must be at least 1"
// }
```

---

## Part 7: Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Breaking Changes** | Medium | High | Legacy API 유지, Deprecated 경고 |
| **설정 복잡도** | Low | Medium | 90%는 Preset만 사용 |
| **검증 오버헤드** | Low | Low | 한 번만 검증, 이후 캐싱 |
| **YAML 파싱 에러** | Medium | Low | 명확한 에러 메시지 + 예제 |
| **성능 회귀** | Low | High | 벤치마크 CI 추가 |

---

## Part 8: Success Metrics

### Quantitative

- [ ] **59개 하드코딩 → 0개** (100% 설정 가능)
- [ ] **API 사용 난이도 감소**: 3줄 → 1줄 (simple case)
- [ ] **설정 공유 가능**: YAML로 버전 관리
- [ ] **검증 커버리지**: 100% (모든 필드 범위 체크)
- [ ] **문서 커버리지**: 100% (rustdoc + examples)

### Qualitative

- [ ] "설정 변경이 쉬워졌다" (User feedback)
- [ ] "팀 표준 설정 공유 가능" (DevOps)
- [ ] "IDE 자동완성이 훌륭하다" (DX)
- [ ] "성능 예측 가능" (Production)

---

## Appendix A: 전체 설정 참조표

| Stage | Config | Fields | Current | Preset Coverage |
|-------|--------|--------|---------|-----------------|
| **L14 Taint** | `TaintConfig` | 8 | ❌ Hardcoded | Fast/Balanced/Thorough |
| **L6 PTA** | `PTAConfig` | 7 | ❌ Hardcoded | Fast/Balanced/Thorough |
| **L10 Clone** | `CloneConfig` | 12 | ❌ Hardcoded | Fast/Balanced/Thorough |
| **L16 PageRank** | `PageRankConfig` | 5 | ✅ Existing | Fast/Balanced/Thorough |
| **L2 Chunking** | `ChunkingConfig` | 5 | ❌ Missing | Fast/Balanced/Thorough |
| **Lexical** | `LexicalConfig` | 6 | ❌ Missing | Fast/Balanced/Thorough |
| **Cache** | `CacheConfig` | 12 | ✅ Existing | - (runtime only) |
| **Parallel** | `ParallelConfig` | 4 | ⚠️ Partial | Fast/Balanced/Thorough |
| **Total** | 8 configs | **59 fields** | **18 existing** | **100% coverage** |

---

## Appendix B: YAML Schema Example

```yaml
# Complete configuration example (thorough-security.yaml)
version: 1  # ✅ Required field
preset: thorough

stages:
  taint: true
  pta: true
  clone: true
  repomap: true

overrides:
  taint:
    max_depth: 200
    max_paths: 10000
    use_points_to: true
    field_sensitive: true
    use_ssa: true
    detect_sanitizers: true
    enable_interprocedural: true
    worklist_max_iterations: 10000

  pta:
    mode: precise
    field_sensitive: true
    max_iterations: 100
    auto_threshold: 100000
    enable_scc: true
    enable_wave: true
    enable_parallel: true

  clone:
    types_enabled: [Type1, Type2, Type3, Type4]
    type1:
      min_tokens: 20
      min_loc: 2
    type2:
      min_tokens: 20
      min_loc: 2
      rename_similarity: 0.8
    type3:
      min_tokens: 15
      min_loc: 2
      gap_threshold: 0.3
      similarity: 0.6
    type4:
      min_tokens: 10
      min_loc: 1
      semantic_threshold: 0.5

  pagerank:
    damping: 0.85
    max_iterations: 20
    tolerance: 0.000001
    enable_personalized: true
    enable_hits: true

  chunking:
    max_chunk_size: 500
    min_chunk_size: 100
    overlap_lines: 5
    enable_semantic: true
    respect_scope: true

  lexical:
    enable_fuzzy: true
    fuzzy_distance: 3
    max_results: 1000
    enable_ngram: true
    ngram_size: 3
    enable_stemming: true

  parallel:
    num_workers: 16
    batch_size: 50
    enable_rayon: true
    stack_size_mb: 16
```

---

## Appendix C: P0 Revision Changelog

**2025-12-29 P0 Revision**:

1. ✅ **strict_mode 추가**: PipelineConfig에 `strict_mode: bool` 필드 추가, 기본값 false (lenient)
2. ✅ **Provenance line 제거**: `ConfigSource::Yaml`에서 `line: usize` 필드 제거 (v1 한계)
3. ✅ **YAML version 필수화**: 모든 YAML 예제에 `version: 1` 추가
4. ✅ **YAML stages 키 통일**: `enable_` 접두사 제거, stage 이름 직접 사용 (`enable_taint: true` → `taint: true`)
5. ✅ **Performance bands 도입**:
   - 기존: `time_multiplier: f64`, `memory_mb: usize` (specific numbers)
   - 신규: `CostClass`, `LatencyBand`, `MemoryBand` (qualitative classes)
6. ✅ **FFI Patch 패턴 추가**: Rust closure + FFI-friendly Patch types dual approach 문서화

**Breaking Changes**: None (purely additive)

**Migration Path**: v1 사용자는 영향 없음, 새 기능은 opt-in

---

## Decision

**Approve**: [ ]
**Revise**: [ ]
**Reject**: [ ]

**Reviewers**: _____________
**Date**: _____________

---

**RFC End**
