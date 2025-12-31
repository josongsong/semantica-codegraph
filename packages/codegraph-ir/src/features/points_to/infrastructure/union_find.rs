//! Union-Find (Disjoint Set Union) Data Structure
//!
//! Optimized implementation with:
//! - Path compression: O(α(n)) find operations
//! - Union by rank: Balanced trees
//! - Weighted quick-union: Track set sizes
//!
//! Essential for Steensgaard's O(n·α(n)) pointer analysis.
//!
//! # References
//! - Tarjan, R. E. "Efficiency of a Good But Not Linear Set Union Algorithm" (1975)
//! - Steensgaard, B. "Points-to Analysis in Almost Linear Time" (POPL 1996)

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Union-Find with path compression and union by rank
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnionFind {
    /// Parent pointers (self-loop = root)
    parent: Vec<u32>,

    /// Rank (tree height upper bound) for union by rank
    rank: Vec<u8>,

    /// Size of each set (only valid for roots)
    size: Vec<u32>,

    /// Number of disjoint sets
    set_count: usize,
}

impl Default for UnionFind {
    fn default() -> Self {
        Self::empty()
    }
}

impl UnionFind {
    /// Create a new Union-Find with n elements (0..n-1)
    pub fn new(n: usize) -> Self {
        Self {
            parent: (0..n as u32).collect(),
            rank: vec![0; n],
            size: vec![1; n],
            set_count: n,
        }
    }

    /// Create an empty Union-Find (for dynamic element addition)
    pub fn empty() -> Self {
        Self {
            parent: Vec::new(),
            rank: Vec::new(),
            size: Vec::new(),
            set_count: 0,
        }
    }

    /// Ensure element exists in the structure
    pub fn make_set(&mut self, x: u32) {
        let idx = x as usize;
        let old_len = self.parent.len();
        if idx >= old_len {
            let new_size = idx + 1;
            self.parent.resize(new_size, 0);
            self.rank.resize(new_size, 0);
            self.size.resize(new_size, 0);

            // Initialize new elements as singletons
            for i in old_len..new_size {
                self.parent[i] = i as u32;
                self.size[i] = 1;
            }
            // Update set_count: each new element is its own set
            self.set_count += new_size - old_len;
        }
    }

    /// Find the representative (root) of element x with path compression
    ///
    /// Complexity: O(α(n)) amortized where α is inverse Ackermann function
    #[inline]
    pub fn find(&mut self, x: u32) -> u32 {
        let idx = x as usize;
        if idx >= self.parent.len() {
            self.make_set(x);
            return x;
        }

        // Path compression with recursion
        if self.parent[idx] != x {
            self.parent[idx] = self.find(self.parent[idx]);
        }
        self.parent[idx]
    }

    /// Find without path compression (for read-only queries)
    #[inline]
    pub fn find_readonly(&self, x: u32) -> u32 {
        let mut current = x;
        while self.parent[current as usize] != current {
            current = self.parent[current as usize];
        }
        current
    }

    /// Union two sets by rank
    ///
    /// Returns the new representative
    ///
    /// Complexity: O(α(n)) amortized
    pub fn union(&mut self, x: u32, y: u32) -> u32 {
        let root_x = self.find(x);
        let root_y = self.find(y);

        if root_x == root_y {
            return root_x; // Already in same set
        }

        let rx = root_x as usize;
        let ry = root_y as usize;

        // Union by rank (attach smaller tree under larger)
        let new_root = if self.rank[rx] < self.rank[ry] {
            self.parent[rx] = root_y;
            self.size[ry] += self.size[rx];
            root_y
        } else if self.rank[rx] > self.rank[ry] {
            self.parent[ry] = root_x;
            self.size[rx] += self.size[ry];
            root_x
        } else {
            // Equal ranks, pick x as root and increment its rank
            self.parent[ry] = root_x;
            self.size[rx] += self.size[ry];
            self.rank[rx] += 1;
            root_x
        };

        self.set_count -= 1;
        new_root
    }

    /// Check if two elements are in the same set
    #[inline]
    pub fn connected(&mut self, x: u32, y: u32) -> bool {
        self.find(x) == self.find(y)
    }

    /// Check connectivity without modifying structure
    #[inline]
    pub fn connected_readonly(&self, x: u32, y: u32) -> bool {
        self.find_readonly(x) == self.find_readonly(y)
    }

    /// Get the size of the set containing x
    #[inline]
    pub fn set_size(&mut self, x: u32) -> u32 {
        let root = self.find(x);
        self.size[root as usize]
    }

    /// Number of disjoint sets
    #[inline]
    pub fn count(&self) -> usize {
        self.set_count
    }

    /// Total number of elements
    #[inline]
    pub fn len(&self) -> usize {
        self.parent.len()
    }

    /// Check if empty
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.parent.is_empty()
    }

    /// Get all elements in the same set as x
    pub fn get_set(&mut self, x: u32) -> Vec<u32> {
        let root = self.find(x);
        (0..self.parent.len() as u32)
            .filter(|&e| self.find(e) == root)
            .collect()
    }

    /// Get all roots (set representatives)
    pub fn get_roots(&self) -> Vec<u32> {
        (0..self.parent.len())
            .filter(|&i| self.parent[i] == i as u32)
            .map(|i| i as u32)
            .collect()
    }

    /// Get all sets as a map: root → [members]
    pub fn get_all_sets(&mut self) -> HashMap<u32, Vec<u32>> {
        let mut sets: HashMap<u32, Vec<u32>> = HashMap::new();
        for i in 0..self.parent.len() as u32 {
            let root = self.find(i);
            sets.entry(root).or_default().push(i);
        }
        sets
    }

    /// Reset to initial state (all singletons)
    pub fn reset(&mut self) {
        for i in 0..self.parent.len() {
            self.parent[i] = i as u32;
            self.rank[i] = 0;
            self.size[i] = 1;
        }
        self.set_count = self.parent.len();
    }
}

/// Specialized Union-Find for string-keyed elements
#[derive(Debug, Clone, Default)]
pub struct StringUnionFind {
    /// String → ID mapping
    string_to_id: HashMap<String, u32>,

    /// ID → String mapping
    id_to_string: Vec<String>,

    /// Underlying Union-Find
    uf: UnionFind,
}

impl StringUnionFind {
    pub fn new() -> Self {
        Self {
            string_to_id: HashMap::new(),
            id_to_string: Vec::new(),
            uf: UnionFind::empty(),
        }
    }

    /// Get or create ID for a string
    fn get_or_create_id(&mut self, s: &str) -> u32 {
        if let Some(&id) = self.string_to_id.get(s) {
            return id;
        }

        let id = self.id_to_string.len() as u32;
        self.string_to_id.insert(s.to_string(), id);
        self.id_to_string.push(s.to_string());
        self.uf.make_set(id);
        id
    }

    /// Find representative for a string
    pub fn find(&mut self, s: &str) -> String {
        let id = self.get_or_create_id(s);
        let root_id = self.uf.find(id);
        self.id_to_string[root_id as usize].clone()
    }

    /// Union two string sets
    pub fn union(&mut self, s1: &str, s2: &str) -> String {
        let id1 = self.get_or_create_id(s1);
        let id2 = self.get_or_create_id(s2);
        let root_id = self.uf.union(id1, id2);
        self.id_to_string[root_id as usize].clone()
    }

    /// Check if two strings are in the same set
    pub fn connected(&mut self, s1: &str, s2: &str) -> bool {
        let id1 = self.get_or_create_id(s1);
        let id2 = self.get_or_create_id(s2);
        self.uf.connected(id1, id2)
    }

    /// Number of elements
    #[inline]
    pub fn len(&self) -> usize {
        self.id_to_string.len()
    }

    /// Check if empty
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.id_to_string.is_empty()
    }

    /// Number of disjoint sets
    #[inline]
    pub fn count(&self) -> usize {
        self.uf.count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_union_find() {
        let mut uf = UnionFind::new(10);

        // Initially all separate
        assert_eq!(uf.count(), 10);
        assert!(!uf.connected(0, 1));

        // Union some elements
        uf.union(0, 1);
        uf.union(2, 3);
        assert!(uf.connected(0, 1));
        assert!(uf.connected(2, 3));
        assert!(!uf.connected(0, 2));
        assert_eq!(uf.count(), 8);

        // Chain union
        uf.union(1, 2); // Merges {0,1} with {2,3}
        assert!(uf.connected(0, 3));
        assert_eq!(uf.count(), 7);
    }

    #[test]
    fn test_set_size() {
        let mut uf = UnionFind::new(5);

        uf.union(0, 1);
        uf.union(1, 2);

        assert_eq!(uf.set_size(0), 3);
        assert_eq!(uf.set_size(1), 3);
        assert_eq!(uf.set_size(2), 3);
        assert_eq!(uf.set_size(3), 1);
        assert_eq!(uf.set_size(4), 1);
    }

    #[test]
    fn test_path_compression() {
        let mut uf = UnionFind::new(100);

        // Create a long chain
        for i in 0..99 {
            uf.union(i, i + 1);
        }

        // After find, should have flat structure
        uf.find(0);
        let root = uf.find(99);

        // All should point to same root with short path
        for i in 0..100 {
            assert_eq!(uf.find(i), root);
        }
    }

    #[test]
    fn test_get_set() {
        let mut uf = UnionFind::new(5);
        uf.union(0, 1);
        uf.union(1, 2);

        let mut set = uf.get_set(0);
        set.sort();
        assert_eq!(set, vec![0, 1, 2]);
    }

    #[test]
    fn test_string_union_find() {
        let mut suf = StringUnionFind::new();

        suf.union("x", "y");
        suf.union("a", "b");

        assert!(suf.connected("x", "y"));
        assert!(suf.connected("a", "b"));
        assert!(!suf.connected("x", "a"));

        suf.union("y", "a");
        assert!(suf.connected("x", "b"));
    }

    #[test]
    fn test_dynamic_make_set() {
        let mut uf = UnionFind::empty();

        uf.make_set(5);
        uf.make_set(10);

        assert_eq!(uf.find(5), 5);
        assert_eq!(uf.find(10), 10);

        uf.union(5, 10);
        assert!(uf.connected(5, 10));
    }
}
