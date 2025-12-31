# RFC-002: Flow-Sensitive Points-To Analysis

**Status**: Draft
**Priority**: P1 (6 months)
**Effort**: 6-8 weeks
**Authors**: Semantica Team
**Created**: 2025-12-30
**Target Version**: v2.2.0

---

## Executive Summary

Implement **flow-sensitive points-to analysis** with strong update and must-alias support to dramatically improve null safety and pointer precision.

**Current State**: 30% implemented - Only flow-insensitive algorithms (Steensgaard, Andersen)
**Gap**: No flow-sensitive analysis, no strong update, no must-alias
**Impact**: +30-40% must-alias precision, critical for null safety and concurrency analysis

---

## Motivation

### Problem Statement

**Current Flow-Insensitive Analysis** (Andersen):
```python
p = [1, 2, 3]  # p → obj1
p = [4, 5, 6]  # p → {obj1, obj2} (weak update!)
return p[0]    # May be 1 or 4 (imprecise!)

# Null check doesn't help
data = get_user()
if data is None:
    return
# Here: Flow-insensitive thinks data may still be None!
access(data.field)  # FALSE POSITIVE: NullPointerException
```

**Flow-Sensitive Analysis** (Target):
```python
p = [1, 2, 3]  # p → obj1
p = [4, 5, 6]  # p → obj2 (strong update!)
return p[0]    # Must be 4 (precise!)

# Null check works correctly
data = get_user()
if data is None:
    return
# Here: Flow-sensitive knows data != None
access(data.field)  # NO FALSE POSITIVE ✅
```

---

## Test-Driven Specification

### Test Suite 1: Strong Update (Unit Tests)

**File**: `packages/codegraph-ir/tests/points_to/test_strong_update.rs`

#### Test 1.1: Basic Strong Update
```rust
#[test]
fn test_basic_strong_update() {
    let mut analyzer = FlowSensitivePTA::new();

    // p = new A()
    analyzer.add_alloc(var(1), loc(100));

    // p = new B() (reassignment)
    analyzer.add_alloc(var(1), loc(200));

    let result = analyzer.solve();

    // After strong update, p should ONLY point to B
    assert_eq!(result.points_to_size(var(1)), 1);
    assert!(result.points_to(var(1)).contains(&loc(200)));
    assert!(!result.points_to(var(1)).contains(&loc(100))); // Old binding removed!
}
```

#### Test 1.2: Strong Update Requires Must-Alias
```rust
#[test]
fn test_strong_update_requires_must_alias() {
    let mut analyzer = FlowSensitivePTA::new();

    // x = new A()
    analyzer.add_alloc(var(1), loc(100));

    // y = x  (may-alias)
    analyzer.add_copy(var(2), var(1));

    // x = new B()
    analyzer.add_alloc(var(1), loc(200));

    let result = analyzer.solve();

    // x gets strong update
    assert_eq!(result.points_to_size(var(1)), 1);
    assert!(result.points_to(var(1)).contains(&loc(200)));

    // y is NOT updated (weak update for aliased variables)
    assert!(result.points_to(var(2)).contains(&loc(100)));
    assert!(!result.points_to(var(2)).contains(&loc(200)));
}
```

#### Test 1.3: No Strong Update for Heap Locations
```rust
#[test]
fn test_no_strong_update_for_heap() {
    let mut analyzer = FlowSensitivePTA::new();

    // obj = new Object()
    analyzer.add_alloc(var(1), loc(100));

    // obj.field = new A()
    analyzer.add_store_field(var(1), "field", loc(200));

    // obj.field = new B() (heap update)
    analyzer.add_store_field(var(1), "field", loc(300));

    let result = analyzer.solve();

    // Heap locations use weak update (conservative)
    let field_pts = result.heap_field_points_to(loc(100), "field");
    assert!(field_pts.contains(&loc(200)));
    assert!(field_pts.contains(&loc(300))); // Both retained (weak update)
}
```

---

### Test Suite 2: Must-Alias Analysis (Unit Tests)

**File**: `packages/codegraph-ir/tests/points_to/test_must_alias.rs`

#### Test 2.1: Must-Alias After Assignment
```rust
#[test]
fn test_must_alias_after_assignment() {
    let mut analyzer = FlowSensitivePTA::new();

    // x = new A()
    analyzer.add_alloc(var(1), loc(100));

    // y = x
    analyzer.add_copy(var(2), var(1));

    let result = analyzer.solve();

    // x and y must-alias (same unique points-to set)
    assert!(result.must_alias(var(1), var(2)));

    // Both point to exactly the same location
    assert_eq!(result.points_to_size(var(1)), 1);
    assert_eq!(result.points_to_size(var(2)), 1);
    assert_eq!(result.points_to(var(1)), result.points_to(var(2)));
}
```

#### Test 2.2: Must-Alias Broken by Reassignment
```rust
#[test]
fn test_must_alias_broken_by_reassignment() {
    let mut analyzer = FlowSensitivePTA::new();

    // x = new A()
    analyzer.add_alloc(var(1), loc(100));

    // y = x (must-alias)
    analyzer.add_copy(var(2), var(1));

    let result_before = analyzer.solve();
    assert!(result_before.must_alias(var(1), var(2)));

    // x = new B() (reassignment breaks must-alias)
    analyzer.add_alloc(var(1), loc(200));

    let result_after = analyzer.solve();

    // No longer must-alias
    assert!(!result_after.must_alias(var(1), var(2)));

    // x points to B, y still points to A
    assert_eq!(result_after.points_to(var(1)), hashset![loc(200)]);
    assert_eq!(result_after.points_to(var(2)), hashset![loc(100)]);
}
```

#### Test 2.3: Must-Not-Alias Detection
```rust
#[test]
fn test_must_not_alias() {
    let mut analyzer = FlowSensitivePTA::new();

    // x = new A()
    analyzer.add_alloc(var(1), loc(100));

    // y = new B()
    analyzer.add_alloc(var(2), loc(200));

    let result = analyzer.solve();

    // x and y must-not-alias (disjoint points-to sets)
    assert!(result.must_not_alias(var(1), var(2)));

    // No overlap in points-to sets
    assert!(result.points_to(var(1)).is_disjoint(&result.points_to(var(2))));
}
```

---

### Test Suite 3: Null Safety Analysis (Integration Tests)

**File**: `packages/codegraph-ir/tests/points_to/test_null_safety.rs`

#### Test 3.1: Null Check Eliminates None Alias
```rust
#[test]
fn test_null_check_eliminates_none() {
    let mut analyzer = FlowSensitivePTA::new();

    // data = get_user() (may return None or User object)
    analyzer.add_allocation_site(var(1), AllocSite::MaybeNull {
        null_loc: loc(0),     // Special location for None
        object_loc: loc(100), // User object
    });

    // Initial: data may-alias None
    let before_check = analyzer.solve_at_line(10);
    assert!(before_check.may_alias(var(1), loc(0))); // May be None

    // if data is None: return (null check)
    analyzer.add_branch_condition(BranchCondition::IsNull(var(1)), TrueBranch, line(11));

    // After null check (false branch)
    let after_check = analyzer.solve_at_line(12);

    // Strong update: data cannot be None anymore
    assert!(!after_check.may_alias(var(1), loc(0))); // Not None!
    assert!(after_check.must_not_alias(var(1), loc(0)));
}
```

#### Test 3.2: Field Access After Null Check
```rust
#[test]
fn test_field_access_after_null_check() {
    let code = r#"
def process(user):
    if user is None:
        return
    # Line 5: user is definitely not None
    return user.name  # Should NOT report NullPointerException
"#;

    let analyzer = FlowSensitivePTA::from_code(code);
    let result = analyzer.solve();

    // At line 5, user must-not-alias None
    let pts_at_line_5 = result.points_to_at_line(var("user"), 5);
    assert!(!pts_at_line_5.contains(&NULL_LOCATION));

    // No null pointer false positive
    let null_errors = result.find_null_dereferences();
    assert_eq!(null_errors.len(), 0); // No FP!
}
```

#### Test 3.3: Null Propagation Through Assignments
```rust
#[test]
fn test_null_propagation() {
    let code = r#"
x = None
y = x      # y must be None
z = y      # z must be None
access(z)  # NullPointerException!
"#;

    let analyzer = FlowSensitivePTA::from_code(code);
    let result = analyzer.solve();

    // All must-alias None
    assert!(result.must_alias(var("x"), NULL_LOCATION));
    assert!(result.must_alias(var("y"), NULL_LOCATION));
    assert!(result.must_alias(var("z"), NULL_LOCATION));

    // Should detect null dereference
    let errors = result.find_null_dereferences();
    assert_eq!(errors.len(), 1);
    assert_eq!(errors[0].var_name, "z");
}
```

---

### Test Suite 4: Control Flow Sensitivity (Integration Tests)

**File**: `packages/codegraph-ir/tests/points_to/test_control_flow_sensitivity.rs`

#### Test 4.1: Different Points-To Sets Per Branch
```rust
#[test]
fn test_branch_specific_points_to() {
    let code = r#"
if condition:
    p = new A()
    # Line 3: p → A
else:
    p = new B()
    # Line 6: p → B
# Line 7: p → {A, B} (merge point)
"#;

    let analyzer = FlowSensitivePTA::from_code(code);
    let result = analyzer.solve();

    // Inside true branch: p must point to A
    let pts_line_3 = result.points_to_at_line(var("p"), 3);
    assert_eq!(pts_line_3.len(), 1);
    assert!(pts_line_3.contains(&loc_a()));

    // Inside false branch: p must point to B
    let pts_line_6 = result.points_to_at_line(var("p"), 6);
    assert_eq!(pts_line_6.len(), 1);
    assert!(pts_line_6.contains(&loc_b()));

    // After merge: p may point to A or B
    let pts_line_7 = result.points_to_at_line(var("p"), 7);
    assert_eq!(pts_line_7.len(), 2);
    assert!(pts_line_7.contains(&loc_a()));
    assert!(pts_line_7.contains(&loc_b()));
}
```

#### Test 4.2: Loop Widening (Conservative Approximation)
```rust
#[test]
fn test_loop_widening() {
    let code = r#"
p = new A()
for i in range(10):
    p = new B()  # Inside loop
# After loop: p → {A, B} (conservative)
"#;

    let analyzer = FlowSensitivePTA::new()
        .with_loop_widening(true);

    let result = analyzer.analyze_code(code);

    // Before loop: p → A
    let before_loop = result.points_to_at_line(var("p"), 1);
    assert_eq!(before_loop, hashset![loc_a()]);

    // After loop: Conservative merge (A from entry, B from loop body)
    let after_loop = result.points_to_at_line(var("p"), 4);
    assert!(after_loop.contains(&loc_a()));
    assert!(after_loop.contains(&loc_b()));
}
```

---

### Test Suite 5: Performance Benchmarks

**File**: `packages/codegraph-ir/benches/flow_sensitive_pta.rs`

#### Benchmark 5.1: Small Function (< 100 LOC)
```rust
#[bench]
fn bench_flow_sensitive_small_function(b: &mut Bencher) {
    let code = generate_test_function(50); // 50 lines

    b.iter(|| {
        let mut analyzer = FlowSensitivePTA::new();
        let result = analyzer.analyze_code(&code);
        black_box(result);
    });
}

// Target: < 10ms per function
```

#### Benchmark 5.2: Large Function (1000+ LOC)
```rust
#[bench]
fn bench_flow_sensitive_large_function(b: &mut Bencher) {
    let code = generate_test_function(1000); // 1000 lines

    b.iter(|| {
        let mut analyzer = FlowSensitivePTA::new();
        let result = analyzer.analyze_code(&code);
        black_box(result);
    });
}

// Target: < 500ms per function
```

#### Benchmark 5.3: Comparison with Flow-Insensitive
```rust
#[bench]
fn bench_compare_flow_insensitive(b: &mut Bencher) {
    let code = generate_test_function(200);

    let flow_insensitive_time = measure(|| {
        AndersenSolver::new().analyze_code(&code);
    });

    let flow_sensitive_time = measure(|| {
        FlowSensitivePTA::new().analyze_code(&code);
    });

    // Target: Flow-sensitive < 5x slower than flow-insensitive
    assert!(flow_sensitive_time < flow_insensitive_time * 5.0);
}
```

---

## Implementation Plan

### Phase 1: Core Flow-Sensitive Framework (Week 1-2)

**File**: `packages/codegraph-ir/src/features/points_to/application/flow_sensitive_pta.rs`

```rust
use std::collections::{HashMap, HashSet};
use rustc_hash::FxHashMap;

/// Flow-sensitive points-to analysis
///
/// **Algorithm**: Forward dataflow with strong update
///
/// **Time Complexity**: O(CFG nodes × variables × locations)
/// **Space Complexity**: O(CFG nodes × variables)
///
/// **References**:
/// - Choi et al. (1999): "Efficient and Precise Modeling of Exceptions"
/// - Hind (2001): "Pointer Analysis: Haven't We Solved This Problem Yet?"
pub struct FlowSensitivePTA {
    /// Points-to facts at each program point: location → (var → locations)
    facts: FxHashMap<ProgramPoint, FxHashMap<VarId, LocationSet>>,

    /// Control flow graph
    cfg: ControlFlowGraph,

    /// Must-alias information: location → (var1, var2) pairs
    must_alias: FxHashMap<ProgramPoint, HashSet<(VarId, VarId)>>,

    /// Worklist for dataflow propagation
    worklist: Vec<ProgramPoint>,

    /// Configuration
    config: FlowSensitiveConfig,
}

#[derive(Debug, Clone)]
pub struct FlowSensitiveConfig {
    /// Enable strong update optimization
    pub enable_strong_update: bool,

    /// Enable must-alias tracking
    pub enable_must_alias: bool,

    /// Loop widening threshold (max iterations before widening)
    pub loop_widening_threshold: usize,

    /// Enable null safety analysis
    pub enable_null_safety: bool,
}

impl Default for FlowSensitiveConfig {
    fn default() -> Self {
        Self {
            enable_strong_update: true,
            enable_must_alias: true,
            loop_widening_threshold: 3,
            enable_null_safety: true,
        }
    }
}

/// Program point in CFG
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ProgramPoint {
    /// Basic block ID
    pub block_id: u32,

    /// Statement index within block
    pub stmt_idx: usize,
}

/// Set of abstract locations
pub type LocationSet = HashSet<LocationId>;

impl FlowSensitivePTA {
    pub fn new() -> Self {
        Self {
            facts: FxHashMap::default(),
            cfg: ControlFlowGraph::new(),
            must_alias: FxHashMap::default(),
            worklist: Vec::new(),
            config: FlowSensitiveConfig::default(),
        }
    }

    /// Solve flow-sensitive points-to analysis
    pub fn solve(&mut self) -> FlowSensitiveResult {
        // Step 1: Build CFG
        self.build_cfg();

        // Step 2: Initialize entry point
        let entry = self.cfg.entry_point();
        self.facts.insert(entry, FxHashMap::default());
        self.worklist.push(entry);

        // Step 3: Dataflow fixpoint iteration
        while let Some(point) = self.worklist.pop() {
            let changed = self.transfer_function(point);

            if changed {
                // Propagate to successors
                for succ in self.cfg.successors(point) {
                    if !self.worklist.contains(&succ) {
                        self.worklist.push(succ);
                    }
                }
            }
        }

        // Step 4: Build result
        self.build_result()
    }

    /// Transfer function for a program point
    ///
    /// Returns true if output facts changed
    fn transfer_function(&mut self, point: ProgramPoint) -> bool {
        // Get input facts (merge from predecessors)
        let input_facts = self.merge_predecessor_facts(point);

        // Get statement at this point
        let stmt = self.cfg.statement_at(point);

        // Apply statement effect
        let output_facts = self.apply_statement(&input_facts, stmt);

        // Check if output changed
        let old_facts = self.facts.get(&point);
        let changed = old_facts != Some(&output_facts);

        if changed {
            self.facts.insert(point, output_facts);
        }

        changed
    }

    /// Apply statement effect to input facts
    fn apply_statement(
        &mut self,
        input: &FxHashMap<VarId, LocationSet>,
        stmt: &Statement,
    ) -> FxHashMap<VarId, LocationSet> {
        let mut output = input.clone();

        match stmt {
            Statement::Alloc { lhs, location } => {
                // Strong update: lhs = new Object()
                if self.config.enable_strong_update && self.can_strong_update(*lhs, input) {
                    // Replace entirely
                    output.insert(*lhs, hashset![*location]);
                } else {
                    // Weak update: add to existing
                    output.entry(*lhs).or_default().insert(*location);
                }
            }

            Statement::Copy { lhs, rhs } => {
                // lhs = rhs
                let rhs_pts = input.get(rhs).cloned().unwrap_or_default();

                if self.config.enable_strong_update && self.can_strong_update(*lhs, input) {
                    output.insert(*lhs, rhs_pts);
                } else {
                    output.entry(*lhs).or_default().extend(&rhs_pts);
                }

                // Update must-alias if applicable
                if self.config.enable_must_alias && rhs_pts.len() == 1 {
                    // lhs and rhs now must-alias
                    // (Tracked separately in must_alias map)
                }
            }

            Statement::Load { lhs, base, field } => {
                // lhs = base.field
                let base_pts = input.get(base).cloned().unwrap_or_default();

                let mut loaded_locs = LocationSet::new();
                for base_loc in base_pts {
                    // Get points-to set of field at base_loc
                    if let Some(field_pts) = self.heap_field_points_to(base_loc, field) {
                        loaded_locs.extend(&field_pts);
                    }
                }

                if self.config.enable_strong_update && self.can_strong_update(*lhs, input) {
                    output.insert(*lhs, loaded_locs);
                } else {
                    output.entry(*lhs).or_default().extend(&loaded_locs);
                }
            }

            Statement::Store { base, field, rhs } => {
                // base.field = rhs
                let base_pts = input.get(base).cloned().unwrap_or_default();
                let rhs_pts = input.get(rhs).cloned().unwrap_or_default();

                for base_loc in base_pts {
                    // Weak update for heap (always conservative)
                    self.heap_field_points_to_mut(base_loc, field)
                        .extend(&rhs_pts);
                }
            }

            Statement::NullCheck { var, is_null } => {
                // if var is None / if var is not None
                if self.config.enable_null_safety {
                    if *is_null {
                        // True branch: var must be None
                        output.insert(*var, hashset![NULL_LOCATION]);
                    } else {
                        // False branch: var cannot be None (strong update!)
                        if let Some(pts) = output.get_mut(var) {
                            pts.remove(&NULL_LOCATION);
                        }
                    }
                }
            }

            _ => {
                // Other statements: identity transfer
            }
        }

        output
    }

    /// Check if strong update is safe for a variable
    ///
    /// Strong update requires:
    /// 1. Variable is not aliased by others
    /// 2. Variable has unique points-to set
    fn can_strong_update(&self, var: VarId, facts: &FxHashMap<VarId, LocationSet>) -> bool {
        if !self.config.enable_strong_update {
            return false;
        }

        // Check if any other variable may-alias this one
        let var_pts = facts.get(&var);
        if var_pts.is_none() {
            return true; // First assignment
        }

        let var_pts = var_pts.unwrap();

        for (other_var, other_pts) in facts.iter() {
            if *other_var == var {
                continue;
            }

            // If points-to sets overlap, cannot strong update
            if !var_pts.is_disjoint(other_pts) {
                return false;
            }
        }

        true
    }

    /// Merge facts from all predecessors (join operation)
    fn merge_predecessor_facts(
        &self,
        point: ProgramPoint,
    ) -> FxHashMap<VarId, LocationSet> {
        let predecessors = self.cfg.predecessors(point);

        if predecessors.is_empty() {
            return FxHashMap::default();
        }

        // Start with first predecessor's facts
        let mut merged = self.facts.get(&predecessors[0])
            .cloned()
            .unwrap_or_default();

        // Union with remaining predecessors
        for pred in &predecessors[1..] {
            if let Some(pred_facts) = self.facts.get(pred) {
                for (var, pred_pts) in pred_facts.iter() {
                    merged.entry(*var).or_default().extend(pred_pts);
                }
            }
        }

        merged
    }

    /// Build final result
    fn build_result(&self) -> FlowSensitiveResult {
        FlowSensitiveResult {
            facts: self.facts.clone(),
            must_alias: self.must_alias.clone(),
            cfg: self.cfg.clone(),
        }
    }

    // Helper methods for heap modeling (simplified)
    fn heap_field_points_to(&self, base: LocationId, field: &str) -> Option<LocationSet> {
        // TODO: Implement heap model
        None
    }

    fn heap_field_points_to_mut(&mut self, base: LocationId, field: &str) -> &mut LocationSet {
        // TODO: Implement heap model
        todo!("Heap model")
    }
}

/// Result of flow-sensitive points-to analysis
#[derive(Debug, Clone)]
pub struct FlowSensitiveResult {
    /// Points-to facts at each program point
    pub facts: FxHashMap<ProgramPoint, FxHashMap<VarId, LocationSet>>,

    /// Must-alias information
    pub must_alias: FxHashMap<ProgramPoint, HashSet<(VarId, VarId)>>,

    /// Control flow graph
    pub cfg: ControlFlowGraph,
}

impl FlowSensitiveResult {
    /// Get points-to set for a variable at a specific program point
    pub fn points_to_at(&self, point: ProgramPoint, var: VarId) -> LocationSet {
        self.facts.get(&point)
            .and_then(|facts| facts.get(&var))
            .cloned()
            .unwrap_or_default()
    }

    /// Get points-to set at a specific source line
    pub fn points_to_at_line(&self, var: VarId, line: usize) -> LocationSet {
        let point = self.cfg.point_at_line(line);
        self.points_to_at(point, var)
    }

    /// Check if two variables must-alias at a program point
    pub fn must_alias(&self, point: ProgramPoint, v1: VarId, v2: VarId) -> bool {
        self.must_alias.get(&point)
            .map(|aliases| aliases.contains(&(v1, v2)) || aliases.contains(&(v2, v1)))
            .unwrap_or(false)
    }

    /// Check if two variables must-not-alias
    pub fn must_not_alias(&self, point: ProgramPoint, v1: VarId, v2: VarId) -> bool {
        let pts1 = self.points_to_at(point, v1);
        let pts2 = self.points_to_at(point, v2);

        // Disjoint points-to sets = must-not-alias
        pts1.is_disjoint(&pts2)
    }

    /// Find potential null pointer dereferences
    pub fn find_null_dereferences(&self) -> Vec<NullDerefError> {
        let mut errors = Vec::new();

        for (point, facts) in &self.facts {
            let stmt = self.cfg.statement_at(*point);

            // Check for field access or method call
            if let Some(var) = stmt.dereferenced_var() {
                if let Some(pts) = facts.get(&var) {
                    // If may-alias None, potential null deref
                    if pts.contains(&NULL_LOCATION) {
                        errors.push(NullDerefError {
                            var_name: format!("var_{}", var),
                            location: *point,
                            line: self.cfg.line_of_point(*point),
                        });
                    }
                }
            }
        }

        errors
    }
}

/// Null dereference error
#[derive(Debug, Clone)]
pub struct NullDerefError {
    pub var_name: String,
    pub location: ProgramPoint,
    pub line: usize,
}

/// Special location ID for None/null
pub const NULL_LOCATION: LocationId = 0;
```

**Tests**: Test Suite 1 (Strong Update), Test Suite 2 (Must-Alias)

---

### Phase 2: Null Safety Analysis (Week 3-4)

**File**: `packages/codegraph-ir/src/features/points_to/application/null_safety.rs`

```rust
/// Null safety analyzer built on flow-sensitive PTA
pub struct NullSafetyAnalyzer {
    pta: FlowSensitivePTA,
}

impl NullSafetyAnalyzer {
    pub fn new() -> Self {
        Self {
            pta: FlowSensitivePTA::new()
                .with_null_safety(true),
        }
    }

    /// Analyze code for null safety violations
    pub fn analyze_code(&mut self, code: &str) -> NullSafetyResult {
        let result = self.pta.analyze_code(code);

        NullSafetyResult {
            null_dereferences: result.find_null_dereferences(),
            guaranteed_non_null: self.find_guaranteed_non_null(&result),
        }
    }

    /// Find variables that are guaranteed to be non-null at each point
    fn find_guaranteed_non_null(&self, result: &FlowSensitiveResult) -> Vec<GuaranteedNonNull> {
        let mut guaranteed = Vec::new();

        for (point, facts) in &result.facts {
            for (var, pts) in facts.iter() {
                // If points-to set doesn't contain None, guaranteed non-null
                if !pts.contains(&NULL_LOCATION) && !pts.is_empty() {
                    guaranteed.push(GuaranteedNonNull {
                        var: *var,
                        location: *point,
                    });
                }
            }
        }

        guaranteed
    }
}
```

**Tests**: Test Suite 3 (Null Safety Analysis)

---

### Phase 3: Control Flow Sensitivity (Week 4-5)

**Enhancement**: Branch-specific points-to facts

```rust
impl FlowSensitivePTA {
    /// Handle conditional branches
    fn handle_branch(
        &mut self,
        condition: &BranchCondition,
        true_branch: ProgramPoint,
        false_branch: ProgramPoint,
        input_facts: &FxHashMap<VarId, LocationSet>,
    ) {
        match condition {
            BranchCondition::IsNull(var) => {
                // True branch: var must be None
                let mut true_facts = input_facts.clone();
                true_facts.insert(*var, hashset![NULL_LOCATION]);
                self.facts.insert(true_branch, true_facts);

                // False branch: var cannot be None
                let mut false_facts = input_facts.clone();
                if let Some(pts) = false_facts.get_mut(var) {
                    pts.remove(&NULL_LOCATION);
                }
                self.facts.insert(false_branch, false_facts);
            }

            BranchCondition::IsInstance(var, type_name) => {
                // True branch: var has specific type
                // (Integration with type narrowing)
                todo!("Type-based narrowing")
            }

            _ => {
                // Conservative: same facts for both branches
                self.facts.insert(true_branch, input_facts.clone());
                self.facts.insert(false_branch, input_facts.clone());
            }
        }
    }
}
```

**Tests**: Test Suite 4 (Control Flow Sensitivity)

---

### Phase 4: Performance Optimization (Week 5-6)

**File**: `packages/codegraph-ir/src/features/points_to/application/optimizations.rs`

```rust
/// Optimized flow-sensitive PTA with sparse representation
pub struct OptimizedFlowSensitivePTA {
    inner: FlowSensitivePTA,

    /// Sparse facts: only store points that differ from predecessors
    sparse_facts: FxHashMap<ProgramPoint, SparseFacts>,
}

/// Sparse facts representation (only deltas)
struct SparseFacts {
    /// Variables with strong updates (complete replacement)
    strong_updates: FxHashMap<VarId, LocationSet>,

    /// Variables with weak updates (additions only)
    weak_updates: FxHashMap<VarId, LocationSet>,
}

impl OptimizedFlowSensitivePTA {
    /// Reconstruct full facts by applying deltas
    fn reconstruct_facts(&self, point: ProgramPoint) -> FxHashMap<VarId, LocationSet> {
        let mut facts = FxHashMap::default();

        // Walk CFG path from entry to point, applying deltas
        for p in self.cfg.path_from_entry(point) {
            if let Some(sparse) = self.sparse_facts.get(&p) {
                // Apply strong updates (replace)
                for (var, locs) in &sparse.strong_updates {
                    facts.insert(*var, locs.clone());
                }

                // Apply weak updates (union)
                for (var, locs) in &sparse.weak_updates {
                    facts.entry(*var).or_default().extend(locs);
                }
            }
        }

        facts
    }
}
```

**Performance Targets**:
- Small functions (< 100 LOC): < 10ms
- Large functions (1000 LOC): < 500ms
- Overhead vs flow-insensitive: < 5x

**Tests**: Test Suite 5 (Performance Benchmarks)

---

### Phase 5: Integration with Taint Analysis (Week 6-7)

**File**: `packages/codegraph-ir/src/features/taint_analysis/integration/flow_sensitive_pta_integration.rs`

```rust
/// Taint analysis enhanced with flow-sensitive PTA
pub struct FlowSensitiveTaintAnalyzer {
    taint_analyzer: PathSensitiveTaintAnalyzer,
    pta: FlowSensitivePTA,
}

impl FlowSensitiveTaintAnalyzer {
    /// Analyze taint with precise null safety
    pub fn analyze(&mut self, code: &str) -> TaintResult {
        // Step 1: Run flow-sensitive PTA
        let pta_result = self.pta.analyze_code(code);

        // Step 2: Use PTA results to refine taint analysis
        let mut taint_result = self.taint_analyzer.analyze(code);

        // Step 3: Eliminate false positives using must-not-alias
        self.eliminate_fps_with_pta(&mut taint_result, &pta_result);

        taint_result
    }

    /// Eliminate false positives using PTA precision
    fn eliminate_fps_with_pta(
        &self,
        taint_result: &mut TaintResult,
        pta_result: &FlowSensitiveResult,
    ) {
        taint_result.vulnerabilities.retain(|vuln| {
            let point = pta_result.cfg.point_at_line(vuln.source.line);

            // If source and sink must-not-alias, eliminate FP
            !pta_result.must_not_alias(
                point,
                vuln.source.var_id,
                vuln.sink.var_id,
            )
        });
    }
}
```

---

## Success Criteria

### Functional Requirements
- ✅ Strong update works for local variables (Test 1.1)
- ✅ No strong update when aliased (Test 1.2)
- ✅ Must-alias detection works (Test 2.1)
- ✅ Null check eliminates None alias (Test 3.1)
- ✅ No false positives after null check (Test 3.2)
- ✅ Branch-specific points-to sets (Test 4.1)

### Non-Functional Requirements
- **Performance**: < 10ms for small functions, < 500ms for large
- **Overhead**: < 5x slower than flow-insensitive
- **Precision**: +30-40% must-alias detection rate

### Acceptance Criteria
1. All 15+ tests pass
2. Null safety false positive rate reduced by > 50%
3. Performance within budget
4. Successfully integrated with taint analysis

---

## Timeline

| Week | Phase | Deliverables | Tests |
|------|-------|-------------|-------|
| 1-2 | Core Framework | FlowSensitivePTA | Suite 1, 2 (6 tests) |
| 3-4 | Null Safety | NullSafetyAnalyzer | Suite 3 (3 tests) |
| 4-5 | Control Flow | Branch handling | Suite 4 (2 tests) |
| 5-6 | Optimization | Sparse representation | Suite 5 (3 benchmarks) |
| 6-7 | Integration | Taint analysis integration | 2 integration tests |

**Total**: 6-8 weeks, 15+ tests

---

## References

- Existing: [andersen_solver.rs](../../packages/codegraph-ir/src/features/points_to/infrastructure/andersen_solver.rs) (647 LOC, flow-insensitive)
- Existing: [steensgaard_solver.rs](../../packages/codegraph-ir/src/features/points_to/infrastructure/steensgaard_solver.rs) (1,200 LOC)
- Academic: Choi et al. (1999) "Efficient and Precise Modeling of Exceptions"
- Academic: Hind (2001) "Pointer Analysis: Haven't We Solved This Problem Yet?"

---

**Status**: Ready for implementation after RFC-001
**Next Step**: Implement Phase 1 (Core Framework) and Test Suite 1-2
