//! Python Expression Builder - tree-sitter Python → Expression IR (L1)
//!
//! SOTA Design:
//! - Recursive descent visitor for tree-sitter AST
//! - Complete expression kind coverage (14 types)
//! - Automatic data flow tracking (reads/defines)
//! - Heap access detection (obj.field, arr[index])
//! - Parent/child relationship tracking

use crate::features::expression_builder::domain::{BuilderContext, ExpressionBuilderTrait};
use crate::shared::models::Result;
use crate::shared::models::{
    AccessKind, BinOp, BoolOp, CollectionKind, CompOp, ExprId, ExprKind, Expression, ExpressionIR,
    HeapAccess, LiteralKind, Span, UnaryOp,
};
use tree_sitter::{Node, Parser, Tree};

pub struct PythonExpressionBuilder {
    parser: Parser,
}

impl PythonExpressionBuilder {
    pub fn new() -> Result<Self> {
        let mut parser = Parser::new();
        let language = tree_sitter_python::language();
        parser.set_language(&language.into()).map_err(|e| {
            crate::shared::models::CodegraphError::parse(format!(
                "Failed to set Python language: {}",
                e
            ))
        })?;

        Ok(Self { parser })
    }

    /// Parse source code and get tree
    fn parse(&mut self, source: &str) -> Result<Tree> {
        self.parser.parse(source, None).ok_or_else(|| {
            crate::shared::models::CodegraphError::parse("Failed to parse Python code")
        })
    }

    /// Visit expression node and build Expression IR
    fn visit_expression(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let kind_str = node.kind();

        match kind_str {
            // Binary operations
            "binary_operator" => self.visit_binary_op(node, source, ctx),

            // Unary operations
            "unary_operator" => self.visit_unary_op(node, source, ctx),

            // Comparisons
            "comparison_operator" => self.visit_comparison(node, source, ctx),

            // Boolean operations
            "boolean_operator" => self.visit_bool_op(node, source, ctx),

            // Function call
            "call" => self.visit_call(node, source, ctx),

            // Attribute access (obj.field)
            "attribute" => self.visit_attribute(node, source, ctx),

            // Subscript (arr[i])
            "subscript" => self.visit_subscript(node, source, ctx),

            // Variable name
            "identifier" => self.visit_identifier(node, source, ctx),

            // Literals
            "integer" | "float" | "string" | "true" | "false" | "none" => {
                self.visit_literal(node, source, ctx)
            }

            // Collections
            "list" | "tuple" | "set" | "dictionary" => self.visit_collection(node, source, ctx),

            // Assignment
            "assignment" => self.visit_assignment(node, source, ctx),

            // Lambda
            "lambda" => self.visit_lambda(node, source, ctx),

            // List/dict comprehension
            "list_comprehension" | "dictionary_comprehension" | "set_comprehension" => {
                self.visit_comprehension(node, source, ctx)
            }

            // Conditional expression (a if cond else b)
            "conditional_expression" => self.visit_conditional(node, source, ctx),

            // Parenthesized expression - transparently visit the inner expression
            "parenthesized_expression" => {
                // Get the inner expression (skip the parentheses)
                for child in node.children(&mut node.walk()) {
                    if child.is_named() {
                        return self.visit_expression(child, source, ctx);
                    }
                }
                None
            }

            _ => {
                // Recursively visit children for unknown nodes
                for child in node.children(&mut node.walk()) {
                    self.visit_expression(child, source, ctx);
                }
                None
            }
        }
    }

    /// Visit binary operator (a + b, a * b, etc.)
    fn visit_binary_op(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        // Get operator
        let op_node = node.child_by_field_name("operator")?;
        let op_str = &source[op_node.byte_range()];

        let bin_op = match op_str {
            "+" => BinOp::Add,
            "-" => BinOp::Sub,
            "*" => BinOp::Mul,
            "/" => BinOp::Div,
            "%" => BinOp::Mod,
            "**" => BinOp::Pow,
            "//" => BinOp::FloorDiv,
            "&" => BinOp::BitAnd,
            "|" => BinOp::BitOr,
            "^" => BinOp::BitXor,
            "<<" => BinOp::LShift,
            ">>" => BinOp::RShift,
            "and" => BinOp::And,
            "or" => BinOp::Or,
            _ => return None,
        };

        // Visit operands
        ctx.push_parent(expr_id);

        let left = node
            .child_by_field_name("left")
            .and_then(|n| self.visit_expression(n, source, ctx));
        let right = node
            .child_by_field_name("right")
            .and_then(|n| self.visit_expression(n, source, ctx));

        ctx.pop_parent();

        let mut reads = Vec::new();
        if let Some(l) = left {
            reads.push(l);
        }
        if let Some(r) = right {
            reads.push(r);
        }

        let mut expr = Expression::new(
            expr_id,
            ExprKind::BinOp(bin_op),
            span,
            ctx.file_path.clone(),
        );
        expr.reads = reads;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        if let (Some(l), Some(r)) = (left, right) {
            expr.children = vec![l, r];
        }

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit unary operator (-a, not x, etc.)
    fn visit_unary_op(&self, node: Node, source: &str, ctx: &mut BuilderContext) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        let op_node = node.child_by_field_name("operator")?;
        let op_str = &source[op_node.byte_range()];

        let unary_op = match op_str {
            "not" => UnaryOp::Not,
            "-" => UnaryOp::Neg,
            "+" => UnaryOp::Pos,
            "~" => UnaryOp::Invert,
            _ => return None,
        };

        ctx.push_parent(expr_id);
        let operand = node
            .child_by_field_name("argument")
            .and_then(|n| self.visit_expression(n, source, ctx));
        ctx.pop_parent();

        let mut expr = Expression::new(
            expr_id,
            ExprKind::UnaryOp(unary_op),
            span,
            ctx.file_path.clone(),
        );

        if let Some(op_id) = operand {
            expr.reads = vec![op_id];
            expr.children = vec![op_id];
        }
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit comparison (a < b, a == b, etc.)
    fn visit_comparison(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        // Get operators
        let operators: Vec<_> = node
            .children_by_field_name("operators", &mut node.walk())
            .collect();

        if let Some(op_node) = operators.first() {
            let op_str = &source[op_node.byte_range()];
            let comp_op = match op_str {
                "==" => CompOp::Eq,
                "!=" => CompOp::NotEq,
                "<" => CompOp::Lt,
                "<=" => CompOp::LtE,
                ">" => CompOp::Gt,
                ">=" => CompOp::GtE,
                "is" => CompOp::Is,
                "is not" => CompOp::IsNot,
                "in" => CompOp::In,
                "not in" => CompOp::NotIn,
                _ => return None,
            };

            ctx.push_parent(expr_id);

            // Visit left and comparators
            let left = node
                .child(0)
                .and_then(|n| self.visit_expression(n, source, ctx));
            let right = node
                .child(2)
                .and_then(|n| self.visit_expression(n, source, ctx));

            ctx.pop_parent();

            let mut reads = Vec::new();
            let mut children = Vec::new();
            if let Some(l) = left {
                reads.push(l);
                children.push(l);
            }
            if let Some(r) = right {
                reads.push(r);
                children.push(r);
            }

            let mut expr = Expression::new(
                expr_id,
                ExprKind::Compare(comp_op),
                span,
                ctx.file_path.clone(),
            );
            expr.reads = reads;
            expr.children = children;
            expr.parent = ctx.current_parent();
            expr.function_id = ctx.current_function.clone();
            expr.block_id = ctx.current_block.clone();

            ctx.add_expression(expr);
            Some(expr_id)
        } else {
            None
        }
    }

    /// Visit boolean operator (a and b, a or b)
    fn visit_bool_op(&self, node: Node, source: &str, ctx: &mut BuilderContext) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        let op_node = node.child_by_field_name("operator")?;
        let op_str = &source[op_node.byte_range()];

        let bool_op = match op_str {
            "and" => BoolOp::And,
            "or" => BoolOp::Or,
            _ => return None,
        };

        ctx.push_parent(expr_id);
        let left = node
            .child_by_field_name("left")
            .and_then(|n| self.visit_expression(n, source, ctx));
        let right = node
            .child_by_field_name("right")
            .and_then(|n| self.visit_expression(n, source, ctx));
        ctx.pop_parent();

        let mut reads = Vec::new();
        let mut children = Vec::new();
        if let Some(l) = left {
            reads.push(l);
            children.push(l);
        }
        if let Some(r) = right {
            reads.push(r);
            children.push(r);
        }

        let mut expr = Expression::new(
            expr_id,
            ExprKind::BoolOp(bool_op),
            span,
            ctx.file_path.clone(),
        );
        expr.reads = reads;
        expr.children = children;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit function call (fn(args))
    fn visit_call(&self, node: Node, source: &str, ctx: &mut BuilderContext) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);

        // Visit function
        let function = node
            .child_by_field_name("function")
            .and_then(|n| self.visit_expression(n, source, ctx));

        // Visit arguments
        let mut arg_ids = Vec::new();
        if let Some(args_node) = node.child_by_field_name("arguments") {
            for arg in args_node.children(&mut args_node.walk()) {
                if arg.is_named() {
                    if let Some(arg_id) = self.visit_expression(arg, source, ctx) {
                        arg_ids.push(arg_id);
                    }
                }
            }
        }

        ctx.pop_parent();

        let mut reads = Vec::new();
        let mut children = Vec::new();
        if let Some(f) = function {
            reads.push(f);
            children.push(f);
        }
        reads.extend(&arg_ids);
        children.extend(&arg_ids);

        let mut expr = Expression::new(expr_id, ExprKind::Call, span, ctx.file_path.clone());
        expr.reads = reads;
        expr.children = children;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit attribute access (obj.field)
    fn visit_attribute(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);
        let object = node
            .child_by_field_name("object")
            .and_then(|n| self.visit_expression(n, source, ctx));
        ctx.pop_parent();

        let attribute = node
            .child_by_field_name("attribute")
            .map(|n| source[n.byte_range()].to_string());

        let mut reads = Vec::new();
        let mut children = Vec::new();
        if let Some(obj_id) = object {
            reads.push(obj_id);
            children.push(obj_id);
        }

        let mut expr = Expression::new(expr_id, ExprKind::Attribute, span, ctx.file_path.clone());
        expr.reads = reads;
        expr.children = children;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        // Heap access tracking
        if let (Some(base_id), Some(field_name)) = (object, attribute) {
            expr.heap_access = Some(HeapAccess {
                base: base_id,
                field: Some(field_name),
                index: None,
                access_kind: AccessKind::Read, // Default, can be refined later
            });
        }

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit subscript (arr[index])
    fn visit_subscript(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);
        let value = node
            .child_by_field_name("value")
            .and_then(|n| self.visit_expression(n, source, ctx));
        let subscript = node
            .child_by_field_name("subscript")
            .and_then(|n| self.visit_expression(n, source, ctx));
        ctx.pop_parent();

        let mut reads = Vec::new();
        let mut children = Vec::new();
        if let Some(v) = value {
            reads.push(v);
            children.push(v);
        }
        if let Some(s) = subscript {
            reads.push(s);
            children.push(s);
        }

        let mut expr = Expression::new(expr_id, ExprKind::Subscript, span, ctx.file_path.clone());
        expr.reads = reads;
        expr.children = children;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        // Heap access tracking
        if let (Some(base_id), Some(index_id)) = (value, subscript) {
            expr.heap_access = Some(HeapAccess {
                base: base_id,
                field: None,
                index: Some(index_id),
                access_kind: AccessKind::Read,
            });
        }

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit identifier (variable name)
    fn visit_identifier(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);
        let name = source[node.byte_range()].to_string();

        let mut expr = Expression::new(expr_id, ExprKind::NameLoad, span, ctx.file_path.clone());
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        // Store variable name in attrs
        expr.attrs
            .insert("name".to_string(), serde_json::json!(name));

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit literal (42, "str", True, None, etc.)
    fn visit_literal(&self, node: Node, _source: &str, ctx: &mut BuilderContext) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        let kind_str = node.kind();
        let literal_kind = match kind_str {
            "integer" => LiteralKind::Integer,
            "float" => LiteralKind::Float,
            "string" => LiteralKind::String,
            "true" | "false" => LiteralKind::Boolean,
            "none" => LiteralKind::None,
            _ => return None,
        };

        let mut expr = Expression::new(
            expr_id,
            ExprKind::Literal(literal_kind),
            span,
            ctx.file_path.clone(),
        );
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit collection ([1, 2], {a: 1}, etc.)
    fn visit_collection(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        let kind_str = node.kind();
        let collection_kind = match kind_str {
            "list" => CollectionKind::List,
            "tuple" => CollectionKind::Tuple,
            "set" => CollectionKind::Set,
            "dictionary" => CollectionKind::Dict,
            _ => return None,
        };

        ctx.push_parent(expr_id);

        // Visit elements
        let mut element_ids = Vec::new();
        for child in node.children(&mut node.walk()) {
            if child.is_named() {
                if let Some(elem_id) = self.visit_expression(child, source, ctx) {
                    element_ids.push(elem_id);
                }
            }
        }

        ctx.pop_parent();

        let mut expr = Expression::new(
            expr_id,
            ExprKind::Collection(collection_kind),
            span,
            ctx.file_path.clone(),
        );
        expr.reads = element_ids.clone();
        expr.children = element_ids;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit assignment (x = expr)
    fn visit_assignment(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);

        let left = node
            .child_by_field_name("left")
            .and_then(|n| self.visit_expression(n, source, ctx));
        let right = node
            .child_by_field_name("right")
            .and_then(|n| self.visit_expression(n, source, ctx));

        ctx.pop_parent();

        // Get variable name from left side
        let var_name = node
            .child_by_field_name("left")
            .map(|n| source[n.byte_range()].to_string());

        let mut reads = Vec::new();
        if let Some(r) = right {
            reads.push(r);
        }

        let mut expr = Expression::new(expr_id, ExprKind::Assign, span, ctx.file_path.clone());
        expr.reads = reads;
        expr.defines = var_name; // Variable being assigned to
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        if let (Some(l), Some(r)) = (left, right) {
            expr.children = vec![l, r];
        }

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit lambda (lambda x: x + 1)
    fn visit_lambda(&self, node: Node, source: &str, ctx: &mut BuilderContext) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);

        // Visit body
        let body = node
            .child_by_field_name("body")
            .and_then(|n| self.visit_expression(n, source, ctx));

        ctx.pop_parent();

        let mut expr = Expression::new(expr_id, ExprKind::Lambda, span, ctx.file_path.clone());

        if let Some(body_id) = body {
            expr.reads = vec![body_id];
            expr.children = vec![body_id];
        }
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit comprehension ([x for x in lst])
    fn visit_comprehension(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);

        // Visit body and iterators
        let mut child_ids = Vec::new();
        for child in node.children(&mut node.walk()) {
            if child.is_named() {
                if let Some(child_id) = self.visit_expression(child, source, ctx) {
                    child_ids.push(child_id);
                }
            }
        }

        ctx.pop_parent();

        let mut expr = Expression::new(
            expr_id,
            ExprKind::Comprehension,
            span,
            ctx.file_path.clone(),
        );
        expr.reads = child_ids.clone();
        expr.children = child_ids;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Visit conditional expression (a if cond else b)
    fn visit_conditional(
        &self,
        node: Node,
        source: &str,
        ctx: &mut BuilderContext,
    ) -> Option<ExprId> {
        let expr_id = ctx.next_id();
        let span = self.node_to_span(node);

        ctx.push_parent(expr_id);

        let consequence = node
            .child_by_field_name("consequence")
            .and_then(|n| self.visit_expression(n, source, ctx));
        let condition = node
            .child_by_field_name("condition")
            .and_then(|n| self.visit_expression(n, source, ctx));
        let alternative = node
            .child_by_field_name("alternative")
            .and_then(|n| self.visit_expression(n, source, ctx));

        ctx.pop_parent();

        let mut reads = Vec::new();
        let mut children = Vec::new();
        if let Some(cond_id) = condition {
            reads.push(cond_id);
            children.push(cond_id);
        }
        if let Some(cons_id) = consequence {
            reads.push(cons_id);
            children.push(cons_id);
        }
        if let Some(alt_id) = alternative {
            reads.push(alt_id);
            children.push(alt_id);
        }

        let mut expr = Expression::new(expr_id, ExprKind::Conditional, span, ctx.file_path.clone());
        expr.reads = reads;
        expr.children = children;
        expr.parent = ctx.current_parent();
        expr.function_id = ctx.current_function.clone();
        expr.block_id = ctx.current_block.clone();

        ctx.add_expression(expr);
        Some(expr_id)
    }

    /// Convert tree-sitter node to Span
    fn node_to_span(&self, node: Node) -> Span {
        let start_pos = node.start_position();
        let end_pos = node.end_position();

        Span {
            start_line: start_pos.row as u32 + 1, // 1-indexed
            start_col: start_pos.column as u32,
            end_line: end_pos.row as u32 + 1,
            end_col: end_pos.column as u32,
        }
    }
}

impl ExpressionBuilderTrait for PythonExpressionBuilder {
    fn build(&mut self, source: &str, file_path: &str) -> Result<ExpressionIR> {
        let tree = self.parse(source)?;
        let root = tree.root_node();

        let mut ctx = BuilderContext::new(file_path.to_string());

        // Visit all expression nodes in the AST
        for child in root.children(&mut root.walk()) {
            self.visit_expression(child, source, &mut ctx);
        }

        Ok(ExpressionIR {
            expressions: ctx.expressions,
            type_bindings: std::collections::HashMap::new(),
            symbol_table: std::collections::HashMap::new(),
            file_path: file_path.to_string(),
            module_path: None,
        })
    }

    fn language(&self) -> &str {
        "python"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_binary_op() {
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let source = "a + b";
        let ir = builder.build(source, "test.py").unwrap();

        assert!(ir.expressions.len() >= 1);

        // Find BinOp expression
        let bin_op = ir
            .expressions
            .iter()
            .find(|e| matches!(e.kind, ExprKind::BinOp(BinOp::Add)));
        assert!(bin_op.is_some());
    }

    #[test]
    fn test_function_call() {
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let source = "print('hello')";
        let ir = builder.build(source, "test.py").unwrap();

        // Should have Call expression
        let call = ir
            .expressions
            .iter()
            .find(|e| matches!(e.kind, ExprKind::Call));
        assert!(call.is_some());
    }

    #[test]
    fn test_attribute_access() {
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let source = "obj.field";
        let ir = builder.build(source, "test.py").unwrap();

        // Should have Attribute expression with heap access
        let attr = ir
            .expressions
            .iter()
            .find(|e| matches!(e.kind, ExprKind::Attribute));
        assert!(attr.is_some());

        if let Some(a) = attr {
            assert!(a.heap_access.is_some());
        }
    }

    #[test]
    fn test_assignment() {
        let mut builder = PythonExpressionBuilder::new().unwrap();
        let source = "x = 42";
        let ir = builder.build(source, "test.py").unwrap();

        // Should have Assign expression
        let assign = ir
            .expressions
            .iter()
            .find(|e| matches!(e.kind, ExprKind::Assign));
        assert!(assign.is_some());

        if let Some(a) = assign {
            assert!(a.defines.is_some());
        }
    }
}
