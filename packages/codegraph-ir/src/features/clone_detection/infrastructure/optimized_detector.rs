//! Optimized Clone Detector with LSH + Caching + Parallelization
//!
//! 3-Tier Architecture:
//! 1. Preprocessing: Build & cache all representations (parallel)
//! 2. Filtering: LSH-based candidate retrieval (O(n log n))
//! 3. Verification: Parallel verification with cached data
//!
//! Expected speedup: 7-10x on Type-2/3/4 detection

use super::{
    lsh::{GraphLSHIndex, LSHIndex, MinHashSignature, WLSignature},
    CloneDetector, SimplePDG, Type1Detector, Type2Detector, Type3Detector, Type4Detector,
};
use crate::features::clone_detection::domain::{
    CloneDeduplicator, ClonePair, CloneType, CodeFragment,
};
use rayon::prelude::*;
use std::collections::HashMap;
use std::sync::Arc;

/// Cached representations for fast comparison
#[derive(Clone)]
struct CachedRepresentation {
    /// MinHash signature for Type-1/2 (always computed)
    minhash: MinHashSignature,

    /// PDG (shared across Type-3/4) (always computed, lightweight)
    pdg: Arc<SimplePDG>,

    /// WL signature for Type-3/4 (lazy - computed on demand)
    wl_signature: Option<WLSignature>,
}

/// Optimized multi-level clone detector
///
/// Uses LSH for candidate filtering and caches expensive representations.
pub struct OptimizedCloneDetector {
    /// Cached representations (built once, used many times)
    cache: HashMap<usize, CachedRepresentation>,

    /// LSH index for Type-1/2 (textual similarity)
    text_lsh: LSHIndex,

    /// Graph LSH for Type-3/4 (structural similarity)
    graph_lsh: GraphLSHIndex,

    /// Fallback detectors for verification
    type1: Type1Detector,
    type2: Type2Detector,
    type3: Type3Detector,
    type4: Type4Detector,

    /// Enable parallel processing
    parallel: bool,

    /// Enable Type-3/4 detection (expensive WL signatures)
    enable_semantic: bool,
}

impl OptimizedCloneDetector {
    /// Create new optimized detector (all clone types: Type-1/2/3/4)
    pub fn new() -> Self {
        Self {
            cache: HashMap::new(),
            text_lsh: LSHIndex::new(32, 4), // Higher precision: threshold ~0.7
            graph_lsh: GraphLSHIndex::new(1), // Very strict! (was 2, reduce candidates)
            type1: Type1Detector::new(),
            type2: Type2Detector::new(),
            type3: Type3Detector::new(),
            type4: Type4Detector::new(),
            parallel: true,
            enable_semantic: true, // Enabled by default (all clone types)
        }
    }

    /// Create with only Type-1/2 (fast mode, skip semantic analysis)
    pub fn fast_mode() -> Self {
        let mut detector = Self::new();
        detector.enable_semantic = false;
        detector
    }

    /// Disable parallelization (for debugging)
    pub fn sequential(mut self) -> Self {
        self.parallel = false;
        self
    }

    /// Tier 1: Preprocessing - Build & cache all representations (parallel)
    fn preprocess(&mut self, fragments: &[CodeFragment]) {
        let representations: Vec<_> = if self.parallel {
            fragments
                .par_iter()
                .enumerate()
                .map(|(i, f)| self.build_representation(i, f))
                .collect()
        } else {
            fragments
                .iter()
                .enumerate()
                .map(|(i, f)| self.build_representation(i, f))
                .collect()
        };

        // Insert into cache and LSH indices
        for (id, repr) in representations {
            self.text_lsh.insert(&repr.minhash, id);

            // Only insert into graph LSH if semantic detection enabled
            if self.enable_semantic {
                if let Some(ref wl_sig) = repr.wl_signature {
                    self.graph_lsh.insert(wl_sig, id);
                }
            }

            self.cache.insert(id, repr);
        }
    }

    /// Build all representations for a fragment
    fn build_representation(
        &self,
        id: usize,
        fragment: &CodeFragment,
    ) -> (usize, CachedRepresentation) {
        // MinHash for textual similarity (always computed - fast!)
        let minhash = MinHashSignature::from_text(&fragment.content, 5, 128);

        // PDG for structural similarity (always computed - lightweight)
        let pdg = Arc::new(self.type4.build_pdg(&fragment.content));

        // WL signature: Only if semantic detection enabled
        let wl_signature = if self.enable_semantic {
            Some(WLSignature::from_pdg(&pdg, 2))
        } else {
            None // Skip expensive WL computation!
        };

        (
            id,
            CachedRepresentation {
                minhash,
                pdg,
                wl_signature,
            },
        )
    }

    /// Tier 2: Candidate Filtering - LSH-based retrieval with threshold pre-filtering
    fn find_candidates(
        &self,
        fragments: &[CodeFragment],
    ) -> HashMap<CloneType, Vec<(usize, usize)>> {
        let mut candidates: HashMap<CloneType, Vec<(usize, usize)>> = HashMap::new();

        for i in 0..fragments.len() {
            // Type-1/2 candidates (textual similarity)
            let text_candidates = self.text_lsh.query(&self.cache[&i].minhash);
            for &j in &text_candidates {
                if i < j {
                    // Pre-filter by similarity threshold!
                    let est_sim = self.cache[&i]
                        .minhash
                        .jaccard_estimate(&self.cache[&j].minhash);

                    // Route based on similarity (avoid duplicate checks)
                    if est_sim >= 0.95 {
                        // Very high similarity → Type-1 only
                        candidates
                            .entry(CloneType::Type1)
                            .or_insert_with(Vec::new)
                            .push((i, j));
                    } else if est_sim >= 0.7 {
                        // High similarity → Type-2 (renamed identifiers)
                        candidates
                            .entry(CloneType::Type2)
                            .or_insert_with(Vec::new)
                            .push((i, j));
                    }
                    // Below 0.7 → skip (not similar enough)
                }
            }

            // Type-3/4 candidates (structural similarity) - only if enabled!
            if self.enable_semantic {
                if let Some(ref wl_sig_i) = self.cache[&i].wl_signature {
                    let graph_candidates = self.graph_lsh.query(wl_sig_i);
                    for &j in &graph_candidates {
                        if i < j {
                            if let Some(ref wl_sig_j) = self.cache[&j].wl_signature {
                                // Pre-filter by graph similarity!
                                let graph_sim = wl_sig_i.similarity(wl_sig_j);

                                if graph_sim >= 0.6 {
                                    // Medium-high similarity → Type-3 (gapped clones)
                                    candidates
                                        .entry(CloneType::Type3)
                                        .or_insert_with(Vec::new)
                                        .push((i, j));
                                } else if graph_sim >= 0.5 {
                                    // Medium similarity → Type-4 (semantic)
                                    candidates
                                        .entry(CloneType::Type4)
                                        .or_insert_with(Vec::new)
                                        .push((i, j));
                                }
                                // Below 0.5 → skip
                            }
                        }
                    }
                }
            }
        }

        candidates
    }

    /// Tier 3: Verification - Parallel verification with cached data
    fn verify_candidates(
        &self,
        fragments: &[CodeFragment],
        candidates: HashMap<CloneType, Vec<(usize, usize)>>,
    ) -> Vec<ClonePair> {
        let mut all_pairs = Vec::new();

        // Type-1: Use existing detector (already fast)
        if let Some(type1_candidates) = candidates.get(&CloneType::Type1) {
            let type1_fragments: Vec<_> = type1_candidates
                .iter()
                .flat_map(|(i, j)| vec![fragments[*i].clone(), fragments[*j].clone()])
                .collect();

            if !type1_fragments.is_empty() {
                let pairs = self.type1.detect(&type1_fragments);
                all_pairs.extend(pairs);
            }
        }

        // Type-2: Verify with cached MinHash
        if let Some(type2_candidates) = candidates.get(&CloneType::Type2) {
            let pairs = self.verify_type2(fragments, type2_candidates);
            all_pairs.extend(pairs);
        }

        // Type-3: Verify with cached PDG
        if let Some(type3_candidates) = candidates.get(&CloneType::Type3) {
            let pairs = self.verify_type3(fragments, type3_candidates);
            all_pairs.extend(pairs);
        }

        // Type-4: Verify with cached WL signature
        if let Some(type4_candidates) = candidates.get(&CloneType::Type4) {
            let pairs = self.verify_type4(fragments, type4_candidates);
            all_pairs.extend(pairs);
        }

        all_pairs
    }

    /// Verify Type-2 candidates with cached MinHash
    fn verify_type2(
        &self,
        fragments: &[CodeFragment],
        candidates: &[(usize, usize)],
    ) -> Vec<ClonePair> {
        if self.parallel {
            candidates
                .par_iter()
                .filter_map(|(i, j)| {
                    let sim = self.cache[i]
                        .minhash
                        .jaccard_estimate(&self.cache[j].minhash);
                    if sim >= 0.7 {
                        Some(ClonePair::new(
                            CloneType::Type2,
                            fragments[*i].clone(),
                            fragments[*j].clone(),
                            sim,
                        ))
                    } else {
                        None
                    }
                })
                .collect()
        } else {
            candidates
                .iter()
                .filter_map(|(i, j)| {
                    let sim = self.cache[i]
                        .minhash
                        .jaccard_estimate(&self.cache[j].minhash);
                    if sim >= 0.7 {
                        Some(ClonePair::new(
                            CloneType::Type2,
                            fragments[*i].clone(),
                            fragments[*j].clone(),
                            sim,
                        ))
                    } else {
                        None
                    }
                })
                .collect()
        }
    }

    /// Verify Type-3 candidates with cached WL signature
    fn verify_type3(
        &self,
        fragments: &[CodeFragment],
        candidates: &[(usize, usize)],
    ) -> Vec<ClonePair> {
        if self.parallel {
            candidates
                .par_iter()
                .filter_map(|(i, j)| {
                    // Both must have WL signatures
                    if let (Some(ref sig_i), Some(ref sig_j)) =
                        (&self.cache[i].wl_signature, &self.cache[j].wl_signature)
                    {
                        let sim = sig_i.similarity(sig_j);
                        if sim >= 0.6 {
                            return Some(ClonePair::new(
                                CloneType::Type3,
                                fragments[*i].clone(),
                                fragments[*j].clone(),
                                sim,
                            ));
                        }
                    }
                    None
                })
                .collect()
        } else {
            candidates
                .iter()
                .filter_map(|(i, j)| {
                    if let (Some(ref sig_i), Some(ref sig_j)) =
                        (&self.cache[i].wl_signature, &self.cache[j].wl_signature)
                    {
                        let sim = sig_i.similarity(sig_j);
                        if sim >= 0.6 {
                            return Some(ClonePair::new(
                                CloneType::Type3,
                                fragments[*i].clone(),
                                fragments[*j].clone(),
                                sim,
                            ));
                        }
                    }
                    None
                })
                .collect()
        }
    }

    /// Verify Type-4 candidates with cached WL signature
    fn verify_type4(
        &self,
        fragments: &[CodeFragment],
        candidates: &[(usize, usize)],
    ) -> Vec<ClonePair> {
        if self.parallel {
            candidates
                .par_iter()
                .filter_map(|(i, j)| {
                    // Both must have WL signatures
                    if let (Some(ref sig_i), Some(ref sig_j)) =
                        (&self.cache[i].wl_signature, &self.cache[j].wl_signature)
                    {
                        let sim = sig_i.similarity(sig_j);
                        if sim >= 0.5 {
                            return Some(ClonePair::new(
                                CloneType::Type4,
                                fragments[*i].clone(),
                                fragments[*j].clone(),
                                sim,
                            ));
                        }
                    }
                    None
                })
                .collect()
        } else {
            candidates
                .iter()
                .filter_map(|(i, j)| {
                    if let (Some(ref sig_i), Some(ref sig_j)) =
                        (&self.cache[i].wl_signature, &self.cache[j].wl_signature)
                    {
                        let sim = sig_i.similarity(sig_j);
                        if sim >= 0.5 {
                            return Some(ClonePair::new(
                                CloneType::Type4,
                                fragments[*i].clone(),
                                fragments[*j].clone(),
                                sim,
                            ));
                        }
                    }
                    None
                })
                .collect()
        }
    }

    /// Detect all clone types with optimization
    pub fn detect_all(&mut self, fragments: &[CodeFragment]) -> Vec<ClonePair> {
        if fragments.is_empty() {
            return Vec::new();
        }

        // Tier 1: Preprocessing (parallel)
        self.preprocess(fragments);

        // Tier 2: Candidate filtering (LSH)
        let candidates = self.find_candidates(fragments);

        // Tier 3: Verification (parallel, cached)
        let pairs = self.verify_candidates(fragments, candidates);

        // Deduplicate
        CloneDeduplicator::deduplicate(pairs)
    }

    /// Get statistics
    pub fn stats(&self) -> OptimizedDetectorStats {
        OptimizedDetectorStats {
            cached_fragments: self.cache.len(),
            text_lsh_stats: self.text_lsh.stats(),
            graph_lsh_stats: self.graph_lsh.stats(),
        }
    }
}

impl Default for OptimizedCloneDetector {
    fn default() -> Self {
        Self::new()
    }
}

/// Statistics for optimized detector
#[derive(Debug, Clone)]
pub struct OptimizedDetectorStats {
    pub cached_fragments: usize,
    pub text_lsh_stats: super::lsh::LSHIndexStats,
    pub graph_lsh_stats: super::lsh::GraphLSHIndexStats,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn create_fragment(file: &str, content: &str) -> CodeFragment {
        CodeFragment::new(
            file.to_string(),
            Span::new(1, 0, 10, 0),
            content.to_string(),
            50,
            6,
        )
    }

    #[test]
    fn test_optimized_detector_creation() {
        let detector = OptimizedCloneDetector::new();
        let stats = detector.stats();
        assert_eq!(stats.cached_fragments, 0);
    }

    #[test]
    fn test_preprocessing() {
        let mut detector = OptimizedCloneDetector::new();
        let fragments = vec![
            create_fragment("file1.py", "def foo(): pass"),
            create_fragment("file2.py", "def bar(): pass"),
        ];

        detector.preprocess(&fragments);

        let stats = detector.stats();
        assert_eq!(stats.cached_fragments, 2);
    }

    #[test]
    fn test_detect_all_optimized() {
        let mut detector = OptimizedCloneDetector::new();
        let fragments = vec![
            create_fragment("file1.py", "def add(a, b): return a + b"),
            create_fragment("file2.py", "def add(a, b): return a + b"),
        ];

        let pairs = detector.detect_all(&fragments);

        // Should find at least Type-1 clone
        assert!(!pairs.is_empty());
    }

    #[test]
    fn test_sequential_mode() {
        let mut detector = OptimizedCloneDetector::new().sequential();
        let fragments = vec![
            create_fragment("file1.py", "def foo(): pass"),
            create_fragment("file2.py", "def foo(): pass"),
        ];

        let pairs = detector.detect_all(&fragments);
        assert!(!pairs.is_empty());
    }
}
