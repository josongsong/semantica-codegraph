/// Race condition domain model
use super::{AccessType, AwaitPoint, LockRegion, RaceSeverity};
use serde::{Deserialize, Serialize};

/// Race condition verdict
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RaceVerdict {
    /// Proven race (must-alias confirmed, 100% confidence)
    Proven,
    /// Likely race (may-alias or heuristic)
    Likely,
    /// Possible race (low confidence)
    Possible,
}

/// Access location (file_path, line, access_type)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AccessLocation {
    pub file_path: String,
    pub line: u32,
    pub access_type: AccessType,
}

/// Race condition
///
/// Detected when:
/// 1. Multiple accesses to shared variable
/// 2. At least one is write
/// 3. At least one has await before (interleaving possible)
/// 4. Not protected by lock
///
/// ## Example
/// ```python
/// class Counter:
///     def __init__(self):
///         self.count = 0  # Shared variable
///
///     async def increment(self):
///         await asyncio.sleep(0)  # Await point (interleaving)
///         self.count += 1  # Write access - RACE!
/// ```
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RaceCondition {
    /// Shared variable name
    pub shared_var: String,

    /// First access location
    pub access1: AccessLocation,

    /// Second access location
    pub access2: AccessLocation,

    /// Severity
    pub severity: RaceSeverity,

    /// Verdict (proven/likely/possible)
    pub verdict: RaceVerdict,

    /// Await points between accesses
    pub await_points: Vec<AwaitPoint>,

    /// Lock regions (if any)
    pub lock_regions: Vec<LockRegion>,

    /// Proof trace (human-readable explanation)
    pub proof_trace: String,

    /// Fix suggestion
    pub fix_suggestion: String,

    /// File path (for reporting)
    pub file_path: String,

    /// Function name
    pub function_name: String,
}

impl RaceCondition {
    /// Build a race condition
    pub fn new(
        shared_var: String,
        access1: AccessLocation,
        access2: AccessLocation,
        await_points: Vec<AwaitPoint>,
        lock_regions: Vec<LockRegion>,
        file_path: String,
        function_name: String,
    ) -> Self {
        let severity = RaceSeverity::from_accesses(access1.access_type, access2.access_type);
        let verdict = RaceVerdict::Proven; // Must-alias confirmed (from alias analyzer)

        let proof_trace = Self::build_proof_trace(&access1, &access2, &await_points);

        let fix_suggestion = Self::build_fix_suggestion(&shared_var);

        Self {
            shared_var,
            access1,
            access2,
            severity,
            verdict,
            await_points,
            lock_regions,
            proof_trace,
            fix_suggestion,
            file_path,
            function_name,
        }
    }

    fn build_proof_trace(
        access1: &AccessLocation,
        access2: &AccessLocation,
        await_points: &[AwaitPoint],
    ) -> String {
        format!(
            "Race detected:\n\
             1. {:?} at line {}\n\
             2. await point(s): {}\n\
             3. {:?} at line {}\n\
             4. No lock protection\n\
             → Interleaving possible (proven by must-alias)",
            access1.access_type,
            access1.line,
            await_points.len(),
            access2.access_type,
            access2.line,
        )
    }

    fn build_fix_suggestion(var_name: &str) -> String {
        format!(
            "Wrap '{}' accesses with asyncio.Lock:\n\
             \n\
             self._lock = asyncio.Lock()\n\
             \n\
             async with self._lock:\n\
                 {} = ...  # Protected",
            var_name, var_name
        )
    }

    /// Check if this race involves write-write
    pub fn is_write_write(&self) -> bool {
        self.access1.access_type.is_write() && self.access2.access_type.is_write()
    }

    /// Get human-readable description
    pub fn description(&self) -> String {
        format!(
            "{:?} race on '{}' in {} ({:?})",
            self.severity, self.shared_var, self.function_name, self.verdict
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_race_condition_new() {
        let access1 = AccessLocation {
            file_path: "test.py".to_string(),
            line: 10,
            access_type: AccessType::Write,
        };
        let access2 = AccessLocation {
            file_path: "test.py".to_string(),
            line: 15,
            access_type: AccessType::Write,
        };

        let race = RaceCondition::new(
            "self.count".to_string(),
            access1,
            access2,
            vec![],
            vec![],
            "test.py".to_string(),
            "increment".to_string(),
        );

        assert_eq!(race.shared_var, "self.count");
        assert_eq!(race.severity, RaceSeverity::Critical);
        assert_eq!(race.verdict, RaceVerdict::Proven);
        assert!(race.is_write_write());
    }

    #[test]
    fn test_race_condition_description() {
        let access1 = AccessLocation {
            file_path: "test.py".to_string(),
            line: 10,
            access_type: AccessType::Write,
        };
        let access2 = AccessLocation {
            file_path: "test.py".to_string(),
            line: 15,
            access_type: AccessType::Read,
        };

        let race = RaceCondition::new(
            "self.count".to_string(),
            access1,
            access2,
            vec![],
            vec![],
            "test.py".to_string(),
            "increment".to_string(),
        );

        let desc = race.description();
        assert!(desc.contains("High"));
        assert!(desc.contains("self.count"));
        assert!(desc.contains("increment"));
    }
}
