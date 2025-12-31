//! Language plugins
//!
//! Each language has its own plugin implementing the LanguagePlugin trait.
//!
//! SOTA Multi-Language Support:
//! - Python, Java, TypeScript, Kotlin, Rust, Go

pub mod go;
pub mod java;
pub mod kotlin;
pub mod python;
pub mod rust_lang;
pub mod typescript;

pub use go::GoPlugin;
pub use java::JavaPlugin;
pub use kotlin::KotlinPlugin;
pub use python::PythonPlugin;
pub use rust_lang::RustPlugin;
pub use typescript::TypeScriptPlugin;

use crate::features::parsing::ports::{LanguageId, LanguageRegistry};

/// Create a registry with all language plugins registered
pub fn create_full_registry() -> LanguageRegistry {
    let mut registry = LanguageRegistry::new();
    registry.register(Box::new(PythonPlugin::new()));
    registry.register(Box::new(JavaPlugin::new()));
    registry.register(Box::new(TypeScriptPlugin::new()));
    registry.register(Box::new(KotlinPlugin::new()));
    registry.register(Box::new(RustPlugin::new()));
    registry.register(Box::new(GoPlugin::new()));
    registry
}

/// Create a registry with only specific languages
pub fn create_registry(languages: &[LanguageId]) -> LanguageRegistry {
    let mut registry = LanguageRegistry::new();
    for lang in languages {
        match lang {
            LanguageId::Python => registry.register(Box::new(PythonPlugin::new())),
            LanguageId::Java => registry.register(Box::new(JavaPlugin::new())),
            LanguageId::TypeScript | LanguageId::JavaScript => {
                registry.register(Box::new(TypeScriptPlugin::new()))
            }
            LanguageId::Kotlin => registry.register(Box::new(KotlinPlugin::new())),
            LanguageId::Rust => registry.register(Box::new(RustPlugin::new())),
            LanguageId::Go => registry.register(Box::new(GoPlugin::new())),
        }
    }
    registry
}
