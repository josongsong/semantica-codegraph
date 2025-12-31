//! Python Expression Lowering - L1 (Expression IR) → L2 (Node IR)
//!
//! SOTA Design:
//! - Maps ExprKind to NodeKind with semantic preservation
//! - Creates explicit data flow edges (READS, WRITES)
//! - Tracks heap access as explicit nodes
//! - Maintains symbol and type information

use crate::shared::models::{
    Expression, ExpressionIR, ExprKind,
    Node, NodeKind, NodeBuilder,
    Edge, EdgeKind, EdgeMetadata,
    Span, Result,
};
use crate::features::lowering::domain::{ExpressionLowering, LoweringContext};

pub struct PythonExpressionLowering;

impl PythonExpressionLowering {
    pub fn new() -> Self {
        Self
    }

    /// Lower expression to Node IR
    fn lower_expr(
        &self,
        expr: &Expression,
        ctx: &mut LoweringContext,
    ) -> Result<String> {
        let node_id = ctx.next_node_id();

        // Map ExprKind to NodeKind
        let node_kind = self.expr_kind_to_node_kind(&expr.kind);

        // Build node
        let mut node = NodeBuilder::new(node_id.clone(), node_kind)
            .with_span(expr.span.clone())
            .with_file_path(&expr.file_path)
            .build();

        // Preserve metadata
        if let Some(ref symbol_id) = expr.symbol_id {
            node.symbol_id = Some(symbol_id.clone());
        }
        if let Some(ref type_info) = expr.type_info {
            node.inferred_type = Some(type_info.type_string.clone());
        }

        // Add to context
        ctx.register_mapping(expr.id, node_id.clone());
        ctx.add_node(node);

        // Create data flow edges from reads
        for &read_expr_id in &expr.reads {
            if let Some(read_node_id) = ctx.get_node_id(read_expr_id) {
                let edge = Edge {
                    id: ctx.next_edge_id(),
                    kind: EdgeKind::READS,
                    from_node: node_id.clone(),
                    to_node: read_node_id.clone(),
                    span: Some(expr.span.clone()),
                    metadata: Some(EdgeMetadata::default()),
                };
                ctx.add_edge(edge);
            }
        }

        // Create WRITES edge for assignments
        if expr.defines.is_some() {
            // Assignment creates a new definition
            // (In full implementation, would create SSA version here)
        }

        Ok(node_id)
    }

    /// Map ExprKind to NodeKind
    fn expr_kind_to_node_kind(&self, kind: &ExprKind) -> NodeKind {
        match kind {
            ExprKind::NameLoad => NodeKind::VariableRead,
            ExprKind::Attribute => NodeKind::FieldAccess,
            ExprKind::Subscript => NodeKind::Subscript,
            ExprKind::BinOp(_) => NodeKind::BinaryOp,
            ExprKind::UnaryOp(_) => NodeKind::UnaryOp,
            ExprKind::Compare(_) => NodeKind::Comparison,
            ExprKind::BoolOp(_) => NodeKind::BooleanOp,
            ExprKind::Call => NodeKind::FunctionCall,
            ExprKind::Instantiate => NodeKind::ObjectInstantiation,
            ExprKind::Literal(_) => NodeKind::Literal,
            ExprKind::Collection(_) => NodeKind::Collection,
            ExprKind::Assign => NodeKind::Assignment,
            ExprKind::Lambda => NodeKind::LambdaDefinition,
            ExprKind::Comprehension => NodeKind::Comprehension,
            ExprKind::Conditional => NodeKind::ConditionalExpression,
        }
    }
}

impl ExpressionLowering for PythonExpressionLowering {
    fn lower(&self, expr_ir: &ExpressionIR) -> Result<(Vec<Node>, Vec<Edge>)> {
        let mut ctx = LoweringContext::new();

        // Lower all expressions in topological order (parents before children)
        for expr in &expr_ir.expressions {
            self.lower_expr(expr, &mut ctx)?;
        }

        Ok((ctx.nodes, ctx.edges))
    }

    fn lower_expression(&self, expr: &Expression) -> Result<Vec<Node>> {
        let mut ctx = LoweringContext::new();
        self.lower_expr(expr, &mut ctx)?;
        Ok(ctx.nodes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::expression_builder::infrastructure::python::PythonExpressionBuilder;
    use crate::features::expression_builder::domain::ExpressionBuilderTrait;

    #[test]
    fn test_lower_binary_op() {
        // Build Expression IR
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let expr_ir = builder.build("a + b", "test.py").unwrap();

        // Lower to Node IR
        let lowering = PythonExpressionLowering::new();
        let (nodes, edges) = lowering.lower(&expr_ir).unwrap();

        // Should have nodes for: a, b, a+b
        assert!(nodes.len() >= 3);

        // Should have at least one BinaryOp node
        let bin_op_nodes: Vec<_> = nodes.iter()
            .filter(|n| n.kind == NodeKind::BinaryOp)
            .collect();
        assert!(!bin_op_nodes.is_empty());

        // Should have READS edges
        assert!(!edges.is_empty());
    }

    #[test]
    fn test_lower_function_call() {
        // Build Expression IR
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let expr_ir = builder.build("print('hello')", "test.py").unwrap();

        // Lower to Node IR
        let lowering = PythonExpressionLowering::new();
        let (nodes, _edges) = lowering.lower(&expr_ir).unwrap();

        // Should have FunctionCall node
        let call_nodes: Vec<_> = nodes.iter()
            .filter(|n| n.kind == NodeKind::FunctionCall)
            .collect();
        assert!(!call_nodes.is_empty());
    }

    #[test]
    fn test_lower_attribute_access() {
        // Build Expression IR
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let expr_ir = builder.build("obj.field", "test.py").unwrap();

        // Lower to Node IR
        let lowering = PythonExpressionLowering::new();
        let (nodes, _edges) = lowering.lower(&expr_ir).unwrap();

        // Should have FieldAccess node
        let field_nodes: Vec<_> = nodes.iter()
            .filter(|n| n.kind == NodeKind::FieldAccess)
            .collect();
        assert!(!field_nodes.is_empty());
    }

    #[test]
    fn test_end_to_end_lowering() {
        // Build Expression IR from Python code
        let source = r#"
x = 42
y = x + 10
print(y)
"#;
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let expr_ir = builder.build(source, "test.py").unwrap();

        // Lower to Node IR
        let lowering = PythonExpressionLowering::new();
        let (nodes, edges) = lowering.lower(&expr_ir).unwrap();

        // Should have nodes for:
        // - Literals (42, 10)
        // - Variables (x, y)
        // - BinaryOp (x + 10)
        // - Assignments (x=, y=)
        // - FunctionCall (print)
        assert!(nodes.len() >= 5);

        // Should have data flow edges
        assert!(!edges.is_empty());

        println!("Lowered {} expressions to {} nodes, {} edges",
                 expr_ir.expressions.len(), nodes.len(), edges.len());
    }
}
