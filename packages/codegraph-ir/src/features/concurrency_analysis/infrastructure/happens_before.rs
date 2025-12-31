//! Happens-Before Relation Analysis
//!
//! Implementation of Lamport's happens-before relation for concurrency analysis.
//!
//! ## Theory
//! Two events a and b are in happens-before relation (a → b) if:
//! 1. **Program order**: a and b are in the same thread and a precedes b
//! 2. **Synchronization order**: a is a release and b is the matching acquire
//! 3. **Transitivity**: if a → c and c → b, then a → b
//!
//! ## Race Condition
//! A data race exists between events a and b iff:
//! - ¬(a → b) ∧ ¬(b → a) (no happens-before order)
//! - conflict(a, b) (at least one is write, same location)
//!
//! ## Python Async Specifics
//! - await = potential yield point (release + re-acquire)
//! - async with lock = acquire + release
//! - task spawn = fork (release) + join (acquire)
//!
//! ## Academic Reference
//! - Lamport (1978), "Time, Clocks, and the Ordering of Events in a Distributed System"
//! - Flanagan & Freund (2009), "FastTrack: Efficient and Precise Dynamic Race Detection"

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

// ═══════════════════════════════════════════════════════════════════════════════
// Event Types for Happens-Before Analysis
// ═══════════════════════════════════════════════════════════════════════════════

/// Event in the program execution (for happens-before ordering)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Event {
    /// Unique event identifier
    pub id: String,

    /// Event type
    pub kind: EventKind,

    /// Associated variable (for read/write events)
    pub variable: Option<String>,

    /// Source location (file:line)
    pub location: String,

    /// Thread/task identifier
    pub thread_id: String,

    /// Line number in source code
    pub line: u32,
}

/// Kind of event for ordering analysis
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EventKind {
    /// Variable read
    Read,
    /// Variable write
    Write,
    /// Await expression (yield point)
    Await,
    /// Lock acquire (async with lock: entry)
    Acquire,
    /// Lock release (async with lock: exit)
    Release,
    /// Task spawn (asyncio.create_task)
    Fork,
    /// Task join (await task)
    Join,
    /// Function entry
    FunctionEntry,
    /// Function exit
    FunctionExit,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Vector Clock for Happens-Before Tracking
// ═══════════════════════════════════════════════════════════════════════════════

/// Vector clock for tracking happens-before relations
///
/// Each thread maintains a vector of logical timestamps.
/// Entry i represents the last known time of thread i.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct VectorClock {
    /// Map from thread_id to logical timestamp
    clocks: HashMap<String, u64>,
}

impl VectorClock {
    /// Create a new empty vector clock
    pub fn new() -> Self {
        Self {
            clocks: HashMap::new(),
        }
    }

    /// Get timestamp for a thread
    pub fn get(&self, thread_id: &str) -> u64 {
        *self.clocks.get(thread_id).unwrap_or(&0)
    }

    /// Increment timestamp for a thread
    pub fn increment(&mut self, thread_id: &str) {
        let entry = self.clocks.entry(thread_id.to_string()).or_insert(0);
        *entry += 1;
    }

    /// Join (max) with another vector clock
    ///
    /// Used when receiving a message or acquiring a lock
    pub fn join(&mut self, other: &VectorClock) {
        for (thread_id, &time) in &other.clocks {
            let entry = self.clocks.entry(thread_id.clone()).or_insert(0);
            *entry = (*entry).max(time);
        }
    }

    /// Check if self happens-before other
    ///
    /// self → other iff ∀t: self[t] ≤ other[t]
    pub fn happens_before(&self, other: &VectorClock) -> bool {
        // All entries in self must be ≤ corresponding entries in other
        for (thread_id, &self_time) in &self.clocks {
            let other_time = other.get(thread_id);
            if self_time > other_time {
                return false;
            }
        }
        true
    }

    /// Check if two clocks are concurrent (no happens-before relation)
    ///
    /// concurrent(a, b) iff ¬(a → b) ∧ ¬(b → a)
    pub fn concurrent(&self, other: &VectorClock) -> bool {
        !self.happens_before(other) && !other.happens_before(self)
    }

    /// Clone the clock
    pub fn copy(&self) -> VectorClock {
        self.clone()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Happens-Before Analyzer
// ═══════════════════════════════════════════════════════════════════════════════

/// Happens-before relation analyzer
///
/// Computes happens-before ordering between events to detect
/// potential data races.
pub struct HappensBeforeAnalyzer {
    /// Vector clocks per thread/task
    thread_clocks: HashMap<String, VectorClock>,

    /// Lock clocks (for acquire-release synchronization)
    lock_clocks: HashMap<String, VectorClock>,

    /// Event timestamps (event_id → VectorClock at event time)
    event_clocks: HashMap<String, VectorClock>,

    /// Events in program order per thread
    thread_events: HashMap<String, Vec<String>>,

    /// All events
    events: HashMap<String, Event>,

    /// Enable debug output
    debug: bool,
}

impl HappensBeforeAnalyzer {
    /// Create a new happens-before analyzer
    pub fn new() -> Self {
        Self {
            thread_clocks: HashMap::new(),
            lock_clocks: HashMap::new(),
            event_clocks: HashMap::new(),
            thread_events: HashMap::new(),
            events: HashMap::new(),
            debug: false,
        }
    }

    /// Enable debug mode
    pub fn with_debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }

    /// Process an event and update happens-before state
    pub fn process_event(&mut self, event: Event) {
        let thread_id = event.thread_id.clone();
        let event_id = event.id.clone();

        // Initialize thread clock if needed
        if !self.thread_clocks.contains_key(&thread_id) {
            self.thread_clocks
                .insert(thread_id.clone(), VectorClock::new());
        }

        // Process event based on kind - handle borrows carefully
        match &event.kind {
            EventKind::Acquire => {
                // Join with lock clock (if exists)
                if let Some(lock_var) = &event.variable {
                    if let Some(lock_clock) = self.lock_clocks.get(lock_var) {
                        let lock_clock_copy = lock_clock.copy();
                        let thread_clock = self.thread_clocks.get_mut(&thread_id).unwrap();
                        thread_clock.join(&lock_clock_copy);
                    }
                }
            }
            EventKind::Release => {
                // Update lock clock
                if let Some(lock_var) = &event.variable {
                    let thread_clock_copy = self.thread_clocks.get(&thread_id).unwrap().copy();
                    let lock_clock = self
                        .lock_clocks
                        .entry(lock_var.clone())
                        .or_insert_with(VectorClock::new);
                    lock_clock.join(&thread_clock_copy);
                }
            }
            EventKind::Fork => {
                // New task inherits parent's clock (will be handled when task starts)
            }
            EventKind::Join => {
                // Join with child task's clock (if we tracked it)
                if let Some(task_id) = &event.variable {
                    // Clone first to release immutable borrow before mutable borrow
                    let task_clock_copy = self.thread_clocks.get(task_id).map(|c| c.copy());
                    if let Some(task_clock) = task_clock_copy {
                        let thread_clock = self.thread_clocks.get_mut(&thread_id).unwrap();
                        thread_clock.join(&task_clock);
                    }
                }
            }
            EventKind::Await => {
                // Await is a potential yield point
                // In Python async, this is where other tasks can run
                // For conservative analysis, we treat it as a release+acquire
                let thread_clock = self.thread_clocks.get_mut(&thread_id).unwrap();
                thread_clock.increment(&thread_id);
            }
            _ => {
                // Read/Write - just record the clock
            }
        }

        // Increment thread clock (program order)
        let thread_clock = self.thread_clocks.get_mut(&thread_id).unwrap();
        thread_clock.increment(&thread_id);

        // Record event clock
        let clock_copy = thread_clock.copy();
        self.event_clocks.insert(event_id.clone(), clock_copy);

        // Record event in thread order
        self.thread_events
            .entry(thread_id)
            .or_insert_with(Vec::new)
            .push(event_id.clone());

        // Store event
        self.events.insert(event_id, event);
    }

    /// Check if event a happens-before event b
    pub fn happens_before(&self, event_a_id: &str, event_b_id: &str) -> bool {
        match (
            self.event_clocks.get(event_a_id),
            self.event_clocks.get(event_b_id),
        ) {
            (Some(clock_a), Some(clock_b)) => clock_a.happens_before(clock_b),
            _ => false,
        }
    }

    /// Check if two events are concurrent (potential race)
    pub fn are_concurrent(&self, event_a_id: &str, event_b_id: &str) -> bool {
        match (
            self.event_clocks.get(event_a_id),
            self.event_clocks.get(event_b_id),
        ) {
            (Some(clock_a), Some(clock_b)) => clock_a.concurrent(clock_b),
            _ => false,
        }
    }

    /// Check if two events conflict (at least one is write, same variable)
    pub fn conflict(&self, event_a_id: &str, event_b_id: &str) -> bool {
        match (self.events.get(event_a_id), self.events.get(event_b_id)) {
            (Some(a), Some(b)) => {
                // Same variable?
                let same_var = match (&a.variable, &b.variable) {
                    (Some(var_a), Some(var_b)) => var_a == var_b,
                    _ => false,
                };

                // At least one is write?
                let at_least_one_write =
                    matches!(a.kind, EventKind::Write) || matches!(b.kind, EventKind::Write);

                same_var && at_least_one_write
            }
            _ => false,
        }
    }

    /// Detect potential data races
    ///
    /// A race exists between events a and b iff:
    /// - concurrent(a, b)
    /// - conflict(a, b)
    pub fn detect_races(&self) -> Vec<PotentialRace> {
        let mut races = Vec::new();

        // Get all read/write events
        let memory_events: Vec<&Event> = self
            .events
            .values()
            .filter(|e| matches!(e.kind, EventKind::Read | EventKind::Write))
            .collect();

        // Check all pairs
        for (i, event_a) in memory_events.iter().enumerate() {
            for event_b in memory_events.iter().skip(i + 1) {
                // Skip events from same thread (program order guarantees ordering)
                if event_a.thread_id == event_b.thread_id {
                    continue;
                }

                // Check for race
                if self.conflict(&event_a.id, &event_b.id)
                    && self.are_concurrent(&event_a.id, &event_b.id)
                {
                    races.push(PotentialRace {
                        event_a: event_a.id.clone(),
                        event_b: event_b.id.clone(),
                        variable: event_a.variable.clone().unwrap_or_default(),
                        location_a: event_a.location.clone(),
                        location_b: event_b.location.clone(),
                    });
                }
            }
        }

        races
    }

    /// Get events for a thread
    pub fn get_thread_events(&self, thread_id: &str) -> Vec<&Event> {
        self.thread_events
            .get(thread_id)
            .map(|ids| ids.iter().filter_map(|id| self.events.get(id)).collect())
            .unwrap_or_default()
    }
}

impl Default for HappensBeforeAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Result Types
// ═══════════════════════════════════════════════════════════════════════════════

/// Potential data race detected by happens-before analysis
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PotentialRace {
    /// First event ID
    pub event_a: String,
    /// Second event ID
    pub event_b: String,
    /// Variable involved
    pub variable: String,
    /// Location of first event
    pub location_a: String,
    /// Location of second event
    pub location_b: String,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vector_clock_happens_before() {
        let mut clock_a = VectorClock::new();
        let mut clock_b = VectorClock::new();

        // a: {T1: 1}
        clock_a.increment("T1");

        // b: {T1: 2}
        clock_b.increment("T1");
        clock_b.increment("T1");

        // a → b because a[T1]=1 < b[T1]=2
        assert!(clock_a.happens_before(&clock_b));
        assert!(!clock_b.happens_before(&clock_a));
    }

    #[test]
    fn test_vector_clock_concurrent() {
        let mut clock_a = VectorClock::new();
        let mut clock_b = VectorClock::new();

        // a: {T1: 1, T2: 0}
        clock_a.increment("T1");

        // b: {T1: 0, T2: 1}
        clock_b.increment("T2");

        // Neither a → b nor b → a
        assert!(!clock_a.happens_before(&clock_b));
        assert!(!clock_b.happens_before(&clock_a));
        assert!(clock_a.concurrent(&clock_b));
    }

    #[test]
    fn test_vector_clock_join() {
        let mut clock_a = VectorClock::new();
        let mut clock_b = VectorClock::new();

        clock_a.increment("T1");
        clock_a.increment("T1"); // a: {T1: 2}

        clock_b.increment("T2");
        clock_b.increment("T2");
        clock_b.increment("T2"); // b: {T2: 3}

        // Join: max of each component
        clock_a.join(&clock_b); // a: {T1: 2, T2: 3}

        assert_eq!(clock_a.get("T1"), 2);
        assert_eq!(clock_a.get("T2"), 3);
    }

    #[test]
    fn test_happens_before_simple_program_order() {
        let mut analyzer = HappensBeforeAnalyzer::new();

        // Thread T1: write x, then read x
        analyzer.process_event(Event {
            id: "e1".to_string(),
            kind: EventKind::Write,
            variable: Some("x".to_string()),
            location: "test.py:1".to_string(),
            thread_id: "T1".to_string(),
            line: 1,
        });

        analyzer.process_event(Event {
            id: "e2".to_string(),
            kind: EventKind::Read,
            variable: Some("x".to_string()),
            location: "test.py:2".to_string(),
            thread_id: "T1".to_string(),
            line: 2,
        });

        // e1 → e2 (program order)
        assert!(analyzer.happens_before("e1", "e2"));
        assert!(!analyzer.happens_before("e2", "e1"));

        // No races in single thread
        let races = analyzer.detect_races();
        assert!(races.is_empty());
    }

    #[test]
    fn test_happens_before_detects_race() {
        let mut analyzer = HappensBeforeAnalyzer::new();

        // Thread T1: write x
        analyzer.process_event(Event {
            id: "e1".to_string(),
            kind: EventKind::Write,
            variable: Some("x".to_string()),
            location: "test.py:1".to_string(),
            thread_id: "T1".to_string(),
            line: 1,
        });

        // Thread T2: write x (concurrent with T1)
        analyzer.process_event(Event {
            id: "e2".to_string(),
            kind: EventKind::Write,
            variable: Some("x".to_string()),
            location: "test.py:2".to_string(),
            thread_id: "T2".to_string(),
            line: 2,
        });

        // Should detect race: concurrent writes to same variable
        let races = analyzer.detect_races();
        assert_eq!(races.len(), 1);
        assert_eq!(races[0].variable, "x");
    }

    #[test]
    fn test_happens_before_lock_synchronization() {
        let mut analyzer = HappensBeforeAnalyzer::new();

        // Thread T1: acquire lock, write x, release lock
        analyzer.process_event(Event {
            id: "e1".to_string(),
            kind: EventKind::Acquire,
            variable: Some("lock".to_string()),
            location: "test.py:1".to_string(),
            thread_id: "T1".to_string(),
            line: 1,
        });

        analyzer.process_event(Event {
            id: "e2".to_string(),
            kind: EventKind::Write,
            variable: Some("x".to_string()),
            location: "test.py:2".to_string(),
            thread_id: "T1".to_string(),
            line: 2,
        });

        analyzer.process_event(Event {
            id: "e3".to_string(),
            kind: EventKind::Release,
            variable: Some("lock".to_string()),
            location: "test.py:3".to_string(),
            thread_id: "T1".to_string(),
            line: 3,
        });

        // Thread T2: acquire same lock, read x, release lock
        analyzer.process_event(Event {
            id: "e4".to_string(),
            kind: EventKind::Acquire,
            variable: Some("lock".to_string()),
            location: "test.py:4".to_string(),
            thread_id: "T2".to_string(),
            line: 4,
        });

        analyzer.process_event(Event {
            id: "e5".to_string(),
            kind: EventKind::Read,
            variable: Some("x".to_string()),
            location: "test.py:5".to_string(),
            thread_id: "T2".to_string(),
            line: 5,
        });

        analyzer.process_event(Event {
            id: "e6".to_string(),
            kind: EventKind::Release,
            variable: Some("lock".to_string()),
            location: "test.py:6".to_string(),
            thread_id: "T2".to_string(),
            line: 6,
        });

        // e2 → e5 due to lock synchronization
        // T1's release transfers to T2's acquire
        assert!(analyzer.happens_before("e2", "e5"));

        // No race because of lock protection
        let races = analyzer.detect_races();
        assert!(races.is_empty());
    }

    #[test]
    fn test_happens_before_await_creates_yield() {
        let mut analyzer = HappensBeforeAnalyzer::new();

        // Thread T1: write x, await, write y
        analyzer.process_event(Event {
            id: "e1".to_string(),
            kind: EventKind::Write,
            variable: Some("x".to_string()),
            location: "test.py:1".to_string(),
            thread_id: "T1".to_string(),
            line: 1,
        });

        analyzer.process_event(Event {
            id: "e2".to_string(),
            kind: EventKind::Await,
            variable: None,
            location: "test.py:2".to_string(),
            thread_id: "T1".to_string(),
            line: 2,
        });

        analyzer.process_event(Event {
            id: "e3".to_string(),
            kind: EventKind::Write,
            variable: Some("y".to_string()),
            location: "test.py:3".to_string(),
            thread_id: "T1".to_string(),
            line: 3,
        });

        // e1 → e3 (program order through await)
        assert!(analyzer.happens_before("e1", "e3"));
    }
}
