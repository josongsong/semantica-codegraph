# RFC: Codegraph-IR 통합 벤치마크 프레임워크

## 상태: Draft
## 작성일: 2025-12-31

---

## 1. 목적

**AI 코딩 에이전트 Use Case 관점**에서 codegraph-ir의 모든 기능을 벤치마킹.

---

## 2. Use Case 기반 그룹핑

### 2.1 벤치마크 카테고리 (AI Agent 관점)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AI CODING AGENT USE CASES                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  🔍 RETRIEVAL (검색)                                                │
│  ├── Semantic Search      "이 함수와 비슷한 코드 찾아줘"             │
│  ├── Symbol Lookup        "UserService 클래스 정의 보여줘"          │
│  └── Reference Finding    "이 함수를 호출하는 곳 찾아줘"            │
│                                                                     │
│  🧠 UNDERSTANDING (이해)                                            │
│  ├── Dependency Graph     "이 모듈의 의존성 보여줘"                 │
│  ├── Call Graph           "이 함수의 호출 흐름 보여줘"              │
│  ├── Data Flow            "이 변수가 어디서 어디로 흐르는지"        │
│  └── Impact Analysis      "이거 바꾸면 어디가 영향받아?"            │
│                                                                     │
│  🔒 SECURITY (보안 분석)                                            │
│  ├── Vulnerability Scan   "SQL Injection 취약점 있어?"              │
│  ├── Taint Analysis       "사용자 입력이 위험한 곳까지 가?"         │
│  └── CWE Detection        "이 코드에 알려진 취약점 패턴 있어?"      │
│                                                                     │
│  🐛 BUG DETECTION (버그 탐지)                                       │
│  ├── Null Deref           "NPE 발생 가능한 곳 있어?"                │
│  ├── Resource Leak        "파일 핸들/커넥션 누수 있어?"             │
│  ├── Race Condition       "동시성 버그 있어?"                       │
│  └── Type Mismatch        "타입 불일치 있어?"                       │
│                                                                     │
│  🔧 REFACTORING (리팩토링 제안)                                     │
│  ├── Code Smell           "이 함수 너무 길어, 분리해야 해?"         │
│  ├── Clone Detection      "중복 코드 있어? 추출할까?"               │
│  ├── Dead Code            "안 쓰는 코드 있어?"                      │
│  └── Complexity           "복잡도 높은 함수 알려줘"                 │
│                                                                     │
│  ✍️ CODE GENERATION (코드 생성 지원)                                │
│  ├── Context Building     "수정하려면 어떤 컨텍스트 필요해?"        │
│  ├── Test Generation      "이 함수 테스트 만들어줘"                 │
│  └── Doc Generation       "이 모듈 문서 만들어줘"                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 카테고리별 Features 매핑

| Use Case | Features | 메트릭 |
|----------|----------|--------|
| **Retrieval** | query_engine, lexical, multi_index, chunking | MRR, NDCG, Recall@K |
| **Understanding** | flow_graph, data_flow, pdg, points_to, cross_file | Graph Accuracy |
| **Security** | taint_analysis, heap_analysis, smt | P/R/F1, CWE Coverage |
| **Bug Detection** | effect_analysis, concurrency_analysis, typestate | P/R/F1 |
| **Refactoring** | clone_detection, cost_analysis, slicing | Precision, Usefulness |
| **Code Gen** | chunking, repomap, ir_generation | Context Quality |

### 2.3 시스템 품질 벤치마크 (NEW)

```
┌─────────────────────────────────────────────────────────────────────┐
│                 SYSTEM QUALITY BENCHMARKS                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  🛡️ ROBUSTNESS (불완전한 코드 대응력)                               │
│  ├── Partial Parsing      "문법 오류 있어도 파싱 가능한 부분까지"   │
│  ├── Unresolved Symbols   "정의 없는 심볼도 합리적으로 추론"        │
│  └── Recovery Rate        "에러 복구 후 분석 재개율"                │
│                                                                     │
│  ⚡ INCREMENTAL (증분 분석 성능)                                    │
│  ├── Edit-Latency         "1줄 수정 시 재분석 시간"                 │
│  ├── Index Update         "인덱스 부분 업데이트 속도"               │
│  └── Cache Efficiency     "캐시 적중률"                             │
│                                                                     │
│  📦 CONTEXT EFFICIENCY (LLM 컨텍스트 효율)                          │
│  ├── Token Compression    "원본 대비 압축률"                        │
│  ├── Relevance Density    "정답 기여 정보 밀도"                     │
│  └── Slice Quality        "슬라이싱 정확도"                         │
│                                                                     │
│  🌐 CROSS-LANGUAGE (다국어 일관성)                                  │
│  ├── Polyglot Linkage     "TS↔Python 데이터 흐름 추적"              │
│  ├── API Mapping          "OpenAPI ↔ 실제 코드 매핑"                │
│  └── Cross-Lang Clones    "다른 언어 간 중복 탐지"                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| Quality | Features | 메트릭 |
|---------|----------|--------|
| **Robustness** | parsing (error recovery) | Resilience Score |
| **Incremental** | cache, file_watcher, indexing | Update Latency, Cache Hit Rate |
| **Context Efficiency** | slicing, chunking, repomap | Token Efficiency, Context Recall |
| **Cross-Language** | cross_file, clone_detection | Linkage Accuracy, Coverage |

---

## 3. 아키텍처 (Hybrid: Rust + Python)

### 3.1 설계 원칙

```
┌─────────────────────────────────────────────────────────────────┐
│                    HYBRID BENCHMARK ARCHITECTURE                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Rust (codegraph-ir/benches/)                                   │
│  └── 역할: 마이크로 성능 벤치마크                               │
│  └── 도구: criterion                                            │
│  └── 측정: Throughput, Latency, Memory                          │
│                                                                 │
│  Python (tools/benchmark/)                                      │
│  └── 역할: 정확도 + E2E + 시각화                                │
│  └── 호출: PyO3 → codegraph_ir                                  │
│  └── 측정: P/R/F1, Ground Truth, Agent 시나리오                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Rust 벤치마크 (성능)

```
packages/codegraph-ir/benches/
├── perf/                         # ⚡ criterion 마이크로벤치마크
│   ├── mod.rs
│   ├── parsing_throughput.rs     # 파싱 처리량
│   ├── cfg_build_latency.rs      # CFG 생성 시간
│   ├── taint_analysis_perf.rs    # Taint 분석 성능
│   ├── incremental_update.rs     # 증분 업데이트 성능
│   └── memory_usage.rs           # 메모리 사용량
│
└── Cargo.toml                    # [[bench]] 정의
```

### 3.3 Python 벤치마크 (정확도 + E2E)

```
tools/benchmark/
├── __init__.py
├── config.py                     # BenchmarkConfig (PipelineConfig 래핑)
│
├── accuracy/                     # 📊 정확도 벤치마크
│   ├── __init__.py
│   ├── base.py                   # AccuracyBenchmark 베이스 클래스
│   ├── security_benchmark.py     # Taint, CWE, OWASP
│   ├── graph_benchmark.py        # CFG, DFG, Call Graph
│   ├── effect_benchmark.py       # Effect Analysis
│   ├── retrieval_benchmark.py    # Search MRR, NDCG
│   ├── context_benchmark.py      # Token Efficiency
│   └── robustness_benchmark.py   # Partial Parsing, Recovery
│
├── e2e/                          # 🎯 E2E Agent 시나리오
│   ├── __init__.py
│   ├── base.py                   # E2EScenario 베이스 클래스
│   ├── bug_fix_scenario.py
│   ├── refactor_scenario.py
│   └── feature_add_scenario.py
│
├── fixtures/                     # 📁 Ground Truth 데이터
│   ├── security/
│   │   ├── cwe89_sql_injection/
│   │   │   ├── vulnerable_01.py
│   │   │   ├── safe_01.py
│   │   │   └── expected.yaml     # Ground Truth
│   │   └── cwe78_command_injection/
│   ├── graph/
│   │   ├── cfg/
│   │   │   ├── if_else.py
│   │   │   └── expected_cfg.json
│   │   └── dfg/
│   ├── context/
│   │   ├── slicing/
│   │   └── compression/
│   └── scenarios/
│       ├── bug_fix_001/
│       ├── refactor_001/
│       └── feature_add_001/
│
├── report/                       # 📈 리포트 생성
│   ├── __init__.py
│   ├── metrics.py                # 메트릭 계산
│   ├── radar_chart.py            # 레이더 차트
│   ├── leaderboard.py            # 리더보드
│   └── templates/
│       └── report.html.jinja2
│
├── cli.py                        # CLI 진입점
└── runner.py                     # 벤치마크 실행기
```

### 3.4 흐름도 (기존 파이프라인 통합)

```
┌─────────────────────────────────────────────────────────────────┐
│              BENCHMARK FLOW (기존 파이프라인 통합)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CLI 실행                                                    │
│     $ python -m benchmark run --category security               │
│                                                                 │
│  2. BenchmarkConfig 생성                                        │
│     config = BenchmarkConfig.from_preset("security")            │
│                                                                 │
│  3. 기존 PipelineBuilder 사용                                   │
│     ┌─────────────────────────────────────────────────────────┐│
│     │ builder = config.to_pipeline_builder()                  ││
│     │                                                         ││
│     │ # 기존 codegraph_engine 파이프라인                       ││
│     │ pipeline = (                                            ││
│     │     builder                                             ││
│     │     .with_profile("full")                               ││
│     │     .with_structural_ir(use_rust=True)  # Rust 가속     ││
│     │     .with_taint_analysis()              # 보안 분석     ││
│     │     .build()                                            ││
│     │ )                                                       ││
│     └─────────────────────────────────────────────────────────┘│
│                                                                 │
│  4. 파이프라인 실행 (기존 코드 재사용)                          │
│     ┌─────────────────────────────────────────────────────────┐│
│     │ result = await pipeline.execute(files=[...])            ││
│     │                                                         ││
│     │ # 내부적으로:                                           ││
│     │ # - StructuralIRStage → codegraph_ir (Rust)             ││
│     │ # - CrossFileStage → Rust cross_file                    ││
│     │ # - AnalysisStage → Rust taint/effect                   ││
│     └─────────────────────────────────────────────────────────┘│
│                                                                 │
│  5. Ground Truth 비교                                           │
│     expected = load_yaml("fixtures/cwe89/expected.yaml")        │
│     metrics = benchmark.compare(result.ir_doc, expected)        │
│                                                                 │
│  6. 리포트 생성                                                 │
│     generate_radar_chart(all_metrics)                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    기존 파이프라인 레이어                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  codegraph_engine (Python)                                      │
│  ├── PipelineBuilder          ← 벤치마크가 사용                 │
│  ├── PipelineStage (Protocol)                                   │
│  │   ├── StructuralIRStage    → codegraph_ir (Rust)            │
│  │   ├── CrossFileStage       → codegraph_ir.cross_file        │
│  │   └── AnalysisStage        → codegraph_ir.taint/effect      │
│  └── IRDocument               ← 공통 모델                       │
│                                                                 │
│  codegraph_ir (Rust via PyO3)                                   │
│  ├── process_python_files()   ← 53x faster                     │
│  ├── IRIndexingOrchestrator   ← 벤치마크에서 직접 호출 가능    │
│  └── E2EPipelineConfig        ← Rust Config                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Interfaces

### 4.1 Python 베이스 클래스 (기존 파이프라인 통합)

```python
# tools/benchmark/accuracy/base.py
"""
기존 파이프라인과 통합:
- PipelineBuilder: codegraph_engine 파이프라인
- codegraph_ir: Rust PyO3 모듈
- IRDocument: 공통 IR 모델
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar, List, Optional
import asyncio

# 기존 모듈 임포트
import codegraph_ir
from codegraph_engine.code_foundation.infrastructure.ir.pipeline.builder import PipelineBuilder
from codegraph_engine.code_foundation.domain.models import IRDocument

T = TypeVar('T')  # Ground Truth 타입

@dataclass
class AccuracyMetrics:
    precision: float
    recall: float
    f1_score: float
    true_positives: int
    false_positives: int
    false_negatives: int

class AccuracyBenchmark(ABC, Generic[T]):
    """
    정확도 벤치마크 베이스 클래스

    기존 파이프라인 통합:
    - PipelineBuilder로 Python 파이프라인 실행
    - codegraph_ir로 직접 Rust 호출 가능
    """

    def __init__(self, config: 'BenchmarkConfig'):
        self.config = config
        # 기존 PipelineBuilder 사용
        self._pipeline_builder = config.to_pipeline_builder()
        self._pipeline = None

    async def _get_pipeline(self):
        """Lazy pipeline initialization"""
        if self._pipeline is None:
            self._pipeline = self._pipeline_builder.build()
        return self._pipeline

    @property
    @abstractmethod
    def name(self) -> str:
        """벤치마크 이름"""
        pass

    @property
    @abstractmethod
    def fixture_dir(self) -> Path:
        """Ground Truth 디렉토리"""
        pass

    @abstractmethod
    def load_fixtures(self) -> List[T]:
        """Ground Truth 로드"""
        pass

    @abstractmethod
    async def analyze(self, fixture: T) -> IRDocument:
        """
        분석 실행 - 기존 파이프라인 사용

        Returns:
            IRDocument with nodes, edges, and analysis results
        """
        pass

    @abstractmethod
    def compare(self, result: IRDocument, expected: T) -> AccuracyMetrics:
        """Ground Truth와 비교"""
        pass

    async def run(self) -> AccuracyMetrics:
        """벤치마크 실행"""
        fixtures = self.load_fixtures()
        all_metrics = []

        for fixture in fixtures:
            result = await self.analyze(fixture)
            metrics = self.compare(result, fixture)
            all_metrics.append(metrics)

        return self._aggregate_metrics(all_metrics)

    def run_sync(self) -> AccuracyMetrics:
        """동기 실행 (테스트용)"""
        return asyncio.run(self.run())


# 예시: Security 벤치마크 구현
class SecurityBenchmark(AccuracyBenchmark['SecurityFixture']):
    """보안 분석 벤치마크 - 기존 Taint 파이프라인 활용"""

    @property
    def name(self) -> str:
        return "security_taint_cwe"

    @property
    def fixture_dir(self) -> Path:
        return Path("tools/benchmark/fixtures/security")

    def load_fixtures(self) -> List['SecurityFixture']:
        # tools/cwe/cwe/test-suite/ 활용
        return load_cwe_fixtures(self.fixture_dir)

    async def analyze(self, fixture: 'SecurityFixture') -> IRDocument:
        """기존 파이프라인으로 분석"""
        pipeline = await self._get_pipeline()

        # 파이프라인 실행 (기존 코드 재사용)
        result = await pipeline.execute(
            files=[fixture.file_path],
            repo_root=fixture.repo_root,
        )

        return result.ir_documents[0]

    def compare(self, result: IRDocument, expected: 'SecurityFixture') -> AccuracyMetrics:
        """탐지 결과 vs Ground Truth 비교"""
        detected_vulns = extract_vulnerabilities(result)
        expected_vulns = expected.vulnerabilities

        tp = len(detected_vulns & expected_vulns)
        fp = len(detected_vulns - expected_vulns)
        fn = len(expected_vulns - detected_vulns)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        return AccuracyMetrics(
            precision=precision,
            recall=recall,
            f1_score=f1,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
        )
```

### 4.2 Config 클래스 (기존 파이프라인 통합)

```python
# tools/benchmark/config.py
"""
기존 파이프라인과 통합:
- codegraph_ir: Rust PyO3 모듈
- PipelineBuilder: codegraph_engine의 파이프라인 빌더
- IRIndexingOrchestrator: Rust 오케스트레이터
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from pathlib import Path

# 기존 Rust 모듈 임포트
import codegraph_ir

# 기존 Python 파이프라인 임포트
from codegraph_engine.code_foundation.infrastructure.ir.pipeline.builder import (
    PipelineBuilder,
    PipelineProfile,
)

class BenchmarkPreset(Enum):
    FAST = "fast"           # PipelineProfile.FAST
    BALANCED = "balanced"   # PipelineProfile.BALANCED
    THOROUGH = "full"       # PipelineProfile.FULL (= Thorough)
    SECURITY = "security"   # Custom: taint + heap enabled
    CONTEXT = "context"     # Custom: chunking + slicing optimized

@dataclass
class BenchmarkConfig:
    """벤치마크 Config - 기존 파이프라인과 통합"""
    preset: BenchmarkPreset
    repo_root: Optional[Path] = None
    timeout_seconds: int = 300
    parallel_workers: int = 4
    use_rust: bool = True
    use_msgpack: bool = True

    def to_pipeline_builder(self) -> PipelineBuilder:
        """기존 PipelineBuilder 반환 (codegraph_engine 통합)"""
        profile = self._map_preset_to_profile()

        builder = (
            PipelineBuilder()
            .with_profile(profile)
            .with_structural_ir(use_rust=self.use_rust, use_msgpack=self.use_msgpack)
        )

        # Preset별 추가 설정
        if self.preset == BenchmarkPreset.SECURITY:
            builder = builder.with_taint_analysis().with_security_analysis()
        elif self.preset == BenchmarkPreset.CONTEXT:
            builder = builder.with_chunking().with_slicing()

        if self.repo_root:
            builder = builder.with_repo_root(self.repo_root)

        return builder

    def to_rust_orchestrator(self) -> 'codegraph_ir.IRIndexingOrchestrator':
        """Rust IRIndexingOrchestrator 반환 (직접 Rust 호출)"""
        config = codegraph_ir.E2EPipelineConfig(
            enable_taint=self.preset in [BenchmarkPreset.SECURITY, BenchmarkPreset.THOROUGH],
            enable_effect=self.preset == BenchmarkPreset.THOROUGH,
            parallel_workers=self.parallel_workers,
        )
        return codegraph_ir.IRIndexingOrchestrator(config)

    def _map_preset_to_profile(self) -> str:
        """BenchmarkPreset → PipelineProfile 매핑"""
        mapping = {
            BenchmarkPreset.FAST: "fast",
            BenchmarkPreset.BALANCED: "balanced",
            BenchmarkPreset.THOROUGH: "full",
            BenchmarkPreset.SECURITY: "full",  # + taint
            BenchmarkPreset.CONTEXT: "balanced",  # + chunking
        }
        return mapping[self.preset]
```

### 4.3 E2E 시나리오 베이스

```python
# tools/benchmark/e2e/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class ScenarioStep:
    action: str           # search, analyze, suggest
    params: Dict[str, Any]
    expected: Dict[str, Any]

@dataclass
class ScenarioResult:
    success: bool
    steps_passed: int
    total_steps: int
    latency_ms: float
    details: Dict[str, Any]

class E2EScenario(ABC):
    """E2E 시나리오 베이스 클래스"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def load_scenario(self) -> List[ScenarioStep]:
        """시나리오 정의 로드 (YAML)"""
        pass

    @abstractmethod
    def execute_step(self, step: ScenarioStep) -> bool:
        """단일 스텝 실행"""
        pass

    def run(self) -> ScenarioResult:
        """시나리오 전체 실행"""
        steps = self.load_scenario()
        passed = 0

        for step in steps:
            if self.execute_step(step):
                passed += 1
            else:
                break  # 실패 시 중단

        return ScenarioResult(
            success=(passed == len(steps)),
            steps_passed=passed,
            total_steps=len(steps),
            ...
        )
```

### 4.4 Rust 성능 벤치마크 (criterion)

```rust
// packages/codegraph-ir/benches/perf/mod.rs
use criterion::{criterion_group, criterion_main, Criterion, BenchmarkId};
use codegraph_ir::config::{PipelineConfig, Preset};

pub fn parsing_throughput(c: &mut Criterion) {
    let config = PipelineConfig::preset(Preset::Fast).build().unwrap();

    c.bench_function("parse_100_files", |b| {
        b.iter(|| {
            // 100개 파일 파싱
        })
    });
}

pub fn taint_analysis_latency(c: &mut Criterion) {
    let mut group = c.benchmark_group("taint_analysis");

    for size in [10, 100, 1000].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(size),
            size,
            |b, &size| {
                b.iter(|| {
                    // size 줄 코드 분석
                })
            }
        );
    }
    group.finish();
}

criterion_group!(benches, parsing_throughput, taint_analysis_latency);
criterion_main!(benches);
```

---

## 5. Config 통합

```rust
/// 벤치마크별 Config 프리셋
pub enum BenchmarkPreset {
    SecurityFull,      // Taint + Heap + CWE
    GraphAnalysis,     // CFG + DFG + PTA
    EffectAnalysis,    // Effect + Concurrency
    PerformanceOnly,   // Throughput 측정
}

impl BenchmarkPreset {
    pub fn to_pipeline_config(&self) -> PipelineConfig {
        match self {
            Self::SecurityFull => PipelineConfig::preset(Preset::Thorough)
                .taint(|t| t.ifds_enabled(true).max_depth(100))
                .heap(|h| h.enable_bi_abduction(true))
                .build(),
            // ...
        }
    }
}
```

---

## 6. Ground Truth 구조

```
fixtures/
├── security/
│   ├── cwe89_sql_injection/
│   │   ├── vulnerable_01.py
│   │   ├── safe_01.py
│   │   └── metadata.yaml      # expected results
│   └── cwe78_command_injection/
│
├── graph/
│   ├── cfg/
│   │   ├── if_else.py
│   │   ├── expected_cfg.json  # expected edges
│   │   └── loop_nested.py
│   └── dfg/
│
└── effect/
    ├── pure_functions/
    ├── io_effects/
    └── complex_effects/
```

---

## 7. 메트릭

### 7.1 정확도 (Security, Effect)
```rust
pub struct AccuracyMetrics {
    pub precision: f64,
    pub recall: f64,
    pub f1_score: f64,
    pub true_positives: usize,
    pub false_positives: usize,
    pub false_negatives: usize,
}
```

### 7.2 그래프 정확도 (Graph)
```rust
pub struct GraphMetrics {
    pub edge_precision: f64,    // 올바른 엣지 비율
    pub edge_recall: f64,       // 누락 없는 엣지 비율
    pub node_coverage: f64,     // 노드 커버리지
}
```

### 7.3 성능 (All)
```rust
pub struct PerformanceMetrics {
    pub throughput_files_per_sec: f64,
    pub latency_p50_ms: f64,
    pub latency_p99_ms: f64,
    pub memory_peak_mb: f64,
}
```

### 7.4 Robustness (불완전 코드)
```rust
pub struct RobustnessMetrics {
    /// 정상 코드 대비 분석 성공률 (0.0 ~ 1.0)
    pub resilience_score: f64,
    /// 파싱 에러에서 복구한 노드 비율
    pub recovery_rate: f64,
    /// 미정의 심볼 추론 정확도
    pub unresolved_inference_accuracy: f64,
}
```

### 7.5 Incremental (증분 분석)
```rust
pub struct IncrementalMetrics {
    /// 1줄 수정 후 재분석 시간 (ms)
    pub edit_latency_ms: f64,
    /// 인덱스 업데이트 시간 (ms)
    pub index_update_ms: f64,
    /// 캐시 적중률 (0.0 ~ 1.0)
    pub cache_hit_rate: f64,
    /// 부분 업데이트 성공률
    pub partial_update_rate: f64,
}
```

### 7.6 Context Efficiency (LLM 컨텍스트)
```rust
pub struct ContextMetrics {
    /// 토큰 효율성 = Relevant Tokens / Total Context Tokens
    pub token_efficiency: f64,
    /// 컨텍스트 압축률 = Sliced Size / Original Size
    pub compression_ratio: f64,
    /// 정답에 필요한 정보가 컨텍스트에 포함된 비율
    pub context_recall: f64,
    /// 불필요한 정보 비율 (낮을수록 좋음)
    pub noise_ratio: f64,
}
```

### 7.7 Cross-Language (다국어)
```rust
pub struct CrossLanguageMetrics {
    /// 다국어 간 데이터 흐름 추적 정확도
    pub linkage_accuracy: f64,
    /// API 스펙 ↔ 구현 매핑 정확도
    pub api_mapping_accuracy: f64,
    /// 다국어 클론 탐지율
    pub cross_lang_clone_recall: f64,
    /// 지원 언어 커버리지
    pub language_coverage: f64,
}
```

---

## 8. 실행 흐름

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SELECT BENCHMARK                                         │
│    cargo bench --bench security                             │
│    cargo bench --bench graph                                │
│    cargo bench --bench all                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. LOAD CONFIG                                              │
│    BenchmarkPreset::SecurityFull.to_pipeline_config()       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. LOAD FIXTURES                                            │
│    fixtures/security/cwe89_sql_injection/*.py               │
│    + metadata.yaml (expected results)                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. RUN PIPELINE                                             │
│    For each fixture:                                        │
│      - Parse → IR → CFG → DFG → Taint → Results             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. CALCULATE METRICS                                        │
│    Compare: Detected vs Expected → P/R/F1                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. GENERATE REPORT                                          │
│    {                                                        │
│      "benchmark": "security",                               │
│      "preset": "SecurityFull",                              │
│      "metrics": { "f1": 0.87, "precision": 0.85 },          │
│      "by_cwe": { "CWE-89": 0.92, "CWE-78": 0.81 }           │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 확장 포인트

새 벤치마크 추가 시:

```rust
// 1. Benchmark trait 구현
pub struct MyNewBenchmark;

impl Benchmark for MyNewBenchmark {
    type Config = MyConfig;
    type Result = MyResult;

    fn name(&self) -> &str { "my_new_benchmark" }
    fn run(&self, config: &Self::Config) -> Self::Result { ... }
}

// 2. fixtures/ 에 Ground Truth 추가
// 3. Cargo.toml에 [[bench]] 추가
```

---

## 10. 우선순위

| Phase | 카테고리 | 벤치마크 | 기간 | 근거 |
|-------|----------|----------|------|------|
| **P0** | Security | Taint + CWE | 1주 | 에이전트 핵심 기능 |
| **P0** | Retrieval | Semantic Search | 3일 | 모든 작업의 시작점 |
| **P0** | Context | Token Efficiency | 3일 | LLM 비용 최적화 |
| **P1** | Understanding | CFG + DFG | 1주 | 코드 이해 기반 |
| **P1** | Incremental | Edit Latency | 3일 | 실시간 에이전트 필수 |
| **P1** | Robustness | Partial Parsing | 3일 | 실제 사용 환경 |
| **P2** | Bug Detection | Effect + Null | 3일 | 버그 수정 지원 |
| **P2** | Refactoring | Clone + Dead Code | 1주 | 리팩토링 제안 |
| **P3** | Cross-Language | Polyglot Linkage | 1주 | 모노레포 지원 |
| **P3** | E2E | Agent Scenarios | 1주 | 통합 검증 |

---

## 11. 성공 기준

### 11.1 정확도 목표

| 카테고리 | 메트릭 | 목표 | SOTA 참고 |
|----------|--------|------|-----------|
| **Security** | Taint F1 | ≥ 80% | Semgrep ~75% |
| | CWE Detection F1 | ≥ 75% | CodeQL ~80% |
| **Retrieval** | MRR@10 | ≥ 0.70 | GitHub Search ~0.5 |
| | Recall@10 | ≥ 0.85 | |
| **Understanding** | CFG Edge Precision | ≥ 95% | |
| | DFG Edge Recall | ≥ 90% | |
| **Bug Detection** | Effect F1 | ≥ 70% | |
| | Null Deref F1 | ≥ 75% | |
| **Refactoring** | Clone Precision | ≥ 85% | PMD ~80% |

### 11.2 성능 목표

| 메트릭 | 목표 | 측정 조건 |
|--------|------|-----------|
| Parsing Throughput | ≥ 10K files/sec | 100 LOC 평균 |
| Full Pipeline | ≥ 1K files/sec | Thorough preset |
| Query Latency P99 | ≤ 100ms | 10K 파일 인덱스 |
| Memory Peak | ≤ 4GB | 100K 파일 레포 |

### 11.3 시스템 품질 목표

| 카테고리 | 메트릭 | 목표 | 설명 |
|----------|--------|------|------|
| **Robustness** | Resilience Score | ≥ 70% | 깨진 코드 분석 성공률 |
| | Recovery Rate | ≥ 80% | 에러 복구 후 재분석 |
| **Incremental** | Edit Latency | ≤ 50ms | 1줄 수정 후 재분석 |
| | Cache Hit Rate | ≥ 90% | 캐시 효율성 |
| **Context** | Token Efficiency | ≥ 60% | 관련 토큰 비율 |
| | Compression Ratio | ≥ 3x | 원본 대비 압축률 |
| **Cross-Lang** | Linkage Accuracy | ≥ 70% | 다국어 연결 정확도 |

### 11.4 Radar Chart 목표 (Overall)

```
목표: 모든 축에서 0.7 이상, 평균 0.75 이상

                  Precision/Recall: 0.80+
                         │
    Robustness: 0.70+ ←──┼──→ Throughput: 0.75+
                         │
    Language: 0.60+  ←───┼───→ Incremental: 0.85+
                         │
              Agent-Friendliness: 0.80+
```

---

## 12. E2E Agent 시나리오

실제 코딩 에이전트가 수행하는 작업을 시뮬레이션:

### 12.1 Bug Fix 시나리오
```yaml
# fixtures/e2e/bug_fix_001/scenario.yaml
name: "SQL Injection Bug Fix"
description: "사용자가 SQL Injection 버그 수정 요청"

steps:
  - action: search
    query: "SQL query execution"
    expected_files: ["db/queries.py", "api/users.py"]

  - action: analyze_security
    target: "api/users.py"
    expected_vulns: ["CWE-89"]

  - action: get_context
    target: "get_user_by_name"
    expected_includes: ["db connection", "parameterized query example"]

  - action: suggest_fix
    expected_pattern: "parameterized query"

ground_truth:
  vulnerable_line: 45
  fixed_code: "cursor.execute('SELECT * FROM users WHERE name = ?', (name,))"
```

### 12.2 Refactoring 시나리오
```yaml
name: "Extract Duplicate Code"
description: "중복 코드 추출 요청"

steps:
  - action: detect_clones
    min_similarity: 0.8
    expected_clones: [["file1.py:10-30", "file2.py:50-70"]]

  - action: analyze_impact
    target: "file1.py:10-30"
    expected_callers: ["main.py", "utils.py"]

  - action: suggest_refactor
    expected: "extract_common_logic()"
```

### 12.3 Feature Add 시나리오
```yaml
name: "Add Caching to API"
description: "API에 캐싱 기능 추가 요청"

steps:
  - action: understand_architecture
    query: "API request handling flow"
    expected_graph: ["router → handler → service → db"]

  - action: find_similar
    query: "caching implementation"
    expected_examples: ["cache/redis_client.py"]

  - action: get_context
    target: "api/handlers.py"
    expected_includes: ["decorator pattern", "existing middleware"]
```

---

## 13. 기존 인프라 활용

| 기존 | 활용 방식 |
|------|----------|
| `tools/cwe/cwe/test-suite/` | Security Ground Truth (29 CWE) |
| `tools/benchmark/fixtures/` | Injection fixtures |
| `tools/benchmark/fixtures/scenarios/` | E2E 시나리오 |
| `tools/benchmark/runners/` | Python 러너 참고 |
| `effect_analysis_ground_truth.rs` | Effect 패턴 참고 |

---

## 14. 벤치마크 시각화 (Leaderboard)

### 14.1 Radar Chart (종합 품질)

```
                    Precision/Recall
                         ⬆️
                         │
                    90%  │    ●
                         │   ╱ ╲
                    70%  │  ╱   ╲
                         │ ╱     ╲
    Language ◀───────────●───────────▶ Throughput
    Coverage             │╲     ╱
                    70%  │ ╲   ╱
                         │  ╲ ╱
                    90%  │   ●
                         │
                         ⬇️
                 Agent-Friendliness
                 (Context Quality)
```

### 14.2 시각화 축 정의

| 축 | 설명 | 구성 메트릭 |
|---|------|-----------|
| **Precision/Recall** | 분석 정확성 | Taint F1, CWE F1, Effect F1 평균 |
| **Throughput** | 대규모 처리 능력 | files/sec, latency P99 |
| **Agent-Friendliness** | 에이전트 친화도 | Token Efficiency, Context Recall |
| **Language Coverage** | 언어 확장성 | 지원 언어 수, Cross-Lang Accuracy |
| **Robustness** | 불완전 코드 대응 | Resilience Score, Recovery Rate |
| **Incremental** | 증분 분석 성능 | Edit Latency, Cache Hit Rate |

### 14.3 리포트 출력 형식

```json
{
  "benchmark_id": "2025-01-01_full_suite",
  "config": "Preset::Thorough",
  "summary": {
    "radar_scores": {
      "precision_recall": 0.82,
      "throughput": 0.75,
      "agent_friendliness": 0.88,
      "language_coverage": 0.60,
      "robustness": 0.70,
      "incremental": 0.85
    },
    "overall_score": 0.77
  },
  "details": {
    "security": { "taint_f1": 0.85, "cwe_f1": 0.78 },
    "retrieval": { "mrr_10": 0.72, "recall_10": 0.88 },
    "context": { "token_efficiency": 0.65, "compression": 0.40 },
    "robustness": { "resilience": 0.70, "recovery": 0.82 },
    "incremental": { "edit_latency_ms": 45, "cache_hit": 0.92 }
  },
  "comparison": {
    "vs_previous": "+2.3%",
    "vs_baseline": "+15.8%"
  }
}
```

### 14.4 CI/CD 통합

```yaml
# .github/workflows/benchmark.yml
benchmark:
  runs-on: ubuntu-latest
  steps:
    - name: Run Benchmarks
      run: cargo bench --features benchmark

    - name: Generate Report
      run: ./tools/benchmark/generate_report.py

    - name: Update Leaderboard
      run: ./tools/benchmark/update_leaderboard.py

    - name: Comment PR with Results
      if: github.event_name == 'pull_request'
      uses: actions/github-script@v6
      with:
        script: |
          // 레이더 차트 + 변경 사항 코멘트
```

---

## 15. CLI 사용법

### 15.1 Python 벤치마크 (정확도/E2E)

```bash
# 전체 벤치마크
python -m benchmark run --all

# 카테고리별 실행
python -m benchmark run --category security
python -m benchmark run --category context
python -m benchmark run --category e2e

# 특정 벤치마크만
python -m benchmark run --name cwe_detection
python -m benchmark run --name token_efficiency

# Preset 지정
python -m benchmark run --all --preset thorough

# 리포트 생성
python -m benchmark report --input results/latest.json
python -m benchmark report --radar-chart
```

### 15.2 Rust 벤치마크 (성능)

```bash
# 전체 성능 벤치마크
cargo bench --bench perf

# 특정 벤치마크
cargo bench --bench perf -- parsing
cargo bench --bench perf -- taint
```

### 15.3 통합 실행

```bash
# 전체 (Rust 성능 + Python 정확도)
./tools/benchmark/run_full.sh
```

---

## 16. Ground Truth 수집 전략

### 16.1 자동 생성
- **CFG/DFG**: TreeSitter + 수동 검증
- **Clone**: PMD/CPD 결과 교차 검증

### 16.2 외부 데이터셋
- **Security**: OWASP Benchmark, Juliet Test Suite
- **Retrieval**: CodeSearchNet, CoSQA

### 16.3 수동 큐레이션
- **Effect**: 도메인 전문가 라벨링
- **E2E**: 실제 버그 수정 PR 분석

---

## 17. 기존 인프라 활용

| 기존 | 활용 방식 |
|------|----------|
| `tools/cwe/cwe/test-suite/` | Security fixtures로 복사 |
| `tools/benchmark/fixtures/` | 그대로 활용 |
| `tools/benchmark/runners/` | 베이스 클래스 참고 |
| `tools/benchmark/report_generator.py` | report/ 모듈로 통합 |

---

## 18. 마이그레이션 계획

| Phase | 작업 | 기간 |
|-------|------|------|
| **1** | Python 베이스 클래스 구현 | 2일 |
| **2** | 기존 fixtures 정리 | 1일 |
| **3** | Security 벤치마크 (P0) | 3일 |
| **4** | Context 벤치마크 (P0) | 2일 |
| **5** | Rust perf 벤치마크 정리 | 2일 |
| **6** | 리포트/시각화 | 2일 |
| **7** | CI 통합 | 1일 |
