//! Preset configurations
//!
//! Presets provide complete default configurations for common use cases.

use super::performance::PerformanceProfile;
use serde::{Deserialize, Serialize};

/// Configuration preset
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Preset {
    /// CI/CD: Minimal fast analysis
    ///
    /// - Taint: max_depth=10, PTA disabled
    /// - PTA: Steensgaard only, iterations=5
    /// - Clone: Type-1 exact clones only
    /// - Performance: <5s, <200MB
    Fast,

    /// Development: Balanced analysis
    ///
    /// - Taint: max_depth=30, PTA enabled
    /// - PTA: Auto mode, iterations=10
    /// - Clone: Type-1 + Type-2
    /// - Performance: <30s, <1GB
    Balanced,

    /// Security Audit: Complete analysis
    ///
    /// - Taint: max_depth=100, all features on
    /// - PTA: Andersen always, iterations=50
    /// - Clone: All types (Type-1~4)
    /// - Performance: <5m, <4GB
    Thorough,

    /// Custom: User-defined (YAML/TOML only)
    ///
    /// This preset provides minimal defaults.
    /// Users must override via YAML or builder API.
    Custom,
}

impl Preset {
    /// Get performance profile for this preset
    pub fn performance_profile(&self) -> PerformanceProfile {
        match self {
            Self::Fast => PerformanceProfile::fast(),
            Self::Balanced => PerformanceProfile::balanced(),
            Self::Thorough => PerformanceProfile::thorough(),
            Self::Custom => PerformanceProfile::balanced(), // Default to balanced
        }
    }

    /// Parse preset from string
    pub fn from_str(s: &str) -> Result<Self, String> {
        match s.to_lowercase().as_str() {
            "fast" => Ok(Self::Fast),
            "balanced" => Ok(Self::Balanced),
            "thorough" => Ok(Self::Thorough),
            "custom" => Ok(Self::Custom),
            _ => Err(format!(
                "Unknown preset '{}'. Valid presets: fast, balanced, thorough, custom",
                s
            )),
        }
    }

    /// Convert to string
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Fast => "fast",
            Self::Balanced => "balanced",
            Self::Thorough => "thorough",
            Self::Custom => "custom",
        }
    }
}

impl Default for Preset {
    fn default() -> Self {
        Self::Balanced
    }
}

impl std::fmt::Display for Preset {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_preset_parsing() {
        assert_eq!(Preset::from_str("fast").unwrap(), Preset::Fast);
        assert_eq!(Preset::from_str("FAST").unwrap(), Preset::Fast);
        assert_eq!(Preset::from_str("balanced").unwrap(), Preset::Balanced);
        assert_eq!(Preset::from_str("thorough").unwrap(), Preset::Thorough);
        assert_eq!(Preset::from_str("custom").unwrap(), Preset::Custom);
        assert!(Preset::from_str("invalid").is_err());
    }

    #[test]
    fn test_preset_display() {
        assert_eq!(Preset::Fast.to_string(), "fast");
        assert_eq!(Preset::Balanced.to_string(), "balanced");
        assert_eq!(Preset::Thorough.to_string(), "thorough");
        assert_eq!(Preset::Custom.to_string(), "custom");
    }

    #[test]
    fn test_preset_performance_profiles() {
        assert!(Preset::Fast.performance_profile().production_ready);
        assert!(Preset::Balanced.performance_profile().production_ready);
        assert!(!Preset::Thorough.performance_profile().production_ready);
    }

    #[test]
    fn test_default_preset() {
        let preset = Preset::default();
        assert_eq!(preset, Preset::Balanced);
    }
}
