/// Core concurrency analysis models
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

/// Variable access type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AccessType {
    /// Read access (e.g., x)
    Read,
    /// Write access (e.g., x = 1)
    Write,
    /// Read-write access (e.g., x += 1)
    ReadWrite,
}

impl AccessType {
    /// Check if this is a write (includes ReadWrite)
    pub fn is_write(&self) -> bool {
        matches!(self, AccessType::Write | AccessType::ReadWrite)
    }

    /// Check if this is a read (includes ReadWrite)
    pub fn is_read(&self) -> bool {
        matches!(self, AccessType::Read | AccessType::ReadWrite)
    }
}

/// Race condition severity
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum RaceSeverity {
    /// Read-Read (informational only)
    Low,
    /// Read-Write race
    Medium,
    /// Write-Read race with side effects
    High,
    /// Write-Write race (most severe)
    Critical,
}

impl RaceSeverity {
    /// Determine severity from two access types
    pub fn from_accesses(a: AccessType, b: AccessType) -> Self {
        match (a.is_write(), b.is_write()) {
            (true, true) => RaceSeverity::Critical,
            (true, false) | (false, true) => RaceSeverity::High,
            (false, false) => RaceSeverity::Low,
        }
    }
}

/// Shared variable type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SharedVarType {
    /// Class field (self.xxx)
    ClassField,
    /// Global variable
    Global,
    /// Module-level variable
    Module,
}

/// Shared variable (class field, global, etc.)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SharedVariable {
    /// Variable name (e.g., "self.count")
    pub name: String,
    /// Variable type
    pub var_type: SharedVarType,
    /// File path
    pub file_path: String,
    /// Line number
    pub line: u32,
    /// Whether the variable is mutable
    pub is_mutable: bool,
}

/// Variable access (read/write at specific location)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VariableAccess {
    /// Variable name
    pub var_name: String,
    /// File path
    pub file_path: String,
    /// Line number
    pub line: u32,
    /// Access type
    pub access_type: AccessType,
    /// Function name
    pub function_name: String,
    /// Whether there's an await before this access
    pub has_await_before: bool,
    /// Whether this access is in a lock region
    pub in_lock_region: bool,
}

/// Await point (potential task interleaving)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AwaitPoint {
    /// File path
    pub file_path: String,
    /// Line number
    pub line: u32,
    /// Await expression (e.g., "await asyncio.sleep(0)")
    pub await_expr: String,
    /// Function name
    pub function_name: String,
}

/// Lock-protected region
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LockRegion {
    /// Lock variable (e.g., "self.lock")
    pub lock_var: String,
    /// File path
    pub file_path: String,
    /// Start line
    pub start_line: u32,
    /// End line
    pub end_line: u32,
    /// Protected variables (if known)
    pub protected_vars: HashSet<String>,
}

impl LockRegion {
    /// Check if a line is within this lock region
    pub fn contains_line(&self, line: u32) -> bool {
        line >= self.start_line && line <= self.end_line
    }

    /// Check if two lines are both within this lock region
    pub fn protects_both(&self, line1: u32, line2: u32) -> bool {
        self.contains_line(line1) && self.contains_line(line2)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_access_type_is_write() {
        assert!(!AccessType::Read.is_write());
        assert!(AccessType::Write.is_write());
        assert!(AccessType::ReadWrite.is_write());
    }

    #[test]
    fn test_race_severity_from_accesses() {
        assert_eq!(
            RaceSeverity::from_accesses(AccessType::Write, AccessType::Write),
            RaceSeverity::Critical
        );
        assert_eq!(
            RaceSeverity::from_accesses(AccessType::Write, AccessType::Read),
            RaceSeverity::High
        );
        assert_eq!(
            RaceSeverity::from_accesses(AccessType::Read, AccessType::Read),
            RaceSeverity::Low
        );
    }

    #[test]
    fn test_lock_region_contains() {
        let region = LockRegion {
            lock_var: "lock".to_string(),
            file_path: "test.py".to_string(),
            start_line: 10,
            end_line: 20,
            protected_vars: HashSet::new(),
        };

        assert!(!region.contains_line(9));
        assert!(region.contains_line(10));
        assert!(region.contains_line(15));
        assert!(region.contains_line(20));
        assert!(!region.contains_line(21));
    }

    #[test]
    fn test_lock_region_protects_both() {
        let region = LockRegion {
            lock_var: "lock".to_string(),
            file_path: "test.py".to_string(),
            start_line: 10,
            end_line: 20,
            protected_vars: HashSet::new(),
        };

        assert!(region.protects_both(12, 15));
        assert!(!region.protects_both(9, 15));
        assert!(!region.protects_both(15, 25));
    }
}
