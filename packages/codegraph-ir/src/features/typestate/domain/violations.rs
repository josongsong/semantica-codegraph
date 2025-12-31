/*
 * Protocol Violations
 *
 * Represents violations of typestate protocols.
 */

use super::{Action, State};
use serde::{Deserialize, Serialize};

/// Protocol violation kind
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ViolationKind {
    /// Use-after-close (e.g., file.read() after file.close())
    UseAfterClose,

    /// Resource leak (e.g., file not closed at function exit)
    ResourceLeak,

    /// Invalid state transition (e.g., lock.acquire() on already locked)
    InvalidTransition,

    /// Protocol violation (e.g., conn.send() before authenticate())
    ProtocolViolation,

    /// Maybe leaked (some paths leak, some don't)
    MaybeLeaked,
}

impl std::fmt::Display for ViolationKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ViolationKind::UseAfterClose => write!(f, "Use-After-Close"),
            ViolationKind::ResourceLeak => write!(f, "Resource Leak"),
            ViolationKind::InvalidTransition => write!(f, "Invalid Transition"),
            ViolationKind::ProtocolViolation => write!(f, "Protocol Violation"),
            ViolationKind::MaybeLeaked => write!(f, "Maybe Leaked"),
        }
    }
}

/// Protocol violation
///
/// Represents a detected violation of a typestate protocol.
///
/// # Example
/// ```ignore
/// let violation = ProtocolViolation {
///     line: 42,
///     kind: ViolationKind::UseAfterClose,
///     variable: "file".to_string(),
///     expected_state: State::new("Open"),
///     actual_state: State::new("Closed"),
///     message: "Cannot read() on closed file".to_string(),
///     action: Some(Action::new("read")),
/// };
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolViolation {
    /// Line number where violation occurs
    pub line: usize,

    /// Violation kind
    pub kind: ViolationKind,

    /// Variable name
    pub variable: String,

    /// Expected state for the action
    pub expected_state: State,

    /// Actual state at the violation point
    pub actual_state: State,

    /// Human-readable message
    pub message: String,

    /// Action that triggered the violation (if applicable)
    pub action: Option<Action>,
}

impl ProtocolViolation {
    /// Create new violation
    pub fn new(
        line: usize,
        kind: ViolationKind,
        variable: impl Into<String>,
        expected_state: State,
        actual_state: State,
        message: impl Into<String>,
    ) -> Self {
        Self {
            line,
            kind,
            variable: variable.into(),
            expected_state,
            actual_state,
            message: message.into(),
            action: None,
        }
    }

    /// Create violation with action
    pub fn with_action(mut self, action: Action) -> Self {
        self.action = Some(action);
        self
    }

    /// Format for display
    pub fn format_message(&self) -> String {
        format!(
            "Line {}: {} on '{}' - {}",
            self.line, self.kind, self.variable, self.message
        )
    }
}

impl std::fmt::Display for ProtocolViolation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.format_message())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_violation_kind_display() {
        assert_eq!(ViolationKind::UseAfterClose.to_string(), "Use-After-Close");
        assert_eq!(ViolationKind::ResourceLeak.to_string(), "Resource Leak");
    }

    #[test]
    fn test_protocol_violation_creation() {
        let violation = ProtocolViolation::new(
            42,
            ViolationKind::UseAfterClose,
            "file",
            State::new("Open"),
            State::new("Closed"),
            "Cannot read() on closed file",
        );

        assert_eq!(violation.line, 42);
        assert_eq!(violation.kind, ViolationKind::UseAfterClose);
        assert_eq!(violation.variable, "file");
        assert_eq!(violation.expected_state, State::new("Open"));
        assert_eq!(violation.actual_state, State::new("Closed"));
    }

    #[test]
    fn test_violation_with_action() {
        let violation = ProtocolViolation::new(
            10,
            ViolationKind::InvalidTransition,
            "lock",
            State::new("Unlocked"),
            State::new("Locked"),
            "Cannot acquire locked lock",
        )
        .with_action(Action::new("acquire"));

        assert!(violation.action.is_some());
        assert_eq!(violation.action.unwrap(), Action::new("acquire"));
    }

    #[test]
    fn test_violation_format() {
        let violation = ProtocolViolation::new(
            15,
            ViolationKind::ResourceLeak,
            "conn",
            State::new("Disconnected"),
            State::new("Connected"),
            "Connection not closed at exit",
        );

        let msg = violation.format_message();
        assert!(msg.contains("Line 15"));
        assert!(msg.contains("Resource Leak"));
        assert!(msg.contains("conn"));
    }
}
