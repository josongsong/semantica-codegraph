# Graph Builder 최적화 제안

## 문제 분석

현재 Graph Layer가 전체 인덱싱 시간의 **81.4% (1,859ms)** 를 차지하는 주요 병목입니다.

### 병목 지점

1. **Request Flow Index**: O(n³) 중첩 루프
2. **Index Building**: 중복 순회 (3회)
3. **Node Filtering**: nodes_by_kind 인덱스 부재

## 최적화 전략

### 1. Request Flow Index - Adjacency List 활용

**Before (O(n³))**:
```python
for route_node in route_nodes:
    for edge in graph.graph_edges:  # O(n)
        for service_edge in graph.graph_edges:  # O(n)
            for repo_edge in graph.graph_edges:  # O(n)
```

**After (O(n))**:
```python
# 미리 adjacency list 구축
edges_by_source: dict[str, list[GraphEdge]] = defaultdict(list)
for edge in graph.graph_edges:
    edges_by_source[edge.source_id].append(edge)

# O(1) lookup으로 변경
for route_node in route_nodes:
    for edge in edges_by_source[route_node.id]:  # O(1)
        if edge.kind == GraphEdgeKind.ROUTE_HANDLER:
            handler_id = edge.target_id
            for service_edge in edges_by_source[handler_id]:  # O(1)
                if service_edge.kind == GraphEdgeKind.HANDLES_REQUEST:
                    # ...
```

**예상 개선**: 11,084³ → 11,084회 = **~99.9% 감소**

### 2. Index Building - Single Pass

**Before (3회 순회)**:
```python
# Pass 1: Group by kind
for edge in graph.graph_edges:
    edges_by_kind[edge.kind].append(edge)

# Pass 2: Build adjacency
for edge in graph.graph_edges:
    outgoing[edge.source_id].append(edge.id)
    incoming[edge.target_id].append(edge.id)

# Pass 3: Build reverse indexes
for edge in edges_by_kind[GraphEdgeKind.CALLS]:
    called_by[edge.target_id].append(edge.source_id)
```

**After (1회 순회)**:
```python
# Single pass - build all indexes simultaneously
for edge in graph.graph_edges:
    # Adjacency indexes
    outgoing[edge.source_id].append(edge.id)
    incoming[edge.target_id].append(edge.id)

    # Reverse indexes by kind (switch-case)
    if edge.kind == GraphEdgeKind.CALLS:
        called_by[edge.target_id].append(edge.source_id)
    elif edge.kind == GraphEdgeKind.IMPORTS:
        imported_by[edge.target_id].append(edge.source_id)
    elif edge.kind == GraphEdgeKind.CONTAINS:
        contains_children[edge.source_id].append(edge.target_id)
    # ... (continue for all kinds)
```

**예상 개선**: 3 × 11,084 → 11,084회 = **~67% 감소**

### 3. nodes_by_kind Index

**Before**:
```python
# 매번 전체 순회
for node in graph.graph_nodes.values():
    if node.kind == GraphNodeKind.ROUTE:
        # ...
```

**After**:
```python
# 초기 구축 시 nodes_by_kind 생성
nodes_by_kind: dict[GraphNodeKind, list[str]] = defaultdict(list)
for node_id, node in graph.graph_nodes.items():
    nodes_by_kind[node.kind].append(node_id)

# O(1) lookup
route_nodes = [graph.graph_nodes[nid] for nid in nodes_by_kind[GraphNodeKind.ROUTE]]
```

**예상 개선**: 8,908 × 3회 → 8,908회 = **~67% 감소**

## 예상 성능 개선

### 현재 (211 files, 8,908 nodes, 11,084 edges)
- **Graph Layer**: 1,859ms (81.4%)
- **Total**: 2,283ms

### 최적화 후 예상
| 구분 | Before | After | 개선율 |
|------|--------|-------|--------|
| Request Flow Index | ~1,200ms | ~12ms | **99%** |
| Index Building | ~500ms | ~150ms | **70%** |
| Node Filtering | ~100ms | ~30ms | **70%** |
| **Total Graph** | **1,859ms** | **~250ms** | **87%** |

**전체 파이프라인**: 2,283ms → ~680ms = **~70% 개선** 예상

## 구현 우선순위

1. **High**: Request Flow Index 최적화 (가장 큰 영향)
2. **Medium**: Index Building Single Pass
3. **Low**: nodes_by_kind Index (구조 변경 필요)

## 다음 단계

1. 세부 프로파일링으로 정확한 병목 측정
2. Request Flow Index 최적화 구현
3. 벤치마크로 실제 개선 효과 측정
