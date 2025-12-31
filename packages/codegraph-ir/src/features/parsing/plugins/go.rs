//! Go Language Plugin
//!
//! Implements LanguagePlugin for Go source code.
//! Supports: structs, interfaces, functions, methods, goroutines, channels

use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::features::parsing::ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, SpanExt,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Result};

/// Go language plugin
pub struct GoPlugin;

impl GoPlugin {
    pub fn new() -> Self {
        Self
    }

    /// Extract type declaration (struct, interface)
    fn extract_type_decl(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // type_declaration contains type_spec(s)
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "type_spec" {
                self.extract_type_spec(ctx, &child, id_gen, result);
            }
        }
    }

    /// Extract type spec
    fn extract_type_spec(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let name = node
            .child_by_field_name("name")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default();

        if name.is_empty() {
            return;
        }

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        // Determine kind based on type
        let type_node = node.child_by_field_name("type");
        let kind = if let Some(type_n) = type_node {
            match type_n.kind() {
                "struct_type" => NodeKind::Struct,
                "interface_type" => NodeKind::Interface,
                "channel_type" => NodeKind::Channel,
                _ => NodeKind::TypeAlias,
            }
        } else {
            NodeKind::TypeAlias
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            kind.clone(),
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        result.add_node(ir_node);

        // Extract struct fields or interface methods
        if let Some(type_n) = type_node {
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            ctx.push_scope(&name);

            match type_n.kind() {
                "struct_type" => self.extract_struct_fields(ctx, &type_n, id_gen, result),
                "interface_type" => self.extract_interface_methods(ctx, &type_n, id_gen, result),
                _ => {}
            }

            ctx.pop_scope();
            ctx.parent_id = old_parent;
        }
    }

    /// Extract function declaration
    fn extract_function(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let name = node
            .child_by_field_name("name")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default();

        if name.is_empty() {
            return;
        }

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Function,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        result.add_node(ir_node);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Scan body for goroutines and channel operations
        if let Some(body) = node.child_by_field_name("body") {
            self.scan_goroutines_and_channels(ctx, &body, result, &node_id);
        }
    }

    /// Extract method declaration (function with receiver)
    fn extract_method(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let name = node
            .child_by_field_name("name")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default();

        if name.is_empty() {
            return;
        }

        // Get receiver type
        let receiver_type = if let Some(receiver) = node.child_by_field_name("receiver") {
            let mut found_type = String::new();
            for i in 0..receiver.child_count() {
                if let Some(child) = receiver.child(i) {
                    if child.kind() == "parameter_declaration" {
                        if let Some(type_node) = child.child_by_field_name("type") {
                            found_type = ctx.node_text(&type_node).to_string();
                            break;
                        }
                    }
                }
            }
            found_type
                .trim_matches(|c| c == '*' || c == '(' || c == ')')
                .to_string()
        } else {
            String::new()
        };

        let node_id = id_gen.next_node();
        let fqn = if receiver_type.is_empty() {
            name.clone()
        } else {
            format!("{}.{}", receiver_type, name)
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Method,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        result.add_node(ir_node);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Scan body for goroutines and channel operations
        if let Some(body) = node.child_by_field_name("body") {
            self.scan_goroutines_and_channels(ctx, &body, result, &node_id);
        }
    }

    /// Extract struct fields
    fn extract_struct_fields(
        &self,
        ctx: &ExtractionContext,
        struct_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = struct_node.walk();
        for child in struct_node.children(&mut cursor) {
            if child.kind() == "field_declaration_list" {
                let mut field_cursor = child.walk();
                for field in child.children(&mut field_cursor) {
                    if field.kind() == "field_declaration" {
                        // Field can have multiple names
                        let mut name_cursor = field.walk();
                        for name_node in field.children(&mut name_cursor) {
                            if name_node.kind() == "field_identifier" {
                                let name = ctx.node_text(&name_node).to_string();
                                if name.is_empty() {
                                    continue;
                                }

                                let node_id = id_gen.next_node();
                                let fqn = format!("{}.{}", ctx.fqn_prefix(), name);

                                let mut ir_node = Node::new(
                                    node_id,
                                    NodeKind::Field,
                                    fqn,
                                    ctx.file_path.to_string(),
                                    name_node.to_span(),
                                )
                                .with_language(ctx.language.name().to_string())
                                .with_name(name);

                                if let Some(ref parent) = ctx.parent_id {
                                    ir_node.parent_id = Some(parent.clone());
                                }

                                result.add_node(ir_node);
                            }
                        }
                    }
                }
            }
        }
    }

    /// Extract interface methods (signatures)
    fn extract_interface_methods(
        &self,
        ctx: &ExtractionContext,
        iface_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = iface_node.walk();
        for child in iface_node.children(&mut cursor) {
            if child.kind() == "method_spec_list" {
                let mut method_cursor = child.walk();
                for method in child.children(&mut method_cursor) {
                    if method.kind() == "method_spec" {
                        if let Some(name_node) = method.child_by_field_name("name") {
                            let name = ctx.node_text(&name_node).to_string();
                            if name.is_empty() {
                                continue;
                            }

                            let node_id = id_gen.next_node();
                            let fqn = format!("{}.{}", ctx.fqn_prefix(), name);

                            let mut ir_node = Node::new(
                                node_id,
                                NodeKind::Method,
                                fqn,
                                ctx.file_path.to_string(),
                                method.to_span(),
                            )
                            .with_language(ctx.language.name().to_string())
                            .with_name(name);

                            if let Some(ref parent) = ctx.parent_id {
                                ir_node.parent_id = Some(parent.clone());
                            }

                            result.add_node(ir_node);
                        }
                    } else if method.kind() == "type_identifier" {
                        // Embedded interface
                        let iface_name = ctx.node_text(&method).to_string();
                        if let Some(ref parent) = ctx.parent_id {
                            result.add_edge(Edge::new(
                                parent.clone(),
                                format!("ref:{}", iface_name),
                                EdgeKind::Extends,
                            ));
                        }
                    }
                }
            }
        }
    }

    /// Extract import
    fn extract_import(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // import_declaration can contain multiple import_spec
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "import_spec_list" {
                let mut spec_cursor = child.walk();
                for spec in child.children(&mut spec_cursor) {
                    if spec.kind() == "import_spec" {
                        self.extract_import_spec(ctx, &spec, id_gen, result);
                    }
                }
            } else if child.kind() == "import_spec" {
                self.extract_import_spec(ctx, &child, id_gen, result);
            }
        }
    }

    fn extract_import_spec(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        if let Some(path_node) = node.child_by_field_name("path") {
            let path = ctx.node_text(&path_node).to_string();
            let node_id = id_gen.next_node();

            let ir_node = Node::new(
                node_id,
                NodeKind::Import,
                format!("import:{}", path),
                ctx.file_path.to_string(),
                node.to_span(),
            )
            .with_language(ctx.language.name().to_string())
            .with_name(path);

            result.add_node(ir_node);
        }
    }

    /// Extract parameters
    fn extract_parameters(
        &self,
        ctx: &ExtractionContext,
        params_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        func_id: &str,
    ) {
        let mut cursor = params_node.walk();
        for child in params_node.children(&mut cursor) {
            if child.kind() == "parameter_declaration" {
                // Can have multiple names per declaration
                let mut name_cursor = child.walk();
                for name_node in child.children(&mut name_cursor) {
                    if name_node.kind() == "identifier" {
                        let name = ctx.node_text(&name_node).to_string();
                        if name.is_empty() {
                            continue;
                        }

                        let node_id = id_gen.next_node();
                        let fqn = format!("{}.{}", ctx.fqn_prefix(), name);

                        let mut ir_node = Node::new(
                            node_id,
                            NodeKind::Parameter,
                            fqn,
                            ctx.file_path.to_string(),
                            name_node.to_span(),
                        )
                        .with_language(ctx.language.name().to_string())
                        .with_name(name);

                        ir_node.parent_id = Some(func_id.to_string());
                        result.add_node(ir_node);
                    }
                }
            }
        }
    }

    /// Scan for goroutines and channel operations
    fn scan_goroutines_and_channels(
        &self,
        ctx: &ExtractionContext,
        body_node: &TSNode,
        result: &mut ExtractionResult,
        func_id: &str,
    ) {
        self.scan_node_recursive(ctx, body_node, result, func_id);
    }

    fn scan_node_recursive(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        func_id: &str,
    ) {
        match node.kind() {
            "go_statement" => {
                // go func() or go someFunc()
                result.add_edge(Edge::new(
                    func_id.to_string(),
                    "goroutine".to_string(),
                    EdgeKind::SpawnsGoroutine,
                ));
            }
            "send_statement" => {
                // channel <- value
                if let Some(channel) = node.child_by_field_name("channel") {
                    let chan_name = ctx.node_text(&channel).to_string();
                    result.add_edge(Edge::new(
                        func_id.to_string(),
                        format!("ref:{}", chan_name),
                        EdgeKind::ChannelSend,
                    ));
                }
            }
            "receive_expression" => {
                // <- channel
                let chan_text = ctx.node_text(node).to_string();
                result.add_edge(Edge::new(
                    func_id.to_string(),
                    format!("ref:{}", chan_text),
                    EdgeKind::ChannelReceive,
                ));
            }
            _ => {}
        }

        // Recurse
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            self.scan_node_recursive(ctx, &child, result, func_id);
        }
    }

    /// Extract defer statement
    fn extract_defer(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Create Finally node for defer (similar semantics - always executes)
        let defer_node = Node::new(
            node_id.clone(),
            NodeKind::Finally,
            "defer".to_string(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Finally,
            ));
        }

        result.add_node(defer_node);

        // Extract deferred call
        if let Some(call) = node.child_by_field_name("arguments") {
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            self.extract_node(ctx, &call, id_gen, result);
            ctx.parent_id = old_parent;
        }
    }

    /// Extract panic call
    fn extract_panic_call(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Get panic arguments
        let panic_text = ctx.node_text(node).to_string();

        // Create Throw node
        let mut throw_node = Node::new(
            node_id.clone(),
            NodeKind::Throw,
            "panic".to_string(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        // Store panic info in metadata
        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "exception_type".to_string(),
            serde_json::Value::String("panic".to_string()),
        );
        metadata.insert(
            "panic_text".to_string(),
            serde_json::Value::String(panic_text),
        );
        throw_node.metadata = Some(serde_json::to_string(&metadata).unwrap_or_default());

        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Contains,
            ));
        }

        result.add_node(throw_node);
    }

    /// Extract recover call
    fn extract_recover_call(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Create Catch node for recover (catches panic)
        let catch_node = Node::new(
            node_id.clone(),
            NodeKind::Catch,
            "recover()".to_string(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        // Store metadata indicating this is a recover call
        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "exception_types".to_string(),
            serde_json::Value::Array(vec![serde_json::Value::String("panic".to_string())]),
        );
        // Note: recover() doesn't name the variable, it just returns the panic value

        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Catches,
            ));
        }

        result.add_node(catch_node);
    }

    /// Check if call_expression is panic or recover
    fn is_panic_or_recover_call(&self, node: &TSNode, ctx: &ExtractionContext) -> Option<&str> {
        if node.kind() == "call_expression" {
            if let Some(function) = node.child_by_field_name("function") {
                let func_name = ctx.node_text(&function).to_string();
                if func_name == "panic" {
                    return Some("panic");
                } else if func_name == "recover" {
                    return Some("recover");
                }
            }
        }
        None
    }

    /// Extract function literal (Go closures/anonymous functions)
    /// Go: func(x int) int { return x * 2 }
    fn extract_function_literal(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Generate synthetic name using line number
        let line = node.start_position().row + 1;
        let name = format!("func_literal_{}", line);

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        // Build function literal node (closure)
        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Lambda,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Add Captures edge (function literals are closures)
        if let Some(ref parent_id) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent_id.clone(),
                node_id.clone(),
                EdgeKind::Captures,
            ));
        }

        result.add_node(ir_node);

        // Process function literal
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Scan body for goroutines and channel operations
        if let Some(body) = node.child_by_field_name("body") {
            self.scan_goroutines_and_channels(ctx, &body, result, &node_id);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract a single node
    fn extract_node(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        match node.kind() {
            "type_declaration" => self.extract_type_decl(ctx, node, id_gen, result),
            "function_declaration" => self.extract_function(ctx, node, id_gen, result),
            "method_declaration" => self.extract_method(ctx, node, id_gen, result),
            "import_declaration" => self.extract_import(ctx, node, id_gen, result),
            "defer_statement" => self.extract_defer(ctx, node, id_gen, result),
            "func_literal" => self.extract_function_literal(ctx, node, id_gen, result),
            "call_expression" => {
                // Check if it's panic() or recover()
                if let Some(call_type) = self.is_panic_or_recover_call(node, ctx) {
                    match call_type {
                        "panic" => self.extract_panic_call(ctx, node, id_gen, result),
                        "recover" => self.extract_recover_call(ctx, node, id_gen, result),
                        _ => {}
                    }
                } else {
                    // Regular call expression - recurse
                    let mut cursor = node.walk();
                    for child in node.children(&mut cursor) {
                        self.extract_node(ctx, &child, id_gen, result);
                    }
                }
            }
            _ => {
                let mut cursor = node.walk();
                for child in node.children(&mut cursor) {
                    self.extract_node(ctx, &child, id_gen, result);
                }
            }
        }
    }
}

impl Default for GoPlugin {
    fn default() -> Self {
        Self::new()
    }
}

impl LanguagePlugin for GoPlugin {
    fn tree_sitter_language(&self) -> TSLanguage {
        tree_sitter_go::language()
    }

    fn language_id(&self) -> LanguageId {
        LanguageId::Go
    }

    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind> {
        match ts_kind {
            "type_spec" => Some(NodeKind::TypeAlias), // Could be struct/interface
            "function_declaration" => Some(NodeKind::Function),
            "method_declaration" => Some(NodeKind::Method),
            "import_declaration" | "import_spec" => Some(NodeKind::Import),
            "parameter_declaration" => Some(NodeKind::Parameter),
            "field_declaration" => Some(NodeKind::Field),
            _ => None,
        }
    }

    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            "type_declaration" | "type_spec" => SyntaxKind::ClassDef, // struct/interface
            "function_declaration" | "method_declaration" => SyntaxKind::FunctionDef,
            "short_var_declaration" | "var_declaration" => SyntaxKind::AssignmentStmt,
            "import_declaration" => SyntaxKind::ImportDecl,
            "parameter_declaration" => SyntaxKind::ParameterDecl,
            "call_expression" => SyntaxKind::CallExpr,
            "identifier" => SyntaxKind::NameExpr,
            "selector_expression" => SyntaxKind::AttributeExpr,
            "return_statement" => SyntaxKind::ReturnStmt,
            "if_statement" => SyntaxKind::IfStmt,
            "for_statement" => SyntaxKind::ForStmt,
            "block" => SyntaxKind::Block,
            "comment" => SyntaxKind::Comment,
            other => SyntaxKind::Other(other.to_string()),
        }
    }

    fn extract(&self, ctx: &mut ExtractionContext, tree: &Tree) -> Result<ExtractionResult> {
        let mut result = ExtractionResult::new();
        let mut id_gen = IdGenerator::new(format!("{}:{}", ctx.repo_id, ctx.file_path));

        // Create file node
        let file_node_id = id_gen.next_node();
        let file_node = Node::new(
            file_node_id.clone(),
            NodeKind::File,
            ctx.file_path.to_string(),
            ctx.file_path.to_string(),
            tree.root_node().to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(ctx.file_path.to_string());

        result.add_node(file_node);
        ctx.parent_id = Some(file_node_id);

        // Extract package declaration
        let root = tree.root_node();
        let mut cursor = root.walk();
        for child in root.children(&mut cursor) {
            if child.kind() == "package_clause" {
                if let Some(name_node) = child.child_by_field_name("name") {
                    ctx.module_path = Some(ctx.node_text(&name_node).to_string());
                }
            }
            self.extract_node(ctx, &child, &mut id_gen, &mut result);
        }

        Ok(result)
    }

    fn comment_patterns(&self) -> &[&str] {
        &["//", "/*"]
    }

    fn is_public(&self, name: &str) -> bool {
        // Go: exported if starts with uppercase
        name.chars()
            .next()
            .map(|c| c.is_uppercase())
            .unwrap_or(false)
    }

    fn extract_docstring(&self, node: &TSNode, source: &str) -> Option<String> {
        // Go doc comments are line comments before the declaration
        if let Some(prev) = node.prev_sibling() {
            if prev.kind() == "comment" {
                let text = source.get(prev.byte_range())?;
                return Some(text.trim_start_matches("//").trim().to_string());
            }
        }
        None
    }

    fn is_statement_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            // Variable declarations
            "var_declaration" | "const_declaration" | "short_var_declaration" |
            // Assignment
            "assignment_statement" |
            // Expression statements
            "expression_statement" |
            // Control flow
            "if_statement" | "switch_statement" | "select_statement" |
            "for_statement" |
            // Other statements
            "return_statement" | "break_statement" | "continue_statement" |
            "go_statement" | "defer_statement" |
            // Import statements
            "import_declaration" | "package_clause" |
            // Type declarations
            "type_declaration" | "function_declaration" | "method_declaration"
        )
    }

    fn is_control_flow_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            "if_statement"
                | "switch_statement"
                | "select_statement"
                | "for_statement"
                | "expression_case"
                | "default_case"
                | "communication_case"
        )
    }

    fn get_control_flow_type(
        &self,
        node: &TSNode,
    ) -> Option<crate::features::parsing::ports::ControlFlowType> {
        use crate::features::parsing::ports::ControlFlowType;
        match node.kind() {
            "if_statement" => Some(ControlFlowType::If),
            "for_statement" => Some(ControlFlowType::Loop),
            "switch_statement" | "type_switch_statement" | "select_statement" => {
                Some(ControlFlowType::Match)
            }
            "return_statement" => Some(ControlFlowType::Return),
            "break_statement" => Some(ControlFlowType::Break),
            "continue_statement" => Some(ControlFlowType::Continue),
            _ => None,
        }
    }

    fn get_match_arms<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        let mut arms = Vec::new();
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if matches!(
                child.kind(),
                "expression_case" | "default_case" | "communication_case" | "type_case"
            ) {
                arms.push(child);
            }
        }
        arms
    }

    fn is_chained_condition(&self, node: &TSNode) -> bool {
        // Go uses "else if" pattern - if_statement inside else block
        node.kind() == "if_statement"
            && node
                .parent()
                .map(|p| {
                    p.kind() == "block"
                        && p.parent()
                            .map(|pp| pp.kind() == "if_statement")
                            .unwrap_or(false)
                })
                .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    fn parse_go(source: &str) -> Tree {
        let mut parser = Parser::new();
        parser.set_language(&tree_sitter_go::language()).unwrap();
        parser.parse(source, None).unwrap()
    }

    #[test]
    fn test_extract_struct() {
        let source = r#"
package main

type User struct {
    ID   int
    Name string
}
"#;
        let tree = parse_go(source);
        let plugin = GoPlugin::new();
        let mut ctx = ExtractionContext::new(source, "user.go", "test-repo", LanguageId::Go);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let struct_node = result.nodes.iter().find(|n| n.kind == NodeKind::Struct);
        assert!(struct_node.is_some());
        assert_eq!(struct_node.unwrap().name, Some("User".to_string()));

        let fields: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Field)
            .collect();
        assert_eq!(fields.len(), 2);
    }

    #[test]
    fn test_extract_interface() {
        let source = r#"
package main

type Reader interface {
    Read(p []byte) (n int, err error)
}
"#;
        let tree = parse_go(source);
        let plugin = GoPlugin::new();
        let mut ctx = ExtractionContext::new(source, "reader.go", "test-repo", LanguageId::Go);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let iface = result.nodes.iter().find(|n| n.kind == NodeKind::Interface);
        assert!(iface.is_some());
    }

    #[test]
    fn test_extract_method() {
        let source = r#"
package main

func (u *User) String() string {
    return u.Name
}
"#;
        let tree = parse_go(source);
        let plugin = GoPlugin::new();
        let mut ctx = ExtractionContext::new(source, "user.go", "test-repo", LanguageId::Go);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let method = result.nodes.iter().find(|n| n.kind == NodeKind::Method);
        assert!(method.is_some());
        assert!(method.unwrap().fqn.contains("User.String"));
    }

    #[test]
    fn test_goroutine_detection() {
        let source = r#"
package main

func worker() {
    go process()
}
"#;
        let tree = parse_go(source);
        let plugin = GoPlugin::new();
        let mut ctx = ExtractionContext::new(source, "worker.go", "test-repo", LanguageId::Go);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let goroutine_edge = result
            .edges
            .iter()
            .find(|e| e.kind == EdgeKind::SpawnsGoroutine);
        assert!(goroutine_edge.is_some());
    }
}
