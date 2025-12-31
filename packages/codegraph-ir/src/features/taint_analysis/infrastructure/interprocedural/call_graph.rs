//! Call Graph Protocol
//!
//! Trait definition for call graph providers.

/// Call graph protocol
///
/// Any call graph implementation must provide:
/// - get_callees(func) -> list of callees
/// - get_functions() -> list of all functions
///
/// Implementations can use any data structure (petgraph, HashMap, etc.)
pub trait CallGraphProvider {
    /// Get functions called by func_name
    ///
    /// Returns list of callee function names.
    /// Empty list if function makes no calls.
    fn get_callees(&self, func_name: &str) -> Vec<String>;

    /// Get all functions in graph
    ///
    /// Returns complete list of function names in the call graph.
    fn get_functions(&self) -> Vec<String>;

    /// Get callers of a function (reverse call graph)
    ///
    /// Returns list of caller function names.
    /// Default implementation returns empty (override for better performance).
    fn get_callers(&self, _func_name: &str) -> Vec<String> {
        Vec::new()
    }

    /// Check if call graph contains function
    fn contains_function(&self, func_name: &str) -> bool {
        self.get_functions().contains(&func_name.to_string())
    }

    /// Get number of functions in graph
    fn num_functions(&self) -> usize {
        self.get_functions().len()
    }
}

/// Simple HashMap-based call graph implementation
///
/// For testing and simple use cases.
#[derive(Debug, Clone, Default)]
pub struct SimpleCallGraph {
    /// Function name -> List of callees
    calls: std::collections::HashMap<String, Vec<String>>,
}

impl SimpleCallGraph {
    /// Create new empty call graph
    pub fn new() -> Self {
        Self {
            calls: std::collections::HashMap::new(),
        }
    }

    /// Add a call edge
    pub fn add_call(&mut self, caller: String, callee: String) {
        self.calls.entry(caller).or_default().push(callee);
    }

    /// Add function with no calls
    pub fn add_function(&mut self, func: String) {
        self.calls.entry(func).or_default();
    }
}

impl CallGraphProvider for SimpleCallGraph {
    fn get_callees(&self, func_name: &str) -> Vec<String> {
        self.calls.get(func_name).cloned().unwrap_or_default()
    }

    fn get_functions(&self) -> Vec<String> {
        // Collect both callers (keys) and callees (values)
        let mut functions = std::collections::HashSet::new();

        for (caller, callees) in &self.calls {
            functions.insert(caller.clone());
            for callee in callees {
                functions.insert(callee.clone());
            }
        }

        functions.into_iter().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_call_graph() {
        let mut cg = SimpleCallGraph::new();
        cg.add_call("main".to_string(), "foo".to_string());
        cg.add_call("foo".to_string(), "bar".to_string());

        assert_eq!(cg.get_callees("main"), vec!["foo"]);
        assert_eq!(cg.get_callees("foo"), vec!["bar"]);
        assert!(cg.get_callees("bar").is_empty());

        assert_eq!(cg.num_functions(), 3);
    }
}
