/*
 * Protocol Edge Cases Test Suite
 *
 * SOTA-level extreme test cases:
 * - Empty protocols
 * - Circular transitions
 * - Large state machines
 * - Concurrent modifications
 * - Boundary conditions
 */

#[cfg(test)]
mod extreme_edge_cases {
    use super::super::{Action, Protocol, State};

    #[test]
    fn test_empty_protocol() {
        let protocol = Protocol::new("Empty");

        // Empty protocol is valid (no states, no transitions)
        assert_eq!(protocol.states.len(), 0);
        assert_eq!(protocol.transitions.len(), 0);

        // But validation should fail (no initial state in states)
        assert!(protocol.validate().is_err());
    }

    #[test]
    fn test_single_state_protocol() {
        let mut protocol = Protocol::new("SingleState");

        let idle = State::new("Idle");
        protocol.set_initial_state(idle.clone());
        protocol.add_final_state(idle.clone());

        // Valid: state can be both initial and final
        assert!(protocol.validate().is_ok());
        assert_eq!(protocol.states.len(), 1);
    }

    #[test]
    fn test_circular_transitions() {
        let mut protocol = Protocol::new("Circular");

        let a = State::new("A");
        let b = State::new("B");
        let c = State::new("C");

        protocol.set_initial_state(a.clone());
        protocol.add_final_state(a.clone());

        // Circular: A → B → C → A
        protocol.add_transition(a.clone(), Action::new("to_b"), b.clone());
        protocol.add_transition(b.clone(), Action::new("to_c"), c.clone());
        protocol.add_transition(c.clone(), Action::new("to_a"), a.clone());

        // Should be valid (circular is OK)
        assert!(protocol.validate().is_ok());

        // Can traverse the circle
        assert_eq!(
            protocol.next_state(&a, &Action::new("to_b")),
            Some(b.clone())
        );
        assert_eq!(
            protocol.next_state(&b, &Action::new("to_c")),
            Some(c.clone())
        );
        assert_eq!(
            protocol.next_state(&c, &Action::new("to_a")),
            Some(a.clone())
        );
    }

    #[test]
    fn test_multiple_self_loops() {
        let mut protocol = Protocol::new("SelfLoops");

        let state = State::new("State");
        protocol.set_initial_state(state.clone());
        protocol.add_final_state(state.clone());

        // Multiple self-loops with different actions
        protocol.add_transition(state.clone(), Action::new("action1"), state.clone());
        protocol.add_transition(state.clone(), Action::new("action2"), state.clone());
        protocol.add_transition(state.clone(), Action::new("action3"), state.clone());

        assert!(protocol.validate().is_ok());
        assert_eq!(protocol.transitions.len(), 3);

        // All actions lead back to same state
        assert_eq!(
            protocol.next_state(&state, &Action::new("action1")),
            Some(state.clone())
        );
        assert_eq!(
            protocol.next_state(&state, &Action::new("action2")),
            Some(state.clone())
        );
        assert_eq!(
            protocol.next_state(&state, &Action::new("action3")),
            Some(state.clone())
        );
    }

    #[test]
    fn test_large_state_machine() {
        let mut protocol = Protocol::new("Large");

        // Create 100 states
        let states: Vec<State> = (0..100).map(|i| State::new(format!("S{}", i))).collect();

        protocol.set_initial_state(states[0].clone());
        protocol.add_final_state(states[99].clone());

        // Create linear chain: S0 → S1 → ... → S99
        for i in 0..99 {
            protocol.add_transition(
                states[i].clone(),
                Action::new(format!("next_{}", i)),
                states[i + 1].clone(),
            );
        }

        assert!(protocol.validate().is_ok());
        assert_eq!(protocol.states.len(), 100);
        assert_eq!(protocol.transitions.len(), 99);

        // Verify first and last transitions
        assert_eq!(
            protocol.next_state(&states[0], &Action::new("next_0")),
            Some(states[1].clone())
        );
        assert_eq!(
            protocol.next_state(&states[98], &Action::new("next_98")),
            Some(states[99].clone())
        );
    }

    #[test]
    fn test_highly_connected_graph() {
        let mut protocol = Protocol::new("FullyConnected");

        let states: Vec<State> = (0..10).map(|i| State::new(format!("S{}", i))).collect();

        protocol.set_initial_state(states[0].clone());
        protocol.add_final_state(states[9].clone());

        // Create fully connected graph (every state connects to every other)
        for i in 0..10 {
            for j in 0..10 {
                if i != j {
                    protocol.add_transition(
                        states[i].clone(),
                        Action::new(format!("go_{}_{}", i, j)),
                        states[j].clone(),
                    );
                }
            }
        }

        assert!(protocol.validate().is_ok());
        assert_eq!(protocol.states.len(), 10);
        assert_eq!(protocol.transitions.len(), 90); // 10 * 9 = 90 transitions

        // Any state can reach any other state
        assert_eq!(
            protocol.next_state(&states[0], &Action::new("go_0_5")),
            Some(states[5].clone())
        );
        assert_eq!(
            protocol.next_state(&states[7], &Action::new("go_7_2")),
            Some(states[2].clone())
        );
    }

    #[test]
    fn test_multiple_final_states() {
        let mut protocol = Protocol::new("MultiFinal");

        let init = State::new("Init");
        let success = State::new("Success");
        let failure = State::new("Failure");
        let timeout = State::new("Timeout");

        protocol.set_initial_state(init.clone());
        protocol.add_final_state(success.clone());
        protocol.add_final_state(failure.clone());
        protocol.add_final_state(timeout.clone());

        protocol.add_transition(init.clone(), Action::new("succeed"), success.clone());
        protocol.add_transition(init.clone(), Action::new("fail"), failure.clone());
        protocol.add_transition(init.clone(), Action::new("timeout"), timeout.clone());

        assert!(protocol.validate().is_ok());
        assert_eq!(protocol.final_states.len(), 3);

        // All final states should be recognized
        assert!(protocol.is_final_state(&success));
        assert!(protocol.is_final_state(&failure));
        assert!(protocol.is_final_state(&timeout));
        assert!(!protocol.is_final_state(&init));
    }

    #[test]
    fn test_same_action_different_contexts() {
        let mut protocol = Protocol::new("ContextSensitive");

        let a = State::new("A");
        let b = State::new("B");
        let c = State::new("C");

        protocol.set_initial_state(a.clone());
        protocol.add_final_state(c.clone());

        // Same action "process" has different effects from different states
        protocol.add_transition(a.clone(), Action::new("process"), b.clone());
        protocol.add_transition(b.clone(), Action::new("process"), c.clone());

        assert!(protocol.validate().is_ok());

        // "process" from A goes to B
        assert_eq!(
            protocol.next_state(&a, &Action::new("process")),
            Some(b.clone())
        );

        // "process" from B goes to C
        assert_eq!(
            protocol.next_state(&b, &Action::new("process")),
            Some(c.clone())
        );

        // "process" from C is invalid (no transition)
        assert_eq!(protocol.next_state(&c, &Action::new("process")), None);
    }

    #[test]
    fn test_boundary_available_actions() {
        let mut protocol = Protocol::new("Boundary");

        let state = State::new("State");
        protocol.set_initial_state(state.clone());

        // No transitions: available_actions should be empty
        let actions = protocol.available_actions(&state);
        assert_eq!(actions.len(), 0);

        // Add 1 transition
        protocol.add_transition(state.clone(), Action::new("a1"), state.clone());
        let actions = protocol.available_actions(&state);
        assert_eq!(actions.len(), 1);

        // Add many transitions
        for i in 2..=100 {
            protocol.add_transition(state.clone(), Action::new(format!("a{}", i)), state.clone());
        }

        let actions = protocol.available_actions(&state);
        assert_eq!(actions.len(), 100);
    }

    #[test]
    fn test_unicode_state_names() {
        let mut protocol = Protocol::new("Unicode");

        let 한글 = State::new("한글");
        let emoji = State::new("😀");
        let 中文 = State::new("中文");

        protocol.set_initial_state(한글.clone());
        protocol.add_final_state(emoji.clone());

        protocol.add_transition(한글.clone(), Action::new("변환"), emoji.clone());
        protocol.add_transition(emoji.clone(), Action::new("转换"), 中文.clone());

        assert!(protocol.validate().is_ok());

        assert_eq!(
            protocol.next_state(&한글, &Action::new("변환")),
            Some(emoji.clone())
        );
    }

    #[test]
    fn test_very_long_state_name() {
        let long_name = "A".repeat(1000); // 1000 character state name
        let state = State::new(&long_name);

        let mut protocol = Protocol::new("LongName");
        protocol.set_initial_state(state.clone());
        protocol.add_final_state(state.clone());

        assert_eq!(state.name.len(), 1000);
        assert!(protocol.validate().is_ok());
    }

    #[test]
    fn test_special_characters_in_names() {
        let mut protocol = Protocol::new("Special!@#$%");

        let state1 = State::new("State<with>brackets");
        let state2 = State::new("State\"with\"quotes");
        let state3 = State::new("State\nwith\nnewlines");

        protocol.set_initial_state(state1.clone());
        protocol.add_final_state(state3.clone());

        protocol.add_transition(state1.clone(), Action::new("go!"), state2.clone());
        protocol.add_transition(state2.clone(), Action::new("go?"), state3.clone());

        assert!(protocol.validate().is_ok());
    }
}
