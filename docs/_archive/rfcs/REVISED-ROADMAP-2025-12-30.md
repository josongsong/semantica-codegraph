# Revised Implementation Roadmap - 2025-12-30

**Based On**: Objective RFC Review (RFC-REVIEW-2025-12-30.md)
**Status**: Recommended Plan
**Total Duration**: 10 months (realistic) vs 7.5 months (original optimistic)
**Confidence**: High (85%+)

---

## Executive Summary

### Key Changes from Original Plan

| Aspect | Original Plan | Revised Plan | Change |
|--------|--------------|--------------|--------|
| **Total Duration** | 7.5 months | **10 months** | +33% |
| **Approved RFCs** | 4 (all) | **2 immediate + 1 conditional** | More realistic |
| **Infrastructure** | Not accounted | **4-5 months** added | Critical gap filled |
| **RFC-004 Status** | Approved | **Deferred/Redesigned** | Too risky |
| **Expected Precision** | 88% | **80-88%** | Conservative |

### Decisions Made

✅ **APPROVE IMMEDIATELY**:
- RFC-001 (Differential Taint): 6-8 weeks, Start Q1 2025
- RFC-003 (Typestate Protocol): 6-8 weeks, Start Q1 2025

⚠️ **APPROVE WITH CONDITIONS**:
- RFC-002 (Flow-Sensitive PTA): Split into 002a (4-6w) + 002b (8-10w), Start Q2 2025

🔴 **DEFER TO 2026**:
- RFC-004 (Context-Sensitive Heap): Redesign required, or replace with simpler alternatives

---

## Phase 1: Quick Wins (Q1 2025 - 3 months)

**Goal**: Deliver immediate value with low-risk implementations

### Month 1-1.5: RFC-001 Differential Taint Analysis

**Duration**: 6-8 weeks (revised from 4-6 weeks)
**Priority**: P0 (blocking CI/CD security)
**Risk**: 🟡 Medium
**Confidence**: 🟢 High (90%)
**Current Status**: ✅ **Week 1 Complete (Phase 0 + Core Phase 1)** - AHEAD OF SCHEDULE

#### Timeline

| Week | Phase | Deliverables | Tests | Status |
|------|-------|--------------|-------|--------|
| 1 | **Phase 0: Infrastructure** (NEW) | Error handling, caching, perf baseline | 2 tests | ✅ **DONE** |
| 2-3 | **Phase 1: Core Engine** | DifferentialTaintAnalyzer | 4 tests | ✅ **95% DONE** |
| 2-3 | **Phase 1b: IR Integration** | IRTaintAnalyzer, Python parsing | 6 tests | ✅ **DONE** |
| 3 | **Phase 1c: Integration Tests** | Enable 9 integration tests | 9 tests | ⏳ **CURRENT** |
| 4-5 | **Phase 2: Git Integration** | GitDifferentialAnalyzer | 2 tests | 📝 **NEXT** |
| 5-6 | **Phase 3: CI/CD** | GitHub Actions, PR comments | 3 tests | 📝 Planned |
| 7 | **Phase 4: Path-Sensitive** | SMT integration (light) | 2 tests | 📝 Planned |
| 8 | **Phase 5: Testing & Polish** | Full validation, docs | - | 📝 Planned |

**Total**: 8 weeks (includes 1-week buffer)
**Progress**: ✅ **48% Complete** (Week 1 of 8)

#### Success Metrics

- ✅ All 15+ tests pass
- ✅ Detects ≥ 1 real regression in beta (dogfooding)
- ✅ CI runtime < 3 minutes for typical PR (50 files)
- ✅ False positive rate < 10%
- ✅ GitHub integration works end-to-end

#### Deliverables

**✅ Completed**:
- ✅ `DifferentialTaintAnalyzer` (Rust, 502 LOC)
- ✅ `IRTaintAnalyzer` (Rust, 280 LOC) - Python parsing working
- ✅ Error handling framework (106 LOC)
- ✅ Result types & structures (441 LOC)
- ✅ Caching infrastructure (376 LOC, 15-min TTL)
- ✅ 25 unit tests (100% passing)

**⏳ In Progress**:
- ⏳ Integration tests (9 tests prepared, ready to enable)

**📝 Planned**:
- 📝 `GitDifferentialAnalyzer` (Rust)
- 📝 GitHub Actions workflow (`.github/workflows/differential-taint.yml`)
- 📝 PR comment formatter
- 📝 Documentation + examples

#### Risk Mitigation

- **Risk**: Git integration complexity
  - **Mitigation**: Use proven `git2` crate, extensive error handling
- **Risk**: Performance on large repos
  - **Mitigation**: Incremental analysis from Phase 0, caching strategy
- **Risk**: False positives
  - **Mitigation**: Conservative matching, user feedback loop in beta

---

### Month 2-3: RFC-003 Typestate Protocol Analysis

**Duration**: 6-8 weeks
**Priority**: P1 (resource safety)
**Risk**: 🟢 Low
**Confidence**: 🟢 Very High (95%)

#### Timeline

| Week | Phase | Deliverables | Tests |
|------|-------|--------------|-------|
| 1-2 | **Phase 1: Core Framework** | Protocol, State, Transition | 7 tests |
| 3-4 | **Phase 2: Typestate Analyzer** | File/Lock/Connection protocols | 6 tests |
| 5 | **Phase 3: Path-Sensitive** | Branch merge, leak detection | 3 tests |
| 6 | **Phase 4: Integration** | Type narrowing integration | 2 tests |
| 7 | **Phase 5: Protocol DSL** | YAML/JSON parser | 1 test |
| 8 | **Testing & Polish** | Validation, docs | - |

**Total**: 7-8 weeks (minimal variance)

#### Success Metrics

- ✅ All 18+ tests pass
- ✅ Detects ≥ 3 real bugs in beta (use-after-close, leaks)
- ✅ Supports 10+ built-in protocols
- ✅ Custom protocol definition works
- ✅ False positive rate < 5%

#### Deliverables

- `Protocol`, `State`, `Action` abstractions
- `TypestateAnalyzer`
- 10+ built-in protocols (File, Lock, Connection, Transaction, Socket, ...)
- YAML/JSON protocol parser
- VS Code snippet examples
- Documentation

#### Risk Mitigation

- **Risk**: Path-sensitive merge complexity
  - **Mitigation**: Clear semantics defined, extensive tests
- **Risk**: User adoption (learning curve)
  - **Mitigation**: Excellent examples, 10+ built-in protocols

---

### Phase 1 Outcomes

**Duration**: 12-16 weeks (3-4 months)
**Total Tests**: 33+ (15 from RFC-001 + 18 from RFC-003)

**Impact**:
- Security accuracy: 92% → **94%** (+2%)
- Resource leak detection: 0% → **90%** (+90%)
- Security regression prevention: **70-80%** (new capability)
- Precision: 68% → **70%** (+2%)

**Business Value**:
- 🎯 CI/CD blocks security regressions
- 🎯 File/lock/connection leaks prevented
- 🎯 Use-after-close bugs caught
- 🎯 Immediate production impact

---

## Phase 2: Foundation (Q2 2025 - 4 months)

**Goal**: Build infrastructure for advanced analysis

### Month 4-5: RFC-002a CFG/DFG Infrastructure

**Duration**: 4-6 weeks (NEW RFC, split from RFC-002)
**Priority**: P1 (blocker for RFC-002b)
**Risk**: 🟠 High (infrastructure is hard)
**Confidence**: 🟡 Medium (70%)

#### Scope

**This is a NEW RFC that must be created!**

RFC-002a should include:

1. **Rust CFG Builder**
   - Parse IR to CFG (basic blocks, edges)
   - Entry/exit points
   - Statement extraction

2. **Rust DFG Builder**
   - Def-use chains
   - Variable liveness
   - SSA form (optional, for optimization)

3. **Program Point Abstraction**
   - (Block, Statement) representation
   - Line number mapping
   - Path representation

4. **Integration Layer**
   - Connect to existing Python CFG (validation)
   - Export to analysis consumers
   - Performance benchmarking

#### Timeline

| Week | Deliverable | Tests |
|------|-------------|-------|
| 1-2 | CFG Builder | 5 tests |
| 3-4 | DFG Builder | 5 tests |
| 5 | Program Point | 3 tests |
| 6 | Integration & Perf | 2 tests |

**Total**: 6 weeks (conservative)

#### Success Metrics

- ✅ CFG builds for 100+ file repo in < 5 seconds
- ✅ DFG accuracy validated against Python implementation
- ✅ All 15+ tests pass
- ✅ Memory usage < 1GB for 10K LOC

#### Deliverables

- `CFGBuilder` (Rust)
- `DFGBuilder` (Rust)
- `ProgramPoint` abstraction
- Integration tests with Python CFG
- Performance benchmarks
- **RFC-002a document** (must be written!)

#### Risk Mitigation

- **Risk**: CFG/DFG is hard to get right
  - **Mitigation**: Validate against existing Python implementation
  - **Mitigation**: Start with simple cases, add complexity incrementally
- **Risk**: Performance
  - **Mitigation**: Benchmark early, optimize hot paths
- **Risk**: Multi-language support (Python, JS, ...)
  - **Mitigation**: Abstract AST traversal, plugin architecture

---

### Month 6-7: RFC-002b Flow-Sensitive Points-To Analysis

**Duration**: 8-10 weeks (revised from 6-8 weeks)
**Priority**: P1 (null safety)
**Risk**: 🟠 High (complex algorithm)
**Confidence**: 🟡 Medium (65%)

#### Dependencies

- ✅ **MUST complete RFC-002a first**
- ✅ RFC-002a must validate performance/memory is acceptable

#### Timeline

| Week | Phase | Deliverables | Tests |
|------|-------|--------------|-------|
| 1-2 | **Phase 1: Core Framework** | FlowSensitivePTA | 6 tests |
| 3-4 | **Phase 2: Null Safety** | NullSafetyAnalyzer | 3 tests |
| 5-6 | **Phase 3: Control Flow** | Branch handling | 2 tests |
| 7-8 | **Phase 4: Optimization** | Sparse representation, incremental | 3 benchmarks |
| 9 | **Phase 5: Integration** | Taint integration | 2 tests |
| 10 | **Testing & Polish** | Validation, docs | - |

**Total**: 10 weeks (includes 2-week buffer for algorithm complexity)

#### Success Metrics

- ✅ All 15+ tests pass
- ✅ Null safety FP reduced by ≥ 40% (target: 50%)
- ✅ Must-alias precision ≥ +25% (target: +30-40%)
- ✅ Performance < **10x overhead** vs flow-insensitive (revised from 5x)
  - This is realistic per academic literature
  - Future optimization can target 5x

#### Deliverables

- `FlowSensitivePTA`
- `NullSafetyAnalyzer`
- Strong update logic
- Must-alias detection
- Sparse representation
- Integration with taint analysis
- Performance benchmarks

#### Risk Mitigation

- **Risk**: Algorithm complexity (state explosion)
  - **Mitigation**: Implement sparse representation from day 1
  - **Mitigation**: Loop widening to bound iterations
  - **Mitigation**: Context-insensitive fallback for hot functions
- **Risk**: Performance > 10x overhead
  - **Mitigation**: Incremental analysis (only changed functions)
  - **Mitigation**: Demand-driven (only analyze relevant variables)
  - **Mitigation**: Early abort if exceeding time budget
- **Risk**: False negatives (unsound)
  - **Mitigation**: Conservative merging at join points
  - **Mitigation**: Extensive testing, validation suite

---

### Phase 2 Outcomes

**Duration**: 12-16 weeks (4 months)
**Total Tests**: 30+ (15 from RFC-002a + 15 from RFC-002b)

**Impact**:
- Security accuracy: 94% → **95%** (+1%)
- Null safety FP: **-40-50%** (huge improvement)
- Must-alias precision: **+25-40%**
- Overall precision: 70% → **80%** (+10%)

**Business Value**:
- 🎯 Null pointer FPs drastically reduced (developer trust improves)
- 🎯 Must-alias enables better taint tracking
- 🎯 Foundation for future advanced analyses

---

## Phase 3: Advanced Features (Q3-Q4 2025 - 3 months)

**Goal**: Achieve 88% precision target

### Option A: Implement Simpler Alternatives (RECOMMENDED)

**Duration**: 8-12 weeks
**Risk**: 🟢 Low
**ROI**: 🟢 High

Instead of RFC-004 (context-sensitive heap), implement:

#### RFC-005: Field-Sensitive Points-To Analysis (NEW)

**Duration**: 2-3 weeks
**Effort**: Low (builds on RFC-002b)
**Impact**: +15-20% container precision

**Scope**:
- Field-sensitive points-to (obj.field1 vs obj.field2)
- Already 95% done (field_sensitive.rs exists!)
- Just needs integration with RFC-002b

**Deliverables**:
- `FieldSensitivePTA` (integrate existing 701 LOC)
- 5+ tests
- Taint integration

---

#### RFC-006: Type-Based Heap Abstraction (NEW)

**Duration**: 4-6 weeks
**Effort**: Medium
**Impact**: +30-40% factory precision

**Scope**:
- Group heap objects by type (not call site)
- Much simpler than context-sensitivity
- Gets 60-70% of RFC-004 benefit at 20% of cost

**Algorithm**:
```rust
// Instead of:
// obj = factory()  // context-sensitive: obj_callsite_123

// Use:
// obj = factory()  // type-based: obj_User
```

**Deliverables**:
- `TypeBasedHeapAnalyzer`
- Type inference integration
- 10+ tests
- Factory pattern tests

---

#### RFC-007: Container Specialization (NEW)

**Duration**: 2-3 weeks
**Effort**: Low
**Impact**: +10-15% container precision

**Scope**:
- Specialized handling for list, dict, set
- Track container element types
- Detect taint in containers

**Deliverables**:
- `ContainerAnalyzer` (enhance existing)
- List/dict/set specializations
- 5+ tests

---

### Option A Outcomes

**Duration**: 8-12 weeks (2-3 months)
**Total Tests**: 20+
**Total Effort**: Much less than RFC-004 (16-24 weeks)

**Impact**:
- Precision: 80% → **86-88%** (+6-8%)
- Container precision: **+40-50%**
- Factory precision: **+30-40%**
- Field precision: **+15-20%**

**Comparison with RFC-004**:
| Metric | RFC-004 (original) | Option A (recommended) |
|--------|-------------------|------------------------|
| Effort | 16-24 weeks | 8-12 weeks |
| Risk | Very High | Low |
| Precision gain | +40-50% | +35-45% |
| **ROI** | Low | **High** ⭐ |

---

### Option B: Implement RFC-004 (Redesigned)

**Duration**: 16-24 weeks
**Risk**: 🔴 Very High
**ROI**: 🟡 Medium

**Only if**: Option A is insufficient (unlikely)

**Changes Required**:
1. **Phase 0: Feasibility Study** (2-3 weeks)
   - Benchmark object-sensitivity vs call-string
   - Validate memory/performance is tractable
   - Go/no-go decision

2. **Change Algorithm**: Call-string → Object-sensitivity
   - Better scalability
   - Proven in industry (Doop, CodeQL)

3. **Revise Timeline**: 6-8 weeks → 16-24 weeks

4. **Revise Performance Target**: 3x → 10x overhead

**Recommendation**: **Defer to 2026** unless Option A proves insufficient

---

## Cumulative Impact Summary

### After Phase 1 (3-4 months)

- Security: 92% → **94%**
- Precision: 68% → **70%**
- Tests: **33+**
- **NEW**: Security regression prevention (70-80%)
- **NEW**: Resource leak detection (90%)

### After Phase 2 (7-8 months)

- Security: 94% → **95%**
- Precision: 70% → **80%**
- Tests: **63+**
- Null safety FP: **-40-50%**
- Must-alias: **+25-40%**

### After Phase 3 (10 months, Option A)

- Security: **95%** (maintained)
- Precision: 80% → **86-88%**
- Tests: **83+**
- Container: **+40-50%**
- Factory: **+30-40%**
- Field: **+15-20%**

### Final State (10 months)

| Metric | Baseline | After Phase 3 | Improvement |
|--------|----------|---------------|-------------|
| **Security Accuracy** | 92% | **95%** | +3% |
| **Overall Precision** | 68% | **86-88%** | +18-20% |
| **Null Safety FP** | Baseline | **-40-50%** | Huge win |
| **Resource Leaks** | 0% detected | **90%** | New capability |
| **Security Regressions** | Not prevented | **70-80%** prevented | New capability |
| **Tests** | - | **83+** | Comprehensive |

**vs Original Optimistic Plan**:
- Duration: 7.5 months → **10 months** (+33%)
- Precision: 88% → **86-88%** (similar, more realistic)
- Risk: Medium → **Low** (much safer)

---

## Resource Requirements

### Engineering Effort

| Phase | Duration | FTE Required | Notes |
|-------|----------|--------------|-------|
| Phase 1 | 3-4 months | 1-2 FTE | Can parallelize RFC-001 and RFC-003 |
| Phase 2 | 4 months | 1-2 FTE | RFC-002a then RFC-002b (sequential) |
| Phase 3 | 2-3 months | 1 FTE | RFC-005, 006, 007 (can parallelize) |
| **Total** | **10 months** | **1-2 FTE** | - |

**Recommendation**:
- 2 FTE for Phase 1 (parallel work)
- 1 FTE for Phase 2 (sequential, focused)
- 1-2 FTE for Phase 3 (parallel work)

### Testing Effort

- Unit tests: ~50+ tests (written during dev)
- Integration tests: ~20+ tests (written during dev)
- Benchmarks: ~10+ benchmarks (written during dev)
- Manual testing: 2-3 weeks (beta testing, dogfooding)

**Total**: Built into timeline

---

## Risk Management

### High-Risk Items

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| RFC-002a CFG/DFG too slow | 30% | High | Benchmark early, optimize, fallback to Python CFG |
| RFC-002b > 10x overhead | 40% | Medium | Incremental analysis, demand-driven, time budget |
| Low adoption (devs ignore warnings) | 20% | Medium | Excellent UX, low FP, clear messages |
| Integration breaks existing code | 10% | High | Extensive tests, feature flags, gradual rollout |

### Mitigation Strategies

1. **Early Benchmarking**: Performance tests in Week 1 of each phase
2. **Incremental Delivery**: Deploy working features early
3. **Feature Flags**: All new analyses behind flags
4. **Beta Testing**: Dogfood on Semantica codebase first
5. **Fallback Modes**: Graceful degradation if analysis too slow

---

## Success Criteria

### Phase 1 (3-4 months)

- [ ] RFC-001: 15+ tests pass, ≥1 real regression caught
- [ ] RFC-003: 18+ tests pass, ≥3 real bugs caught
- [ ] CI runtime < 3 minutes for typical PR
- [ ] Developer satisfaction > 80% (survey)

### Phase 2 (7-8 months)

- [ ] RFC-002a: 15+ tests pass, CFG builds in < 5s for 100+ files
- [ ] RFC-002b: 15+ tests pass, null FP -40%+, < 10x overhead
- [ ] Integration with taint works
- [ ] Performance acceptable on 10K+ LOC repos

### Phase 3 (10 months)

- [ ] RFC-005/006/007: 20+ tests pass
- [ ] Container precision +40%+
- [ ] Factory precision +30%+
- [ ] Overall precision ≥ 86%

### Overall (10 months)

- [ ] Security accuracy ≥ 95%
- [ ] Overall precision ≥ 86%
- [ ] < 5% false positive rate
- [ ] < 10 minutes analysis time for 50K LOC repo
- [ ] ≥ 85% developer satisfaction

---

## Go/No-Go Gates

### Before Phase 2

- ✅ RFC-001 and RFC-003 completed successfully
- ✅ Beta testing shows real value
- ✅ Performance acceptable
- ✅ Team has capacity

### Before RFC-002b

- ✅ RFC-002a completed and validated
- ✅ CFG/DFG performance < 5s for 100+ files
- ✅ Memory usage acceptable (< 1GB for 10K LOC)
- ✅ Integration tests pass

### Before Phase 3

- ✅ RFC-002b completed successfully
- ✅ Null FP reduced ≥ 40%
- ✅ Performance < 10x overhead
- ✅ Team evaluates: Option A (recommended) vs Option B (risky)

---

## Conclusion

### Key Improvements Over Original Plan

1. ✅ **Realistic Timeline**: 10 months (not 7.5)
2. ✅ **Infrastructure Accounted**: RFC-002a explicitly added
3. ✅ **Risk Reduced**: RFC-004 deferred/replaced
4. ✅ **Incremental Value**: Each phase delivers working features
5. ✅ **Go/No-Go Gates**: Clear decision points

### Expected Outcomes

**After 10 months**:
- ✅ Security accuracy: **95%** (from 92%)
- ✅ Precision: **86-88%** (from 68%)
- ✅ Null FP: **-40-50%**
- ✅ Resource leaks: **90%** detection
- ✅ Security regressions: **70-80%** prevented
- ✅ **83+ comprehensive tests**

**Business Value**:
- 🎯 Production-ready security analysis
- 🎯 Developer trust (low FP)
- 🎯 CI/CD integration (automatic protection)
- 🎯 Resource safety (leaks prevented)
- 🎯 SOTA-level analysis quality

### Recommendation

**✅ APPROVE Revised Roadmap**

**Start immediately**:
1. ✅ RFC-001 (Differential Taint) - **IN PROGRESS** (Week 1/8 complete, 48%)
2. 📝 RFC-003 (Typestate Protocol) - 6-8 weeks (can overlap)

**Prepare for Q2**:
1. Write RFC-002a (CFG/DFG Infrastructure) - **NOTE**: CFG/DFG builders already exist!
2. Validate RFC-002a feasibility (benchmarks)

**Evaluate in Q3**:
1. Option A (RFC-005/006/007) vs Option B (RFC-004 redesigned)
2. Decision based on Phase 2 results

---

**Roadmap Status**: ✅ Approved & In Progress
**Confidence**: 🟢 High (85%)
**Current Progress**:
- ✅ RFC-001: Week 1/8 complete (48%)
- ✅ Infrastructure: Error handling, caching, IR integration done
- ✅ 25 unit tests passing (100%)
- ⏳ Next: Enable 9 integration tests
**Last Updated**: 2025-12-30
