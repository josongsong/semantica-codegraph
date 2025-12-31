/*
 * Typestate Protocol Analysis
 *
 * Detects resource lifecycle violations:
 * - Use-after-close bugs
 * - Resource leaks (file/lock/connection not released)
 * - Protocol violations (e.g., send before authenticate)
 *
 * Architecture:
 * - Domain: Protocol, State, Action, Violation models
 * - Application: TypestateAnalyzer (CFG-based dataflow)
 * - Infrastructure: Built-in protocols, YAML parser
 * - Ports: ProtocolDefinition trait
 *
 * Algorithm:
 * - Forward dataflow analysis on CFG
 * - Track state per variable per program point
 * - Merge states at join points (may-analysis)
 *
 * Performance Target:
 * - Time: O(CFG nodes × variables × states)
 * - Space: O(variables × program points)
 *
 * References:
 * - RFC-003: Typestate Protocol Analysis
 * - Strom & Yellin (1993) "Typestate"
 * - DeLine & Fähndrich (2004) "Enforcing High-Level Protocols"
 */

pub mod application;
pub mod domain;
pub mod infrastructure;
pub mod ports;

// Re-export main types
pub use domain::{Action, Protocol, ProtocolViolation, State, ViolationKind};

pub use application::{TypestateAnalyzer, TypestateConfig, TypestateResult};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{ConnectionProtocol, FileProtocol, LockProtocol};

pub use ports::ProtocolDefinition;
