//! Strongly Connected Component Detection
//!
//! Implements Tarjan's and Kosaraju's SCC algorithms for cycle detection
//! in the constraint graph. SCCs are collapsed for O(n²) → O(n) optimization.
//!
//! # Why SCC Detection?
//! In constraint graphs like:
//!   x ⊇ y, y ⊇ z, z ⊇ x (cycle)
//!
//! All variables in the cycle have the same points-to set.
//! Collapsing them to a single representative reduces work.
//!
//! # References
//! - Tarjan, R. "Depth-First Search and Linear Graph Algorithms" (1972)
//! - Nuutila, E. "On Finding the Strongly Connected Components" (1994)

use rustc_hash::{FxHashMap, FxHashSet};
use std::cmp::min;

/// Result of SCC detection
#[derive(Debug, Clone)]
pub struct SCCResult {
    /// Mapping from variable to SCC representative
    pub var_to_rep: FxHashMap<u32, u32>,

    /// All SCCs (only cycles with >1 member)
    pub sccs: Vec<FxHashSet<u32>>,

    /// Statistics
    pub stats: SCCStats,
}

#[derive(Debug, Clone, Default)]
pub struct SCCStats {
    pub total_nodes: usize,
    pub total_edges: usize,
    pub scc_count: usize,
    pub largest_scc: usize,
    pub collapsed_nodes: usize,
}

/// Tarjan's SCC algorithm
///
/// Time: O(V + E)
/// Space: O(V)
pub fn tarjan_scc(edges: &[(u32, u32)]) -> SCCResult {
    // Build adjacency list
    let mut adj: FxHashMap<u32, Vec<u32>> = FxHashMap::default();
    let mut all_nodes: FxHashSet<u32> = FxHashSet::default();

    for &(src, dst) in edges {
        adj.entry(src).or_default().push(dst);
        all_nodes.insert(src);
        all_nodes.insert(dst);
        adj.entry(dst).or_default();
    }

    let mut state = TarjanState::new();

    // Run DFS from all unvisited nodes
    for &node in &all_nodes {
        if !state.index.contains_key(&node) {
            tarjan_dfs(node, &adj, &mut state);
        }
    }

    // Build set of self-loop nodes for special handling
    let self_loop_nodes: FxHashSet<u32> = edges
        .iter()
        .filter(|(src, dst)| src == dst)
        .map(|(src, _)| *src)
        .collect();

    // Build result
    let mut var_to_rep: FxHashMap<u32, u32> = FxHashMap::default();
    let mut actual_sccs = Vec::new();
    let mut collapsed = 0;

    for scc in &state.sccs {
        // SCC is meaningful if:
        // 1. Size > 1 (regular cycle), OR
        // 2. Size == 1 but has self-loop (node points to itself)
        let is_cycle = scc.len() > 1
            || (scc.len() == 1 && self_loop_nodes.contains(scc.iter().next().unwrap()));

        if is_cycle {
            // Pick representative (minimum for determinism)
            let rep = *scc.iter().min().unwrap();
            for &member in scc {
                var_to_rep.insert(member, rep);
            }
            if scc.len() > 1 {
                collapsed += scc.len() - 1;
            }
            actual_sccs.push(scc.clone());
        }
    }

    let largest = state.sccs.iter().map(|s| s.len()).max().unwrap_or(0);

    SCCResult {
        var_to_rep,
        sccs: actual_sccs.clone(),
        stats: SCCStats {
            total_nodes: all_nodes.len(),
            total_edges: edges.len(),
            scc_count: actual_sccs.len(), // Includes self-loops as valid SCCs
            largest_scc: largest,
            collapsed_nodes: collapsed,
        },
    }
}

struct TarjanState {
    index: FxHashMap<u32, usize>,
    lowlink: FxHashMap<u32, usize>,
    on_stack: FxHashSet<u32>,
    stack: Vec<u32>,
    current_index: usize,
    sccs: Vec<FxHashSet<u32>>,
}

impl TarjanState {
    fn new() -> Self {
        Self {
            index: FxHashMap::default(),
            lowlink: FxHashMap::default(),
            on_stack: FxHashSet::default(),
            stack: Vec::new(),
            current_index: 0,
            sccs: Vec::new(),
        }
    }
}

fn tarjan_dfs(v: u32, adj: &FxHashMap<u32, Vec<u32>>, state: &mut TarjanState) {
    // Set index and lowlink for v
    state.index.insert(v, state.current_index);
    state.lowlink.insert(v, state.current_index);
    state.current_index += 1;
    state.stack.push(v);
    state.on_stack.insert(v);

    // Visit all successors
    if let Some(neighbors) = adj.get(&v) {
        for &w in neighbors {
            if !state.index.contains_key(&w) {
                // Not visited: recurse
                tarjan_dfs(w, adj, state);
                let new_lowlink = min(state.lowlink[&v], state.lowlink[&w]);
                state.lowlink.insert(v, new_lowlink);
            } else if state.on_stack.contains(&w) {
                // On stack: update lowlink
                let new_lowlink = min(state.lowlink[&v], state.index[&w]);
                state.lowlink.insert(v, new_lowlink);
            }
        }
    }

    // If v is a root node, pop the stack and generate SCC
    if state.lowlink[&v] == state.index[&v] {
        let mut scc = FxHashSet::default();
        loop {
            let w = state.stack.pop().unwrap();
            state.on_stack.remove(&w);
            scc.insert(w);
            if w == v {
                break;
            }
        }
        state.sccs.push(scc);
    }
}

/// Simplified SCC detection for constraint graphs
///
/// Only considers COPY constraints (x = y creates edge y → x)
pub fn detect_copy_cycles(constraints: &[(u32, u32)]) -> SCCResult {
    tarjan_scc(constraints)
}

/// Detect SCCs with parallel processing for large graphs
#[cfg(feature = "parallel")]
pub fn tarjan_scc_parallel(edges: &[(u32, u32)]) -> SCCResult {
    use rayon::prelude::*;

    // For small graphs, use sequential
    if edges.len() < 10000 {
        return tarjan_scc(edges);
    }

    // Build adjacency list in parallel
    let adj: FxHashMap<u32, Vec<u32>> = edges
        .par_iter()
        .fold(
            || FxHashMap::<u32, Vec<u32>>::default(),
            |mut acc: FxHashMap<u32, Vec<u32>>, &(src, dst)| {
                acc.entry(src).or_default().push(dst);
                acc
            },
        )
        .reduce(
            || FxHashMap::<u32, Vec<u32>>::default(),
            |mut a, b| {
                for (k, v) in b {
                    a.entry(k).or_default().extend(v);
                }
                a
            },
        );

    // Run Tarjan's (sequential for correctness)
    let mut all_nodes: FxHashSet<u32> = FxHashSet::default();
    for &(src, dst) in edges {
        all_nodes.insert(src);
        all_nodes.insert(dst);
    }

    let mut state = TarjanState::new();
    for &node in &all_nodes {
        if !state.index.contains_key(&node) {
            tarjan_dfs(node, &adj, &mut state);
        }
    }

    // Build result
    let mut var_to_rep: FxHashMap<u32, u32> = FxHashMap::default();
    let mut actual_sccs = Vec::new();
    let mut collapsed = 0;

    for scc in &state.sccs {
        if scc.len() > 1 {
            let rep = *scc.iter().min().unwrap();
            for &member in scc {
                var_to_rep.insert(member, rep);
            }
            collapsed += scc.len() - 1;
            actual_sccs.push(scc.clone());
        }
    }

    SCCResult {
        var_to_rep,
        sccs: actual_sccs,
        stats: SCCStats {
            total_nodes: all_nodes.len(),
            total_edges: edges.len(),
            scc_count: state.sccs.iter().filter(|s| s.len() > 1).count(),
            largest_scc: state.sccs.iter().map(|s| s.len()).max().unwrap_or(0),
            collapsed_nodes: collapsed,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_cycle() {
        // A → B → C → A
        let edges = vec![(1, 2), (2, 3), (3, 1)];
        let result = tarjan_scc(&edges);

        assert_eq!(result.stats.scc_count, 1);
        assert_eq!(result.sccs[0].len(), 3);
        assert!(result.sccs[0].contains(&1));
        assert!(result.sccs[0].contains(&2));
        assert!(result.sccs[0].contains(&3));
    }

    #[test]
    fn test_no_cycle() {
        // A → B → C (chain, no cycle)
        let edges = vec![(1, 2), (2, 3)];
        let result = tarjan_scc(&edges);

        // No SCC with >1 member
        assert_eq!(result.stats.scc_count, 0);
        assert!(result.var_to_rep.is_empty());
    }

    #[test]
    fn test_multiple_sccs() {
        // Two separate cycles: (1,2,3) and (4,5)
        let edges = vec![
            (1, 2),
            (2, 3),
            (3, 1), // Cycle 1
            (4, 5),
            (5, 4), // Cycle 2
        ];
        let result = tarjan_scc(&edges);

        assert_eq!(result.stats.scc_count, 2);
    }

    #[test]
    fn test_self_loop() {
        // Self-loop: A → A
        let edges = vec![(1, 1)];
        let result = tarjan_scc(&edges);

        assert_eq!(result.stats.scc_count, 1);
        assert!(result.sccs[0].contains(&1));
    }

    #[test]
    fn test_scc_representative() {
        // Cycle: 5 → 3 → 7 → 5
        let edges = vec![(5, 3), (3, 7), (7, 5)];
        let result = tarjan_scc(&edges);

        // Representative should be minimum (3)
        assert_eq!(result.var_to_rep.get(&5), Some(&3));
        assert_eq!(result.var_to_rep.get(&7), Some(&3));
        assert_eq!(result.var_to_rep.get(&3), Some(&3));
    }
}
