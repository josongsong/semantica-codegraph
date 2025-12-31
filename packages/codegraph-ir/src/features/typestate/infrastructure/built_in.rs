/*
 * Built-in Protocols
 *
 * Standard protocol definitions for common resources:
 * - FileProtocol: File open/close lifecycle
 * - LockProtocol: Lock acquire/release lifecycle
 * - ConnectionProtocol: Network connection lifecycle
 *
 * These protocols are used out-of-the-box without configuration.
 */

use crate::features::typestate::domain::{Action, Protocol, State};

/// File protocol
///
/// States: Closed → Open → Closed
///
/// Transitions:
/// - Closed --open()--> Open
/// - Open --read()--> Open
/// - Open --write()--> Open
/// - Open --close()--> Closed
///
/// Final states: {Closed}
///
/// Violations:
/// - Use-after-close: read()/write() on Closed file
/// - Resource leak: File not Closed at function exit
pub struct FileProtocol;

impl FileProtocol {
    /// Define file protocol
    ///
    /// # Example
    /// ```ignore
    /// let protocol = FileProtocol::define();
    /// assert_eq!(protocol.initial_state(), State::new("Closed"));
    /// assert!(protocol.can_transition(
    ///     &State::new("Closed"),
    ///     &Action::new("open"),
    ///     &State::new("Open")
    /// ));
    /// ```
    pub fn define() -> Protocol {
        let mut protocol = Protocol::new("File");

        let closed = State::new("Closed");
        let open = State::new("Open");

        protocol.set_initial_state(closed.clone());
        protocol.add_final_state(closed.clone());

        // Transitions
        protocol.add_transition(closed.clone(), Action::new("open"), open.clone());
        protocol.add_transition(open.clone(), Action::new("read"), open.clone());
        protocol.add_transition(open.clone(), Action::new("write"), open.clone());
        protocol.add_transition(open.clone(), Action::new("readline"), open.clone());
        protocol.add_transition(open.clone(), Action::new("readlines"), open.clone());
        protocol.add_transition(open.clone(), Action::new("writelines"), open.clone());
        protocol.add_transition(open.clone(), Action::new("seek"), open.clone());
        protocol.add_transition(open.clone(), Action::new("tell"), open.clone());
        protocol.add_transition(open.clone(), Action::new("flush"), open.clone());
        protocol.add_transition(open.clone(), Action::new("close"), closed.clone());

        // Preconditions
        protocol.add_precondition(Action::new("read"), open.clone());
        protocol.add_precondition(Action::new("write"), open.clone());
        protocol.add_precondition(Action::new("readline"), open.clone());
        protocol.add_precondition(Action::new("readlines"), open.clone());
        protocol.add_precondition(Action::new("writelines"), open.clone());
        protocol.add_precondition(Action::new("seek"), open.clone());
        protocol.add_precondition(Action::new("tell"), open.clone());
        protocol.add_precondition(Action::new("flush"), open.clone());

        protocol
    }
}

/// Lock protocol
///
/// States: Unlocked ⇄ Locked
///
/// Transitions:
/// - Unlocked --acquire()--> Locked
/// - Locked --release()--> Unlocked
///
/// Final states: {Unlocked}
///
/// Violations:
/// - Double acquire: acquire() on Locked lock (deadlock risk)
/// - Double release: release() on Unlocked lock
/// - Resource leak: Lock not Unlocked at function exit
pub struct LockProtocol;

impl LockProtocol {
    /// Define lock protocol
    ///
    /// # Example
    /// ```ignore
    /// let protocol = LockProtocol::define();
    /// assert_eq!(protocol.initial_state(), State::new("Unlocked"));
    /// assert!(protocol.can_transition(
    ///     &State::new("Unlocked"),
    ///     &Action::new("acquire"),
    ///     &State::new("Locked")
    /// ));
    /// ```
    pub fn define() -> Protocol {
        let mut protocol = Protocol::new("Lock");

        let unlocked = State::new("Unlocked");
        let locked = State::new("Locked");

        protocol.set_initial_state(unlocked.clone());
        protocol.add_final_state(unlocked.clone()); // Must release before exit

        // Transitions
        protocol.add_transition(unlocked.clone(), Action::new("acquire"), locked.clone());
        protocol.add_transition(locked.clone(), Action::new("release"), unlocked.clone());
        protocol.add_transition(locked.clone(), Action::new("__enter__"), locked.clone()); // Python context manager
        protocol.add_transition(locked.clone(), Action::new("__exit__"), unlocked.clone()); // Python context manager

        // Preconditions
        protocol.add_precondition(Action::new("release"), locked.clone());

        protocol
    }
}

/// Connection protocol
///
/// States: Disconnected → Connected → Authenticated → Disconnected
///
/// Transitions:
/// - Disconnected --connect()--> Connected
/// - Connected --authenticate()--> Authenticated
/// - Authenticated --send()--> Authenticated
/// - Authenticated --receive()--> Authenticated
/// - Authenticated --disconnect()--> Disconnected
/// - Connected --disconnect()--> Disconnected
///
/// Final states: {Disconnected}
///
/// Violations:
/// - Protocol violation: send()/receive() before authenticate()
/// - Resource leak: Connection not Disconnected at function exit
pub struct ConnectionProtocol;

impl ConnectionProtocol {
    /// Define connection protocol
    ///
    /// # Example
    /// ```ignore
    /// let protocol = ConnectionProtocol::define();
    /// assert_eq!(protocol.initial_state(), State::new("Disconnected"));
    /// assert!(protocol.can_transition(
    ///     &State::new("Connected"),
    ///     &Action::new("authenticate"),
    ///     &State::new("Authenticated")
    /// ));
    /// ```
    pub fn define() -> Protocol {
        let mut protocol = Protocol::new("Connection");

        let disconnected = State::new("Disconnected");
        let connected = State::new("Connected");
        let authenticated = State::new("Authenticated");

        protocol.set_initial_state(disconnected.clone());
        protocol.add_final_state(disconnected.clone());

        // Transitions
        protocol.add_transition(
            disconnected.clone(),
            Action::new("connect"),
            connected.clone(),
        );
        protocol.add_transition(
            connected.clone(),
            Action::new("authenticate"),
            authenticated.clone(),
        );
        protocol.add_transition(
            authenticated.clone(),
            Action::new("send"),
            authenticated.clone(),
        );
        protocol.add_transition(
            authenticated.clone(),
            Action::new("receive"),
            authenticated.clone(),
        );
        protocol.add_transition(
            authenticated.clone(),
            Action::new("query"),
            authenticated.clone(),
        );
        protocol.add_transition(
            authenticated.clone(),
            Action::new("execute"),
            authenticated.clone(),
        );
        protocol.add_transition(
            authenticated.clone(),
            Action::new("disconnect"),
            disconnected.clone(),
        );
        protocol.add_transition(
            connected.clone(),
            Action::new("disconnect"),
            disconnected.clone(),
        );

        // Preconditions
        protocol.add_precondition(Action::new("send"), authenticated.clone());
        protocol.add_precondition(Action::new("receive"), authenticated.clone());
        protocol.add_precondition(Action::new("query"), authenticated.clone());
        protocol.add_precondition(Action::new("execute"), authenticated.clone());

        protocol
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_protocol_definition() {
        let protocol = FileProtocol::define();

        assert_eq!(protocol.name, "File");
        assert_eq!(protocol.initial_state(), State::new("Closed"));
        assert!(protocol.is_final_state(&State::new("Closed")));
        assert!(!protocol.is_final_state(&State::new("Open")));
    }

    #[test]
    fn test_file_protocol_transitions() {
        let protocol = FileProtocol::define();

        let closed = State::new("Closed");
        let open = State::new("Open");

        // Valid transitions
        assert!(protocol.can_transition(&closed, &Action::new("open"), &open));
        assert!(protocol.can_transition(&open, &Action::new("read"), &open));
        assert!(protocol.can_transition(&open, &Action::new("write"), &open));
        assert!(protocol.can_transition(&open, &Action::new("close"), &closed));

        // Invalid transitions
        assert!(!protocol.can_transition(&closed, &Action::new("read"), &closed));
        assert!(!protocol.can_transition(&closed, &Action::new("close"), &closed));
    }

    #[test]
    fn test_lock_protocol_definition() {
        let protocol = LockProtocol::define();

        assert_eq!(protocol.name, "Lock");
        assert_eq!(protocol.initial_state(), State::new("Unlocked"));
        assert!(protocol.is_final_state(&State::new("Unlocked")));
        assert!(!protocol.is_final_state(&State::new("Locked")));
    }

    #[test]
    fn test_lock_protocol_transitions() {
        let protocol = LockProtocol::define();

        let unlocked = State::new("Unlocked");
        let locked = State::new("Locked");

        // Valid transitions
        assert!(protocol.can_transition(&unlocked, &Action::new("acquire"), &locked));
        assert!(protocol.can_transition(&locked, &Action::new("release"), &unlocked));

        // Invalid transitions
        assert!(!protocol.can_transition(&locked, &Action::new("acquire"), &locked));
        assert!(!protocol.can_transition(&unlocked, &Action::new("release"), &unlocked));
    }

    #[test]
    fn test_connection_protocol_definition() {
        let protocol = ConnectionProtocol::define();

        assert_eq!(protocol.name, "Connection");
        assert_eq!(protocol.initial_state(), State::new("Disconnected"));
        assert!(protocol.is_final_state(&State::new("Disconnected")));
    }

    #[test]
    fn test_connection_protocol_transitions() {
        let protocol = ConnectionProtocol::define();

        let disconnected = State::new("Disconnected");
        let connected = State::new("Connected");
        let authenticated = State::new("Authenticated");

        // Valid transitions
        assert!(protocol.can_transition(&disconnected, &Action::new("connect"), &connected));
        assert!(protocol.can_transition(&connected, &Action::new("authenticate"), &authenticated));
        assert!(protocol.can_transition(&authenticated, &Action::new("send"), &authenticated));
        assert!(protocol.can_transition(&authenticated, &Action::new("receive"), &authenticated));
        assert!(protocol.can_transition(&authenticated, &Action::new("disconnect"), &disconnected));

        // Invalid transitions
        assert!(!protocol.can_transition(&connected, &Action::new("send"), &connected));
    }

    #[test]
    fn test_file_protocol_next_state() {
        let protocol = FileProtocol::define();

        let closed = State::new("Closed");
        let open = State::new("Open");

        assert_eq!(
            protocol.next_state(&closed, &Action::new("open")),
            Some(open.clone())
        );
        assert_eq!(
            protocol.next_state(&open, &Action::new("read")),
            Some(open.clone())
        );
        assert_eq!(
            protocol.next_state(&open, &Action::new("close")),
            Some(closed.clone())
        );

        // Invalid transition
        assert_eq!(protocol.next_state(&closed, &Action::new("read")), None);
    }

    #[test]
    fn test_lock_protocol_double_acquire() {
        let protocol = LockProtocol::define();

        let locked = State::new("Locked");

        // Cannot acquire locked lock
        assert_eq!(protocol.next_state(&locked, &Action::new("acquire")), None);
    }

    #[test]
    fn test_connection_send_before_authenticate() {
        let protocol = ConnectionProtocol::define();

        let connected = State::new("Connected");

        // Cannot send before authenticate
        assert_eq!(protocol.next_state(&connected, &Action::new("send")), None);
    }

    #[test]
    fn test_all_protocols_validate() {
        let file = FileProtocol::define();
        let lock = LockProtocol::define();
        let conn = ConnectionProtocol::define();

        assert!(file.validate().is_ok());
        assert!(lock.validate().is_ok());
        assert!(conn.validate().is_ok());
    }
}
