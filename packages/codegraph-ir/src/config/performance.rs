//! Performance profile types
//!
//! Qualitative cost classes and expected resource bands.
//! These are NOT quantitative guarantees, but general guidance.

use serde::{Deserialize, Serialize};

/// Qualitative cost class (not quantitative guarantees)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CostClass {
    /// Light analysis, suitable for tight feedback loops
    Low,
    /// Moderate analysis, suitable for CI/CD
    Medium,
    /// Deep analysis, suitable for nightly scans
    High,
    /// Exhaustive analysis, may be unbounded
    Extreme,
}

/// Expected latency band (qualitative, not guaranteed)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LatencyBand {
    /// Typically completes in <5 seconds
    SubFiveSeconds,
    /// Typically completes in <30 seconds
    SubThirtySeconds,
    /// Typically completes in <5 minutes
    SubFiveMinutes,
    /// May take longer, unbounded
    Unbounded,
}

/// Expected memory band (qualitative, not guaranteed)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MemoryBand {
    /// Typically uses <200MB
    Under200MB,
    /// Typically uses <1GB
    Under1GB,
    /// Typically uses <4GB
    Under4GB,
    /// May use more, unbounded
    Unbounded,
}

/// Performance profile (qualitative bands, NOT guarantees)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerformanceProfile {
    /// Cost class: Low | Medium | High | Extreme
    pub cost_class: CostClass,

    /// Expected latency: <5s | <30s | <5m | unbounded
    pub expected_latency: LatencyBand,

    /// Expected memory: <200MB | <1GB | <4GB | unbounded
    pub expected_memory: MemoryBand,

    /// Whether recommended for production use
    pub production_ready: bool,
}

impl PerformanceProfile {
    /// Create a new performance profile
    pub fn new(
        cost_class: CostClass,
        expected_latency: LatencyBand,
        expected_memory: MemoryBand,
        production_ready: bool,
    ) -> Self {
        Self {
            cost_class,
            expected_latency,
            expected_memory,
            production_ready,
        }
    }

    /// Get a human-readable description
    pub fn describe(&self) -> String {
        format!(
            "Cost: {:?}, Latency: {:?}, Memory: {:?}, Production: {}",
            self.cost_class,
            self.expected_latency,
            self.expected_memory,
            if self.production_ready {
                "Yes ✅"
            } else {
                "No ⚠️"
            }
        )
    }

    /// Fast profile: Low cost, <5s, <200MB
    pub fn fast() -> Self {
        Self {
            cost_class: CostClass::Low,
            expected_latency: LatencyBand::SubFiveSeconds,
            expected_memory: MemoryBand::Under200MB,
            production_ready: true,
        }
    }

    /// Balanced profile: Medium cost, <30s, <1GB
    pub fn balanced() -> Self {
        Self {
            cost_class: CostClass::Medium,
            expected_latency: LatencyBand::SubThirtySeconds,
            expected_memory: MemoryBand::Under1GB,
            production_ready: true,
        }
    }

    /// Thorough profile: High cost, <5m, <4GB
    pub fn thorough() -> Self {
        Self {
            cost_class: CostClass::High,
            expected_latency: LatencyBand::SubFiveMinutes,
            expected_memory: MemoryBand::Under4GB,
            production_ready: false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_profile_describe() {
        let profile = PerformanceProfile::fast();
        let desc = profile.describe();
        assert!(desc.contains("Low"));
        assert!(desc.contains("SubFiveSeconds"));
        assert!(desc.contains("Under200MB"));
        assert!(desc.contains("Yes"));
    }

    #[test]
    fn test_preset_profiles() {
        let fast = PerformanceProfile::fast();
        assert_eq!(fast.cost_class, CostClass::Low);
        assert!(fast.production_ready);

        let balanced = PerformanceProfile::balanced();
        assert_eq!(balanced.cost_class, CostClass::Medium);
        assert!(balanced.production_ready);

        let thorough = PerformanceProfile::thorough();
        assert_eq!(thorough.cost_class, CostClass::High);
        assert!(!thorough.production_ready);
    }

    #[test]
    fn test_cost_class_ordering() {
        assert_eq!(CostClass::Low, CostClass::Low);
        assert_ne!(CostClass::Low, CostClass::Medium);
        assert_ne!(CostClass::Medium, CostClass::High);
        assert_ne!(CostClass::High, CostClass::Extreme);
    }

    #[test]
    fn test_latency_band_ordering() {
        assert_eq!(LatencyBand::SubFiveSeconds, LatencyBand::SubFiveSeconds);
        assert_ne!(LatencyBand::SubFiveSeconds, LatencyBand::SubThirtySeconds);
        assert_ne!(LatencyBand::SubThirtySeconds, LatencyBand::SubFiveMinutes);
        assert_ne!(LatencyBand::SubFiveMinutes, LatencyBand::Unbounded);
    }

    #[test]
    fn test_memory_band_ordering() {
        assert_eq!(MemoryBand::Under200MB, MemoryBand::Under200MB);
        assert_ne!(MemoryBand::Under200MB, MemoryBand::Under1GB);
        assert_ne!(MemoryBand::Under1GB, MemoryBand::Under4GB);
        assert_ne!(MemoryBand::Under4GB, MemoryBand::Unbounded);
    }

    #[test]
    fn test_custom_profile() {
        let profile = PerformanceProfile::new(
            CostClass::Extreme,
            LatencyBand::Unbounded,
            MemoryBand::Unbounded,
            false,
        );

        assert_eq!(profile.cost_class, CostClass::Extreme);
        assert_eq!(profile.expected_latency, LatencyBand::Unbounded);
        assert_eq!(profile.expected_memory, MemoryBand::Unbounded);
        assert!(!profile.production_ready);
    }

    #[test]
    fn test_profile_serialization() {
        let profile = PerformanceProfile::fast();
        let json = serde_json::to_string(&profile).unwrap();
        assert!(json.contains("Low"));
        assert!(json.contains("SubFiveSeconds"));

        let deserialized: PerformanceProfile = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.cost_class, CostClass::Low);
    }

    #[test]
    fn test_cost_class_serialization() {
        let cost = CostClass::Medium;
        let json = serde_json::to_string(&cost).unwrap();
        assert_eq!(json, "\"Medium\"");

        let deserialized: CostClass = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, CostClass::Medium);
    }

    #[test]
    fn test_all_presets_valid() {
        // Ensure all preset profiles are valid
        let fast = PerformanceProfile::fast();
        assert_eq!(fast.expected_latency, LatencyBand::SubFiveSeconds);
        assert_eq!(fast.expected_memory, MemoryBand::Under200MB);

        let balanced = PerformanceProfile::balanced();
        assert_eq!(balanced.expected_latency, LatencyBand::SubThirtySeconds);
        assert_eq!(balanced.expected_memory, MemoryBand::Under1GB);

        let thorough = PerformanceProfile::thorough();
        assert_eq!(thorough.expected_latency, LatencyBand::SubFiveMinutes);
        assert_eq!(thorough.expected_memory, MemoryBand::Under4GB);
    }
}
