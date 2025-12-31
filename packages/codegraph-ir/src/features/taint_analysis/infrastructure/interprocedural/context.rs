//! Call Context for Context-Sensitive Analysis
//!
//! Tracks calling context during interprocedural taint analysis.

use std::collections::{HashMap, HashSet};

/// Call context for context-sensitive analysis
///
/// Tracks:
/// - Call stack (which functions called this)
/// - Tainted parameters
/// - Return taint status
#[derive(Debug, Clone)]
pub struct CallContext {
    /// Stack of caller function names
    pub call_stack: Vec<String>,

    /// Tainted parameter indices -> taint sources
    pub tainted_params: HashMap<usize, HashSet<String>>,

    /// Whether return value is tainted
    pub return_tainted: bool,

    /// Call depth (for recursion limiting)
    pub depth: usize,
}

impl CallContext {
    /// Create new empty context
    pub fn new() -> Self {
        Self {
            call_stack: Vec::new(),
            tainted_params: HashMap::new(),
            return_tainted: false,
            depth: 0,
        }
    }

    /// Create context with additional call
    pub fn with_call(&self, func_name: String) -> Self {
        let mut ctx = self.clone();
        ctx.call_stack.push(func_name);
        ctx.depth += 1;
        ctx
    }

    /// Check if function is in call stack (circular call detection)
    pub fn is_circular(&self, func_name: &str) -> bool {
        self.call_stack.contains(&func_name.to_string())
    }
}

impl Default for CallContext {
    fn default() -> Self {
        Self::new()
    }
}
