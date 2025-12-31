// Infrastructure: NodeMatcher - Selector to Node matching
// Maps to Python: NodeMatcher

use super::graph_index::GraphIndex;
use crate::features::query_engine::domain::{NodeSelector, NodeSelectorType, SelectorValue};
use crate::shared::models::{Node, NodeKind};

/// Node Matcher - Converts selectors to actual nodes
///
/// Maps domain selectors to infrastructure nodes using GraphIndex
pub struct NodeMatcher<'a> {
    index: &'a GraphIndex,
}

impl<'a> NodeMatcher<'a> {
    pub fn new(index: &'a GraphIndex) -> Self {
        Self { index }
    }

    /// Match selector to nodes (O(1) lookup + O(k) filter)
    pub fn match_nodes(&self, selector: &NodeSelector) -> Vec<&Node> {
        match selector.selector_type {
            NodeSelectorType::Var => self.match_var(selector),
            NodeSelectorType::Func => self.match_func(selector),
            NodeSelectorType::Call => self.match_call(selector),
            NodeSelectorType::Block => self.match_block(selector),
            NodeSelectorType::Expr => self.match_expr(selector),
            NodeSelectorType::Class => self.match_class(selector),
            NodeSelectorType::Module => self.match_module(selector),
            NodeSelectorType::Field => self.match_field(selector),
            NodeSelectorType::Source => self.match_source(selector),
            NodeSelectorType::Sink => self.match_sink(selector),
            NodeSelectorType::Any => self.match_any(),
        }
    }

    fn match_var(&self, selector: &NodeSelector) -> Vec<&Node> {
        if let Some(name) = selector.get_string("name") {
            self.index
                .find_nodes_by_name(name)
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Variable))
                .collect()
        } else {
            // Wildcard: all variables
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Variable))
                .collect()
        }
    }

    fn match_func(&self, selector: &NodeSelector) -> Vec<&Node> {
        if let Some(name) = selector.get_string("name") {
            self.index
                .find_nodes_by_name(name)
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Function))
                .collect()
        } else {
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Function))
                .collect()
        }
    }

    fn match_call(&self, selector: &NodeSelector) -> Vec<&Node> {
        if let Some(name) = selector.get_string("name") {
            self.index
                .find_nodes_by_name(name)
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Function))
                .collect()
        } else {
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Function))
                .collect()
        }
    }

    fn match_block(&self, selector: &NodeSelector) -> Vec<&Node> {
        // Block kind matching (CFG blocks)
        if let Some(_kind) = selector.get_string("kind") {
            // INTEGRATION(v2): CFG block kind matching
            // - Current: Returns Class nodes as placeholder
            // - Improvement: Match NodeKind::Block with CFGBlockKind
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Class))
                .collect()
        } else {
            // All blocks
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Class))
                .collect()
        }
    }

    fn match_expr(&self, selector: &NodeSelector) -> Vec<&Node> {
        // Expression kind matching
        if let Some(_kind) = selector.get_string("kind") {
            // INTEGRATION(v2): Expression IR kind matching
            // - Current: Returns Variable nodes as placeholder
            // - Improvement: Match NodeKind::Expression with ExprKind
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Variable))
                .collect()
        } else {
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Variable))
                .collect()
        }
    }

    fn match_class(&self, selector: &NodeSelector) -> Vec<&Node> {
        if let Some(name) = selector.get_string("name") {
            self.index
                .find_nodes_by_name(name)
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Class))
                .collect()
        } else {
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Class))
                .collect()
        }
    }

    fn match_module(&self, selector: &NodeSelector) -> Vec<&Node> {
        if let Some(_pattern) = selector.get_string("pattern") {
            // FEATURE(v2): Glob pattern matching (e.g., "auth.*")
            // - Current: Returns all modules (pattern ignored)
            // - Improvement: Use glob crate for pattern matching
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Module))
                .collect()
        } else {
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Module))
                .collect()
        }
    }

    fn match_field(&self, selector: &NodeSelector) -> Vec<&Node> {
        // Field-sensitive matching
        if let Some(_obj) = selector.get_string("obj") {
            // FEATURE(v2): Field-sensitive analysis (e.g., "user.email")
            // - Current: Returns all Field nodes (obj ignored)
            // - Improvement: Match obj.field pairs using PTA alias info
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Field))
                .collect()
        } else {
            self.index
                .get_all_nodes()
                .into_iter()
                .filter(|n| matches!(n.kind, NodeKind::Field))
                .collect()
        }
    }

    fn match_source(&self, selector: &NodeSelector) -> Vec<&Node> {
        // Taint source matching
        let category = selector.get_string("category").unwrap_or("request");

        // Default source patterns
        let source_names = match category {
            "request" => vec!["input", "request", "get", "post"],
            "file" => vec!["open", "read", "readline"],
            "env" => vec!["environ", "getenv", "argv"],
            "socket" => vec!["socket", "recv", "accept"],
            "database" => vec!["query", "fetchone", "fetchall"],
            _ => vec![],
        };

        self.index
            .get_all_nodes()
            .into_iter()
            .filter(|n| {
                if let Some(name) = &n.name {
                    source_names.iter().any(|s| name.contains(s))
                } else {
                    false
                }
            })
            .collect()
    }

    fn match_sink(&self, selector: &NodeSelector) -> Vec<&Node> {
        // Taint sink matching
        let category = selector.get_string("category").unwrap_or("execute");

        // Default sink patterns
        let sink_names = match category {
            "execute" => vec!["eval", "exec", "system", "subprocess"],
            "sql" => vec!["execute", "query", "executemany"],
            "file" => vec!["write", "writelines", "dump"],
            "log" => vec!["logger", "print", "log"],
            "network" => vec!["send", "sendto"],
            _ => vec![],
        };

        self.index
            .get_all_nodes()
            .into_iter()
            .filter(|n| {
                if let Some(name) = &n.name {
                    sink_names.iter().any(|s| name.contains(s))
                } else {
                    false
                }
            })
            .collect()
    }

    fn match_any(&self) -> Vec<&Node> {
        // Wildcard: all nodes
        self.index.get_all_nodes()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::features::query_engine::domain::Q;
    use crate::shared::models::Span;

    fn create_test_graph() -> GraphIndex {
        let mut ir_doc = IRDocument::new("test.py".to_string());

        ir_doc.nodes.push(Node {
            id: "var1".to_string(),
            kind: NodeKind::Variable,
            fqn: "test.user".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 1, 1, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("user".to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        });

        ir_doc.nodes.push(Node {
            id: "call1".to_string(),
            kind: NodeKind::Function,
            fqn: "test.execute".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(2, 1, 2, 10),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("execute".to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        });

        ir_doc.nodes.push(Node {
            id: "func1".to_string(),
            kind: NodeKind::Function,
            fqn: "test.process".to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(3, 1, 3, 20),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("process".to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        });

        GraphIndex::new(&ir_doc)
    }

    #[test]
    fn test_match_var() {
        let index = create_test_graph();
        let matcher = NodeMatcher::new(&index);

        let nodes = matcher.match_nodes(&Q::var("user"));
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].id, "var1");
    }

    #[test]
    fn test_match_call() {
        let index = create_test_graph();
        let matcher = NodeMatcher::new(&index);

        let nodes = matcher.match_nodes(&Q::call("execute"));
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].id, "call1");
    }

    #[test]
    fn test_match_func() {
        let index = create_test_graph();
        let matcher = NodeMatcher::new(&index);

        let nodes = matcher.match_nodes(&Q::func("process"));
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].id, "func1");
    }

    #[test]
    fn test_match_any() {
        let index = create_test_graph();
        let matcher = NodeMatcher::new(&index);

        let nodes = matcher.match_nodes(&Q::any());
        assert_eq!(nodes.len(), 3); // All nodes
    }
}
