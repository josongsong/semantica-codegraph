//! Configuration I/O (YAML/Env loading)
//!
//! Defines YAML schema types. Implementation methods are in pipeline_config.rs
//! to avoid field visibility issues.

use super::{pipeline_config::StageControl, stage_configs::*, CacheConfig, PageRankConfig};
use serde::{Deserialize, Serialize};

/// YAML Schema v1
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConfigExportV1 {
    /// Schema version (always 1 for v1)
    pub version: u32,

    /// Base preset
    pub preset: String,

    /// Stage on/off switches
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stages: Option<StageControl>,

    /// Fine-grained overrides
    #[serde(skip_serializing_if = "Option::is_none")]
    pub overrides: Option<ConfigOverrides>,
}

/// Configuration overrides
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConfigOverrides {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub taint: Option<TaintConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub pta: Option<PTAConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub clone: Option<CloneConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub pagerank: Option<PageRankConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub chunking: Option<ChunkingConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub lexical: Option<LexicalConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub parallel: Option<ParallelConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache: Option<CacheConfig>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub heap: Option<HeapConfig>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::error::ConfigError;
    use crate::config::{PipelineConfig, Preset};
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_yaml_roundtrip() {
        let config = PipelineConfig::preset(Preset::Balanced).taint(|c| c.max_depth(50));

        let yaml = config.to_yaml().unwrap();
        assert!(yaml.contains("version: 1"));
        assert!(yaml.contains("preset: balanced"));
        assert!(yaml.contains("max_depth: 50"));
    }

    #[test]
    fn test_yaml_loading() {
        let yaml_content = r#"
version: 1
preset: fast
stages:
  taint: true
  pta: true
overrides:
  taint:
    max_depth: 50
    max_paths: 1000
    use_points_to: true
    field_sensitive: false
    use_ssa: false
    detect_sanitizers: false
    enable_interprocedural: false
    worklist_max_iterations: 100
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(yaml_content.as_bytes()).unwrap();
        let path = temp_file.path().to_str().unwrap();

        let config = PipelineConfig::from_yaml(path).unwrap();
        let taint = config.taint().unwrap();
        assert_eq!(taint.max_depth, 50);
        assert_eq!(taint.max_paths, 1000);
    }

    #[test]
    fn test_yaml_missing_version() {
        let yaml_content = r#"
preset: fast
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(yaml_content.as_bytes()).unwrap();
        let path = temp_file.path().to_str().unwrap();

        let result = PipelineConfig::from_yaml(path);
        assert!(result.is_err());
    }

    #[test]
    fn test_yaml_unsupported_version() {
        let yaml_content = r#"
version: 2
preset: fast
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(yaml_content.as_bytes()).unwrap();
        let path = temp_file.path().to_str().unwrap();

        let result = PipelineConfig::from_yaml(path);
        assert!(result.is_err());
        assert!(matches!(
            result.unwrap_err(),
            ConfigError::UnsupportedVersion { .. }
        ));
    }
}
