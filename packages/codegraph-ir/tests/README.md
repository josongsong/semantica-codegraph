# Testing Guide - Quick Reference

## 🚀 테스트 실행

```bash
# 빠른 테스트만 실행
cargo test

# 모든 테스트 (slow 포함)
cargo test -- --ignored

# 벤치마크
cargo bench

# 커버리지
make coverage-open
```

## 📝 테스트 작성 방법

### 현재 API 구조

```rust
// PipelineResult 구조
pub struct PipelineResult<S: PipelineStages> {
    pub outputs: S::Outputs,        // Stage outputs (nodes, edges, etc.)
    pub metadata: PipelineMetadata, // Metadata (includes errors)
    pub stage_metrics: HashMap<&'static str, StageMetrics>,
}

// SingleFileStages outputs
pub type SingleFileOutputs = (
    Vec<Node>,          // IR nodes
    Vec<Edge>,          // IR edges
    Vec<Occurrence>,    // Occurrences
    Vec<TypeEntity>,    // Types
    Vec<BasicFlowGraph>,// BFG
    Vec<CFGEdge>,       // CFG
    Vec<DataFlowGraph>, // DFG
    Vec<SSAGraph>,      // SSA
);
```

### 기본 테스트 예제

```rust
use codegraph_ir::pipeline::process_python_file;

#[test]
fn test_parse_function() {
    let source = "def hello(): pass";
    let result = process_python_file(source, "repo", "test.py", "test");

    // Errors는 metadata에 있음
    assert!(result.metadata.errors.is_empty());

    // Nodes는 outputs의 첫 번째 요소
    let (nodes, _edges, ..) = &result.outputs;
    assert!(!nodes.is_empty());
}
```

### Fixture 사용

```rust
mod common;
use common::fixtures::*;

#[test]
fn test_with_fixture() {
    let source = fixture_simple_class("User", 3);
    let result = process_python_file(&source, "repo", "test.py", "test");

    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 4); // class + 3 methods
}
```

## 🛠️ 사용 가능한 Fixture

```rust
// Python
fixture_simple_function("name")
fixture_simple_class("ClassName", method_count)
fixture_django_model("ModelName", field_count)
fixture_with_imports(&["os", "sys"])

// TypeScript
fixture_typescript_class("ClassName", method_count)
fixture_typescript_interface("InterfaceName", property_count)
fixture_react_component("ComponentName")

// 파일 로드
load_fixture("python/simple.py")
load_fixture_dir("python/")
```

## ⚠️ 현재 상태

### ✅ 작동하는 것
- Fixture generators
- Property test strategies (proptest)
- Benchmark infrastructure
- CI/CD pipeline
- Development tooling (Makefile)

### 🔧 업데이트 필요
- `tests/common/assertions.rs` - 실제 API에 맞춰 수정 필요
- `tests/common/builders.rs` - 실제 types에 맞춰 수정 필요

## 📚 자세한 문서

- [TESTING.md](../TESTING.md) - 전체 테스트 가이드
- [TEST_ORGANIZATION.md](../../TEST_ORGANIZATION.md) - 테스트 구조 설명
- [Makefile](../Makefile) - 사용 가능한 모든 명령어
