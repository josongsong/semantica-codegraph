//! Ownership Tracking - Rust-Style Memory Safety for All Languages
//!
//! Implements ownership-based memory safety analysis inspired by Rust's ownership system.
//! Can be applied to Python, Java, C++, and other languages to detect:
//! - Use-after-move
//! - Double-free (via ownership violation)
//! - Dangling references
//! - Aliasing violations
//!
//! ## Academic References
//! - **Rust RFC 2094**: Non-lexical lifetimes
//! - **Weiss et al. (2019)**: "Oxide: The Essence of Rust"
//! - **Jung et al. (2017)**: "RustBelt: Securing the Foundations of the Rust Programming Language"
//!
//! ## Industry
//! - **Rust Compiler**: Borrow checker (MIR-based)
//! - **Miri**: Rust interpreter for undefined behavior detection
//! - **Polonius**: Next-gen borrow checker
//!
//! ## Core Concepts
//!
//! ### 1. Ownership
//! - Each value has exactly one owner
//! - When owner goes out of scope, value is dropped
//! - Ownership can be transferred (moved)
//!
//! ### 2. Borrowing
//! - Immutable borrows: `&T` - multiple allowed
//! - Mutable borrows: `&mut T` - exclusive
//! - No mutable + immutable at same time
//!
//! ### 3. Lifetimes
//! - References must not outlive their referent
//! - Tracked via lexical/non-lexical scopes
//!
//! ## Example Issues Detected
//!
//! ```text
//! # Use-after-move
//! x = create_resource()
//! y = x  # x moved to y
//! use(x)  # ❌ Use after move!
//!
//! # Aliasing violation
//! ref1 = &mut data
//! ref2 = &data  # ❌ Can't borrow while mutably borrowed!
//!
//! # Dangling reference
//! ref = &local_var
//! return ref  # ❌ Reference outlives local_var!
//! ```

use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

// ═══════════════════════════════════════════════════════════════════════════
// Ownership State Model
// ═══════════════════════════════════════════════════════════════════════════

/// Ownership state of a variable
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OwnershipState {
    /// Variable owns the value (can use, move, or drop)
    Owned,

    /// Value has been moved to another variable
    Moved,

    /// Variable is borrowed immutably (can read, cannot write/move)
    BorrowedImmutable,

    /// Variable is borrowed mutably (exclusive access)
    BorrowedMutable,

    /// Variable is invalid (e.g., after scope ends)
    Invalid,

    /// Ownership state is unknown (conservative)
    Unknown,
}

impl OwnershipState {
    /// Check if the variable can be read
    pub fn can_read(&self) -> bool {
        matches!(
            self,
            Self::Owned | Self::BorrowedImmutable | Self::BorrowedMutable
        )
    }

    /// Check if the variable can be written
    pub fn can_write(&self) -> bool {
        matches!(self, Self::Owned | Self::BorrowedMutable)
    }

    /// Check if the value can be moved
    pub fn can_move(&self) -> bool {
        matches!(self, Self::Owned)
    }

    /// Check if this is an error state
    pub fn is_error(&self) -> bool {
        matches!(self, Self::Moved | Self::Invalid)
    }
}

/// Borrow kind
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BorrowKind {
    /// Shared/immutable borrow: &T
    Shared,
    /// Exclusive/mutable borrow: &mut T
    Mutable,
}

/// Information about an active borrow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BorrowInfo {
    /// The variable being borrowed
    pub borrowed_var: String,

    /// The borrowing variable (reference)
    pub borrower: String,

    /// Kind of borrow
    pub kind: BorrowKind,

    /// Location where borrow started
    pub borrow_location: String,

    /// Scope/lifetime identifier
    pub scope_id: String,

    /// Line number where borrow starts
    pub start_line: u32,

    /// Line number where borrow ends (if known)
    pub end_line: Option<u32>,
}

/// Ownership tracking information for a variable
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OwnershipInfo {
    /// Variable name
    pub var: String,

    /// Current ownership state
    pub state: OwnershipState,

    /// If moved, where was it moved to?
    pub moved_to: Option<String>,

    /// If moved, at what location?
    pub moved_at: Option<String>,

    /// Active borrows of this variable
    pub active_borrows: Vec<BorrowInfo>,

    /// Scope where variable was defined
    pub defining_scope: String,

    /// Location where variable was defined
    pub definition_location: String,
}

impl OwnershipInfo {
    pub fn new(
        var: impl Into<String>,
        scope: impl Into<String>,
        location: impl Into<String>,
    ) -> Self {
        Self {
            var: var.into(),
            state: OwnershipState::Owned,
            moved_to: None,
            moved_at: None,
            active_borrows: Vec::new(),
            defining_scope: scope.into(),
            definition_location: location.into(),
        }
    }

    /// Mark as moved to another variable
    pub fn mark_moved(&mut self, to: impl Into<String>, at: impl Into<String>) {
        self.state = OwnershipState::Moved;
        self.moved_to = Some(to.into());
        self.moved_at = Some(at.into());
    }

    /// Add an immutable borrow
    pub fn add_immutable_borrow(
        &mut self,
        borrower: impl Into<String>,
        location: impl Into<String>,
        scope: impl Into<String>,
        line: u32,
    ) {
        self.active_borrows.push(BorrowInfo {
            borrowed_var: self.var.clone(),
            borrower: borrower.into(),
            kind: BorrowKind::Shared,
            borrow_location: location.into(),
            scope_id: scope.into(),
            start_line: line,
            end_line: None,
        });
    }

    /// Add a mutable borrow
    pub fn add_mutable_borrow(
        &mut self,
        borrower: impl Into<String>,
        location: impl Into<String>,
        scope: impl Into<String>,
        line: u32,
    ) {
        self.active_borrows.push(BorrowInfo {
            borrowed_var: self.var.clone(),
            borrower: borrower.into(),
            kind: BorrowKind::Mutable,
            borrow_location: location.into(),
            scope_id: scope.into(),
            start_line: line,
            end_line: None,
        });
    }

    /// Check if there's an active mutable borrow
    pub fn has_mutable_borrow(&self) -> bool {
        self.active_borrows
            .iter()
            .any(|b| b.kind == BorrowKind::Mutable)
    }

    /// Check if there are any active borrows
    pub fn has_any_borrow(&self) -> bool {
        !self.active_borrows.is_empty()
    }

    /// End borrows in a specific scope
    pub fn end_borrows_in_scope(&mut self, scope: &str) {
        self.active_borrows.retain(|b| b.scope_id != scope);
    }

    /// End all borrows
    pub fn end_all_borrows(&mut self) {
        self.active_borrows.clear();
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Ownership Violations
// ═══════════════════════════════════════════════════════════════════════════

/// Types of ownership violations
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OwnershipViolationKind {
    /// Using a value after it was moved
    UseAfterMove,

    /// Moving a value while it's borrowed
    MoveWhileBorrowed,

    /// Creating mutable borrow while immutable borrows exist
    MutableBorrowWhileImmutable,

    /// Creating any borrow while mutable borrow exists
    BorrowWhileMutableBorrow,

    /// Reference outlives the value it refers to
    DanglingReference,

    /// Double move (moving same value twice)
    DoubleMove,

    /// Writing to immutably borrowed variable
    WriteWhileBorrowed,

    /// Variable used after scope ends
    UseAfterScopeEnd,
}

/// An ownership violation detected during analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OwnershipViolation {
    /// Kind of violation
    pub kind: OwnershipViolationKind,

    /// Variable involved
    pub variable: String,

    /// Location where violation occurs
    pub location: String,

    /// Line number
    pub line: u32,

    /// Detailed message
    pub message: String,

    /// Related location (e.g., where the move happened)
    pub related_location: Option<String>,

    /// Severity (1-10)
    pub severity: u8,
}

impl OwnershipViolation {
    pub fn use_after_move(var: &str, use_location: &str, use_line: u32, moved_at: &str) -> Self {
        Self {
            kind: OwnershipViolationKind::UseAfterMove,
            variable: var.to_string(),
            location: use_location.to_string(),
            line: use_line,
            message: format!(
                "Use of moved value '{}'. Value was moved at {}",
                var, moved_at
            ),
            related_location: Some(moved_at.to_string()),
            severity: 9,
        }
    }

    pub fn move_while_borrowed(
        var: &str,
        move_location: &str,
        move_line: u32,
        borrow_location: &str,
    ) -> Self {
        Self {
            kind: OwnershipViolationKind::MoveWhileBorrowed,
            variable: var.to_string(),
            location: move_location.to_string(),
            line: move_line,
            message: format!(
                "Cannot move '{}' while it is borrowed. Borrow created at {}",
                var, borrow_location
            ),
            related_location: Some(borrow_location.to_string()),
            severity: 9,
        }
    }

    pub fn mutable_borrow_conflict(
        var: &str,
        location: &str,
        line: u32,
        existing_borrow: &str,
    ) -> Self {
        Self {
            kind: OwnershipViolationKind::MutableBorrowWhileImmutable,
            variable: var.to_string(),
            location: location.to_string(),
            line: line,
            message: format!(
                "Cannot borrow '{}' as mutable because it is already borrowed as immutable at {}",
                var, existing_borrow
            ),
            related_location: Some(existing_borrow.to_string()),
            severity: 8,
        }
    }

    pub fn borrow_while_mutable(
        var: &str,
        location: &str,
        line: u32,
        mutable_borrow: &str,
    ) -> Self {
        Self {
            kind: OwnershipViolationKind::BorrowWhileMutableBorrow,
            variable: var.to_string(),
            location: location.to_string(),
            line: line,
            message: format!(
                "Cannot borrow '{}' because it is already mutably borrowed at {}",
                var, mutable_borrow
            ),
            related_location: Some(mutable_borrow.to_string()),
            severity: 8,
        }
    }

    pub fn dangling_reference(
        var: &str,
        ref_location: &str,
        ref_line: u32,
        referent_scope: &str,
    ) -> Self {
        Self {
            kind: OwnershipViolationKind::DanglingReference,
            variable: var.to_string(),
            location: ref_location.to_string(),
            line: ref_line,
            message: format!(
                "Reference '{}' may outlive the value it refers to (defined in scope {})",
                var, referent_scope
            ),
            related_location: Some(referent_scope.to_string()),
            severity: 10,
        }
    }

    pub fn write_while_borrowed(
        var: &str,
        write_location: &str,
        write_line: u32,
        borrow_location: &str,
    ) -> Self {
        Self {
            kind: OwnershipViolationKind::WriteWhileBorrowed,
            variable: var.to_string(),
            location: write_location.to_string(),
            line: write_line,
            message: format!(
                "Cannot write to '{}' while it is borrowed at {}",
                var, borrow_location
            ),
            related_location: Some(borrow_location.to_string()),
            severity: 8,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Ownership Tracker
// ═══════════════════════════════════════════════════════════════════════════

/// Ownership Tracker - Main analysis component
///
/// Tracks ownership state of all variables and detects violations.
///
/// ## Algorithm
///
/// 1. **Initialization**: Mark all variables as Owned when defined
/// 2. **Assignment Analysis**: Detect moves vs copies
/// 3. **Borrow Analysis**: Track & and &mut operations
/// 4. **Scope Tracking**: End borrows when scope ends
/// 5. **Use Analysis**: Check state before each use
///
/// ## Time Complexity
/// O(n × m) where n = statements, m = variables
///
/// ## Space Complexity
/// O(m) for ownership state map
pub struct OwnershipTracker {
    /// Ownership info for each variable
    ownership_map: HashMap<String, OwnershipInfo>,

    /// Current scope stack (for lifetime tracking)
    pub(crate) scope_stack: Vec<String>,

    /// Variables defined in each scope
    scope_vars: HashMap<String, HashSet<String>>,

    /// Detected violations
    pub(crate) violations: Vec<OwnershipViolation>,

    /// Move semantics types (types that move instead of copy)
    move_types: HashSet<String>,

    /// Copy types (types that copy instead of move)
    copy_types: HashSet<String>,

    /// Enable strict mode (report warnings as errors)
    strict_mode: bool,
}

impl Default for OwnershipTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl OwnershipTracker {
    pub fn new() -> Self {
        let mut copy_types = HashSet::new();
        // Primitive types are Copy
        copy_types.insert("int".to_string());
        copy_types.insert("float".to_string());
        copy_types.insert("bool".to_string());
        copy_types.insert("char".to_string());
        copy_types.insert("str".to_string()); // In Python, strings are immutable
        copy_types.insert("i32".to_string());
        copy_types.insert("i64".to_string());
        copy_types.insert("f32".to_string());
        copy_types.insert("f64".to_string());
        copy_types.insert("usize".to_string());

        let mut move_types = HashSet::new();
        // Types that typically move
        move_types.insert("Vec".to_string());
        move_types.insert("String".to_string());
        move_types.insert("Box".to_string());
        move_types.insert("list".to_string());
        move_types.insert("dict".to_string());
        move_types.insert("File".to_string());
        move_types.insert("Connection".to_string());
        move_types.insert("Resource".to_string());

        Self {
            ownership_map: HashMap::new(),
            scope_stack: vec!["global".to_string()],
            scope_vars: HashMap::new(),
            violations: Vec::new(),
            move_types,
            copy_types,
            strict_mode: false,
        }
    }

    /// Enable strict mode
    pub fn with_strict_mode(mut self, strict: bool) -> Self {
        self.strict_mode = strict;
        self
    }

    /// Add a move type
    pub fn add_move_type(&mut self, type_name: impl Into<String>) {
        self.move_types.insert(type_name.into());
    }

    /// Add a copy type
    pub fn add_copy_type(&mut self, type_name: impl Into<String>) {
        self.copy_types.insert(type_name.into());
    }

    /// Get current scope
    fn current_scope(&self) -> &str {
        self.scope_stack
            .last()
            .map(|s| s.as_str())
            .unwrap_or("global")
    }

    /// Enter a new scope
    pub fn enter_scope(&mut self, scope_id: impl Into<String>) {
        let scope = scope_id.into();
        self.scope_stack.push(scope.clone());
        self.scope_vars.entry(scope).or_default();
    }

    /// Exit current scope
    pub fn exit_scope(&mut self) -> Vec<OwnershipViolation> {
        let mut violations = Vec::new();

        if let Some(scope) = self.scope_stack.pop() {
            // End all borrows in this scope
            for info in self.ownership_map.values_mut() {
                info.end_borrows_in_scope(&scope);
            }

            // Check for dangling references (references to scope-local vars)
            if let Some(scope_vars) = self.scope_vars.get(&scope) {
                for var in scope_vars {
                    // Check if any reference to this var exists outside scope
                    for (ref_var, info) in &self.ownership_map {
                        if ref_var != var {
                            for borrow in &info.active_borrows {
                                if &borrow.borrowed_var == var && borrow.scope_id != scope {
                                    violations.push(OwnershipViolation::dangling_reference(
                                        ref_var,
                                        &borrow.borrow_location,
                                        borrow.start_line,
                                        &scope,
                                    ));
                                }
                            }
                        }
                    }

                    // Mark scope-local vars as invalid
                    if let Some(info) = self.ownership_map.get_mut(var) {
                        info.state = OwnershipState::Invalid;
                    }
                }
            }
        }

        self.violations.extend(violations.clone());
        violations
    }

    /// Define a new variable
    pub fn define_variable(&mut self, var: impl Into<String>, location: impl Into<String>) {
        let var = var.into();
        let location = location.into();
        let scope = self.current_scope().to_string();

        let info = OwnershipInfo::new(&var, &scope, &location);
        self.ownership_map.insert(var.clone(), info);

        // Track that this var was defined in current scope
        self.scope_vars.entry(scope).or_default().insert(var);
    }

    /// Check if a type is Copy
    fn is_copy_type(&self, type_name: Option<&str>) -> bool {
        type_name
            .map(|t| self.copy_types.iter().any(|ct| t.contains(ct)))
            .unwrap_or(false)
    }

    /// Check if a type is Move
    fn is_move_type(&self, type_name: Option<&str>) -> bool {
        type_name
            .map(|t| self.move_types.iter().any(|mt| t.contains(mt)))
            .unwrap_or(true) // Default to move semantics
    }

    /// Process an assignment: `target = source`
    ///
    /// Determines whether this is a move or copy based on type.
    pub fn process_assignment(
        &mut self,
        target: &str,
        source: &str,
        source_type: Option<&str>,
        location: &str,
        line: u32,
    ) -> Option<OwnershipViolation> {
        // Check if source is valid
        if let Some(source_info) = self.ownership_map.get(source) {
            match source_info.state {
                OwnershipState::Moved => {
                    let moved_at = source_info.moved_at.clone().unwrap_or_default();
                    let violation =
                        OwnershipViolation::use_after_move(source, location, line, &moved_at);
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                OwnershipState::Invalid => {
                    let violation = OwnershipViolation {
                        kind: OwnershipViolationKind::UseAfterScopeEnd,
                        variable: source.to_string(),
                        location: location.to_string(),
                        line,
                        message: format!("Use of invalid variable '{}'", source),
                        related_location: None,
                        severity: 9,
                    };
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                _ => {}
            }

            // Check if source has active borrows (can't move while borrowed)
            if source_info.has_any_borrow() && self.is_move_type(source_type) {
                let borrow_loc = source_info
                    .active_borrows
                    .first()
                    .map(|b| b.borrow_location.clone())
                    .unwrap_or_default();
                let violation =
                    OwnershipViolation::move_while_borrowed(source, location, line, &borrow_loc);
                self.violations.push(violation.clone());
                return Some(violation);
            }
        }

        // Determine if this is a move or copy
        if self.is_copy_type(source_type) {
            // Copy: source remains valid, target gets copy
            self.define_variable(target, location);
        } else {
            // Move: source becomes invalid, target takes ownership
            if let Some(source_info) = self.ownership_map.get_mut(source) {
                source_info.mark_moved(target, location);
            }
            self.define_variable(target, location);
        }

        None
    }

    /// Process an immutable borrow: `ref = &source`
    pub fn process_immutable_borrow(
        &mut self,
        borrower: &str,
        source: &str,
        location: &str,
        line: u32,
    ) -> Option<OwnershipViolation> {
        // Check source state
        if let Some(source_info) = self.ownership_map.get(source) {
            match source_info.state {
                OwnershipState::Moved => {
                    let moved_at = source_info.moved_at.clone().unwrap_or_default();
                    let violation =
                        OwnershipViolation::use_after_move(source, location, line, &moved_at);
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                OwnershipState::Invalid => {
                    let violation = OwnershipViolation {
                        kind: OwnershipViolationKind::UseAfterScopeEnd,
                        variable: source.to_string(),
                        location: location.to_string(),
                        line,
                        message: format!("Cannot borrow invalid variable '{}'", source),
                        related_location: None,
                        severity: 9,
                    };
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                _ => {}
            }

            // Check for existing mutable borrow
            if source_info.has_mutable_borrow() {
                let mutable_loc = source_info
                    .active_borrows
                    .iter()
                    .find(|b| b.kind == BorrowKind::Mutable)
                    .map(|b| b.borrow_location.clone())
                    .unwrap_or_default();
                let violation =
                    OwnershipViolation::borrow_while_mutable(source, location, line, &mutable_loc);
                self.violations.push(violation.clone());
                return Some(violation);
            }
        }

        // Add the immutable borrow
        let scope = self.current_scope().to_string();
        if let Some(source_info) = self.ownership_map.get_mut(source) {
            source_info.add_immutable_borrow(borrower, location, &scope, line);
        }

        // Define borrower as having borrowed state
        self.define_variable(borrower, location);
        if let Some(borrower_info) = self.ownership_map.get_mut(borrower) {
            borrower_info.state = OwnershipState::BorrowedImmutable;
        }

        None
    }

    /// Process a mutable borrow: `ref = &mut source`
    pub fn process_mutable_borrow(
        &mut self,
        borrower: &str,
        source: &str,
        location: &str,
        line: u32,
    ) -> Option<OwnershipViolation> {
        // Check source state
        if let Some(source_info) = self.ownership_map.get(source) {
            match source_info.state {
                OwnershipState::Moved => {
                    let moved_at = source_info.moved_at.clone().unwrap_or_default();
                    let violation =
                        OwnershipViolation::use_after_move(source, location, line, &moved_at);
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                OwnershipState::Invalid => {
                    let violation = OwnershipViolation {
                        kind: OwnershipViolationKind::UseAfterScopeEnd,
                        variable: source.to_string(),
                        location: location.to_string(),
                        line,
                        message: format!("Cannot borrow invalid variable '{}'", source),
                        related_location: None,
                        severity: 9,
                    };
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                _ => {}
            }

            // Check for any existing borrow
            if source_info.has_any_borrow() {
                let existing_loc = source_info
                    .active_borrows
                    .first()
                    .map(|b| b.borrow_location.clone())
                    .unwrap_or_default();

                let violation = if source_info.has_mutable_borrow() {
                    OwnershipViolation::borrow_while_mutable(source, location, line, &existing_loc)
                } else {
                    OwnershipViolation::mutable_borrow_conflict(
                        source,
                        location,
                        line,
                        &existing_loc,
                    )
                };
                self.violations.push(violation.clone());
                return Some(violation);
            }
        }

        // Add the mutable borrow
        let scope = self.current_scope().to_string();
        if let Some(source_info) = self.ownership_map.get_mut(source) {
            source_info.add_mutable_borrow(borrower, location, &scope, line);
        }

        // Define borrower as having borrowed state
        self.define_variable(borrower, location);
        if let Some(borrower_info) = self.ownership_map.get_mut(borrower) {
            borrower_info.state = OwnershipState::BorrowedMutable;
        }

        None
    }

    /// Process a variable use (read)
    pub fn process_use(
        &mut self,
        var: &str,
        location: &str,
        line: u32,
    ) -> Option<OwnershipViolation> {
        if let Some(info) = self.ownership_map.get(var) {
            match info.state {
                OwnershipState::Moved => {
                    let moved_at = info.moved_at.clone().unwrap_or_default();
                    let violation =
                        OwnershipViolation::use_after_move(var, location, line, &moved_at);
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                OwnershipState::Invalid => {
                    let violation = OwnershipViolation {
                        kind: OwnershipViolationKind::UseAfterScopeEnd,
                        variable: var.to_string(),
                        location: location.to_string(),
                        line,
                        message: format!("Use of invalid variable '{}'", var),
                        related_location: None,
                        severity: 9,
                    };
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                _ => {}
            }
        }
        None
    }

    /// Process a variable write
    pub fn process_write(
        &mut self,
        var: &str,
        location: &str,
        line: u32,
    ) -> Option<OwnershipViolation> {
        if let Some(info) = self.ownership_map.get(var) {
            // Can't write to moved/invalid vars
            match info.state {
                OwnershipState::Moved => {
                    let moved_at = info.moved_at.clone().unwrap_or_default();
                    let violation =
                        OwnershipViolation::use_after_move(var, location, line, &moved_at);
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                OwnershipState::Invalid => {
                    let violation = OwnershipViolation {
                        kind: OwnershipViolationKind::UseAfterScopeEnd,
                        variable: var.to_string(),
                        location: location.to_string(),
                        line,
                        message: format!("Cannot write to invalid variable '{}'", var),
                        related_location: None,
                        severity: 9,
                    };
                    self.violations.push(violation.clone());
                    return Some(violation);
                }
                _ => {}
            }

            // Can't write while borrowed (unless we're the mutable borrower)
            if info.has_any_borrow() {
                let borrow_loc = info
                    .active_borrows
                    .first()
                    .map(|b| b.borrow_location.clone())
                    .unwrap_or_default();
                let violation =
                    OwnershipViolation::write_while_borrowed(var, location, line, &borrow_loc);
                self.violations.push(violation.clone());
                return Some(violation);
            }
        }
        None
    }

    /// Get all violations
    pub fn get_violations(&self) -> &[OwnershipViolation] {
        &self.violations
    }

    /// Get ownership info for a variable
    pub fn get_ownership_info(&self, var: &str) -> Option<&OwnershipInfo> {
        self.ownership_map.get(var)
    }

    /// Clear all state
    pub fn clear(&mut self) {
        self.ownership_map.clear();
        self.scope_stack = vec!["global".to_string()];
        self.scope_vars.clear();
        self.violations.clear();
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Ownership Analyzer (High-level API)
// ═══════════════════════════════════════════════════════════════════════════

/// High-level ownership analyzer that works with IR Nodes
pub struct OwnershipAnalyzer {
    /// Underlying tracker
    tracker: OwnershipTracker,
}

impl Default for OwnershipAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

impl OwnershipAnalyzer {
    pub fn new() -> Self {
        Self {
            tracker: OwnershipTracker::new(),
        }
    }

    /// Analyze nodes for ownership violations
    pub fn analyze(&mut self, nodes: &[Node], edges: &[Edge]) -> Vec<OwnershipViolation> {
        // Build node map for quick lookup
        let node_map: HashMap<&str, &Node> = nodes.iter().map(|n| (n.id.as_str(), n)).collect();

        // Pass 1: Process function/scope entries
        for node in nodes {
            if matches!(node.kind, NodeKind::Function | NodeKind::Method) {
                let scope_id = node.id.clone();
                self.tracker.enter_scope(&scope_id);
            }
        }

        // Pass 2: Process variable definitions and assignments
        for node in nodes {
            let location = format!("{}:{}", node.file_path, node.span.start_line);
            let line = node.span.start_line;

            match node.kind {
                NodeKind::Variable => {
                    if let Some(name) = &node.name {
                        self.tracker.define_variable(name, &location);
                    }
                }

                NodeKind::Expression => {
                    // Detect assignment patterns from FQN
                    self.analyze_expression(node, edges, &node_map);
                }

                _ => {}
            }
        }

        // Pass 3: Check uses from edges
        for edge in edges {
            match edge.kind {
                EdgeKind::Reads => {
                    // source reads target
                    if let Some(source_node) = node_map.get(edge.source_id.as_str()) {
                        let location =
                            format!("{}:{}", source_node.file_path, source_node.span.start_line);
                        self.tracker.process_use(
                            &edge.target_id,
                            &location,
                            source_node.span.start_line,
                        );
                    }
                }

                EdgeKind::Writes => {
                    // source writes to target
                    if let Some(source_node) = node_map.get(edge.source_id.as_str()) {
                        let location =
                            format!("{}:{}", source_node.file_path, source_node.span.start_line);
                        self.tracker.process_write(
                            &edge.target_id,
                            &location,
                            source_node.span.start_line,
                        );
                    }
                }

                _ => {}
            }
        }

        // Exit all scopes
        while self.tracker.scope_stack.len() > 1 {
            self.tracker.exit_scope();
        }

        self.tracker.violations.clone()
    }

    /// Analyze an expression node for ownership patterns
    fn analyze_expression(
        &mut self,
        node: &Node,
        _edges: &[Edge],
        _node_map: &HashMap<&str, &Node>,
    ) {
        let location = format!("{}:{}", node.file_path, node.span.start_line);
        let line = node.span.start_line;

        // Detect assignment: target = source
        // FQN pattern: "target::=::source" or contains "assignment"
        if node.fqn.contains("::=::") || node.fqn.contains("assignment") {
            let parts: Vec<&str> = node.fqn.split("::").collect();
            if parts.len() >= 3 {
                let target = parts[0];
                let source = parts[2];
                let source_type = node.type_annotation.as_deref();

                self.tracker
                    .process_assignment(target, source, source_type, &location, line);
            }
        }

        // Detect borrow: ref = &source or ref = &mut source
        if node.fqn.contains("&mut") {
            // Mutable borrow
            if let Some((borrower, source)) = self.parse_borrow_pattern(&node.fqn) {
                self.tracker
                    .process_mutable_borrow(&borrower, &source, &location, line);
            }
        } else if node.fqn.contains('&') && !node.fqn.contains("&&") {
            // Immutable borrow
            if let Some((borrower, source)) = self.parse_borrow_pattern(&node.fqn) {
                self.tracker
                    .process_immutable_borrow(&borrower, &source, &location, line);
            }
        }

        // Detect move patterns
        // Python: x = y (where y is not primitive)
        // Rust: let x = y; (move)
        if node.fqn.contains("move") || node.fqn.contains("::=::") {
            // Already handled in assignment
        }
    }

    /// Parse a borrow pattern from FQN
    fn parse_borrow_pattern(&self, fqn: &str) -> Option<(String, String)> {
        // Pattern: "borrower::=::&source" or "borrower::=::&mut::source"
        let parts: Vec<&str> = fqn.split("::").collect();

        if parts.len() >= 3 {
            let borrower = parts[0].to_string();
            let source = parts.last()?.trim_start_matches('&').to_string();
            return Some((borrower, source));
        }

        None
    }

    /// Get all violations
    pub fn get_violations(&self) -> &[OwnershipViolation] {
        self.tracker.get_violations()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    // ═══════════════════════════════════════════════════════════════════════════
    // BASE CASES - Basic functionality
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_ownership_state_can_read() {
        assert!(OwnershipState::Owned.can_read());
        assert!(OwnershipState::BorrowedImmutable.can_read());
        assert!(OwnershipState::BorrowedMutable.can_read());
        assert!(!OwnershipState::Moved.can_read());
        assert!(!OwnershipState::Invalid.can_read());
        assert!(!OwnershipState::Unknown.can_read());
    }

    #[test]
    fn test_ownership_state_can_write() {
        assert!(OwnershipState::Owned.can_write());
        assert!(!OwnershipState::BorrowedImmutable.can_write());
        assert!(OwnershipState::BorrowedMutable.can_write());
        assert!(!OwnershipState::Moved.can_write());
        assert!(!OwnershipState::Invalid.can_write());
    }

    #[test]
    fn test_ownership_state_can_move() {
        assert!(OwnershipState::Owned.can_move());
        assert!(!OwnershipState::BorrowedImmutable.can_move());
        assert!(!OwnershipState::BorrowedMutable.can_move());
        assert!(!OwnershipState::Moved.can_move());
        assert!(!OwnershipState::Invalid.can_move());
    }

    #[test]
    fn test_ownership_state_is_error() {
        assert!(!OwnershipState::Owned.is_error());
        assert!(!OwnershipState::BorrowedImmutable.is_error());
        assert!(!OwnershipState::BorrowedMutable.is_error());
        assert!(OwnershipState::Moved.is_error());
        assert!(OwnershipState::Invalid.is_error());
        assert!(!OwnershipState::Unknown.is_error());
    }

    #[test]
    fn test_define_variable() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.rs:1");

        let info = tracker.get_ownership_info("x");
        assert!(info.is_some());
        let info = info.unwrap();
        assert_eq!(info.var, "x");
        assert_eq!(info.state, OwnershipState::Owned);
        assert_eq!(info.defining_scope, "global");
    }

    #[test]
    fn test_use_after_move() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.py:1");
        tracker.process_assignment("y", "x", Some("Vec"), "test.py:2", 2);

        let violation = tracker.process_use("x", "test.py:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::UseAfterMove
        );
    }

    #[test]
    fn test_copy_semantics() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.py:1");
        tracker.process_assignment("y", "x", Some("int"), "test.py:2", 2);

        // x should still be valid (int is Copy)
        let violation = tracker.process_use("x", "test.py:3", 3);
        assert!(violation.is_none());
    }

    #[test]
    fn test_mutable_borrow_conflict() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");
        tracker.process_immutable_borrow("ref1", "data", "test.rs:2", 2);

        let violation = tracker.process_mutable_borrow("ref2", "data", "test.rs:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::MutableBorrowWhileImmutable
        );
    }

    #[test]
    fn test_borrow_while_mutable() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");
        tracker.process_mutable_borrow("ref1", "data", "test.rs:2", 2);

        let violation = tracker.process_immutable_borrow("ref2", "data", "test.rs:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::BorrowWhileMutableBorrow
        );
    }

    #[test]
    fn test_move_while_borrowed() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");
        tracker.process_immutable_borrow("ref1", "data", "test.rs:2", 2);

        let violation =
            tracker.process_assignment("new_owner", "data", Some("Vec"), "test.rs:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::MoveWhileBorrowed
        );
    }

    #[test]
    fn test_write_while_borrowed() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");
        tracker.process_immutable_borrow("ref1", "data", "test.rs:2", 2);

        let violation = tracker.process_write("data", "test.rs:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::WriteWhileBorrowed
        );
    }

    #[test]
    fn test_scope_tracking() {
        let mut tracker = OwnershipTracker::new();
        tracker.enter_scope("func1");
        tracker.define_variable("local", "test.rs:2");
        tracker.exit_scope();

        let info = tracker.get_ownership_info("local");
        assert!(info.is_some());
        assert_eq!(info.unwrap().state, OwnershipState::Invalid);
    }

    #[test]
    fn test_multiple_immutable_borrows() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");

        // Multiple immutable borrows are OK
        let v1 = tracker.process_immutable_borrow("ref1", "data", "test.rs:2", 2);
        let v2 = tracker.process_immutable_borrow("ref2", "data", "test.rs:3", 3);
        let v3 = tracker.process_immutable_borrow("ref3", "data", "test.rs:4", 4);

        assert!(v1.is_none());
        assert!(v2.is_none());
        assert!(v3.is_none());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // EDGE CASES - Boundary conditions
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_double_move() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.rs:1");

        // First move - OK
        let v1 = tracker.process_assignment("y", "x", Some("String"), "test.rs:2", 2);
        assert!(v1.is_none());

        // Second move - should fail (use after move)
        let v2 = tracker.process_assignment("z", "x", Some("String"), "test.rs:3", 3);
        assert!(v2.is_some());
        assert_eq!(v2.unwrap().kind, OwnershipViolationKind::UseAfterMove);
    }

    #[test]
    fn test_nested_scopes() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("global_var", "test.rs:1");

        tracker.enter_scope("outer");
        tracker.define_variable("outer_var", "test.rs:3");

        tracker.enter_scope("inner");
        tracker.define_variable("inner_var", "test.rs:5");

        // Exit inner scope
        tracker.exit_scope();
        assert_eq!(
            tracker.get_ownership_info("inner_var").unwrap().state,
            OwnershipState::Invalid
        );
        assert_eq!(
            tracker.get_ownership_info("outer_var").unwrap().state,
            OwnershipState::Owned
        );

        // Exit outer scope
        tracker.exit_scope();
        assert_eq!(
            tracker.get_ownership_info("outer_var").unwrap().state,
            OwnershipState::Invalid
        );
        assert_eq!(
            tracker.get_ownership_info("global_var").unwrap().state,
            OwnershipState::Owned
        );
    }

    #[test]
    fn test_borrow_ends_then_reborrow() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");

        // Enter scope, borrow
        tracker.enter_scope("scope1");
        let v1 = tracker.process_immutable_borrow("ref1", "data", "test.rs:2", 2);
        assert!(v1.is_none());

        // Exit scope - borrow ends
        tracker.exit_scope();

        // Now mutable borrow should be OK
        let v2 = tracker.process_mutable_borrow("ref2", "data", "test.rs:5", 5);
        assert!(v2.is_none());
    }

    #[test]
    fn test_undefined_variable_use() {
        let mut tracker = OwnershipTracker::new();

        // Use undefined variable - no violation (undefined vars aren't tracked)
        let violation = tracker.process_use("undefined_var", "test.rs:1", 1);
        assert!(violation.is_none());
    }

    #[test]
    fn test_self_assignment() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.rs:1");

        // x = x (self assignment) - moves to self
        let violation = tracker.process_assignment("x", "x", Some("Vec"), "test.rs:2", 2);
        // This is technically a move, then redefine
        // The semantics here: x moves to x, x becomes moved, then x is redefined
        // So no violation for the assignment itself
        // But we should verify the state is correct
        let info = tracker.get_ownership_info("x").unwrap();
        assert_eq!(info.state, OwnershipState::Owned); // Redefined
    }

    #[test]
    fn test_chain_of_moves() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("a", "test.rs:1");

        // a -> b -> c -> d
        tracker.process_assignment("b", "a", Some("Vec"), "test.rs:2", 2);
        tracker.process_assignment("c", "b", Some("Vec"), "test.rs:3", 3);
        tracker.process_assignment("d", "c", Some("Vec"), "test.rs:4", 4);

        // a, b, c should be moved
        assert_eq!(
            tracker.get_ownership_info("a").unwrap().state,
            OwnershipState::Moved
        );
        assert_eq!(
            tracker.get_ownership_info("b").unwrap().state,
            OwnershipState::Moved
        );
        assert_eq!(
            tracker.get_ownership_info("c").unwrap().state,
            OwnershipState::Moved
        );
        assert_eq!(
            tracker.get_ownership_info("d").unwrap().state,
            OwnershipState::Owned
        );
    }

    #[test]
    fn test_use_after_scope_end() {
        let mut tracker = OwnershipTracker::new();

        tracker.enter_scope("func");
        tracker.define_variable("local", "test.rs:2");
        tracker.exit_scope();

        // Try to use invalid variable
        let violation = tracker.process_use("local", "test.rs:5", 5);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::UseAfterScopeEnd
        );
    }

    #[test]
    fn test_write_to_invalid_variable() {
        let mut tracker = OwnershipTracker::new();

        tracker.enter_scope("func");
        tracker.define_variable("local", "test.rs:2");
        tracker.exit_scope();

        // Try to write to invalid variable
        let violation = tracker.process_write("local", "test.rs:5", 5);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::UseAfterScopeEnd
        );
    }

    #[test]
    fn test_borrow_moved_variable() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");
        tracker.process_assignment("new_owner", "data", Some("Vec"), "test.rs:2", 2);

        // Try to borrow moved variable
        let violation = tracker.process_immutable_borrow("ref", "data", "test.rs:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::UseAfterMove
        );
    }

    #[test]
    fn test_mutable_borrow_moved_variable() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");
        tracker.process_assignment("new_owner", "data", Some("Vec"), "test.rs:2", 2);

        // Try to mutable borrow moved variable
        let violation = tracker.process_mutable_borrow("ref", "data", "test.rs:3", 3);
        assert!(violation.is_some());
        assert_eq!(
            violation.unwrap().kind,
            OwnershipViolationKind::UseAfterMove
        );
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // EXTREME CASES - Stress tests
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_many_immutable_borrows() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("data", "test.rs:1");

        // 100 immutable borrows should all succeed
        for i in 0..100 {
            let ref_name = format!("ref{}", i);
            let loc = format!("test.rs:{}", i + 2);
            let violation =
                tracker.process_immutable_borrow(&ref_name, "data", &loc, (i + 2) as u32);
            assert!(violation.is_none(), "Failed at borrow {}", i);
        }

        // Mutable borrow should still fail
        let violation = tracker.process_mutable_borrow("mut_ref", "data", "test.rs:200", 200);
        assert!(violation.is_some());
    }

    #[test]
    fn test_deep_scope_nesting() {
        let mut tracker = OwnershipTracker::new();

        // 50 levels of nesting
        for i in 0..50 {
            tracker.enter_scope(format!("scope_{}", i));
            tracker.define_variable(format!("var_{}", i), format!("test.rs:{}", i + 1));
        }

        // All variables should be valid
        for i in 0..50 {
            let var_name = format!("var_{}", i);
            assert_eq!(
                tracker.get_ownership_info(&var_name).unwrap().state,
                OwnershipState::Owned,
                "var_{} should be Owned",
                i
            );
        }

        // Exit all scopes
        for i in (0..50).rev() {
            tracker.exit_scope();
            let var_name = format!("var_{}", i);
            assert_eq!(
                tracker.get_ownership_info(&var_name).unwrap().state,
                OwnershipState::Invalid,
                "var_{} should be Invalid after scope exit",
                i
            );
        }
    }

    #[test]
    fn test_rapid_move_chain() {
        let mut tracker = OwnershipTracker::new();

        // Create a long chain of moves: v0 -> v1 -> v2 -> ... -> v99
        tracker.define_variable("v0", "test.rs:1");
        for i in 1..100 {
            let from = format!("v{}", i - 1);
            let to = format!("v{}", i);
            let loc = format!("test.rs:{}", i + 1);
            tracker.process_assignment(&to, &from, Some("String"), &loc, (i + 1) as u32);
        }

        // Only v99 should be Owned
        for i in 0..99 {
            let var_name = format!("v{}", i);
            assert_eq!(
                tracker.get_ownership_info(&var_name).unwrap().state,
                OwnershipState::Moved,
                "v{} should be Moved",
                i
            );
        }
        assert_eq!(
            tracker.get_ownership_info("v99").unwrap().state,
            OwnershipState::Owned
        );
    }

    #[test]
    fn test_custom_type_registration() {
        let mut tracker = OwnershipTracker::new();

        // Add custom copy type
        tracker.add_copy_type("MyPrimitive");
        tracker.define_variable("x", "test.rs:1");

        // Assignment with custom copy type should not move
        tracker.process_assignment("y", "x", Some("MyPrimitive"), "test.rs:2", 2);
        assert_eq!(
            tracker.get_ownership_info("x").unwrap().state,
            OwnershipState::Owned
        );
    }

    #[test]
    fn test_clear_resets_state() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.rs:1");
        tracker.enter_scope("scope1");
        tracker.process_assignment("y", "x", Some("Vec"), "test.rs:2", 2);

        // Clear all state
        tracker.clear();

        // Everything should be reset
        assert!(tracker.get_ownership_info("x").is_none());
        assert!(tracker.get_ownership_info("y").is_none());
        assert_eq!(tracker.scope_stack.len(), 1); // Only global
        assert!(tracker.violations.is_empty());
    }

    #[test]
    fn test_violations_accumulate() {
        let mut tracker = OwnershipTracker::new();
        tracker.define_variable("x", "test.rs:1");
        tracker.process_assignment("y", "x", Some("Vec"), "test.rs:2", 2);

        // Generate multiple violations
        tracker.process_use("x", "test.rs:3", 3);
        tracker.process_use("x", "test.rs:4", 4);
        tracker.process_use("x", "test.rs:5", 5);

        assert_eq!(tracker.get_violations().len(), 3);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // OWNERSHIP INFO TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_ownership_info_has_mutable_borrow() {
        let mut info = OwnershipInfo::new("x", "global", "test.rs:1");
        assert!(!info.has_mutable_borrow());

        info.add_immutable_borrow("ref1", "test.rs:2", "global", 2);
        assert!(!info.has_mutable_borrow());

        info.add_mutable_borrow("ref2", "test.rs:3", "global", 3);
        assert!(info.has_mutable_borrow());
    }

    #[test]
    fn test_ownership_info_has_any_borrow() {
        let mut info = OwnershipInfo::new("x", "global", "test.rs:1");
        assert!(!info.has_any_borrow());

        info.add_immutable_borrow("ref1", "test.rs:2", "global", 2);
        assert!(info.has_any_borrow());
    }

    #[test]
    fn test_ownership_info_end_borrows_in_scope() {
        let mut info = OwnershipInfo::new("x", "global", "test.rs:1");
        info.add_immutable_borrow("ref1", "test.rs:2", "scope1", 2);
        info.add_immutable_borrow("ref2", "test.rs:3", "scope2", 3);
        info.add_immutable_borrow("ref3", "test.rs:4", "scope1", 4);

        info.end_borrows_in_scope("scope1");
        assert_eq!(info.active_borrows.len(), 1);
        assert_eq!(info.active_borrows[0].borrower, "ref2");
    }

    #[test]
    fn test_ownership_info_end_all_borrows() {
        let mut info = OwnershipInfo::new("x", "global", "test.rs:1");
        info.add_immutable_borrow("ref1", "test.rs:2", "scope1", 2);
        info.add_mutable_borrow("ref2", "test.rs:3", "scope2", 3);

        info.end_all_borrows();
        assert!(info.active_borrows.is_empty());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // VIOLATION MESSAGE TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_violation_messages() {
        let v1 = OwnershipViolation::use_after_move("x", "test.rs:10", 10, "test.rs:5");
        assert!(v1.message.contains("moved value"));
        assert!(v1.message.contains("x"));
        assert_eq!(v1.severity, 9);

        let v2 = OwnershipViolation::move_while_borrowed("y", "test.rs:20", 20, "test.rs:15");
        assert!(v2.message.contains("borrowed"));
        assert_eq!(v2.severity, 9);

        let v3 = OwnershipViolation::dangling_reference("ref", "test.rs:30", 30, "inner_scope");
        assert!(v3.message.contains("outlive"));
        assert_eq!(v3.severity, 10); // Highest severity
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STRICT MODE TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    #[test]
    fn test_strict_mode_enabled() {
        let tracker = OwnershipTracker::new().with_strict_mode(true);
        assert!(tracker.strict_mode);
    }

    #[test]
    fn test_strict_mode_disabled_by_default() {
        let tracker = OwnershipTracker::new();
        assert!(!tracker.strict_mode);
    }
}
