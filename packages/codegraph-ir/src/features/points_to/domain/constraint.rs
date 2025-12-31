//! Points-to Analysis Constraints
//!
//! Four constraint types following Andersen's formulation:
//! - ALLOC: x = new T()      → x ⊇ {alloc_site}
//! - COPY:  x = y            → x ⊇ y
//! - LOAD:  x = *y (or y.f)  → x ⊇ *y
//! - STORE: *x = y (or x.f)  → *x ⊇ y

use super::abstract_location::LocationId;
use serde::{Deserialize, Serialize};

/// Variable identifier (interned string index for performance)
pub type VarId = u32;

/// Constraint types for points-to analysis
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ConstraintKind {
    /// Base constraint: x = new T()
    /// Semantics: pts(x) ⊇ {alloc_site}
    Alloc,

    /// Copy constraint: x = y
    /// Semantics: pts(x) ⊇ pts(y)
    Copy,

    /// Load constraint: x = *y or x = y.f
    /// Semantics: ∀o ∈ pts(y): pts(x) ⊇ pts(o) (or pts(o.f))
    Load,

    /// Store constraint: *x = y or x.f = y
    /// Semantics: ∀o ∈ pts(x): pts(o) ⊇ pts(y) (or pts(o.f) ⊇ pts(y))
    Store,
}

impl ConstraintKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            ConstraintKind::Alloc => "ALLOC",
            ConstraintKind::Copy => "COPY",
            ConstraintKind::Load => "LOAD",
            ConstraintKind::Store => "STORE",
        }
    }
}

/// A single constraint in the points-to analysis
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Constraint {
    /// Constraint type
    pub kind: ConstraintKind,

    /// Left-hand side variable (destination)
    pub lhs: VarId,

    /// Right-hand side variable or location
    /// - For ALLOC: location ID
    /// - For COPY/LOAD/STORE: source variable ID
    pub rhs: VarId,

    /// Optional field for field-sensitive analysis
    /// If Some, this is a field access (x.field or x->field)
    pub field: Option<u32>,

    /// Source location for debugging
    pub source_line: Option<u32>,
}

impl Constraint {
    /// Create an ALLOC constraint: x = new T()
    #[inline]
    pub fn alloc(lhs: VarId, location: LocationId) -> Self {
        Self {
            kind: ConstraintKind::Alloc,
            lhs,
            rhs: location,
            field: None,
            source_line: None,
        }
    }

    /// Create a COPY constraint: x = y
    #[inline]
    pub fn copy(lhs: VarId, rhs: VarId) -> Self {
        Self {
            kind: ConstraintKind::Copy,
            lhs,
            rhs,
            field: None,
            source_line: None,
        }
    }

    /// Create a LOAD constraint: x = *y
    #[inline]
    pub fn load(lhs: VarId, rhs: VarId) -> Self {
        Self {
            kind: ConstraintKind::Load,
            lhs,
            rhs,
            field: None,
            source_line: None,
        }
    }

    /// Create a STORE constraint: *x = y
    #[inline]
    pub fn store(lhs: VarId, rhs: VarId) -> Self {
        Self {
            kind: ConstraintKind::Store,
            lhs,
            rhs,
            field: None,
            source_line: None,
        }
    }

    /// Create a field LOAD constraint: x = y.f
    #[inline]
    pub fn field_load(lhs: VarId, base: VarId, field: u32) -> Self {
        Self {
            kind: ConstraintKind::Load,
            lhs,
            rhs: base,
            field: Some(field),
            source_line: None,
        }
    }

    /// Create a field STORE constraint: x.f = y
    #[inline]
    pub fn field_store(base: VarId, field: u32, rhs: VarId) -> Self {
        Self {
            kind: ConstraintKind::Store,
            lhs: base,
            rhs,
            field: Some(field),
            source_line: None,
        }
    }

    /// Add source location for debugging
    #[inline]
    pub fn with_source(mut self, line: u32) -> Self {
        self.source_line = Some(line);
        self
    }

    /// Check if this is a field access constraint
    #[inline]
    pub fn is_field_access(&self) -> bool {
        self.field.is_some()
    }

    /// Check if this is a complex constraint (LOAD or STORE)
    #[inline]
    pub fn is_complex(&self) -> bool {
        matches!(self.kind, ConstraintKind::Load | ConstraintKind::Store)
    }
}

/// Constraint set with statistics
#[derive(Debug, Default)]
pub struct ConstraintSet {
    /// All constraints
    pub constraints: Vec<Constraint>,

    /// Statistics
    pub alloc_count: usize,
    pub copy_count: usize,
    pub load_count: usize,
    pub store_count: usize,
}

impl ConstraintSet {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            constraints: Vec::with_capacity(capacity),
            ..Default::default()
        }
    }

    /// Add a constraint and update statistics
    pub fn add(&mut self, constraint: Constraint) {
        match constraint.kind {
            ConstraintKind::Alloc => self.alloc_count += 1,
            ConstraintKind::Copy => self.copy_count += 1,
            ConstraintKind::Load => self.load_count += 1,
            ConstraintKind::Store => self.store_count += 1,
        }
        self.constraints.push(constraint);
    }

    /// Total number of constraints
    #[inline]
    pub fn len(&self) -> usize {
        self.constraints.len()
    }

    /// Check if empty
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.constraints.is_empty()
    }

    /// Iterate over constraints
    #[inline]
    pub fn iter(&self) -> impl Iterator<Item = &Constraint> {
        self.constraints.iter()
    }

    /// Get constraints by kind
    pub fn by_kind(&self, kind: ConstraintKind) -> impl Iterator<Item = &Constraint> {
        self.constraints.iter().filter(move |c| c.kind == kind)
    }

    /// Get all ALLOC constraints (base case for solving)
    pub fn allocs(&self) -> impl Iterator<Item = &Constraint> {
        self.by_kind(ConstraintKind::Alloc)
    }

    /// Get all COPY constraints
    pub fn copies(&self) -> impl Iterator<Item = &Constraint> {
        self.by_kind(ConstraintKind::Copy)
    }

    /// Get complex constraints (LOAD + STORE)
    pub fn complex(&self) -> impl Iterator<Item = &Constraint> {
        self.constraints
            .iter()
            .filter(|c| matches!(c.kind, ConstraintKind::Load | ConstraintKind::Store))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_alloc_constraint() {
        let c = Constraint::alloc(1, 10);
        assert_eq!(c.kind, ConstraintKind::Alloc);
        assert_eq!(c.lhs, 1);
        assert_eq!(c.rhs, 10);
        assert!(!c.is_complex());
    }

    #[test]
    fn test_copy_constraint() {
        let c = Constraint::copy(1, 2);
        assert_eq!(c.kind, ConstraintKind::Copy);
        assert!(!c.is_complex());
    }

    #[test]
    fn test_field_constraint() {
        let c = Constraint::field_load(1, 2, 5);
        assert!(c.is_field_access());
        assert!(c.is_complex());
        assert_eq!(c.field, Some(5));
    }

    #[test]
    fn test_constraint_set() {
        let mut set = ConstraintSet::new();
        set.add(Constraint::alloc(1, 10));
        set.add(Constraint::copy(2, 1));
        set.add(Constraint::load(3, 2));

        assert_eq!(set.len(), 3);
        assert_eq!(set.alloc_count, 1);
        assert_eq!(set.copy_count, 1);
        assert_eq!(set.load_count, 1);
    }
}
