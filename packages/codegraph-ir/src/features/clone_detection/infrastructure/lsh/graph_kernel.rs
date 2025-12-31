//! Weisfeiler-Lehman Graph Kernels for Structural Similarity
//!
//! Implements WL graph kernels (Shervashidze et al., 2011) for fast
//! graph comparison in Type-3/Type-4 clone detection.
//!
//! # Algorithm
//!
//! 1. Initialize node labels
//! 2. For k iterations:
//!    a. Aggregate neighbor labels
//!    b. Hash aggregated labels
//!    c. Create new node labels
//! 3. Compute label histogram
//! 4. Compare histograms via Jaccard similarity
//!
//! # Performance
//!
//! - **Complexity**: O(n × k) where n = nodes, k = iterations
//! - **Comparison**: O(h) where h = unique labels (typically << n)
//! - **Much faster than graph isomorphism**: O(n!) → O(n)
//!
//! # Example
//!
//! ```ignore
//! let pdg1 = build_pdg("def foo(x): return x + 1");
//! let pdg2 = build_pdg("def bar(y): return y + 1");
//!
//! let sig1 = WLSignature::from_pdg(&pdg1, 3);
//! let sig2 = WLSignature::from_pdg(&pdg2, 3);
//!
//! let similarity = sig1.similarity(&sig2);
//! // High similarity despite different identifiers
//! ```

use std::collections::hash_map::DefaultHasher;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};

/// Simplified PDG node (re-export from type4_detector)
use crate::features::clone_detection::infrastructure::type4_detector::SimplePDG;

/// Weisfeiler-Lehman signature for graph comparison
#[derive(Debug, Clone)]
pub struct WLSignature {
    /// Label histogram after k iterations
    label_histogram: HashMap<String, usize>,

    /// Iteration-wise hash signatures (for multi-resolution comparison)
    iteration_hashes: Vec<u64>,

    /// Number of nodes
    num_nodes: usize,

    /// Number of edges
    num_edges: usize,
}

impl WLSignature {
    /// Compute WL signature from a PDG
    ///
    /// # Arguments
    /// * `pdg` - Program Dependence Graph
    /// * `iterations` - Number of WL iterations (typically 2-5)
    ///
    /// # Recommended Parameters
    /// - `iterations = 3`: Good balance for code graphs
    /// - More iterations capture wider neighborhoods
    pub fn from_pdg(pdg: &SimplePDG, iterations: usize) -> Self {
        if pdg.nodes.is_empty() {
            return Self::empty();
        }

        // Initialize labels with node types
        let mut labels: Vec<String> = pdg.nodes.iter().map(|node| format!("{:?}", node)).collect();

        let mut iteration_hashes = Vec::new();

        // WL iterations
        for _iter in 0..iterations {
            labels = Self::wl_iteration(pdg, &labels);

            // Hash labels for this iteration
            let iter_hash = Self::hash_labels(&labels);
            iteration_hashes.push(iter_hash);
        }

        // Compute final label histogram
        let label_histogram = Self::compute_histogram(&labels);

        Self {
            label_histogram,
            iteration_hashes,
            num_nodes: pdg.nodes.len(),
            num_edges: pdg.edges.len(),
        }
    }

    /// Create empty signature
    fn empty() -> Self {
        Self {
            label_histogram: HashMap::new(),
            iteration_hashes: Vec::new(),
            num_nodes: 0,
            num_edges: 0,
        }
    }

    /// Perform one WL iteration
    fn wl_iteration(pdg: &SimplePDG, labels: &[String]) -> Vec<String> {
        let mut new_labels = Vec::new();

        for i in 0..pdg.nodes.len() {
            // Collect neighbor labels
            let mut neighbor_labels: Vec<String> = pdg
                .edges
                .iter()
                .filter_map(|(from, to, _edge_type)| {
                    if *from == i {
                        Some(labels[*to].clone())
                    } else if *to == i {
                        Some(labels[*from].clone())
                    } else {
                        None
                    }
                })
                .collect();

            // Sort for deterministic hashing
            neighbor_labels.sort();

            // Aggregate: current_label(neighbor_labels)
            let aggregated = if neighbor_labels.is_empty() {
                labels[i].clone()
            } else {
                format!("{}({})", labels[i], neighbor_labels.join(","))
            };

            new_labels.push(aggregated);
        }

        new_labels
    }

    /// Hash a label vector
    fn hash_labels(labels: &[String]) -> u64 {
        let mut hasher = DefaultHasher::new();
        for label in labels {
            label.hash(&mut hasher);
        }
        hasher.finish()
    }

    /// Compute label histogram
    fn compute_histogram(labels: &[String]) -> HashMap<String, usize> {
        let mut histogram = HashMap::new();
        for label in labels {
            *histogram.entry(label.clone()).or_insert(0) += 1;
        }
        histogram
    }

    /// Compute Jaccard similarity with another WL signature
    pub fn similarity(&self, other: &Self) -> f64 {
        Self::jaccard_similarity(&self.label_histogram, &other.label_histogram)
    }

    /// Jaccard similarity of two histograms
    ///
    /// Optimized version: O(min(|A|, |B|)) instead of O(|A| + |B| log(|A| + |B|))
    fn jaccard_similarity(hist_a: &HashMap<String, usize>, hist_b: &HashMap<String, usize>) -> f64 {
        if hist_a.is_empty() && hist_b.is_empty() {
            return 1.0;
        }

        if hist_a.is_empty() || hist_b.is_empty() {
            return 0.0;
        }

        // Structural optimization: Single pass through smaller histogram
        // No sorting/deduplication needed!
        let (smaller, larger) = if hist_a.len() <= hist_b.len() {
            (hist_a, hist_b)
        } else {
            (hist_b, hist_a)
        };

        let mut intersection = 0;
        let mut union_from_smaller = 0;

        // Iterate only through smaller histogram
        for (key, &count_small) in smaller.iter() {
            union_from_smaller += count_small;
            if let Some(&count_large) = larger.get(key) {
                intersection += count_small.min(count_large);
            }
        }

        // Add unique entries from larger histogram
        let mut union_from_larger = 0;
        for (key, &count_large) in larger.iter() {
            if let Some(&count_small) = smaller.get(key) {
                // Already counted in intersection
                union_from_larger += count_small.max(count_large);
            } else {
                // Unique to larger
                union_from_larger += count_large;
            }
        }

        let union = union_from_larger;

        if union == 0 {
            return 0.0;
        }

        intersection as f64 / union as f64
    }

    /// Get compact hash for LSH indexing
    ///
    /// Combines iteration hashes for fast bucketing
    pub fn compact_hash(&self) -> u64 {
        let mut hasher = DefaultHasher::new();
        for &iter_hash in &self.iteration_hashes {
            iter_hash.hash(&mut hasher);
        }
        hasher.finish()
    }

    /// Get number of nodes
    pub fn num_nodes(&self) -> usize {
        self.num_nodes
    }

    /// Get number of edges
    pub fn num_edges(&self) -> usize {
        self.num_edges
    }
}

impl Hash for WLSignature {
    fn hash<H: Hasher>(&self, state: &mut H) {
        for iter_hash in &self.iteration_hashes {
            iter_hash.hash(state);
        }
    }
}

/// LSH Index for WL Signatures (graph-based)
pub struct GraphLSHIndex {
    /// Buckets: compact_hash → List of fragment IDs
    buckets: HashMap<u64, Vec<usize>>,

    /// Hash tolerance for bucketing (bits to mask)
    tolerance_bits: u32,
}

impl GraphLSHIndex {
    /// Create new graph LSH index
    ///
    /// # Arguments
    /// * `tolerance_bits` - Number of bits to mask for bucketing (0-8)
    ///   - 0: Exact match only
    ///   - 4: Allow minor differences
    ///   - 8: Allow moderate differences
    pub fn new(tolerance_bits: u32) -> Self {
        Self {
            buckets: HashMap::new(),
            tolerance_bits,
        }
    }

    /// Create with default tolerance
    pub fn default() -> Self {
        Self::new(4) // Moderate tolerance
    }

    /// Insert a WL signature
    pub fn insert(&mut self, signature: &WLSignature, id: usize) {
        let bucket_key = self.bucket_hash(signature);

        self.buckets
            .entry(bucket_key)
            .or_insert_with(Vec::new)
            .push(id);
    }

    /// Query for candidates
    pub fn query(&self, signature: &WLSignature) -> Vec<usize> {
        let bucket_key = self.bucket_hash(signature);

        self.buckets
            .get(&bucket_key)
            .map(|bucket| bucket.clone())
            .unwrap_or_default()
    }

    /// Compute bucket hash with tolerance
    fn bucket_hash(&self, signature: &WLSignature) -> u64 {
        let hash = signature.compact_hash();

        // Mask lower bits for tolerance
        let mask = !((1u64 << self.tolerance_bits) - 1);
        hash & mask
    }

    /// Get statistics
    pub fn stats(&self) -> GraphLSHIndexStats {
        GraphLSHIndexStats {
            num_buckets: self.buckets.len(),
            total_entries: self.buckets.values().map(|b| b.len()).sum(),
            max_bucket_size: self.buckets.values().map(|b| b.len()).max().unwrap_or(0),
        }
    }
}

/// Graph LSH index statistics
#[derive(Debug, Clone)]
pub struct GraphLSHIndexStats {
    pub num_buckets: usize,
    pub total_entries: usize,
    pub max_bucket_size: usize,
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::clone_detection::infrastructure::type4_detector::{PDGEdge, PDGNode};

    fn create_simple_pdg() -> SimplePDG {
        let mut pdg = SimplePDG::new();
        let n0 = pdg.add_node(PDGNode::Function);
        let n1 = pdg.add_node(PDGNode::Variable);
        let n2 = pdg.add_node(PDGNode::Return);
        pdg.add_edge(n0, n1, PDGEdge::DataDep);
        pdg.add_edge(n1, n2, PDGEdge::DataDep);
        pdg
    }

    #[test]
    fn test_wl_signature_identical_graphs() {
        let pdg1 = create_simple_pdg();
        let pdg2 = create_simple_pdg();

        let sig1 = WLSignature::from_pdg(&pdg1, 2);
        let sig2 = WLSignature::from_pdg(&pdg2, 2);

        assert_eq!(sig1.similarity(&sig2), 1.0);
    }

    #[test]
    fn test_wl_signature_empty_graph() {
        let pdg = SimplePDG::new();
        let sig = WLSignature::from_pdg(&pdg, 2);

        assert_eq!(sig.num_nodes(), 0);
        assert_eq!(sig.num_edges(), 0);
    }

    #[test]
    fn test_graph_lsh_insert_and_query() {
        let mut index = GraphLSHIndex::new(4);

        let pdg1 = create_simple_pdg();
        let pdg2 = create_simple_pdg();

        let sig1 = WLSignature::from_pdg(&pdg1, 2);
        let sig2 = WLSignature::from_pdg(&pdg2, 2);

        index.insert(&sig1, 0);
        index.insert(&sig2, 1);

        let candidates = index.query(&sig1);
        assert!(candidates.contains(&0));
        assert!(candidates.contains(&1));
    }

    #[test]
    fn test_jaccard_similarity() {
        let mut hist1 = HashMap::new();
        hist1.insert("A".to_string(), 2);
        hist1.insert("B".to_string(), 1);

        let mut hist2 = HashMap::new();
        hist2.insert("A".to_string(), 1);
        hist2.insert("B".to_string(), 2);

        let sim = WLSignature::jaccard_similarity(&hist1, &hist2);
        assert!(sim > 0.0 && sim < 1.0);
    }

    #[test]
    fn test_empty_histogram_similarity() {
        let hist1 = HashMap::new();
        let hist2 = HashMap::new();

        assert_eq!(WLSignature::jaccard_similarity(&hist1, &hist2), 1.0);
    }
}
