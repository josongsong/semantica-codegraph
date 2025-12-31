/*
 * Typestate Ports
 *
 * Interfaces for external integration.
 */

use crate::features::typestate::domain::Protocol;

/// Protocol definition trait
///
/// Implement this trait to define custom protocols.
pub trait ProtocolDefinition {
    /// Define the protocol
    fn define() -> Protocol;
}
