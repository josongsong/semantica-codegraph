# Next Actions - 2025-12-30

**Based On**: REVISED-ROADMAP-2025-12-30.md, RFC-001-IMPLEMENTATION-STATUS.md
**Current Status**: RFC-001 Week 1 Complete (48% done)
**Updated**: 2025-12-30

---

## Executive Summary

### Current Progress

✅ **Completed (Week 1)**:
- Phase 0: Infrastructure (error handling, caching, perf baseline)
- Phase 1 Core: DifferentialTaintAnalyzer (95% done)
- Phase 1b: IR Integration (IRTaintAnalyzer, Python parsing working)
- 25 unit tests (100% passing)
- 1,774 LOC across 6 new files

⏳ **Current Week (Week 2-3)**:
- Phase 1c: Enable 9 integration tests
- Complete remaining Phase 1 work

📝 **Upcoming (Week 4-5)**:
- Phase 2: Git Integration (GitDifferentialAnalyzer)

---

## Immediate Next Actions (Priority Order)

### 🔥 P0: Integration Test Activation (1-2 days)

**Goal**: Enable and validate 9 prepared integration tests

**File**: `tests/integration/test_differential_taint_basic.rs` (211 LOC)

**Tasks**:
1. ✅ Enable all 9 integration tests (remove placeholders)
2. ✅ Add real Python code examples for each test case
3. ✅ Validate against RFC Test Suite 1 specifications
4. ✅ Ensure 100% pass rate

**Test Coverage**:
- ✅ Test 1.1: Detect new taint flow
- ✅ Test 1.2: Detect removed sanitizer
- ✅ Test 1.3: No false positive on safe refactoring
- ✅ Test 1.4: Detect bypass path
- ✅ Performance: Empty diff < 1s
- ✅ Cache: Hit rate tracking works
- ✅ Time budget: Respected (3 min default)
- ✅ Configuration: All options work

**Expected Outcome**:
- 9 integration tests passing (100%)
- Real Python code examples demonstrating each scenario
- RFC-001 compliance validated

**Risk**: 🟢 Low (infrastructure already working)

---

### 🟢 P1: Git Integration (Week 4-5, 2 weeks)

**Goal**: Implement `GitDifferentialAnalyzer` for commit comparison

**New File**: `packages/codegraph-ir/src/features/taint_analysis/infrastructure/differential/git_integration.rs` (~400 LOC)

**Dependencies**:
- `git2` crate (proven library)
- Existing `DifferentialTaintAnalyzer`
- Existing `IRTaintAnalyzer`

**Tasks**:
1. **Git Operations** (Week 4, Day 1-2)
   - Parse commit SHA
   - Extract file diffs (added, modified, deleted)
   - Read file content at specific commits
   - Error handling for git operations

2. **Differential Analysis** (Week 4, Day 3-4)
   - Analyze base commit (version A)
   - Analyze modified commit (version B)
   - Compare results using `DifferentialTaintAnalyzer`
   - Aggregate vulnerabilities across all changed files

3. **Performance Optimization** (Week 4, Day 5)
   - Incremental analysis (only changed files)
   - Cache integration (reuse base analysis)
   - Parallel processing (per-file analysis)

4. **Testing** (Week 5, Day 1-2)
   - 5+ unit tests (git operations, diff parsing)
   - 3+ integration tests (real git repos)
   - Performance benchmarks (50 files < 3 min)

**Deliverables**:
```rust
pub struct GitDifferentialAnalyzer {
    analyzer: DifferentialTaintAnalyzer,
    cache: Arc<AnalysisCache>,
    config: GitConfig,
}

impl GitDifferentialAnalyzer {
    pub fn compare_commits(
        &self,
        repo_path: &Path,
        base_commit: &str,
        modified_commit: &str,
    ) -> DifferentialResult<DifferentialTaintResult>;

    pub fn compare_branches(
        &self,
        repo_path: &Path,
        base_branch: &str,
        modified_branch: &str,
    ) -> DifferentialResult<DifferentialTaintResult>;
}
```

**Expected Outcome**:
- `GitDifferentialAnalyzer` working (400 LOC)
- 8+ tests passing
- < 3 minutes for typical PR (50 files)
- RFC-001 Phase 2 complete

**Risk**: 🟡 Medium (git2 crate complexity, but proven library)

---

### 🟡 P2: CI/CD Integration (Week 5-6, 1-2 weeks)

**Goal**: GitHub Actions integration with PR comments

**New Files**:
1. `.github/workflows/differential-taint.yml` (~80 LOC)
2. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/differential/pr_formatter.rs` (~200 LOC)

**Tasks**:
1. **GitHub Actions Workflow** (Week 5, Day 3-4)
   - Trigger on pull_request
   - Checkout base and head commits
   - Run `GitDifferentialAnalyzer`
   - Generate report

2. **PR Comment Formatter** (Week 5, Day 5)
   - Format vulnerabilities as markdown
   - Add severity badges (🔴 Critical, 🟠 High, etc.)
   - Include code snippets with line numbers
   - Add summary statistics

3. **GitHub Integration** (Week 6, Day 1-2)
   - Post PR comment via GitHub API
   - Update check run status (✅ pass / ❌ fail)
   - Handle errors gracefully

4. **Testing** (Week 6, Day 3)
   - Test on real PR (dogfooding)
   - Validate comment formatting
   - Ensure < 3 min runtime

**Deliverables**:
- GitHub Actions workflow
- PR comment formatter
- End-to-end CI/CD working
- RFC-001 Phase 3 complete

**Expected Outcome**:
- Automatic security regression detection on PRs
- Clear, actionable PR comments
- < 3 minutes CI runtime
- 70-80% regression prevention

**Risk**: 🟢 Low (standard GitHub Actions patterns)

---

## Alternative: Parallel Work on RFC-003

If RFC-001 integration tests are blocked or waiting for review, consider starting RFC-003 in parallel.

### RFC-003: Typestate Protocol Analysis (6-8 weeks)

**Status**: Not started (can overlap with RFC-001)
**Priority**: P1 (resource safety)
**Risk**: 🟢 Low
**Confidence**: 🟢 Very High (95%)

**Week 1-2 Tasks** (if starting now):
1. **Core Framework** (Week 1)
   - `Protocol` trait
   - `State` enum
   - `Transition` struct
   - `Action` enum (Open, Close, Read, Write, etc.)

2. **Built-in Protocols** (Week 2)
   - `FileProtocol` (open → read/write → close)
   - `LockProtocol` (acquire → hold → release)
   - `ConnectionProtocol` (connect → send/recv → disconnect)

**Deliverables** (Week 1-2):
- Protocol framework (300 LOC)
- 3 built-in protocols (200 LOC)
- 7+ tests
- RFC-003 Phase 1 complete (35%)

**Risk**: 🟢 Low (simple state machine, well-defined)

---

## Decision Matrix

### Option A: Focus on RFC-001 (Recommended)

**Pros**:
- ✅ Finish Phase 1 completely (integration tests)
- ✅ Move to Phase 2 (Git integration) immediately
- ✅ Complete RFC-001 in 6-8 weeks as planned
- ✅ Deliver immediate CI/CD value

**Cons**:
- ⏳ RFC-003 delayed by 1-2 weeks

**Timeline**:
- Week 2-3: Integration tests + Git integration start
- Week 4-5: Git integration complete
- Week 5-6: CI/CD integration
- Week 7-8: Testing, polish, docs
- **Total**: 8 weeks (RFC-001 complete)

---

### Option B: Parallel RFC-001 + RFC-003

**Pros**:
- ✅ Faster overall progress (2 RFCs in parallel)
- ✅ Can leverage existing infrastructure for both
- ✅ Phase 1 outcome achieved faster (3-4 months → 2.5-3 months)

**Cons**:
- ⚠️ Requires 2 FTE (or context switching)
- ⚠️ Risk of incomplete work if team capacity limited
- ⚠️ Harder to maintain focus

**Timeline** (2 FTE):
- Week 2-3: RFC-001 integration tests + RFC-003 Phase 1
- Week 4-5: RFC-001 Git integration + RFC-003 Phase 2
- Week 6-7: RFC-001 CI/CD + RFC-003 Phase 3
- Week 8-10: RFC-001 polish + RFC-003 completion
- **Total**: 10 weeks (both RFCs complete)

---

## Recommendation

### ✅ **Option A: Focus on RFC-001** (1 FTE)

**Rationale**:
1. ✅ RFC-001 is 48% complete (Week 1/8)
2. ✅ Infrastructure already working (Python parsing end-to-end)
3. ✅ Git integration is next logical step
4. ✅ CI/CD integration delivers immediate business value
5. ✅ Finish one RFC completely before starting another (reduce risk)

**Next Immediate Steps** (this week):
1. 🔥 **P0**: Enable 9 integration tests (1-2 days)
2. 🟢 **P1**: Start Git integration (Week 4-5)
3. 📝 **P2**: Plan CI/CD integration (Week 5-6)

**Go/No-Go Gate** (after Week 3):
- ✅ All 9 integration tests passing?
- ✅ Git integration design reviewed?
- ✅ Team capacity confirmed for Week 4-5?
- ✅ Performance acceptable (< 3 min for 50 files)?

---

## Key Milestones

### Short-term (2 weeks)
- ✅ Week 2: Integration tests enabled (9 tests passing)
- ✅ Week 3: Git integration started (basic git ops working)

### Medium-term (4-6 weeks)
- ✅ Week 4-5: Git integration complete (`GitDifferentialAnalyzer` working)
- ✅ Week 5-6: CI/CD integration (GitHub Actions working)

### Long-term (6-8 weeks)
- ✅ Week 7: Testing & polish (RFC Test Suite 1 validated)
- ✅ Week 8: Documentation & examples (RFC-001 complete)

---

## Success Criteria

**By Week 3** (Integration Tests):
- [ ] 9 integration tests passing (100%)
- [ ] Real Python code examples for each test case
- [ ] RFC-001 compliance validated
- [ ] Performance: Empty diff < 1s

**By Week 5** (Git Integration):
- [ ] `GitDifferentialAnalyzer` working (400 LOC)
- [ ] 8+ tests passing
- [ ] < 3 minutes for typical PR (50 files)
- [ ] Cache hit rate > 50%

**By Week 8** (RFC-001 Complete):
- [ ] All 15+ tests passing (unit + integration)
- [ ] GitHub Actions workflow working
- [ ] PR comments formatted correctly
- [ ] ≥1 real regression caught in beta (dogfooding)
- [ ] Developer satisfaction > 80%

---

## Risk Assessment

### Low Risk ✅
- Integration tests (infrastructure already working)
- Git integration (git2 crate proven)
- CI/CD integration (standard patterns)

### Medium Risk ⚠️
- Performance at scale (50+ files)
  - **Mitigation**: Caching, incremental analysis, time budget
- False positive rate
  - **Mitigation**: Conservative matching, user feedback loop

### High Risk 🔴
- None identified (Phase 0 infrastructure de-risked everything)

---

## Resources Required

**Engineering Effort**:
- 1 FTE for RFC-001 (Weeks 2-8)
- Optional: 1 FTE for RFC-003 (Weeks 2-10, parallel work)

**External Dependencies**:
- `git2` crate (already in Cargo.toml)
- GitHub Actions (free for public repos)
- No new infrastructure required

---

## Conclusion

**Status**: ✅ RFC-001 Week 1 Complete (48% done, AHEAD OF SCHEDULE)

**Next Immediate Action**:
1. 🔥 **Enable 9 integration tests** (1-2 days)
2. 🟢 **Start Git integration** (Week 4-5)

**Recommendation**: **Focus on RFC-001 completion** (Option A)

**Go/No-Go Decision Point**: After Week 3 (integration tests complete)

---

**Last Updated**: 2025-12-30
**Status**: Ready for Team Review
