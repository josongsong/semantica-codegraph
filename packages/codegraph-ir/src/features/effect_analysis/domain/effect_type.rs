/// Effect types
use serde::{Deserialize, Serialize};

/// Effect type classification
///
/// 12 effect types matching Python implementation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EffectType {
    /// Pure (no side effects)
    Pure,

    /// I/O operations (print, file read/write)
    Io,

    /// State mutations (write to variables)
    WriteState,

    /// State reads
    ReadState,

    /// Global variable mutation
    GlobalMutation,

    /// Database read (SELECT)
    DbRead,

    /// Database write (INSERT/UPDATE/DELETE)
    DbWrite,

    /// Network operations (HTTP, etc.)
    Network,

    /// Logging
    Log,

    /// External function call
    ExternalCall,

    /// Throws exceptions
    Throws,

    /// Unknown effect (pessimistic)
    Unknown,
}

impl EffectType {
    /// Check if this is a side effect (not Pure)
    pub fn is_side_effect(&self) -> bool {
        !matches!(self, EffectType::Pure)
    }

    /// Check if this is a write effect
    pub fn is_write(&self) -> bool {
        matches!(
            self,
            EffectType::WriteState
                | EffectType::GlobalMutation
                | EffectType::DbWrite
                | EffectType::Io
        )
    }

    /// Get severity score (0-10, higher = more severe)
    pub fn severity_score(&self) -> u8 {
        match self {
            EffectType::Pure => 0,
            EffectType::Log => 1,
            EffectType::ReadState => 2,
            EffectType::DbRead => 3,
            EffectType::Io => 4,
            EffectType::ExternalCall => 5,
            EffectType::Throws => 6,
            EffectType::WriteState => 7,
            EffectType::Network => 8,
            EffectType::DbWrite => 9,
            EffectType::GlobalMutation => 9,
            EffectType::Unknown => 10,
        }
    }
}

impl std::fmt::Display for EffectType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EffectType::Pure => write!(f, "PURE"),
            EffectType::Io => write!(f, "IO"),
            EffectType::WriteState => write!(f, "WRITE_STATE"),
            EffectType::ReadState => write!(f, "READ_STATE"),
            EffectType::GlobalMutation => write!(f, "GLOBAL_MUTATION"),
            EffectType::DbRead => write!(f, "DB_READ"),
            EffectType::DbWrite => write!(f, "DB_WRITE"),
            EffectType::Network => write!(f, "NETWORK"),
            EffectType::Log => write!(f, "LOG"),
            EffectType::ExternalCall => write!(f, "EXTERNAL_CALL"),
            EffectType::Throws => write!(f, "THROWS"),
            EffectType::Unknown => write!(f, "UNKNOWN"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_side_effect() {
        assert!(!EffectType::Pure.is_side_effect());
        assert!(EffectType::Io.is_side_effect());
        assert!(EffectType::GlobalMutation.is_side_effect());
    }

    #[test]
    fn test_is_write() {
        assert!(!EffectType::Pure.is_write());
        assert!(!EffectType::ReadState.is_write());
        assert!(EffectType::WriteState.is_write());
        assert!(EffectType::DbWrite.is_write());
    }

    #[test]
    fn test_severity_score() {
        assert_eq!(EffectType::Pure.severity_score(), 0);
        assert!(EffectType::Log.severity_score() < EffectType::Io.severity_score());
        assert!(EffectType::Io.severity_score() < EffectType::DbWrite.severity_score());
        assert_eq!(EffectType::Unknown.severity_score(), 10);
    }

    #[test]
    fn test_display() {
        assert_eq!(EffectType::Pure.to_string(), "PURE");
        assert_eq!(EffectType::GlobalMutation.to_string(), "GLOBAL_MUTATION");
    }
}
