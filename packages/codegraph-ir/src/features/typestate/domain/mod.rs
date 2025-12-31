/*
 * Typestate Domain Models
 *
 * Core domain types for typestate protocol analysis.
 */

mod protocol;
mod violations;

#[cfg(test)]
mod protocol_edge_cases_test;

pub use protocol::{Action, Protocol, State};
pub use violations::{ProtocolViolation, ViolationKind};
