//! Separation Logic - SOTA Heap Verification
//!
//! Academic References:
//! - Reynolds, J. C. (2002). "Separation Logic: A Logic for Shared Mutable Data Structures"
//! - O'Hearn, P. W. (2004). "Resources, Concurrency, and Local Reasoning"
//! - Calcagno, C. et al. (2011). "Infer: An Automatic Program Verifier for Memory Safety"
//!
//! Industry:
//! - Meta Infer: Production heap analyzer for Facebook/Instagram
//! - Microsoft SLAM: Device driver verification
//!
//! ## Core Concepts
//!
//! ### Separation Logic Heap
//! ```text
//! Heap ::= emp                    // Empty heap
//!        | x ↦ {f₁: v₁, ...}     // Points-to assertion
//!        | H₁ * H₂                // Separating conjunction (disjoint)
//!        | H₁ ∨ H₂                // Disjunction (branches)
//! ```
//!
//! ### Example
//! ```text
//! p ↦ {name: "Alice", age: 30} * q ↦ {balance: 100}
//! Pure: [p ≠ null, q ≠ null, p ≠ q]
//! ```
//!
//! ### Separating Conjunction (★)
//! - `H₁ * H₂` means:
//!   - H₁ and H₂ are **disjoint** (no overlapping memory)
//!   - Together they describe the full heap
//! - Key invariant: **No aliasing within ★**
//!
//! ## Operations
//!
//! ### 1. Allocation
//! ```text
//! {emp} x = new Object() {x ↦ {}}
//! ```
//!
//! ### 2. Deallocation
//! ```text
//! {x ↦ v} free(x) {emp}
//! ```
//!
//! ### 3. Frame Rule
//! ```text
//! {P} C {Q}
//! ─────────────────
//! {P * F} C {Q * F}
//! ```
//! (Frame F is unchanged by command C)

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Abstract heap location
///
/// Represents a memory location that can hold values.
///
/// Examples:
/// - Variable: `x`, `y`, `p`
/// - Field access: `obj.field`
/// - Array element: `arr[i]`
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AbstractLocation {
    /// Variable (local or global)
    Variable(String),

    /// Field access: object.field
    Field { object: String, field: String },

    /// Array element: array[index]
    ArrayElement { array: String, index: i64 },

    /// Heap allocation (fresh location)
    Allocation { id: usize },
}

impl AbstractLocation {
    pub fn variable(name: impl Into<String>) -> Self {
        Self::Variable(name.into())
    }

    pub fn field(object: impl Into<String>, field: impl Into<String>) -> Self {
        Self::Field {
            object: object.into(),
            field: field.into(),
        }
    }

    pub fn array_element(array: impl Into<String>, index: i64) -> Self {
        Self::ArrayElement {
            array: array.into(),
            index,
        }
    }

    pub fn allocation(id: usize) -> Self {
        Self::Allocation { id }
    }

    /// Get base variable name
    pub fn base_var(&self) -> Option<&str> {
        match self {
            Self::Variable(v) => Some(v),
            Self::Field { object, .. } => Some(object),
            Self::ArrayElement { array, .. } => Some(array),
            Self::Allocation { .. } => None,
        }
    }
}

/// Heap cell - represents allocated memory
///
/// Separation Logic: x ↦ {f₁: v₁, f₂: v₂, ...}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeapCell {
    /// Fields: field_name → value
    pub fields: HashMap<String, String>,

    /// Allocation status
    pub is_allocated: bool,

    /// Null status
    pub may_be_null: bool,

    /// Free count (for double-free detection)
    pub free_count: usize,
}

impl HeapCell {
    pub fn new() -> Self {
        Self {
            fields: HashMap::new(),
            is_allocated: true,
            may_be_null: false,
            free_count: 0,
        }
    }

    pub fn null() -> Self {
        Self {
            fields: HashMap::new(),
            is_allocated: false,
            may_be_null: true,
            free_count: 0,
        }
    }

    pub fn with_field(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.fields.insert(name.into(), value.into());
        self
    }

    pub fn mark_freed(&mut self) {
        self.is_allocated = false;
        self.free_count += 1;
    }

    pub fn is_freed(&self) -> bool {
        !self.is_allocated && self.free_count > 0
    }

    pub fn is_double_freed(&self) -> bool {
        self.free_count > 1
    }
}

impl Default for HeapCell {
    fn default() -> Self {
        Self::new()
    }
}

/// Symbolic Heap - Separation Logic state
///
/// Heap ::= Spatial * Pure
/// - Spatial: x ↦ cell (points-to assertions)
/// - Pure: path conditions (x ≠ null, etc.)
///
/// Invariants:
/// - **Separation**: No two cells overlap (enforced by HashMap)
/// - **Consistency**: Pure constraints are satisfiable
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolicHeap {
    /// Spatial part: variable → heap cell
    ///
    /// Represents: x₁ ↦ cell₁ * x₂ ↦ cell₂ * ...
    pub cells: HashMap<String, HeapCell>,

    /// Pure constraints (path conditions)
    ///
    /// Example: ["x != null", "x != y", "x.field > 0"]
    pub pure_constraints: Vec<String>,

    /// Error state (null deref, UAF, etc.)
    pub is_error: bool,

    /// Error message
    pub error_message: Option<String>,

    /// Next allocation ID (for fresh locations)
    next_alloc_id: usize,
}

impl SymbolicHeap {
    /// Create empty heap: emp
    pub fn new() -> Self {
        Self {
            cells: HashMap::new(),
            pure_constraints: Vec::new(),
            is_error: false,
            error_message: None,
            next_alloc_id: 0,
        }
    }

    /// Allocate new location
    ///
    /// ```text
    /// {emp} x = new T() {x ↦ {}}
    /// ```
    pub fn allocate(&mut self, var: impl Into<String>) -> AbstractLocation {
        let var = var.into();
        let cell = HeapCell::new();
        self.cells.insert(var.clone(), cell);

        // Add non-null constraint
        self.add_pure_constraint(format!("{} != null", var));

        AbstractLocation::variable(var)
    }

    /// Deallocate location
    ///
    /// ```text
    /// {x ↦ v} free(x) {emp}
    /// ```
    ///
    /// Returns true if successful, false if double-free
    pub fn deallocate(&mut self, var: &str) -> Result<(), &'static str> {
        let cell = self
            .cells
            .get_mut(var)
            .ok_or("Use-after-free: variable not allocated")?;

        if !cell.is_allocated {
            if cell.free_count > 0 {
                return Err("Double-free detected");
            } else {
                return Err("Use-after-free: already freed");
            }
        }

        cell.mark_freed();
        Ok(())
    }

    /// Add pure constraint
    pub fn add_pure_constraint(&mut self, constraint: impl Into<String>) {
        let constraint = constraint.into();
        if !self.pure_constraints.contains(&constraint) {
            self.pure_constraints.push(constraint);
        }
    }

    /// Check if variable is allocated
    pub fn is_allocated(&self, var: &str) -> bool {
        self.cells
            .get(var)
            .map(|cell| cell.is_allocated)
            .unwrap_or(false)
    }

    /// Check if variable may be null
    pub fn may_be_null(&self, var: &str) -> bool {
        self.cells
            .get(var)
            .map(|cell| cell.may_be_null)
            .unwrap_or(true) // Conservative: unknown = may be null
    }

    /// Mark variable as possibly null
    pub fn mark_may_be_null(&mut self, var: &str) {
        if let Some(cell) = self.cells.get_mut(var) {
            cell.may_be_null = true;
        }
    }

    /// Mark variable as definitely not null
    pub fn mark_not_null(&mut self, var: &str) {
        if let Some(cell) = self.cells.get_mut(var) {
            cell.may_be_null = false;
        }
        self.add_pure_constraint(format!("{} != null", var));
    }

    /// Set error state
    pub fn set_error(&mut self, message: impl Into<String>) {
        self.is_error = true;
        self.error_message = Some(message.into());
    }

    /// Merge two heaps (for join points)
    ///
    /// CRITICAL: Over-approximation for soundness
    /// - Union of spatial parts
    /// - Intersection of pure constraints (only keep common)
    /// - Conservative null analysis (may_be_null = true if either is)
    pub fn merge(&self, other: &Self) -> Self {
        // If either is error, result is error
        if self.is_error || other.is_error {
            let mut merged = Self::new();
            merged.is_error = true;
            merged.error_message = self
                .error_message
                .clone()
                .or_else(|| other.error_message.clone());
            return merged;
        }

        let mut merged = Self::new();
        merged.next_alloc_id = self.next_alloc_id.max(other.next_alloc_id);

        // Merge spatial parts (union)
        for (var, cell) in &self.cells {
            merged.cells.insert(var.clone(), cell.clone());
        }

        for (var, cell) in &other.cells {
            if let Some(existing) = merged.cells.get_mut(var) {
                // Conservative merge: if either may be null, result may be null
                existing.may_be_null = existing.may_be_null || cell.may_be_null;

                // Free count: take max (conservative)
                existing.free_count = existing.free_count.max(cell.free_count);

                // Allocated: both must be allocated
                existing.is_allocated = existing.is_allocated && cell.is_allocated;
            } else {
                merged.cells.insert(var.clone(), cell.clone());
            }
        }

        // Merge pure constraints (intersection - only keep common)
        let common_constraints: Vec<String> = self
            .pure_constraints
            .iter()
            .filter(|c| other.pure_constraints.contains(c))
            .cloned()
            .collect();

        merged.pure_constraints = common_constraints;
        merged
    }

    /// Deep copy for branching
    pub fn copy(&self) -> Self {
        Self {
            cells: self.cells.clone(),
            pure_constraints: self.pure_constraints.clone(),
            is_error: self.is_error,
            error_message: self.error_message.clone(),
            next_alloc_id: self.next_alloc_id,
        }
    }
}

impl Default for SymbolicHeap {
    fn default() -> Self {
        Self::new()
    }
}

/// Memory safety issue
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemorySafetyIssue {
    /// Issue type
    pub kind: MemorySafetyIssueKind,

    /// Variable involved
    pub variable: String,

    /// Location (file, line)
    pub location: String,

    /// Error message
    pub message: String,

    /// Severity (1-10)
    pub severity: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MemorySafetyIssueKind {
    NullDereference,
    UseAfterFree,
    DoubleFree,
    MemoryLeak,
    BufferOverflow,
    /// Spatial memory safety violation - accessing memory outside allocated bounds
    /// This includes:
    /// - Out-of-bounds pointer arithmetic
    /// - Object size mismatch (cast to larger type)
    /// - Sub-object bounds violation
    SpatialViolation,
}

impl MemorySafetyIssue {
    pub fn null_dereference(variable: impl Into<String>, location: impl Into<String>) -> Self {
        let variable = variable.into();
        Self {
            kind: MemorySafetyIssueKind::NullDereference,
            message: format!("Potential null dereference of '{}'", variable),
            variable,
            location: location.into(),
            severity: 8,
        }
    }

    pub fn use_after_free(variable: impl Into<String>, location: impl Into<String>) -> Self {
        let variable = variable.into();
        Self {
            kind: MemorySafetyIssueKind::UseAfterFree,
            message: format!("Use-after-free detected on '{}'", variable),
            variable,
            location: location.into(),
            severity: 10,
        }
    }

    pub fn double_free(variable: impl Into<String>, location: impl Into<String>) -> Self {
        let variable = variable.into();
        Self {
            kind: MemorySafetyIssueKind::DoubleFree,
            message: format!("Double-free detected on '{}'", variable),
            variable,
            location: location.into(),
            severity: 10,
        }
    }

    /// Create buffer overflow issue
    ///
    /// # Arguments
    /// * `array` - Array variable name
    /// * `index` - Index value that caused overflow
    /// * `size` - Array size
    /// * `location` - Source location (file:line)
    pub fn buffer_overflow(
        array: impl Into<String>,
        index: i64,
        size: usize,
        location: impl Into<String>,
    ) -> Self {
        let array = array.into();
        Self {
            kind: MemorySafetyIssueKind::BufferOverflow,
            message: format!(
                "Buffer overflow: array '{}' accessed at index {} (size: {})",
                array, index, size
            ),
            variable: array,
            location: location.into(),
            severity: 10, // Critical - exploitable
        }
    }

    /// Create buffer overflow issue with symbolic index
    pub fn buffer_overflow_symbolic(
        array: impl Into<String>,
        index_var: impl Into<String>,
        location: impl Into<String>,
    ) -> Self {
        let array = array.into();
        let index_var = index_var.into();
        Self {
            kind: MemorySafetyIssueKind::BufferOverflow,
            message: format!(
                "Potential buffer overflow: array '{}' accessed with unchecked index '{}'",
                array, index_var
            ),
            variable: array,
            location: location.into(),
            severity: 9, // High - potential exploit
        }
    }

    /// Create spatial memory violation - out-of-bounds pointer arithmetic
    ///
    /// # Arguments
    /// * `pointer` - Pointer variable name
    /// * `offset` - Offset that caused violation
    /// * `object_size` - Size of the allocated object
    /// * `location` - Source location (file:line)
    pub fn spatial_out_of_bounds(
        pointer: impl Into<String>,
        offset: i64,
        object_size: usize,
        location: impl Into<String>,
    ) -> Self {
        let pointer = pointer.into();
        Self {
            kind: MemorySafetyIssueKind::SpatialViolation,
            message: format!(
                "Spatial violation: pointer '{}' + {} exceeds object bounds (size: {})",
                pointer, offset, object_size
            ),
            variable: pointer,
            location: location.into(),
            severity: 10, // Critical - exploitable
        }
    }

    /// Create spatial memory violation - sub-object bounds exceeded
    ///
    /// # Arguments
    /// * `base_object` - Base object name
    /// * `sub_object` - Sub-object/field being accessed
    /// * `access_size` - Size of access attempted
    /// * `field_size` - Actual size of the field
    /// * `location` - Source location (file:line)
    pub fn spatial_sub_object_violation(
        base_object: impl Into<String>,
        sub_object: impl Into<String>,
        access_size: usize,
        field_size: usize,
        location: impl Into<String>,
    ) -> Self {
        let base_object = base_object.into();
        let sub_object = sub_object.into();
        Self {
            kind: MemorySafetyIssueKind::SpatialViolation,
            message: format!(
                "Spatial violation: access to '{}.{}' of size {} exceeds field size {}",
                base_object, sub_object, access_size, field_size
            ),
            variable: base_object,
            location: location.into(),
            severity: 9, // High - memory corruption
        }
    }

    /// Create spatial memory violation - type size mismatch
    ///
    /// # Arguments
    /// * `variable` - Variable name
    /// * `cast_to_size` - Size of the casted type
    /// * `actual_size` - Actual allocated size
    /// * `location` - Source location (file:line)
    pub fn spatial_type_mismatch(
        variable: impl Into<String>,
        cast_to_size: usize,
        actual_size: usize,
        location: impl Into<String>,
    ) -> Self {
        let variable = variable.into();
        Self {
            kind: MemorySafetyIssueKind::SpatialViolation,
            message: format!(
                "Spatial violation: '{}' cast to type of size {} but allocated size is {}",
                variable, cast_to_size, actual_size
            ),
            variable,
            location: location.into(),
            severity: 8, // High - potential memory corruption
        }
    }

    /// Create spatial memory violation - negative pointer arithmetic
    pub fn spatial_negative_offset(
        pointer: impl Into<String>,
        offset: i64,
        location: impl Into<String>,
    ) -> Self {
        let pointer = pointer.into();
        Self {
            kind: MemorySafetyIssueKind::SpatialViolation,
            message: format!(
                "Spatial violation: pointer '{}' with negative offset {} goes before allocation start",
                pointer, offset
            ),
            variable: pointer,
            location: location.into(),
            severity: 10, // Critical
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Separation Logic Entailment Checker (SOTA Implementation)
// ═══════════════════════════════════════════════════════════════════════════
//
// Academic Reference:
// - Berdine, J., Calcagno, C., O'Hearn, P. (2005)
//   "Symbolic Execution with Separation Logic"
//
// Key Operations:
// 1. Entailment: H₁ ⊢ H₂ (H₁ implies H₂)
// 2. Frame Inference: Given H₁ ⊢ H₂ * ?F, find F
// 3. Bi-abduction: Given H₁ * ?A ⊢ H₂ * ?F, find A and F

/// Entailment result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EntailmentResult {
    /// H₁ ⊢ H₂ holds
    Valid,
    /// H₁ ⊢ H₂ does not hold, with counterexample
    Invalid { reason: String },
    /// Cannot determine (incomplete)
    Unknown,
}

/// Frame inference result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FrameResult {
    /// Whether frame inference succeeded
    pub success: bool,
    /// The inferred frame F where H₁ ⊢ H₂ * F
    pub frame: Option<SymbolicHeap>,
    /// Reason for failure
    pub error: Option<String>,
}

/// Bi-abduction result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BiAbductionResult {
    /// Whether bi-abduction succeeded
    pub success: bool,
    /// Anti-frame (precondition to add): ?A where H₁ * A ⊢ H₂ * F
    pub anti_frame: Option<SymbolicHeap>,
    /// Frame (postcondition leftover): ?F
    pub frame: Option<SymbolicHeap>,
    /// Error message if failed
    pub error: Option<String>,
}

/// Separation Logic Entailment Checker
///
/// Implements symbolic execution rules for memory reasoning
pub struct EntailmentChecker {
    /// Enable pure constraint reasoning
    use_pure_reasoning: bool,
    /// Maximum iterations for fixpoint
    max_iterations: usize,
}

impl Default for EntailmentChecker {
    fn default() -> Self {
        Self::new()
    }
}

impl EntailmentChecker {
    pub fn new() -> Self {
        Self {
            use_pure_reasoning: true,
            max_iterations: 100,
        }
    }

    /// Check if H₁ ⊢ H₂ (H₁ entails H₂)
    ///
    /// Algorithm:
    /// 1. Match spatial predicates (points-to assertions)
    /// 2. Check pure constraints compatibility
    /// 3. Verify no dangling references
    pub fn check_entailment(&self, lhs: &SymbolicHeap, rhs: &SymbolicHeap) -> EntailmentResult {
        // Rule 1: Error state propagates
        if lhs.is_error {
            return EntailmentResult::Valid; // Anything follows from false
        }
        if rhs.is_error && !lhs.is_error {
            return EntailmentResult::Invalid {
                reason: "LHS is not error but RHS requires error".to_string(),
            };
        }

        // Rule 2: Check all RHS spatial predicates are in LHS
        for (var, rhs_cell) in &rhs.cells {
            match lhs.cells.get(var) {
                Some(lhs_cell) => {
                    // Check allocation status
                    if rhs_cell.is_allocated && !lhs_cell.is_allocated {
                        return EntailmentResult::Invalid {
                            reason: format!(
                                "Variable '{}' must be allocated but isn't in LHS",
                                var
                            ),
                        };
                    }

                    // Check null status (over-approximation)
                    if !rhs_cell.may_be_null && lhs_cell.may_be_null {
                        return EntailmentResult::Invalid {
                            reason: format!(
                                "Variable '{}' may be null in LHS but must not be null in RHS",
                                var
                            ),
                        };
                    }

                    // Check fields are present
                    for (field, value) in &rhs_cell.fields {
                        match lhs_cell.fields.get(field) {
                            Some(lhs_value) if lhs_value == value => {}
                            Some(lhs_value) => {
                                return EntailmentResult::Invalid {
                                    reason: format!(
                                        "Field '{}.{}' has value '{}' in LHS but '{}' in RHS",
                                        var, field, lhs_value, value
                                    ),
                                };
                            }
                            None => {
                                return EntailmentResult::Invalid {
                                    reason: format!(
                                        "Field '{}.{}' required by RHS but missing in LHS",
                                        var, field
                                    ),
                                };
                            }
                        }
                    }
                }
                None => {
                    return EntailmentResult::Invalid {
                        reason: format!("Variable '{}' in RHS but not in LHS", var),
                    };
                }
            }
        }

        // Rule 3: Check pure constraints
        if self.use_pure_reasoning {
            for constraint in &rhs.pure_constraints {
                if !self.check_pure_constraint_implied(lhs, constraint) {
                    return EntailmentResult::Invalid {
                        reason: format!("Pure constraint '{}' not implied by LHS", constraint),
                    };
                }
            }
        }

        EntailmentResult::Valid
    }

    /// Check if a pure constraint is implied by the heap state
    fn check_pure_constraint_implied(&self, heap: &SymbolicHeap, constraint: &str) -> bool {
        // Simple pattern matching for common constraints
        if constraint.ends_with("!= null") {
            let var = constraint.trim_end_matches(" != null").trim();
            return heap.pure_constraints.contains(&constraint.to_string())
                || heap.cells.get(var).map_or(false, |c| !c.may_be_null);
        }

        if constraint.ends_with("== null") {
            let var = constraint.trim_end_matches(" == null").trim();
            return heap.cells.get(var).map_or(true, |c| c.may_be_null);
        }

        // Check if constraint is directly present
        heap.pure_constraints.contains(&constraint.to_string())
    }

    /// Infer frame F where LHS ⊢ RHS * F
    ///
    /// Frame = LHS - RHS (spatial predicates not consumed by RHS)
    ///
    /// This is the foundation of local reasoning in separation logic
    pub fn infer_frame(&self, lhs: &SymbolicHeap, rhs: &SymbolicHeap) -> FrameResult {
        // First check if entailment is possible
        match self.check_entailment(lhs, rhs) {
            EntailmentResult::Invalid { reason } => {
                return FrameResult {
                    success: false,
                    frame: None,
                    error: Some(reason),
                };
            }
            EntailmentResult::Unknown => {
                return FrameResult {
                    success: false,
                    frame: None,
                    error: Some("Entailment unknown".to_string()),
                };
            }
            EntailmentResult::Valid => {}
        }

        // Build frame: cells in LHS but not "consumed" by RHS
        let mut frame = SymbolicHeap::new();

        for (var, lhs_cell) in &lhs.cells {
            if !rhs.cells.contains_key(var) {
                // This cell is part of the frame
                frame.cells.insert(var.clone(), lhs_cell.clone());
            }
        }

        // Frame inherits pure constraints from LHS that aren't in RHS
        for constraint in &lhs.pure_constraints {
            if !rhs.pure_constraints.contains(constraint) {
                frame.add_pure_constraint(constraint.clone());
            }
        }

        FrameResult {
            success: true,
            frame: Some(frame),
            error: None,
        }
    }

    /// Bi-abduction: Given H₁ * ?A ⊢ H₂ * ?F, find A (anti-frame) and F (frame)
    ///
    /// This is the core of compositional verification (Calcagno et al., 2011)
    ///
    /// Algorithm:
    /// 1. Compute missing resources in LHS → Anti-frame A
    /// 2. Compute leftover resources in LHS → Frame F
    /// 3. Verify: H₁ * A ⊢ H₂ * F
    pub fn bi_abduce(&self, lhs: &SymbolicHeap, rhs: &SymbolicHeap) -> BiAbductionResult {
        let mut anti_frame = SymbolicHeap::new(); // Missing preconditions
        let mut frame = SymbolicHeap::new(); // Leftover postconditions

        // Step 1: Find resources required by RHS but missing in LHS (anti-frame)
        for (var, rhs_cell) in &rhs.cells {
            match lhs.cells.get(var) {
                Some(lhs_cell) => {
                    // Check for missing fields
                    for (field, value) in &rhs_cell.fields {
                        if !lhs_cell.fields.contains_key(field) {
                            // Need to add this field to anti-frame
                            let anti_cell = anti_frame
                                .cells
                                .entry(var.clone())
                                .or_insert_with(HeapCell::new);
                            anti_cell.fields.insert(field.clone(), value.clone());
                        }
                    }

                    // Check null constraints
                    if !rhs_cell.may_be_null && lhs_cell.may_be_null {
                        anti_frame.add_pure_constraint(format!("{} != null", var));
                    }
                }
                None => {
                    // Entire cell missing - add to anti-frame
                    anti_frame.cells.insert(var.clone(), rhs_cell.clone());
                    if !rhs_cell.may_be_null {
                        anti_frame.add_pure_constraint(format!("{} != null", var));
                    }
                }
            }
        }

        // Step 2: Find resources in LHS not consumed by RHS (frame)
        for (var, lhs_cell) in &lhs.cells {
            if !rhs.cells.contains_key(var) {
                frame.cells.insert(var.clone(), lhs_cell.clone());
            }
        }

        // Step 3: Add pure constraints to anti-frame
        for constraint in &rhs.pure_constraints {
            if !lhs.pure_constraints.contains(constraint) {
                // This constraint is missing and needs to be assumed
                anti_frame.add_pure_constraint(constraint.clone());
            }
        }

        // Frame inherits leftover pure constraints
        for constraint in &lhs.pure_constraints {
            if !rhs.pure_constraints.contains(constraint) {
                frame.add_pure_constraint(constraint.clone());
            }
        }

        // Verify the bi-abduction is correct
        let combined_lhs = self.separating_conjunction(lhs, &anti_frame);
        let combined_rhs = self.separating_conjunction(rhs, &frame);

        match self.check_entailment(&combined_lhs, &combined_rhs) {
            EntailmentResult::Valid => BiAbductionResult {
                success: true,
                anti_frame: Some(anti_frame),
                frame: Some(frame),
                error: None,
            },
            EntailmentResult::Invalid { reason } => BiAbductionResult {
                success: false,
                anti_frame: None,
                frame: None,
                error: Some(format!("Bi-abduction verification failed: {}", reason)),
            },
            EntailmentResult::Unknown => BiAbductionResult {
                success: false,
                anti_frame: Some(anti_frame),
                frame: Some(frame),
                error: Some("Bi-abduction result unknown".to_string()),
            },
        }
    }

    /// Compute separating conjunction: H₁ * H₂
    ///
    /// Precondition: H₁ and H₂ must be disjoint (no overlapping cells)
    pub fn separating_conjunction(&self, h1: &SymbolicHeap, h2: &SymbolicHeap) -> SymbolicHeap {
        let mut result = h1.copy();

        // Add cells from h2 (disjoint union)
        for (var, cell) in &h2.cells {
            if result.cells.contains_key(var) {
                // Overlapping cells - this is an error in separation logic
                result.set_error(format!(
                    "Overlapping cell '{}' in separating conjunction",
                    var
                ));
                return result;
            }
            result.cells.insert(var.clone(), cell.clone());
        }

        // Combine pure constraints
        for constraint in &h2.pure_constraints {
            result.add_pure_constraint(constraint.clone());
        }

        result
    }

    /// Check if two heaps are separable (can be combined with *)
    pub fn is_separable(&self, h1: &SymbolicHeap, h2: &SymbolicHeap) -> bool {
        // Heaps are separable if they have no overlapping cells
        for var in h1.cells.keys() {
            if h2.cells.contains_key(var) {
                return false;
            }
        }
        true
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Function Specification (for compositional verification)
// ═══════════════════════════════════════════════════════════════════════════

/// Function specification in separation logic
///
/// Represents: {Pre} f(args) {Post}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionSpec {
    /// Function name
    pub name: String,
    /// Precondition (required heap state)
    pub precondition: SymbolicHeap,
    /// Postcondition (resulting heap state)
    pub postcondition: SymbolicHeap,
    /// Modified variables
    pub modifies: HashSet<String>,
}

impl FunctionSpec {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            precondition: SymbolicHeap::new(),
            postcondition: SymbolicHeap::new(),
            modifies: HashSet::new(),
        }
    }

    /// Set precondition
    pub fn with_precondition(mut self, pre: SymbolicHeap) -> Self {
        self.precondition = pre;
        self
    }

    /// Set postcondition
    pub fn with_postcondition(mut self, post: SymbolicHeap) -> Self {
        self.postcondition = post;
        self
    }

    /// Add modified variable
    pub fn modifies(mut self, var: impl Into<String>) -> Self {
        self.modifies.insert(var.into());
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_heap() {
        let heap = SymbolicHeap::new();
        assert!(heap.cells.is_empty());
        assert!(heap.pure_constraints.is_empty());
        assert!(!heap.is_error);
    }

    #[test]
    fn test_allocate() {
        let mut heap = SymbolicHeap::new();
        heap.allocate("x");

        assert!(heap.is_allocated("x"));
        assert!(!heap.may_be_null("x"));
        assert!(heap.pure_constraints.contains(&"x != null".to_string()));
    }

    #[test]
    fn test_deallocate() {
        let mut heap = SymbolicHeap::new();
        heap.allocate("x");

        assert!(heap.deallocate("x").is_ok());
        assert!(!heap.is_allocated("x"));
    }

    #[test]
    fn test_double_free() {
        let mut heap = SymbolicHeap::new();
        heap.allocate("x");
        heap.deallocate("x").unwrap();

        let result = heap.deallocate("x");
        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "Double-free detected");
    }

    #[test]
    fn test_merge_null_status() {
        let mut heap1 = SymbolicHeap::new();
        heap1.allocate("x");
        heap1.mark_not_null("x");

        let mut heap2 = SymbolicHeap::new();
        heap2.allocate("x");
        heap2.mark_may_be_null("x");

        let merged = heap1.merge(&heap2);

        // Conservative: if either may be null, result may be null
        assert!(merged.may_be_null("x"));
    }

    #[test]
    fn test_abstract_location() {
        let var = AbstractLocation::variable("x");
        assert_eq!(var.base_var(), Some("x"));

        let field = AbstractLocation::field("obj", "name");
        assert_eq!(field.base_var(), Some("obj"));

        let arr = AbstractLocation::array_element("arr", 5);
        assert_eq!(arr.base_var(), Some("arr"));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Entailment Checker Tests
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_entailment_empty_heaps() {
        let checker = EntailmentChecker::new();
        let h1 = SymbolicHeap::new();
        let h2 = SymbolicHeap::new();

        assert!(matches!(
            checker.check_entailment(&h1, &h2),
            EntailmentResult::Valid
        ));
    }

    #[test]
    fn test_entailment_simple_valid() {
        let checker = EntailmentChecker::new();

        let mut h1 = SymbolicHeap::new();
        h1.allocate("x");
        h1.allocate("y");

        let mut h2 = SymbolicHeap::new();
        h2.allocate("x");

        // h1 (x, y) ⊢ h2 (x) - valid because h1 has more
        assert!(matches!(
            checker.check_entailment(&h1, &h2),
            EntailmentResult::Valid
        ));
    }

    #[test]
    fn test_entailment_missing_variable() {
        let checker = EntailmentChecker::new();

        let mut h1 = SymbolicHeap::new();
        h1.allocate("x");

        let mut h2 = SymbolicHeap::new();
        h2.allocate("x");
        h2.allocate("y"); // y not in h1

        // h1 (x) ⊢ h2 (x, y) - invalid because y missing
        assert!(matches!(
            checker.check_entailment(&h1, &h2),
            EntailmentResult::Invalid { .. }
        ));
    }

    #[test]
    fn test_frame_inference() {
        let checker = EntailmentChecker::new();

        let mut h1 = SymbolicHeap::new();
        h1.allocate("x");
        h1.allocate("y");
        h1.allocate("z");

        let mut h2 = SymbolicHeap::new();
        h2.allocate("x");

        // Frame = {y, z} (what's left after "consuming" h2)
        let result = checker.infer_frame(&h1, &h2);
        assert!(result.success);

        let frame = result.frame.unwrap();
        assert!(frame.cells.contains_key("y"));
        assert!(frame.cells.contains_key("z"));
        assert!(!frame.cells.contains_key("x")); // x was consumed
    }

    #[test]
    fn test_bi_abduction() {
        let checker = EntailmentChecker::new();

        // h1: {x ↦ _}
        let mut h1 = SymbolicHeap::new();
        h1.allocate("x");

        // h2: {x ↦ _, y ↦ _}
        let mut h2 = SymbolicHeap::new();
        h2.allocate("x");
        h2.allocate("y");

        // Bi-abduce: h1 * ?A ⊢ h2 * ?F
        // Should find: A = {y ↦ _}, F = emp
        let result = checker.bi_abduce(&h1, &h2);
        assert!(result.success);

        let anti_frame = result.anti_frame.unwrap();
        assert!(anti_frame.cells.contains_key("y")); // y was missing
        assert!(!anti_frame.cells.contains_key("x")); // x was present
    }

    #[test]
    fn test_separating_conjunction() {
        let checker = EntailmentChecker::new();

        let mut h1 = SymbolicHeap::new();
        h1.allocate("x");

        let mut h2 = SymbolicHeap::new();
        h2.allocate("y");

        // h1 * h2 = {x ↦ _, y ↦ _}
        let combined = checker.separating_conjunction(&h1, &h2);
        assert!(!combined.is_error);
        assert!(combined.cells.contains_key("x"));
        assert!(combined.cells.contains_key("y"));
    }

    #[test]
    fn test_separating_conjunction_overlap_error() {
        let checker = EntailmentChecker::new();

        let mut h1 = SymbolicHeap::new();
        h1.allocate("x");

        let mut h2 = SymbolicHeap::new();
        h2.allocate("x"); // Overlapping!

        // h1 * h2 should fail (overlapping cells)
        let combined = checker.separating_conjunction(&h1, &h2);
        assert!(combined.is_error);
    }

    #[test]
    fn test_function_spec() {
        let spec = FunctionSpec::new("malloc")
            .with_precondition(SymbolicHeap::new())
            .with_postcondition({
                let mut post = SymbolicHeap::new();
                post.allocate("result");
                post
            })
            .modifies("result");

        assert_eq!(spec.name, "malloc");
        assert!(spec.precondition.cells.is_empty());
        assert!(spec.postcondition.cells.contains_key("result"));
        assert!(spec.modifies.contains("result"));
    }
}
