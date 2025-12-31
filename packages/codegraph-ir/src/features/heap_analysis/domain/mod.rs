//! Heap Analysis Domain - Core Business Logic & Value Objects
//!
//! This module contains the domain models (entities, value objects) for heap analysis.
//! Domain logic is independent of infrastructure concerns.
//!
//! ## DDD Concepts Applied
//! - **Entity**: Objects with identity (HeapObject, AllocationSite)
//! - **Value Object**: Immutable objects defined by attributes (EscapeState, OwnershipState)
//! - **Domain Service**: Business logic that doesn't belong to entities
//!
//! ## SOLID Compliance
//! - **S**: Each struct has single responsibility
//! - **O**: Extensible via new variants in enums
//! - **L**: All states are valid substitutes

use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fmt;

// ═══════════════════════════════════════════════════════════════════════════
// Value Objects - Immutable, Defined by Attributes
// ═══════════════════════════════════════════════════════════════════════════

/// Escape State (Value Object)
///
/// Defines how an object reference escapes its scope.
/// Based on Choi et al. (1999) escape analysis lattice.
///
/// Lattice: NoEscape < ArgEscape < GlobalEscape
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EscapeState {
    /// Object never leaves method scope (stack-allocatable)
    NoEscape,

    /// Object is passed as argument but doesn't escape caller
    ArgEscape,

    /// Object escapes via return statement
    ReturnEscape,

    /// Object escapes via field assignment
    FieldEscape,

    /// Object escapes via array storage
    ArrayEscape,

    /// Object escapes to global/heap (most conservative)
    GlobalEscape,

    /// Unknown escape state (analysis incomplete)
    Unknown,
}

impl EscapeState {
    /// Check if object can be stack-allocated
    pub fn is_stack_allocatable(&self) -> bool {
        matches!(self, EscapeState::NoEscape | EscapeState::ArgEscape)
    }

    /// Check if object definitely escapes
    pub fn escapes(&self) -> bool {
        !matches!(self, EscapeState::NoEscape | EscapeState::ArgEscape | EscapeState::Unknown)
    }

    /// Join two escape states (least upper bound)
    pub fn join(self, other: Self) -> Self {
        use EscapeState::*;
        match (self, other) {
            (Unknown, x) | (x, Unknown) => x,
            (NoEscape, x) | (x, NoEscape) => x,
            (ArgEscape, x) | (x, ArgEscape) if !matches!(x, NoEscape | Unknown) => x,
            (GlobalEscape, _) | (_, GlobalEscape) => GlobalEscape,
            (FieldEscape, _) | (_, FieldEscape) => FieldEscape,
            (ArrayEscape, _) | (_, ArrayEscape) => ArrayEscape,
            (ReturnEscape, _) | (_, ReturnEscape) => ReturnEscape,
            _ => self,
        }
    }
}

impl Default for EscapeState {
    fn default() -> Self {
        EscapeState::Unknown
    }
}

impl fmt::Display for EscapeState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            EscapeState::NoEscape => write!(f, "NoEscape"),
            EscapeState::ArgEscape => write!(f, "ArgEscape"),
            EscapeState::ReturnEscape => write!(f, "ReturnEscape"),
            EscapeState::FieldEscape => write!(f, "FieldEscape"),
            EscapeState::ArrayEscape => write!(f, "ArrayEscape"),
            EscapeState::GlobalEscape => write!(f, "GlobalEscape"),
            EscapeState::Unknown => write!(f, "Unknown"),
        }
    }
}

/// Ownership State (Value Object)
///
/// Rust-inspired ownership tracking for any language.
/// Based on Weiss et al. (2019) "Oxide: The Essence of Rust".
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OwnershipState {
    /// Variable owns the value
    Owned,

    /// Variable has been moved from (invalid to use)
    Moved,

    /// Variable is immutably borrowed
    BorrowedImmut,

    /// Variable is mutably borrowed
    BorrowedMut,

    /// Ownership transferred via copy (for Copy types)
    Copied,

    /// Variable is uninitialized
    Uninitialized,

    /// Variable is in error state
    Invalid,
}

impl OwnershipState {
    /// Check if variable can be read
    pub fn can_read(&self) -> bool {
        matches!(
            self,
            OwnershipState::Owned | OwnershipState::BorrowedImmut | OwnershipState::Copied
        )
    }

    /// Check if variable can be written
    pub fn can_write(&self) -> bool {
        matches!(self, OwnershipState::Owned | OwnershipState::BorrowedMut)
    }

    /// Check if variable can be moved
    pub fn can_move(&self) -> bool {
        matches!(self, OwnershipState::Owned)
    }

    /// Check if state is valid for use
    pub fn is_valid(&self) -> bool {
        !matches!(
            self,
            OwnershipState::Moved | OwnershipState::Uninitialized | OwnershipState::Invalid
        )
    }
}

impl Default for OwnershipState {
    fn default() -> Self {
        OwnershipState::Uninitialized
    }
}

impl fmt::Display for OwnershipState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OwnershipState::Owned => write!(f, "Owned"),
            OwnershipState::Moved => write!(f, "Moved"),
            OwnershipState::BorrowedImmut => write!(f, "BorrowedImmut"),
            OwnershipState::BorrowedMut => write!(f, "BorrowedMut"),
            OwnershipState::Copied => write!(f, "Copied"),
            OwnershipState::Uninitialized => write!(f, "Uninitialized"),
            OwnershipState::Invalid => write!(f, "Invalid"),
        }
    }
}

/// Issue Severity (Value Object)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IssueSeverity {
    /// Information only
    Info,
    /// Potential issue (warning)
    Warning,
    /// Definite issue (error)
    Error,
    /// Critical security issue
    Critical,
}

impl Default for IssueSeverity {
    fn default() -> Self {
        IssueSeverity::Warning
    }
}

/// Issue Category (Value Object)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IssueCategory {
    /// Null pointer dereference
    NullDereference,
    /// Use after free
    UseAfterFree,
    /// Double free
    DoubleFree,
    /// Buffer overflow
    BufferOverflow,
    /// Spatial memory safety (OOB pointer arithmetic)
    SpatialSafety,
    /// Use after move
    UseAfterMove,
    /// Borrow conflict
    BorrowConflict,
    /// Security vulnerability
    Security,
    /// Memory leak
    MemoryLeak,
    /// Uninitialized read
    UninitializedRead,
}

impl fmt::Display for IssueCategory {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IssueCategory::NullDereference => write!(f, "Null Dereference"),
            IssueCategory::UseAfterFree => write!(f, "Use After Free"),
            IssueCategory::DoubleFree => write!(f, "Double Free"),
            IssueCategory::BufferOverflow => write!(f, "Buffer Overflow"),
            IssueCategory::SpatialSafety => write!(f, "Spatial Safety"),
            IssueCategory::UseAfterMove => write!(f, "Use After Move"),
            IssueCategory::BorrowConflict => write!(f, "Borrow Conflict"),
            IssueCategory::Security => write!(f, "Security"),
            IssueCategory::MemoryLeak => write!(f, "Memory Leak"),
            IssueCategory::UninitializedRead => write!(f, "Uninitialized Read"),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Entities - Objects with Identity
// ═══════════════════════════════════════════════════════════════════════════

/// Heap Issue (Entity)
///
/// Represents a detected heap-related issue with full context.
/// Identity: unique id
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeapIssue {
    /// Unique identifier
    pub id: String,

    /// Issue category
    pub category: IssueCategory,

    /// Issue severity
    pub severity: IssueSeverity,

    /// Variable/location involved
    pub variable: String,

    /// File path
    pub file_path: String,

    /// Line number
    pub line: usize,

    /// Human-readable message
    pub message: String,

    /// Additional context (e.g., stack trace, related variables)
    pub context: Vec<String>,

    /// Fix suggestion (optional)
    pub suggestion: Option<String>,
}

impl HeapIssue {
    /// Create new heap issue
    pub fn new(
        category: IssueCategory,
        severity: IssueSeverity,
        variable: &str,
        line: usize,
        file_path: &str,
        message: &str,
    ) -> Self {
        Self {
            id: format!("{:?}_{}_{}_{}", category, file_path, line, variable),
            category,
            severity,
            variable: variable.to_string(),
            file_path: file_path.to_string(),
            line,
            message: message.to_string(),
            context: Vec::new(),
            suggestion: None,
        }
    }

    /// Create null dereference issue
    pub fn null_dereference(variable: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::NullDereference,
            IssueSeverity::Error,
            variable,
            line,
            file_path,
            &format!("Potential null dereference of '{}'", variable),
        )
    }

    /// Create use-after-free issue
    pub fn use_after_free(variable: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::UseAfterFree,
            IssueSeverity::Critical,
            variable,
            line,
            file_path,
            &format!("Use after free of '{}'", variable),
        )
    }

    /// Create double-free issue
    pub fn double_free(variable: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::DoubleFree,
            IssueSeverity::Critical,
            variable,
            line,
            file_path,
            &format!("Double free of '{}'", variable),
        )
    }

    /// Create buffer overflow issue
    pub fn buffer_overflow(variable: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::BufferOverflow,
            IssueSeverity::Critical,
            variable,
            line,
            file_path,
            &format!("Buffer overflow in '{}'", variable),
        )
    }

    /// Create use-after-move issue
    pub fn use_after_move(variable: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::UseAfterMove,
            IssueSeverity::Error,
            variable,
            line,
            file_path,
            &format!("Use of moved value '{}'", variable),
        )
    }

    /// Create borrow conflict issue
    pub fn borrow_conflict(variable: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::BorrowConflict,
            IssueSeverity::Error,
            variable,
            line,
            file_path,
            &format!("Borrow conflict on '{}'", variable),
        )
    }

    /// Create security issue
    pub fn security(category: &str, line: usize, file_path: &str) -> Self {
        Self::new(
            IssueCategory::Security,
            IssueSeverity::Critical,
            category,
            line,
            file_path,
            &format!("Security vulnerability: {}", category),
        )
    }

    /// Add context information
    pub fn with_context(mut self, context: Vec<String>) -> Self {
        self.context = context;
        self
    }

    /// Add fix suggestion
    pub fn with_suggestion(mut self, suggestion: &str) -> Self {
        self.suggestion = Some(suggestion.to_string());
        self
    }
}

/// Heap Object (Entity)
///
/// Represents a heap-allocated object.
/// Identity: allocation_site
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeapObject {
    /// Unique allocation site identifier
    pub allocation_site: String,

    /// Object type name
    pub type_name: Option<String>,

    /// Current escape state
    pub escape_state: EscapeState,

    /// Current ownership state
    pub ownership_state: OwnershipState,

    /// Is this object allocated (not freed)?
    pub is_allocated: bool,

    /// Free count (for double-free detection)
    pub free_count: usize,

    /// Variables that alias this object
    pub aliases: HashSet<String>,

    /// Allocation line number
    pub allocation_line: usize,

    /// Allocation file path
    pub allocation_file: String,
}

impl HeapObject {
    /// Create new heap object
    pub fn new(allocation_site: String, allocation_file: String, allocation_line: usize) -> Self {
        Self {
            allocation_site,
            type_name: None,
            escape_state: EscapeState::NoEscape,
            ownership_state: OwnershipState::Owned,
            is_allocated: true,
            free_count: 0,
            aliases: HashSet::new(),
            allocation_line,
            allocation_file,
        }
    }

    /// Set type name
    pub fn with_type(mut self, type_name: &str) -> Self {
        self.type_name = Some(type_name.to_string());
        self
    }

    /// Add an alias
    pub fn add_alias(&mut self, var: &str) {
        self.aliases.insert(var.to_string());
    }

    /// Free this object
    pub fn free(&mut self) {
        self.is_allocated = false;
        self.free_count += 1;
    }

    /// Check if double-free would occur
    pub fn would_double_free(&self) -> bool {
        self.free_count > 0
    }

    /// Check if use-after-free would occur
    pub fn would_use_after_free(&self) -> bool {
        !self.is_allocated
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Domain Services
// ═══════════════════════════════════════════════════════════════════════════

/// Escape state lattice operations
pub struct EscapeLattice;

impl EscapeLattice {
    /// Join two escape states (least upper bound)
    pub fn join(a: EscapeState, b: EscapeState) -> EscapeState {
        a.join(b)
    }

    /// Check if a ≤ b in lattice
    pub fn leq(a: EscapeState, b: EscapeState) -> bool {
        use EscapeState::*;
        match (a, b) {
            (Unknown, _) | (_, GlobalEscape) => true,
            (NoEscape, NoEscape) => true,
            (NoEscape, _) => true,
            (ArgEscape, ArgEscape | ReturnEscape | FieldEscape | ArrayEscape | GlobalEscape) => true,
            (ReturnEscape, ReturnEscape | GlobalEscape) => true,
            (FieldEscape, FieldEscape | GlobalEscape) => true,
            (ArrayEscape, ArrayEscape | GlobalEscape) => true,
            _ => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escape_state_join() {
        assert_eq!(EscapeState::NoEscape.join(EscapeState::ArgEscape), EscapeState::ArgEscape);
        assert_eq!(EscapeState::ArgEscape.join(EscapeState::GlobalEscape), EscapeState::GlobalEscape);
        assert_eq!(EscapeState::Unknown.join(EscapeState::NoEscape), EscapeState::NoEscape);
    }

    #[test]
    fn test_escape_state_stack_allocatable() {
        assert!(EscapeState::NoEscape.is_stack_allocatable());
        assert!(EscapeState::ArgEscape.is_stack_allocatable());
        assert!(!EscapeState::GlobalEscape.is_stack_allocatable());
        assert!(!EscapeState::ReturnEscape.is_stack_allocatable());
    }

    #[test]
    fn test_ownership_state_permissions() {
        assert!(OwnershipState::Owned.can_read());
        assert!(OwnershipState::Owned.can_write());
        assert!(OwnershipState::Owned.can_move());

        assert!(OwnershipState::BorrowedImmut.can_read());
        assert!(!OwnershipState::BorrowedImmut.can_write());
        assert!(!OwnershipState::BorrowedImmut.can_move());

        assert!(!OwnershipState::Moved.is_valid());
        assert!(!OwnershipState::Uninitialized.is_valid());
    }

    #[test]
    fn test_heap_issue_constructors() {
        let issue = HeapIssue::null_dereference("x", 10, "test.rs");
        assert_eq!(issue.category, IssueCategory::NullDereference);
        assert_eq!(issue.severity, IssueSeverity::Error);
        assert_eq!(issue.variable, "x");
        assert_eq!(issue.line, 10);

        let issue = HeapIssue::use_after_free("y", 20, "test.rs");
        assert_eq!(issue.category, IssueCategory::UseAfterFree);
        assert_eq!(issue.severity, IssueSeverity::Critical);
    }

    #[test]
    fn test_heap_object_lifecycle() {
        let mut obj = HeapObject::new("alloc_1".to_string(), "test.rs".to_string(), 5);
        assert!(obj.is_allocated);
        assert_eq!(obj.free_count, 0);
        assert!(!obj.would_double_free());
        assert!(!obj.would_use_after_free());

        obj.free();
        assert!(!obj.is_allocated);
        assert_eq!(obj.free_count, 1);
        assert!(obj.would_double_free());
        assert!(obj.would_use_after_free());
    }

    #[test]
    fn test_escape_lattice() {
        assert!(EscapeLattice::leq(EscapeState::NoEscape, EscapeState::GlobalEscape));
        assert!(EscapeLattice::leq(EscapeState::NoEscape, EscapeState::ArgEscape));
        assert!(!EscapeLattice::leq(EscapeState::GlobalEscape, EscapeState::NoEscape));
    }
}
