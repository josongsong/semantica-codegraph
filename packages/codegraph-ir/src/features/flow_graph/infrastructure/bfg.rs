/*
 * BFG (Basic Flow Graph) Module
 *
 * Extracts control flow blocks from function bodies.
 *
 * SOTA Features:
 * - Zero-copy (Span references)
 * - Visitor pattern integration
 * - Parallel processing
 *
 * MATCHES: BfgBuilder.build_full()
 */

use crate::features::ir_generation::infrastructure::visitor::AstVisitor;
use crate::features::parsing::ports::LanguagePlugin;
use crate::shared::models::span_ref::BlockRef;
use crate::shared::models::Span;
use tree_sitter::Node;

/// Block kind (matches Python BFGBlockKind enum values exactly)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockKind {
    Entry,
    Exit,
    Statement,
    Condition,  // if/elif (Python: Condition)
    LoopHeader, // for/while (Python: LoopHeader)
    Try,
    Catch,
    Finally,
    Suspend,     // await suspend
    Resume,      // await resume
    Dispatcher,  // generator state machine
    Yield,       // generator yield
    ResumeYield, // resume after yield
}

impl BlockKind {
    /// Returns the exact string value matching Python's BFGBlockKind enum
    pub fn as_str(&self) -> &'static str {
        match self {
            BlockKind::Entry => "Entry",
            BlockKind::Exit => "Exit",
            BlockKind::Statement => "Statement",
            BlockKind::Condition => "Condition",
            BlockKind::LoopHeader => "LoopHeader",
            BlockKind::Try => "Try",
            BlockKind::Catch => "Catch",
            BlockKind::Finally => "Finally",
            BlockKind::Suspend => "Suspend",
            BlockKind::Resume => "Resume",
            BlockKind::Dispatcher => "Dispatcher",
            BlockKind::Yield => "Yield",
            BlockKind::ResumeYield => "ResumeYield",
        }
    }
}

/// Basic Flow Graph
#[derive(Debug, Clone)]
pub struct BasicFlowGraph {
    pub id: String,
    pub function_id: String,
    pub entry_block_id: String,
    pub exit_block_id: String,
    pub blocks: Vec<BlockRef>,
    pub total_statements: usize,
}

/// BFG Visitor - extracts control flow blocks
///
/// Implements AstVisitor to integrate with unified traversal.
///
/// PRODUCTION GRADE:
/// - Accurate block boundaries
/// - Statement counting
/// - Nested block handling
/// - Control flow detection
/// - Language-agnostic via LanguagePlugin delegation
pub struct BfgVisitor<'a> {
    function_id: Option<String>,
    blocks: Vec<BlockRef>,
    block_counter: usize,
    current_block_statements: Vec<Span>,
    language_plugin: &'a dyn LanguagePlugin,
}

impl<'a> BfgVisitor<'a> {
    pub fn new(language_plugin: &'a dyn LanguagePlugin) -> Self {
        Self {
            function_id: None,
            blocks: Vec::new(),
            block_counter: 0,
            current_block_statements: Vec::new(),
            language_plugin,
        }
    }

    pub fn set_function_id(&mut self, function_id: String) {
        self.function_id = Some(function_id);
    }

    pub fn get_blocks(&self) -> &[BlockRef] {
        &self.blocks
    }

    pub fn finalize(&mut self) {
        // Create final block if statements remain
        if !self.current_block_statements.is_empty() {
            self.flush_current_block(BlockKind::Statement);
        }
    }

    fn flush_current_block(&mut self, kind: BlockKind) {
        if self.current_block_statements.is_empty() {
            return;
        }

        // SAFETY: We just checked that the vector is not empty above
        // Therefore first() and last() will always return Some
        let first = self.current_block_statements.first().unwrap();
        let last = self.current_block_statements.last().unwrap();

        let span = Span::new(
            first.start_line,
            first.start_col,
            last.end_line,
            last.end_col,
        );

        let block_id = format!(
            "bfg:{}:block:{}",
            self.function_id.as_ref().unwrap_or(&"unknown".to_string()),
            self.block_counter
        );
        self.block_counter += 1;

        let block = BlockRef::new(
            block_id,
            kind.as_str().to_string(),
            span,
            self.current_block_statements.len(),
        );

        self.blocks.push(block);
        self.current_block_statements.clear();
    }

    /// Check if node is control flow construct
    ///
    /// Delegates to language plugin for language-specific detection.
    /// This eliminates hardcoded magic strings and enables extensibility.
    fn is_control_flow(&self, node: &Node) -> bool {
        self.language_plugin.is_control_flow_node(node)
    }

    /// Check if node is a statement
    ///
    /// Delegates to language plugin for language-specific detection.
    /// This eliminates hardcoded magic strings and enables extensibility.
    fn is_statement(&self, node: &Node) -> bool {
        self.language_plugin.is_statement_node(node)
    }

    /// Visit statements within a block (used for if/else/loop bodies)
    ///
    /// Recursively processes block contents to handle nested control flow
    fn visit_block_statements(&mut self, block_node: &Node, source: &str) {
        let mut cursor = block_node.walk();
        for child in block_node.children(&mut cursor) {
            // Handle control flow recursively
            if self.is_control_flow(&child) {
                self.visit_node(&child, source, 0);
            }
            // Accumulate regular statements
            else if self.is_statement(&child) {
                let span = node_to_span(&child);
                self.current_block_statements.push(span);
            }
        }
    }

    // ========================================
    // Control Flow Processing Helpers
    // ========================================

    /// Process if/elif/else construct
    fn process_if(&mut self, node: &Node, source: &str) {
        // 1. Condition block
        if let Some(condition) = self.language_plugin.get_control_flow_condition(node) {
            let span = node_to_span(&condition);
            self.current_block_statements.push(span);
            self.flush_current_block(BlockKind::Condition);
        }

        // 2. Then block (consequence)
        if let Some(consequence) = self.language_plugin.get_control_flow_body(node) {
            self.visit_block_statements(&consequence, source);
            self.flush_current_block(BlockKind::Statement);
        }

        // 3. Else block (alternative)
        if let Some(alternative) = self.language_plugin.get_control_flow_alternative(node) {
            // Check if chained (elif/else if)
            if self.language_plugin.is_chained_condition(&alternative) {
                // Recursively handle elif as another if
                self.visit_node(&alternative, source, 0);
            } else {
                // Regular else block
                // For else_clause nodes, need to get body
                if let Some(else_body) = self.language_plugin.get_control_flow_body(&alternative) {
                    self.visit_block_statements(&else_body, source);
                } else {
                    // Alternative itself is the body
                    self.visit_block_statements(&alternative, source);
                }
                self.flush_current_block(BlockKind::Statement);
            }
        }
    }

    /// Process loop construct (for/while)
    fn process_loop(&mut self, node: &Node, source: &str) {
        // 1. Loop header (condition or iterator)
        let iterators = self.language_plugin.get_loop_iterator(node);
        if !iterators.is_empty() {
            // For loop: iterator nodes
            for iter_node in iterators {
                let span = node_to_span(&iter_node);
                self.current_block_statements.push(span);
            }
            self.flush_current_block(BlockKind::LoopHeader);
        } else if let Some(condition) = self.language_plugin.get_control_flow_condition(node) {
            // While loop: condition
            let span = node_to_span(&condition);
            self.current_block_statements.push(span);
            self.flush_current_block(BlockKind::LoopHeader);
        }

        // 2. Loop body
        if let Some(body) = self.language_plugin.get_control_flow_body(node) {
            self.visit_block_statements(&body, source);
            self.flush_current_block(BlockKind::Statement);
        }
    }

    /// Process match/switch/when construct
    fn process_match(&mut self, node: &Node, source: &str) {
        // Each arm/case is a separate block
        let arms = self.language_plugin.get_match_arms(node);
        for arm in arms {
            self.visit_block_statements(&arm, source);
            self.flush_current_block(BlockKind::Statement);
        }
    }

    /// Process try/catch/finally construct
    fn process_try(&mut self, node: &Node, source: &str) {
        // 1. Try block
        if let Some(body) = self.language_plugin.get_control_flow_body(node) {
            self.visit_block_statements(&body, source);
            self.flush_current_block(BlockKind::Try);
        }

        // 2. Exception handlers
        let handlers = self.language_plugin.get_exception_handlers(node);

        // Catch blocks
        for catch_block in handlers.catch_blocks {
            if let Some(catch_body) = self.language_plugin.get_control_flow_body(&catch_block) {
                self.visit_block_statements(&catch_body, source);
                self.flush_current_block(BlockKind::Catch);
            }
        }

        // Finally block
        if let Some(finally_block) = handlers.finally_block {
            if let Some(finally_body) = self.language_plugin.get_control_flow_body(&finally_block) {
                self.visit_block_statements(&finally_body, source);
                self.flush_current_block(BlockKind::Finally);
            }
        }
    }
}

impl<'a> AstVisitor for BfgVisitor<'a> {
    fn visit_node(&mut self, node: &Node, source: &str, _depth: usize) {
        // Process all nodes (function body assumed)

        // Control flow nodes cause block split
        if self.is_control_flow(node) {
            // Flush current block before control flow
            self.flush_current_block(BlockKind::Statement);

            // Dispatch to appropriate handler based on control flow type
            use crate::features::parsing::ports::ControlFlowType;
            if let Some(cf_type) = self.language_plugin.get_control_flow_type(node) {
                match cf_type {
                    ControlFlowType::If => {
                        self.process_if(node, source);
                    }
                    ControlFlowType::Loop => {
                        self.process_loop(node, source);
                    }
                    ControlFlowType::Match => {
                        self.process_match(node, source);
                    }
                    ControlFlowType::Try => {
                        self.process_try(node, source);
                    }
                    ControlFlowType::Yield => {
                        let span = node_to_span(node);
                        self.current_block_statements.push(span);
                        self.flush_current_block(BlockKind::Yield);
                    }
                    ControlFlowType::Return
                    | ControlFlowType::Break
                    | ControlFlowType::Continue
                    | ControlFlowType::Raise => {
                        let span = node_to_span(node);
                        self.current_block_statements.push(span);
                        self.flush_current_block(BlockKind::Statement);
                    }
                }
            } else {
                // Fallback: treat as generic control flow (shouldn't happen if plugin is correct)
                let span = node_to_span(node);
                self.current_block_statements.push(span);
                self.flush_current_block(BlockKind::Statement);
            }
        }
        // Regular statements accumulate
        else if self.is_statement(node) {
            let span = node_to_span(node);
            self.current_block_statements.push(span);
        }
    }

    fn enter_node(&mut self, _node: &Node, _source: &str, _depth: usize) {
        // BFG visitor는 function body만 처리
        // Entry block은 processor에서 생성
    }

    fn exit_node(&mut self, _node: &Node, _source: &str, _depth: usize) {
        // Exit block은 processor에서 생성
    }
}

fn node_to_span(node: &Node) -> Span {
    let start_pos = node.start_position();
    let end_pos = node.end_position();

    Span::new(
        start_pos.row as u32 + 1,
        start_pos.column as u32,
        end_pos.row as u32 + 1,
        end_pos.column as u32,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::infrastructure::visitor::traverse_with_visitor;
    use tree_sitter::Parser;

    fn parse_python(code: &str) -> tree_sitter::Tree {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        parser.parse(code, None).unwrap()
    }

    #[test]
    fn test_bfg_visitor_simple() {
        let code = r#"
def test():
    x = 1
    return x
"#;

        let tree = parse_python(code);
        let python_plugin = crate::features::parsing::plugins::PythonPlugin::new();
        let mut visitor = BfgVisitor::new(&python_plugin);
        visitor.set_function_id("test_func".to_string());

        traverse_with_visitor(&tree.root_node(), code, &mut visitor);
        visitor.finalize(); // Flush final block

        let blocks = visitor.get_blocks();
        assert!(blocks.len() > 0, "Should have blocks");
    }

    #[test]
    fn test_bfg_visitor_control_flow() {
        let code = r#"
def test(x):
    if x > 0:
        return x
    else:
        return 0
"#;

        let tree = parse_python(code);
        let python_plugin = crate::features::parsing::plugins::PythonPlugin::new();
        let mut visitor = BfgVisitor::new(&python_plugin);
        visitor.set_function_id("test_func".to_string());

        traverse_with_visitor(&tree.root_node(), code, &mut visitor);

        let blocks = visitor.get_blocks();

        // Should have: condition block (if statement)
        // Note: "Condition" matches Python's BFGBlockKind.CONDITION
        let condition_blocks = blocks.iter().filter(|b| b.kind == "Condition").count();
        assert!(
            condition_blocks > 0,
            "Should have condition blocks for if statement"
        );
    }
}
