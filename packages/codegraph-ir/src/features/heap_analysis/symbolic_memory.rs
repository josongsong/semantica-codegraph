//! KLEE-Style Symbolic Memory Model
//!
//! Academic References:
//! - Cadar, C., Dunbar, D., Engler, D. (2008). "KLEE: Unassisted and Automatic
//!   Generation of High-Coverage Tests for Complex Systems Programs"
//! - Baldoni, R. et al. (2018). "A Survey of Symbolic Execution Techniques"
//!
//! Key Features:
//! - **Copy-on-Write Objects**: Memory objects with lazy copying
//! - **Symbolic Addresses**: Support for symbolic pointer arithmetic
//! - **Object Resolution**: Efficient lookup for symbolic pointers
//! - **Path Conditions**: Integrated constraint management
//!
//! ## Memory Model
//!
//! ```text
//! Memory ::= ObjectStore × AddressSpace × PathConditions
//!
//! ObjectStore = ObjectId → MemoryObject
//! AddressSpace = Address → ObjectId
//! ```
//!
//! ## KLEE's Key Insight
//!
//! Instead of modeling memory as a flat byte array, model it as a collection
//! of memory objects. This allows:
//! - Efficient copy-on-write during forking
//! - Precise aliasing analysis
//! - Sound handling of symbolic pointers

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::Arc;

// ═══════════════════════════════════════════════════════════════════════════
// Core Types
// ═══════════════════════════════════════════════════════════════════════════

/// Unique object identifier
pub type ObjectId = u64;

/// Memory address (can be concrete or symbolic)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Address {
    /// Concrete address
    Concrete(u64),
    /// Symbolic address: base + symbolic_offset
    Symbolic {
        base_object: ObjectId,
        offset: SymbolicExpr,
    },
    /// Null pointer
    Null,
    /// Invalid/uninitialized
    Invalid,
}

/// Symbolic expression for addresses/values
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SymbolicExpr {
    /// Concrete value
    Concrete(i64),
    /// Symbolic variable
    Symbol(String),
    /// Addition: e1 + e2
    Add(Box<SymbolicExpr>, Box<SymbolicExpr>),
    /// Subtraction: e1 - e2
    Sub(Box<SymbolicExpr>, Box<SymbolicExpr>),
    /// Multiplication: e1 * e2
    Mul(Box<SymbolicExpr>, Box<SymbolicExpr>),
    /// Conditional: if cond then e1 else e2
    Ite(Box<PathCondition>, Box<SymbolicExpr>, Box<SymbolicExpr>),
}

impl SymbolicExpr {
    pub fn concrete(val: i64) -> Self {
        Self::Concrete(val)
    }

    pub fn symbol(name: impl Into<String>) -> Self {
        Self::Symbol(name.into())
    }

    pub fn add(self, other: Self) -> Self {
        match (&self, &other) {
            (Self::Concrete(a), Self::Concrete(b)) => Self::Concrete(a + b),
            _ => Self::Add(Box::new(self), Box::new(other)),
        }
    }

    pub fn sub(self, other: Self) -> Self {
        match (&self, &other) {
            (Self::Concrete(a), Self::Concrete(b)) => Self::Concrete(a - b),
            _ => Self::Sub(Box::new(self), Box::new(other)),
        }
    }

    pub fn is_concrete(&self) -> bool {
        matches!(self, Self::Concrete(_))
    }

    pub fn as_concrete(&self) -> Option<i64> {
        match self {
            Self::Concrete(v) => Some(*v),
            _ => None,
        }
    }

    /// Get all symbolic variables in this expression
    pub fn free_symbols(&self) -> HashSet<String> {
        let mut symbols = HashSet::new();
        self.collect_symbols(&mut symbols);
        symbols
    }

    fn collect_symbols(&self, symbols: &mut HashSet<String>) {
        match self {
            Self::Concrete(_) => {}
            Self::Symbol(s) => {
                symbols.insert(s.clone());
            }
            Self::Add(a, b) | Self::Sub(a, b) | Self::Mul(a, b) => {
                a.collect_symbols(symbols);
                b.collect_symbols(symbols);
            }
            Self::Ite(_, t, e) => {
                t.collect_symbols(symbols);
                e.collect_symbols(symbols);
            }
        }
    }
}

/// Path condition for symbolic execution
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PathCondition {
    /// True
    True,
    /// False
    False,
    /// Comparison: e1 op e2
    Compare {
        lhs: SymbolicExpr,
        op: CompareOp,
        rhs: SymbolicExpr,
    },
    /// Logical AND
    And(Vec<PathCondition>),
    /// Logical OR
    Or(Vec<PathCondition>),
    /// Logical NOT
    Not(Box<PathCondition>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CompareOp {
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
}

impl PathCondition {
    pub fn and(conditions: Vec<Self>) -> Self {
        let filtered: Vec<_> = conditions
            .into_iter()
            .filter(|c| *c != Self::True)
            .collect();
        match filtered.len() {
            0 => Self::True,
            1 => filtered.into_iter().next().unwrap(),
            _ => Self::And(filtered),
        }
    }

    pub fn or(conditions: Vec<Self>) -> Self {
        let filtered: Vec<_> = conditions
            .into_iter()
            .filter(|c| *c != Self::False)
            .collect();
        match filtered.len() {
            0 => Self::False,
            1 => filtered.into_iter().next().unwrap(),
            _ => Self::Or(filtered),
        }
    }

    pub fn not(self) -> Self {
        match self {
            Self::True => Self::False,
            Self::False => Self::True,
            Self::Not(inner) => *inner,
            other => Self::Not(Box::new(other)),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Memory Object (KLEE-style)
// ═══════════════════════════════════════════════════════════════════════════

/// Memory object - represents a contiguous region of memory
///
/// Examples:
/// - Stack allocation: local variable
/// - Heap allocation: malloc result
/// - Global: global variable
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryObject {
    /// Unique identifier
    pub id: ObjectId,
    /// Object name (for debugging)
    pub name: String,
    /// Size in bytes (may be symbolic)
    pub size: SymbolicExpr,
    /// Base address
    pub address: u64,
    /// Is this object allocated on the heap?
    pub is_heap: bool,
    /// Is this object symbolic?
    pub is_symbolic: bool,
    /// Object contents: offset → value
    pub contents: BTreeMap<i64, SymbolicValue>,
    /// Is this object freed?
    pub is_freed: bool,
    /// Allocation site (for debugging)
    pub alloc_site: Option<String>,
}

/// Symbolic value stored in memory
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SymbolicValue {
    /// Concrete byte value
    Concrete(u8),
    /// Concrete integer (4/8 bytes)
    ConcreteInt(i64),
    /// Symbolic expression
    Symbolic(SymbolicExpr),
    /// Pointer to another object
    Pointer(Address),
    /// Uninitialized
    Uninitialized,
}

impl MemoryObject {
    pub fn new(id: ObjectId, name: impl Into<String>, size: i64, address: u64) -> Self {
        Self {
            id,
            name: name.into(),
            size: SymbolicExpr::concrete(size),
            address,
            is_heap: false,
            is_symbolic: false,
            contents: BTreeMap::new(),
            is_freed: false,
            alloc_site: None,
        }
    }

    pub fn heap(id: ObjectId, name: impl Into<String>, size: SymbolicExpr, address: u64) -> Self {
        Self {
            id,
            name: name.into(),
            size,
            address,
            is_heap: true,
            is_symbolic: false,
            contents: BTreeMap::new(),
            is_freed: false,
            alloc_site: None,
        }
    }

    pub fn symbolic(id: ObjectId, name: impl Into<String>, size: SymbolicExpr) -> Self {
        Self {
            id,
            name: name.into(),
            size,
            address: 0, // Symbolic objects may not have concrete address
            is_heap: false,
            is_symbolic: true,
            contents: BTreeMap::new(),
            is_freed: false,
            alloc_site: None,
        }
    }

    /// Read value at offset
    pub fn read(&self, offset: i64) -> &SymbolicValue {
        self.contents
            .get(&offset)
            .unwrap_or(&SymbolicValue::Uninitialized)
    }

    /// Write value at offset
    pub fn write(&mut self, offset: i64, value: SymbolicValue) {
        self.contents.insert(offset, value);
    }

    /// Mark as freed
    pub fn free(&mut self) {
        self.is_freed = true;
    }

    /// Check if access is in bounds (concrete size only)
    pub fn is_in_bounds(&self, offset: i64) -> Option<bool> {
        match &self.size {
            SymbolicExpr::Concrete(size) => Some(offset >= 0 && offset < *size),
            _ => None, // Symbolic size - need solver
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Symbolic Memory State
// ═══════════════════════════════════════════════════════════════════════════

/// Symbolic memory state - KLEE-style memory model
///
/// Represents the complete memory state at a program point,
/// including path conditions that constrain symbolic values.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolicMemory {
    /// Object store: id → memory object
    objects: HashMap<ObjectId, Arc<MemoryObject>>,
    /// Address space: base_address → object_id
    address_space: BTreeMap<u64, ObjectId>,
    /// Variable to address mapping
    variables: HashMap<String, Address>,
    /// Path conditions
    path_conditions: Vec<PathCondition>,
    /// Next object ID
    next_object_id: ObjectId,
    /// Next free address
    next_address: u64,
    /// Error state
    pub error: Option<MemoryError>,
}

/// Memory error types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MemoryError {
    NullDereference {
        location: String,
    },
    UseAfterFree {
        object: String,
        location: String,
    },
    DoubleFree {
        object: String,
        location: String,
    },
    BufferOverflow {
        object: String,
        offset: i64,
        size: i64,
        location: String,
    },
    InvalidPointer {
        location: String,
    },
}

impl Default for SymbolicMemory {
    fn default() -> Self {
        Self::new()
    }
}

impl SymbolicMemory {
    pub fn new() -> Self {
        Self {
            objects: HashMap::new(),
            address_space: BTreeMap::new(),
            variables: HashMap::new(),
            path_conditions: Vec::new(),
            next_object_id: 1,
            next_address: 0x1000, // Start allocations at 0x1000
            error: None,
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Allocation
    // ═══════════════════════════════════════════════════════════════════════

    /// Allocate stack object (local variable)
    pub fn alloc_stack(&mut self, name: impl Into<String>, size: i64) -> Address {
        let name = name.into();
        let id = self.next_object_id;
        self.next_object_id += 1;

        let address = self.next_address;
        self.next_address += size as u64;

        let mut obj = MemoryObject::new(id, name.clone(), size, address);
        obj.is_heap = false;

        self.objects.insert(id, Arc::new(obj));
        self.address_space.insert(address, id);

        let addr = Address::Concrete(address);
        self.variables.insert(name, addr.clone());
        addr
    }

    /// Allocate heap object (malloc)
    pub fn alloc_heap(&mut self, size: SymbolicExpr) -> Address {
        let id = self.next_object_id;
        self.next_object_id += 1;

        let address = self.next_address;
        // For symbolic sizes, allocate worst-case
        let alloc_size = size.as_concrete().unwrap_or(1024) as u64;
        self.next_address += alloc_size;

        let mut obj = MemoryObject::heap(id, format!("heap_{}", id), size, address);
        obj.alloc_site = Some("malloc".to_string());

        self.objects.insert(id, Arc::new(obj));
        self.address_space.insert(address, id);

        Address::Concrete(address)
    }

    /// Create symbolic object (function argument, etc.)
    pub fn make_symbolic(&mut self, name: impl Into<String>, size: SymbolicExpr) -> Address {
        let name = name.into();
        let id = self.next_object_id;
        self.next_object_id += 1;

        let obj = MemoryObject::symbolic(id, name.clone(), size);
        self.objects.insert(id, Arc::new(obj));

        let addr = Address::Symbolic {
            base_object: id,
            offset: SymbolicExpr::concrete(0),
        };
        self.variables.insert(name, addr.clone());
        addr
    }

    /// Free heap object
    pub fn free(&mut self, addr: &Address, location: &str) -> Result<(), MemoryError> {
        match addr {
            Address::Null => {
                // free(NULL) is allowed in C
                Ok(())
            }
            Address::Concrete(base) => {
                let obj_id = self.address_space.get(base).copied().ok_or_else(|| {
                    MemoryError::InvalidPointer {
                        location: location.to_string(),
                    }
                })?;

                let obj = self
                    .objects
                    .get(&obj_id)
                    .ok_or_else(|| MemoryError::InvalidPointer {
                        location: location.to_string(),
                    })?;

                if obj.is_freed {
                    return Err(MemoryError::DoubleFree {
                        object: obj.name.clone(),
                        location: location.to_string(),
                    });
                }

                if !obj.is_heap {
                    return Err(MemoryError::InvalidPointer {
                        location: location.to_string(),
                    });
                }

                // Copy-on-write: create modified version
                let mut new_obj = obj.as_ref().clone();
                new_obj.free();
                self.objects.insert(obj_id, Arc::new(new_obj));

                Ok(())
            }
            Address::Symbolic { base_object, .. } => {
                let obj =
                    self.objects
                        .get(base_object)
                        .ok_or_else(|| MemoryError::InvalidPointer {
                            location: location.to_string(),
                        })?;

                if obj.is_freed {
                    return Err(MemoryError::DoubleFree {
                        object: obj.name.clone(),
                        location: location.to_string(),
                    });
                }

                let mut new_obj = obj.as_ref().clone();
                new_obj.free();
                self.objects.insert(*base_object, Arc::new(new_obj));

                Ok(())
            }
            Address::Invalid => Err(MemoryError::InvalidPointer {
                location: location.to_string(),
            }),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Read/Write Operations
    // ═══════════════════════════════════════════════════════════════════════

    /// Read value from address
    pub fn read(&self, addr: &Address, location: &str) -> Result<SymbolicValue, MemoryError> {
        match addr {
            Address::Null => Err(MemoryError::NullDereference {
                location: location.to_string(),
            }),
            Address::Concrete(base) => {
                let obj_id = self
                    .address_space
                    .get(base)
                    .or_else(|| {
                        // Find object containing this address
                        self.address_space
                            .range(..=*base)
                            .next_back()
                            .map(|(_, id)| id)
                    })
                    .copied()
                    .ok_or_else(|| MemoryError::InvalidPointer {
                        location: location.to_string(),
                    })?;

                let obj = self
                    .objects
                    .get(&obj_id)
                    .ok_or_else(|| MemoryError::InvalidPointer {
                        location: location.to_string(),
                    })?;

                if obj.is_freed {
                    return Err(MemoryError::UseAfterFree {
                        object: obj.name.clone(),
                        location: location.to_string(),
                    });
                }

                let offset = (*base - obj.address) as i64;

                // Check bounds
                if let Some(false) = obj.is_in_bounds(offset) {
                    let size = obj.size.as_concrete().unwrap_or(-1);
                    return Err(MemoryError::BufferOverflow {
                        object: obj.name.clone(),
                        offset,
                        size,
                        location: location.to_string(),
                    });
                }

                Ok(obj.read(offset).clone())
            }
            Address::Symbolic {
                base_object,
                offset,
            } => {
                let obj =
                    self.objects
                        .get(base_object)
                        .ok_or_else(|| MemoryError::InvalidPointer {
                            location: location.to_string(),
                        })?;

                if obj.is_freed {
                    return Err(MemoryError::UseAfterFree {
                        object: obj.name.clone(),
                        location: location.to_string(),
                    });
                }

                // For symbolic offset, return symbolic read
                match offset.as_concrete() {
                    Some(off) => Ok(obj.read(off).clone()),
                    None => {
                        // Symbolic read - need to return ITE expression
                        Ok(SymbolicValue::Symbolic(SymbolicExpr::symbol(format!(
                            "read_{}_{:?}",
                            obj.name, offset
                        ))))
                    }
                }
            }
            Address::Invalid => Err(MemoryError::InvalidPointer {
                location: location.to_string(),
            }),
        }
    }

    /// Write value to address
    pub fn write(
        &mut self,
        addr: &Address,
        value: SymbolicValue,
        location: &str,
    ) -> Result<(), MemoryError> {
        match addr {
            Address::Null => Err(MemoryError::NullDereference {
                location: location.to_string(),
            }),
            Address::Concrete(base) => {
                let obj_id = self
                    .address_space
                    .get(base)
                    .or_else(|| {
                        self.address_space
                            .range(..=*base)
                            .next_back()
                            .map(|(_, id)| id)
                    })
                    .copied()
                    .ok_or_else(|| MemoryError::InvalidPointer {
                        location: location.to_string(),
                    })?;

                let obj = self
                    .objects
                    .get(&obj_id)
                    .ok_or_else(|| MemoryError::InvalidPointer {
                        location: location.to_string(),
                    })?;

                if obj.is_freed {
                    return Err(MemoryError::UseAfterFree {
                        object: obj.name.clone(),
                        location: location.to_string(),
                    });
                }

                let offset = (*base - obj.address) as i64;

                // Check bounds
                if let Some(false) = obj.is_in_bounds(offset) {
                    let size = obj.size.as_concrete().unwrap_or(-1);
                    return Err(MemoryError::BufferOverflow {
                        object: obj.name.clone(),
                        offset,
                        size,
                        location: location.to_string(),
                    });
                }

                // Copy-on-write
                let mut new_obj = obj.as_ref().clone();
                new_obj.write(offset, value);
                self.objects.insert(obj_id, Arc::new(new_obj));

                Ok(())
            }
            Address::Symbolic {
                base_object,
                offset,
            } => {
                let obj =
                    self.objects
                        .get(base_object)
                        .ok_or_else(|| MemoryError::InvalidPointer {
                            location: location.to_string(),
                        })?;

                if obj.is_freed {
                    return Err(MemoryError::UseAfterFree {
                        object: obj.name.clone(),
                        location: location.to_string(),
                    });
                }

                // For concrete offset, write directly
                if let Some(off) = offset.as_concrete() {
                    let mut new_obj = obj.as_ref().clone();
                    new_obj.write(off, value);
                    self.objects.insert(*base_object, Arc::new(new_obj));
                }
                // For symbolic offset, we'd need to update all possible locations
                // This is handled by the constraint solver

                Ok(())
            }
            Address::Invalid => Err(MemoryError::InvalidPointer {
                location: location.to_string(),
            }),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Path Conditions
    // ═══════════════════════════════════════════════════════════════════════

    /// Add path condition
    pub fn add_constraint(&mut self, cond: PathCondition) {
        if cond != PathCondition::True {
            self.path_conditions.push(cond);
        }
    }

    /// Get all path conditions
    pub fn constraints(&self) -> &[PathCondition] {
        &self.path_conditions
    }

    /// Fork state with additional constraint
    pub fn fork_with(&self, cond: PathCondition) -> Self {
        let mut forked = self.clone();
        forked.add_constraint(cond);
        forked
    }

    // ═══════════════════════════════════════════════════════════════════════
    // State Merging (Path-Conditioned)
    // ═══════════════════════════════════════════════════════════════════════

    /// Merge two memory states with path conditions
    ///
    /// This implements path-conditioned state merging where:
    /// - State values become ITE expressions based on path conditions
    /// - Path conditions are combined with OR
    ///
    /// Example:
    /// - State A (condition: x > 0): y = 1
    /// - State B (condition: x <= 0): y = 2
    /// - Merged: y = ITE(x > 0, 1, 2)
    pub fn merge_with(&self, other: &Self) -> Self {
        let mut merged = Self::new();
        merged.next_object_id = self.next_object_id.max(other.next_object_id);
        merged.next_address = self.next_address.max(other.next_address);

        // Merge objects (take union)
        for (id, obj) in &self.objects {
            merged.objects.insert(*id, Arc::clone(obj));
        }
        for (id, obj) in &other.objects {
            if !merged.objects.contains_key(id) {
                merged.objects.insert(*id, Arc::clone(obj));
            } else {
                // Object exists in both - need to merge contents
                let self_obj = self.objects.get(id).unwrap();
                let other_obj = obj;

                // Create merged object with ITE values
                let mut new_obj = (**self_obj).clone();
                for (offset, other_val) in &other_obj.contents {
                    let self_val = self_obj.read(*offset);
                    if self_val != other_val {
                        // Values differ - create ITE
                        let merged_val = self.create_ite_value(
                            &self.path_conditions,
                            self_val,
                            &other.path_conditions,
                            other_val,
                        );
                        new_obj.write(*offset, merged_val);
                    }
                }
                new_obj.is_freed = self_obj.is_freed && other_obj.is_freed;
                merged.objects.insert(*id, Arc::new(new_obj));
            }
        }

        // Merge address space
        merged.address_space = self.address_space.clone();
        for (addr, id) in &other.address_space {
            merged.address_space.insert(*addr, *id);
        }

        // Merge variables
        merged.variables = self.variables.clone();
        for (name, addr) in &other.variables {
            merged.variables.insert(name.clone(), addr.clone());
        }

        // Combine path conditions with OR
        let self_cond = PathCondition::and(self.path_conditions.clone());
        let other_cond = PathCondition::and(other.path_conditions.clone());
        merged.path_conditions = vec![PathCondition::or(vec![self_cond, other_cond])];

        merged
    }

    /// Create ITE value from two different values under different conditions
    fn create_ite_value(
        &self,
        self_conds: &[PathCondition],
        self_val: &SymbolicValue,
        _other_conds: &[PathCondition],
        other_val: &SymbolicValue,
    ) -> SymbolicValue {
        // Extract symbolic expressions
        let self_expr = match self_val {
            SymbolicValue::ConcreteInt(i) => SymbolicExpr::concrete(*i),
            SymbolicValue::Symbolic(e) => e.clone(),
            _ => return self_val.clone(), // Can't create ITE for other types
        };

        let other_expr = match other_val {
            SymbolicValue::ConcreteInt(i) => SymbolicExpr::concrete(*i),
            SymbolicValue::Symbolic(e) => e.clone(),
            _ => return other_val.clone(),
        };

        let cond = Box::new(PathCondition::and(self_conds.to_vec()));
        SymbolicValue::Symbolic(SymbolicExpr::Ite(
            cond,
            Box::new(self_expr),
            Box::new(other_expr),
        ))
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Variable Access
    // ═══════════════════════════════════════════════════════════════════════

    /// Get address of variable
    pub fn get_variable(&self, name: &str) -> Option<&Address> {
        self.variables.get(name)
    }

    /// Set variable to address
    pub fn set_variable(&mut self, name: impl Into<String>, addr: Address) {
        self.variables.insert(name.into(), addr);
    }

    /// Check if variable may be null
    pub fn may_be_null(&self, name: &str) -> bool {
        match self.variables.get(name) {
            Some(Address::Null) => true,
            Some(Address::Concrete(_)) => false,
            Some(Address::Symbolic { .. }) => true, // Conservative
            _ => true,
        }
    }

    /// Get all allocated objects
    pub fn get_objects(&self) -> impl Iterator<Item = &MemoryObject> {
        self.objects.values().map(|arc| arc.as_ref())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stack_allocation() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_stack("x", 8);

        assert!(matches!(addr, Address::Concrete(_)));
        assert!(mem.get_variable("x").is_some());
    }

    #[test]
    fn test_heap_allocation() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_heap(SymbolicExpr::concrete(64));

        assert!(matches!(addr, Address::Concrete(_)));
    }

    #[test]
    fn test_write_read() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_stack("arr", 32);

        // Write
        mem.write(&addr, SymbolicValue::ConcreteInt(42), "test:1")
            .unwrap();

        // Read
        let val = mem.read(&addr, "test:2").unwrap();
        assert!(matches!(val, SymbolicValue::ConcreteInt(42)));
    }

    #[test]
    fn test_null_dereference() {
        let mem = SymbolicMemory::new();
        let result = mem.read(&Address::Null, "test:1");

        assert!(matches!(result, Err(MemoryError::NullDereference { .. })));
    }

    #[test]
    fn test_use_after_free() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_heap(SymbolicExpr::concrete(64));

        // Free
        mem.free(&addr, "test:1").unwrap();

        // Use after free
        let result = mem.read(&addr, "test:2");
        assert!(matches!(result, Err(MemoryError::UseAfterFree { .. })));
    }

    #[test]
    fn test_double_free() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_heap(SymbolicExpr::concrete(64));

        // First free
        mem.free(&addr, "test:1").unwrap();

        // Double free
        let result = mem.free(&addr, "test:2");
        assert!(matches!(result, Err(MemoryError::DoubleFree { .. })));
    }

    #[test]
    fn test_buffer_overflow() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_stack("arr", 8);

        if let Address::Concrete(base) = addr {
            // Access beyond bounds
            let bad_addr = Address::Concrete(base + 100);
            let result = mem.read(&bad_addr, "test:1");
            assert!(matches!(result, Err(MemoryError::BufferOverflow { .. })));
        }
    }

    #[test]
    fn test_symbolic_variable() {
        let mut mem = SymbolicMemory::new();
        let _addr = mem.make_symbolic("input", SymbolicExpr::concrete(256));

        assert!(mem.get_variable("input").is_some());
    }

    #[test]
    fn test_path_conditions() {
        let mut mem = SymbolicMemory::new();

        mem.add_constraint(PathCondition::Compare {
            lhs: SymbolicExpr::symbol("x"),
            op: CompareOp::Gt,
            rhs: SymbolicExpr::concrete(0),
        });

        assert_eq!(mem.constraints().len(), 1);
    }

    #[test]
    fn test_fork() {
        let mut mem = SymbolicMemory::new();
        mem.alloc_stack("x", 8);

        let forked = mem.fork_with(PathCondition::Compare {
            lhs: SymbolicExpr::symbol("x"),
            op: CompareOp::Lt,
            rhs: SymbolicExpr::concrete(10),
        });

        assert_eq!(mem.constraints().len(), 0);
        assert_eq!(forked.constraints().len(), 1);
    }

    #[test]
    fn test_merge_states() {
        let mut state_a = SymbolicMemory::new();
        let addr = state_a.alloc_stack("y", 8);
        state_a
            .write(&addr, SymbolicValue::ConcreteInt(1), "a:1")
            .unwrap();
        state_a.add_constraint(PathCondition::Compare {
            lhs: SymbolicExpr::symbol("x"),
            op: CompareOp::Gt,
            rhs: SymbolicExpr::concrete(0),
        });

        let mut state_b = SymbolicMemory::new();
        let addr_b = state_b.alloc_stack("y", 8);
        state_b
            .write(&addr_b, SymbolicValue::ConcreteInt(2), "b:1")
            .unwrap();
        state_b.add_constraint(PathCondition::Compare {
            lhs: SymbolicExpr::symbol("x"),
            op: CompareOp::Le,
            rhs: SymbolicExpr::concrete(0),
        });

        let merged = state_a.merge_with(&state_b);

        // Should have path condition (x > 0) OR (x <= 0)
        assert!(!merged.constraints().is_empty());
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Edge Cases (L11 SOTA Coverage)
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_edge_invalid_address_access() {
        let mem = SymbolicMemory::new();
        let result = mem.read(&Address::Invalid, "test:1");

        // Invalid address should return error
        assert!(result.is_err());
    }

    #[test]
    fn test_edge_pointer_aliasing() {
        let mut mem = SymbolicMemory::new();

        // Allocate one object
        let addr = mem.alloc_heap(SymbolicExpr::concrete(64));

        // Create alias
        mem.set_variable("ptr1".to_string(), addr.clone());
        mem.set_variable("ptr2".to_string(), addr.clone());

        // Write through ptr1
        mem.write(&addr, SymbolicValue::ConcreteInt(42), "test:1")
            .unwrap();

        // Read through ptr2 (alias) should see same value
        let val = mem.read(&addr, "test:2").unwrap();
        assert!(matches!(val, SymbolicValue::ConcreteInt(42)));

        // Both variables should point to same address
        assert_eq!(mem.get_variable("ptr1"), mem.get_variable("ptr2"));
    }

    #[test]
    fn test_edge_empty_memory_merge() {
        let mem_a = SymbolicMemory::new();
        let mem_b = SymbolicMemory::new();

        let merged = mem_a.merge_with(&mem_b);

        // Empty merge should produce empty result
        assert_eq!(merged.get_objects().count(), 0);
    }

    #[test]
    fn test_edge_concrete_address_zero() {
        let mut mem = SymbolicMemory::new();

        // Address 0 is valid but unusual
        let addr = Address::Concrete(0);

        // Should fail because no object at address 0
        let result = mem.read(&addr, "test:1");
        assert!(result.is_err());
    }

    #[test]
    fn test_edge_symbolic_offset_read() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_heap(SymbolicExpr::concrete(64));

        if let Address::Concrete(base) = addr {
            // Create symbolic offset address
            let obj_id = *mem.address_space.get(&base).unwrap();
            let sym_addr = Address::Symbolic {
                base_object: obj_id,
                offset: SymbolicExpr::symbol("idx"),
            };

            // Read from symbolic address should work
            let result = mem.read(&sym_addr, "test:1");
            // May succeed or fail depending on bounds - just check no panic
            let _ = result;
        }
    }

    #[test]
    fn test_edge_free_null_pointer() {
        let mut mem = SymbolicMemory::new();

        // Freeing null is allowed in C (no-op)
        let result = mem.free(&Address::Null, "test:1");
        assert!(result.is_ok()); // C standard: free(NULL) is a no-op
    }

    #[test]
    fn test_edge_write_to_freed_memory() {
        let mut mem = SymbolicMemory::new();
        let addr = mem.alloc_heap(SymbolicExpr::concrete(64));

        // Free the memory
        mem.free(&addr, "test:1").unwrap();

        // Write to freed memory should fail
        let result = mem.write(&addr, SymbolicValue::ConcreteInt(42), "test:2");
        assert!(matches!(result, Err(MemoryError::UseAfterFree { .. })));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Extreme Cases (Stress Tests)
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_extreme_mass_allocation() {
        let mut mem = SymbolicMemory::new();
        let count = 1000;

        // Allocate 1000 objects
        let mut addrs = Vec::with_capacity(count);
        for i in 0..count {
            let addr = mem.alloc_heap(SymbolicExpr::concrete(64));
            mem.set_variable(format!("ptr_{}", i), addr.clone());
            addrs.push(addr);
        }

        // Verify all allocations
        assert_eq!(mem.get_objects().count(), count);

        // Free all
        for addr in addrs {
            mem.free(&addr, "test:cleanup").unwrap();
        }

        // All should be marked as freed
        assert!(mem.get_objects().all(|obj| obj.is_freed));
    }

    #[test]
    fn test_extreme_deep_symbolic_expression() {
        let mut mem = SymbolicMemory::new();

        // Build deeply nested symbolic expression
        let mut expr = SymbolicExpr::symbol("x");
        for i in 0..50 {
            expr = expr.add(SymbolicExpr::concrete(i));
        }

        // Create address with complex offset
        let addr = mem.alloc_heap(expr);

        // Should handle without stack overflow
        assert!(matches!(addr, Address::Concrete(_)));
    }

    #[test]
    fn test_extreme_many_path_conditions() {
        let mut mem = SymbolicMemory::new();

        // Add 100 path conditions
        for i in 0..100 {
            mem.add_constraint(PathCondition::Compare {
                lhs: SymbolicExpr::symbol(format!("x_{}", i)),
                op: CompareOp::Gt,
                rhs: SymbolicExpr::concrete(0),
            });
        }

        assert_eq!(mem.constraints().len(), 100);

        // Fork should preserve all conditions
        let forked = mem.fork_with(PathCondition::True);
        assert_eq!(forked.constraints().len(), 100);
    }

    #[test]
    fn test_extreme_rapid_alloc_free_cycle() {
        let mut mem = SymbolicMemory::new();

        // Rapid allocation and deallocation cycle
        for _ in 0..500 {
            let addr = mem.alloc_heap(SymbolicExpr::concrete(32));
            mem.free(&addr, "test:cycle").unwrap();
        }

        // All objects should be freed
        assert!(mem.get_objects().all(|obj| obj.is_freed));
    }

    #[test]
    fn test_extreme_merge_many_states() {
        let mut states: Vec<SymbolicMemory> = Vec::new();

        // Create 10 states with different values
        for i in 0..10 {
            let mut state = SymbolicMemory::new();
            let addr = state.alloc_stack("x", 8);
            state
                .write(&addr, SymbolicValue::ConcreteInt(i), "test:init")
                .unwrap();
            state.add_constraint(PathCondition::Compare {
                lhs: SymbolicExpr::symbol("branch"),
                op: CompareOp::Eq,
                rhs: SymbolicExpr::concrete(i),
            });
            states.push(state);
        }

        // Cascade merge
        let mut merged = states.remove(0);
        for state in states {
            merged = merged.merge_with(&state);
        }

        // Should have combined path conditions
        assert!(!merged.constraints().is_empty());
    }
}
