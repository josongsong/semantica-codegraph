//! Scope stack for FQN management
//!
//! Tracks nested scopes during AST traversal.

/// Scope stack for managing fully qualified names
#[derive(Debug, Clone, Default)]
pub struct ScopeStack {
    scopes: Vec<String>,
    separator: &'static str,
}

impl ScopeStack {
    /// Create a new scope stack with default separator "."
    pub fn new() -> Self {
        Self {
            scopes: Vec::new(),
            separator: ".",
        }
    }

    /// Create with a custom separator
    pub fn with_separator(separator: &'static str) -> Self {
        Self {
            scopes: Vec::new(),
            separator,
        }
    }

    /// Push a new scope
    pub fn push(&mut self, name: impl Into<String>) {
        self.scopes.push(name.into());
    }

    /// Pop the current scope
    pub fn pop(&mut self) -> Option<String> {
        self.scopes.pop()
    }

    /// Get current FQN
    pub fn fqn(&self) -> String {
        self.scopes.join(self.separator)
    }

    /// Get FQN with additional name
    pub fn fqn_with(&self, name: &str) -> String {
        if self.scopes.is_empty() {
            name.to_string()
        } else {
            format!("{}{}{}", self.fqn(), self.separator, name)
        }
    }

    /// Current depth
    pub fn depth(&self) -> usize {
        self.scopes.len()
    }

    /// Is empty?
    pub fn is_empty(&self) -> bool {
        self.scopes.is_empty()
    }

    /// Get current scope name
    pub fn current(&self) -> Option<&str> {
        self.scopes.last().map(|s| s.as_str())
    }

    /// Clear all scopes
    pub fn clear(&mut self) {
        self.scopes.clear();
    }

    /// Execute a closure within a new scope
    pub fn with_scope<F, R>(&mut self, name: impl Into<String>, f: F) -> R
    where
        F: FnOnce(&mut Self) -> R,
    {
        self.push(name);
        let result = f(self);
        self.pop();
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scope_stack_fqn() {
        let mut stack = ScopeStack::new();
        stack.push("module");
        stack.push("class");
        stack.push("method");
        assert_eq!(stack.fqn(), "module.class.method");
    }

    #[test]
    fn test_scope_stack_fqn_with() {
        let mut stack = ScopeStack::new();
        stack.push("module");
        stack.push("class");
        assert_eq!(stack.fqn_with("method"), "module.class.method");
    }

    #[test]
    fn test_scope_stack_pop() {
        let mut stack = ScopeStack::new();
        stack.push("a");
        stack.push("b");
        assert_eq!(stack.pop(), Some("b".to_string()));
        assert_eq!(stack.fqn(), "a");
    }

    #[test]
    fn test_with_scope() {
        let mut stack = ScopeStack::new();
        stack.push("module");

        let inner_fqn = stack.with_scope("class", |s| s.fqn());

        assert_eq!(inner_fqn, "module.class");
        assert_eq!(stack.fqn(), "module");
    }
}
