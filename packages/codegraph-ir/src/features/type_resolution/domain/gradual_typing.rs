//! Gradual Typing System
//!
//! Implements SOTA gradual typing based on:
//! - Siek & Taha (2006): "Gradual Typing for Functional Languages"
//! - Siek & Vachharajani (2008): "Gradual Typing with Unification-based Inference"
//!
//! ## Key Concepts
//!
//! 1. **Consistency Relation (~)**: Unlike subtyping, consistency is symmetric
//!    - `Any ~ T` for all T
//!    - `T ~ Any` for all T
//!    - Structural consistency for compound types
//!
//! 2. **Blame Tracking**: When runtime type errors occur, identify the source
//!    - Positive blame: value flowed into context expecting different type
//!    - Negative blame: context expected different type than value
//!
//! 3. **Cast Insertion**: Automatically insert casts at type boundaries
//!    - `⟨T⟩e` casts expression `e` to type `T`
//!
//! ## Performance
//! - Consistency check: O(size of types)
//! - Blame tracking: O(1) per cast
//! - Cast insertion: O(AST nodes)

use super::{Type, TypeKind};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fmt;

// ==================== Consistency Relation ====================

/// Consistency relation result
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConsistencyResult {
    /// Types are consistent
    Consistent,
    /// Types are inconsistent with explanation
    Inconsistent(String),
}

impl ConsistencyResult {
    pub fn is_consistent(&self) -> bool {
        matches!(self, ConsistencyResult::Consistent)
    }
}

/// Check if two types are consistent (gradual typing relation)
///
/// Consistency (~) is different from subtyping (<:):
/// - Consistency is symmetric: T ~ S ⟺ S ~ T
/// - Any is consistent with everything: Any ~ T for all T
/// - Structural consistency for compound types
///
/// # Examples
/// ```ignore
/// assert!(is_consistent(&Type::any(), &Type::simple("int"))); // Any ~ int
/// assert!(is_consistent(&Type::simple("int"), &Type::any())); // int ~ Any
/// assert!(!is_consistent(&Type::simple("int"), &Type::simple("str"))); // int ≁ str
/// ```
pub fn is_consistent(t1: &Type, t2: &Type) -> ConsistencyResult {
    match (&t1.kind, &t2.kind) {
        // Any is consistent with everything
        (TypeKind::Any, _) | (_, TypeKind::Any) => ConsistencyResult::Consistent,

        // Never is consistent with nothing (bottom type)
        (TypeKind::Never, _) | (_, TypeKind::Never) => ConsistencyResult::Consistent,

        // None is consistent with None
        (TypeKind::None, TypeKind::None) => ConsistencyResult::Consistent,

        // Simple types must match exactly
        (TypeKind::Simple(n1), TypeKind::Simple(n2)) => {
            if n1 == n2 {
                ConsistencyResult::Consistent
            } else {
                ConsistencyResult::Inconsistent(format!(
                    "Type mismatch: '{}' is not consistent with '{}'",
                    n1, n2
                ))
            }
        }

        // Literal consistent with its base type
        (TypeKind::Literal(v), TypeKind::Simple(name)) => {
            let literal_base = infer_literal_base_type(v);
            if literal_base == *name {
                ConsistencyResult::Consistent
            } else {
                ConsistencyResult::Inconsistent(format!(
                    "Literal '{}' (base type '{}') not consistent with '{}'",
                    v, literal_base, name
                ))
            }
        }
        (TypeKind::Simple(name), TypeKind::Literal(v)) => {
            let literal_base = infer_literal_base_type(v);
            if literal_base == *name {
                ConsistencyResult::Consistent
            } else {
                ConsistencyResult::Inconsistent(format!(
                    "'{}' not consistent with literal '{}' (base type '{}')",
                    name, v, literal_base
                ))
            }
        }

        // Generic types: base must match, params must be pairwise consistent
        (
            TypeKind::Generic {
                base: b1,
                params: p1,
            },
            TypeKind::Generic {
                base: b2,
                params: p2,
            },
        ) => {
            if b1 != b2 {
                return ConsistencyResult::Inconsistent(format!(
                    "Generic base mismatch: '{}' vs '{}'",
                    b1, b2
                ));
            }
            if p1.len() != p2.len() {
                return ConsistencyResult::Inconsistent(format!(
                    "Generic arity mismatch: {} vs {} type parameters",
                    p1.len(),
                    p2.len()
                ));
            }
            for (i, (param1, param2)) in p1.iter().zip(p2.iter()).enumerate() {
                if let ConsistencyResult::Inconsistent(reason) = is_consistent(param1, param2) {
                    return ConsistencyResult::Inconsistent(format!(
                        "Type parameter {} inconsistent: {}",
                        i, reason
                    ));
                }
            }
            ConsistencyResult::Consistent
        }

        // Union types: each member must be consistent with some member of other
        (TypeKind::Union(types1), TypeKind::Union(types2)) => {
            // For gradual typing, unions are consistent if they overlap
            for t1_member in types1 {
                let mut found_consistent = false;
                for t2_member in types2 {
                    if is_consistent(t1_member, t2_member).is_consistent() {
                        found_consistent = true;
                        break;
                    }
                }
                if !found_consistent {
                    return ConsistencyResult::Inconsistent(format!(
                        "Union member '{}' has no consistent counterpart",
                        t1_member
                    ));
                }
            }
            ConsistencyResult::Consistent
        }

        // Union with non-union: at least one member must be consistent
        (TypeKind::Union(types), other) | (other, TypeKind::Union(types)) => {
            let other_type = Type {
                kind: other.clone(),
            };
            for member in types {
                if is_consistent(member, &other_type).is_consistent() {
                    return ConsistencyResult::Consistent;
                }
            }
            ConsistencyResult::Inconsistent(format!(
                "No union member consistent with '{:?}'",
                other
            ))
        }

        // Callable types: contravariant params, covariant return
        (
            TypeKind::Callable {
                params: p1,
                return_type: r1,
            },
            TypeKind::Callable {
                params: p2,
                return_type: r2,
            },
        ) => {
            if p1.len() != p2.len() {
                return ConsistencyResult::Inconsistent(format!(
                    "Callable arity mismatch: {} vs {} parameters",
                    p1.len(),
                    p2.len()
                ));
            }
            // Parameters are contravariant (reversed consistency)
            for (i, (param1, param2)) in p1.iter().zip(p2.iter()).enumerate() {
                if let ConsistencyResult::Inconsistent(reason) = is_consistent(param2, param1) {
                    return ConsistencyResult::Inconsistent(format!(
                        "Parameter {} inconsistent (contravariant): {}",
                        i, reason
                    ));
                }
            }
            // Return type is covariant
            if let ConsistencyResult::Inconsistent(reason) = is_consistent(r1, r2) {
                return ConsistencyResult::Inconsistent(format!(
                    "Return type inconsistent: {}",
                    reason
                ));
            }
            ConsistencyResult::Consistent
        }

        // Intersection types: must be consistent with all members
        (TypeKind::Intersection(types), other) | (other, TypeKind::Intersection(types)) => {
            let other_type = Type {
                kind: other.clone(),
            };
            for member in types {
                if let ConsistencyResult::Inconsistent(reason) = is_consistent(member, &other_type)
                {
                    return ConsistencyResult::Inconsistent(format!(
                        "Intersection member inconsistent: {}",
                        reason
                    ));
                }
            }
            ConsistencyResult::Consistent
        }

        // TypeVar is consistent with anything (like Any for unification)
        (TypeKind::TypeVar(_), _) | (_, TypeKind::TypeVar(_)) => ConsistencyResult::Consistent,

        // Default: inconsistent
        _ => ConsistencyResult::Inconsistent(format!(
            "Types '{:?}' and '{:?}' are structurally incompatible",
            t1.kind, t2.kind
        )),
    }
}

/// Infer base type from literal value
fn infer_literal_base_type(value: &str) -> String {
    if value.starts_with('"') || value.starts_with('\'') {
        "str".to_string()
    } else if value == "True" || value == "False" {
        "bool".to_string()
    } else if value == "None" {
        "None".to_string()
    } else if value.contains('.') {
        "float".to_string()
    } else if value.chars().all(|c| c.is_ascii_digit() || c == '-') {
        "int".to_string()
    } else {
        "object".to_string()
    }
}

// ==================== Blame Tracking ====================

/// Blame label for tracking type errors
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct BlameLabel {
    /// Unique identifier for this blame point
    pub id: String,
    /// Source location (file:line:column)
    pub location: String,
    /// Description of the cast/boundary
    pub description: String,
}

impl BlameLabel {
    pub fn new(
        id: impl Into<String>,
        location: impl Into<String>,
        description: impl Into<String>,
    ) -> Self {
        Self {
            id: id.into(),
            location: location.into(),
            description: description.into(),
        }
    }
}

impl fmt::Display for BlameLabel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}@{}", self.id, self.location)
    }
}

/// Blame polarity
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BlamePolarity {
    /// Positive blame: value producer is at fault
    /// e.g., function returned wrong type
    Positive,
    /// Negative blame: value consumer is at fault
    /// e.g., function received wrong argument type
    Negative,
}

/// Blame information for a type cast
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlameInfo {
    /// Blame label
    pub label: BlameLabel,
    /// Polarity (positive or negative)
    pub polarity: BlamePolarity,
    /// Source type (what was provided)
    pub source_type: String,
    /// Target type (what was expected)
    pub target_type: String,
    /// Call stack at time of cast (for debugging)
    pub call_stack: Vec<String>,
}

impl BlameInfo {
    pub fn new(
        label: BlameLabel,
        polarity: BlamePolarity,
        source_type: impl Into<String>,
        target_type: impl Into<String>,
    ) -> Self {
        Self {
            label,
            polarity,
            source_type: source_type.into(),
            target_type: target_type.into(),
            call_stack: Vec::new(),
        }
    }

    pub fn with_call_stack(mut self, stack: Vec<String>) -> Self {
        self.call_stack = stack;
        self
    }
}

impl fmt::Display for BlameInfo {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let polarity_str = match self.polarity {
            BlamePolarity::Positive => "+",
            BlamePolarity::Negative => "-",
        };
        write!(
            f,
            "Blame[{}{}]: {} → {} at {}",
            polarity_str, self.label.id, self.source_type, self.target_type, self.label.location
        )
    }
}

/// Blame tracker for collecting runtime type errors
#[derive(Debug, Default)]
pub struct BlameTracker {
    /// All blame infos collected
    blames: Vec<BlameInfo>,
    /// Counter for generating unique blame IDs
    next_id: usize,
}

impl BlameTracker {
    pub fn new() -> Self {
        Self {
            blames: Vec::new(),
            next_id: 0,
        }
    }

    /// Generate a new unique blame label
    pub fn new_label(
        &mut self,
        location: impl Into<String>,
        description: impl Into<String>,
    ) -> BlameLabel {
        let id = format!("blame_{}", self.next_id);
        self.next_id += 1;
        BlameLabel::new(id, location, description)
    }

    /// Record a blame (runtime type error)
    pub fn record_blame(&mut self, info: BlameInfo) {
        self.blames.push(info);
    }

    /// Get all recorded blames
    pub fn get_blames(&self) -> &[BlameInfo] {
        &self.blames
    }

    /// Get blames at a specific location
    pub fn get_blames_at(&self, location: &str) -> Vec<&BlameInfo> {
        self.blames
            .iter()
            .filter(|b| b.label.location == location)
            .collect()
    }

    /// Clear all recorded blames
    pub fn clear(&mut self) {
        self.blames.clear();
    }

    /// Get total number of blames
    pub fn blame_count(&self) -> usize {
        self.blames.len()
    }
}

// ==================== Cast Insertion ====================

/// Type cast kind
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum CastKind {
    /// Upcast to dynamic type (losing static info)
    /// T → Any (always safe)
    Upcast,
    /// Downcast from dynamic type (runtime check needed)
    /// Any → T (may fail at runtime)
    Downcast,
    /// Identity cast (no runtime check)
    Identity,
    /// Ground cast between compatible ground types
    Ground,
}

/// A type cast operation
#[derive(Debug, Clone)]
pub struct TypeCast {
    /// Source type
    pub source: Type,
    /// Target type
    pub target: Type,
    /// Cast kind
    pub kind: CastKind,
    /// Blame label for this cast
    pub blame: BlameLabel,
}

impl TypeCast {
    pub fn new(source: Type, target: Type, blame: BlameLabel) -> Self {
        let kind = determine_cast_kind(&source, &target);
        Self {
            source,
            target,
            kind,
            blame,
        }
    }

    /// Check if this cast requires a runtime check
    pub fn needs_runtime_check(&self) -> bool {
        matches!(self.kind, CastKind::Downcast)
    }
}

impl fmt::Display for TypeCast {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "⟨{}⟩{}", self.target, self.blame)
    }
}

/// Determine the kind of cast between two types
fn determine_cast_kind(source: &Type, target: &Type) -> CastKind {
    match (&source.kind, &target.kind) {
        // Same type: identity
        _ if source == target => CastKind::Identity,

        // To Any: upcast (safe)
        (_, TypeKind::Any) => CastKind::Upcast,

        // From Any: downcast (needs runtime check)
        (TypeKind::Any, _) => CastKind::Downcast,

        // Ground types: ground cast
        _ => CastKind::Ground,
    }
}

/// Cast inserter for gradual type boundaries
#[derive(Debug)]
pub struct CastInserter {
    /// Blame tracker for generating labels
    blame_tracker: BlameTracker,
    /// Inserted casts
    casts: Vec<TypeCast>,
}

impl CastInserter {
    pub fn new() -> Self {
        Self {
            blame_tracker: BlameTracker::new(),
            casts: Vec::new(),
        }
    }

    /// Insert a cast if types are not equal
    ///
    /// Returns `Some(cast)` if cast needed, `None` if types are equal
    pub fn insert_cast_if_needed(
        &mut self,
        source: &Type,
        target: &Type,
        location: impl Into<String>,
        description: impl Into<String>,
    ) -> Option<TypeCast> {
        if source == target {
            return None;
        }

        // Check consistency first
        if let ConsistencyResult::Inconsistent(reason) = is_consistent(source, target) {
            // Log warning but still insert cast (will fail at runtime)
            eprintln!("[CastInserter] Warning: Inconsistent cast: {}", reason);
        }

        let blame = self.blame_tracker.new_label(location, description);
        let cast = TypeCast::new(source.clone(), target.clone(), blame);
        self.casts.push(cast.clone());
        Some(cast)
    }

    /// Get all inserted casts
    pub fn get_casts(&self) -> &[TypeCast] {
        &self.casts
    }

    /// Get casts that need runtime checks
    pub fn get_runtime_checks(&self) -> Vec<&TypeCast> {
        self.casts
            .iter()
            .filter(|c| c.needs_runtime_check())
            .collect()
    }

    /// Get the blame tracker
    pub fn blame_tracker(&self) -> &BlameTracker {
        &self.blame_tracker
    }

    /// Get mutable blame tracker
    pub fn blame_tracker_mut(&mut self) -> &mut BlameTracker {
        &mut self.blame_tracker
    }
}

impl Default for CastInserter {
    fn default() -> Self {
        Self::new()
    }
}

// ==================== Gradual Guarantee ====================

/// Result of gradual guarantee check
#[derive(Debug, Clone)]
pub struct GradualGuaranteeResult {
    /// Whether the guarantee holds
    pub holds: bool,
    /// Explanation
    pub explanation: String,
    /// Affected casts (if guarantee violated)
    pub affected_casts: Vec<String>,
}

/// Check the gradual guarantee property
///
/// The gradual guarantee states that:
/// 1. Adding type annotations should not change runtime behavior
/// 2. Removing type annotations should not change runtime behavior (except for errors)
///
/// This is a static approximation of the guarantee.
pub fn check_gradual_guarantee(
    original_type: &Type,
    annotated_type: &Type,
) -> GradualGuaranteeResult {
    // If types are consistent, guarantee holds
    if is_consistent(original_type, annotated_type).is_consistent() {
        return GradualGuaranteeResult {
            holds: true,
            explanation: "Types are consistent, gradual guarantee holds".to_string(),
            affected_casts: Vec::new(),
        };
    }

    // If original has Any and annotated doesn't, annotation is refinement (OK)
    if has_any_type(original_type) && !has_any_type(annotated_type) {
        return GradualGuaranteeResult {
            holds: true,
            explanation: "Type annotation refines dynamic type".to_string(),
            affected_casts: Vec::new(),
        };
    }

    GradualGuaranteeResult {
        holds: false,
        explanation: format!(
            "Type annotation changes semantics: {} → {}",
            original_type, annotated_type
        ),
        affected_casts: vec![format!("{} → {}", original_type, annotated_type)],
    }
}

/// Check if type contains Any
fn has_any_type(ty: &Type) -> bool {
    match &ty.kind {
        TypeKind::Any => true,
        TypeKind::Union(types) | TypeKind::Intersection(types) => types.iter().any(has_any_type),
        TypeKind::Generic { params, .. } => params.iter().any(has_any_type),
        TypeKind::Callable {
            params,
            return_type,
        } => params.iter().any(has_any_type) || has_any_type(return_type),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_any_consistency() {
        let any = Type::any();
        let int = Type::simple("int");
        let str_type = Type::simple("str");

        // Any is consistent with everything
        assert!(is_consistent(&any, &int).is_consistent());
        assert!(is_consistent(&int, &any).is_consistent());
        assert!(is_consistent(&any, &str_type).is_consistent());
        assert!(is_consistent(&any, &any).is_consistent());
    }

    #[test]
    fn test_simple_type_consistency() {
        let int = Type::simple("int");
        let str_type = Type::simple("str");

        // Same type is consistent
        assert!(is_consistent(&int, &int).is_consistent());
        assert!(is_consistent(&str_type, &str_type).is_consistent());

        // Different types are inconsistent
        assert!(!is_consistent(&int, &str_type).is_consistent());
    }

    #[test]
    fn test_generic_consistency() {
        let list_int = Type::generic("List", vec![Type::simple("int")]);
        let list_str = Type::generic("List", vec![Type::simple("str")]);
        let list_any = Type::generic("List", vec![Type::any()]);

        // Same generic is consistent
        assert!(is_consistent(&list_int, &list_int).is_consistent());

        // Different element types are inconsistent
        assert!(!is_consistent(&list_int, &list_str).is_consistent());

        // List[Any] is consistent with List[T] for any T
        assert!(is_consistent(&list_any, &list_int).is_consistent());
        assert!(is_consistent(&list_int, &list_any).is_consistent());
    }

    #[test]
    fn test_union_consistency() {
        let int_or_str = Type::union(vec![Type::simple("int"), Type::simple("str")]);
        let int = Type::simple("int");
        let bool_type = Type::simple("bool");

        // Union is consistent with its members
        assert!(is_consistent(&int_or_str, &int).is_consistent());

        // Union is inconsistent with non-members
        assert!(!is_consistent(&int_or_str, &bool_type).is_consistent());
    }

    #[test]
    fn test_callable_consistency() {
        let fn1 = Type::callable(vec![Type::simple("int")], Type::simple("str"));
        let fn2 = Type::callable(vec![Type::simple("int")], Type::simple("str"));
        let fn3 = Type::callable(vec![Type::any()], Type::simple("str"));

        // Same callable is consistent
        assert!(is_consistent(&fn1, &fn2).is_consistent());

        // Any in params is consistent (contravariant)
        assert!(is_consistent(&fn1, &fn3).is_consistent());
    }

    #[test]
    fn test_blame_tracker() {
        let mut tracker = BlameTracker::new();

        let label = tracker.new_label("file.py:10:5", "function call");
        assert_eq!(label.id, "blame_0");

        let blame = BlameInfo::new(label, BlamePolarity::Positive, "int", "str");
        tracker.record_blame(blame);

        assert_eq!(tracker.blame_count(), 1);
    }

    #[test]
    fn test_cast_inserter() {
        let mut inserter = CastInserter::new();

        let int = Type::simple("int");
        let any = Type::any();

        // Cast int → Any (upcast)
        let cast = inserter.insert_cast_if_needed(&int, &any, "line:10", "upcast to any");
        assert!(cast.is_some());
        assert_eq!(cast.unwrap().kind, CastKind::Upcast);

        // Cast Any → int (downcast)
        let cast = inserter.insert_cast_if_needed(&any, &int, "line:20", "downcast from any");
        assert!(cast.is_some());
        let cast = cast.unwrap();
        assert_eq!(cast.kind, CastKind::Downcast);
        assert!(cast.needs_runtime_check());
    }

    #[test]
    fn test_cast_kind_determination() {
        let int = Type::simple("int");
        let any = Type::any();

        // Identity
        assert_eq!(determine_cast_kind(&int, &int), CastKind::Identity);

        // Upcast
        assert_eq!(determine_cast_kind(&int, &any), CastKind::Upcast);

        // Downcast
        assert_eq!(determine_cast_kind(&any, &int), CastKind::Downcast);
    }

    #[test]
    fn test_gradual_guarantee() {
        let any = Type::any();
        let int = Type::simple("int");
        let str_type = Type::simple("str");

        // Refining Any to int: guarantee holds
        let result = check_gradual_guarantee(&any, &int);
        assert!(result.holds);

        // int → str: guarantee violated
        let result = check_gradual_guarantee(&int, &str_type);
        assert!(!result.holds);
    }

    #[test]
    fn test_literal_consistency() {
        let literal_42 = Type::literal("42");
        let int = Type::simple("int");
        let str_type = Type::simple("str");

        // Literal[42] ~ int
        assert!(is_consistent(&literal_42, &int).is_consistent());

        // Literal[42] ≁ str
        assert!(!is_consistent(&literal_42, &str_type).is_consistent());
    }
}
