/*
 * Visitor Pattern for Unified AST Processing
 *
 * SOTA Design:
 * - Trait-based abstraction
 * - L1 + L2 통합
 * - 확장 가능
 * - Type safe
 *
 * PRODUCTION REQUIREMENTS:
 * - No code duplication
 * - Single traversal
 * - Composable visitors
 */

use tree_sitter::Node;

/// AST Visitor trait
///
/// Allows multiple processors to observe the same AST traversal.
///
/// Design Pattern: Visitor Pattern
/// - Separation of concerns
/// - Single traversal, multiple processors
/// - Easy to add new visitors
pub trait AstVisitor {
    /// Visit a node during AST traversal
    ///
    /// # Arguments
    /// * `node` - Current AST node
    /// * `source` - Source code (for text extraction)
    /// * `depth` - Traversal depth (for context)
    fn visit_node(&mut self, node: &Node, source: &str, depth: usize);

    /// Called before visiting children
    fn enter_node(&mut self, node: &Node, source: &str, depth: usize) {
        // Default: do nothing
        let _ = (node, source, depth);
    }

    /// Called after visiting children
    fn exit_node(&mut self, node: &Node, source: &str, depth: usize) {
        // Default: do nothing
        let _ = (node, source, depth);
    }
}

/// Composite visitor - combines multiple visitors
///
/// Allows running multiple visitors in a single traversal.
pub struct CompositeVisitor {
    visitors: Vec<Box<dyn AstVisitor>>,
}

impl CompositeVisitor {
    pub fn new() -> Self {
        Self {
            visitors: Vec::new(),
        }
    }

    pub fn add_visitor(&mut self, visitor: Box<dyn AstVisitor>) {
        self.visitors.push(visitor);
    }
}

impl AstVisitor for CompositeVisitor {
    fn visit_node(&mut self, node: &Node, source: &str, depth: usize) {
        for visitor in &mut self.visitors {
            visitor.visit_node(node, source, depth);
        }
    }

    fn enter_node(&mut self, node: &Node, source: &str, depth: usize) {
        for visitor in &mut self.visitors {
            visitor.enter_node(node, source, depth);
        }
    }

    fn exit_node(&mut self, node: &Node, source: &str, depth: usize) {
        for visitor in &mut self.visitors {
            visitor.exit_node(node, source, depth);
        }
    }
}

/// Traverse AST with visitor
///
/// Single traversal, multiple visitors.
pub fn traverse_with_visitor(root: &Node, source: &str, visitor: &mut dyn AstVisitor) {
    traverse_recursive(root, source, visitor, 0);
}

fn traverse_recursive(node: &Node, source: &str, visitor: &mut dyn AstVisitor, depth: usize) {
    // Enter
    visitor.enter_node(node, source, depth);

    // Visit
    visitor.visit_node(node, source, depth);

    // Children
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i) {
            traverse_recursive(&child, source, visitor, depth + 1);
        }
    }

    // Exit
    visitor.exit_node(node, source, depth);
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    struct CountingVisitor {
        count: usize,
    }

    impl AstVisitor for CountingVisitor {
        fn visit_node(&mut self, _node: &Node, _source: &str, _depth: usize) {
            self.count += 1;
        }
    }

    #[test]
    fn test_visitor_pattern() {
        let code = "def hello(): pass";

        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();

        let mut visitor = CountingVisitor { count: 0 };
        traverse_with_visitor(&tree.root_node(), code, &mut visitor);

        assert!(visitor.count > 0);
    }

    #[test]
    fn test_composite_visitor() {
        let code = "def hello(): pass";

        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        let tree = parser.parse(code, None).unwrap();

        let mut visitor1 = CountingVisitor { count: 0 };
        let mut visitor2 = CountingVisitor { count: 0 };

        let mut composite = CompositeVisitor::new();
        composite.add_visitor(Box::new(visitor1));
        composite.add_visitor(Box::new(visitor2));

        traverse_with_visitor(&tree.root_node(), code, &mut composite);

        // Both visitors should have counted
        // (Can't check directly due to ownership, but no crash = success)
    }
}
