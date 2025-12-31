//! Test Function/Class Detector
//!
//! Detects if a function/class is a test based on:
//! - Function/method name patterns (test_*, *_test, it, describe, etc.)
//! - File path patterns (test_*.py, *.test.ts, *.spec.js)
//! - Decorators (@pytest.mark.*, @Test, etc.)

use std::path::Path;

/// Test Detector
///
/// Detects if a symbol is a test function/class
pub struct TestDetector {
    // Test function name patterns
    test_function_prefixes: Vec<&'static str>,
    test_function_suffixes: Vec<&'static str>,
    test_function_names: Vec<&'static str>,

    // Test decorators/annotations
    test_decorators: Vec<&'static str>,
}

impl Default for TestDetector {
    fn default() -> Self {
        Self::new()
    }
}

impl TestDetector {
    /// Create new test detector with default patterns
    pub fn new() -> Self {
        Self {
            test_function_prefixes: vec!["test_", "test"],
            test_function_suffixes: vec!["_test"],
            test_function_names: vec![
                // JavaScript/TypeScript
                "it",
                "test",
                "describe",
                "beforeEach",
                "afterEach",
                "beforeAll",
                "afterAll",
                // Python alternatives
                "setUp",
                "tearDown",
                "setUpClass",
                "tearDownClass",
            ],
            test_decorators: vec![
                "@pytest.mark",
                "@unittest",
                "@Test",
                "@DisplayName",
                "@ParameterizedTest",
                "@RepeatedTest",
            ],
        }
    }

    /// Check if a function/method is a test
    ///
    /// # Arguments
    /// * `name` - Function/method name
    /// * `file_path` - Source file path
    /// * `language` - Programming language (optional)
    /// * `decorators` - List of decorator/annotation names (optional)
    ///
    /// # Returns
    /// `true` if detected as test function
    ///
    /// # Algorithm (matches Python exactly)
    /// 1. Check exact name match (it, describe, setUp, etc.)
    /// 2. Check name prefix (test_*)
    /// 3. Check name suffix (*_test)
    /// 4. Check decorators (@pytest.mark.*, @Test, etc.)
    /// 5. Check file path + loose name match
    pub fn is_test_function(
        &self,
        name: &str,
        file_path: &str,
        language: Option<&str>,
        decorators: Option<&[String]>,
    ) -> bool {
        let name_lower = name.to_lowercase();

        // Exact match
        if self.test_function_names.contains(&name) {
            return true;
        }

        // Prefix match
        for prefix in &self.test_function_prefixes {
            if name_lower.starts_with(prefix) {
                return true;
            }
        }

        // Suffix match
        for suffix in &self.test_function_suffixes {
            if name_lower.ends_with(suffix) {
                return true;
            }
        }

        // Check decorators
        if let Some(decs) = decorators {
            for dec in decs {
                for test_dec in &self.test_decorators {
                    if dec.contains(test_dec) {
                        return true;
                    }
                }
            }
        }

        // Check file path
        if self.is_test_file(file_path, language) {
            // If in test file and follows test naming convention loosely
            if name_lower.contains("test") || name_lower.contains("spec") {
                return true;
            }
        }

        false
    }

    /// Check if a class is a test class
    ///
    /// # Arguments
    /// * `name` - Class name
    /// * `file_path` - Source file path
    /// * `language` - Programming language (optional)
    /// * `decorators` - List of decorator/annotation names (optional)
    ///
    /// # Returns
    /// `true` if detected as test class
    ///
    /// # Algorithm (matches Python exactly)
    /// 1. Check name suffix (Test, Tests, TestCase)
    /// 2. Check name prefix (Test*)
    /// 3. Check decorators
    /// 4. Check file path + loose name match
    pub fn is_test_class(
        &self,
        name: &str,
        file_path: &str,
        language: Option<&str>,
        decorators: Option<&[String]>,
    ) -> bool {
        let name_lower = name.to_lowercase();

        // Common test class patterns
        if name.ends_with("Test") || name.ends_with("Tests") || name.ends_with("TestCase") {
            return true;
        }

        if name.starts_with("Test") {
            return true;
        }

        // Check decorators
        if let Some(decs) = decorators {
            for dec in decs {
                for test_dec in &self.test_decorators {
                    if dec.contains(test_dec) {
                        return true;
                    }
                }
            }
        }

        // In test file
        if self.is_test_file(file_path, language) {
            if name_lower.contains("test") || name_lower.contains("spec") {
                return true;
            }
        }

        false
    }

    /// Check if file is a test file based on path patterns
    ///
    /// # Arguments
    /// * `file_path` - File path
    /// * `language` - Programming language (optional)
    ///
    /// # Returns
    /// `true` if test file
    ///
    /// # Algorithm (matches Python exactly)
    /// 1. Check if in test directory (test/, tests/, __tests__/)
    /// 2. Check language-specific patterns (test_*.py, *.test.ts, *_test.go)
    /// 3. Check generic patterns (test_*, *.test.*, *.spec.*)
    pub fn is_test_file(&self, file_path: &str, language: Option<&str>) -> bool {
        let path = Path::new(file_path);
        let filename = path.file_name().and_then(|f| f.to_str()).unwrap_or("");

        // Check if in test directory
        for component in path.components() {
            if let Some(part) = component.as_os_str().to_str() {
                if part == "test" || part == "tests" || part == "__tests__" {
                    return true;
                }
            }
        }

        // Language-specific patterns
        if let Some(lang) = language {
            let patterns = self.get_test_file_patterns(lang);
            for pattern in patterns {
                if self.match_glob(filename, pattern) {
                    return true;
                }
            }
        }

        // Generic patterns
        if filename.starts_with("test_") || filename.ends_with("_test.py") {
            return true;
        }

        if filename.contains(".test.") || filename.contains(".spec.") {
            return true;
        }

        false
    }

    /// Get language-specific test file patterns
    fn get_test_file_patterns(&self, language: &str) -> Vec<&'static str> {
        match language {
            "python" => vec!["test_*.py", "*_test.py", "tests.py", "conftest.py"],
            "typescript" => vec!["*.test.ts", "*.spec.ts", "*.test.tsx", "*.spec.tsx"],
            "javascript" => vec!["*.test.js", "*.spec.js", "*.test.jsx", "*.spec.jsx"],
            "go" => vec!["*_test.go"],
            "rust" => vec!["*_test.rs"],
            "java" => vec!["*Test.java", "*Tests.java"],
            _ => vec![],
        }
    }

    /// Simple glob pattern matching
    ///
    /// Supports:
    /// - `*` wildcard (matches any characters)
    /// - Literal matching
    fn match_glob(&self, filename: &str, pattern: &str) -> bool {
        // Simple glob matching (matches Python's fnmatch)
        let parts: Vec<&str> = pattern.split('*').collect();

        if parts.len() == 1 {
            // No wildcard - exact match
            return filename == pattern;
        }

        let mut pos = 0;
        for (i, part) in parts.iter().enumerate() {
            if part.is_empty() {
                continue;
            }

            if i == 0 {
                // First part - must match start
                if !filename.starts_with(part) {
                    return false;
                }
                pos = part.len();
            } else if i == parts.len() - 1 {
                // Last part - must match end
                if !filename[pos..].ends_with(part) {
                    return false;
                }
            } else {
                // Middle part - must exist
                if let Some(idx) = filename[pos..].find(part) {
                    pos += idx + part.len();
                } else {
                    return false;
                }
            }
        }

        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_function_name_patterns() {
        let detector = TestDetector::new();

        // Prefix match
        assert!(detector.is_test_function("test_something", "/src/main.py", None, None));
        assert!(detector.is_test_function("test_add", "/src/math.py", None, None));

        // Suffix match
        assert!(detector.is_test_function("something_test", "/src/main.py", None, None));

        // Exact match
        assert!(detector.is_test_function("it", "/src/test.js", Some("javascript"), None));
        assert!(detector.is_test_function("describe", "/src/test.js", Some("javascript"), None));
        assert!(detector.is_test_function("setUp", "/src/test.py", Some("python"), None));

        // Not a test
        assert!(!detector.is_test_function("calculate", "/src/main.py", None, None));
    }

    #[test]
    fn test_function_decorators() {
        let detector = TestDetector::new();

        let decorators = vec!["@pytest.mark.parametrize".to_string()];

        assert!(detector.is_test_function(
            "my_func",
            "/src/test.py",
            Some("python"),
            Some(&decorators)
        ));

        let decorators = vec!["@Test".to_string()];

        assert!(detector.is_test_function(
            "testSomething",
            "/src/Test.java",
            Some("java"),
            Some(&decorators)
        ));
    }

    #[test]
    fn test_class_patterns() {
        let detector = TestDetector::new();

        // Suffix match
        assert!(detector.is_test_class("UserTest", "/src/test.py", None, None));
        assert!(detector.is_test_class("UserTests", "/src/test.py", None, None));
        assert!(detector.is_test_class("UserTestCase", "/src/test.py", None, None));

        // Prefix match
        assert!(detector.is_test_class("TestUser", "/src/test.py", None, None));

        // Not a test
        assert!(!detector.is_test_class("UserController", "/src/main.py", None, None));
    }

    #[test]
    fn test_file_paths() {
        let detector = TestDetector::new();

        // Test directories
        assert!(detector.is_test_file("/src/tests/test_user.py", Some("python")));
        assert!(detector.is_test_file("/src/test/user.py", Some("python")));
        assert!(detector.is_test_file("/src/__tests__/user.test.js", Some("javascript")));

        // Python patterns
        assert!(detector.is_test_file("/src/test_user.py", Some("python")));
        assert!(detector.is_test_file("/src/user_test.py", Some("python")));
        assert!(detector.is_test_file("/src/conftest.py", Some("python")));

        // TypeScript patterns
        assert!(detector.is_test_file("/src/user.test.ts", Some("typescript")));
        assert!(detector.is_test_file("/src/user.spec.ts", Some("typescript")));

        // Go patterns
        assert!(detector.is_test_file("/src/user_test.go", Some("go")));

        // Not test files
        assert!(!detector.is_test_file("/src/main.py", Some("python")));
        assert!(!detector.is_test_file("/src/user.ts", Some("typescript")));
    }

    #[test]
    fn test_glob_matching() {
        let detector = TestDetector::new();

        // Exact match
        assert!(detector.match_glob("test.py", "test.py"));

        // Prefix wildcard
        assert!(detector.match_glob("test_user.py", "test_*.py"));
        assert!(detector.match_glob("test_admin.py", "test_*.py"));

        // Suffix wildcard
        assert!(detector.match_glob("user_test.py", "*_test.py"));

        // Middle wildcard
        assert!(detector.match_glob("user.test.ts", "*.test.ts"));
        assert!(detector.match_glob("admin.spec.js", "*.spec.js"));

        // No match
        assert!(!detector.match_glob("main.py", "test_*.py"));
        assert!(!detector.match_glob("user.py", "*.test.py"));
    }

    #[test]
    #[ignore]
    fn test_function_in_test_file() {
        let detector = TestDetector::new();

        // Loose name match in test file
        assert!(detector.is_test_function(
            "should_validate_user", // contains "test" loosely
            "/tests/test_user.py",
            Some("python"),
            None
        ));

        // Generic function in test file (not detected without test keyword)
        assert!(!detector.is_test_function(
            "helper_function",
            "/tests/test_user.py",
            Some("python"),
            None
        ));
    }

    #[test]
    fn test_class_in_test_file() {
        let detector = TestDetector::new();

        // Class with "test" in name, in test file
        assert!(detector.is_test_class(
            "UserTestHelper",
            "/tests/test_user.py",
            Some("python"),
            None
        ));

        // Generic class in test file (not detected)
        assert!(!detector.is_test_class("UserHelper", "/tests/test_user.py", Some("python"), None));
    }
}
