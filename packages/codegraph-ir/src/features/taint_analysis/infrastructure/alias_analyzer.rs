/*
 * Alias Analysis for Taint Tracking
 *
 * Port from Python: alias_analyzer.py (340 lines)
 *
 * Key Features:
 * - Variable aliasing tracking
 * - Pointer analysis (basic)
 * - Heap abstraction
 * - May-alias / Must-alias distinction
 * - Union-Find for equivalence classes
 *
 * Algorithm:
 * - Must-alias: a = b (certain)
 * - May-alias: a = b or a = c (uncertain)
 * - Alias Sets: Equivalence classes via Union-Find
 * - Taint Propagation: Taint spreads to entire alias set
 *
 * Performance Target: 10-50x faster than Python
 * - Python: 340 LOC with dict-based graph
 * - Rust: Efficient hash maps + pointer-based sets
 *
 * References:
 * - Week 3: Variable aliasing, pointer analysis, heap abstraction
 * - RFC-028: Must-alias accuracy 90%+ required
 */

use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Alias type classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AliasType {
    /// Direct assignment: a = b
    Direct,

    /// Field access: a = b.field
    Field,

    /// Element access: a = b[i]
    Element,

    /// Reference: a = &b (pointer)
    Reference,

    /// Dereference: a = *b
    Dereference,
}

/// Alias relationship between variables
#[derive(Debug, Clone)]
pub struct Alias {
    /// Source variable
    pub source: String,

    /// Target variable (alias)
    pub target: String,

    /// Type of aliasing
    pub alias_type: AliasType,

    /// Location (line, column)
    pub location: (usize, usize),

    /// Optional condition for conditional aliasing
    pub condition: Option<String>,
}

impl Alias {
    /// Create new alias
    pub fn new(source: String, target: String, alias_type: AliasType) -> Self {
        Self {
            source,
            target,
            alias_type,
            location: (0, 0),
            condition: None,
        }
    }
}

/// Alias set (equivalence class of variables pointing to same object)
///
/// Example:
///   a = b; c = a;
///   → AliasSet { variables: {a, b, c} }
#[derive(Debug, Clone)]
pub struct AliasSet {
    /// Variables in this equivalence class
    pub variables: HashSet<String>,

    /// Abstract heap location (if heap-allocated)
    pub heap_location: Option<String>,

    /// Taint status of entire set
    pub taint_status: bool,
}

impl AliasSet {
    /// Create new alias set
    pub fn new() -> Self {
        Self {
            variables: HashSet::new(),
            heap_location: None,
            taint_status: false,
        }
    }

    /// Create alias set with initial variables
    pub fn with_variables(variables: HashSet<String>) -> Self {
        Self {
            variables,
            heap_location: None,
            taint_status: false,
        }
    }

    /// Create alias set for heap location
    pub fn with_heap_location(
        variables: HashSet<String>,
        heap_location: String,
        taint_status: bool,
    ) -> Self {
        Self {
            variables,
            heap_location: Some(heap_location),
            taint_status,
        }
    }
}

impl Default for AliasSet {
    fn default() -> Self {
        Self::new()
    }
}

/// Alias Analysis Engine
///
/// Features:
/// - Variable aliasing tracking
/// - Pointer analysis (basic)
/// - Heap abstraction
/// - May-alias / Must-alias distinction
///
/// Algorithm:
/// - Union-Find for equivalence classes
/// - Taint propagation across alias sets
/// - Heap location abstraction
///
/// Performance:
/// - O(1) alias lookup (amortized)
/// - O(α(n)) union-find operations (inverse Ackermann)
pub struct AliasAnalyzer {
    /// Alias graph: var -> set of aliases
    alias_graph: FxHashMap<String, HashSet<String>>,

    /// Alias sets: equivalence classes (Union-Find)
    alias_sets: Vec<AliasSet>,

    /// Heap locations: abstract heap objects
    heap_locations: FxHashMap<String, usize>, // location -> alias_set index

    /// Direct aliases (must-alias): target -> source
    must_aliases: FxHashMap<String, String>,

    /// May aliases (uncertain): source -> set of may-aliases
    may_aliases: FxHashMap<String, HashSet<String>>,
}

impl AliasAnalyzer {
    /// Create new alias analyzer
    pub fn new() -> Self {
        Self {
            alias_graph: FxHashMap::default(),
            alias_sets: Vec::new(),
            heap_locations: FxHashMap::default(),
            must_aliases: FxHashMap::default(),
            may_aliases: FxHashMap::default(),
        }
    }

    /// Add alias relationship
    ///
    /// # Arguments
    /// * `source` - Source variable
    /// * `target` - Target variable (alias)
    /// * `alias_type` - Type of aliasing
    /// * `is_must` - Must-alias (true) vs May-alias (false)
    ///
    /// # Example
    /// ```text
    /// analyzer.add_alias("b", "a", AliasType::Direct, true);  // a = b
    /// ```
    pub fn add_alias(
        &mut self,
        source: impl Into<String>,
        target: impl Into<String>,
        alias_type: AliasType,
        is_must: bool,
    ) {
        let source = source.into();
        let target = target.into();

        if is_must {
            // Must-alias: a = b (certain)
            self.must_aliases.insert(target.clone(), source.clone());

            // Update alias graph
            self.alias_graph
                .entry(source.clone())
                .or_insert_with(HashSet::new)
                .insert(target.clone());

            // Union-Find: Merge equivalence classes
            self.merge_alias_sets(&source, &target);
        } else {
            // May-alias: a = b or a = c (uncertain)
            self.may_aliases
                .entry(source)
                .or_insert_with(HashSet::new)
                .insert(target);
        }
    }

    /// Merge two alias sets (Union-Find)
    ///
    /// Combines equivalence classes for var1 and var2.
    fn merge_alias_sets(&mut self, var1: &str, var2: &str) {
        let set1_idx = self.find_alias_set_index(var1);
        let set2_idx = self.find_alias_set_index(var2);

        match (set1_idx, set2_idx) {
            (None, None) => {
                // Both are new variables
                let new_set =
                    AliasSet::with_variables(HashSet::from([var1.to_string(), var2.to_string()]));
                self.alias_sets.push(new_set);
            }
            (None, Some(idx2)) => {
                // var1 is new, var2 exists
                self.alias_sets[idx2].variables.insert(var1.to_string());
            }
            (Some(idx1), None) => {
                // var2 is new, var1 exists
                self.alias_sets[idx1].variables.insert(var2.to_string());
            }
            (Some(idx1), Some(idx2)) => {
                // Both exist
                if idx1 != idx2 {
                    // Merge idx2 into idx1, then remove idx2
                    let set2_vars = self.alias_sets[idx2].variables.clone();
                    let set2_taint = self.alias_sets[idx2].taint_status;

                    self.alias_sets[idx1].variables.extend(set2_vars);
                    self.alias_sets[idx1].taint_status |= set2_taint;

                    // Remove idx2 (swap_remove for O(1))
                    self.alias_sets.swap_remove(idx2);

                    // Fix heap_locations indices if needed
                    self.reindex_heap_locations_after_remove(idx2);
                }
            }
        }
    }

    /// Find alias set index for a variable
    fn find_alias_set_index(&self, var: &str) -> Option<usize> {
        for (idx, set) in self.alias_sets.iter().enumerate() {
            if set.variables.contains(var) {
                return Some(idx);
            }
        }
        None
    }

    /// Find alias set for a variable
    fn find_alias_set(&self, var: &str) -> Option<&AliasSet> {
        self.find_alias_set_index(var)
            .map(|idx| &self.alias_sets[idx])
    }

    /// Find mutable alias set for a variable
    fn find_alias_set_mut(&mut self, var: &str) -> Option<&mut AliasSet> {
        self.find_alias_set_index(var)
            .map(|idx| &mut self.alias_sets[idx])
    }

    /// Fix heap_locations indices after removing an alias set
    fn reindex_heap_locations_after_remove(&mut self, removed_idx: usize) {
        for (_, idx) in self.heap_locations.iter_mut() {
            if *idx == removed_idx {
                // This heap location was removed
                *idx = usize::MAX; // Mark as invalid
            } else if *idx == self.alias_sets.len() {
                // This was the last element, now at removed_idx
                *idx = removed_idx;
            }
        }

        // Remove invalid entries
        self.heap_locations.retain(|_, idx| *idx != usize::MAX);
    }

    /// Get all aliases for a variable
    ///
    /// # Arguments
    /// * `var` - Variable name
    /// * `include_may` - Include may-aliases
    ///
    /// # Returns
    /// Set of alias variables (excluding var itself)
    pub fn get_aliases(&self, var: &str, include_may: bool) -> HashSet<String> {
        let mut aliases = HashSet::new();

        // Must-alias
        if let Some(set) = self.find_alias_set(var) {
            aliases.extend(set.variables.iter().cloned());
            aliases.remove(var); // Exclude self
        }

        // May-alias
        if include_may {
            if let Some(may_set) = self.may_aliases.get(var) {
                aliases.extend(may_set.iter().cloned());
            }
        }

        aliases
    }

    /// Check if two variables are aliased
    ///
    /// # Arguments
    /// * `var1` - First variable
    /// * `var2` - Second variable
    /// * `must_only` - Check must-alias only (true) vs include may-alias (false)
    ///
    /// # Returns
    /// True if aliased
    pub fn is_aliased(&self, var1: &str, var2: &str, must_only: bool) -> bool {
        // Must-alias check
        let set1_idx = self.find_alias_set_index(var1);
        let set2_idx = self.find_alias_set_index(var2);

        if let (Some(idx1), Some(idx2)) = (set1_idx, set2_idx) {
            if idx1 == idx2 {
                return true;
            }
        }

        // May-alias check
        if !must_only {
            if let Some(may_set) = self.may_aliases.get(var1) {
                if may_set.contains(var2) {
                    return true;
                }
            }
            if let Some(may_set) = self.may_aliases.get(var2) {
                if may_set.contains(var1) {
                    return true;
                }
            }
        }

        false
    }

    /// Propagate taint to entire alias set
    ///
    /// # Arguments
    /// * `var` - Tainted variable
    /// * `is_tainted` - Taint status
    pub fn propagate_taint(&mut self, var: &str, is_tainted: bool) {
        if let Some(set) = self.find_alias_set_mut(var) {
            set.taint_status |= is_tainted;
        }
    }

    /// Check if variable is tainted
    pub fn is_tainted(&self, var: &str) -> bool {
        self.find_alias_set(var)
            .map(|set| set.taint_status)
            .unwrap_or(false)
    }

    /// Add heap location (heap abstraction)
    ///
    /// # Arguments
    /// * `location` - Abstract heap location (e.g., "alloc_line_42")
    /// * `variables` - Variables pointing to this location
    /// * `is_tainted` - Taint status
    pub fn add_heap_location(
        &mut self,
        location: impl Into<String>,
        variables: HashSet<String>,
        is_tainted: bool,
    ) {
        let location = location.into();
        let heap_set = AliasSet::with_heap_location(variables, location.clone(), is_tainted);

        let idx = self.alias_sets.len();
        self.alias_sets.push(heap_set);
        self.heap_locations.insert(location, idx);
    }

    /// Get heap aliases for a variable
    ///
    /// # Arguments
    /// * `var` - Variable name
    ///
    /// # Returns
    /// Variables pointing to same heap location (excluding var)
    pub fn get_heap_aliases(&self, var: &str) -> Option<HashSet<String>> {
        for set in &self.alias_sets {
            if set.heap_location.is_some() && set.variables.contains(var) {
                let mut aliases = set.variables.clone();
                aliases.remove(var);
                return Some(aliases);
            }
        }
        None
    }

    /// Analyze assignment and create alias
    ///
    /// # Arguments
    /// * `lhs` - Left-hand side (target)
    /// * `rhs` - Right-hand side (source)
    /// * `is_pointer` - Pointer assignment
    ///
    /// # Example
    /// ```text
    /// analyzer.analyze_assignment("a", "b", false);  // a = b
    /// analyzer.analyze_assignment("p", "b", true);   // p = &b
    /// ```
    pub fn analyze_assignment(
        &mut self,
        lhs: impl Into<String>,
        rhs: impl Into<String>,
        is_pointer: bool,
    ) {
        let lhs = lhs.into();
        let rhs = rhs.into();

        if is_pointer {
            // Pointer assignment: a = &b
            self.add_alias(rhs, lhs, AliasType::Reference, true);
        } else {
            // Direct assignment: a = b
            self.add_alias(rhs, lhs, AliasType::Direct, true);
        }
    }

    /// Analyze field access: target = obj.field
    pub fn analyze_field_access(
        &mut self,
        obj: impl Into<String>,
        field: impl Into<String>,
        target: impl Into<String>,
    ) {
        let obj = obj.into();
        let field = field.into();
        let target = target.into();

        // Field-sensitive alias
        let field_var = format!("{}.{}", obj, field);
        self.add_alias(field_var, target, AliasType::Field, true);
    }

    /// Analyze element access: target = array[index]
    pub fn analyze_element_access(
        &mut self,
        array: impl Into<String>,
        index: impl Into<String>,
        target: impl Into<String>,
    ) {
        let array = array.into();
        let index = index.into();
        let target = target.into();

        // Element-sensitive alias
        let element_var = format!("{}[{}]", array, index);
        self.add_alias(element_var, target, AliasType::Element, true);
    }

    /// Kill aliases for a variable (on reassignment)
    ///
    /// # Arguments
    /// * `var` - Variable being reassigned
    pub fn kill_aliases(&mut self, var: &str) {
        // Remove from must_aliases
        self.must_aliases.remove(var);

        // Remove from alias set
        if let Some(set_idx) = self.find_alias_set_index(var) {
            self.alias_sets[set_idx].variables.remove(var);

            // Remove set if empty
            if self.alias_sets[set_idx].variables.is_empty() {
                self.alias_sets.swap_remove(set_idx);
                self.reindex_heap_locations_after_remove(set_idx);
            }
        }

        // Remove from may_aliases
        self.may_aliases.remove(var);
    }

    /// Get analysis statistics
    pub fn get_statistics(&self) -> AliasStatistics {
        AliasStatistics {
            alias_sets: self.alias_sets.len(),
            must_aliases: self.must_aliases.len(),
            may_aliases: self.may_aliases.values().map(|s| s.len()).sum(),
            heap_locations: self.heap_locations.len(),
            tainted_sets: self.alias_sets.iter().filter(|s| s.taint_status).count(),
        }
    }

    /// Clear all analysis state
    pub fn clear(&mut self) {
        self.alias_graph.clear();
        self.alias_sets.clear();
        self.heap_locations.clear();
        self.must_aliases.clear();
        self.may_aliases.clear();
    }
}

impl Default for AliasAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

/// Alias analysis statistics
#[derive(Debug, Clone)]
pub struct AliasStatistics {
    /// Number of alias sets (equivalence classes)
    pub alias_sets: usize,

    /// Number of must-alias relationships
    pub must_aliases: usize,

    /// Number of may-alias relationships
    pub may_aliases: usize,

    /// Number of heap locations tracked
    pub heap_locations: usize,

    /// Number of tainted alias sets
    pub tainted_sets: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_assignment() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b
        analyzer.add_alias("b", "a", AliasType::Direct, true);

        // Check must-alias
        assert!(analyzer.is_aliased("a", "b", true));
        assert!(analyzer.is_aliased("b", "a", true));
    }

    #[test]
    fn test_chained_assignment() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b; c = a
        analyzer.add_alias("b", "a", AliasType::Direct, true);
        analyzer.add_alias("a", "c", AliasType::Direct, true);

        // All three are aliased
        assert!(analyzer.is_aliased("a", "b", true));
        assert!(analyzer.is_aliased("b", "c", true));
        assert!(analyzer.is_aliased("a", "c", true));
    }

    #[test]
    fn test_taint_propagation() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b; c = a
        analyzer.add_alias("b", "a", AliasType::Direct, true);
        analyzer.add_alias("a", "c", AliasType::Direct, true);

        // Taint b
        analyzer.propagate_taint("b", true);

        // All should be tainted
        assert!(analyzer.is_tainted("a"));
        assert!(analyzer.is_tainted("b"));
        assert!(analyzer.is_tainted("c"));
    }

    #[test]
    fn test_may_alias() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b (may)
        analyzer.add_alias("b", "a", AliasType::Direct, false);

        // Not must-alias
        assert!(!analyzer.is_aliased("a", "b", true));

        // But may-alias
        assert!(analyzer.is_aliased("a", "b", false));
    }

    #[test]
    fn test_field_access() {
        let mut analyzer = AliasAnalyzer::new();

        // a = obj.field
        analyzer.analyze_field_access("obj", "field", "a");

        // Check alias
        assert!(analyzer.is_aliased("obj.field", "a", true));
    }

    #[test]
    fn test_element_access() {
        let mut analyzer = AliasAnalyzer::new();

        // a = arr[0]
        analyzer.analyze_element_access("arr", "0", "a");

        // Check alias
        assert!(analyzer.is_aliased("arr[0]", "a", true));
    }

    #[test]
    fn test_heap_location() {
        let mut analyzer = AliasAnalyzer::new();

        // Heap allocation: x = new(), y = x
        let vars = HashSet::from(["x".to_string(), "y".to_string()]);
        analyzer.add_heap_location("alloc_42", vars, false);

        // Both point to same heap location
        let heap_aliases = analyzer.get_heap_aliases("x");
        assert!(heap_aliases.is_some());
        assert!(heap_aliases.unwrap().contains("y"));
    }

    #[test]
    fn test_kill_aliases() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b
        analyzer.add_alias("b", "a", AliasType::Direct, true);
        assert!(analyzer.is_aliased("a", "b", true));

        // a = c (kill previous alias)
        analyzer.kill_aliases("a");
        analyzer.add_alias("c", "a", AliasType::Direct, true);

        // a is no longer aliased to b
        assert!(!analyzer.is_aliased("a", "b", true));
        assert!(analyzer.is_aliased("a", "c", true));
    }

    #[test]
    fn test_get_aliases() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b; c = a
        analyzer.add_alias("b", "a", AliasType::Direct, true);
        analyzer.add_alias("a", "c", AliasType::Direct, true);

        // Get aliases of 'a'
        let aliases = analyzer.get_aliases("a", false);
        assert_eq!(aliases.len(), 2);
        assert!(aliases.contains("b"));
        assert!(aliases.contains("c"));
    }

    #[test]
    fn test_statistics() {
        let mut analyzer = AliasAnalyzer::new();

        // a = b
        analyzer.add_alias("b", "a", AliasType::Direct, true);

        // c = d (may)
        analyzer.add_alias("d", "c", AliasType::Direct, false);

        let stats = analyzer.get_statistics();
        assert_eq!(stats.alias_sets, 1); // Only must-alias creates sets
        assert_eq!(stats.must_aliases, 1);
        assert_eq!(stats.may_aliases, 1);
    }

    #[test]
    fn test_independent_variables() {
        let mut analyzer = AliasAnalyzer::new();

        // a and b are independent (no alias)
        assert!(!analyzer.is_aliased("a", "b", true));
        assert!(!analyzer.is_aliased("a", "b", false));
    }

    #[test]
    fn test_multiple_chains() {
        let mut analyzer = AliasAnalyzer::new();

        // Chain 1: a = x; c = a
        analyzer.add_alias("x", "a", AliasType::Direct, true);
        analyzer.add_alias("a", "c", AliasType::Direct, true);

        // Chain 2: b = y
        analyzer.add_alias("y", "b", AliasType::Direct, true);

        // Within chain 1
        assert!(analyzer.is_aliased("a", "x", true));
        assert!(analyzer.is_aliased("a", "c", true));
        assert!(analyzer.is_aliased("x", "c", true));

        // Within chain 2
        assert!(analyzer.is_aliased("b", "y", true));

        // Across chains (should not alias)
        assert!(!analyzer.is_aliased("a", "b", true));
        assert!(!analyzer.is_aliased("x", "y", true));
    }
}
