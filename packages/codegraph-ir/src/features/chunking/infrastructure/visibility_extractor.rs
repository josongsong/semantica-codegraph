//! Symbol Visibility Extractor
//!
//! Determines symbol visibility (public/internal/private) based on:
//! - Language-specific naming conventions
//! - IR node attributes
//! - Source code annotations
//!
//! Supports:
//! - Python: _private, __dunder
//! - TypeScript/JavaScript: private, protected, public
//! - Go: Uppercase = public, lowercase = private

use std::collections::HashMap;

/// Symbol visibility level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Visibility {
    /// Exported, external API
    Public,
    /// Package/module-internal
    Internal,
    /// Class/file-private
    Private,
}

impl Visibility {
    pub fn as_str(&self) -> &'static str {
        match self {
            Visibility::Public => "public",
            Visibility::Internal => "internal",
            Visibility::Private => "private",
        }
    }

    pub fn from_str(s: &str) -> Self {
        match s {
            "public" => Visibility::Public,
            "internal" => Visibility::Internal,
            "private" => Visibility::Private,
            _ => Visibility::Public, // Default
        }
    }

    pub fn is_public(&self) -> bool {
        matches!(self, Visibility::Public)
    }

    pub fn is_internal(&self) -> bool {
        matches!(self, Visibility::Internal)
    }

    pub fn is_private(&self) -> bool {
        matches!(self, Visibility::Private)
    }
}

/// Visibility Extractor
///
/// Extracts symbol visibility from name and attributes
pub struct VisibilityExtractor;

impl VisibilityExtractor {
    /// Extract visibility from symbol name and attributes
    ///
    /// # Arguments
    /// * `name` - Symbol name
    /// * `language` - Programming language
    /// * `attrs` - Optional attributes (visibility, modifiers)
    ///
    /// # Returns
    /// Visibility level (public/internal/private)
    ///
    /// # Algorithm (matches Python exactly)
    /// 1. Check explicit attrs["visibility"] first
    /// 2. Check attrs["modifiers"] for keywords (private, protected, public)
    /// 3. Language-specific inference from name
    pub fn extract(
        name: &str,
        language: &str,
        attrs: Option<&HashMap<String, String>>,
    ) -> Visibility {
        // 1. Check explicit attrs
        if let Some(attrs) = attrs {
            // Direct visibility attribute
            if let Some(vis) = attrs.get("visibility") {
                return Visibility::from_str(vis);
            }

            // Check modifiers (TypeScript/Java)
            if let Some(modifiers) = attrs.get("modifiers") {
                if modifiers.contains("private") {
                    return Visibility::Private;
                }
                if modifiers.contains("protected") {
                    return Visibility::Internal;
                }
                if modifiers.contains("public") {
                    return Visibility::Public;
                }
            }
        }

        // 2. Language-specific inference from name
        if name.is_empty() {
            return Visibility::Public; // Default
        }

        match language {
            "python" => Self::extract_python(name),
            "typescript" | "javascript" => Self::extract_typescript(name),
            "go" => Self::extract_go(name),
            _ => Visibility::Public, // Default for unknown languages
        }
    }

    /// Python naming conventions:
    /// - `__name__`: Dunder methods (public)
    /// - `__name`: Name mangling (private)
    /// - `_name`: Internal convention (internal)
    /// - `name`: Public
    fn extract_python(name: &str) -> Visibility {
        if name.starts_with("__") && name.ends_with("__") {
            // Dunder methods are public (__init__, __str__, etc.)
            Visibility::Public
        } else if name.starts_with("__") {
            // Name mangling: __private_var
            Visibility::Private
        } else if name.starts_with('_') {
            // Single underscore: _internal
            Visibility::Internal
        } else {
            // Public
            Visibility::Public
        }
    }

    /// TypeScript/JavaScript conventions:
    /// - `#private`: Private fields (ES2022)
    /// - `_internal`: Convention (internal)
    /// - `name`: Public
    ///
    /// Note: Actual private/protected keywords should be in modifiers (checked above)
    fn extract_typescript(name: &str) -> Visibility {
        if name.starts_with('#') {
            // ES2022 private fields
            Visibility::Private
        } else if name.starts_with('_') {
            // Internal convention
            Visibility::Internal
        } else {
            Visibility::Public
        }
    }

    /// Go visibility rules:
    /// - Uppercase first letter: Exported (public)
    /// - Lowercase first letter: Package-private (internal)
    fn extract_go(name: &str) -> Visibility {
        if name.is_empty() {
            return Visibility::Public;
        }

        // SAFETY: name is guaranteed to be non-empty by the check above
        let first_char = name.chars().next().unwrap();
        if first_char.is_uppercase() {
            Visibility::Public
        } else {
            Visibility::Internal
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_python_visibility() {
        // Dunder methods (public)
        assert_eq!(
            VisibilityExtractor::extract("__init__", "python", None),
            Visibility::Public
        );
        assert_eq!(
            VisibilityExtractor::extract("__str__", "python", None),
            Visibility::Public
        );

        // Name mangling (private)
        assert_eq!(
            VisibilityExtractor::extract("__private_var", "python", None),
            Visibility::Private
        );

        // Single underscore (internal)
        assert_eq!(
            VisibilityExtractor::extract("_internal", "python", None),
            Visibility::Internal
        );

        // Public
        assert_eq!(
            VisibilityExtractor::extract("public_func", "python", None),
            Visibility::Public
        );
    }

    #[test]
    fn test_typescript_visibility() {
        // ES2022 private fields
        assert_eq!(
            VisibilityExtractor::extract("#privateField", "typescript", None),
            Visibility::Private
        );

        // Internal convention
        assert_eq!(
            VisibilityExtractor::extract("_internal", "typescript", None),
            Visibility::Internal
        );

        // Public
        assert_eq!(
            VisibilityExtractor::extract("publicMethod", "typescript", None),
            Visibility::Public
        );
    }

    #[test]
    fn test_go_visibility() {
        // Uppercase = exported (public)
        assert_eq!(
            VisibilityExtractor::extract("ExportedFunc", "go", None),
            Visibility::Public
        );

        // Lowercase = package-private (internal)
        assert_eq!(
            VisibilityExtractor::extract("internalFunc", "go", None),
            Visibility::Internal
        );
    }

    #[test]
    fn test_explicit_attrs() {
        let mut attrs = HashMap::new();
        attrs.insert("visibility".to_string(), "private".to_string());

        // Explicit visibility overrides name
        assert_eq!(
            VisibilityExtractor::extract("public_name", "python", Some(&attrs)),
            Visibility::Private
        );
    }

    #[test]
    fn test_modifiers() {
        let mut attrs = HashMap::new();
        attrs.insert("modifiers".to_string(), "private static".to_string());

        assert_eq!(
            VisibilityExtractor::extract("myField", "typescript", Some(&attrs)),
            Visibility::Private
        );

        attrs.insert("modifiers".to_string(), "protected".to_string());
        assert_eq!(
            VisibilityExtractor::extract("myField", "typescript", Some(&attrs)),
            Visibility::Internal
        );

        attrs.insert("modifiers".to_string(), "public".to_string());
        assert_eq!(
            VisibilityExtractor::extract("myField", "typescript", Some(&attrs)),
            Visibility::Public
        );
    }

    #[test]
    fn test_is_methods() {
        assert!(Visibility::Public.is_public());
        assert!(!Visibility::Public.is_internal());
        assert!(!Visibility::Public.is_private());

        assert!(!Visibility::Internal.is_public());
        assert!(Visibility::Internal.is_internal());
        assert!(!Visibility::Internal.is_private());

        assert!(!Visibility::Private.is_public());
        assert!(!Visibility::Private.is_internal());
        assert!(Visibility::Private.is_private());
    }

    #[test]
    fn test_as_str() {
        assert_eq!(Visibility::Public.as_str(), "public");
        assert_eq!(Visibility::Internal.as_str(), "internal");
        assert_eq!(Visibility::Private.as_str(), "private");
    }

    #[test]
    fn test_unknown_language_defaults_to_public() {
        assert_eq!(
            VisibilityExtractor::extract("anyName", "unknown", None),
            Visibility::Public
        );
    }
}
