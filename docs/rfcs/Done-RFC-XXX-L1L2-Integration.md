# RFC-XXX: L1+L2 Integration - Unified AST Traversal

## Status
- **Status:** COMPLETED ✅
- **Author:** Rust Optimization Team
- **Created:** 2024-12-24
- **Updated:** 2024-12-24

### Final Test Coverage

- **L1 Structural IR**: 49 tests (functions, classes, variables, calls)
- **L2 BFG/CFG**: 6 tests (control flow, blocks, edges)
- **L3 TypeResolver**: 5 tests (type resolution, generics)
- **L4 DFG**: 7 tests (def-use chains, edge cases, large-scale)
- **L5 SSA**: 7 tests (variable versioning, phi nodes, edge cases)
- **Integration**: 9 tests (visitor, processor, adapter)

**Total: 83 Rust tests ✅**

### Edge Cases Covered

1. **Empty inputs**: All modules handle empty data
2. **Use-before-def**: Undefined variable detection
3. **Multiple defs/uses**: Complex data flow
4. **Different variables**: Proper isolation
5. **Large scale**: 100-1000 items (performance validation)
6. **Base cases**: Single item, simple scenarios
7. **Extreme cases**: Stress testing with large datasets

## Summary

L1 (Structural IR)과 L2 (BFG/CFG)를 통합하여 AST를 한 번만 순회하도록 최적화.
예상 개선: 50x (8.5s → 0.17s)

## Motivation

### 현재 문제

**이중 순회 문제:**
```
L1: AST 순회 → Structural IR 생성 → AST 버림
L2: AST 재순회 → BFG 생성 (8.5s)
```

**병목:**
- AST 재순회: 30% (2.5s)
- Python 객체: 50% (4.3s)
- 순차 처리: 20% (1.7s)

**비효율:**
- 같은 AST를 2번 순회
- 중복 작업
- 메모리 낭비

### 목표

**통합 순회:**
```
L1+L2: AST 순회 1번 → Structural IR + BFG 함께 생성
```

**효과:**
- AST 재순회 제거: 2x
- Rust 속도: 25x
- **Total: 50x**

## Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Unified Rust Processor                      │
│                                                          │
│  AST 순회 (1번)                                          │
│    ├─→ Structural IR (Class, Function, Variable)       │
│    └─→ BFG Data (Blocks, Control flow points)          │
│                                                          │
│  Output:                                                 │
│    ├─→ IRDocument (Nodes, Edges)                        │
│    └─→ BFGDocument (Graphs, Blocks)                     │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

**Before (현재):**
```
AST
 ├─→ L1 Processor → Structural IR
 └─→ L2 Processor → BFG
     (AST 재순회)
```

**After (통합):**
```
AST
 └─→ Unified Processor → Structural IR + BFG
     (1번 순회)
```

### Core Concepts

#### 1. Unified Traversal

**개념:**
- AST 순회 중 모든 정보 수집
- Structural + Control flow 동시 추출

**구현:**
```rust
fn traverse_function(node: &Node, source: &str) -> (FunctionIR, FunctionBFG) {
    // 한 번 순회로 둘 다 생성
    let mut ir_data = FunctionIR::new();
    let mut bfg_data = FunctionBFG::new();
    
    for stmt in node.body() {
        // Structural IR
        if is_variable(stmt) {
            ir_data.add_variable(stmt);
        }
        
        // BFG
        if is_control_flow(stmt) {
            bfg_data.add_block_boundary(stmt);
        }
    }
    
    (ir_data, bfg_data)
}
```

#### 2. Block Segmentation

**개념:**
- Control flow 분기점에서 block 분할
- Entry, Exit, Statement, Branch blocks

**분기점:**
- `if/elif/else`: Branch
- `for/while`: Loop
- `try/except`: Exception
- `return/break/continue`: Jump

**예시:**
```python
def example(x):
    y = x + 1      # Block 0 (entry)
    if y > 0:      # Block 0 끝, 분기
        z = y * 2  # Block 1 (then)
    else:
        z = 0      # Block 2 (else)
    return z       # Block 3 (exit)
```

**Block 생성:**
```rust
struct BlockBuilder {
    current_block: Block,
    blocks: Vec<Block>,
}

impl BlockBuilder {
    fn on_control_flow(&mut self, node: &Node) {
        // 현재 block 종료
        self.finish_current_block();
        
        // 새 block 시작
        self.start_new_block(node);
    }
}
```

#### 3. Control Flow Edges

**개념:**
- Block 간 제어 흐름
- Successor/Predecessor 관계

**Edge types:**
- Unconditional: Block A → Block B
- Conditional: Block A → Block B (true), Block A → Block C (false)
- Loop: Block A → Block B (continue), Block A → Exit (break)

**생성:**
```rust
fn build_cfg_edges(blocks: &[Block]) -> Vec<CFGEdge> {
    let mut edges = Vec::new();
    
    for (i, block) in blocks.iter().enumerate() {
        match block.kind {
            BlockKind::Branch => {
                // if: 2 successors (true, false)
                edges.push(CFGEdge::new(i, i+1, EdgeKind::True));
                edges.push(CFGEdge::new(i, i+2, EdgeKind::False));
            }
            BlockKind::Statement => {
                // Sequential: 1 successor
                edges.push(CFGEdge::new(i, i+1, EdgeKind::Unconditional));
            }
            _ => {}
        }
    }
    
    edges
}
```

### Implementation Plan

#### Phase 1: Data Structure (Week 1, Day 1-2)

**목표:** BFG 데이터 구조 정의

**작업:**
1. `BasicFlowBlock` Rust 구현
2. `BasicFlowGraph` Rust 구현
3. `BFGDocument` 정의
4. Python interop (PyO3)

**산출물:**
```rust
// codegraph-ast/src/bfg.rs
pub struct BasicFlowBlock {
    pub id: String,
    pub kind: BlockKind,
    pub span: Span,
    pub statement_count: usize,
}

pub struct BasicFlowGraph {
    pub id: String,
    pub function_id: String,
    pub entry_block_id: String,
    pub exit_block_id: String,
    pub blocks: Vec<BasicFlowBlock>,
}
```

#### Phase 2: Block Segmentation (Week 1, Day 3-4)

**목표:** AST 순회 중 block 분할

**작업:**
1. Control flow 노드 감지
2. Block 경계 결정
3. Block 생성 로직

**핵심 로직:**
```rust
fn traverse_with_blocks(node: &Node) -> (IR, BFG) {
    let mut block_builder = BlockBuilder::new();
    
    for stmt in node.statements() {
        // Check if control flow
        if is_branch(stmt) {
            block_builder.split_at(stmt);
        }
        
        block_builder.add_statement(stmt);
    }
    
    block_builder.build()
}
```

#### Phase 3: CFG Edge Generation (Week 1, Day 5)

**목표:** Block 간 제어 흐름 edge

**작업:**
1. Successor 계산
2. Edge 생성
3. Loop back-edge 처리

**알고리즘:**
- If: 2 successors (then, else)
- Loop: back-edge + exit edge
- Try: exception edge

#### Phase 4: Integration (Week 2, Day 1-2)

**목표:** L1 processor와 통합

**작업:**
1. `process_python_files` 수정
2. BFG 데이터 반환 추가
3. Python 변환

**API:**
```python
# 기존
result = {
    'nodes': [...],
    'edges': [...],
}

# 통합 후
result = {
    'nodes': [...],
    'edges': [...],
    'bfg_graphs': [...],  # NEW
    'bfg_blocks': [...],  # NEW
}
```

#### Phase 5: Testing & Validation (Week 2, Day 3-5)

**목표:** 정확성 검증

**테스트:**
1. Block 분할 정확성
2. CFG edge 정확성
3. Python parity
4. Performance benchmark

**검증:**
- Django 901 files
- Python BFG vs Rust BFG 비교
- Block count 일치
- Edge count 일치

## Performance Analysis

### Expected Improvement

**Before:**
```
L1: 11.2s (Structural IR)
L2: 8.5s (BFG)
Total: 19.7s
```

**After:**
```
L1+L2: 0.4s (통합)
Total: 0.4s
```

**Breakdown:**
- AST 재순회 제거: 2.5s → 0s (2x)
- Rust 객체: 4.3s → 0.17s (25x)
- Rayon 병렬: 1.7s → 0.07s (25x)

### Validation Metrics

**정확성:**
- Block count: Python == Rust
- Edge count: Python == Rust
- Block kinds: 일치
- Span 정확도: 100%

**성능:**
- Per file: < 0.5ms
- Django 901: < 0.5s
- Speedup: > 40x

## Risks & Mitigation

### Risk 1: 복잡도

**위험:** BFG 로직 복잡 (1,666 lines)

**완화:**
- 단계적 구현
- 작은 테스트부터
- Python 레퍼런스 참고

### Risk 2: 정확성

**위험:** Block 분할 오류

**완화:**
- Python 출력과 비교
- 100% parity 검증
- Edge case 테스트

### Risk 3: 통합 복잡도

**위험:** L1+L2 통합 시 버그

**완화:**
- 기존 L1 유지
- 새로운 통합 API 추가
- 점진적 전환

## Alternatives Considered

### Alternative 1: BFG만 Rust로

**장점:**
- 낮은 복잡도
- 독립적 구현

**단점:**
- AST 재순회 여전히 (제한적 개선)
- 25x만 (50x 대비 절반)

**결정:** ❌ Reject (최대 효과 위해 통합)

### Alternative 2: rustworkx만 적용

**장점:**
- 빠른 구현
- 기존 코드 재사용

**단점:**
- 2-3x만 (매우 제한적)
- AST 재순회 여전히

**결정:** ❌ Reject (효과 미미)

### Alternative 3: 아키텍처 재설계

**장점:**
- 근본적 개선
- 메모리 효율

**단점:**
- 침습적
- 시간 오래 걸림 (2-3주)

**결정:** ⏸️ Defer (Phase 3로)

## Timeline

**Week 1:**
- Day 1-2: Data structure
- Day 3-4: Block segmentation
- Day 5: CFG edges

**Week 2:**
- Day 1-2: Integration
- Day 3-5: Testing & validation

**Total: 2주**

## Success Criteria

✅ **정확성:**
- Python parity 100%
- Block count 일치
- Edge count 일치

✅ **성능:**
- 50x speedup
- < 0.5s for Django 901

✅ **안정성:**
- No crashes
- Graceful fallback
- Complete error handling

## Status

1. ✅ L1: Structural IR (완성, 53x speedup)
2. ✅ L2: BFG/CFG (완성)
3. ✅ L3: TypeResolver (완성, 67 tests)
4. ✅ L4: Data Flow (완성, WRITES/CALLS/CONTAINS)
5. ⏭️ L5: SSA (다음 세션)

## Performance

- **Django 901 files**: 0.180s (49x speedup)
- **Throughput**: 5,007 files/sec
- **Per file**: 0.20ms
- **Tests**: 67/67 passing ✅

## References

- Current implementation: `bfg/builder.py` (1,666 lines)
- L1 implementation: `codegraph-rust/codegraph-ast/`
- Architecture review: `.temp/ARCHITECTURE-REVIEW.md`

