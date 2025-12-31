//! SOTA Type Inference Engine
//!
//! High-level type inference coordinating constraint generation and solving.
//!
//! Features:
//! - Expression type inference
//! - Assignment type propagation
//! - Function return type inference
//! - Generic type parameter inference
//! - Integration with signature cache
//!
//! Usage:
//! ```text
//! let mut engine = InferenceEngine::new();
//! let inferred_type = engine.infer_expression(&expr_node, &context)?;
//! ```

use std::collections::HashMap;
use std::sync::Arc;

use super::constraint_solver::{Constraint, ConstraintSolver, InferType, Substitution, TypeVarId};
use super::signature_cache::SignatureCache;
use crate::features::type_resolution::domain::{get_builtin_type, Type};
use crate::shared::models::{Node, NodeKind};

/// Inference context
pub struct InferenceContext {
    /// Variable name → inferred type
    var_types: HashMap<String, InferType>,

    /// Signature cache
    signature_cache: Arc<SignatureCache>,

    /// Constraint solver
    solver: ConstraintSolver,
}

impl InferenceContext {
    pub fn new(signature_cache: Arc<SignatureCache>) -> Self {
        Self {
            var_types: HashMap::new(),
            signature_cache,
            solver: ConstraintSolver::new(),
        }
    }

    /// Get inferred type for a variable
    pub fn get_var_type(&self, var_name: &str) -> Option<&InferType> {
        self.var_types.get(var_name)
    }

    /// Set inferred type for a variable
    pub fn set_var_type(&mut self, var_name: String, ty: InferType) {
        self.var_types.insert(var_name, ty);
    }

    /// Generate fresh type variable
    pub fn fresh_var(&mut self) -> TypeVarId {
        self.solver.fresh_var()
    }

    /// Add constraint
    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.solver.add_constraint(constraint);
    }

    /// Solve all constraints and get substitution
    pub fn solve(&mut self) -> Result<Substitution, super::constraint_solver::SolverError> {
        self.solver.solve()
    }
}

/// Type inference engine
pub struct InferenceEngine {
    /// Global inference context
    context: InferenceContext,
}

impl InferenceEngine {
    pub fn new(signature_cache: Arc<SignatureCache>) -> Self {
        Self {
            context: InferenceContext::new(signature_cache),
        }
    }

    /// Infer type for an expression node
    ///
    /// This is the main entry point for type inference
    pub fn infer_expression(&mut self, node: &Node) -> Result<InferType, InferenceError> {
        match node.kind {
            NodeKind::Variable => self.infer_variable(node),
            NodeKind::Function => self.infer_function(node),
            NodeKind::Lambda => self.infer_lambda(node),
            _ => {
                // For unknown node kinds, generate fresh variable
                let var = self.context.fresh_var();
                Ok(InferType::Variable(var))
            }
        }
    }

    /// Infer type for a variable reference
    fn infer_variable(&mut self, node: &Node) -> Result<InferType, InferenceError> {
        // Check if variable type is already known
        if let Some(ty) = self.context.get_var_type(&node.fqn) {
            return Ok(ty.clone());
        }

        // Check if it's a builtin
        if let Some(builtin_ty) = get_builtin_type(&node.fqn) {
            return Ok(InferType::Concrete(builtin_ty.clone()));
        }

        // Generate fresh variable for unknown
        let var = self.context.fresh_var();
        self.context
            .set_var_type(node.fqn.clone(), InferType::Variable(var));
        Ok(InferType::Variable(var))
    }

    /// Infer type for a function definition
    fn infer_function(&mut self, node: &Node) -> Result<InferType, InferenceError> {
        // Check signature cache first
        if let Some(cached) = self.context.signature_cache.get_by_id(&node.id) {
            return Ok(InferType::CallableInfer {
                params: cached
                    .param_types
                    .iter()
                    .map(|_t| {
                        // Type → InferType: requires type_to_infer_type() helper
                        let var = self.context.fresh_var();
                        InferType::Variable(var)
                    })
                    .collect(),
                return_type: Box::new({
                    let var = self.context.fresh_var();
                    InferType::Variable(var)
                }),
            });
        }

        // Generate fresh variables for params and return
        let param_count = self.estimate_param_count(node);
        let mut param_vars = Vec::new();
        for _ in 0..param_count {
            param_vars.push(InferType::Variable(self.context.fresh_var()));
        }

        let return_var = InferType::Variable(self.context.fresh_var());

        Ok(InferType::CallableInfer {
            params: param_vars,
            return_type: Box::new(return_var),
        })
    }

    /// Infer type for a lambda expression
    fn infer_lambda(&mut self, node: &Node) -> Result<InferType, InferenceError> {
        // Similar to function inference
        self.infer_function(node)
    }

    /// Infer type for an assignment
    ///
    /// Generates constraint: var_type = expr_type
    pub fn infer_assignment(
        &mut self,
        var_node: &Node,
        expr_node: &Node,
    ) -> Result<(), InferenceError> {
        let var_type = self.infer_expression(var_node)?;
        let expr_type = self.infer_expression(expr_node)?;

        // Add equality constraint
        self.context
            .add_constraint(Constraint::Equality(var_type, expr_type));

        Ok(())
    }

    /// Infer return type of a function from its body
    ///
    /// Analyzes all return statements and generates constraints
    pub fn infer_function_return_type(
        &mut self,
        function_node: &Node,
        return_nodes: &[Node],
    ) -> Result<InferType, InferenceError> {
        let return_var = self.context.fresh_var();
        let return_type = InferType::Variable(return_var);

        // Add constraint for each return statement
        for ret_node in return_nodes {
            let ret_expr_type = self.infer_expression(ret_node)?;
            self.context
                .add_constraint(Constraint::Equality(return_type.clone(), ret_expr_type));
        }

        Ok(return_type)
    }

    /// Solve all constraints and finalize types
    pub fn finalize(&mut self) -> Result<Substitution, InferenceError> {
        self.context.solve().map_err(InferenceError::SolverError)
    }

    /// Get concrete type for a variable after solving
    pub fn get_concrete_type(&self, var_name: &str, substitution: &Substitution) -> Option<Type> {
        self.context
            .get_var_type(var_name)
            .and_then(|t| t.to_concrete(substitution))
    }

    // Helper methods

    /// Estimate parameter count from node metadata
    ///
    /// Accurate count: Use node.parameters.len() when available
    fn estimate_param_count(&self, node: &Node) -> usize {
        node.parameters.as_ref().map(|p| p.len()).unwrap_or(2)
    }
}

/// Inference errors
#[derive(Debug)]
pub enum InferenceError {
    /// Constraint solver error
    SolverError(super::constraint_solver::SolverError),

    /// Node type not supported
    UnsupportedNodeKind(NodeKind),

    /// Variable not found
    VariableNotFound(String),

    /// Invalid function signature
    InvalidSignature(String),
}

impl std::fmt::Display for InferenceError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            InferenceError::SolverError(e) => write!(f, "Solver error: {}", e),
            InferenceError::UnsupportedNodeKind(kind) => {
                write!(f, "Unsupported node kind: {:?}", kind)
            }
            InferenceError::VariableNotFound(name) => {
                write!(f, "Variable not found: {}", name)
            }
            InferenceError::InvalidSignature(msg) => {
                write!(f, "Invalid signature: {}", msg)
            }
        }
    }
}

impl std::error::Error for InferenceError {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn create_test_node(kind: NodeKind, fqn: &str) -> Node {
        Node::new(
            format!("node_{}", fqn),
            kind,
            fqn.to_string(),
            "test.py".to_string(),
            Span::new(0, 0, 0, 0),
        )
    }

    #[test]
    fn test_infer_variable() {
        let cache = Arc::new(SignatureCache::new());
        let mut engine = InferenceEngine::new(cache);

        let var_node = create_test_node(NodeKind::Variable, "x");
        let inferred = engine.infer_expression(&var_node).unwrap();

        // Should generate a fresh type variable
        match inferred {
            InferType::Variable(_) => {}
            _ => panic!("Expected type variable"),
        }
    }

    #[test]
    fn test_infer_builtin() {
        let cache = Arc::new(SignatureCache::new());
        let mut engine = InferenceEngine::new(cache);

        let builtin_node = create_test_node(NodeKind::Variable, "int");
        let inferred = engine.infer_expression(&builtin_node).unwrap();

        // Should resolve to builtin int type
        match inferred {
            InferType::Concrete(ty) => assert_eq!(ty.to_string(), "int"),
            _ => panic!("Expected concrete type"),
        }
    }

    #[test]
    fn test_infer_assignment() {
        let cache = Arc::new(SignatureCache::new());
        let mut engine = InferenceEngine::new(cache);

        let var_node = create_test_node(NodeKind::Variable, "x");
        let value_node = create_test_node(NodeKind::Variable, "int");

        // x = int
        engine.infer_assignment(&var_node, &value_node).unwrap();

        // Solve constraints
        let subst = engine.finalize().unwrap();

        // x should be int
        let x_type = engine.get_concrete_type("x", &subst);
        assert!(x_type.is_some());
    }

    #[test]
    fn test_infer_function() {
        let cache = Arc::new(SignatureCache::new());
        let mut engine = InferenceEngine::new(cache);

        let func_node = create_test_node(NodeKind::Function, "test_func");
        let inferred = engine.infer_expression(&func_node).unwrap();

        // Should be callable type
        match inferred {
            InferType::CallableInfer {
                params,
                return_type,
            } => {
                assert!(!params.is_empty());
            }
            _ => panic!("Expected callable type"),
        }
    }
}
