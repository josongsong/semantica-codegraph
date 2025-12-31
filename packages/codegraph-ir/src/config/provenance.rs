//! Configuration provenance tracking
//!
//! Track where each configuration value came from (preset, YAML, env, builder)

use super::preset::Preset;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Configuration provenance tracking
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigProvenance {
    /// Base preset used
    preset: Preset,

    /// Field-level tracking: field path → source
    /// Example: "taint.max_depth" → ConfigSource::Env("CODEGRAPH__TAINT__MAX_DEPTH")
    field_sources: HashMap<String, ConfigSource>,
}

/// Configuration source
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConfigSource {
    /// From preset defaults
    Preset(Preset),

    /// From YAML file (v1: path only, no line tracking)
    Yaml { path: String },

    /// From environment variable
    Env(String),

    /// From builder API
    Builder,
}

impl ConfigProvenance {
    /// Create from preset
    pub fn from_preset(preset: Preset) -> Self {
        Self {
            preset,
            field_sources: HashMap::new(),
        }
    }

    /// Record field-level override
    pub fn track_field(&mut self, field_path: &str, source: ConfigSource) {
        self.field_sources.insert(field_path.to_string(), source);
    }

    /// Get source for a specific field
    pub fn get_source(&self, field_path: &str) -> Option<&ConfigSource> {
        self.field_sources.get(field_path)
    }

    /// Get base preset
    pub fn preset(&self) -> Preset {
        self.preset
    }

    /// Get all field sources
    pub fn field_sources(&self) -> &HashMap<String, ConfigSource> {
        &self.field_sources
    }

    /// Get human-readable summary
    pub fn summary(&self) -> String {
        let mut lines = vec![format!("Base preset: {:?}", self.preset)];

        if !self.field_sources.is_empty() {
            lines.push("\nOverridden fields:".to_string());

            let mut sorted_fields: Vec<_> = self.field_sources.iter().collect();
            sorted_fields.sort_by_key(|(k, _)| *k);

            for (field, source) in sorted_fields {
                let source_str = match source {
                    ConfigSource::Preset(p) => format!("preset {:?}", p),
                    ConfigSource::Yaml { path } => format!("{}", path),
                    ConfigSource::Env(var) => format!("env ${}", var),
                    ConfigSource::Builder => "builder API".to_string(),
                };
                lines.push(format!("  {} ← {}", field, source_str));
            }
        }

        lines.join("\n")
    }
}

impl ConfigSource {
    /// Get a short description
    pub fn describe(&self) -> String {
        match self {
            ConfigSource::Preset(p) => format!("preset:{}", p),
            ConfigSource::Yaml { path } => format!("yaml:{}", path),
            ConfigSource::Env(var) => format!("env:{}", var),
            ConfigSource::Builder => "builder".to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_provenance_tracking() {
        let mut prov = ConfigProvenance::from_preset(Preset::Balanced);
        assert_eq!(prov.preset(), Preset::Balanced);
        assert!(prov.field_sources().is_empty());

        prov.track_field("taint.max_depth", ConfigSource::Builder);
        assert_eq!(prov.field_sources().len(), 1);

        let source = prov.get_source("taint.max_depth").unwrap();
        assert!(matches!(source, ConfigSource::Builder));
    }

    #[test]
    fn test_provenance_summary() {
        let mut prov = ConfigProvenance::from_preset(Preset::Fast);
        prov.track_field("taint.max_depth", ConfigSource::Builder);
        prov.track_field(
            "pta.mode",
            ConfigSource::Yaml {
                path: "team.yaml".to_string(),
            },
        );

        let summary = prov.summary();
        assert!(summary.contains("Fast"));
        assert!(summary.contains("taint.max_depth"));
        assert!(summary.contains("builder API"));
        assert!(summary.contains("pta.mode"));
        assert!(summary.contains("team.yaml"));
    }

    #[test]
    fn test_source_describe() {
        let source = ConfigSource::Preset(Preset::Balanced);
        assert_eq!(source.describe(), "preset:balanced");

        let source = ConfigSource::Builder;
        assert_eq!(source.describe(), "builder");

        let source = ConfigSource::Env("CODEGRAPH__TAINT__MAX_DEPTH".to_string());
        assert_eq!(source.describe(), "env:CODEGRAPH__TAINT__MAX_DEPTH");
    }

    #[test]
    fn test_provenance_from_preset() {
        let prov = ConfigProvenance::from_preset(Preset::Fast);
        assert_eq!(prov.preset(), Preset::Fast);
        assert!(prov.field_sources().is_empty());

        let prov2 = ConfigProvenance::from_preset(Preset::Thorough);
        assert_eq!(prov2.preset(), Preset::Thorough);
    }

    #[test]
    fn test_multiple_field_tracking() {
        let mut prov = ConfigProvenance::from_preset(Preset::Balanced);

        prov.track_field("taint.max_depth", ConfigSource::Builder);
        prov.track_field(
            "pta.mode",
            ConfigSource::Yaml {
                path: "config.yaml".to_string(),
            },
        );
        prov.track_field(
            "clone.min_tokens",
            ConfigSource::Env("CLONE_MIN_TOKENS".to_string()),
        );

        assert_eq!(prov.field_sources().len(), 3);

        assert!(matches!(
            prov.get_source("taint.max_depth").unwrap(),
            ConfigSource::Builder
        ));

        assert!(matches!(
            prov.get_source("pta.mode").unwrap(),
            ConfigSource::Yaml { .. }
        ));

        assert!(matches!(
            prov.get_source("clone.min_tokens").unwrap(),
            ConfigSource::Env(_)
        ));
    }

    #[test]
    fn test_get_source_nonexistent() {
        let prov = ConfigProvenance::from_preset(Preset::Fast);
        assert!(prov.get_source("nonexistent.field").is_none());
    }

    #[test]
    fn test_field_override() {
        let mut prov = ConfigProvenance::from_preset(Preset::Fast);

        // First override
        prov.track_field("taint.max_depth", ConfigSource::Builder);
        assert!(matches!(
            prov.get_source("taint.max_depth").unwrap(),
            ConfigSource::Builder
        ));

        // Override the same field again (last write wins)
        prov.track_field(
            "taint.max_depth",
            ConfigSource::Env("MAX_DEPTH".to_string()),
        );
        assert!(matches!(
            prov.get_source("taint.max_depth").unwrap(),
            ConfigSource::Env(_)
        ));
    }

    #[test]
    fn test_summary_formatting() {
        let mut prov = ConfigProvenance::from_preset(Preset::Balanced);
        let empty_summary = prov.summary();
        assert!(empty_summary.contains("Balanced"));
        assert!(!empty_summary.contains("Overridden fields"));

        prov.track_field("a.field", ConfigSource::Builder);
        prov.track_field(
            "z.field",
            ConfigSource::Yaml {
                path: "test.yaml".to_string(),
            },
        );
        prov.track_field("m.field", ConfigSource::Env("ENV_VAR".to_string()));

        let summary = prov.summary();
        assert!(summary.contains("Overridden fields"));

        // Check alphabetical sorting (a < m < z)
        let a_pos = summary.find("a.field").unwrap();
        let m_pos = summary.find("m.field").unwrap();
        let z_pos = summary.find("z.field").unwrap();
        assert!(a_pos < m_pos);
        assert!(m_pos < z_pos);
    }

    #[test]
    fn test_yaml_source() {
        let source = ConfigSource::Yaml {
            path: "/path/to/config.yaml".to_string(),
        };

        let desc = source.describe();
        assert!(desc.contains("yaml"));
        assert!(desc.contains("/path/to/config.yaml"));
    }

    #[test]
    fn test_all_preset_sources() {
        let fast_source = ConfigSource::Preset(Preset::Fast);
        assert_eq!(fast_source.describe(), "preset:fast");

        let balanced_source = ConfigSource::Preset(Preset::Balanced);
        assert_eq!(balanced_source.describe(), "preset:balanced");

        let thorough_source = ConfigSource::Preset(Preset::Thorough);
        assert_eq!(thorough_source.describe(), "preset:thorough");
    }
}
