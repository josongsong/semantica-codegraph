# Taint Analysis DFG Requirement

## Problem

Taint Analysis가 Sources와 Sinks를 탐지하지만 Vulnerabilities는 0개를 보고하는 현상.

## Root Cause

**IR 빌드 시 `enable_semantic_ir=True`가 필수입니다.**

### 문제의 Flow (DFG 없음)
```
1. IR 빌드 (enable_semantic_ir=False)
   └─ dfg_snapshot = None

2. EdgeIndex._build(ir_doc)
   └─ DFG edges = 0 (dfg_snapshot이 None이므로)

3. Path Finding: input() → execute()
   └─ 경로 없음 (DFG edges가 없어서)

4. Vulnerabilities = 0
```

### 정상 Flow (DFG 있음)
```
1. IR 빌드 (enable_semantic_ir=True, semantic_mode="full")
   └─ dfg_snapshot 생성 (14 variables, 7 DFG edges)

2. EdgeIndex._build(ir_doc)
   └─ DFG edges = 113 (Expression→Variable, Variable→Variable 등)

3. Path Finding: input() → execute()
   └─ 30개 경로 발견!
      Path: expr:input → var:user_input → expr:execute

4. Vulnerabilities 탐지됨! ✅
```

## Solution

IR 빌드 시 Semantic IR을 활성화해야 합니다:

```python
from src.contexts.code_foundation.infrastructure.ir.layered_ir_builder import (
    LayeredIRBuilder,
    LayeredIRConfig,
)

builder = LayeredIRBuilder(project_root)

result = await builder.build_full(
    files=[test_file],
    enable_semantic_ir=True,   # ⭐ REQUIRED for Taint Analysis
    semantic_mode="full",      # ⭐ "full" mode generates DFG
)

ir_docs, global_ctx, retrieval_index, diag_idx, pkg_idx = result
```

## Technical Details

### EdgeIndex에서 DFG Edges 빌드

[edge_index.py:67-89](src/contexts/code_foundation/infrastructure/query/indexes/edge_index.py#L67-L89)

```python
def _build(self, ir_doc: "IRDocument") -> None:
    # 1. DFG edges (dfg_snapshot 필수!)
    if ir_doc.dfg_snapshot:  # ⭐ dfg_snapshot이 None이면 DFG edges = 0
        for edge in ir_doc.dfg_snapshot.edges:
            unified = UnifiedEdge(
                from_node=edge.from_variable_id,
                to_node=edge.to_variable_id,
                edge_type=EdgeType.DFG,
            )
            self._add_edge(unified, EdgeType.DFG)
```

### LayeredIRBuilder Layer 5: Semantic IR

[layered_ir_builder.py:291-322](src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py#L291-L322)

```python
# Layer 5: Semantic IR (CFG/DFG) ⭐ v2.1 [OPTIONAL]
if enable_semantic_ir:
    semantic_builder = DefaultSemanticIrBuilder()
    build_mode = SemanticIrBuildMode.QUICK if semantic_mode == "quick" else SemanticIrBuildMode.FULL

    for file_path, ir_doc in structural_irs.items():
        snapshot, index = semantic_builder.build_full(ir_doc, source_map, mode=build_mode)
        ir_doc.dfg_snapshot = snapshot.dfg_snapshot  # ⭐ DFG 저장
```

## Verification

검증 테스트: [_temp_test/debug_dfg_snapshot.py](_temp_test/debug_dfg_snapshot.py)

```
============================================================
Checking dfg_snapshot
============================================================
File: /tmp/dfg_test/vuln.py
  dfg_snapshot: True
  DFG variables: 14
  DFG edges: 7

============================================================
EdgeIndex stats
============================================================
  Total edges: 127
  DFG edges: 113
  ✅ DFG edges present!

============================================================
Testing Path Finding
============================================================
Sources (input): 1
Sinks (execute): 3
PathSet found: 30 paths
  ✅ PATH FOUND! Taint Analysis works correctly!
  Path 1: expr:input → var:user_input → expr:execute
```

## Configuration Summary

| Setting | Value | Description |
|---------|-------|-------------|
| `enable_semantic_ir` | `True` | **필수** - DFG 생성에 필요 |
| `semantic_mode` | `"full"` | DFG 생성 (814x 느리지만 필수) |
| `semantic_mode` | `"quick"` | Signature만 (DFG 없음, Taint 불가) |

## Key Insight

> **Taint Analysis는 DFG (Data Flow Graph)를 통해 source → sink 경로를 찾습니다.**
> DFG가 없으면 경로를 찾을 수 없어 Vulnerabilities = 0이 됩니다.
