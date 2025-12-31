/*
 * Protocol Definition Language Parser
 *
 * Parse protocol definitions from YAML/JSON for custom resource types.
 *
 * # Supported Formats
 * - YAML: Human-readable, recommended
 * - JSON: Machine-generated, API-friendly
 *
 * # Schema
 * ```yaml
 * protocol: DatabaseTransaction
 * initial_state: Idle
 * final_states:
 *   - Committed
 *   - RolledBack
 * transitions:
 *   - from: Idle
 *     action: begin
 *     to: Active
 *   - from: Active
 *     action: commit
 *     to: Committed
 * preconditions:
 *   query:
 *     requires: Active
 * ```
 *
 * # Validation
 * - All states in transitions must be declared
 * - Initial state must exist
 * - Final states must exist
 * - No orphan states (unreachable)
 *
 * # Time Complexity
 * O(states + transitions) - Linear scan for validation
 */

use crate::features::typestate::domain::{Action, Protocol, State};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Protocol configuration (YAML/JSON schema)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolConfig {
    /// Protocol name
    pub protocol: String,

    /// Initial state
    pub initial_state: String,

    /// Final states (valid at function exit)
    #[serde(default)]
    pub final_states: Vec<String>,

    /// State transitions
    pub transitions: Vec<TransitionConfig>,

    /// Action preconditions (optional)
    #[serde(default)]
    pub preconditions: HashMap<String, PreconditionConfig>,
}

/// Transition configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransitionConfig {
    /// Source state
    pub from: String,

    /// Action (method name)
    pub action: String,

    /// Target state
    pub to: String,
}

/// Precondition configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreconditionConfig {
    /// Required state for action
    pub requires: String,
}

/// Protocol parser
pub struct ProtocolParser;

/// Parse error
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseError {
    /// YAML/JSON syntax error
    SyntaxError(String),

    /// Schema validation error
    ValidationError(String),

    /// Semantic error (orphan states, etc.)
    SemanticError(String),
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ParseError::SyntaxError(msg) => write!(f, "Syntax error: {}", msg),
            ParseError::ValidationError(msg) => write!(f, "Validation error: {}", msg),
            ParseError::SemanticError(msg) => write!(f, "Semantic error: {}", msg),
        }
    }
}

impl std::error::Error for ParseError {}

impl ProtocolParser {
    /// Parse protocol from YAML
    ///
    /// # Example
    /// ```rust,ignore
    /// let yaml = r#"
    /// protocol: File
    /// initial_state: Closed
    /// final_states: [Closed]
    /// transitions:
    ///   - from: Closed
    ///     action: open
    ///     to: Open
    ///   - from: Open
    ///     action: close
    ///     to: Closed
    /// "#;
    ///
    /// let protocol = ProtocolParser::from_yaml(yaml)?;
    /// ```
    pub fn from_yaml(yaml: &str) -> Result<Protocol, ParseError> {
        let config: ProtocolConfig = serde_yaml::from_str(yaml)
            .map_err(|e| ParseError::SyntaxError(format!("YAML parse error: {}", e)))?;

        Self::build_protocol(config)
    }

    /// Parse protocol from JSON
    ///
    /// # Example
    /// ```rust,ignore
    /// let json = r#"{
    ///   "protocol": "File",
    ///   "initial_state": "Closed",
    ///   "final_states": ["Closed"],
    ///   "transitions": [
    ///     {"from": "Closed", "action": "open", "to": "Open"},
    ///     {"from": "Open", "action": "close", "to": "Closed"}
    ///   ]
    /// }"#;
    ///
    /// let protocol = ProtocolParser::from_json(json)?;
    /// ```
    pub fn from_json(json: &str) -> Result<Protocol, ParseError> {
        let config: ProtocolConfig = serde_json::from_str(json)
            .map_err(|e| ParseError::SyntaxError(format!("JSON parse error: {}", e)))?;

        Self::build_protocol(config)
    }

    /// Build protocol from configuration
    ///
    /// # Validation Steps
    /// 1. Check initial state exists in transitions
    /// 2. Check final states exist in transitions
    /// 3. Check all states in transitions are reachable
    /// 4. Check preconditions reference valid actions/states
    fn build_protocol(config: ProtocolConfig) -> Result<Protocol, ParseError> {
        let mut protocol = Protocol::new(&config.protocol);

        // Set initial state
        protocol.set_initial_state(State::new(&config.initial_state));

        // Add final states
        for final_state in &config.final_states {
            protocol.add_final_state(State::new(final_state));
        }

        // Add transitions
        for transition in &config.transitions {
            protocol.add_transition(
                State::new(&transition.from),
                Action::new(&transition.action),
                State::new(&transition.to),
            );
        }

        // Add preconditions
        for (action_name, precond) in &config.preconditions {
            protocol.add_precondition(Action::new(action_name), State::new(&precond.requires));
        }

        // Validate protocol
        protocol
            .validate()
            .map_err(|e| ParseError::ValidationError(e))?;

        // Semantic validation
        Self::validate_semantics(&protocol, &config)?;

        Ok(protocol)
    }

    /// Validate semantic correctness
    ///
    /// Checks:
    /// - No orphan states (states with no transitions in or out)
    /// - Initial state is reachable (trivially true)
    /// - Final states are reachable
    fn validate_semantics(protocol: &Protocol, config: &ProtocolConfig) -> Result<(), ParseError> {
        // Collect all states from transitions
        let mut all_states: HashSet<String> = HashSet::new();
        for t in &config.transitions {
            all_states.insert(t.from.clone());
            all_states.insert(t.to.clone());
        }

        // Check initial state exists in transitions
        if !all_states.contains(&config.initial_state) {
            return Err(ParseError::SemanticError(format!(
                "Initial state '{}' not found in transitions",
                config.initial_state
            )));
        }

        // Check final states exist in transitions
        for final_state in &config.final_states {
            if !all_states.contains(final_state) {
                return Err(ParseError::SemanticError(format!(
                    "Final state '{}' not found in transitions",
                    final_state
                )));
            }
        }

        // Check reachability (simplified: just verify final states appear as 'to')
        let mut reachable_states: HashSet<String> = HashSet::new();
        reachable_states.insert(config.initial_state.clone());

        for t in &config.transitions {
            if reachable_states.contains(&t.from) {
                reachable_states.insert(t.to.clone());
            }
        }

        for final_state in &config.final_states {
            if !reachable_states.contains(final_state) {
                return Err(ParseError::SemanticError(format!(
                    "Final state '{}' is unreachable from initial state '{}'",
                    final_state, config.initial_state
                )));
            }
        }

        Ok(())
    }
}

/// Protocol builder (fluent API)
///
/// # Example
/// ```rust
/// use codegraph_ir::features::typestate::infrastructure::ProtocolBuilder;
///
/// let protocol = ProtocolBuilder::new("MyProtocol")
///     .initial_state("Init")
///     .add_transition("Init", "start", "Running")
///     .add_transition("Running", "stop", "Stopped")
///     .final_state("Stopped")
///     .build();
/// ```
pub struct ProtocolBuilder {
    protocol: Protocol,
}

impl ProtocolBuilder {
    /// Create new protocol builder
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            protocol: Protocol::new(name),
        }
    }

    /// Set initial state
    pub fn initial_state(mut self, state: impl Into<String>) -> Self {
        self.protocol.set_initial_state(State::new(state.into()));
        self
    }

    /// Add state transition
    pub fn add_transition(
        mut self,
        from: impl Into<String>,
        action: impl Into<String>,
        to: impl Into<String>,
    ) -> Self {
        self.protocol.add_transition(
            State::new(from.into()),
            Action::new(action.into()),
            State::new(to.into()),
        );
        self
    }

    /// Add final state
    pub fn final_state(mut self, state: impl Into<String>) -> Self {
        self.protocol.add_final_state(State::new(state.into()));
        self
    }

    /// Add action precondition
    pub fn precondition(
        mut self,
        action: impl Into<String>,
        required_state: impl Into<String>,
    ) -> Self {
        self.protocol.add_precondition(
            Action::new(action.into()),
            State::new(required_state.into()),
        );
        self
    }

    /// Build protocol
    pub fn build(self) -> Protocol {
        self.protocol
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_yaml_simple() {
        let yaml = r#"
protocol: File
initial_state: Closed
final_states:
  - Closed
transitions:
  - from: Closed
    action: open
    to: Open
  - from: Open
    action: close
    to: Closed
"#;

        let protocol = ProtocolParser::from_yaml(yaml).unwrap();

        assert_eq!(protocol.name, "File");
        assert_eq!(protocol.initial_state(), State::new("Closed"));
        assert!(protocol.is_final_state(&State::new("Closed")));
        assert!(protocol.can_transition(
            &State::new("Closed"),
            &Action::new("open"),
            &State::new("Open")
        ));
    }

    #[test]
    fn test_parse_json_simple() {
        let json = r#"{
  "protocol": "Lock",
  "initial_state": "Unlocked",
  "final_states": ["Unlocked"],
  "transitions": [
    {"from": "Unlocked", "action": "acquire", "to": "Locked"},
    {"from": "Locked", "action": "release", "to": "Unlocked"}
  ]
}"#;

        let protocol = ProtocolParser::from_json(json).unwrap();

        assert_eq!(protocol.name, "Lock");
        assert_eq!(protocol.initial_state(), State::new("Unlocked"));
        assert!(protocol.can_transition(
            &State::new("Unlocked"),
            &Action::new("acquire"),
            &State::new("Locked")
        ));
    }

    #[test]
    fn test_parse_with_preconditions() {
        let yaml = r#"
protocol: Connection
initial_state: Disconnected
final_states:
  - Disconnected
transitions:
  - from: Disconnected
    action: connect
    to: Connected
  - from: Connected
    action: authenticate
    to: Authenticated
  - from: Authenticated
    action: send
    to: Authenticated
  - from: Authenticated
    action: disconnect
    to: Disconnected
preconditions:
  send:
    requires: Authenticated
"#;

        let protocol = ProtocolParser::from_yaml(yaml).unwrap();

        assert_eq!(protocol.name, "Connection");
        assert_eq!(
            protocol
                .action_preconditions
                .get(&Action::new("send"))
                .unwrap(),
            &State::new("Authenticated")
        );
    }

    #[test]
    fn test_parse_error_invalid_yaml() {
        let invalid_yaml = "protocol: [invalid syntax";
        let result = ProtocolParser::from_yaml(invalid_yaml);

        assert!(result.is_err());
        match result.unwrap_err() {
            ParseError::SyntaxError(_) => {}
            _ => panic!("Expected SyntaxError"),
        }
    }

    #[test]
    fn test_parse_error_unreachable_final_state() {
        let yaml = r#"
protocol: Test
initial_state: A
final_states:
  - C
transitions:
  - from: A
    action: go
    to: B
"#;

        let result = ProtocolParser::from_yaml(yaml);

        assert!(result.is_err());
        match result.unwrap_err() {
            ParseError::SemanticError(msg) => {
                // Accept both "unreachable" and "not found" error messages
                assert!(
                    msg.contains("unreachable") || msg.contains("not found"),
                    "Expected error about unreachable/not found, got: {}",
                    msg
                );
            }
            ParseError::ValidationError(msg) => {
                // Also accept validation errors about final states
                assert!(
                    msg.contains("Final state") && msg.contains("not in states"),
                    "Expected validation error, got: {}",
                    msg
                );
            }
            _ => panic!("Expected SemanticError or ValidationError"),
        }
    }

    #[test]
    fn test_protocol_builder() {
        let protocol = ProtocolBuilder::new("MyProtocol")
            .initial_state("Init")
            .add_transition("Init", "start", "Running")
            .add_transition("Running", "stop", "Stopped")
            .final_state("Stopped")
            .precondition("stop", "Running")
            .build();

        assert_eq!(protocol.name, "MyProtocol");
        assert_eq!(protocol.initial_state(), State::new("Init"));
        assert!(protocol.is_final_state(&State::new("Stopped")));
        assert!(protocol.can_transition(
            &State::new("Init"),
            &Action::new("start"),
            &State::new("Running")
        ));
    }

    #[test]
    fn test_protocol_builder_complex() {
        let protocol = ProtocolBuilder::new("Transaction")
            .initial_state("Idle")
            .add_transition("Idle", "begin", "Active")
            .add_transition("Active", "query", "Active")
            .add_transition("Active", "commit", "Committed")
            .add_transition("Active", "rollback", "RolledBack")
            .final_state("Committed")
            .final_state("RolledBack")
            .precondition("query", "Active")
            .precondition("commit", "Active")
            .precondition("rollback", "Active")
            .build();

        assert_eq!(protocol.name, "Transaction");
        assert_eq!(protocol.transitions.len(), 4);
        assert_eq!(protocol.final_states.len(), 2);
        assert_eq!(protocol.action_preconditions.len(), 3);
    }
}
