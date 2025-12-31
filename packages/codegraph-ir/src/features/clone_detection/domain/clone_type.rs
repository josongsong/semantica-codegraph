//! Clone Type Classification
//!
//! Defines the 4 types of code clones as per Bellon et al. (2007):
//! - **Type-1**: Exact clones (only whitespace/comments differ)
//! - **Type-2**: Renamed clones (identifiers/types/literals differ)
//! - **Type-3**: Gapped clones (statements added/removed/modified)
//! - **Type-4**: Semantic clones (different syntax, same behavior)

use serde::{Deserialize, Serialize};
use std::fmt;

/// Clone type classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CloneType {
    /// Type-1: Exact clones
    ///
    /// Only whitespace, layout, and comments differ.
    /// Example:
    /// ```text
    /// // Clone 1
    /// def foo(x):
    ///     return x + 1
    ///
    /// // Clone 2
    /// def foo(x):
    ///     return x+1  # Different spacing
    /// ```
    Type1,

    /// Type-2: Renamed clones
    ///
    /// Identifiers, types, or literals differ but structure is identical.
    /// Example:
    /// ```text
    /// // Clone 1
    /// def add(a, b):
    ///     return a + b
    ///
    /// // Clone 2
    /// def sum(x, y):
    ///     return x + y
    /// ```
    Type2,

    /// Type-3: Gapped clones
    ///
    /// Statements added, removed, or modified but overall structure similar.
    /// Example:
    /// ```text
    /// // Clone 1
    /// def process(data):
    ///     validate(data)
    ///     result = transform(data)
    ///     return result
    ///
    /// // Clone 2
    /// def process(data):
    ///     validate(data)
    ///     log("Processing")  # Added statement
    ///     result = transform(data)
    ///     return result
    /// ```
    Type3,

    /// Type-4: Semantic clones
    ///
    /// Different syntax but same functionality.
    /// Example:
    /// ```text
    /// // Clone 1
    /// def factorial(n):
    ///     if n == 0:
    ///         return 1
    ///     return n * factorial(n - 1)
    ///
    /// // Clone 2
    /// def factorial(n):
    ///     result = 1
    ///     for i in range(1, n + 1):
    ///         result *= i
    ///     return result
    /// ```
    Type4,
}

impl CloneType {
    /// Get all clone types in order of increasing abstraction
    pub fn all() -> [CloneType; 4] {
        [
            CloneType::Type1,
            CloneType::Type2,
            CloneType::Type3,
            CloneType::Type4,
        ]
    }

    /// Get human-readable description
    pub fn description(&self) -> &'static str {
        match self {
            CloneType::Type1 => "Exact clone (whitespace/comments differ)",
            CloneType::Type2 => "Renamed clone (identifiers/types/literals differ)",
            CloneType::Type3 => "Gapped clone (statements added/removed/modified)",
            CloneType::Type4 => "Semantic clone (different syntax, same behavior)",
        }
    }

    /// Get detection algorithm name
    pub fn algorithm(&self) -> &'static str {
        match self {
            CloneType::Type1 => "String-based hashing (MD5/SHA256)",
            CloneType::Type2 => "AST-based normalization + hashing",
            CloneType::Type3 => "PDG-based + edit distance (threshold: 0.7)",
            CloneType::Type4 => "Graph isomorphism + behavioral analysis",
        }
    }

    /// Get detection complexity (Big-O notation)
    pub fn complexity(&self) -> &'static str {
        match self {
            CloneType::Type1 => "O(n) - Linear",
            CloneType::Type2 => "O(n log n) - AST traversal + hash table",
            CloneType::Type3 => "O(n²) - Pairwise edit distance",
            CloneType::Type4 => "O(n³) - Graph isomorphism (NP-complete)",
        }
    }

    /// Get typical detection speed (LOC/s)
    pub fn typical_speed(&self) -> usize {
        match self {
            CloneType::Type1 => 1_000_000, // 1M LOC/s
            CloneType::Type2 => 500_000,   // 500K LOC/s
            CloneType::Type3 => 50_000,    // 50K LOC/s
            CloneType::Type4 => 5_000,     // 5K LOC/s
        }
    }

    /// Check if this clone type is a subset of another
    ///
    /// Type-1 ⊂ Type-2 ⊂ Type-3 ⊂ Type-4
    pub fn is_subset_of(&self, other: CloneType) -> bool {
        let self_level = self.abstraction_level();
        let other_level = other.abstraction_level();
        self_level <= other_level
    }

    /// Get abstraction level (0 = most concrete, 3 = most abstract)
    pub fn abstraction_level(&self) -> u8 {
        match self {
            CloneType::Type1 => 0,
            CloneType::Type2 => 1,
            CloneType::Type3 => 2,
            CloneType::Type4 => 3,
        }
    }

    /// Check if detection requires AST
    pub fn requires_ast(&self) -> bool {
        matches!(self, CloneType::Type2 | CloneType::Type3 | CloneType::Type4)
    }

    /// Check if detection requires PDG
    pub fn requires_pdg(&self) -> bool {
        matches!(self, CloneType::Type3 | CloneType::Type4)
    }

    /// Check if detection requires data flow analysis
    pub fn requires_dataflow(&self) -> bool {
        matches!(self, CloneType::Type4)
    }

    /// Get minimum token threshold for clone (Bellon et al. recommend 50 tokens)
    pub fn min_token_threshold(&self) -> usize {
        match self {
            CloneType::Type1 | CloneType::Type2 => 50, // Standard threshold
            CloneType::Type3 => 30,                    // Allow smaller gapped clones
            CloneType::Type4 => 20,                    // Semantic similarity can be shorter
        }
    }

    /// Get minimum LOC threshold for clone
    pub fn min_loc_threshold(&self) -> usize {
        match self {
            CloneType::Type1 | CloneType::Type2 => 6, // ~6 lines minimum
            CloneType::Type3 => 4,                    // Gapped clones can be shorter
            CloneType::Type4 => 3,                    // Semantic clones focus on behavior
        }
    }

    /// Get similarity threshold for detection
    pub fn similarity_threshold(&self) -> f64 {
        match self {
            CloneType::Type1 => 1.0,  // Exact match
            CloneType::Type2 => 0.95, // Very high similarity after normalization
            CloneType::Type3 => 0.7,  // 70% similarity (Bellon et al. standard)
            CloneType::Type4 => 0.6,  // 60% behavioral similarity
        }
    }
}

impl fmt::Display for CloneType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CloneType::Type1 => write!(f, "Type-1"),
            CloneType::Type2 => write!(f, "Type-2"),
            CloneType::Type3 => write!(f, "Type-3"),
            CloneType::Type4 => write!(f, "Type-4"),
        }
    }
}

impl From<u8> for CloneType {
    fn from(value: u8) -> Self {
        match value {
            1 => CloneType::Type1,
            2 => CloneType::Type2,
            3 => CloneType::Type3,
            4 => CloneType::Type4,
            _ => panic!("Invalid clone type: {}. Must be 1-4", value),
        }
    }
}

impl From<CloneType> for u8 {
    fn from(clone_type: CloneType) -> u8 {
        clone_type.abstraction_level() + 1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // =====================================================================
    // BASIC FUNCTIONALITY
    // =====================================================================

    #[test]
    fn test_clone_type_all() {
        let all = CloneType::all();
        assert_eq!(all.len(), 4);
        assert_eq!(all[0], CloneType::Type1);
        assert_eq!(all[1], CloneType::Type2);
        assert_eq!(all[2], CloneType::Type3);
        assert_eq!(all[3], CloneType::Type4);
    }

    #[test]
    fn test_clone_type_description() {
        assert_eq!(
            CloneType::Type1.description(),
            "Exact clone (whitespace/comments differ)"
        );
        assert_eq!(
            CloneType::Type2.description(),
            "Renamed clone (identifiers/types/literals differ)"
        );
        assert_eq!(
            CloneType::Type3.description(),
            "Gapped clone (statements added/removed/modified)"
        );
        assert_eq!(
            CloneType::Type4.description(),
            "Semantic clone (different syntax, same behavior)"
        );
    }

    #[test]
    fn test_clone_type_algorithm() {
        assert!(CloneType::Type1.algorithm().contains("hashing"));
        assert!(CloneType::Type2.algorithm().contains("AST"));
        assert!(CloneType::Type3.algorithm().contains("PDG"));
        assert!(CloneType::Type4.algorithm().contains("isomorphism"));
    }

    #[test]
    fn test_clone_type_complexity() {
        assert_eq!(CloneType::Type1.complexity(), "O(n) - Linear");
        assert!(CloneType::Type2.complexity().contains("O(n log n)"));
        assert!(CloneType::Type3.complexity().contains("O(n²)"));
        assert!(CloneType::Type4.complexity().contains("O(n³)"));
    }

    #[test]
    fn test_clone_type_typical_speed() {
        assert_eq!(CloneType::Type1.typical_speed(), 1_000_000);
        assert_eq!(CloneType::Type2.typical_speed(), 500_000);
        assert_eq!(CloneType::Type3.typical_speed(), 50_000);
        assert_eq!(CloneType::Type4.typical_speed(), 5_000);
    }

    #[test]
    fn test_abstraction_level() {
        assert_eq!(CloneType::Type1.abstraction_level(), 0);
        assert_eq!(CloneType::Type2.abstraction_level(), 1);
        assert_eq!(CloneType::Type3.abstraction_level(), 2);
        assert_eq!(CloneType::Type4.abstraction_level(), 3);
    }

    #[test]
    fn test_is_subset_of() {
        // Type-1 is subset of all
        assert!(CloneType::Type1.is_subset_of(CloneType::Type1));
        assert!(CloneType::Type1.is_subset_of(CloneType::Type2));
        assert!(CloneType::Type1.is_subset_of(CloneType::Type3));
        assert!(CloneType::Type1.is_subset_of(CloneType::Type4));

        // Type-2 is subset of Type-2, Type-3, Type-4
        assert!(!CloneType::Type2.is_subset_of(CloneType::Type1));
        assert!(CloneType::Type2.is_subset_of(CloneType::Type2));
        assert!(CloneType::Type2.is_subset_of(CloneType::Type3));
        assert!(CloneType::Type2.is_subset_of(CloneType::Type4));

        // Type-3 is subset of Type-3, Type-4
        assert!(!CloneType::Type3.is_subset_of(CloneType::Type1));
        assert!(!CloneType::Type3.is_subset_of(CloneType::Type2));
        assert!(CloneType::Type3.is_subset_of(CloneType::Type3));
        assert!(CloneType::Type3.is_subset_of(CloneType::Type4));

        // Type-4 is only subset of itself
        assert!(!CloneType::Type4.is_subset_of(CloneType::Type1));
        assert!(!CloneType::Type4.is_subset_of(CloneType::Type2));
        assert!(!CloneType::Type4.is_subset_of(CloneType::Type3));
        assert!(CloneType::Type4.is_subset_of(CloneType::Type4));
    }

    #[test]
    fn test_requires_ast() {
        assert!(!CloneType::Type1.requires_ast());
        assert!(CloneType::Type2.requires_ast());
        assert!(CloneType::Type3.requires_ast());
        assert!(CloneType::Type4.requires_ast());
    }

    #[test]
    fn test_requires_pdg() {
        assert!(!CloneType::Type1.requires_pdg());
        assert!(!CloneType::Type2.requires_pdg());
        assert!(CloneType::Type3.requires_pdg());
        assert!(CloneType::Type4.requires_pdg());
    }

    #[test]
    fn test_requires_dataflow() {
        assert!(!CloneType::Type1.requires_dataflow());
        assert!(!CloneType::Type2.requires_dataflow());
        assert!(!CloneType::Type3.requires_dataflow());
        assert!(CloneType::Type4.requires_dataflow());
    }

    #[test]
    fn test_min_token_threshold() {
        assert_eq!(CloneType::Type1.min_token_threshold(), 50);
        assert_eq!(CloneType::Type2.min_token_threshold(), 50);
        assert_eq!(CloneType::Type3.min_token_threshold(), 30);
        assert_eq!(CloneType::Type4.min_token_threshold(), 20);
    }

    #[test]
    fn test_min_loc_threshold() {
        assert_eq!(CloneType::Type1.min_loc_threshold(), 6);
        assert_eq!(CloneType::Type2.min_loc_threshold(), 6);
        assert_eq!(CloneType::Type3.min_loc_threshold(), 4);
        assert_eq!(CloneType::Type4.min_loc_threshold(), 3);
    }

    #[test]
    fn test_similarity_threshold() {
        assert_eq!(CloneType::Type1.similarity_threshold(), 1.0);
        assert_eq!(CloneType::Type2.similarity_threshold(), 0.95);
        assert_eq!(CloneType::Type3.similarity_threshold(), 0.7);
        assert_eq!(CloneType::Type4.similarity_threshold(), 0.6);
    }

    #[test]
    fn test_display() {
        assert_eq!(format!("{}", CloneType::Type1), "Type-1");
        assert_eq!(format!("{}", CloneType::Type2), "Type-2");
        assert_eq!(format!("{}", CloneType::Type3), "Type-3");
        assert_eq!(format!("{}", CloneType::Type4), "Type-4");
    }

    #[test]
    fn test_from_u8() {
        assert_eq!(CloneType::from(1), CloneType::Type1);
        assert_eq!(CloneType::from(2), CloneType::Type2);
        assert_eq!(CloneType::from(3), CloneType::Type3);
        assert_eq!(CloneType::from(4), CloneType::Type4);
    }

    #[test]
    fn test_to_u8() {
        assert_eq!(u8::from(CloneType::Type1), 1);
        assert_eq!(u8::from(CloneType::Type2), 2);
        assert_eq!(u8::from(CloneType::Type3), 3);
        assert_eq!(u8::from(CloneType::Type4), 4);
    }

    #[test]
    fn test_serde_serialization() {
        let type1 = CloneType::Type1;
        let json = serde_json::to_string(&type1).unwrap();
        assert_eq!(json, "\"TYPE1\"");

        let type2 = CloneType::Type2;
        let json = serde_json::to_string(&type2).unwrap();
        assert_eq!(json, "\"TYPE2\"");
    }

    #[test]
    fn test_serde_deserialization() {
        let type1: CloneType = serde_json::from_str("\"TYPE1\"").unwrap();
        assert_eq!(type1, CloneType::Type1);

        let type3: CloneType = serde_json::from_str("\"TYPE3\"").unwrap();
        assert_eq!(type3, CloneType::Type3);
    }

    // =====================================================================
    // EDGE CASES (빡세게!)
    // =====================================================================

    #[test]
    #[should_panic(expected = "Invalid clone type: 0")]
    fn test_from_u8_zero() {
        let _ = CloneType::from(0);
    }

    #[test]
    #[should_panic(expected = "Invalid clone type: 5")]
    fn test_from_u8_out_of_range() {
        let _ = CloneType::from(5);
    }

    #[test]
    #[should_panic(expected = "Invalid clone type: 255")]
    fn test_from_u8_max() {
        let _ = CloneType::from(255);
    }

    #[test]
    fn test_equality() {
        assert_eq!(CloneType::Type1, CloneType::Type1);
        assert_ne!(CloneType::Type1, CloneType::Type2);
        assert_ne!(CloneType::Type2, CloneType::Type3);
        assert_ne!(CloneType::Type3, CloneType::Type4);
    }

    #[test]
    fn test_clone_and_copy() {
        let t1 = CloneType::Type1;
        let t2 = t1; // Copy
        let t3 = t1.clone(); // Clone
        assert_eq!(t1, t2);
        assert_eq!(t1, t3);
    }

    #[test]
    fn test_hash() {
        use std::collections::HashSet;
        let mut set = HashSet::new();
        set.insert(CloneType::Type1);
        set.insert(CloneType::Type2);
        set.insert(CloneType::Type1); // Duplicate
        assert_eq!(set.len(), 2);
    }

    // =====================================================================
    // CORNER CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_subset_transitivity() {
        // If A ⊂ B and B ⊂ C, then A ⊂ C
        let type1 = CloneType::Type1;
        let type2 = CloneType::Type2;
        let type4 = CloneType::Type4;

        assert!(type1.is_subset_of(type2));
        assert!(type2.is_subset_of(type4));
        assert!(type1.is_subset_of(type4)); // Transitivity
    }

    #[test]
    fn test_subset_reflexivity() {
        // Every type is subset of itself
        for clone_type in CloneType::all() {
            assert!(clone_type.is_subset_of(clone_type));
        }
    }

    #[test]
    fn test_threshold_monotonicity() {
        // As abstraction increases, thresholds should decrease or stay same
        let types = CloneType::all();
        for i in 0..types.len() - 1 {
            assert!(
                types[i].min_token_threshold() >= types[i + 1].min_token_threshold(),
                "Token threshold should decrease with abstraction"
            );
            assert!(
                types[i].min_loc_threshold() >= types[i + 1].min_loc_threshold(),
                "LOC threshold should decrease with abstraction"
            );
            assert!(
                types[i].similarity_threshold() >= types[i + 1].similarity_threshold(),
                "Similarity threshold should decrease with abstraction"
            );
        }
    }

    #[test]
    fn test_speed_inverse_monotonicity() {
        // As abstraction increases, speed should decrease
        let types = CloneType::all();
        for i in 0..types.len() - 1 {
            assert!(
                types[i].typical_speed() > types[i + 1].typical_speed(),
                "Speed should decrease with abstraction"
            );
        }
    }

    #[test]
    fn test_requirement_monotonicity() {
        // As abstraction increases, requirements should increase or stay same
        let types = CloneType::all();

        // Count requirements for each type
        for i in 0..types.len() - 1 {
            let curr_reqs = (types[i].requires_ast() as u8)
                + (types[i].requires_pdg() as u8)
                + (types[i].requires_dataflow() as u8);

            let next_reqs = (types[i + 1].requires_ast() as u8)
                + (types[i + 1].requires_pdg() as u8)
                + (types[i + 1].requires_dataflow() as u8);

            assert!(
                curr_reqs <= next_reqs,
                "Requirements should increase or stay same with abstraction"
            );
        }
    }

    #[test]
    fn test_roundtrip_conversion() {
        // u8 -> CloneType -> u8 should be identity
        for i in 1..=4 {
            let clone_type = CloneType::from(i);
            let back_to_u8 = u8::from(clone_type);
            assert_eq!(i, back_to_u8);
        }
    }

    #[test]
    fn test_all_types_unique() {
        let all = CloneType::all();
        for i in 0..all.len() {
            for j in (i + 1)..all.len() {
                assert_ne!(all[i], all[j], "All types should be unique");
            }
        }
    }

    #[test]
    fn test_similarity_threshold_range() {
        // All similarity thresholds should be in [0, 1]
        for clone_type in CloneType::all() {
            let threshold = clone_type.similarity_threshold();
            assert!(threshold >= 0.0 && threshold <= 1.0);
        }
    }

    #[test]
    fn test_min_thresholds_positive() {
        // All minimum thresholds should be positive
        for clone_type in CloneType::all() {
            assert!(clone_type.min_token_threshold() > 0);
            assert!(clone_type.min_loc_threshold() > 0);
        }
    }

    // =====================================================================
    // COMPLEX CASES (빡세게!)
    // =====================================================================

    #[test]
    fn test_bellon_standard_compliance() {
        // Bellon et al. (2007) recommend 50 tokens minimum
        assert!(CloneType::Type1.min_token_threshold() >= 50);
        assert!(CloneType::Type2.min_token_threshold() >= 50);

        // Type-3 threshold: 0.7 (70% similarity)
        assert_eq!(CloneType::Type3.similarity_threshold(), 0.7);
    }

    #[test]
    fn test_performance_expectations() {
        // Type-1 should be fastest (1M LOC/s)
        assert!(CloneType::Type1.typical_speed() >= 1_000_000);

        // Type-4 should be slowest (5K LOC/s)
        assert!(CloneType::Type4.typical_speed() <= 10_000);

        // Speed should drop at least 10x from Type-1 to Type-2
        assert!(CloneType::Type1.typical_speed() >= CloneType::Type2.typical_speed() * 2);
    }

    #[test]
    fn test_algorithm_complexity_consistency() {
        // Type-1 should be linear
        assert!(CloneType::Type1.complexity().contains("O(n)"));

        // Type-4 should be at least cubic
        assert!(
            CloneType::Type4.complexity().contains("O(n³)")
                || CloneType::Type4.complexity().contains("NP")
        );
    }

    #[test]
    fn test_description_non_empty() {
        for clone_type in CloneType::all() {
            assert!(!clone_type.description().is_empty());
            assert!(!clone_type.algorithm().is_empty());
            assert!(!clone_type.complexity().is_empty());
        }
    }

    #[test]
    fn test_json_roundtrip() {
        for clone_type in CloneType::all() {
            let json = serde_json::to_string(&clone_type).unwrap();
            let deserialized: CloneType = serde_json::from_str(&json).unwrap();
            assert_eq!(clone_type, deserialized);
        }
    }

    #[test]
    fn test_debug_format() {
        let type1 = CloneType::Type1;
        let debug_str = format!("{:?}", type1);
        assert!(debug_str.contains("Type1"));
    }

    #[test]
    fn test_multiple_serialization_formats() {
        let type2 = CloneType::Type2;

        // JSON
        let json = serde_json::to_string(&type2).unwrap();
        assert_eq!(json, "\"TYPE2\"");

        // MessagePack (binary)
        let msgpack = rmp_serde::to_vec(&type2).unwrap();
        let deserialized: CloneType = rmp_serde::from_slice(&msgpack).unwrap();
        assert_eq!(type2, deserialized);
    }

    #[test]
    fn test_abstraction_level_bijection() {
        // abstraction_level() should be bijective with [0,3]
        let mut levels = Vec::new();
        for clone_type in CloneType::all() {
            levels.push(clone_type.abstraction_level());
        }
        levels.sort();
        assert_eq!(levels, vec![0, 1, 2, 3]);
    }
}
