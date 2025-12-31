# Feature Activation Guide

codegraph-ir의 숨겨진 기능들을 활성화하는 방법 가이드입니다.

## 📊 Feature Exposure Matrix

### Pipeline Stage Control

| Stage | 기본값 | `StageControl::security()` | `StageControl::all()` |
|-------|--------|---------------------------|----------------------|
| `parsing` | ✅ | ✅ | ✅ |
| `chunking` | ✅ | ✅ | ✅ |
| `lexical` | ✅ | ✅ | ✅ |
| `cross_file` | ❌ | ✅ | ✅ |
| `clone` | ❌ | ❌ | ✅ |
| `pta` | ❌ | ✅ | ✅ |
| `flow_graphs` | ❌ | ✅ | ✅ |
| `type_inference` | ❌ | ❌ | ✅ |
| `symbols` | ❌ | ❌ | ✅ |
| `effects` | ❌ | ✅ | ✅ |
| `taint` | ❌ | ✅ | ✅ |
| `repomap` | ❌ | ❌ | ✅ |
| `heap` | ❌ | ✅ | ✅ |
| `pdg` | ❌ | ✅ | ✅ |
| `concurrency` | ❌ | ✅ | ✅ |
| `slicing` | ❌ | ✅ | ✅ |

### HeapConfig (Preset별)

| Feature | Fast | Balanced | Thorough |
|---------|------|----------|----------|
| `enabled` | ❌ | ✅ | ✅ |
| `enable_memory_safety` | ❌ | ✅ | ✅ |
| `enable_ownership` | ❌ | ✅ | ✅ |
| `enable_escape` | ❌ | ✅ | ✅ |
| `enable_security` | ❌ | ✅ | ✅ |
| `enable_context_sensitive` | ❌ | ❌ | ✅ |
| `enable_symbolic_memory` | ❌ | ✅ | ✅ |
| `enable_separation_logic` | ❌ | ❌ | ✅ |
| `enable_bi_abduction` | ❌ | ❌ | ✅ |

### TaintConfig (Preset별)

| Feature | Fast | Balanced | Thorough |
|---------|------|----------|----------|
| `ifds_enabled` | ❌ | ✅ | ✅ |
| `ide_enabled` | ❌ | ✅ | ✅ |
| `sparse_ifds_enabled` | ❌ | ❌ | ✅ |
| `implicit_flow_enabled` | ❌ | ❌ | ✅ |
| `backward_analysis_enabled` | ❌ | ✅ | ✅ |
| `context_sensitive` | ❌ | ✅ | ✅ |
| `path_sensitive` | ❌ | ❌ | ✅ |

---

## 🚀 사용 방법

### 1. 기본 사용 (Fast - CI/CD용)

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

let config = PipelineConfig::preset(Preset::Fast)
    .build()?;

// 기본 파싱 + 청킹 + 어휘 분석만 실행
```

### 2. 보안 분석 활성화

```rust
use codegraph_ir::config::{PipelineConfig, Preset, StageControl};

let config = PipelineConfig::preset(Preset::Balanced)
    .with_stages(|_| StageControl::security())  // 보안 관련 스테이지 활성화
    .build()?;

// 실행 항목:
// - Taint Analysis (SQL Injection, XSS 등)
// - Heap Analysis (UAF, Buffer Overflow 등)
// - Concurrency Analysis (Race Condition)
// - PDG & Slicing (버그 원인 추적)
```

### 3. 전체 분석 활성화

```rust
use codegraph_ir::config::{PipelineConfig, Preset, StageControl};

let config = PipelineConfig::preset(Preset::Thorough)
    .with_stages(|_| StageControl::all())  // 모든 스테이지 활성화
    .build()?;

// 모든 분석 기능 실행 (시간 소요 주의)
```

### 4. 특정 Stage만 활성화

```rust
use codegraph_ir::config::{PipelineConfig, Preset, StageId};

let config = PipelineConfig::preset(Preset::Balanced)
    .with_stages(|s| s
        .enable(StageId::Taint)      // Taint 분석
        .enable(StageId::Heap)       // Heap 분석
        .enable(StageId::Pta)        // Points-to 분석 (Taint 의존)
    )
    .build()?;
```

### 5. HeapConfig 세부 조정

```rust
use codegraph_ir::config::{PipelineConfig, Preset, StageId, HeapConfig};

let config = PipelineConfig::preset(Preset::Balanced)
    .with_stages(|s| s.enable(StageId::Heap))
    .heap(|h| h
        .enable_memory_safety(true)      // UAF, Double-Free, Buffer Overflow
        .enable_ownership(true)          // Rust-style ownership tracking
        .enable_context_sensitive(true)  // Context-sensitive analysis
        .enable_separation_logic(true)   // Separation logic verification
        .enable_bi_abduction(true)       // Infer specs from code
        .context_sensitivity(2)          // 2-callsite sensitivity
        .add_copy_type("i32")
        .add_move_type("Vec<T>")
    )
    .build()?;
```

### 6. TaintConfig SOTA 기능 활성화

```rust
use codegraph_ir::config::{PipelineConfig, Preset, StageId, TaintConfig};

let config = PipelineConfig::preset(Preset::Thorough)
    .with_stages(|s| s.enable(StageId::Taint).enable(StageId::Pta))
    .taint(|t| t
        .ifds_enabled(true)              // IFDS 솔버
        .ide_enabled(true)               // IDE 솔버 (값 추적)
        .sparse_ifds_enabled(true)       // Sparse 최적화
        .implicit_flow_enabled(true)     // 암시적 정보 흐름
        .backward_analysis_enabled(true) // 역방향 분석
        .context_sensitive(true)         // Context-sensitive
        .path_sensitive(true)            // Path-sensitive
    )
    .build()?;
```

---

## 🏗️ Hexagonal Architecture 사용

### HeapAnalysisService (권장)

```rust
use codegraph_ir::config::HeapConfig;
use codegraph_ir::pipeline::processor::stages::run_heap_analysis_with_config;

// Config-driven Hexagonal Architecture
let config = HeapConfig::from_preset(Preset::Balanced)
    .enable_ownership(true)
    .enable_security(true);

let result = run_heap_analysis_with_config(&nodes, &edges, &config);

// result.memory_issues      - 메모리 안전성 이슈
// result.ownership_issues   - 소유권 위반
// result.escape_states      - 이스케이프 상태
// result.security_issues    - 보안 취약점
```

### 커스텀 Checker 추가 (SOLID: OCP)

```rust
use codegraph_ir::features::heap_analysis::{
    HeapAnalysisService, MemoryCheckerPort, HeapIssue,
};

// 커스텀 체커 구현
struct MyCustomChecker;

impl MemoryCheckerPort for MyCustomChecker {
    fn analyze(&mut self, nodes: &[Node]) -> Vec<HeapIssue> {
        // 커스텀 분석 로직
        vec![]
    }

    fn name(&self) -> &'static str {
        "MyCustomChecker"
    }
}

// 서비스에 추가 (코드 수정 없이!)
let mut service = HeapAnalysisService::new(config);
service.with_memory_checker(Box::new(MyCustomChecker));
```

---

## 📋 Feature 의존성 매트릭스

```
Taint Analysis
├── requires: PTA (Points-to Analysis)
├── requires: Flow Graphs (CFG/DFG)
└── optional: Heap Analysis (alias info)

Heap Analysis
├── requires: PTA (for pointer analysis)
├── optional: DFG (for def-use info)
└── optional: CFG (for path-sensitive)

Concurrency Analysis
├── requires: Escape Analysis
├── requires: Heap Analysis
└── optional: PTA

Slicing
├── requires: PDG
├── requires: DFG
└── requires: CFG
```

---

## ⚠️ 성능 주의사항

| Preset | 예상 시간 | 메모리 | 권장 사용 |
|--------|----------|--------|----------|
| Fast | 1-5s | ~100MB | CI/CD, 빠른 피드백 |
| Balanced | 10-60s | ~500MB | 일반 개발 |
| Thorough | 1-10min | ~2GB | 릴리즈 전 전체 분석 |
| All Stages | 5-30min | ~4GB | 연구/심층 분석 |

---

## 🔗 관련 문서

- [RFC-001: Configuration System](./RFC-CONFIG-SYSTEM.md)
- [HeapConfig Reference](./handbook/config/heap-config.md)
- [TaintConfig Reference](./handbook/config/taint-config.md)
- [SOLID Compliance](./CLEAN_ARCHITECTURE_SUMMARY.md)
