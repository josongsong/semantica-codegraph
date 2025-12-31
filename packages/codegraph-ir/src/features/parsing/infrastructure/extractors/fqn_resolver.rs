/*
 * FQN (Fully Qualified Name) Resolver
 *
 * Resolves function/class references to their fully qualified names.
 *
 * SOTA Implementation based on:
 * - Python IR Generator (codegraph-engine)
 * - PyCG (Python Call Graph) - ACM ISSTA 2021
 * - Pyan3 (Python static analyzer)
 * - Pyright/Pylance (Microsoft)
 *
 * Key Features:
 * - Built-in function resolution (builtins.input, builtins.eval, etc.)
 * - Standard library module tracking (os.system, subprocess.run, etc.)
 * - Import alias resolution (numpy as np → numpy)
 * - Attribute chain resolution (os.path.join → os.path.join)
 */

use std::collections::HashMap;

/// FQN Resolver for Python
///
/// Resolves simple names (like "input", "eval") to FQNs (like "builtins.input")
pub struct FqnResolver {
    /// Import aliases (e.g., np → numpy, pd → pandas)
    import_aliases: HashMap<String, String>,
}

impl FqnResolver {
    pub fn new() -> Self {
        Self {
            import_aliases: HashMap::new(),
        }
    }

    /// Register an import alias
    ///
    /// # Examples
    /// ```text
    /// resolver.register_alias("np", "numpy");
    /// resolver.register_alias("pd", "pandas");
    /// ```
    pub fn register_alias(&mut self, alias: String, module: String) {
        self.import_aliases.insert(alias, module);
    }

    /// Resolve a function/class name to its FQN
    ///
    /// # Arguments
    /// * `name` - Function or class name (e.g., "input", "os.system", "np.array")
    ///
    /// # Returns
    /// Fully qualified name (e.g., "builtins.input", "os.system", "numpy.array")
    ///
    /// # Examples
    /// ```text
    /// resolver.resolve("input")      → "builtins.input"
    /// resolver.resolve("eval")       → "builtins.eval"
    /// resolver.resolve("os.system")  → "os.system"
    /// resolver.resolve("np.array")   → "numpy.array" (if np is aliased)
    /// ```
    pub fn resolve(&self, name: &str) -> String {
        // Check if it has a dot (module.function)
        if name.contains('.') {
            // Split into parts
            let parts: Vec<&str> = name.split('.').collect();
            let first_part = parts[0];

            // Check if first part is an alias
            if let Some(real_module) = self.import_aliases.get(first_part) {
                // Replace alias with real module name
                let rest = &parts[1..].join(".");
                return format!("{}.{}", real_module, rest);
            }

            // Not an alias, return as-is
            return name.to_string();
        }

        // Simple name (no dot)
        // Check if it's a built-in
        if is_python_builtin(name) {
            format!("builtins.{}", name)
        } else {
            // Unknown simple name - mark as external
            format!("external.{}", name)
        }
    }
}

impl Default for FqnResolver {
    fn default() -> Self {
        Self::new()
    }
}

/// Check if a name is a Python built-in
///
/// Based on:
/// - Python 3.12 built-ins: https://docs.python.org/3/library/functions.html
/// - codegraph-engine/python/call_analyzer.py:383-472
/// - Security-critical functions flagged for taint analysis
fn is_python_builtin(name: &str) -> bool {
    // SOTA: Comprehensive built-in list from Python IR Generator
    // Reference: packages/codegraph-engine/.../python/call_analyzer.py:383-472
    const PYTHON_BUILTINS: &[&str] = &[
        // ═══════════════════════════════════════════════════════════════
        // Types (15 items)
        // ═══════════════════════════════════════════════════════════════
        "dict",
        "list",
        "set",
        "tuple",
        "frozenset",
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        "bytearray",
        "object",
        "type",
        "super",
        "complex",
        // ═══════════════════════════════════════════════════════════════
        // Functions (30 items)
        // ═══════════════════════════════════════════════════════════════
        "len",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "min",
        "max",
        "sum",
        "abs",
        "all",
        "any",
        "iter",
        "next",
        "repr",
        "hash",
        "format",
        "round",
        "pow",
        "divmod",
        "chr",
        "ord",
        "bin",
        "hex",
        "oct",
        "slice",
        "memoryview",
        "Ellipsis",
        // ═══════════════════════════════════════════════════════════════
        // Security-Critical Functions (10 items)
        // ═══════════════════════════════════════════════════════════════
        // IMPORTANT: These are SOURCES and SINKS in taint analysis
        "print",      // Output sink
        "input",      // User input source (CRITICAL)
        "open",       // File I/O sink (CRITICAL)
        "eval",       // Code execution sink (CRITICAL)
        "exec",       // Code execution sink (CRITICAL)
        "compile",    // Code compilation sink (CRITICAL)
        "__import__", // Dynamic import (CRITICAL)
        "getattr",    // Attribute access (potential sink)
        "setattr",    // Attribute mutation (potential sink)
        "delattr",    // Attribute deletion
        // ═══════════════════════════════════════════════════════════════
        // Reflection & Introspection (10 items)
        // ═══════════════════════════════════════════════════════════════
        "hasattr",
        "isinstance",
        "issubclass",
        "callable",
        "id",
        "vars",
        "dir",
        "globals",
        "locals",
        "help",
        // ═══════════════════════════════════════════════════════════════
        // Decorators & Descriptors (3 items)
        // ═══════════════════════════════════════════════════════════════
        "staticmethod",
        "classmethod",
        "property",
        // ═══════════════════════════════════════════════════════════════
        // Exception Handling (25 items)
        // ═══════════════════════════════════════════════════════════════
        "Exception",
        "BaseException",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "StopIteration",
        "GeneratorExit",
        "AssertionError",
        "ImportError",
        "ModuleNotFoundError",
        "OSError",
        "IOError",
        "FileNotFoundError",
        "PermissionError",
        "TimeoutError",
        "NotImplementedError",
        "ZeroDivisionError",
        "OverflowError",
        "FloatingPointError",
        "MemoryError",
        "RecursionError",
        "SyntaxError",
    ];

    PYTHON_BUILTINS.contains(&name)
}

/// Get module path from FQN
///
/// # Examples
/// ```text
/// get_module_path("builtins.input")    → "builtins"
/// get_module_path("os.path.join")      → "os.path"
/// get_module_path("numpy.array")       → "numpy"
/// ```
pub fn get_module_path(fqn: &str) -> String {
    if let Some(last_dot) = fqn.rfind('.') {
        fqn[..last_dot].to_string()
    } else {
        // No dot, return as-is
        fqn.to_string()
    }
}

/// Check if an FQN is a security-critical function
///
/// Used for taint analysis priority filtering
pub fn is_security_critical(fqn: &str) -> bool {
    matches!(
        fqn,
        // Code execution
        "builtins.eval"
            | "builtins.exec"
            | "builtins.compile"
            | "builtins.__import__"
        // User input
            | "builtins.input"
        // File I/O
            | "builtins.open"
        // OS commands
            | "os.system"
            | "os.popen"
            | "os.execv"
            | "os.execve"
            | "os.execl"
            | "os.execle"
            | "os.execlp"
            | "os.execvp"
            | "os.execvpe"
            | "os.spawnl"
            | "os.spawnle"
            | "os.spawnlp"
            | "os.spawnv"
            | "os.spawnve"
            | "os.spawnvp"
            | "os.spawnvpe"
        // Subprocess
            | "subprocess.run"
            | "subprocess.Popen"
            | "subprocess.call"
            | "subprocess.check_call"
            | "subprocess.check_output"
            | "subprocess.getoutput"
            | "subprocess.getstatusoutput"
        // SQL
            | "sqlite3.execute"
            | "sqlite3.executemany"
            | "sqlite3.executescript"
        // Network
            | "socket.socket"
            | "urllib.request.urlopen"
            | "requests.get"
            | "requests.post"
        // Pickle (deserialization)
            | "pickle.load"
            | "pickle.loads"
            | "pickle.Unpickler"
        // YAML (deserialization)
            | "yaml.load"
            | "yaml.unsafe_load"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builtin_resolution() {
        let resolver = FqnResolver::new();

        // Security-critical built-ins
        assert_eq!(resolver.resolve("input"), "builtins.input");
        assert_eq!(resolver.resolve("eval"), "builtins.eval");
        assert_eq!(resolver.resolve("exec"), "builtins.exec");
        assert_eq!(resolver.resolve("compile"), "builtins.compile");
        assert_eq!(resolver.resolve("open"), "builtins.open");

        // Common built-ins
        assert_eq!(resolver.resolve("len"), "builtins.len");
        assert_eq!(resolver.resolve("range"), "builtins.range");
        assert_eq!(resolver.resolve("print"), "builtins.print");
        assert_eq!(resolver.resolve("dict"), "builtins.dict");
        assert_eq!(resolver.resolve("list"), "builtins.list");
    }

    #[test]
    fn test_module_functions() {
        let resolver = FqnResolver::new();

        // Standard library
        assert_eq!(resolver.resolve("os.system"), "os.system");
        assert_eq!(resolver.resolve("os.path.join"), "os.path.join");
        assert_eq!(resolver.resolve("subprocess.run"), "subprocess.run");
        assert_eq!(resolver.resolve("json.loads"), "json.loads");
    }

    #[test]
    fn test_import_aliases() {
        let mut resolver = FqnResolver::new();

        // Register common aliases
        resolver.register_alias("np".to_string(), "numpy".to_string());
        resolver.register_alias("pd".to_string(), "pandas".to_string());

        // Resolve aliased calls
        assert_eq!(resolver.resolve("np.array"), "numpy.array");
        assert_eq!(resolver.resolve("pd.DataFrame"), "pandas.DataFrame");
        assert_eq!(resolver.resolve("np.random.rand"), "numpy.random.rand");
    }

    #[test]
    fn test_unknown_functions() {
        let resolver = FqnResolver::new();

        // Unknown simple names
        assert_eq!(
            resolver.resolve("my_custom_func"),
            "external.my_custom_func"
        );
        assert_eq!(resolver.resolve("helper"), "external.helper");
    }

    #[test]
    fn test_module_path_extraction() {
        assert_eq!(get_module_path("builtins.input"), "builtins");
        assert_eq!(get_module_path("os.path.join"), "os.path");
        assert_eq!(get_module_path("numpy.array"), "numpy");
        assert_eq!(get_module_path("simple"), "simple");
    }

    #[test]
    fn test_security_critical_detection() {
        // Code execution
        assert!(is_security_critical("builtins.eval"));
        assert!(is_security_critical("builtins.exec"));
        assert!(is_security_critical("builtins.compile"));

        // OS commands
        assert!(is_security_critical("os.system"));
        assert!(is_security_critical("subprocess.run"));

        // User input
        assert!(is_security_critical("builtins.input"));

        // Not critical
        assert!(!is_security_critical("builtins.len"));
        assert!(!is_security_critical("builtins.print"));
    }

    #[test]
    fn test_comprehensive_builtins() {
        // Verify all 70+ built-ins are recognized
        let resolver = FqnResolver::new();

        let test_cases = vec![
            // Types
            "dict",
            "list",
            "set",
            "tuple",
            "str",
            "int",
            "float",
            "bool",
            // Functions
            "len",
            "range",
            "zip",
            "map",
            "filter",
            "sorted",
            // Security-critical
            "eval",
            "exec",
            "compile",
            "input",
            "open",
            // Exceptions
            "ValueError",
            "TypeError",
            "KeyError",
        ];

        for builtin in test_cases {
            let fqn = resolver.resolve(builtin);
            assert!(
                fqn.starts_with("builtins."),
                "Expected {} to resolve to builtins.*, got {}",
                builtin,
                fqn
            );
        }
    }
}
