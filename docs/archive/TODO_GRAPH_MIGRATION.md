# TODO: GraphIndex Migration

## Current Status

**PyGraphIndex is working but using deprecated GraphIndex**

- ✅ PyGraphIndex implemented and tested (229x speedup)
- ✅ query_engine.GraphIndex marked as DEPRECATED
- ⏳ Waiting for graph_builder to be completed
- ⏳ Migration planned but blocked

---

## The Problem

### We have TWO GraphIndex implementations:

1. **query_engine.GraphIndex (현재 사용 중)** ❌
   - 위치: `features/query_engine/infrastructure/graph_index.rs`
   - 상태: DEPRECATED
   - 문제점:
     - std::HashMap (느림)
     - String interning 없음 (메모리 낭비)
     - 기본 기능만
   - 성능:
     - Build: 800ms
     - Memory: 높음

2. **graph_builder.GraphIndex (SOTA 버전)** ✅
   - 위치: `features/graph_builder/domain/mod.rs`
   - 상태: Work in progress
   - 장점:
     - AHashMap (2-3x faster)
     - String interning (50% 메모리 절감)
     - EdgeKind별 인덱스
     - Framework awareness
   - 예상 성능:
     - Build: ~500ms (37% faster)
     - Memory: 50% reduction

---

## Why Not Migrate Now?

**graph_builder is still being developed**

현재 graph_builder가 작업 중이므로:
- API가 변경될 수 있음
- 완성도 확인 필요
- 통합 테스트 필요

따라서 **일단 deprecated 버전을 그대로 사용**하고 나중에 마이그레이션 예정

---

## Migration Checklist (나중에)

### Phase 1: Preparation
- [ ] graph_builder 완성 확인
- [ ] graph_builder API 문서화
- [ ] graph_builder 단독 테스트

### Phase 2: Code Changes
- [ ] `query.rs`: Import 변경
  ```rust
  // use crate::features::query_engine::infrastructure::GraphIndex;
  use crate::features::graph_builder::domain::GraphIndex;
  ```
- [ ] `build_graph_index_from_result()`: GraphDocument 사용
- [ ] `matches_filter()`: InternedString 지원
- [ ] Serialization: GraphNode/GraphEdge → msgpack

### Phase 3: Testing
- [ ] Rust 빌드 성공
- [ ] PyGraphIndex import 성공
- [ ] Performance test 통과 (229x speedup 유지)
- [ ] 새 성능 측정 (500ms 빌드 확인)

### Phase 4: Cleanup
- [ ] `query_engine/infrastructure/graph_index.rs` 삭제
- [ ] DEPRECATED 주석 제거
- [ ] 문서 업데이트

---

## Expected Benefits

### Performance
```
Build time:  800ms → 500ms  (37% faster)
Memory:      100MB → 50MB   (50% reduction)
Query time:  3ms → 2ms      (similar or better)
```

### Features
```
✅ EdgeKind별 필터링 (O(1))
✅ Framework queries (routes, services)
✅ Reverse indexes (called_by, imported_by)
✅ Request flow tracking
```

---

## Files Modified (for migration)

### Will Change
1. `adapters/pyo3/api/query.rs`
   - Import statements
   - `build_graph_index_from_result()`
   - `matches_filter()` (maybe)

### Will Delete
1. `features/query_engine/infrastructure/graph_index.rs`
   - Entire file (deprecated)

### Won't Change
1. Python API (backward compatible)
2. PyGraphIndex interface
3. Test scripts

---

## Risk Assessment

### Low Risk
- ✅ Can rollback easily (just change import)
- ✅ Python API stays the same
- ✅ Deprecated version available as fallback

### Medium Risk
- ⚠️ API differences (InternedString vs String)
- ⚠️ Serialization changes (GraphNode vs Node)
- ⚠️ Need thorough testing

### Mitigation
- Keep deprecated code until migration proven
- Test in isolation first
- Document all API changes

---

## Current Workaround

**임시로 deprecated 버전 사용:**

```rust
// query.rs (current)
use crate::features::query_engine::infrastructure::GraphIndex;  // ← deprecated but works

#[pyclass]
pub struct PyGraphIndex {
    index: GraphIndex,  // ← using deprecated version temporarily
}
```

**이유:**
1. graph_builder 작업 중
2. API 변경 가능성
3. 완성도 확인 필요

**언제 바꿀지:**
- graph_builder 완성 후
- API 안정화 후
- 통합 테스트 후

---

## Action Items

### For Now
- ✅ Keep using deprecated GraphIndex
- ✅ Mark as DEPRECATED with TODO comments
- ✅ Document migration plan

### For Later (when graph_builder ready)
1. Review graph_builder API
2. Update PyGraphIndex to use graph_builder.GraphIndex
3. Test thoroughly
4. Measure performance improvements
5. Delete deprecated code

---

## Related Files

- [GRAPH_ARCHITECTURE_PROBLEM.md](GRAPH_ARCHITECTURE_PROBLEM.md) - 문제 분석
- [MIGRATION_TO_GRAPH_BUILDER.md](MIGRATION_TO_GRAPH_BUILDER.md) - 마이그레이션 가이드
- [PYGRAPHINDEX_SUMMARY.md](PYGRAPHINDEX_SUMMARY.md) - PyGraphIndex 동작 원리

---

## Notes

**Why this approach is correct:**

1. ✅ PyGraphIndex는 이미 229x speedup 달성 (동작함)
2. ✅ Deprecated 버전으로도 충분히 빠름 (800ms build, 3ms query)
3. ✅ graph_builder 완성되면 마이그레이션으로 추가 30-50% 개선
4. ✅ 리스크 낮음 (롤백 쉬움)

**graph_builder가 완성되면:**
- 50% 메모리 절감
- 37% 빠른 빌드
- 새로운 기능들 (EdgeKind 필터링, framework queries)
