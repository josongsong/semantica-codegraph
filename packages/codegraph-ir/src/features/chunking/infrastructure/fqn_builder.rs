//! FQN (Fully Qualified Name) Builder
//!
//! Provides centralized, consistent FQN generation for all chunk types.
//!
//! MATCHES: Python FQNBuilder in chunk/fqn_builder.py
//!
//! Ensures:
//! - Consistent FQN format across all chunk levels
//! - Language-specific handling
//! - Proper dotted notation
//!
//! Performance optimizations:
//! - Zero-copy with `Cow<str>` where possible
//! - Compile-time const for language extensions

use std::borrow::Cow;

/// FQN Builder for chunks
///
/// Centralized FQN generation across:
/// Repo → Project → Module → File → Class → Function
pub struct FQNBuilder;

impl FQNBuilder {
    /// Generate FQN from file path
    ///
    /// # Algorithm
    ///
    /// 1. Remove language-specific extension (.py, .ts, .rs, etc)
    /// 2. Replace path separators (/ or \) with dots
    ///
    /// # Examples
    ///
    /// ```
    /// use codegraph_ir::features::chunking::infrastructure::fqn_builder::FQNBuilder;
    ///
    /// assert_eq!(
    ///     FQNBuilder::from_file_path("backend/api/routes.py", "python"),
    ///     "backend.api.routes"
    /// );
    ///
    /// assert_eq!(
    ///     FQNBuilder::from_file_path("src/main.ts", "typescript"),
    ///     "src.main"
    /// );
    ///
    /// // Windows paths supported
    /// assert_eq!(
    ///     FQNBuilder::from_file_path("backend\\api\\routes.py", "python"),
    ///     "backend.api.routes"
    /// );
    /// ```
    ///
    /// # Arguments
    ///
    /// * `file_path` - File path (e.g., "backend/api/routes.py")
    /// * `language` - Programming language
    ///
    /// # Returns
    ///
    /// FQN string (e.g., "backend.api.routes")
    pub fn from_file_path(file_path: &str, language: &str) -> String {
        // Remove extension
        let ext = Self::get_extension(language);
        let mut fqn = if file_path.ends_with(ext) {
            Cow::Borrowed(&file_path[..file_path.len() - ext.len()])
        } else {
            Cow::Borrowed(file_path)
        };

        // Replace path separators with dots
        if fqn.contains('/') || fqn.contains('\\') {
            let replaced = fqn.replace(['/', '\\'], ".");
            fqn = Cow::Owned(replaced);
        }

        fqn.into_owned()
    }

    /// Generate FQN from module path parts
    ///
    /// # Examples
    ///
    /// ```
    /// use codegraph_ir::features::chunking::infrastructure::fqn_builder::FQNBuilder;
    ///
    /// assert_eq!(
    ///     FQNBuilder::from_module_path(&["backend", "api"]),
    ///     "backend.api"
    /// );
    /// ```
    ///
    /// # Arguments
    ///
    /// * `parts` - Module path components (e.g., ["backend", "api"])
    ///
    /// # Returns
    ///
    /// FQN string (e.g., "backend.api")
    pub fn from_module_path(parts: &[&str]) -> String {
        parts.join(".")
    }

    /// Generate FQN for a symbol (class/function)
    ///
    /// # Examples
    ///
    /// ```
    /// use codegraph_ir::features::chunking::infrastructure::fqn_builder::FQNBuilder;
    ///
    /// assert_eq!(
    ///     FQNBuilder::from_symbol("backend.api.routes", "UserController"),
    ///     "backend.api.routes.UserController"
    /// );
    ///
    /// assert_eq!(
    ///     FQNBuilder::from_symbol("backend.api.routes.UserController", "get_user"),
    ///     "backend.api.routes.UserController.get_user"
    /// );
    ///
    /// // Empty parent
    /// assert_eq!(
    ///     FQNBuilder::from_symbol("", "UserController"),
    ///     "UserController"
    /// );
    /// ```
    ///
    /// # Arguments
    ///
    /// * `parent_fqn` - Parent's FQN (e.g., "backend.api.routes")
    /// * `symbol_name` - Symbol name (e.g., "UserController")
    ///
    /// # Returns
    ///
    /// FQN string (e.g., "backend.api.routes.UserController")
    pub fn from_symbol(parent_fqn: &str, symbol_name: &str) -> String {
        if parent_fqn.is_empty() {
            symbol_name.to_string()
        } else {
            format!("{}.{}", parent_fqn, symbol_name)
        }
    }

    /// Extract parent FQN from a full FQN
    ///
    /// # Examples
    ///
    /// ```
    /// use codegraph_ir::features::chunking::infrastructure::fqn_builder::FQNBuilder;
    ///
    /// assert_eq!(
    ///     FQNBuilder::get_parent_fqn("backend.api.routes.UserController"),
    ///     Some("backend.api.routes".to_string())
    /// );
    ///
    /// assert_eq!(
    ///     FQNBuilder::get_parent_fqn("backend"),
    ///     None
    /// );
    /// ```
    ///
    /// # Arguments
    ///
    /// * `fqn` - Full FQN (e.g., "backend.api.routes.UserController")
    ///
    /// # Returns
    ///
    /// Parent FQN (e.g., "backend.api.routes") or None if root
    pub fn get_parent_fqn(fqn: &str) -> Option<String> {
        fqn.rsplit_once('.').map(|(parent, _)| parent.to_string())
    }

    /// Extract symbol name from FQN
    ///
    /// # Examples
    ///
    /// ```
    /// use codegraph_ir::features::chunking::infrastructure::fqn_builder::FQNBuilder;
    ///
    /// assert_eq!(
    ///     FQNBuilder::get_symbol_name("backend.api.routes.UserController"),
    ///     "UserController"
    /// );
    ///
    /// assert_eq!(
    ///     FQNBuilder::get_symbol_name("backend"),
    ///     "backend"
    /// );
    /// ```
    ///
    /// # Arguments
    ///
    /// * `fqn` - Full FQN (e.g., "backend.api.routes.UserController")
    ///
    /// # Returns
    ///
    /// Symbol name (e.g., "UserController")
    pub fn get_symbol_name(fqn: &str) -> &str {
        fqn.rsplit('.').next().unwrap_or(fqn)
    }

    /// Get file extension for language
    ///
    /// # Arguments
    ///
    /// * `language` - Programming language
    ///
    /// # Returns
    ///
    /// File extension (e.g., ".py" for Python)
    fn get_extension(language: &str) -> &'static str {
        match language.to_lowercase().as_str() {
            "python" => ".py",
            "typescript" => ".ts",
            "javascript" => ".js",
            "go" => ".go",
            "rust" => ".rs",
            "java" => ".java",
            "cpp" | "c++" => ".cpp",
            "c" => ".c",
            "kotlin" => ".kt",
            "swift" => ".swift",
            "ruby" => ".rb",
            "php" => ".php",
            _ => ".py", // Default fallback
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_from_file_path() {
        // Python
        assert_eq!(
            FQNBuilder::from_file_path("backend/api/routes.py", "python"),
            "backend.api.routes"
        );

        // TypeScript
        assert_eq!(
            FQNBuilder::from_file_path("src/main.ts", "typescript"),
            "src.main"
        );

        // Rust
        assert_eq!(FQNBuilder::from_file_path("src/lib.rs", "rust"), "src.lib");

        // Windows paths
        assert_eq!(
            FQNBuilder::from_file_path("backend\\api\\routes.py", "python"),
            "backend.api.routes"
        );

        // Mixed separators
        assert_eq!(
            FQNBuilder::from_file_path("backend/api\\routes.py", "python"),
            "backend.api.routes"
        );

        // No extension
        assert_eq!(
            FQNBuilder::from_file_path("backend/api/routes", "python"),
            "backend.api.routes"
        );
    }

    #[test]
    fn test_from_module_path() {
        assert_eq!(
            FQNBuilder::from_module_path(&["backend", "api"]),
            "backend.api"
        );

        assert_eq!(FQNBuilder::from_module_path(&["main"]), "main");

        assert_eq!(FQNBuilder::from_module_path(&[]), "");
    }

    #[test]
    fn test_from_symbol() {
        // Normal case
        assert_eq!(
            FQNBuilder::from_symbol("backend.api.routes", "UserController"),
            "backend.api.routes.UserController"
        );

        // Nested symbol
        assert_eq!(
            FQNBuilder::from_symbol("backend.api.routes.UserController", "get_user"),
            "backend.api.routes.UserController.get_user"
        );

        // Empty parent (root symbol)
        assert_eq!(
            FQNBuilder::from_symbol("", "UserController"),
            "UserController"
        );
    }

    #[test]
    fn test_get_parent_fqn() {
        // Multi-level FQN
        assert_eq!(
            FQNBuilder::get_parent_fqn("backend.api.routes.UserController"),
            Some("backend.api.routes".to_string())
        );

        // Two-level FQN
        assert_eq!(
            FQNBuilder::get_parent_fqn("backend.api"),
            Some("backend".to_string())
        );

        // Single-level FQN (no parent)
        assert_eq!(FQNBuilder::get_parent_fqn("backend"), None);

        // Empty FQN
        assert_eq!(FQNBuilder::get_parent_fqn(""), None);
    }

    #[test]
    fn test_get_symbol_name() {
        // Multi-level FQN
        assert_eq!(
            FQNBuilder::get_symbol_name("backend.api.routes.UserController"),
            "UserController"
        );

        // Single-level FQN
        assert_eq!(FQNBuilder::get_symbol_name("backend"), "backend");

        // Empty FQN
        assert_eq!(FQNBuilder::get_symbol_name(""), "");
    }

    #[test]
    fn test_get_extension() {
        assert_eq!(FQNBuilder::get_extension("python"), ".py");
        assert_eq!(FQNBuilder::get_extension("Python"), ".py"); // Case-insensitive
        assert_eq!(FQNBuilder::get_extension("typescript"), ".ts");
        assert_eq!(FQNBuilder::get_extension("javascript"), ".js");
        assert_eq!(FQNBuilder::get_extension("go"), ".go");
        assert_eq!(FQNBuilder::get_extension("rust"), ".rs");
        assert_eq!(FQNBuilder::get_extension("java"), ".java");
        assert_eq!(FQNBuilder::get_extension("cpp"), ".cpp");
        assert_eq!(FQNBuilder::get_extension("C++"), ".cpp");
        assert_eq!(FQNBuilder::get_extension("c"), ".c");
        assert_eq!(FQNBuilder::get_extension("kotlin"), ".kt");
        assert_eq!(FQNBuilder::get_extension("swift"), ".swift");
        assert_eq!(FQNBuilder::get_extension("ruby"), ".rb");
        assert_eq!(FQNBuilder::get_extension("php"), ".php");
        assert_eq!(FQNBuilder::get_extension("unknown"), ".py"); // Default
    }

    #[test]
    fn test_round_trip() {
        // File path → FQN → Parent FQN → Symbol name
        let file_path = "backend/api/routes.py";
        let fqn = FQNBuilder::from_file_path(file_path, "python");
        assert_eq!(fqn, "backend.api.routes");

        // Add symbol
        let class_fqn = FQNBuilder::from_symbol(&fqn, "UserController");
        assert_eq!(class_fqn, "backend.api.routes.UserController");

        // Extract parent
        let parent = FQNBuilder::get_parent_fqn(&class_fqn);
        assert_eq!(parent, Some("backend.api.routes".to_string()));

        // Extract symbol name
        let symbol = FQNBuilder::get_symbol_name(&class_fqn);
        assert_eq!(symbol, "UserController");
    }
}
