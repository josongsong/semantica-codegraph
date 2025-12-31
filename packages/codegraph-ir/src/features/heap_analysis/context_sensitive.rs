/*
 * RFC-004: Context-Sensitive Heap Analysis
 *
 * Implements heap cloning per call site for precise container/factory analysis.
 *
 * Algorithm:
 * 1. Track allocation sites with call context
 * 2. Clone heap objects per unique call site
 * 3. Maintain field independence
 *
 * Performance: O(k × n) where k = call sites, n = objects
 */

use rustc_hash::FxHashMap;
use std::collections::HashSet;

use crate::features::points_to::domain::{abstract_location::LocationId, constraint::VarId};

/// Call site identifier (file:line:col)
pub type CallSiteId = String;

/// Context-sensitive location (call site + allocation site)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ContextLocation {
    /// Allocation site
    pub alloc_site: LocationId,

    /// Call site context
    pub call_site: CallSiteId,
}

impl ContextLocation {
    pub fn new(alloc_site: LocationId, call_site: CallSiteId) -> Self {
        Self {
            alloc_site,
            call_site,
        }
    }

    /// Context-insensitive (no cloning)
    pub fn insensitive(alloc_site: LocationId) -> Self {
        Self {
            alloc_site,
            call_site: "global".to_string(),
        }
    }
}

/// Context-Sensitive Heap Analyzer
pub struct ContextSensitiveHeapAnalyzer {
    /// Heap object cloning enabled
    heap_cloning: bool,

    /// Global merging (singletons)
    global_merging: bool,

    /// Call site → cloned objects
    cloned_objects: FxHashMap<CallSiteId, Vec<ContextLocation>>,
}

impl ContextSensitiveHeapAnalyzer {
    pub fn new() -> Self {
        Self {
            heap_cloning: true,
            global_merging: false,
            cloned_objects: FxHashMap::default(),
        }
    }

    pub fn with_heap_cloning(mut self, enable: bool) -> Self {
        self.heap_cloning = enable;
        self
    }

    pub fn with_global_merging(mut self, enable: bool) -> Self {
        self.global_merging = enable;
        self
    }

    /// Allocate object with context
    pub fn allocate(&mut self, alloc_site: LocationId, call_site: CallSiteId) -> ContextLocation {
        if self.heap_cloning {
            // Clone per call site
            let ctx_loc = ContextLocation::new(alloc_site, call_site.clone());
            self.cloned_objects
                .entry(call_site)
                .or_default()
                .push(ctx_loc.clone());
            ctx_loc
        } else {
            // Context-insensitive
            ContextLocation::insensitive(alloc_site)
        }
    }

    /// Check if two locations may alias
    pub fn may_alias(&self, loc1: &ContextLocation, loc2: &ContextLocation) -> bool {
        if self.heap_cloning {
            // Same allocation site AND same call site
            loc1.alloc_site == loc2.alloc_site && loc1.call_site == loc2.call_site
        } else {
            // Context-insensitive
            loc1.alloc_site == loc2.alloc_site
        }
    }

    /// Get all objects allocated at a call site
    pub fn objects_at_call_site(&self, call_site: &CallSiteId) -> Vec<ContextLocation> {
        self.cloned_objects
            .get(call_site)
            .cloned()
            .unwrap_or_default()
    }
}

impl Default for ContextSensitiveHeapAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn call_site(line: u32) -> CallSiteId {
        format!("file.py:{}:0", line)
    }

    #[test]
    fn test_heap_cloning_enabled() {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new().with_heap_cloning(true);

        // Allocate at different call sites
        let loc1 = analyzer.allocate(100, call_site(1));
        let loc2 = analyzer.allocate(100, call_site(2)); // Same alloc site, different call site

        // Should NOT alias (different call sites)
        assert!(!analyzer.may_alias(&loc1, &loc2));
        assert_ne!(loc1, loc2);
    }

    #[test]
    fn test_heap_cloning_disabled() {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new().with_heap_cloning(false);

        let loc1 = analyzer.allocate(100, call_site(1));
        let loc2 = analyzer.allocate(100, call_site(2));

        // Should alias (context-insensitive)
        assert!(analyzer.may_alias(&loc1, &loc2));
    }

    #[test]
    fn test_same_call_site_aliases() {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new();

        // Same call site (loop iteration)
        let loc1 = analyzer.allocate(100, call_site(1));
        let loc2 = analyzer.allocate(100, call_site(1));

        // Should alias (same call site)
        assert!(analyzer.may_alias(&loc1, &loc2));
    }

    #[test]
    fn test_objects_tracking() {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new();

        analyzer.allocate(100, call_site(1));
        analyzer.allocate(200, call_site(1));

        let objs = analyzer.objects_at_call_site(&call_site(1));
        assert_eq!(objs.len(), 2);
    }

    #[test]
    fn test_factory_pattern() {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new();

        // Simulate: alice = create_user()
        let alice = analyzer.allocate(100, call_site(10));

        // Simulate: bob = create_user()
        let bob = analyzer.allocate(100, call_site(20));

        // Different users, no aliasing
        assert!(!analyzer.may_alias(&alice, &bob));
    }

    #[test]
    fn test_container_independence() {
        let mut analyzer = ContextSensitiveHeapAnalyzer::new();

        // list1 = []
        let list1 = analyzer.allocate(1000, call_site(1));

        // list2 = []
        let list2 = analyzer.allocate(1000, call_site(2));

        // Independent containers
        assert!(!analyzer.may_alias(&list1, &list2));
    }
}
