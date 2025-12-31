//! Abstract Heap Location
//!
//! Represents allocation sites in the program.
//! Flow-insensitive abstraction where each `new T()` maps to a unique location.

use serde::{Deserialize, Serialize};
use std::fmt;

/// Unique identifier for abstract locations
pub type LocationId = u32;

/// Abstract representation of a heap allocation site
///
/// In points-to analysis, concrete heap addresses are abstracted to allocation sites.
/// This provides a finite (and typically small) set of abstract locations.
///
/// # Example
/// ```
/// // Source code:
/// // Line 10: x = new A()
/// // Line 20: y = new A()
/// // Line 30: z = new B()
///
/// // Abstract locations:
/// // alloc:10:A - First allocation of A
/// // alloc:20:A - Second allocation of A (different site, different location)
/// // alloc:30:B - Allocation of B
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AbstractLocation {
    /// Unique numeric ID for efficient set operations
    pub id: LocationId,

    /// Human-readable allocation site identifier (e.g., "alloc:10:MyClass")
    pub allocation_site: String,

    /// Type information (if available)
    pub type_info: Option<String>,

    /// Source file path
    pub file_path: Option<String>,

    /// Line number in source
    pub line: Option<u32>,

    /// Whether this is a summary node (represents multiple concrete locations)
    pub is_summary: bool,
}

impl AbstractLocation {
    /// Create a new abstract location
    #[inline]
    pub fn new(id: LocationId, allocation_site: impl Into<String>) -> Self {
        Self {
            id,
            allocation_site: allocation_site.into(),
            type_info: None,
            file_path: None,
            line: None,
            is_summary: false,
        }
    }

    /// Create with type information
    #[inline]
    pub fn with_type(mut self, type_info: impl Into<String>) -> Self {
        self.type_info = Some(type_info.into());
        self
    }

    /// Create with source location
    #[inline]
    pub fn with_source(mut self, file_path: impl Into<String>, line: u32) -> Self {
        self.file_path = Some(file_path.into());
        self.line = Some(line);
        self
    }

    /// Mark as summary node
    #[inline]
    pub fn as_summary(mut self) -> Self {
        self.is_summary = true;
        self
    }

    /// Create a special "null" location
    #[inline]
    pub fn null() -> Self {
        Self::new(0, "null").as_summary()
    }

    /// Create a special "unknown" location (conservative)
    #[inline]
    pub fn unknown() -> Self {
        Self::new(u32::MAX, "unknown").as_summary()
    }

    /// Check if this is the null location
    #[inline]
    pub fn is_null(&self) -> bool {
        self.id == 0 && self.allocation_site == "null"
    }

    /// Check if this is the unknown location
    #[inline]
    pub fn is_unknown(&self) -> bool {
        self.id == u32::MAX && self.allocation_site == "unknown"
    }
}

impl fmt::Display for AbstractLocation {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(ref type_info) = self.type_info {
            write!(f, "{}:{}", self.allocation_site, type_info)
        } else {
            write!(f, "{}", self.allocation_site)
        }
    }
}

/// Factory for creating abstract locations with unique IDs
#[derive(Debug, Default)]
pub struct LocationFactory {
    next_id: LocationId,
}

impl LocationFactory {
    pub fn new() -> Self {
        Self { next_id: 1 } // 0 is reserved for null
    }

    /// Create a new location with auto-generated ID
    #[inline]
    pub fn create(&mut self, allocation_site: impl Into<String>) -> AbstractLocation {
        let id = self.next_id;
        self.next_id += 1;
        AbstractLocation::new(id, allocation_site)
    }

    /// Create location from source position
    pub fn create_from_source(
        &mut self,
        file_path: impl Into<String>,
        line: u32,
        type_info: Option<&str>,
    ) -> AbstractLocation {
        let file = file_path.into();
        let site = format!("alloc:{}:{}", line, type_info.unwrap_or("?"));
        let mut loc = self.create(site);
        loc.file_path = Some(file);
        loc.line = Some(line);
        if let Some(t) = type_info {
            loc.type_info = Some(t.to_string());
        }
        loc
    }

    /// Current count of created locations
    #[inline]
    pub fn count(&self) -> u32 {
        self.next_id - 1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_location_creation() {
        let loc = AbstractLocation::new(1, "alloc:10:Foo");
        assert_eq!(loc.id, 1);
        assert_eq!(loc.allocation_site, "alloc:10:Foo");
        assert!(!loc.is_summary);
    }

    #[test]
    fn test_location_with_type() {
        let loc = AbstractLocation::new(1, "alloc:10").with_type("MyClass");
        assert_eq!(loc.type_info, Some("MyClass".to_string()));
    }

    #[test]
    fn test_special_locations() {
        let null = AbstractLocation::null();
        assert!(null.is_null());
        assert!(!null.is_unknown());

        let unknown = AbstractLocation::unknown();
        assert!(unknown.is_unknown());
        assert!(!unknown.is_null());
    }

    #[test]
    fn test_factory() {
        let mut factory = LocationFactory::new();
        let loc1 = factory.create("alloc:1");
        let loc2 = factory.create("alloc:2");

        assert_eq!(loc1.id, 1);
        assert_eq!(loc2.id, 2);
        assert_eq!(factory.count(), 2);
    }
}
