# Codegraph SOTA 정적 분석 사용 가이드

## 🚀 Quick Start

### 1. 기본 사용 (가장 간단)

```rust
use codegraph_ir::pipeline::{E2EPipelineConfig, IRIndexingOrchestrator};
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 1. Config 생성 (Balanced 프리셋 - 기본값)
    let config = E2EPipelineConfig::balanced()
        .with_repo_root(PathBuf::from("/path/to/your/repo"))
        .with_repo_name("my-project".to_string());
    
    // 2. Orchestrator 생성 및 실행
    let orchestrator = IRIndexingOrchestrator::new(config);
    let result = orchestrator.execute()?;
    
    // 3. 결과 확인
    println!("📊 분석 완료!");
    println!("  - 파일: {} 개", result.stats.files_processed);
    println!("  - 노드: {} 개", result.full_result.nodes.len());
    println!("  - 엣지: {} 개", result.full_result.edges.len());
    println!("  - 청크: {} 개", result.full_result.chunks.len());
    println!("  - 시간: {:?}", result.stats.total_duration);
    
    Ok(())
}
```

---

## 📋 프리셋 선택 가이드

| 프리셋 | 사용 시나리오 | 속도 | 정밀도 |
|--------|--------------|------|--------|
| `Fast` | CI/CD, 빠른 피드백 | 🚀🚀🚀 | ⭐⭐ |
| `Balanced` | 일반 개발 (기본값) | 🚀🚀 | ⭐⭐⭐ |
| `Thorough` | 보안 감사, 전체 분석 | 🚀 | ⭐⭐⭐⭐⭐ |

```rust
// Fast: CI/CD용 (5초 목표)
let config = E2EPipelineConfig::fast();

// Balanced: 개발용 (30초 목표) - 기본값
let config = E2EPipelineConfig::balanced();

// Thorough: 전체 분석 (시간 제한 없음)
let config = E2EPipelineConfig::thorough();
```

---

## ⚙️ 상세 설정 (Level 2)

### Taint Analysis 설정

```rust
use codegraph_ir::config::{PipelineConfig, Preset};

let config = PipelineConfig::preset(Preset::Balanced)
    .taint(|c| c
        .max_depth(100)        // 최대 분석 깊이
        .max_paths(5000)       // 최대 경로 수
        .ifds_enabled(true)    // IFDS 알고리즘 활성화
        .backward_analysis_enabled(true)  // 역방향 분석
    )
    .build()?;
```

### Points-To Analysis 설정

```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .pta(|c| c
        .mode(PTAMode::Andersen)  // Andersen (정밀) / Steensgaard (빠름)
        .max_iterations(1000)
        .context_sensitivity(2)   // k-CFA (0=context-insensitive)
    )
    .build()?;
```

### Clone Detection 설정

```rust
let config = PipelineConfig::preset(Preset::Balanced)
    .clone(|c| c
        .type1_enabled(true)   // 완전 복제
        .type2_enabled(true)   // 이름 변경 복제
        .type3_enabled(true)   // 갭 있는 복제
        .type4_enabled(true)   // 의미적 복제
        .min_lines(6)          // 최소 라인 수
        .similarity_threshold(0.8)
    )
    .build()?;
```

---

## 🔧 개별 분석기 직접 사용

### Taint Analysis

```rust
use codegraph_ir::features::taint_analysis::infrastructure::InterproceduralTaintAnalyzer;

let mut analyzer = InterproceduralTaintAnalyzer::new();

// 소스/싱크/새니타이저 등록
analyzer.add_source("user_input");
analyzer.add_source("request.body");
analyzer.add_sink("execute_sql");
analyzer.add_sink("eval");
analyzer.add_sanitizer("escape_html");

// 분석 실행
let results = analyzer.analyze(&ir_document)?;

for vuln in results {
    println!("⚠️ Taint: {} → {} (경로: {:?})", 
        vuln.source, vuln.sink, vuln.path);
}
```

### Concurrency Analysis (Race Detection)

```rust
use codegraph_ir::features::concurrency_analysis::{
    AsyncRaceDetector, RaceCondition
};

let detector = AsyncRaceDetector::new();
let races = detector.detect(&ir_document)?;

for race in races {
    println!("🏃 Race Condition: {:?}", race);
    println!("  - 변수: {}", race.variable);
    println!("  - 위치: {:?}", race.locations);
    println!("  - 심각도: {:?}", race.severity);
}
```

### Clone Detection

```rust
use codegraph_ir::features::clone_detection::HybridCloneDetector;

let detector = HybridCloneDetector::new();
let clones = detector.detect(&ir_document)?;

for clone in clones {
    println!("📋 Clone (Type {}): similarity={:.1}%", 
        clone.clone_type, clone.similarity * 100.0);
    println!("  - 위치1: {}", clone.fragment1.file_path);
    println!("  - 위치2: {}", clone.fragment2.file_path);
}
```

### SMT/Symbolic Execution

```rust
use codegraph_ir::features::smt::infrastructure::UnifiedOrchestrator;

let orchestrator = UnifiedOrchestrator::new();
let results = orchestrator.verify(&ir_document)?;

for result in results {
    if !result.is_safe {
        println!("🔍 SMT 검증 실패: {}", result.description);
        println!("  - 반례: {:?}", result.counterexample);
    }
}
```

---

## 📊 결과 구조

```rust
// E2EPipelineResult 구조
pub struct E2EPipelineResult {
    pub stats: PipelineStats,           // 실행 통계
    pub full_result: FullIndexingResult, // 전체 결과
}

pub struct FullIndexingResult {
    pub nodes: Vec<Node>,               // IR 노드
    pub edges: Vec<Edge>,               // IR 엣지  
    pub chunks: Vec<Chunk>,             // 검색용 청크
    pub symbols: Vec<Symbol>,           // 심볼
    pub taint_results: Vec<TaintSummary>,       // Taint 분석
    pub clone_pairs: Vec<ClonePairSummary>,     // 클론 탐지
    pub points_to_summary: Option<PointsToSummary>, // PTA
    pub concurrency_results: Vec<ConcurrencyIssueSummary>, // Race
    pub smt_results: Vec<SMTVerificationSummary>,  // SMT 검증
    // ... 더 많은 결과
}
```

---

## 🐍 Python에서 사용 (PyO3)

```python
import codegraph_ir

# 전체 파이프라인 실행
result = codegraph_ir.analyze_repository(
    repo_path="/path/to/repo",
    preset="balanced",  # fast, balanced, thorough
)

# 결과 확인
print(f"노드: {len(result.nodes)}")
print(f"Taint 취약점: {len(result.taint_results)}")
print(f"Race Conditions: {len(result.concurrency_results)}")

# 개별 분석
taint_result = codegraph_ir.analyze_taint(
    ir_doc,
    sources=["user_input"],
    sinks=["execute"],
)
```

---

## 🎛️ YAML 설정 (Level 3 - 고급)

```yaml
# team-security.yaml
version: 1
preset: thorough

stages:
  enable_taint: true
  enable_pta: true
  enable_clone: true
  enable_concurrency: true
  enable_smt: true

taint:
  max_depth: 200
  max_paths: 10000
  ifds_enabled: true
  implicit_flow_enabled: true
  backward_analysis_enabled: true

pta:
  mode: andersen
  context_sensitivity: 3
  field_sensitivity: true

clone:
  type1_enabled: true
  type2_enabled: true
  type3_enabled: true
  type4_enabled: true
  min_lines: 5

parallel:
  max_workers: 16
  batch_size: 50
```

```rust
// YAML에서 설정 로드
let config = PipelineConfig::from_yaml("team-security.yaml")?;
```

---

## 📈 성능 팁

1. **병렬 처리**: `parallel.max_workers`를 CPU 코어 수에 맞게 설정
2. **배치 크기**: 메모리가 부족하면 `batch_size` 줄이기
3. **선택적 분석**: 필요한 분석만 활성화 (예: CI에서는 taint만)
4. **증분 분석**: `IndexingMode::Incremental` 사용

```rust
// CI용 최소 설정
let config = E2EPipelineConfig::fast()
    .with_mode(IndexingMode::Incremental);
```

---

## 🔗 관련 문서

- [RFC-001 Config System](docs/RFC-CONFIG-SYSTEM.md)
- [Architecture Overview](docs/CLEAN_ARCHITECTURE_SUMMARY.md)
- [API Reference](docs/api/)
