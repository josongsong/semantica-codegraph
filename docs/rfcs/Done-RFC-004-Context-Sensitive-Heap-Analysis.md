# RFC-004: Context-Sensitive Heap Analysis

**Status**: Draft
**Priority**: P1 (6 months)
**Effort**: 6-8 weeks
**Authors**: Semantica Team
**Created**: 2025-12-30
**Target Version**: v2.2.0

---

## Executive Summary

Implement **context-sensitive heap analysis** with heap cloning to dramatically improve precision for container operations and factory patterns.

**Current State**: 50% implemented - Separation logic exists ([separation_logic.rs:956](../../packages/codegraph-ir/src/features/heap_analysis/separation_logic.rs) LOC), no heap cloning
**Gap**: No context-sensitive heap modeling, container imprecision
**Impact**: +40-50% precision for container operations, critical for factory/builder patterns

---

## Motivation

### Problem Statement

**Current Context-Insensitive Heap** (Andersen-style):
```python
# Factory pattern
def create_user(name):
    user = User()
    user.name = name
    return user

alice = create_user("Alice")
bob = create_user("Bob")

# Context-insensitive: Both point to SAME abstract object!
# alice.name and bob.name are ALIASED ❌
print(alice.name)  # May be "Alice" or "Bob" (imprecise!)
```

**Context-Sensitive Heap** (Target):
```python
# Factory pattern
def create_user(name):
    user = User()  # Heap clone per call site!
    user.name = name
    return user

# Call site 1
alice = create_user("Alice")  # Object_1 (Alice)

# Call site 2
bob = create_user("Bob")      # Object_2 (Bob, separate!)

# Context-sensitive: alice and bob are DISTINCT
# alice.name = "Alice", bob.name = "Bob" ✅
print(alice.name)  # Must be "Alice" (precise!)
```

**Container Imprecision (Current)**:
```python
list1 = []
list1.append(tainted_data)

list2 = []
list2.append(safe_data)

# Context-insensitive: Both lists point to SAME abstract container
# list1[0] and list2[0] are ALIASED ❌
return list2[0]  # FALSE POSITIVE: Tainted (actually safe!)
```

**Container Precision (Target)**:
```python
list1 = []             # Container_1
list1.append(tainted)

list2 = []             # Container_2 (separate!)
list2.append(safe)

# Context-sensitive: list1 and list2 are DISTINCT
return list2[0]  # NO FALSE POSITIVE ✅ (safe!)
```

---

## Test-Driven Specification

### Test Suite 1: Basic Heap Cloning (Unit Tests)

**File**: `packages/codegraph-ir/tests/heap_analysis/test_heap_cloning.rs`

#### Test 1.1: Heap Clone Per Call Site
```rust
#[test]
fn test_heap_clone_per_call_site() {
    let code = r#"
def factory():
    obj = Object()
    return obj

o1 = factory()  # Call site 1
o2 = factory()  # Call site 2
"#;

    let analyzer = ContextSensitiveHeapAnalyzer::new()
        .with_heap_cloning(true);

    let result = analyzer.analyze(code).unwrap();

    // o1 and o2 should point to DIFFERENT abstract objects
    assert!(!result.may_alias(var("o1"), var("o2")));

    let o1_pts = result.points_to(var("o1"));
    let o2_pts = result.points_to(var("o2"));

    // Disjoint points-to sets
    assert!(o1_pts.is_disjoint(&o2_pts));

    // Each has exactly one location (the cloned heap object)
    assert_eq!(o1_pts.len(), 1);
    assert_eq!(o2_pts.len(), 1);
}
```

#### Test 1.2: Field Independence After Cloning
```rust
#[test]
fn test_field_independence_after_cloning() {
    let code = r#"
def create_user(name):
    user = User()
    user.name = name
    return user

alice = create_user("Alice")
bob = create_user("Bob")
"#;

    let result = ContextSensitiveHeapAnalyzer::analyze(code).unwrap();

    // alice and bob must not alias
    assert!(!result.may_alias(var("alice"), var("bob")));

    // alice.name and bob.name are independent
    let alice_name_pts = result.field_points_to(var("alice"), "name");
    let bob_name_pts = result.field_points_to(var("bob"), "name");

    assert!(alice_name_pts.is_disjoint(&bob_name_pts));
}
```

#### Test 1.3: No Cloning for Globals
```rust
#[test]
fn test_no_cloning_for_globals() {
    let code = r#"
SINGLETON = create_global()

def get_singleton():
    return SINGLETON

s1 = get_singleton()
s2 = get_singleton()
"#;

    let result = ContextSensitiveHeapAnalyzer::new()
        .with_global_merging(true)
        .analyze(code)
        .unwrap();

    // s1 and s2 should ALIAS (same global object)
    assert!(result.may_alias(var("s1"), var("s2")));
    assert!(result.must_alias(var("s1"), var("s2")));
}
```

---

### Test Suite 2: Container Precision (Integration Tests)

**File**: `packages/codegraph-ir/tests/heap_analysis/test_container_precision.rs`

#### Test 2.1: Independent List Instances
```rust
#[test]
fn test_independent_list_instances() {
    let code = r#"
list1 = []
list1.append(tainted_data)

list2 = []
list2.append(safe_data)
"#;

    let result = ContainerAnalyzer::new()
        .with_context_sensitive_heap(true)
        .analyze(code)
        .unwrap();

    // list1 and list2 must not alias
    assert!(!result.may_alias(var("list1"), var("list2")));

    // Contents should be independent
    let list1_contents = result.container_contents(var("list1"));
    let list2_contents = result.container_contents(var("list2"));

    // list1 contains tainted, list2 contains safe
    assert!(list1_contents.contains(&tainted_location()));
    assert!(list2_contents.contains(&safe_location()));

    // No overlap
    assert!(list1_contents.is_disjoint(&list2_contents));
}
```

#### Test 2.2: Nested Container Independence
```rust
#[test]
fn test_nested_container_independence() {
    let code = r#"
outer1 = []
inner1 = []
inner1.append(data1)
outer1.append(inner1)

outer2 = []
inner2 = []
inner2.append(data2)
outer2.append(inner2)
"#;

    let result = ContainerAnalyzer::analyze(code).unwrap();

    // outer1 != outer2
    assert!(!result.may_alias(var("outer1"), var("outer2")));

    // inner1 != inner2
    assert!(!result.may_alias(var("inner1"), var("inner2")));

    // data1 != data2 (deep independence)
    let inner1_contents = result.container_contents(var("inner1"));
    let inner2_contents = result.container_contents(var("inner2"));
    assert!(inner1_contents.is_disjoint(&inner2_contents));
}
```

#### Test 2.3: Dictionary Key-Value Independence
```rust
#[test]
fn test_dict_key_value_independence() {
    let code = r#"
cache1 = {}
cache1["key"] = tainted_value

cache2 = {}
cache2["key"] = safe_value
"#;

    let result = DictAnalyzer::analyze(code).unwrap();

    // cache1 != cache2
    assert!(!result.may_alias(var("cache1"), var("cache2")));

    // cache1["key"] != cache2["key"]
    let cache1_key_pts = result.dict_value_points_to(var("cache1"), "key");
    let cache2_key_pts = result.dict_value_points_to(var("cache2"), "key");

    assert!(cache1_key_pts.contains(&tainted_location()));
    assert!(cache2_key_pts.contains(&safe_location()));
    assert!(cache1_key_pts.is_disjoint(&cache2_key_pts));
}
```

---

### Test Suite 3: Factory Pattern Precision (Integration Tests)

**File**: `packages/codegraph-ir/tests/heap_analysis/test_factory_pattern.rs`

#### Test 3.1: Simple Factory
```rust
#[test]
fn test_simple_factory() {
    let code = r#"
def create_object(field_value):
    obj = Object()
    obj.field = field_value
    return obj

obj1 = create_object(value1)
obj2 = create_object(value2)
"#;

    let result = FactoryAnalyzer::analyze(code).unwrap();

    // obj1 != obj2
    assert!(!result.may_alias(var("obj1"), var("obj2")));

    // obj1.field != obj2.field
    assert!(!result.field_may_alias(var("obj1"), "field", var("obj2"), "field"));
}
```

#### Test 3.2: Builder Pattern
```rust
#[test]
fn test_builder_pattern() {
    let code = r#"
def build():
    builder = Builder()
    builder.set_name("Alice")
    builder.set_age(30)
    return builder.build()

user1 = build()
user2 = build()
"#;

    let result = BuilderAnalyzer::analyze(code).unwrap();

    // user1 and user2 are independent
    assert!(!result.may_alias(var("user1"), var("user2")));

    // Fields are independent
    assert!(!result.field_may_alias(var("user1"), "name", var("user2"), "name"));
    assert!(!result.field_may_alias(var("user1"), "age", var("user2"), "age"));
}
```

#### Test 3.3: Singleton Pattern (No Cloning)
```rust
#[test]
fn test_singleton_pattern() {
    let code = r#"
class Singleton:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

s1 = Singleton.get_instance()
s2 = Singleton.get_instance()
"#;

    let result = SingletonAnalyzer::analyze(code).unwrap();

    // s1 and s2 MUST alias (same instance)
    assert!(result.must_alias(var("s1"), var("s2")));
}
```

---

### Test Suite 4: Call String Context Sensitivity (Unit Tests)

**File**: `packages/codegraph-ir/tests/heap_analysis/test_call_string.rs`

#### Test 4.1: 1-Call-Site Sensitivity
```rust
#[test]
fn test_1_call_site_sensitivity() {
    let code = r#"
def helper():
    return Object()

def caller1():
    return helper()  # Call site 1

def caller2():
    return helper()  # Call site 2

obj1 = caller1()
obj2 = caller2()
"#;

    let analyzer = CallStringSensitiveAnalyzer::new()
        .with_k(1);  // 1-call-site sensitivity

    let result = analyzer.analyze(code).unwrap();

    // With k=1, obj1 and obj2 should be distinguished
    assert!(!result.may_alias(var("obj1"), var("obj2")));
}
```

#### Test 4.2: K-Limiting (Precision vs Cost Trade-off)
```rust
#[test]
fn test_k_limiting() {
    let code = generate_deep_call_chain(10);  // 10-level call chain

    // k=0 (context-insensitive): Fast but imprecise
    let k0_result = CallStringSensitiveAnalyzer::new()
        .with_k(0)
        .analyze(&code)
        .unwrap();

    // k=1 (1-call-site): Balance
    let k1_result = CallStringSensitiveAnalyzer::new()
        .with_k(1)
        .analyze(&code)
        .unwrap();

    // k=3 (3-call-site): Precise but slow
    let k3_result = CallStringSensitiveAnalyzer::new()
        .with_k(3)
        .analyze(&code)
        .unwrap();

    // Precision should improve with k
    assert!(k1_result.precision() > k0_result.precision());
    assert!(k3_result.precision() > k1_result.precision());

    // Cost should increase with k
    assert!(k1_result.analysis_time() > k0_result.analysis_time());
    assert!(k3_result.analysis_time() > k1_result.analysis_time());
}
```

---

### Test Suite 5: Taint Analysis Integration (End-to-End Tests)

**File**: `packages/codegraph-ir/tests/heap_analysis/test_taint_integration.rs`

#### Test 5.1: Eliminate False Positive with Container Precision
```rust
#[test]
fn test_eliminate_fp_with_container_precision() {
    let code = r#"
def process():
    tainted_list = []
    tainted_list.append(user_input)  # Tainted

    safe_list = []
    safe_list.append(constant)       # Safe

    # Context-insensitive: Would report FP here
    execute_sql(safe_list[0])  # Should be safe!
"#;

    // Without context-sensitive heap
    let insensitive_result = TaintAnalyzer::new()
        .with_context_sensitive_heap(false)
        .analyze(code)
        .unwrap();

    // FALSE POSITIVE: Reports taint
    assert_eq!(insensitive_result.vulnerabilities.len(), 1);

    // With context-sensitive heap
    let sensitive_result = TaintAnalyzer::new()
        .with_context_sensitive_heap(true)
        .analyze(code)
        .unwrap();

    // NO FALSE POSITIVE: Knows safe_list is independent
    assert_eq!(sensitive_result.vulnerabilities.len(), 0); // ✅
}
```

#### Test 5.2: Field-Sensitive Taint with Heap Cloning
```rust
#[test]
fn test_field_sensitive_taint_with_cloning() {
    let code = r#"
def create_user(name, email):
    user = User()
    user.name = name      # May be tainted
    user.email = email    # Safe
    return user

alice = create_user(user_input, "alice@example.com")
bob = create_user("Bob", "bob@example.com")

# alice.name is tainted, but alice.email is safe
execute_sql(alice.email)  # Should be safe!
execute_sql(bob.name)     # Should be safe!
"#;

    let result = FieldSensitiveTaintAnalyzer::new()
        .with_context_sensitive_heap(true)
        .analyze(code)
        .unwrap();

    // No false positives
    assert_eq!(result.vulnerabilities.len(), 0);

    // alice.name is tainted
    assert!(result.is_tainted(var("alice"), field("name")));

    // alice.email is safe (field-sensitive)
    assert!(!result.is_tainted(var("alice"), field("email")));

    // bob.name is safe (heap cloning)
    assert!(!result.is_tainted(var("bob"), field("name")));
}
```

---

## Implementation Plan

### Phase 1: Core Heap Cloning (Week 1-3)

**File**: `packages/codegraph-ir/src/features/heap_analysis/context_sensitive_heap.rs`

```rust
use std::collections::{HashMap, HashSet};
use rustc_hash::FxHashMap;

/// Context-sensitive heap analysis with heap cloning
///
/// **Algorithm**: k-Call-Site Sensitivity
///
/// **Key Idea**: Clone heap objects per call site
/// - Factory returns at line 10 → Object_10
/// - Factory returns at line 20 → Object_20
///
/// **Time Complexity**: O(k^d × nodes) where k=context depth, d=max call depth
/// **Space Complexity**: O(k^d × heap objects)
///
/// **References**:
/// - Milanova et al. (2002): "Parameterized Object Sensitivity for Points-to Analysis"
/// - Smaragdakis et al. (2011): "Pick Your Contexts Well"
pub struct ContextSensitiveHeapAnalyzer {
    /// Heap abstraction: (call context, allocation site) → abstract object
    heap: FxHashMap<(CallContext, AllocSite), AbstractObject>,

    /// Points-to facts: (context, var) → {abstract objects}
    points_to: FxHashMap<(CallContext, VarId), HashSet<AbstractObject>>,

    /// Call graph with context
    call_graph: ContextSensitiveCallGraph,

    /// Configuration
    config: ContextSensitiveConfig,
}

#[derive(Debug, Clone)]
pub struct ContextSensitiveConfig {
    /// k-call-site sensitivity depth
    pub k: usize,

    /// Enable heap cloning
    pub enable_heap_cloning: bool,

    /// Merge global allocations (no cloning)
    pub global_merging: bool,

    /// Enable container precision
    pub container_precision: bool,
}

impl Default for ContextSensitiveConfig {
    fn default() -> Self {
        Self {
            k: 1,  // 1-call-site sensitivity (balance)
            enable_heap_cloning: true,
            global_merging: true,
            container_precision: true,
        }
    }
}

/// Call context (k-limited call string)
///
/// Example with k=2:
/// - main → foo → bar → baz
/// - Context for baz: [bar, foo] (last 2 call sites)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CallContext {
    /// Call sites (limited to k entries)
    pub call_sites: Vec<CallSite>,
}

impl CallContext {
    /// Empty context (for entry point)
    pub fn empty() -> Self {
        Self { call_sites: Vec::new() }
    }

    /// Extend context with new call site (k-limiting)
    pub fn extend(&self, call_site: CallSite, k: usize) -> Self {
        let mut new_sites = self.call_sites.clone();
        new_sites.push(call_site);

        // Keep only last k call sites
        if new_sites.len() > k {
            new_sites = new_sites.into_iter().skip(new_sites.len() - k).collect();
        }

        Self { call_sites: new_sites }
    }
}

/// Call site (source location of function call)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CallSite {
    pub file: String,
    pub line: usize,
    pub callee: String,
}

/// Allocation site (source location of object creation)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct AllocSite {
    pub file: String,
    pub line: usize,
    pub kind: AllocKind,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum AllocKind {
    Object,     // User()
    List,       // []
    Dict,       // {}
    Set,        // set()
}

/// Abstract heap object (cloned per context)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct AbstractObject {
    /// Allocation site
    pub alloc_site: AllocSite,

    /// Call context where allocated
    pub context: CallContext,

    /// Object ID (unique per context + alloc site)
    pub id: ObjectId,
}

pub type ObjectId = u64;

impl ContextSensitiveHeapAnalyzer {
    pub fn new() -> Self {
        Self {
            heap: FxHashMap::default(),
            points_to: FxHashMap::default(),
            call_graph: ContextSensitiveCallGraph::new(),
            config: ContextSensitiveConfig::default(),
        }
    }

    /// Configure k-call-site sensitivity
    pub fn with_k(mut self, k: usize) -> Self {
        self.config.k = k;
        self
    }

    /// Enable/disable heap cloning
    pub fn with_heap_cloning(mut self, enable: bool) -> Self {
        self.config.enable_heap_cloning = enable;
        self
    }

    /// Analyze with context-sensitive heap
    pub fn analyze(&mut self, code: &str) -> Result<HeapAnalysisResult, CodegraphError> {
        // Step 1: Build context-sensitive call graph
        self.build_context_sensitive_cg(code)?;

        // Step 2: Process allocations with cloning
        self.process_allocations();

        // Step 3: Propagate points-to facts
        self.propagate_points_to();

        // Step 4: Build result
        Ok(self.build_result())
    }

    /// Process allocation with heap cloning
    fn process_allocations(&mut self) {
        for (context, alloc_site) in self.find_all_allocations() {
            // Check if should clone or merge
            let should_clone = self.config.enable_heap_cloning
                && !self.is_global_allocation(&alloc_site);

            if should_clone {
                // Heap cloning: Create separate object per context
                let obj = AbstractObject {
                    alloc_site: alloc_site.clone(),
                    context: context.clone(),
                    id: self.next_object_id(),
                };

                self.heap.insert((context.clone(), alloc_site), obj);
            } else {
                // Merging: Use same object for all contexts (conservative)
                let merged_context = CallContext::empty();
                if !self.heap.contains_key(&(merged_context.clone(), alloc_site.clone())) {
                    let obj = AbstractObject {
                        alloc_site: alloc_site.clone(),
                        context: merged_context.clone(),
                        id: self.next_object_id(),
                    };
                    self.heap.insert((merged_context, alloc_site), obj);
                }
            }
        }
    }

    /// Check if allocation is global (no cloning)
    fn is_global_allocation(&self, alloc_site: &AllocSite) -> bool {
        self.config.global_merging && self.is_in_global_scope(alloc_site)
    }

    /// Check if allocation site is in global scope
    fn is_in_global_scope(&self, alloc_site: &AllocSite) -> bool {
        // Heuristic: Check if allocation is at module level
        // (Real implementation would use scope analysis)
        alloc_site.file.contains("__init__") || alloc_site.line < 10
    }

    /// Find all allocation sites with their contexts
    fn find_all_allocations(&self) -> Vec<(CallContext, AllocSite)> {
        // TODO: Implement allocation site finder
        vec![]
    }

    /// Propagate points-to facts with context sensitivity
    fn propagate_points_to(&mut self) {
        // Worklist algorithm with context
        let mut worklist = vec![CallContext::empty()];

        while let Some(context) = worklist.pop() {
            // Process statements in this context
            for stmt in self.statements_in_context(&context) {
                match stmt {
                    Statement::Alloc { var, alloc_site } => {
                        // var points to heap object at (context, alloc_site)
                        if let Some(obj) = self.heap.get(&(context.clone(), alloc_site)) {
                            self.points_to
                                .entry((context.clone(), var))
                                .or_default()
                                .insert(obj.clone());
                        }
                    }

                    Statement::Copy { lhs, rhs } => {
                        // lhs = rhs
                        if let Some(rhs_pts) = self.points_to.get(&(context.clone(), rhs)).cloned() {
                            self.points_to
                                .entry((context.clone(), lhs))
                                .or_default()
                                .extend(rhs_pts);
                        }
                    }

                    Statement::Call { lhs, callee, call_site } => {
                        // Extend context for callee
                        let callee_context = context.extend(call_site, self.config.k);

                        // Add callee context to worklist
                        if !worklist.contains(&callee_context) {
                            worklist.push(callee_context.clone());
                        }

                        // lhs = callee's return value (with callee context)
                        // (Simplified - real implementation would track return values)
                    }

                    _ => {}
                }
            }
        }
    }

    /// Generate next object ID
    fn next_object_id(&mut self) -> ObjectId {
        static COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        COUNTER.fetch_add(1, std::sync::atomic::Ordering::SeqCst)
    }

    /// Build analysis result
    fn build_result(&self) -> HeapAnalysisResult {
        HeapAnalysisResult {
            heap: self.heap.clone(),
            points_to: self.points_to.clone(),
        }
    }

    // Placeholder methods
    fn build_context_sensitive_cg(&mut self, code: &str) -> Result<(), CodegraphError> {
        todo!("Build context-sensitive call graph")
    }

    fn statements_in_context(&self, context: &CallContext) -> Vec<Statement> {
        todo!("Get statements for context")
    }
}

/// Heap analysis result
#[derive(Debug, Clone)]
pub struct HeapAnalysisResult {
    pub heap: FxHashMap<(CallContext, AllocSite), AbstractObject>,
    pub points_to: FxHashMap<(CallContext, VarId), HashSet<AbstractObject>>,
}

impl HeapAnalysisResult {
    /// Check if two variables may alias
    pub fn may_alias(&self, v1: VarId, v2: VarId) -> bool {
        // Check all contexts
        for ((ctx1, var1), pts1) in &self.points_to {
            if *var1 != v1 {
                continue;
            }

            for ((ctx2, var2), pts2) in &self.points_to {
                if *var2 != v2 {
                    continue;
                }

                // If points-to sets overlap in any context, may alias
                if !pts1.is_disjoint(pts2) {
                    return true;
                }
            }
        }

        false
    }

    /// Check if two variables must alias
    pub fn must_alias(&self, v1: VarId, v2: VarId) -> bool {
        // Must have same unique points-to set in all contexts
        let v1_pts: Vec<_> = self.points_to.iter()
            .filter(|((_, var), _)| *var == v1)
            .map(|(_, pts)| pts)
            .collect();

        let v2_pts: Vec<_> = self.points_to.iter()
            .filter(|((_, var), _)| *var == v2)
            .map(|(_, pts)| pts)
            .collect();

        if v1_pts.is_empty() || v2_pts.is_empty() {
            return false;
        }

        // Check all contexts have same singleton points-to set
        v1_pts.iter().all(|pts1| {
            pts1.len() == 1 && v2_pts.iter().all(|pts2| pts1 == *pts2)
        })
    }

    /// Get points-to set for a variable (merged across contexts)
    pub fn points_to(&self, var: VarId) -> HashSet<AbstractObject> {
        let mut result = HashSet::new();

        for ((_, v), pts) in &self.points_to {
            if *v == var {
                result.extend(pts.iter().cloned());
            }
        }

        result
    }

    /// Get field points-to set
    pub fn field_points_to(&self, var: VarId, field: &str) -> HashSet<AbstractObject> {
        // TODO: Implement field-sensitive heap model
        HashSet::new()
    }

    /// Check if two fields may alias
    pub fn field_may_alias(
        &self,
        v1: VarId,
        f1: &str,
        v2: VarId,
        f2: &str,
    ) -> bool {
        let pts1 = self.field_points_to(v1, f1);
        let pts2 = self.field_points_to(v2, f2);

        !pts1.is_disjoint(&pts2)
    }
}

/// Context-sensitive call graph
#[derive(Debug, Clone)]
pub struct ContextSensitiveCallGraph {
    // TODO: Implement context-sensitive call graph
}

impl ContextSensitiveCallGraph {
    pub fn new() -> Self {
        Self {}
    }
}

// Placeholder types
type VarId = u32;

#[derive(Debug, Clone)]
enum Statement {
    Alloc { var: VarId, alloc_site: AllocSite },
    Copy { lhs: VarId, rhs: VarId },
    Call { lhs: VarId, callee: String, call_site: CallSite },
}
```

**Tests**: Test Suite 1 (Basic Heap Cloning), Test Suite 4 (Call String)

---

### Phase 2: Container Precision (Week 3-4)

**File**: `packages/codegraph-ir/src/features/heap_analysis/container_precision.rs`

```rust
/// Container-specific heap analysis
pub struct ContainerAnalyzer {
    heap_analyzer: ContextSensitiveHeapAnalyzer,
}

impl ContainerAnalyzer {
    pub fn new() -> Self {
        Self {
            heap_analyzer: ContextSensitiveHeapAnalyzer::new()
                .with_container_precision(true),
        }
    }

    /// Analyze container operations
    pub fn analyze(&mut self, code: &str) -> Result<ContainerResult, CodegraphError> {
        let heap_result = self.heap_analyzer.analyze(code)?;

        Ok(ContainerResult {
            heap_result,
            container_contents: self.extract_container_contents(&heap_result),
        })
    }

    /// Extract container contents (list elements, dict values)
    fn extract_container_contents(
        &self,
        heap_result: &HeapAnalysisResult,
    ) -> FxHashMap<AbstractObject, HashSet<AbstractObject>> {
        // TODO: Implement container content extraction
        FxHashMap::default()
    }
}

#[derive(Debug, Clone)]
pub struct ContainerResult {
    pub heap_result: HeapAnalysisResult,
    pub container_contents: FxHashMap<AbstractObject, HashSet<AbstractObject>>,
}

impl ContainerResult {
    /// Get contents of a container variable
    pub fn container_contents(&self, var: VarId) -> HashSet<AbstractObject> {
        let container_objs = self.heap_result.points_to(var);

        let mut contents = HashSet::new();
        for obj in container_objs {
            if let Some(obj_contents) = self.container_contents.get(&obj) {
                contents.extend(obj_contents.iter().cloned());
            }
        }

        contents
    }
}
```

**Tests**: Test Suite 2 (Container Precision)

---

### Phase 3: Factory Pattern Support (Week 4-5)

**Enhancement**: Specialized handling for factory patterns

```rust
/// Factory pattern detector and analyzer
pub struct FactoryAnalyzer {
    heap_analyzer: ContextSensitiveHeapAnalyzer,
}

impl FactoryAnalyzer {
    pub fn analyze(code: &str) -> Result<HeapAnalysisResult, CodegraphError> {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new()
            .with_k(1)  // 1-call-site is usually enough for factories
            .with_heap_cloning(true);

        analyzer.analyze(code)
    }
}
```

**Tests**: Test Suite 3 (Factory Pattern Precision)

---

### Phase 4: Taint Integration (Week 5-6)

**File**: `packages/codegraph-ir/src/features/taint_analysis/integration/heap_sensitive_taint.rs`

```rust
/// Taint analysis with context-sensitive heap
pub struct HeapSensitiveTaintAnalyzer {
    taint_analyzer: PathSensitiveTaintAnalyzer,
    heap_analyzer: ContextSensitiveHeapAnalyzer,
}

impl HeapSensitiveTaintAnalyzer {
    pub fn new() -> Self {
        Self {
            taint_analyzer: PathSensitiveTaintAnalyzer::new(None, None, 1000),
            heap_analyzer: ContextSensitiveHeapAnalyzer::new(),
        }
    }

    pub fn with_context_sensitive_heap(mut self, enable: bool) -> Self {
        self.heap_analyzer = self.heap_analyzer.with_heap_cloning(enable);
        self
    }

    /// Analyze taint with heap precision
    pub fn analyze(&mut self, code: &str) -> Result<TaintResult, CodegraphError> {
        // Step 1: Heap analysis
        let heap_result = self.heap_analyzer.analyze(code)?;

        // Step 2: Taint analysis (using heap precision)
        let mut taint_result = self.taint_analyzer.analyze(code)?;

        // Step 3: Eliminate FPs using heap precision
        self.eliminate_fps_with_heap(&mut taint_result, &heap_result);

        Ok(taint_result)
    }

    /// Eliminate false positives using heap precision
    fn eliminate_fps_with_heap(
        &self,
        taint_result: &mut TaintResult,
        heap_result: &HeapAnalysisResult,
    ) {
        taint_result.vulnerabilities.retain(|vuln| {
            // If source and sink point to different heap objects, not a real flow
            !heap_result.must_not_alias(vuln.source.var_id, vuln.sink.var_id)
        });
    }
}
```

**Tests**: Test Suite 5 (Taint Integration)

---

### Phase 5: Performance Optimization (Week 6-7)

**File**: `packages/codegraph-ir/src/features/heap_analysis/optimizations.rs`

```rust
/// Optimized context-sensitive heap with adaptive k
pub struct AdaptiveContextSensitiveAnalyzer {
    inner: ContextSensitiveHeapAnalyzer,
}

impl AdaptiveContextSensitiveAnalyzer {
    /// Adaptively choose k based on program characteristics
    pub fn analyze(&mut self, code: &str) -> Result<HeapAnalysisResult, CodegraphError> {
        // Heuristic: Use k=1 for most code, k=2 for factories
        let k = if self.has_factory_pattern(code) { 2 } else { 1 };

        self.inner = self.inner.clone().with_k(k);
        self.inner.analyze(code)
    }

    fn has_factory_pattern(&self, code: &str) -> bool {
        // Simple heuristic: Check for common factory method names
        code.contains("create_") || code.contains("build_") || code.contains("make_")
    }
}
```

**Performance Targets**:
- k=0 (context-insensitive): Baseline
- k=1 (1-call-site): < 3x slower
- k=2 (2-call-site): < 10x slower

---

## Success Criteria

### Functional Requirements
- ✅ Heap clone per call site (Test 1.1)
- ✅ Field independence after cloning (Test 1.2)
- ✅ No cloning for globals (Test 1.3)
- ✅ Independent container instances (Test 2.1-2.3)
- ✅ Factory pattern precision (Test 3.1-3.2)
- ✅ Eliminate taint FP with heap precision (Test 5.1)

### Non-Functional Requirements
- **Performance**: k=1 < 3x overhead, k=2 < 10x overhead
- **Precision**: +40-50% for container operations
- **Scalability**: Handle 10K+ LOC repos with k=1

### Acceptance Criteria
1. All 15+ tests pass
2. Taint FP reduced by > 30% on real codebase
3. Performance within budget
4. Successfully integrated with taint analysis

---

## Timeline

| Week | Phase | Deliverables | Tests |
|------|-------|-------------|-------|
| 1-3 | Core Cloning | ContextSensitiveHeapAnalyzer | Suite 1, 4 (5 tests) |
| 3-4 | Container Precision | ContainerAnalyzer | Suite 2 (3 tests) |
| 4-5 | Factory Support | FactoryAnalyzer | Suite 3 (3 tests) |
| 5-6 | Taint Integration | HeapSensitiveTaintAnalyzer | Suite 5 (2 tests) |
| 6-7 | Optimization | Adaptive k selection | 3 benchmarks |

**Total**: 6-8 weeks, 15+ tests

---

## References

- Existing: [separation_logic.rs](../../packages/codegraph-ir/src/features/heap_analysis/separation_logic.rs) (956 LOC, no heap cloning)
- Academic: Milanova et al. (2002) "Parameterized Object Sensitivity for Points-to Analysis"
- Academic: Smaragdakis et al. (2011) "Pick Your Contexts Well"
- Industry: Infer (Facebook), CodeQL (GitHub) - both use context-sensitive heap

---

**Status**: Ready for implementation after RFC-001, RFC-002, RFC-003
**Next Step**: Implement Phase 1 (Core Heap Cloning) and Test Suite 1, 4
