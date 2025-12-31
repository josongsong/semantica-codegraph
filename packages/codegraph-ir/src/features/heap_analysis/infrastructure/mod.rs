//! Heap Analysis Infrastructure - Port Implementations (Adapters)
//!
//! This module contains the concrete implementations of port interfaces.
//! Infrastructure code depends on ports, not the other way around.
//!
//! ## Hexagonal Architecture
//! - **Adapters**: Implement port interfaces (this module)
//! - **Primary Adapters**: Drive the application (analyzers)
//! - **Secondary Adapters**: Driven by application (storage, external services)
//!
//! ## SOLID Compliance
//! - **D**: Implements port traits, application depends on traits
//! - **O**: Each adapter can be replaced without affecting others
//!
//! ## Module Structure
//! ```text
//! infrastructure/
//! ├── memory_checkers/      # MemoryCheckerPort implementations
//! │   ├── null_checker.rs
//! │   ├── uaf_checker.rs
//! │   ├── double_free_checker.rs
//! │   ├── buffer_overflow_checker.rs
//! │   └── spatial_checker.rs
//! ├── escape_analyzer.rs    # EscapeAnalyzerPort implementation
//! ├── ownership_tracker.rs  # OwnershipAnalyzerPort implementation
//! ├── security_analyzer.rs  # SecurityAnalyzerPort implementation
//! ├── symbolic_heap.rs      # SymbolicHeapPort implementation
//! └── separation_logic.rs   # SeparationLogicPort implementation
//! ```

// Re-export existing infrastructure implementations
// These will be moved to subdirectories as the codebase evolves

pub mod adapters;

pub use adapters::*;
