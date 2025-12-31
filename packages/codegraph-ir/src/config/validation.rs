//! Configuration validation
//!
//! Provides validation traits and validators for configuration.
//!
//! ## SOLID Compliance
//! - **D (Dependency Inversion)**: Code depends on `Validatable` trait, not concrete types
//! - **I (Interface Segregation)**: Minimal `Validatable` interface
//! - **O (Open/Closed)**: New configs implement `Validatable` without modifying existing code

use super::error::{ConfigError, ConfigResult, WarningSeverity};
use super::pipeline_config::PipelineConfig;

// ═══════════════════════════════════════════════════════════════════════════
// Validatable Trait (DIP - Dependency Inversion Principle)
// ═══════════════════════════════════════════════════════════════════════════

/// Trait for validatable configuration objects
///
/// # SOLID Compliance
/// - **D**: Application code depends on this trait, not concrete config types
/// - **I**: Minimal interface - only `validate()` required
/// - **L**: Any implementor can substitute another in validation contexts
///
/// # Example
/// ```rust,ignore
/// use config::validation::Validatable;
///
/// fn build_stage<C: Validatable>(config: C) -> Result<Stage, ConfigError> {
///     config.validate()?;  // Works with any Validatable config
///     // ... build stage
/// }
/// ```
pub trait Validatable {
    /// Validate the configuration
    ///
    /// Returns `Ok(())` if valid, `Err(ConfigError)` with details if invalid.
    fn validate(&self) -> ConfigResult<()>;

    /// Get the configuration name for error messages
    fn config_name(&self) -> &'static str {
        "Config"
    }
}

/// Extension trait for validating collections of configs
pub trait ValidatableCollection {
    /// Validate all configs in collection
    fn validate_all(&self) -> ConfigResult<()>;
}

impl<T: Validatable> ValidatableCollection for Vec<T> {
    fn validate_all(&self) -> ConfigResult<()> {
        for config in self {
            config.validate()?;
        }
        Ok(())
    }
}

impl<T: Validatable> ValidatableCollection for Option<T> {
    fn validate_all(&self) -> ConfigResult<()> {
        if let Some(config) = self {
            config.validate()?;
        }
        Ok(())
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Validator Structs
// ═══════════════════════════════════════════════════════════════════════════

/// Configuration validator
pub struct ConfigValidator;

impl ConfigValidator {
    /// Validate complete configuration
    pub fn validate(config: &PipelineConfig) -> ConfigResult<()> {
        // Individual stage validation is done in build()
        // This can be used for additional global validation

        Ok(())
    }

    /// Validate any Validatable config
    pub fn validate_config<V: Validatable>(config: &V) -> ConfigResult<()> {
        config.validate()
    }
}

/// Cross-stage validator
pub struct CrossStageValidator;

impl CrossStageValidator {
    /// Validate cross-stage dependencies
    pub fn validate(config: &PipelineConfig) -> ConfigResult<()> {
        // Cross-stage validation is done in build()
        // This can be used for additional dependency checks

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::super::preset::Preset;
    use super::super::stage_configs::PTAMode;
    use super::*;

    #[test]
    fn test_config_validator() {
        let config = PipelineConfig::preset(Preset::Balanced);
        assert!(ConfigValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_config_validator_fast_preset() {
        let config = PipelineConfig::preset(Preset::Fast);
        assert!(ConfigValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_config_validator_thorough_preset() {
        let config = PipelineConfig::preset(Preset::Thorough);
        assert!(ConfigValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_config_validator_with_taint() {
        let config = PipelineConfig::preset(Preset::Balanced).taint(|c| c.max_depth(50));
        assert!(ConfigValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_config_validator_with_pta() {
        let config = PipelineConfig::preset(Preset::Balanced).pta(|c| c.mode(PTAMode::Fast));
        assert!(ConfigValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_cross_stage_validator() {
        let config = PipelineConfig::preset(Preset::Balanced);
        assert!(CrossStageValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_cross_stage_validator_with_dependencies() {
        let config = PipelineConfig::preset(Preset::Balanced)
            .taint(|c| c.max_depth(50))
            .pta(|c| c.mode(PTAMode::Fast));
        assert!(CrossStageValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_cross_stage_validator_multiple_stages() {
        let config = PipelineConfig::preset(Preset::Thorough)
            .taint(|c| c.max_depth(100).field_sensitive(true))
            .pta(|c| c.mode(PTAMode::Precise).field_sensitive(true));
        assert!(CrossStageValidator::validate(&config).is_ok());
    }

    #[test]
    fn test_validator_empty_config() {
        let config = PipelineConfig::preset(Preset::Fast);
        assert!(ConfigValidator::validate(&config).is_ok());
        assert!(CrossStageValidator::validate(&config).is_ok());
    }
}
