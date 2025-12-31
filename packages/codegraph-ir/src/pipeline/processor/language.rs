//! Language detection and plugin selection
//!
//! Extracted from processor.rs lines 1850-1862
//!
//! Maps file extensions to appropriate LanguagePlugin implementations.

use crate::features::parsing::plugins::{
    GoPlugin, JavaPlugin, KotlinPlugin, PythonPlugin, RustPlugin, TypeScriptPlugin,
};
use crate::features::parsing::ports::{LanguageId, LanguagePlugin};

/// Get the appropriate language plugin and LanguageId based on file extension
///
/// # Supported Languages
/// - Python (.py)
/// - Java (.java)
/// - TypeScript (.ts, .tsx)
/// - JavaScript (.js, .jsx)
/// - Kotlin (.kt, .kts)
/// - Rust (.rs)
/// - Go (.go)
///
/// # Arguments
/// * `file_path` - File path with extension
///
/// # Returns
/// Some((plugin, language_id)) if language is supported, None otherwise
pub fn get_plugin_for_file(
    file_path: &str,
) -> Option<(Box<dyn LanguagePlugin + Send + Sync>, LanguageId)> {
    let ext = file_path.rsplit('.').next()?;
    match ext {
        "py" => Some((Box::new(PythonPlugin::new()), LanguageId::Python)),
        "java" => Some((Box::new(JavaPlugin::new()), LanguageId::Java)),
        "ts" | "tsx" => Some((Box::new(TypeScriptPlugin::new()), LanguageId::TypeScript)),
        "js" | "jsx" => Some((Box::new(TypeScriptPlugin::new()), LanguageId::JavaScript)),
        "kt" | "kts" => Some((Box::new(KotlinPlugin::new()), LanguageId::Kotlin)),
        "rs" => Some((Box::new(RustPlugin::new()), LanguageId::Rust)),
        "go" => Some((Box::new(GoPlugin::new()), LanguageId::Go)),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_python_detection() {
        let result = get_plugin_for_file("main.py");
        assert!(result.is_some());
        let (_, lang_id) = result.unwrap();
        assert!(matches!(lang_id, LanguageId::Python));
    }

    #[test]
    fn test_typescript_detection() {
        let result = get_plugin_for_file("app.tsx");
        assert!(result.is_some());
        let (_, lang_id) = result.unwrap();
        assert!(matches!(lang_id, LanguageId::TypeScript));
    }

    #[test]
    fn test_javascript_detection() {
        let result = get_plugin_for_file("script.js");
        assert!(result.is_some());
        let (_, lang_id) = result.unwrap();
        assert!(matches!(lang_id, LanguageId::JavaScript));
    }

    #[test]
    fn test_kotlin_detection() {
        let result = get_plugin_for_file("Main.kt");
        assert!(result.is_some());
        let (_, lang_id) = result.unwrap();
        assert!(matches!(lang_id, LanguageId::Kotlin));
    }

    #[test]
    fn test_rust_detection() {
        let result = get_plugin_for_file("lib.rs");
        assert!(result.is_some());
        let (_, lang_id) = result.unwrap();
        assert!(matches!(lang_id, LanguageId::Rust));
    }

    #[test]
    fn test_go_detection() {
        let result = get_plugin_for_file("main.go");
        assert!(result.is_some());
        let (_, lang_id) = result.unwrap();
        assert!(matches!(lang_id, LanguageId::Go));
    }

    #[test]
    fn test_unsupported_extension() {
        let result = get_plugin_for_file("file.txt");
        assert!(result.is_none());
    }
}
