//! Configuration error types

use thiserror::Error;

/// Configuration error type
#[derive(Debug, Error)]
pub enum ConfigError {
    /// Range validation error
    #[error("Invalid range for field '{field}': {value} not in {min}..={max}. {hint}")]
    Range {
        field: String,
        value: String,
        min: String,
        max: String,
        hint: String,
    },

    /// Unknown field in YAML
    #[error("Unknown field '{field}' in stage '{stage}'. {suggestion}")]
    UnknownField {
        field: String,
        stage: String,
        suggestion: String,
        valid_fields: Vec<String>,
    },

    /// Missing version field in YAML
    #[error("Missing 'version' field in configuration file. Add 'version: 1' to the top of your YAML file.")]
    MissingVersion,

    /// Unsupported version
    #[error("Unsupported configuration version {found}. Supported versions: {}", supported.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(", "))]
    UnsupportedVersion { found: u32, supported: Vec<u32> },

    /// Unknown preset name
    #[error("Unknown preset '{0}'. Valid presets: fast, balanced, thorough, custom")]
    UnknownPreset(String),

    /// Disabled stage has overrides (strict mode)
    #[error("Stage '{stage}' is disabled but has configuration overrides. {hint}")]
    DisabledStageOverride { stage: String, hint: String },

    /// Cross-stage conflict
    #[error("Cross-stage configuration conflict: {issue}. Fix: {fix}")]
    CrossStageConflict { issue: String, fix: String },

    /// Cross-stage warning (non-fatal)
    #[error("Configuration warning ({severity:?}): {warning}. Recommendation: {recommendation}")]
    CrossStageWarning {
        warning: String,
        recommendation: String,
        severity: WarningSeverity,
    },

    /// IO error
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    /// YAML parsing error
    #[error("YAML parsing error: {0}")]
    Yaml(#[from] serde_yaml::Error),

    /// Validation error (from validator crate)
    #[error("Validation error: {0}")]
    Validation(String),

    /// Custom error
    #[error("{0}")]
    Custom(String),
}

/// Warning severity for cross-stage validation
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WarningSeverity {
    Low,
    Medium,
    High,
}

/// Configuration result type
pub type ConfigResult<T> = Result<T, ConfigError>;

impl ConfigError {
    /// Create a range error with a hint
    pub fn range_with_hint(
        field: impl Into<String>,
        value: impl ToString,
        min: impl ToString,
        max: impl ToString,
        hint: impl Into<String>,
    ) -> Self {
        Self::Range {
            field: field.into(),
            value: value.to_string(),
            min: min.to_string(),
            max: max.to_string(),
            hint: hint.into(),
        }
    }

    /// Create an unknown field error with suggestion
    pub fn unknown_field_with_suggestion(
        field: impl Into<String>,
        stage: impl Into<String>,
        valid_fields: Vec<String>,
    ) -> Self {
        let field = field.into();
        let suggestion = find_closest_match(&field, &valid_fields);

        Self::UnknownField {
            field,
            stage: stage.into(),
            suggestion,
            valid_fields,
        }
    }
}

/// Find closest match using simple edit distance
fn find_closest_match(target: &str, candidates: &[String]) -> String {
    if candidates.is_empty() {
        return "No valid fields available".to_string();
    }

    let closest = candidates
        .iter()
        .min_by_key(|candidate| levenshtein_distance(target, candidate))
        .unwrap();

    format!("Did you mean '{}'?", closest)
}

/// Simple Levenshtein distance implementation
fn levenshtein_distance(s1: &str, s2: &str) -> usize {
    let len1 = s1.len();
    let len2 = s2.len();
    let mut matrix = vec![vec![0; len2 + 1]; len1 + 1];

    for i in 0..=len1 {
        matrix[i][0] = i;
    }
    for j in 0..=len2 {
        matrix[0][j] = j;
    }

    for (i, c1) in s1.chars().enumerate() {
        for (j, c2) in s2.chars().enumerate() {
            let cost = if c1 == c2 { 0 } else { 1 };
            matrix[i + 1][j + 1] = *[
                matrix[i][j + 1] + 1, // deletion
                matrix[i + 1][j] + 1, // insertion
                matrix[i][j] + cost,  // substitution
            ]
            .iter()
            .min()
            .unwrap();
        }
    }

    matrix[len1][len2]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_levenshtein_distance() {
        // "max_depth" -> "max_depht": delete 't', delete 'h', insert 'h', insert 't' at end = 4 ops
        // or substitute 'th' -> 'ht' = 2 substitutions = 2 ops (correct for Levenshtein)
        // Actually: "max_depth" vs "max_depht" = swap positions of 't' and 'h'
        // Levenshtein: delete one + insert one = 2, OR substitute + substitute = 2
        // Let's verify: "...pth" -> "...pht" needs 2 substitutions minimum
        assert_eq!(levenshtein_distance("kitten", "sitting"), 3); // classic example
        assert_eq!(levenshtein_distance("max_depth", "max_depth"), 0);
        assert_eq!(levenshtein_distance("max_depth", "max_paths"), 4); // depth->paths
    }

    #[test]
    fn test_closest_match() {
        let valid_fields = vec![
            "max_depth".to_string(),
            "max_paths".to_string(),
            "use_points_to".to_string(),
        ];

        let suggestion = find_closest_match("max_depht", &valid_fields);
        assert!(suggestion.contains("max_depth"));
    }

    #[test]
    fn test_error_formatting() {
        let err = ConfigError::range_with_hint(
            "max_depth",
            0,
            1,
            1000,
            "Call chain depth must be at least 1",
        );

        let msg = err.to_string();
        assert!(msg.contains("max_depth"));
        assert!(msg.contains("0"));
        assert!(msg.contains("1..=1000"));
        assert!(msg.contains("Call chain depth"));
    }

    #[test]
    fn test_unknown_field_error() {
        let valid = vec!["max_depth".to_string(), "max_paths".to_string()];
        let err = ConfigError::unknown_field_with_suggestion("max_depht", "taint", valid);

        let msg = err.to_string();
        assert!(msg.contains("max_depht"));
        assert!(msg.contains("taint"));
        assert!(msg.contains("Did you mean"));
    }

    #[test]
    fn test_unsupported_version_error() {
        let err = ConfigError::UnsupportedVersion {
            found: 2,
            supported: vec![1],
        };

        let msg = err.to_string();
        assert!(msg.contains("version 2"));
        assert!(msg.contains("Supported versions: 1"));
    }

    #[test]
    fn test_unknown_preset_error() {
        let err = ConfigError::UnknownPreset("ultra_fast".to_string());
        let msg = err.to_string();
        assert!(msg.contains("ultra_fast"));
        assert!(msg.contains("fast, balanced, thorough"));
    }

    #[test]
    fn test_cross_stage_conflict_error() {
        let err = ConfigError::CrossStageConflict {
            issue: "Taint uses points-to but PTA is disabled".to_string(),
            fix: "Enable PTA stage or set use_points_to=false".to_string(),
        };

        let msg = err.to_string();
        assert!(msg.contains("Taint uses points-to"));
        assert!(msg.contains("Enable PTA"));
    }

    #[test]
    fn test_cross_stage_warning() {
        let warning = ConfigError::CrossStageWarning {
            warning: "Clone detection without chunking may be less effective".to_string(),
            recommendation: "Enable chunking stage".to_string(),
            severity: WarningSeverity::Medium,
        };

        let msg = warning.to_string();
        assert!(msg.contains("Clone detection"));
        assert!(msg.contains("Enable chunking"));
        assert!(msg.contains("Medium"));
    }

    #[test]
    fn test_warning_severity_levels() {
        assert_eq!(WarningSeverity::Low, WarningSeverity::Low);
        assert_ne!(WarningSeverity::Low, WarningSeverity::Medium);
        assert_ne!(WarningSeverity::Medium, WarningSeverity::High);
    }

    #[test]
    fn test_disabled_stage_override_error() {
        let err = ConfigError::DisabledStageOverride {
            stage: "taint".to_string(),
            hint: "Either enable the stage or remove overrides".to_string(),
        };

        let msg = err.to_string();
        assert!(msg.contains("taint"));
        assert!(msg.contains("disabled"));
        assert!(msg.contains("overrides"));
    }

    #[test]
    fn test_missing_version_error() {
        let err = ConfigError::MissingVersion;
        let msg = err.to_string();
        assert!(msg.contains("version"));
        assert!(msg.contains("version: 1"));
    }

    #[test]
    fn test_validation_error() {
        let err = ConfigError::Validation("Invalid value for max_depth".to_string());
        let msg = err.to_string();
        assert!(msg.contains("Validation error"));
        assert!(msg.contains("max_depth"));
    }

    #[test]
    fn test_custom_error() {
        let err = ConfigError::Custom("Something went wrong".to_string());
        let msg = err.to_string();
        assert_eq!(msg, "Something went wrong");
    }

    #[test]
    fn test_levenshtein_edge_cases() {
        assert_eq!(levenshtein_distance("", ""), 0);
        assert_eq!(levenshtein_distance("abc", ""), 3);
        assert_eq!(levenshtein_distance("", "abc"), 3);
        assert_eq!(levenshtein_distance("a", "a"), 0);
        assert_eq!(levenshtein_distance("a", "b"), 1);
    }

    #[test]
    fn test_closest_match_empty_candidates() {
        let empty: Vec<String> = vec![];
        let suggestion = find_closest_match("max_depth", &empty);
        assert!(suggestion.contains("No valid fields"));
    }
}
