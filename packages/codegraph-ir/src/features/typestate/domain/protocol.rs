/*
 * Protocol Definition
 *
 * Defines valid state transitions for resource lifecycle.
 *
 * # Example: File Protocol
 * ```
 * States: {Closed, Open}
 * Transitions:
 *   Closed --open()--> Open
 *   Open --read()--> Open
 *   Open --write()--> Open
 *   Open --close()--> Closed
 * ```
 *
 * # Time Complexity
 * - add_transition: O(1)
 * - can_transition: O(1) (hash lookup)
 * - next_state: O(1)
 *
 * # Space Complexity
 * - O(states + transitions)
 */

use rustc_hash::FxHashMap;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// State in typestate protocol
///
/// Represents the current state of a resource (e.g., "Open", "Closed").
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct State {
    pub name: String,
}

impl State {
    /// Create new state
    pub fn new(name: impl Into<String>) -> Self {
        Self { name: name.into() }
    }

    /// Create state from &str (convenience)
    pub fn from(name: &str) -> Self {
        Self::new(name)
    }
}

impl std::fmt::Display for State {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.name)
    }
}

/// Action that triggers state transition
///
/// Represents a method call on a resource (e.g., "open", "read", "close").
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Action {
    pub method_name: String,
}

impl Action {
    /// Create new action
    pub fn new(method: impl Into<String>) -> Self {
        Self {
            method_name: method.into(),
        }
    }

    /// Create action from &str (convenience)
    pub fn from(method: &str) -> Self {
        Self::new(method)
    }
}

impl std::fmt::Display for Action {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.method_name)
    }
}

/// Typestate protocol definition
///
/// Defines valid state transitions for resource lifecycle.
///
/// # Example
/// ```ignore
/// let mut protocol = Protocol::new("File");
///
/// let closed = State::new("Closed");
/// let open = State::new("Open");
///
/// protocol.initial_state = closed.clone();
/// protocol.final_states.insert(closed.clone());
///
/// protocol.add_transition(closed.clone(), Action::new("open"), open.clone());
/// protocol.add_transition(open.clone(), Action::new("close"), closed.clone());
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Protocol {
    /// Protocol name (e.g., "File", "Lock", "Connection")
    pub name: String,

    /// All possible states
    pub states: HashSet<State>,

    /// Initial state (e.g., "Closed", "Unlocked")
    pub initial_state: State,

    /// Final states (valid states at function exit)
    /// E.g., File: {Closed}, Lock: {Unlocked}
    pub final_states: HashSet<State>,

    /// State transitions: (from_state, action) → to_state
    pub transitions: FxHashMap<(State, Action), State>,

    /// Actions that require specific states
    /// E.g., read() requires Open state
    pub action_preconditions: HashMap<Action, State>,
}

impl Protocol {
    /// Create new protocol
    ///
    /// # Example
    /// ```ignore
    /// let protocol = Protocol::new("MyResource");
    /// assert_eq!(protocol.name, "MyResource");
    /// ```
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            states: HashSet::new(),
            initial_state: State::new("Initial"),
            final_states: HashSet::new(),
            transitions: FxHashMap::default(),
            action_preconditions: HashMap::new(),
        }
    }

    /// Add state to protocol
    pub fn add_state(&mut self, state: State) {
        self.states.insert(state);
    }

    /// Add state transition
    ///
    /// # Example
    /// ```ignore
    /// protocol.add_transition(
    ///     State::new("Closed"),
    ///     Action::new("open"),
    ///     State::new("Open")
    /// );
    /// ```
    ///
    /// # Time Complexity
    /// O(1) - Hash map insertion
    pub fn add_transition(&mut self, from: State, action: Action, to: State) {
        self.transitions.insert((from.clone(), action), to.clone());
        self.states.insert(from);
        self.states.insert(to);
    }

    /// Check if transition is valid
    ///
    /// # Example
    /// ```ignore
    /// assert!(protocol.can_transition(
    ///     &State::new("Closed"),
    ///     &Action::new("open"),
    ///     &State::new("Open")
    /// ));
    /// ```
    ///
    /// # Time Complexity
    /// O(1) - Hash map lookup
    pub fn can_transition(&self, from: &State, action: &Action, to: &State) -> bool {
        self.transitions.get(&(from.clone(), action.clone())) == Some(to)
    }

    /// Get next state after action (if valid)
    ///
    /// # Returns
    /// - Some(state) if transition is valid
    /// - None if transition is invalid
    ///
    /// # Time Complexity
    /// O(1) - Hash map lookup
    pub fn next_state(&self, from: &State, action: &Action) -> Option<State> {
        self.transitions
            .get(&(from.clone(), action.clone()))
            .cloned()
    }

    /// Check if state is a valid final state
    ///
    /// Used to detect resource leaks at function exit.
    ///
    /// # Example
    /// ```ignore
    /// // File must be Closed at exit
    /// assert!(protocol.is_final_state(&State::new("Closed")));
    /// assert!(!protocol.is_final_state(&State::new("Open")));
    /// ```
    pub fn is_final_state(&self, state: &State) -> bool {
        self.final_states.contains(state)
    }

    /// Get initial state
    pub fn initial_state(&self) -> State {
        self.initial_state.clone()
    }

    /// Add final state
    pub fn add_final_state(&mut self, state: State) {
        self.states.insert(state.clone());
        self.final_states.insert(state);
    }

    /// Set initial state
    pub fn set_initial_state(&mut self, state: State) {
        self.states.insert(state.clone());
        self.initial_state = state;
    }

    /// Add action precondition
    ///
    /// Specifies required state for an action.
    ///
    /// # Example
    /// ```ignore
    /// // read() requires Open state
    /// protocol.add_precondition(Action::new("read"), State::new("Open"));
    /// ```
    pub fn add_precondition(&mut self, action: Action, required_state: State) {
        self.action_preconditions.insert(action, required_state);
    }

    /// Get all possible actions from a state
    ///
    /// # Time Complexity
    /// O(transitions) - Linear scan of transitions
    pub fn available_actions(&self, from: &State) -> Vec<Action> {
        self.transitions
            .keys()
            .filter_map(|(state, action)| {
                if state == from {
                    Some(action.clone())
                } else {
                    None
                }
            })
            .collect()
    }

    /// Validate protocol definition
    ///
    /// Checks:
    /// - Initial state exists in states
    /// - All final states exist in states
    /// - All transitions reference valid states
    pub fn validate(&self) -> Result<(), String> {
        // Check initial state
        if !self.states.contains(&self.initial_state) {
            return Err(format!(
                "Initial state '{}' not in states",
                self.initial_state
            ));
        }

        // Check final states
        for state in &self.final_states {
            if !self.states.contains(state) {
                return Err(format!("Final state '{}' not in states", state));
            }
        }

        // Check transitions
        for ((from, _action), to) in &self.transitions {
            if !self.states.contains(from) {
                return Err(format!("Transition from state '{}' not in states", from));
            }
            if !self.states.contains(to) {
                return Err(format!("Transition to state '{}' not in states", to));
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_state_creation() {
        let state = State::new("Open");
        assert_eq!(state.name, "Open");

        let state2 = State::from("Closed");
        assert_eq!(state2.name, "Closed");
    }

    #[test]
    fn test_action_creation() {
        let action = Action::new("read");
        assert_eq!(action.method_name, "read");

        let action2 = Action::from("write");
        assert_eq!(action2.method_name, "write");
    }

    #[test]
    fn test_protocol_basic() {
        let protocol = Protocol::new("TestProtocol");
        assert_eq!(protocol.name, "TestProtocol");
        assert_eq!(protocol.initial_state.name, "Initial");
    }

    #[test]
    fn test_add_transition() {
        let mut protocol = Protocol::new("Test");

        let s1 = State::new("S1");
        let s2 = State::new("S2");
        let action = Action::new("transition");

        protocol.add_transition(s1.clone(), action.clone(), s2.clone());

        assert!(protocol.can_transition(&s1, &action, &s2));
        assert!(!protocol.can_transition(&s2, &action, &s1));
    }

    #[test]
    fn test_next_state() {
        let mut protocol = Protocol::new("Test");

        let s1 = State::new("S1");
        let s2 = State::new("S2");
        let action = Action::new("go");

        protocol.add_transition(s1.clone(), action.clone(), s2.clone());

        assert_eq!(protocol.next_state(&s1, &action), Some(s2.clone()));
        assert_eq!(protocol.next_state(&s2, &action), None);
    }

    #[test]
    fn test_final_states() {
        let mut protocol = Protocol::new("Test");

        let closed = State::new("Closed");
        protocol.add_final_state(closed.clone());

        assert!(protocol.is_final_state(&closed));
        assert!(!protocol.is_final_state(&State::new("Open")));
    }

    #[test]
    fn test_available_actions() {
        let mut protocol = Protocol::new("Test");

        let s1 = State::new("S1");
        let s2 = State::new("S2");

        protocol.add_transition(s1.clone(), Action::new("a1"), s2.clone());
        protocol.add_transition(s1.clone(), Action::new("a2"), s2.clone());

        let actions = protocol.available_actions(&s1);
        assert_eq!(actions.len(), 2);
        assert!(actions.contains(&Action::new("a1")));
        assert!(actions.contains(&Action::new("a2")));
    }

    #[test]
    fn test_validate_protocol() {
        let mut protocol = Protocol::new("Test");

        let s1 = State::new("S1");
        let s2 = State::new("S2");

        protocol.set_initial_state(s1.clone());
        protocol.add_final_state(s2.clone());
        protocol.add_transition(s1.clone(), Action::new("go"), s2.clone());

        assert!(protocol.validate().is_ok());
    }
}
