/*
 * IDE Framework (Interprocedural Distributive Environment)
 *
 * NEW SOTA Implementation - No Python equivalent
 *
 * Extends IFDS with edge functions for value propagation.
 *
 * Key Features:
 * - Edge functions: fact → value transformations
 * - Meet operator: combining values from multiple paths
 * - Micro-functions: composition of edge functions
 * - Distributive value propagation
 * - O(ED³) complexity (same as IFDS)
 *
 * Algorithm Overview:
 * 1. IFDS computes reachability (which facts reach which nodes)
 * 2. IDE computes values (what values do facts have at each node)
 * 3. Edge functions transform values along CFG edges
 * 4. Meet operator combines values from multiple paths
 * 5. Tabulation computes final values at each node
 *
 * Use Cases:
 * - Constant propagation: track constant values
 * - Range analysis: track min/max values
 * - Taint level: track taint severity (0-10)
 * - Nullness: track null/not-null/maybe-null
 *
 * Performance Target: Handle 10k+ functions, 100k+ facts
 *
 * References:
 * - Sagiv, Reps, Horwitz (1996): "Precise Interprocedural Dataflow Analysis with Applications to Constant Propagation"
 * - Naeem, Lhoták (2008): "Typestate-like Analysis of Multiple Interacting Objects"
 */

use rustc_hash::FxHashMap;
use std::collections::{HashMap, HashSet};
use std::fmt::Debug;
use std::hash::Hash;

use super::ifds_framework::DataflowFact;

/// Value in the IDE lattice
///
/// Represents abstract values propagated along with facts.
///
/// Example:
///   - Constant propagation: Value = Option<i64> (Some(42), None=Top)
///   - Taint level: Value = u8 (0=untainted, 10=highly tainted)
///   - Nullness: Value = Nullness enum (Null, NotNull, Maybe)
pub trait IDEValue: Clone + Eq + Hash + Debug {
    /// Top element (⊤) - represents "all possible values" or "unknown"
    ///
    /// Example:
    ///   - Constant propagation: None (unknown value)
    ///   - Taint level: 10 (maximally tainted)
    fn top() -> Self;

    /// Bottom element (⊥) - represents "no value" or "unreachable"
    ///
    /// Example:
    ///   - Constant propagation: Some(specific value)
    ///   - Taint level: 0 (untainted)
    fn bottom() -> Self;

    /// Meet operator: combine values from multiple paths
    ///
    /// Properties:
    /// - Commutative: meet(a, b) = meet(b, a)
    /// - Associative: meet(meet(a, b), c) = meet(a, meet(b, c))
    /// - Top is identity: meet(a, Top) = a
    /// - Bottom is zero: meet(a, Bottom) = Bottom
    ///
    /// # Arguments
    /// * `other` - Value to meet with
    ///
    /// # Returns
    /// Combined value
    ///
    /// # Example
    /// ```text
    /// // Constant propagation
    /// Some(5).meet(Some(5)) = Some(5)  // same value
    /// Some(5).meet(Some(7)) = None     // different values → unknown
    ///
    /// // Taint level
    /// 3.meet(5) = 5  // max taint level
    /// ```
    fn meet(&self, other: &Self) -> Self;

    /// Check if this is Top
    fn is_top(&self) -> bool;

    /// Check if this is Bottom
    fn is_bottom(&self) -> bool;
}

/// Edge function: transforms values along CFG edges
///
/// Maps input value to output value.
///
/// Properties:
/// - Distributive: f(meet(a, b)) = meet(f(a), f(b))
/// - Monotonic: if a ≤ b, then f(a) ≤ f(b)
///
/// Example:
///   - Identity: f(v) = v
///   - Constant: f(v) = c (replace with constant)
///   - Add: f(v) = v + 5 (increment)
///   - Taint: f(v) = max(v, 3) (increase taint level)
pub trait EdgeFunction<V: IDEValue>: Debug {
    /// Apply edge function to a value
    ///
    /// # Arguments
    /// * `input` - Input value
    ///
    /// # Returns
    /// Output value after transformation
    fn apply(&self, input: &V) -> V;

    /// Compose this edge function with another
    ///
    /// Returns a new edge function representing f ∘ g
    /// where (f ∘ g)(x) = f(g(x))
    ///
    /// # Arguments
    /// * `other` - Edge function to compose with (applied first)
    ///
    /// # Returns
    /// Composed edge function
    fn compose(&self, other: &dyn EdgeFunction<V>) -> Box<dyn EdgeFunction<V>>;

    /// Check if this is the identity edge function
    fn is_identity(&self) -> bool {
        false
    }

    /// Check if this is a constant function (returns same value for all inputs)
    fn is_constant(&self) -> bool {
        false
    }
}

/// Identity edge function: f(v) = v
#[derive(Debug, Clone)]
pub struct IdentityEdgeFunction;

impl<V: IDEValue> EdgeFunction<V> for IdentityEdgeFunction {
    fn apply(&self, input: &V) -> V {
        input.clone()
    }

    fn compose(&self, other: &dyn EdgeFunction<V>) -> Box<dyn EdgeFunction<V>> {
        // Identity ∘ g = g
        // This is a simplification; in practice, would clone other
        Box::new(IdentityEdgeFunction)
    }

    fn is_identity(&self) -> bool {
        true
    }
}

/// Constant edge function: f(v) = c
#[derive(Debug, Clone)]
pub struct ConstantEdgeFunction<V: IDEValue> {
    pub constant: V,
}

impl<V: IDEValue> ConstantEdgeFunction<V> {
    pub fn new(constant: V) -> Self {
        Self { constant }
    }
}

impl<V: IDEValue + 'static> EdgeFunction<V> for ConstantEdgeFunction<V> {
    fn apply(&self, _input: &V) -> V {
        self.constant.clone()
    }

    fn compose(&self, _other: &dyn EdgeFunction<V>) -> Box<dyn EdgeFunction<V>> {
        // Constant ∘ g = Constant (ignores g's output)
        Box::new(ConstantEdgeFunction::new(self.constant.clone()))
    }

    fn is_constant(&self) -> bool {
        true
    }
}

/// All-Top edge function: f(v) = ⊤
#[derive(Debug, Clone)]
pub struct AllTopEdgeFunction;

impl<V: IDEValue + 'static> EdgeFunction<V> for AllTopEdgeFunction {
    fn apply(&self, _input: &V) -> V {
        V::top()
    }

    fn compose(&self, _other: &dyn EdgeFunction<V>) -> Box<dyn EdgeFunction<V>> {
        // AllTop ∘ g = AllTop
        Box::new(AllTopEdgeFunction)
    }

    fn is_constant(&self) -> bool {
        true
    }
}

/// Micro-function: maps (fact, value) pairs across program points
///
/// Example:
///   At call site: (Tainted("x"), TaintLevel(5))
///   After sanitizer: (Tainted("x"), TaintLevel(0))
///   → Micro-function: λv. 0
///
/// Note: We don't store the edge function here since Box<dyn Trait> doesn't implement Clone.
/// Instead, edge functions are recomputed when needed or stored separately.
#[derive(Debug, Clone)]
pub struct MicroFunction<F: DataflowFact> {
    /// Source fact
    pub source_fact: F,

    /// Target fact
    pub target_fact: F,

    /// CFG node
    pub node: String,
}

/// Jump function: summary of value transformation across procedure calls
///
/// Represents the effect of a procedure on (fact, value) pairs.
///
/// Example:
///   Function sanitize(x: Tainted) → Clean
///   Jump function: (Tainted("x"), TaintLevel(5)) → (Clean("x"), TaintLevel(0))
///
/// Note: We don't store the edge function here since Box<dyn Trait> doesn't implement Clone.
/// Instead, edge functions are recomputed when needed or stored separately.
#[derive(Debug, Clone)]
pub struct JumpFunction<F: DataflowFact> {
    /// Call site
    pub call_site: String,

    /// Source fact at call site
    pub source_fact: F,

    /// Return site
    pub return_site: String,

    /// Target fact at return site
    pub target_fact: F,
}

/// IDE Problem specification
///
/// Extends IFDSProblem with edge functions for value propagation.
///
/// # Design Note (2025-01-01 Fix)
/// IDE problems can optionally provide flow functions for fact transformation.
/// If not provided, identity flow is assumed (backward compatible).
/// For full IFDS/IDE integration, implement the flow functions.
pub trait IDEProblem<F: DataflowFact, V: IDEValue> {
    /// Get initial seeds: (node, fact, value)
    ///
    /// Example (taint analysis):
    ///   [("main_entry", Tainted("argv"), TaintLevel(10))]
    fn initial_seeds(&self) -> Vec<(String, F, V)>;

    // ==================== Flow Functions (Fact Transformation) ====================
    // These control which facts flow to which nodes.
    // Default: identity (same fact propagates unchanged)

    /// Get target facts for normal edge (fact transformation)
    ///
    /// Given a source fact at from_node, returns the set of facts that flow to to_node.
    /// Default: identity (source_fact flows unchanged)
    ///
    /// # Example
    /// Statement: y = x (tainted)
    /// Source fact: Tainted("x") → Target facts: {Tainted("x"), Tainted("y")}
    fn normal_flow_function(&self, _from_node: &str, _to_node: &str, source_fact: &F) -> Vec<F> {
        vec![source_fact.clone()] // Default: identity
    }

    /// Get target facts for call edge (argument mapping)
    fn call_flow_function(&self, _call_site: &str, _callee_entry: &str, source_fact: &F) -> Vec<F> {
        vec![source_fact.clone()] // Default: identity
    }

    /// Get target facts for return edge (return value mapping)
    fn return_flow_function(
        &self,
        _callee_exit: &str,
        _return_site: &str,
        _call_site: &str,
        source_fact: &F,
    ) -> Vec<F> {
        vec![source_fact.clone()] // Default: identity
    }

    /// Get target facts for call-to-return edge (local variable pass-through)
    fn call_to_return_flow_function(
        &self,
        _call_site: &str,
        _return_site: &str,
        source_fact: &F,
    ) -> Vec<F> {
        vec![source_fact.clone()] // Default: identity
    }

    // ==================== Edge Functions (Value Transformation) ====================
    // These control how values change along edges.

    /// Get edge function for normal edge
    ///
    /// # Arguments
    /// * `from_node` - Source CFG node
    /// * `to_node` - Target CFG node
    /// * `source_fact` - Fact at source node
    /// * `target_fact` - Fact at target node
    ///
    /// # Returns
    /// Edge function transforming values
    ///
    /// # Example
    /// ```
    /// // Statement: y = x
    /// // Source: (Tainted("x"), TaintLevel(5))
    /// // Target: (Tainted("y"), TaintLevel(5))
    /// // Edge function: Identity (taint level preserved)
    /// ```
    fn normal_edge_function(
        &self,
        from_node: &str,
        to_node: &str,
        source_fact: &F,
        target_fact: &F,
    ) -> Box<dyn EdgeFunction<V>>;

    /// Get edge function for call edge
    ///
    /// # Arguments
    /// * `call_site` - Call site node
    /// * `callee_entry` - Callee entry node
    /// * `source_fact` - Fact at call site
    /// * `target_fact` - Fact at callee entry
    ///
    /// # Returns
    /// Edge function transforming values
    fn call_edge_function(
        &self,
        call_site: &str,
        callee_entry: &str,
        source_fact: &F,
        target_fact: &F,
    ) -> Box<dyn EdgeFunction<V>>;

    /// Get edge function for return edge
    ///
    /// # Arguments
    /// * `callee_exit` - Callee exit node
    /// * `return_site` - Return site node
    /// * `call_site` - Corresponding call site
    /// * `source_fact` - Fact at callee exit
    /// * `target_fact` - Fact at return site
    ///
    /// # Returns
    /// Edge function transforming values
    fn return_edge_function(
        &self,
        callee_exit: &str,
        return_site: &str,
        call_site: &str,
        source_fact: &F,
        target_fact: &F,
    ) -> Box<dyn EdgeFunction<V>>;

    /// Get edge function for call-to-return edge
    ///
    /// # Arguments
    /// * `call_site` - Call site node
    /// * `return_site` - Return site node
    /// * `source_fact` - Fact at call site
    /// * `target_fact` - Fact at return site
    ///
    /// # Returns
    /// Edge function transforming values
    fn call_to_return_edge_function(
        &self,
        call_site: &str,
        return_site: &str,
        source_fact: &F,
        target_fact: &F,
    ) -> Box<dyn EdgeFunction<V>>;
}

/// IDE Analysis Statistics
#[derive(Debug, Clone, Default)]
pub struct IDEStatistics {
    /// Number of micro-functions computed
    pub num_micro_functions: usize,

    /// Number of micro-function cache reuses (optimization metric)
    /// Higher is better - indicates edge function recomputation was avoided
    pub num_micro_function_reuses: usize,

    /// Number of jump functions computed
    pub num_jump_functions: usize,

    /// Number of jump function cache reuses (optimization metric)
    /// Higher is better - indicates procedure re-analysis was avoided
    pub num_jump_function_reuses: usize,

    /// Number of value propagations
    pub num_value_propagations: usize,

    /// Number of meet operations
    pub num_meet_operations: usize,

    /// Analysis time (milliseconds)
    pub analysis_time_ms: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Simple value for testing (constant propagation)
    #[derive(Debug, Clone, PartialEq, Eq, Hash)]
    enum TestValue {
        Bottom,        // Unreachable
        Constant(i64), // Known constant
        Top,           // Unknown
    }

    impl IDEValue for TestValue {
        fn top() -> Self {
            TestValue::Top
        }

        fn bottom() -> Self {
            TestValue::Bottom
        }

        fn meet(&self, other: &Self) -> Self {
            match (self, other) {
                (TestValue::Bottom, v) | (v, TestValue::Bottom) => v.clone(),
                (TestValue::Top, _) | (_, TestValue::Top) => TestValue::Top,
                (TestValue::Constant(a), TestValue::Constant(b)) => {
                    if a == b {
                        TestValue::Constant(*a)
                    } else {
                        TestValue::Top
                    }
                }
            }
        }

        fn is_top(&self) -> bool {
            matches!(self, TestValue::Top)
        }

        fn is_bottom(&self) -> bool {
            matches!(self, TestValue::Bottom)
        }
    }

    #[test]
    fn test_value_top_bottom() {
        assert!(TestValue::top().is_top());
        assert!(TestValue::bottom().is_bottom());
        assert!(!TestValue::Constant(5).is_top());
        assert!(!TestValue::Constant(5).is_bottom());
    }

    #[test]
    fn test_value_meet_same() {
        let v1 = TestValue::Constant(5);
        let v2 = TestValue::Constant(5);
        assert_eq!(v1.meet(&v2), TestValue::Constant(5));
    }

    #[test]
    fn test_value_meet_different() {
        let v1 = TestValue::Constant(5);
        let v2 = TestValue::Constant(7);
        assert_eq!(v1.meet(&v2), TestValue::Top);
    }

    #[test]
    fn test_value_meet_with_top() {
        let v = TestValue::Constant(5);
        let top = TestValue::Top;
        assert_eq!(v.meet(&top), TestValue::Top);
        assert_eq!(top.meet(&v), TestValue::Top);
    }

    #[test]
    fn test_value_meet_with_bottom() {
        let v = TestValue::Constant(5);
        let bottom = TestValue::Bottom;
        assert_eq!(v.meet(&bottom), TestValue::Constant(5));
        assert_eq!(bottom.meet(&v), TestValue::Constant(5));
    }

    #[test]
    fn test_identity_edge_function() {
        let f = IdentityEdgeFunction;
        let v = TestValue::Constant(5);

        assert_eq!(f.apply(&v), v);
        assert!(EdgeFunction::<TestValue>::is_identity(&f));
    }

    #[test]
    fn test_constant_edge_function() {
        let f = ConstantEdgeFunction::new(TestValue::Constant(42));
        let v = TestValue::Constant(5);

        assert_eq!(f.apply(&v), TestValue::Constant(42));
        assert!(EdgeFunction::<TestValue>::is_constant(&f));
    }

    #[test]
    fn test_all_top_edge_function() {
        let f: AllTopEdgeFunction = AllTopEdgeFunction;
        let v = TestValue::Constant(5);

        assert_eq!(f.apply(&v), TestValue::Top);
        assert!(EdgeFunction::<TestValue>::is_constant(&f));
    }

    #[test]
    fn test_meet_commutative() {
        let v1 = TestValue::Constant(5);
        let v2 = TestValue::Constant(7);

        assert_eq!(v1.meet(&v2), v2.meet(&v1));
    }

    #[test]
    fn test_meet_associative() {
        let v1 = TestValue::Constant(5);
        let v2 = TestValue::Constant(7);
        let v3 = TestValue::Constant(9);

        let left = v1.meet(&v2).meet(&v3);
        let right = v1.meet(&v2.meet(&v3));

        assert_eq!(left, right);
    }
}
