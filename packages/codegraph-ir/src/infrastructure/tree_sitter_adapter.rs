/*
 * Infrastructure: tree-sitter Adapter
 *
 * Implements AstParser port with tree-sitter
 *
 * NOTE: Due to tree-sitter's lifetime requirements, we use a different approach:
 * - Store Tree + Node together
 * - Use Rc for shared ownership
 */

use crate::domain::ports::{AstParser, AstTree, AstNode};
use tree_sitter::{Parser, Tree, Node};
use std::rc::Rc;

/// tree-sitter parser adapter
pub struct TreeSitterParser {
    _marker: std::marker::PhantomData<()>,
}

impl TreeSitterParser {
    pub fn new() -> Self {
        Self {
            _marker: std::marker::PhantomData,
        }
    }
}

impl AstParser for TreeSitterParser {
    fn parse(&self, content: &str) -> Result<Box<dyn AstTree>, String> {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .map_err(|e| format!("Failed to set language: {}", e))?;
        
        let tree = parser
            .parse(content, None)
            .ok_or_else(|| "Failed to parse content".to_string())?;
        
        Ok(Box::new(TreeSitterTree { 
            tree: Rc::new(tree),
        }))
    }
}

/// tree-sitter tree wrapper
struct TreeSitterTree {
    tree: Rc<Tree>,
}

impl AstTree for TreeSitterTree {
    fn root_node(&self) -> Box<dyn AstNode> {
        Box::new(TreeSitterNode {
            tree: Rc::clone(&self.tree),
            node_data: NodeData::from_node(&self.tree.root_node()),
        })
    }
}

/// Node data (extracted from tree-sitter Node)
#[derive(Clone)]
struct NodeData {
    kind: String,
    start_byte: usize,
    end_byte: usize,
    start_line: u32,
    start_column: u32,
    end_line: u32,
    end_column: u32,
    child_count: usize,
}

impl NodeData {
    fn from_node(node: &Node) -> Self {
        Self {
            kind: node.kind().to_string(),
            start_byte: node.start_byte(),
            end_byte: node.end_byte(),
            start_line: node.start_position().row as u32 + 1,
            start_column: node.start_position().column as u32,
            end_line: node.end_position().row as u32 + 1,
            end_column: node.end_position().column as u32,
            child_count: node.child_count(),
        }
    }
}

/// tree-sitter node wrapper
struct TreeSitterNode {
    tree: Rc<Tree>,
    node_data: NodeData,
}

impl AstNode for TreeSitterNode {
    fn kind(&self) -> &str {
        &self.node_data.kind
    }
    
    fn child_count(&self) -> usize {
        self.node_data.child_count
    }
    
    fn child(&self, index: usize) -> Option<Box<dyn AstNode>> {
        // Recreate node from tree to get child
        let root = self.tree.root_node();
        let node = find_node_at(&root, &self.node_data)?;
        
        node.child(index).map(|child| {
            Box::new(TreeSitterNode {
                tree: Rc::clone(&self.tree),
                node_data: NodeData::from_node(&child),
            }) as Box<dyn AstNode>
        })
    }
    
    fn start_byte(&self) -> usize {
        self.node_data.start_byte
    }
    
    fn end_byte(&self) -> usize {
        self.node_data.end_byte
    }
    
    fn start_line(&self) -> u32 {
        self.node_data.start_line
    }
    
    fn start_column(&self) -> u32 {
        self.node_data.start_column
    }
    
    fn end_line(&self) -> u32 {
        self.node_data.end_line
    }
    
    fn end_column(&self) -> u32 {
        self.node_data.end_column
    }
}

/// Find node in tree by matching position
fn find_node_at<'a>(root: &'a Node<'a>, target: &NodeData) -> Option<Node<'a>> {
    if root.start_byte() == target.start_byte && root.end_byte() == target.end_byte {
        return Some(*root);
    }
    
    for i in 0..root.child_count() {
        if let Some(child) = root.child(i) {
            if let Some(found) = find_node_at(&child, target) {
                return Some(found);
            }
        }
    }
    
    None
}

