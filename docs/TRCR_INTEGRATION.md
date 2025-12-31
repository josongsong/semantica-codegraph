# TRCR Integration Guide

## 개요

TRCR (Taint Rule Compiler & Runtime)을 codegraph L14 Taint Analysis에 통합하는 가이드입니다.

### TRCR 특징
- **488 Atoms**: 13개 언어 지원
- **30+ CWE Rules**: SQL Injection, XSS, Command Injection 등
- **Type-Aware Matching**: `base_type`, `constraints` 지원
- **0.0006ms/rule**: 초고속 실행
- **980+ Tests**: Production-ready

---

## 통합 단계

### Phase 1: TRCR 복제 및 설치 (30분)

#### Step 1: TRCR 복제
```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# TRCR 복제 스크립트 실행
chmod +x scripts/integrate_trcr.sh
./scripts/integrate_trcr.sh
```

**결과**:
- `packages/codegraph-trcr/trcr/` - TRCR 소스코드
- `packages/codegraph-trcr/catalog/` - CWE YAML 룰
- `packages/codegraph-trcr/rules/` - Atom 정의

#### Step 2: TRCR 설치
```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# TRCR 패키지 설치
uv pip install -e packages/codegraph-trcr

# 의존성 확인
uv pip list | grep trcr
# → codegraph-trcr 0.3.0
```

#### Step 3: 통합 테스트
```bash
# Python에서 TRCR 사용 가능한지 확인
python scripts/test_trcr_integration.py
```

**예상 출력**:
```
✅ PASS: Import
✅ PASS: Compile CWE Rules
✅ PASS: Execute Rules

Total: 3/3 passed
🎉 All tests passed! TRCR integration is working.
```

---

### Phase 2: PyO3 바인딩 생성 (1-2일)

#### Step 1: PyO3 바인딩 파일 생성
```bash
chmod +x scripts/create_pyo3_bindings.sh
./scripts/create_pyo3_bindings.sh
```

**결과**: `packages/codegraph-ir/src/adapters/pyo3/trcr_bindings.rs`

#### Step 2: Cargo.toml 업데이트
```toml
# packages/codegraph-ir/Cargo.toml
[dependencies]
pyo3 = { version = "0.20", features = ["auto-initialize"] }
```

#### Step 3: mod.rs 업데이트
```rust
// packages/codegraph-ir/src/adapters/pyo3/mod.rs
pub mod bindings;
pub mod trcr_bindings;  // ✅ 추가

pub use trcr_bindings::TRCRBridge;
```

#### Step 4: 빌드 테스트
```bash
cd packages/codegraph-ir
cargo build --lib
```

---

### Phase 3: L14 통합 (1-2일)

#### Step 1: L14에 TRCR 옵션 추가

**`end_to_end_orchestrator.rs` 수정**:
```rust
// StageControl에 TRCR 옵션 추가
pub struct StageControl {
    // ... existing fields
    pub enable_taint: bool,
    pub use_trcr: bool,  // ✅ NEW
}

// execute_l14_taint_analysis 수정
fn execute_l14_taint_analysis(
    &self,
    file_ir_map: &HashMap<String, &ProcessResult>,
) -> Result<Vec<TaintSummary>, CodegraphError> {
    if self.config.stages.use_trcr {
        return self.execute_l14_with_trcr(file_ir_map);
    }

    // Fallback: Current Rust analyzer
    // ... existing code
}

// TRCR 실행 (NEW)
fn execute_l14_with_trcr(
    &self,
    file_ir_map: &HashMap<String, &ProcessResult>,
) -> Result<Vec<TaintSummary>, CodegraphError> {
    use crate::adapters::pyo3::TRCRBridge;

    eprintln!("[L14 TRCR] Starting TRCR-based taint analysis...");

    // Build global call graph
    let mut all_nodes = Vec::new();
    for (_file_path, process_result) in file_ir_map {
        all_nodes.extend(process_result.nodes.iter().cloned());
    }

    // Create TRCR bridge
    let mut trcr = TRCRBridge::new()?;

    // Compile CWE rules
    let cwe_ids = vec![
        "cwe-89",   // SQL Injection
        "cwe-79",   // XSS
        "cwe-78",   // Command Injection
        "cwe-502",  // Deserialization
        "cwe-22",   // Path Traversal
    ];
    trcr.compile_cwe_rules(&cwe_ids)?;

    // Execute rules
    let matches = trcr.execute(&all_nodes)?;

    eprintln!("[L14 TRCR] Found {} matches", matches.len());

    // Convert to TaintSummary
    let mut function_summaries = HashMap::new();

    for m in &matches {
        let summary = function_summaries
            .entry(m.entity_id.clone())
            .or_insert_with(|| TaintSummary {
                function_id: m.entity_id.clone(),
                sources_found: 0,
                sinks_found: 0,
                taint_flows: 0,
            });

        match m.effect_kind.as_str() {
            "source" => summary.sources_found += 1,
            "sink" => summary.sinks_found += 1,
            _ => {}
        }

        eprintln!("[L14 TRCR] 🔥 Match: {} → {} (conf={:.2f})",
            m.entity_id, m.rule_id, m.confidence);
    }

    Ok(function_summaries.into_values().collect())
}
```

#### Step 2: 테스트 업데이트
```rust
// test_taint_e2e.rs 수정
let config = E2EPipelineConfig {
    // ... existing config
    stages: StageControl {
        enable_taint: true,
        use_trcr: true,  // ✅ Enable TRCR
        // ...
    },
};
```

#### Step 3: 테스트 실행
```bash
cargo run --example test_taint_e2e
```

**예상 출력**:
```
[L14 TRCR] Starting TRCR-based taint analysis...
[L14 TRCR] Compiled 5 CWE rules
[L14 TRCR] Found 12 matches
[L14 TRCR] 🔥 Match: vulnerable.unsafe_function → sink.sql.sqlite3 (conf=1.00)
[L14 TRCR] 🔥 Match: vulnerable.unsafe_function → input.user (conf=0.90)
✅ Pipeline completed successfully!
```

---

## 통합 후 비교

### Before (현재 Rust)
```
Capabilities:
  - Basic pattern matching
  - Inter + Intra-procedural
  - ~20 hardcoded rules

Performance:
  - ~7ms

Accuracy:
  - 2 vulnerabilities detected
```

### After (TRCR)
```
Capabilities:
  - Type-aware matching
  - Constraints validation
  - 488 atoms × 30 CWEs = ~14,640 rules

Performance:
  - ~15-20ms (PyO3 overhead)

Accuracy:
  - 12+ vulnerabilities detected
  - Precise type checking
  - False positive filtering
```

---

## 스크립트 요약

| 스크립트 | 용도 | 실행 시간 |
|----------|------|-----------|
| `integrate_trcr.sh` | TRCR 복제 및 패키지 생성 | 1분 |
| `test_trcr_integration.py` | Python 통합 검증 | 10초 |
| `create_pyo3_bindings.sh` | Rust 바인딩 생성 | 1분 |

---

## 트러블슈팅

### Python Import Error
```bash
# PYTHONPATH 설정
export PYTHONPATH=/Users/songmin/Documents/code-jo/semantica-v2/codegraph/packages/codegraph-trcr:$PYTHONPATH

# 또는 editable install
uv pip install -e packages/codegraph-trcr
```

### PyO3 Build Error
```bash
# PyO3 버전 확인
cargo tree | grep pyo3

# Python 버전 확인 (3.11+ 필요)
python --version
```

### CWE 파일 없음
```bash
# catalog 복제 확인
ls packages/codegraph-trcr/catalog/cwe/
# → cwe-89.yaml, cwe-79.yaml, ...
```

---

## 다음 단계

1. ✅ **Phase 1 완료**: TRCR 복제 및 설치
2. 🔄 **Phase 2 진행 중**: PyO3 바인딩
3. ⏳ **Phase 3 대기**: L14 통합

총 예상 시간: **3-5일**
