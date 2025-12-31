//! Similarity Metrics for Clone Detection
//!
//! Implements various similarity measures used across different clone types:
//! - Jaccard similarity (token-based)
//! - Cosine similarity (vector-based)
//! - Levenshtein edit distance
//! - AST-based similarity
//! - Semantic similarity

use std::collections::{HashMap, HashSet};
use std::hash::Hash;

/// Jaccard similarity coefficient
///
/// J(A, B) = |A ∩ B| / |A ∪ B|
///
/// Returns a value in [0.0, 1.0] where:
/// - 1.0 = identical sets
/// - 0.0 = completely disjoint sets
pub fn jaccard_similarity<T>(set_a: &HashSet<T>, set_b: &HashSet<T>) -> f64
where
    T: Eq + Hash,
{
    if set_a.is_empty() && set_b.is_empty() {
        return 1.0; // Both empty = identical
    }

    let intersection_size = set_a.intersection(set_b).count();
    let union_size = set_a.union(set_b).count();

    if union_size == 0 {
        return 0.0;
    }

    intersection_size as f64 / union_size as f64
}

/// Jaccard similarity from vectors (converts to sets)
pub fn jaccard_similarity_vec<T>(vec_a: &[T], vec_b: &[T]) -> f64
where
    T: Eq + Hash + Clone,
{
    let set_a: HashSet<T> = vec_a.iter().cloned().collect();
    let set_b: HashSet<T> = vec_b.iter().cloned().collect();
    jaccard_similarity(&set_a, &set_b)
}

/// Cosine similarity
///
/// cos(A, B) = (A · B) / (||A|| * ||B||)
///
/// Returns a value in [0.0, 1.0] where:
/// - 1.0 = identical vectors
/// - 0.0 = orthogonal vectors
pub fn cosine_similarity(vec_a: &[f64], vec_b: &[f64]) -> f64 {
    if vec_a.len() != vec_b.len() {
        return 0.0;
    }

    if vec_a.is_empty() {
        return 1.0; // Both empty = identical
    }

    let dot_product: f64 = vec_a.iter().zip(vec_b.iter()).map(|(a, b)| a * b).sum();

    let norm_a: f64 = vec_a.iter().map(|x| x * x).sum::<f64>().sqrt();
    let norm_b: f64 = vec_b.iter().map(|x| x * x).sum::<f64>().sqrt();

    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }

    (dot_product / (norm_a * norm_b)).clamp(0.0, 1.0)
}

/// Token-based cosine similarity
///
/// Converts token sequences to TF vectors and computes cosine similarity
pub fn token_cosine_similarity<T>(tokens_a: &[T], tokens_b: &[T]) -> f64
where
    T: Eq + Hash + Clone,
{
    if tokens_a.is_empty() && tokens_b.is_empty() {
        return 1.0;
    }

    // Build vocabulary
    let mut vocab = HashMap::new();
    let mut idx = 0;

    for token in tokens_a.iter().chain(tokens_b.iter()) {
        vocab.entry(token.clone()).or_insert_with(|| {
            let current_idx = idx;
            idx += 1;
            current_idx
        });
    }

    // Build TF vectors
    let vec_size = vocab.len();
    let mut vec_a = vec![0.0; vec_size];
    let mut vec_b = vec![0.0; vec_size];

    for token in tokens_a {
        if let Some(&i) = vocab.get(token) {
            vec_a[i] += 1.0;
        }
    }

    for token in tokens_b {
        if let Some(&i) = vocab.get(token) {
            vec_b[i] += 1.0;
        }
    }

    cosine_similarity(&vec_a, &vec_b)
}

/// Levenshtein edit distance (Wagner-Fischer algorithm)
///
/// Returns the minimum number of single-character edits (insertions, deletions, substitutions)
/// required to change one string into another.
///
/// Time complexity: O(m * n)
/// Space complexity: O(min(m, n))
pub fn levenshtein_distance(s1: &str, s2: &str) -> usize {
    let s1_chars: Vec<char> = s1.chars().collect();
    let s2_chars: Vec<char> = s2.chars().collect();

    let len1 = s1_chars.len();
    let len2 = s2_chars.len();

    if len1 == 0 {
        return len2;
    }
    if len2 == 0 {
        return len1;
    }

    // Use two rows for space optimization
    let mut prev_row: Vec<usize> = (0..=len2).collect();
    let mut curr_row: Vec<usize> = vec![0; len2 + 1];

    for i in 1..=len1 {
        curr_row[0] = i;

        for j in 1..=len2 {
            let cost = if s1_chars[i - 1] == s2_chars[j - 1] {
                0
            } else {
                1
            };

            curr_row[j] = std::cmp::min(
                std::cmp::min(curr_row[j - 1] + 1, prev_row[j] + 1),
                prev_row[j - 1] + cost,
            );
        }

        std::mem::swap(&mut prev_row, &mut curr_row);
    }

    prev_row[len2]
}

/// Normalized Levenshtein similarity
///
/// Returns: 1.0 - (edit_distance / max_length)
///
/// Result is in [0.0, 1.0] where:
/// - 1.0 = identical strings
/// - 0.0 = completely different
pub fn normalized_levenshtein_similarity(s1: &str, s2: &str) -> f64 {
    let max_len = s1.len().max(s2.len());

    if max_len == 0 {
        return 1.0; // Both empty
    }

    let distance = levenshtein_distance(s1, s2);
    1.0 - (distance as f64 / max_len as f64)
}

/// Dice coefficient (Sørensen–Dice)
///
/// DSC(A, B) = 2 * |A ∩ B| / (|A| + |B|)
///
/// Returns a value in [0.0, 1.0]
pub fn dice_coefficient<T>(set_a: &HashSet<T>, set_b: &HashSet<T>) -> f64
where
    T: Eq + Hash,
{
    if set_a.is_empty() && set_b.is_empty() {
        return 1.0;
    }

    let intersection_size = set_a.intersection(set_b).count();
    let sum_size = set_a.len() + set_b.len();

    if sum_size == 0 {
        return 0.0;
    }

    2.0 * intersection_size as f64 / sum_size as f64
}

/// Overlap coefficient
///
/// overlap(A, B) = |A ∩ B| / min(|A|, |B|)
///
/// Returns a value in [0.0, 1.0]
pub fn overlap_coefficient<T>(set_a: &HashSet<T>, set_b: &HashSet<T>) -> f64
where
    T: Eq + Hash,
{
    if set_a.is_empty() && set_b.is_empty() {
        return 1.0;
    }

    let intersection_size = set_a.intersection(set_b).count();
    let min_size = set_a.len().min(set_b.len());

    if min_size == 0 {
        return 0.0;
    }

    intersection_size as f64 / min_size as f64
}

/// Containment coefficient (A in B)
///
/// containment(A, B) = |A ∩ B| / |A|
///
/// Returns how much of A is contained in B
pub fn containment_coefficient<T>(set_a: &HashSet<T>, set_b: &HashSet<T>) -> f64
where
    T: Eq + Hash,
{
    if set_a.is_empty() {
        return 1.0; // Empty set is contained in everything
    }

    let intersection_size = set_a.intersection(set_b).count();
    intersection_size as f64 / set_a.len() as f64
}

/// Longest Common Subsequence (LCS) length
///
/// Returns the length of the longest common subsequence
///
/// Time complexity: O(m * n)
/// Space complexity: O(min(m, n))
pub fn lcs_length<T>(seq_a: &[T], seq_b: &[T]) -> usize
where
    T: Eq,
{
    let len_a = seq_a.len();
    let len_b = seq_b.len();

    if len_a == 0 || len_b == 0 {
        return 0;
    }

    // Use two rows for space optimization
    let mut prev_row: Vec<usize> = vec![0; len_b + 1];
    let mut curr_row: Vec<usize> = vec![0; len_b + 1];

    for i in 1..=len_a {
        for j in 1..=len_b {
            if seq_a[i - 1] == seq_b[j - 1] {
                curr_row[j] = prev_row[j - 1] + 1;
            } else {
                curr_row[j] = std::cmp::max(curr_row[j - 1], prev_row[j]);
            }
        }
        std::mem::swap(&mut prev_row, &mut curr_row);
    }

    prev_row[len_b]
}

/// LCS-based similarity
///
/// Returns: LCS_length / max(len_a, len_b)
///
/// Result is in [0.0, 1.0]
pub fn lcs_similarity<T>(seq_a: &[T], seq_b: &[T]) -> f64
where
    T: Eq,
{
    let max_len = seq_a.len().max(seq_b.len());

    if max_len == 0 {
        return 1.0;
    }

    let lcs_len = lcs_length(seq_a, seq_b);
    lcs_len as f64 / max_len as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    // =====================================================================
    // JACCARD SIMILARITY
    // =====================================================================

    #[test]
    fn test_jaccard_identical() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![1, 2, 3].into_iter().collect();

        assert_eq!(jaccard_similarity(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_jaccard_disjoint() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![4, 5, 6].into_iter().collect();

        assert_eq!(jaccard_similarity(&set_a, &set_b), 0.0);
    }

    #[test]
    fn test_jaccard_partial() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3, 4].into_iter().collect();

        // Intersection: {2, 3} = 2
        // Union: {1, 2, 3, 4} = 4
        // Jaccard = 2/4 = 0.5
        assert_eq!(jaccard_similarity(&set_a, &set_b), 0.5);
    }

    #[test]
    fn test_jaccard_empty() {
        let set_a: HashSet<i32> = HashSet::new();
        let set_b: HashSet<i32> = HashSet::new();

        assert_eq!(jaccard_similarity(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_jaccard_one_empty() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = HashSet::new();

        assert_eq!(jaccard_similarity(&set_a, &set_b), 0.0);
    }

    #[test]
    fn test_jaccard_vec() {
        let vec_a = vec![1, 2, 3, 2]; // Duplicates
        let vec_b = vec![2, 3, 4];

        // Sets: {1, 2, 3} and {2, 3, 4}
        // Jaccard = 2/4 = 0.5
        assert_eq!(jaccard_similarity_vec(&vec_a, &vec_b), 0.5);
    }

    // =====================================================================
    // COSINE SIMILARITY
    // =====================================================================

    #[test]
    fn test_cosine_identical() {
        let vec_a = vec![1.0, 2.0, 3.0];
        let vec_b = vec![1.0, 2.0, 3.0];

        assert!((cosine_similarity(&vec_a, &vec_b) - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_cosine_orthogonal() {
        let vec_a = vec![1.0, 0.0];
        let vec_b = vec![0.0, 1.0];

        assert!((cosine_similarity(&vec_a, &vec_b) - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_cosine_opposite() {
        let vec_a = vec![1.0, 2.0];
        let vec_b = vec![-1.0, -2.0];

        // Cosine = -1.0, but we clamp to [0, 1]
        assert_eq!(cosine_similarity(&vec_a, &vec_b), 0.0);
    }

    #[test]
    fn test_cosine_empty() {
        let vec_a: Vec<f64> = vec![];
        let vec_b: Vec<f64> = vec![];

        assert_eq!(cosine_similarity(&vec_a, &vec_b), 1.0);
    }

    #[test]
    fn test_cosine_zero_norm() {
        let vec_a = vec![0.0, 0.0, 0.0];
        let vec_b = vec![1.0, 2.0, 3.0];

        assert_eq!(cosine_similarity(&vec_a, &vec_b), 0.0);
    }

    #[test]
    fn test_cosine_different_lengths() {
        let vec_a = vec![1.0, 2.0];
        let vec_b = vec![1.0, 2.0, 3.0];

        assert_eq!(cosine_similarity(&vec_a, &vec_b), 0.0);
    }

    #[test]
    fn test_token_cosine() {
        let tokens_a = vec!["hello", "world", "foo"];
        let tokens_b = vec!["hello", "world", "bar"];

        let similarity = token_cosine_similarity(&tokens_a, &tokens_b);
        assert!(similarity > 0.0 && similarity < 1.0);
    }

    // =====================================================================
    // LEVENSHTEIN DISTANCE
    // =====================================================================

    #[test]
    fn test_levenshtein_identical() {
        assert_eq!(levenshtein_distance("hello", "hello"), 0);
    }

    #[test]
    fn test_levenshtein_insertion() {
        assert_eq!(levenshtein_distance("hello", "hellow"), 1);
    }

    #[test]
    fn test_levenshtein_deletion() {
        assert_eq!(levenshtein_distance("hello", "hell"), 1);
    }

    #[test]
    fn test_levenshtein_substitution() {
        assert_eq!(levenshtein_distance("hello", "hallo"), 1);
    }

    #[test]
    fn test_levenshtein_empty() {
        assert_eq!(levenshtein_distance("", ""), 0);
        assert_eq!(levenshtein_distance("hello", ""), 5);
        assert_eq!(levenshtein_distance("", "world"), 5);
    }

    #[test]
    fn test_levenshtein_complex() {
        assert_eq!(levenshtein_distance("kitten", "sitting"), 3);
        // k->s, e->i, insert g
    }

    #[test]
    fn test_normalized_levenshtein() {
        assert_eq!(normalized_levenshtein_similarity("hello", "hello"), 1.0);
        assert_eq!(normalized_levenshtein_similarity("", ""), 1.0);

        // "hello" vs "hell" = distance 1, max_len 5, similarity = 0.8
        assert_eq!(normalized_levenshtein_similarity("hello", "hell"), 0.8);
    }

    // =====================================================================
    // DICE COEFFICIENT
    // =====================================================================

    #[test]
    fn test_dice_identical() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![1, 2, 3].into_iter().collect();

        assert_eq!(dice_coefficient(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_dice_disjoint() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![4, 5, 6].into_iter().collect();

        assert_eq!(dice_coefficient(&set_a, &set_b), 0.0);
    }

    #[test]
    fn test_dice_partial() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3, 4].into_iter().collect();

        // Intersection: 2
        // Sum: 3 + 3 = 6
        // Dice = 2*2/6 = 2/3 ≈ 0.6666
        assert!((dice_coefficient(&set_a, &set_b) - 2.0 / 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_dice_empty() {
        let set_a: HashSet<i32> = HashSet::new();
        let set_b: HashSet<i32> = HashSet::new();

        assert_eq!(dice_coefficient(&set_a, &set_b), 1.0);
    }

    // =====================================================================
    // OVERLAP COEFFICIENT
    // =====================================================================

    #[test]
    fn test_overlap_identical() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![1, 2, 3].into_iter().collect();

        assert_eq!(overlap_coefficient(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_overlap_subset() {
        let set_a: HashSet<i32> = vec![1, 2].into_iter().collect();
        let set_b: HashSet<i32> = vec![1, 2, 3, 4].into_iter().collect();

        // Intersection: 2
        // Min size: 2
        // Overlap = 2/2 = 1.0
        assert_eq!(overlap_coefficient(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_overlap_partial() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3, 4].into_iter().collect();

        // Intersection: 2
        // Min size: 3
        // Overlap = 2/3 ≈ 0.6666
        assert!((overlap_coefficient(&set_a, &set_b) - 2.0 / 3.0).abs() < 1e-10);
    }

    // =====================================================================
    // CONTAINMENT COEFFICIENT
    // =====================================================================

    #[test]
    fn test_containment_full() {
        let set_a: HashSet<i32> = vec![1, 2].into_iter().collect();
        let set_b: HashSet<i32> = vec![1, 2, 3, 4].into_iter().collect();

        assert_eq!(containment_coefficient(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_containment_partial() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3].into_iter().collect();

        // Intersection: 2
        // |A| = 3
        // Containment = 2/3 ≈ 0.6666
        assert!((containment_coefficient(&set_a, &set_b) - 2.0 / 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_containment_empty() {
        let set_a: HashSet<i32> = HashSet::new();
        let set_b: HashSet<i32> = vec![1, 2, 3].into_iter().collect();

        assert_eq!(containment_coefficient(&set_a, &set_b), 1.0);
    }

    // =====================================================================
    // LONGEST COMMON SUBSEQUENCE
    // =====================================================================

    #[test]
    fn test_lcs_identical() {
        let seq_a = vec![1, 2, 3, 4];
        let seq_b = vec![1, 2, 3, 4];

        assert_eq!(lcs_length(&seq_a, &seq_b), 4);
    }

    #[test]
    fn test_lcs_partial() {
        let seq_a = vec![1, 2, 3, 4, 5];
        let seq_b = vec![2, 3, 5];

        // LCS: [2, 3, 5] = length 3
        assert_eq!(lcs_length(&seq_a, &seq_b), 3);
    }

    #[test]
    fn test_lcs_disjoint() {
        let seq_a = vec![1, 2, 3];
        let seq_b = vec![4, 5, 6];

        assert_eq!(lcs_length(&seq_a, &seq_b), 0);
    }

    #[test]
    fn test_lcs_empty() {
        let seq_a: Vec<i32> = vec![];
        let seq_b = vec![1, 2, 3];

        assert_eq!(lcs_length(&seq_a, &seq_b), 0);
    }

    #[test]
    fn test_lcs_similarity() {
        let seq_a = vec![1, 2, 3, 4];
        let seq_b = vec![1, 2, 3, 4];

        assert_eq!(lcs_similarity(&seq_a, &seq_b), 1.0);
    }

    #[test]
    fn test_lcs_similarity_empty() {
        let seq_a: Vec<i32> = vec![];
        let seq_b: Vec<i32> = vec![];

        assert_eq!(lcs_similarity(&seq_a, &seq_b), 1.0);
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_jaccard_symmetry() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3, 4].into_iter().collect();

        assert_eq!(
            jaccard_similarity(&set_a, &set_b),
            jaccard_similarity(&set_b, &set_a)
        );
    }

    #[test]
    fn test_cosine_symmetry() {
        let vec_a = vec![1.0, 2.0, 3.0];
        let vec_b = vec![2.0, 3.0, 4.0];

        assert_eq!(
            cosine_similarity(&vec_a, &vec_b),
            cosine_similarity(&vec_b, &vec_a)
        );
    }

    #[test]
    fn test_levenshtein_symmetry() {
        assert_eq!(
            levenshtein_distance("hello", "world"),
            levenshtein_distance("world", "hello")
        );
    }

    #[test]
    fn test_cosine_normalization() {
        let vec_a = vec![2.0, 4.0, 6.0]; // Scaled version
        let vec_b = vec![1.0, 2.0, 3.0];

        // Cosine similarity should be 1.0 (same direction)
        assert!((cosine_similarity(&vec_a, &vec_b) - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_levenshtein_unicode() {
        assert_eq!(levenshtein_distance("café", "cafe"), 1);
        assert_eq!(levenshtein_distance("你好", "您好"), 1);
    }

    #[test]
    fn test_lcs_order_matters() {
        let seq_a = vec![1, 2, 3];
        let seq_b = vec![3, 2, 1];

        // Only single element matches in order
        assert_eq!(lcs_length(&seq_a, &seq_b), 1);
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_jaccard_single_element() {
        let set_a: HashSet<i32> = vec![42].into_iter().collect();
        let set_b: HashSet<i32> = vec![42].into_iter().collect();

        assert_eq!(jaccard_similarity(&set_a, &set_b), 1.0);
    }

    #[test]
    fn test_cosine_single_dimension() {
        let vec_a = vec![5.0];
        let vec_b = vec![10.0];

        assert_eq!(cosine_similarity(&vec_a, &vec_b), 1.0);
    }

    #[test]
    fn test_levenshtein_single_char() {
        assert_eq!(levenshtein_distance("a", "a"), 0);
        assert_eq!(levenshtein_distance("a", "b"), 1);
    }

    #[test]
    fn test_dice_vs_jaccard() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3, 4].into_iter().collect();

        let jaccard = jaccard_similarity(&set_a, &set_b);
        let dice = dice_coefficient(&set_a, &set_b);

        // Dice is always >= Jaccard
        assert!(dice >= jaccard);
    }

    #[test]
    fn test_overlap_vs_containment() {
        let set_a: HashSet<i32> = vec![1, 2].into_iter().collect();
        let set_b: HashSet<i32> = vec![1, 2, 3, 4].into_iter().collect();

        let overlap = overlap_coefficient(&set_a, &set_b);
        let contain = containment_coefficient(&set_a, &set_b);

        // For subset, both should be 1.0
        assert_eq!(overlap, 1.0);
        assert_eq!(contain, 1.0);
    }

    #[test]
    fn test_lcs_reverse() {
        let seq_a = vec![1, 2, 3, 4, 5];
        let seq_b = vec![5, 4, 3, 2, 1];

        // LCS of sequence and its reverse = 1 (any single element)
        assert_eq!(lcs_length(&seq_a, &seq_b), 1);
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_all_metrics_consistency() {
        let set_a: HashSet<i32> = vec![1, 2, 3].into_iter().collect();
        let set_b: HashSet<i32> = vec![2, 3, 4].into_iter().collect();

        let jaccard = jaccard_similarity(&set_a, &set_b);
        let dice = dice_coefficient(&set_a, &set_b);
        let overlap = overlap_coefficient(&set_a, &set_b);

        // All should be in [0, 1]
        assert!(jaccard >= 0.0 && jaccard <= 1.0);
        assert!(dice >= 0.0 && dice <= 1.0);
        assert!(overlap >= 0.0 && overlap <= 1.0);

        // Dice >= Jaccard (always true)
        assert!(dice >= jaccard);
    }

    #[test]
    fn test_token_cosine_duplicates() {
        let tokens_a = vec!["foo", "foo", "bar"];
        let tokens_b = vec!["foo", "bar", "bar"];

        let similarity = token_cosine_similarity(&tokens_a, &tokens_b);

        // Should handle duplicates via TF counts
        assert!(similarity > 0.0 && similarity < 1.0);
    }

    #[test]
    fn test_levenshtein_long_strings() {
        let s1 = "a".repeat(100);
        let s2 = "b".repeat(100);

        // All 100 characters need substitution
        assert_eq!(levenshtein_distance(&s1, &s2), 100);
    }

    #[test]
    fn test_lcs_longest_path() {
        let seq_a: Vec<i32> = (1..=100).collect();
        let seq_b: Vec<i32> = (1..=100).collect();

        // Identical sequences
        assert_eq!(lcs_length(&seq_a, &seq_b), 100);
    }

    #[test]
    fn test_jaccard_large_sets() {
        let set_a: HashSet<i32> = (1..=1000).collect();
        let set_b: HashSet<i32> = (500..=1500).collect();

        let similarity = jaccard_similarity(&set_a, &set_b);

        // Intersection: 500-1000 (501 elements)
        // Union: 1-1500 (1500 elements)
        // Jaccard ≈ 501/1500 ≈ 0.334
        assert!((similarity - 501.0 / 1500.0).abs() < 1e-10);
    }

    #[test]
    fn test_cosine_high_dimensional() {
        let vec_a: Vec<f64> = (0..1000).map(|i| i as f64).collect();
        let vec_b: Vec<f64> = (0..1000).map(|i| i as f64 * 2.0).collect();

        // Scaled version = cosine = 1.0
        assert!((cosine_similarity(&vec_a, &vec_b) - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_normalized_levenshtein_boundary() {
        // Max distance = max_len
        let s1 = "aaaa";
        let s2 = "bbbb";

        let similarity = normalized_levenshtein_similarity(s1, s2);

        // Distance = 4, max_len = 4, similarity = 1 - 4/4 = 0.0
        assert_eq!(similarity, 0.0);
    }

    #[test]
    fn test_all_zero_inputs() {
        let vec_a = vec![0.0, 0.0, 0.0];
        let vec_b = vec![0.0, 0.0, 0.0];

        // Both zero vectors
        assert_eq!(cosine_similarity(&vec_a, &vec_b), 0.0);
    }

    #[test]
    fn test_asymmetric_containment() {
        let small: HashSet<i32> = vec![1, 2].into_iter().collect();
        let large: HashSet<i32> = vec![1, 2, 3, 4].into_iter().collect();

        let contain_small_in_large = containment_coefficient(&small, &large);
        let contain_large_in_small = containment_coefficient(&large, &small);

        // Small is fully contained in large
        assert_eq!(contain_small_in_large, 1.0);

        // Large is only partially contained in small
        assert_eq!(contain_large_in_small, 0.5);
    }
}
