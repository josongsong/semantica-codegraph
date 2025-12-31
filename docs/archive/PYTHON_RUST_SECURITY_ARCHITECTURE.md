# Python-Rust Security Architecture (Final)

## 아키텍처 개요

**Python = Rule Compiler (규칙 관리 + 전달)**
**Rust = Analysis Engine (순수 분석 엔진)**

```
┌──────────────────────────────────────────┐
│  Python: Rule Management Layer           │
│  ├── Pydantic atoms (type-aware)         │  ← 그대로 유지
│  ├── Dataclass rules (pattern-based)     │  ← 그대로 유지
│  └── YAML configs (library models)       │  ← 그대로 유지
│                                           │
│  Rule Export: to_dict()                  │  ← ✅ 추가됨
└──────────────┬───────────────────────────┘
               │
               │ PyO3 (dict transfer)
               │ • sources: List[Dict]
               │ • sinks: List[Dict]
               │ • sanitizers: List[Dict]
               ▼
┌──────────────────────────────────────────┐
│  Rust: Pure Analysis Engine              │
│  ├── Pattern matching (RegexSet)         │
│  ├── Taint tracking (DFG traversal)      │
│  ├── Vulnerability detection             │
│  └── Performance optimization (10-50x)   │
└──────────────────────────────────────────┘
```

## Python Side: Rule Management

### 1. 규칙 정의 (그대로 유지)

```python
# packages/codegraph-engine/.../taint_rules/sources/python_core.py

PYTHON_CORE_SOURCES = [
    SourceRule(
        pattern=r"\binput\s*\(",
        description="User input from stdin",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-20",
        examples=["user_input = input('Enter: ')"],
    ),
    # ... 40+ more sources
]
```

### 2. to_dict() 메서드 (✅ 구현 완료)

```python
# packages/codegraph-engine/.../taint_rules/base.py

@dataclass
class SourceRule(TaintRule):
    taint_kind: TaintKind = TaintKind.USER_INPUT
    framework: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for Rust PyO3 transfer"""
        return {
            "type": "source",
            "id": self.id,
            "pattern": self.pattern,
            "description": self.description,
            "severity": self.severity.value,
            "vuln_type": self.vuln_type.value,
            "taint_kind": self.taint_kind.value,
            "cwe_id": self.cwe_id,
            "framework": self.framework,
            "examples": self.examples,
            "tags": self.tags,
        }

@dataclass
class SinkRule(TaintRule):
    requires_sanitization: bool = True
    framework: str | None = None
    safe_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for Rust PyO3 transfer"""
        return {
            "type": "sink",
            "id": self.id,
            "pattern": self.pattern,
            "description": self.description,
            "severity": self.severity.value,
            "vuln_type": self.vuln_type.value,
            "requires_sanitization": self.requires_sanitization,
            "cwe_id": self.cwe_id,
            "framework": self.framework,
            "safe_patterns": self.safe_patterns,
            "examples": self.examples,
            "tags": self.tags,
        }

@dataclass
class SanitizerRule:
    pattern: str
    sanitizes: dict[VulnerabilityType, float]
    description: str
    framework: str | None = None
    enabled: bool = True
    examples: list[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for Rust PyO3 transfer"""
        return {
            "type": "sanitizer",
            "pattern": self.pattern,
            "description": self.description,
            "sanitizes": {v.value: e for v, e in self.sanitizes.items()},
            "framework": self.framework,
            "examples": self.examples or [],
        }
```

### 3. Rust 엔진 호출

```python
# packages/codegraph-analysis/.../security_pipeline.py

from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.sources import (
    PYTHON_CORE_SOURCES,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.sinks import (
    PYTHON_CORE_SINKS,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.sanitizers import (
    PYTHON_CORE_SANITIZERS,
)
from codegraph_ir import analyze_security  # ⭐ Rust function

class SecurityAnalysisPipeline:
    def analyze(self, ir_document: IRDocument) -> list[Vulnerability]:
        """
        Rust 엔진 호출 (규칙을 dict로 전달)
        """
        # Python 규칙을 dict로 변환
        sources_dicts = [r.to_dict() for r in PYTHON_CORE_SOURCES]
        sinks_dicts = [s.to_dict() for s in PYTHON_CORE_SINKS]
        sanitizers_dicts = [s.to_dict() for s in PYTHON_CORE_SANITIZERS]

        # ⭐ Rust 엔진 호출 (PyO3)
        rust_results = analyze_security(
            ir_document=ir_document,
            sources=sources_dicts,      # List[Dict] → Rust
            sinks=sinks_dicts,          # List[Dict] → Rust
            sanitizers=sanitizers_dicts # List[Dict] → Rust
        )

        # Rust 결과를 Python 객체로 변환
        return [
            Vulnerability.from_dict(r) for r in rust_results
        ]
```

## Rust Side: Pure Engine

### 1. PyO3 인터페이스 (규칙 받기)

```rust
// packages/codegraph-rust/codegraph-ir/src/adapters/pyo3/api/security.rs

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

/// Rust에서 사용할 규칙 구조체
#[derive(Debug, Clone)]
pub struct RustSourceRule {
    pub id: String,
    pub pattern: String,
    pub description: String,
    pub severity: String,
    pub vuln_type: String,
    pub taint_kind: String,
    pub cwe_id: Option<String>,
    pub framework: Option<String>,
    pub examples: Vec<String>,
    pub tags: Vec<String>,
}

impl RustSourceRule {
    /// Python dict → Rust struct 변환
    fn from_py_dict(dict: &PyDict) -> PyResult<Self> {
        Ok(Self {
            id: dict.get_item("id")?.and_then(|v| v.extract().ok()).unwrap_or_default(),
            pattern: dict.get_item("pattern")?.extract()?,
            description: dict.get_item("description")?.extract()?,
            severity: dict.get_item("severity")?.extract()?,
            vuln_type: dict.get_item("vuln_type")?.extract()?,
            taint_kind: dict.get_item("taint_kind")?.extract()?,
            cwe_id: dict.get_item("cwe_id")?.and_then(|v| v.extract().ok()),
            framework: dict.get_item("framework")?.and_then(|v| v.extract().ok()),
            examples: dict.get_item("examples")?.extract().unwrap_or_default(),
            tags: dict.get_item("tags")?.extract().unwrap_or_default(),
        })
    }
}

/// ⭐ Python에서 호출할 main function
#[pyfunction]
pub fn analyze_security(
    py: Python<'_>,
    ir_document: PyObject,
    sources: &PyList,
    sinks: &PyList,
    sanitizers: &PyList,
) -> PyResult<Vec<PyObject>> {
    // 1. Python 규칙을 Rust 구조체로 변환
    let rust_sources: Vec<RustSourceRule> = sources
        .iter()
        .map(|item| {
            let dict: &PyDict = item.downcast()?;
            RustSourceRule::from_py_dict(dict)
        })
        .collect::<PyResult<Vec<_>>>()?;

    let rust_sinks: Vec<RustSinkRule> = sinks
        .iter()
        .map(|item| {
            let dict: &PyDict = item.downcast()?;
            RustSinkRule::from_py_dict(dict)
        })
        .collect::<PyResult<Vec<_>>>()?;

    let rust_sanitizers: Vec<RustSanitizerRule> = sanitizers
        .iter()
        .map(|item| {
            let dict: &PyDict = item.downcast()?;
            RustSanitizerRule::from_py_dict(dict)
        })
        .collect::<PyResult<Vec<_>>>()?;

    // 2. IRDocument 변환 (Python → Rust)
    let rust_ir_doc: IRDocument = convert_py_ir_to_rust(py, &ir_document)?;

    // 3. ⭐ Rust 엔진 실행 (순수 알고리즘)
    let engine = SecurityEngine::new(rust_sources, rust_sinks, rust_sanitizers);
    let vulnerabilities = engine.analyze(&rust_ir_doc);

    // 4. 결과를 Python으로 변환
    vulnerabilities
        .iter()
        .map(|v| convert_rust_vuln_to_py(py, v))
        .collect()
}
```

### 2. SecurityEngine (순수 분석 로직)

```rust
// packages/codegraph-rust/codegraph-ir/src/security/engine.rs

use regex::RegexSet;
use std::sync::Arc;

pub struct SecurityEngine {
    // ⭐ RegexSet: 모든 패턴을 단일 DFA로 컴파일 (O(1) 매칭)
    source_set: RegexSet,
    source_rules: Vec<RustSourceRule>,

    sink_set: RegexSet,
    sink_rules: Vec<RustSinkRule>,

    sanitizer_set: RegexSet,
    sanitizer_rules: Vec<RustSanitizerRule>,
}

impl SecurityEngine {
    /// 생성자: Python에서 받은 규칙으로 엔진 생성
    pub fn new(
        sources: Vec<RustSourceRule>,
        sinks: Vec<RustSinkRule>,
        sanitizers: Vec<RustSanitizerRule>,
    ) -> Self {
        // ⭐ 모든 source 패턴을 하나의 RegexSet으로 컴파일
        let source_patterns: Vec<&str> = sources
            .iter()
            .map(|s| s.pattern.as_str())
            .collect();

        let source_set = RegexSet::new(source_patterns)
            .expect("Failed to compile source patterns");

        // Sink, Sanitizer도 동일하게 컴파일
        let sink_patterns: Vec<&str> = sinks.iter().map(|s| s.pattern.as_str()).collect();
        let sink_set = RegexSet::new(sink_patterns).expect("Failed to compile sink patterns");

        let sanitizer_patterns: Vec<&str> = sanitizers.iter().map(|s| s.pattern.as_str()).collect();
        let sanitizer_set = RegexSet::new(sanitizer_patterns)
            .expect("Failed to compile sanitizer patterns");

        Self {
            source_set,
            source_rules: sources,
            sink_set,
            sink_rules: sinks,
            sanitizer_set,
            sanitizer_rules: sanitizers,
        }
    }

    /// ⭐ 분석 실행 (순수 알고리즘)
    pub fn analyze(&self, ir_doc: &IRDocument) -> Vec<Vulnerability> {
        // Step 1: Find all sources (single pass, all patterns at once)
        let sources = self.find_sources(ir_doc);

        // Step 2: Taint tracking (data flow analysis)
        let taint_tracker = TaintTracker::new(sources);
        let tainted_paths = taint_tracker.propagate(ir_doc);

        // Step 3: Detect vulnerabilities (source → sink)
        self.detect_vulnerabilities(tainted_paths, ir_doc)
    }

    /// ⭐ Single pass: O(nodes) not O(nodes × rules)
    fn find_sources(&self, ir_doc: &IRDocument) -> Vec<TaintSource> {
        let mut sources = Vec::new();

        for node in &ir_doc.nodes {
            // ⭐ RegexSet: 모든 40개 패턴을 한 번에 매칭 (O(1))
            let matches = self.source_set.matches(&node.text);

            for idx in matches.iter() {
                sources.push(TaintSource {
                    rule: self.source_rules[idx].clone(),
                    location: node.span.clone(),
                    taint_kind: self.source_rules[idx].taint_kind.clone(),
                });
            }
        }

        sources
    }

    fn detect_vulnerabilities(
        &self,
        tainted_paths: Vec<TaintPath>,
        ir_doc: &IRDocument,
    ) -> Vec<Vulnerability> {
        let mut vulns = Vec::new();

        for path in tainted_paths {
            // Check if tainted data reaches a sink
            if let Some(sink) = self.match_sink(&path.end_node) {
                // Check if sanitized
                if !self.is_sanitized(&path) {
                    vulns.push(Vulnerability {
                        source: path.source.clone(),
                        sink: sink.clone(),
                        flow: path.nodes.clone(),
                        severity: sink.severity.clone(),
                        cwe_id: sink.cwe_id.clone(),
                    });
                }
            }
        }

        vulns
    }

    fn match_sink(&self, node: &IRNode) -> Option<&RustSinkRule> {
        let matches = self.sink_set.matches(&node.text);
        matches.iter().next().map(|idx| &self.sink_rules[idx])
    }

    fn is_sanitized(&self, path: &TaintPath) -> bool {
        path.nodes.iter().any(|node| {
            self.sanitizer_set.is_match(&node.text)
        })
    }
}
```

## Performance

### RegexSet Optimization

**Naive Approach** (각 규칙마다 순회):
```rust
// ❌ O(nodes × rules) = O(1,000 × 40) = 40,000 iterations
for node in &ir_doc.nodes {
    for rule in &source_rules {
        if rule.regex.is_match(&node.text) {
            // ...
        }
    }
}
```

**Optimized Approach** (RegexSet):
```rust
// ✅ O(nodes) = O(1,000) iterations
// RegexSet compiles all patterns into single DFA
let source_set = RegexSet::new(&[
    r"\binput\s*\(",
    r"sys\.argv",
    // ... 40 patterns
]).unwrap();

for node in &ir_doc.nodes {
    // ⭐ All 40 patterns checked at once!
    let matches = source_set.matches(&node.text);
    for idx in matches.iter() {
        sources.push(source_rules[idx]);
    }
}
```

**Result**: **40x speedup** for pattern matching alone!

## Benefits

### Python의 강점 (그대로 유지)
- ✅ 규칙 정의가 쉬움 (Pydantic, dataclass)
- ✅ 수정 즉시 반영 (Python 코드 수정)
- ✅ Type validation (Pydantic)
- ✅ Dynamic 조합 (runtime에 규칙 선택)
- ✅ Framework별 규칙 관리

### Rust의 강점 (새로 추가)
- ✅ 10-50x faster (pattern matching, graph traversal)
- ✅ RegexSet optimization (O(1) pattern matching)
- ✅ Parallel processing (Rayon)
- ✅ Zero-cost abstractions
- ✅ Memory efficiency

## Next Steps

### 1. Rust PyO3 구현 (1일)
- [ ] `RustSourceRule`, `RustSinkRule`, `RustSanitizerRule` 구조체 정의
- [ ] `from_py_dict()` 변환 함수 구현
- [ ] `analyze_security()` PyO3 function 구현
- [ ] Python bindings 테스트

### 2. SecurityEngine 구현 (1일)
- [ ] RegexSet 기반 pattern cache
- [ ] `find_sources()`, `find_sinks()` 구현
- [ ] Taint tracking algorithm 구현
- [ ] Vulnerability detection 로직

### 3. Integration Testing (1일)
- [ ] Python → Rust 규칙 전달 테스트
- [ ] 동일한 코드에 대해 같은 vulnerability 탐지 확인
- [ ] 성능 벤치마크 (Python vs Rust)
- [ ] End-to-end 테스트

## File Locations

**Python (규칙 관리)**:
- `packages/codegraph-engine/.../taint_rules/base.py` (✅ `to_dict()` 추가됨)
- `packages/codegraph-engine/.../taint_rules/sources/python_core.py`
- `packages/codegraph-engine/.../taint_rules/sinks/python_core.py`
- `packages/codegraph-engine/.../taint_rules/sanitizers/python_core.py`

**Rust (분석 엔진)**:
- `packages/codegraph-rust/codegraph-ir/src/adapters/pyo3/api/security.rs` (PyO3 interface)
- `packages/codegraph-rust/codegraph-ir/src/security/engine.rs` (SecurityEngine)
- `packages/codegraph-rust/codegraph-ir/src/security/tracker.rs` (TaintTracker)

**Usage**:
- `packages/codegraph-analysis/.../security_pipeline.py` (Python orchestrator)

## Status

**DECISION: Rust Security Engine NOT Implemented**

After reviewing the existing Python codebase, we found that Python already has:
- ✅ Complete taint analysis system (`TaintAnalyzer`, `InterproceduralTaint`)
- ✅ Rule management with YAML/JSON config (`TaintConfig`)
- ✅ Framework-specific rules (Django, Flask, React, etc.)
- ✅ Adapter registry with LRU caching
- ✅ Pre-defined profiles (strict, performance, frontend, backend)
- ✅ Rule override and customization system

**Implementing all of this in Rust would require:**
- Serde YAML/JSON parsing
- Complex config management
- Profile system
- Framework-specific modules
- Override/filtering logic
- Adapter registry

**Conclusion**: Keep security analysis in Python where it already works well.
Python's flexibility is better suited for rule management and configuration.

If performance becomes critical, consider optimizing specific hot paths rather than rewriting the entire system.
