//! Java Language Plugin
//!
//! Implements LanguagePlugin for Java source code.
//! Supports: classes, interfaces, enums, records, annotations, generics

use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::features::parsing::ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, SpanExt,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Result};

/// Java language plugin
pub struct JavaPlugin;

impl JavaPlugin {
    pub fn new() -> Self {
        Self
    }

    /// Extract class declaration
    fn extract_class(
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

        // Determine kind
        let kind = match node.kind() {
            "interface_declaration" => NodeKind::Interface,
            "enum_declaration" => NodeKind::Enum,
            "record_declaration" => NodeKind::Record,
            "annotation_type_declaration" => NodeKind::AnnotationDecl,
            _ => NodeKind::Class,
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            kind,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        // Extract Javadoc
        if let Some(doc) = self.extract_javadoc(node, ctx.source) {
            ir_node = ir_node.with_docstring(doc);
        }

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
            // Add defines edge
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Defines,
            ));
        }

        // Extract type parameters (generics)
        self.extract_type_parameters(ctx, node, id_gen, result, &node_id);

        // Extract superclass
        if let Some(superclass) = node.child_by_field_name("superclass") {
            let base_name = ctx.node_text(&superclass).to_string();
            if !base_name.is_empty() && base_name != "type_identifier" {
                result.add_edge(Edge::new(
                    node_id.clone(),
                    format!("ref:{}", base_name),
                    EdgeKind::Extends,
                ));
            }
        }

        // Extract interfaces
        if let Some(interfaces) = node.child_by_field_name("interfaces") {
            self.extract_implements(ctx, &interfaces, result, &node_id);
        }

        // Extract annotations
        self.extract_annotations(ctx, node, result, &node_id);

        result.add_node(ir_node);

        // Process body
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        if let Some(body) = node.child_by_field_name("body") {
            self.extract_body(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract method declaration
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

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        let kind = if node.kind() == "constructor_declaration" {
            NodeKind::Function // Constructor
        } else {
            NodeKind::Method
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            kind,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        // Extract Javadoc
        if let Some(doc) = self.extract_javadoc(node, ctx.source) {
            ir_node = ir_node.with_docstring(doc);
        }

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Extract annotations
        self.extract_annotations(ctx, node, result, &node_id);

        // Check for @Async annotation (Spring framework)
        // is_async detection: check modifiers/annotations for @Async keyword
        // Note: requires modifiers child traversal (Spring-specific)

        // Add edges from parent
        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Defines,
            ));
        }

        // Check for @Override
        if self.has_override_annotation(node, ctx.source) {
            // We'd ideally link to the overridden method
            result.add_edge(Edge::new(
                node_id.clone(),
                "ref:super".to_string(),
                EdgeKind::Overrides,
            ));
        }

        // Extract throws
        if let Some(throws) = node.child_by_field_name("throws") {
            self.extract_throws(ctx, &throws, result, &node_id);
        }

        result.add_node(ir_node);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }
    }

    /// Extract field declaration
    fn extract_field(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Get declarator (name and optional initializer)
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "variable_declarator" {
                if let Some(name_node) = child.child_by_field_name("name") {
                    let name = ctx.node_text(&name_node).to_string();
                    if name.is_empty() {
                        continue;
                    }

                    let node_id = id_gen.next_node();
                    let fqn = if ctx.fqn_prefix().is_empty() {
                        name.clone()
                    } else {
                        format!("{}.{}", ctx.fqn_prefix(), name)
                    };

                    let mut ir_node = Node::new(
                        node_id.clone(),
                        NodeKind::Field,
                        fqn,
                        ctx.file_path.to_string(),
                        name_node.to_span(),
                    )
                    .with_language(ctx.language.name().to_string())
                    .with_name(name);

                    if let Some(ref parent) = ctx.parent_id {
                        ir_node.parent_id = Some(parent.clone());
                        result.add_edge(Edge::new(
                            parent.clone(),
                            node_id.clone(),
                            EdgeKind::Defines,
                        ));
                    }

                    result.add_node(ir_node);
                }
            }
        }
    }

    /// Extract import declaration
    fn extract_import(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();
        let import_text = ctx.node_text(node).to_string();

        // Extract the imported name
        let mut cursor = node.walk();
        let imported = node
            .children(&mut cursor)
            .find(|c| c.kind() == "scoped_identifier" || c.kind() == "identifier")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or(import_text);

        let ir_node = Node::new(
            node_id,
            NodeKind::Import,
            format!("import:{}", imported),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(imported);

        result.add_node(ir_node);
    }

    /// Extract enum constant
    fn extract_enum_constant(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        parent_id: &str,
    ) {
        let name = node
            .child_by_field_name("name")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default();

        if name.is_empty() {
            return;
        }

        let node_id = id_gen.next_node();
        let fqn = format!("{}.{}", ctx.fqn_prefix(), name);

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::EnumMember,
            fqn,
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name);

        ir_node.parent_id = Some(parent_id.to_string());
        result.add_edge(Edge::new(
            parent_id.to_string(),
            node_id.clone(),
            EdgeKind::Defines,
        ));

        result.add_node(ir_node);
    }

    /// Extract parameters
    fn extract_parameters(
        &self,
        ctx: &ExtractionContext,
        params_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        method_id: &str,
    ) {
        let mut cursor = params_node.walk();
        for child in params_node.children(&mut cursor) {
            if child.kind() == "formal_parameter" || child.kind() == "spread_parameter" {
                if let Some(name_node) = child.child_by_field_name("name") {
                    let name = ctx.node_text(&name_node).to_string();
                    if name.is_empty() {
                        continue;
                    }

                    let node_id = id_gen.next_node();
                    let fqn = format!("{}.{}", ctx.fqn_prefix(), name);

                    let mut ir_node = Node::new(
                        node_id.clone(),
                        NodeKind::Parameter,
                        fqn,
                        ctx.file_path.to_string(),
                        name_node.to_span(),
                    )
                    .with_language(ctx.language.name().to_string())
                    .with_name(name);

                    ir_node.parent_id = Some(method_id.to_string());
                    result.add_node(ir_node);
                }
            }
        }
    }

    /// Extract type parameters (generics)
    fn extract_type_parameters(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        parent_id: &str,
    ) {
        if let Some(type_params) = node.child_by_field_name("type_parameters") {
            let mut cursor = type_params.walk();
            for child in type_params.children(&mut cursor) {
                if child.kind() == "type_parameter" {
                    let name = ctx.node_text(&child).to_string();
                    // Extract just the name part (before extends/super)
                    let type_name = name.split_whitespace().next().unwrap_or(&name);

                    let node_id = id_gen.next_node();
                    let mut ir_node = Node::new(
                        node_id.clone(),
                        NodeKind::TypeParameter,
                        format!("{}.{}", ctx.fqn_prefix(), type_name),
                        ctx.file_path.to_string(),
                        child.to_span(),
                    )
                    .with_language(ctx.language.name().to_string())
                    .with_name(type_name.to_string());

                    ir_node.parent_id = Some(parent_id.to_string());
                    result.add_node(ir_node);

                    // Extract bounds (extends)
                    if let Some(bounds) = child.child_by_field_name("bounds") {
                        let bound_text = ctx.node_text(&bounds).to_string();
                        result.add_edge(Edge::new(
                            node_id,
                            format!("ref:{}", bound_text),
                            EdgeKind::BoundedBy,
                        ));
                    }
                }
            }
        }
    }

    /// Extract implements clause
    fn extract_implements(
        &self,
        ctx: &ExtractionContext,
        interfaces_node: &TSNode,
        result: &mut ExtractionResult,
        class_id: &str,
    ) {
        let mut cursor = interfaces_node.walk();
        for child in interfaces_node.children(&mut cursor) {
            if child.kind() == "type_identifier" || child.kind() == "generic_type" {
                let iface_name = ctx.node_text(&child).to_string();
                if !iface_name.is_empty() {
                    result.add_edge(Edge::new(
                        class_id.to_string(),
                        format!("ref:{}", iface_name),
                        EdgeKind::Implements,
                    ));
                }
            }
        }
    }

    /// Extract annotations
    fn extract_annotations(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        target_id: &str,
    ) {
        // Look for annotations in modifiers
        if let Some(modifiers) = node.child_by_field_name("modifiers") {
            let mut cursor = modifiers.walk();
            for child in modifiers.children(&mut cursor) {
                if child.kind() == "annotation" || child.kind() == "marker_annotation" {
                    let anno_text = ctx.node_text(&child).to_string();
                    result.add_edge(Edge::new(
                        target_id.to_string(),
                        format!("ref:{}", anno_text),
                        EdgeKind::AnnotatedWith,
                    ));
                }
            }
        }
    }

    /// Check for @Override annotation
    fn has_override_annotation(&self, node: &TSNode, source: &str) -> bool {
        if let Some(modifiers) = node.child_by_field_name("modifiers") {
            let mut cursor = modifiers.walk();
            for child in modifiers.children(&mut cursor) {
                if child.kind() == "annotation" || child.kind() == "marker_annotation" {
                    let text = source.get(child.byte_range()).unwrap_or("");
                    if text.contains("Override") {
                        return true;
                    }
                }
            }
        }
        false
    }

    /// Check for @Async annotation (Spring framework)
    fn has_async_annotation(&self, node: &TSNode, source: &str) -> bool {
        if let Some(modifiers) = node.child_by_field_name("modifiers") {
            let mut cursor = modifiers.walk();
            for child in modifiers.children(&mut cursor) {
                if child.kind() == "annotation" || child.kind() == "marker_annotation" {
                    let text = source.get(child.byte_range()).unwrap_or("");
                    if text.contains("Async") {
                        return true;
                    }
                }
            }
        }
        false
    }

    /// Extract throws clause
    fn extract_throws(
        &self,
        ctx: &ExtractionContext,
        throws_node: &TSNode,
        result: &mut ExtractionResult,
        method_id: &str,
    ) {
        let mut cursor = throws_node.walk();
        for child in throws_node.children(&mut cursor) {
            if child.kind() == "type_identifier" {
                let exc_name = ctx.node_text(&child).to_string();
                result.add_edge(Edge::new(
                    method_id.to_string(),
                    format!("ref:{}", exc_name),
                    EdgeKind::Throws,
                ));
            }
        }
    }

    /// Extract Javadoc comment
    fn extract_javadoc(&self, node: &TSNode, source: &str) -> Option<String> {
        // Look for preceding block_comment that starts with /**
        let mut cursor = node.walk();
        if cursor.goto_first_child() {
            loop {
                let child = cursor.node();
                if child.kind() == "block_comment" {
                    let text = source.get(child.byte_range())?;
                    if text.starts_with("/**") {
                        // Strip /** and */ and clean up
                        let doc = text
                            .trim_start_matches("/**")
                            .trim_end_matches("*/")
                            .lines()
                            .map(|l| l.trim().trim_start_matches('*').trim())
                            .collect::<Vec<_>>()
                            .join("\n");
                        return Some(doc.trim().to_string());
                    }
                }
                if !cursor.goto_next_sibling() {
                    break;
                }
            }
        }
        None
    }

    /// Extract body (class/interface body)
    fn extract_body(
        &self,
        ctx: &mut ExtractionContext,
        body_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = body_node.walk();
        for child in body_node.children(&mut cursor) {
            self.extract_node(ctx, &child, id_gen, result);
        }
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
            "class_declaration"
            | "interface_declaration"
            | "enum_declaration"
            | "record_declaration"
            | "annotation_type_declaration" => self.extract_class(ctx, node, id_gen, result),
            "method_declaration" | "constructor_declaration" => {
                self.extract_method(ctx, node, id_gen, result)
            }
            "field_declaration" => self.extract_field(ctx, node, id_gen, result),
            "import_declaration" => self.extract_import(ctx, node, id_gen, result),
            "enum_constant" => {
                if let Some(ref parent) = ctx.parent_id {
                    self.extract_enum_constant(ctx, node, id_gen, result, parent);
                }
            }
            "try_statement" | "try_with_resources_statement" => {
                self.extract_try(ctx, node, id_gen, result)
            }
            "throw_statement" => self.extract_throw(ctx, node, id_gen, result),
            "lambda_expression" => self.extract_lambda(ctx, node, id_gen, result),
            "method_reference" => self.extract_method_reference(ctx, node, id_gen, result),
            _ => {
                // Recurse for nested declarations
                let mut cursor = node.walk();
                for child in node.children(&mut cursor) {
                    self.extract_node(ctx, &child, id_gen, result);
                }
            }
        }
    }

    /// Extract try-catch-finally statement
    fn extract_try(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Create Try node
        let try_node = Node::new(
            node_id.clone(),
            NodeKind::Try,
            "try".to_string(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Contains,
            ));
        }

        result.add_node(try_node);

        // Extract try body
        if let Some(body) = node.child_by_field_name("body") {
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            self.extract_body(ctx, &body, id_gen, result);
            ctx.parent_id = old_parent;
        }

        // Extract catch clauses
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "catch_clause" {
                self.extract_catch(ctx, &child, id_gen, result, &node_id);
            } else if child.kind() == "finally_clause" {
                self.extract_finally(ctx, &child, id_gen, result, &node_id);
            }
        }

        // Extract resources (try-with-resources)
        if let Some(resources) = node.child_by_field_name("resources") {
            // Process resource declarations
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            self.extract_node(ctx, &resources, id_gen, result);
            ctx.parent_id = old_parent;
        }
    }

    /// Extract catch clause
    fn extract_catch(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        try_id: &str,
    ) {
        let node_id = id_gen.next_node();

        // Get exception parameter (type and variable)
        let (exception_types, exception_var) =
            if let Some(param) = node.child_by_field_name("parameter") {
                let var_name = param
                    .child_by_field_name("name")
                    .map(|n| ctx.node_text(&n).to_string());

                // Get exception type(s) - can be multi-catch: catch (IOException | SQLException e)
                let mut types = Vec::new();
                if let Some(type_node) = param.child_by_field_name("type") {
                    let type_text = ctx.node_text(&type_node).to_string();
                    // Split by | for multi-catch
                    for exc_type in type_text.split('|') {
                        types.push(exc_type.trim().to_string());
                    }
                }

                (types, var_name)
            } else {
                (vec![], None)
            };

        // Create Catch node
        let mut catch_node = Node::new(
            node_id.clone(),
            NodeKind::Catch,
            format!("catch ({})", exception_types.join(" | ")),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        // Store exception metadata
        let mut metadata = serde_json::Map::new();
        if !exception_types.is_empty() {
            metadata.insert(
                "exception_types".to_string(),
                serde_json::Value::Array(
                    exception_types
                        .iter()
                        .map(|s| serde_json::Value::String(s.clone()))
                        .collect(),
                ),
            );
        }
        if let Some(var) = exception_var {
            metadata.insert("exception_var".to_string(), serde_json::Value::String(var));
        }
        catch_node.metadata = Some(serde_json::to_string(&metadata).unwrap_or_default());

        // Link to try block
        result.add_edge(Edge::new(
            try_id.to_string(),
            node_id.clone(),
            EdgeKind::Catches,
        ));

        result.add_node(catch_node);

        // Extract catch body
        if let Some(body) = node.child_by_field_name("body") {
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            self.extract_body(ctx, &body, id_gen, result);
            ctx.parent_id = old_parent;
        }
    }

    /// Extract finally clause
    fn extract_finally(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        try_id: &str,
    ) {
        let node_id = id_gen.next_node();

        // Create Finally node
        let finally_node = Node::new(
            node_id.clone(),
            NodeKind::Finally,
            "finally".to_string(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        // Link to try block
        result.add_edge(Edge::new(
            try_id.to_string(),
            node_id.clone(),
            EdgeKind::Finally,
        ));

        result.add_node(finally_node);

        // Extract finally body
        if let Some(body) = node.child_by_field_name("body") {
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            self.extract_body(ctx, &body, id_gen, result);
            ctx.parent_id = old_parent;
        }
    }

    /// Extract throw statement
    fn extract_throw(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Get exception being thrown
        let exception_type = node
            .child(0)
            .filter(|child| child.kind() != "throw")
            .and_then(|child| {
                if child.kind() == "object_creation_expression" {
                    // throw new RuntimeException("msg")
                    child
                        .child_by_field_name("type")
                        .map(|t| ctx.node_text(&t).to_string())
                } else {
                    // throw exc
                    Some(ctx.node_text(&child).to_string())
                }
            })
            .unwrap_or_else(|| "Exception".to_string());

        // Create Throw node
        let mut throw_node = Node::new(
            node_id.clone(),
            NodeKind::Throw,
            format!("throw {}", exception_type),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string());

        // Store exception type in metadata
        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "exception_type".to_string(),
            serde_json::Value::String(exception_type),
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

    /// Extract lambda expression
    /// Java lambda: (x, y) -> x + y
    fn extract_lambda(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Generate synthetic name using line number
        let line = node.start_position().row + 1;
        let name = format!("lambda_{}", line);

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        // Build lambda node
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

        // Add Captures edge (lambda is a closure)
        if let Some(ref parent_id) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent_id.clone(),
                node_id.clone(),
                EdgeKind::Captures,
            ));
        }

        result.add_node(ir_node);

        // Process lambda
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_lambda_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Extract body
        if let Some(body) = node.child_by_field_name("body") {
            self.extract_node(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract lambda parameters
    fn extract_lambda_parameters(
        &self,
        ctx: &ExtractionContext,
        params_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        lambda_id: &str,
    ) {
        // Lambda can have: (x), (int x), (x, y), etc.
        let mut cursor = params_node.walk();
        for child in params_node.children(&mut cursor) {
            if child.kind() == "identifier" || child.kind() == "formal_parameter" {
                let name = if child.kind() == "identifier" {
                    ctx.node_text(&child).to_string()
                } else {
                    // formal_parameter has a name field
                    child
                        .child_by_field_name("name")
                        .map(|n| ctx.node_text(&n).to_string())
                        .unwrap_or_default()
                };

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
                    child.to_span(),
                )
                .with_language(ctx.language.name().to_string())
                .with_name(name);

                ir_node.parent_id = Some(lambda_id.to_string());
                result.add_node(ir_node);
            }
        }
    }

    /// Extract method reference
    /// Java method reference: String::valueOf, obj::toString, Class::new
    fn extract_method_reference(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let method_ref_text = ctx.node_text(node).to_string();

        // Generate synthetic name using line number
        let line = node.start_position().row + 1;
        let name = format!("method_ref_{}", line);

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        // Build method reference node (also treated as lambda/closure)
        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Lambda,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        // Store method reference text in metadata
        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "method_reference".to_string(),
            serde_json::Value::String(method_ref_text.clone()),
        );
        ir_node.metadata = Some(serde_json::to_string(&metadata).unwrap_or_default());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Add Captures edge (method reference is also a closure)
        if let Some(ref parent_id) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent_id.clone(),
                node_id.clone(),
                EdgeKind::Captures,
            ));
        }

        result.add_node(ir_node);
    }
}

impl Default for JavaPlugin {
    fn default() -> Self {
        Self::new()
    }
}

impl LanguagePlugin for JavaPlugin {
    fn tree_sitter_language(&self) -> TSLanguage {
        tree_sitter_java::language()
    }

    fn language_id(&self) -> LanguageId {
        LanguageId::Java
    }

    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind> {
        match ts_kind {
            "class_declaration" => Some(NodeKind::Class),
            "interface_declaration" => Some(NodeKind::Interface),
            "enum_declaration" => Some(NodeKind::Enum),
            "record_declaration" => Some(NodeKind::Record),
            "annotation_type_declaration" => Some(NodeKind::AnnotationDecl),
            "method_declaration" => Some(NodeKind::Method),
            "constructor_declaration" => Some(NodeKind::Function),
            "field_declaration" => Some(NodeKind::Field),
            "import_declaration" => Some(NodeKind::Import),
            "enum_constant" => Some(NodeKind::EnumMember),
            "formal_parameter" => Some(NodeKind::Parameter),
            "type_parameter" => Some(NodeKind::TypeParameter),
            _ => None,
        }
    }

    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            "class_declaration" => SyntaxKind::ClassDef,
            "interface_declaration" | "enum_declaration" => SyntaxKind::ClassDef,
            "method_declaration" | "constructor_declaration" => SyntaxKind::FunctionDef,
            "field_declaration" => SyntaxKind::AssignmentStmt,
            "import_declaration" => SyntaxKind::ImportDecl,
            "formal_parameter" => SyntaxKind::ParameterDecl,
            "method_invocation" => SyntaxKind::CallExpr,
            "identifier" => SyntaxKind::NameExpr,
            "field_access" => SyntaxKind::AttributeExpr,
            "return_statement" => SyntaxKind::ReturnStmt,
            "if_statement" => SyntaxKind::IfStmt,
            "for_statement" | "enhanced_for_statement" => SyntaxKind::ForStmt,
            "while_statement" => SyntaxKind::WhileStmt,
            "try_statement" | "try_with_resources_statement" => SyntaxKind::TryStmt,
            "throw_statement" => SyntaxKind::RaiseStmt,
            "block" => SyntaxKind::Block,
            "line_comment" | "block_comment" => SyntaxKind::Comment,
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

        // Extract package as module path
        let root = tree.root_node();
        let mut cursor = root.walk();
        for child in root.children(&mut cursor) {
            if child.kind() == "package_declaration" {
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
        // Java uses modifiers, not naming conventions
        // Default to true for simplicity
        !name.is_empty()
    }

    fn extract_docstring(&self, node: &TSNode, source: &str) -> Option<String> {
        self.extract_javadoc(node, source)
    }

    fn is_statement_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            // Variable declarations
            "local_variable_declaration" | "field_declaration" |
            // Assignment
            "assignment_expression" |
            // Expression statements
            "expression_statement" |
            // Control flow
            "if_statement" | "for_statement" | "enhanced_for_statement" |
            "while_statement" | "do_statement" | "switch_expression" |
            "try_statement" | "try_with_resources_statement" |
            // Other statements
            "return_statement" | "break_statement" | "continue_statement" |
            "throw_statement" | "assert_statement" | "synchronized_statement" |
            // Import statements
            "import_declaration" | "package_declaration" |
            // Class and method declarations
            "class_declaration" | "interface_declaration" | "enum_declaration" |
            "method_declaration" | "constructor_declaration"
        )
    }

    fn is_control_flow_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            "if_statement"
                | "for_statement"
                | "enhanced_for_statement"
                | "while_statement"
                | "do_statement"
                | "switch_expression"
                | "try_statement"
                | "try_with_resources_statement"
                | "catch_clause"
                | "finally_clause"
        )
    }

    fn get_control_flow_type(
        &self,
        node: &TSNode,
    ) -> Option<crate::features::parsing::ports::ControlFlowType> {
        use crate::features::parsing::ports::ControlFlowType;
        match node.kind() {
            "if_statement" => Some(ControlFlowType::If),
            "for_statement" | "enhanced_for_statement" | "while_statement" | "do_statement" => {
                Some(ControlFlowType::Loop)
            }
            "switch_expression" | "switch_statement" => Some(ControlFlowType::Match),
            "try_statement" | "try_with_resources_statement" => Some(ControlFlowType::Try),
            "yield_statement" => Some(ControlFlowType::Yield),
            "return_statement" => Some(ControlFlowType::Return),
            "break_statement" => Some(ControlFlowType::Break),
            "continue_statement" => Some(ControlFlowType::Continue),
            "throw_statement" => Some(ControlFlowType::Raise),
            _ => None,
        }
    }

    fn get_match_arms<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        let mut arms = Vec::new();
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if matches!(
                child.kind(),
                "switch_block_statement_group" | "switch_rule" | "default_case"
            ) {
                arms.push(child);
            }
        }
        arms
    }

    fn is_chained_condition(&self, node: &TSNode) -> bool {
        // Java doesn't have explicit elif, but can have if_statement inside else block
        node.kind() == "if_statement"
            && node
                .parent()
                .map(|p| {
                    matches!(p.kind(), "block")
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

    fn parse_java(source: &str) -> Tree {
        let mut parser = Parser::new();
        parser.set_language(&tree_sitter_java::language()).unwrap();
        parser.parse(source, None).unwrap()
    }

    #[test]
    #[ignore]
    fn test_extract_class() {
        let source = r#"
package com.example;

public class MyClass extends BaseClass implements Serializable {
    private int field;

    public void method(String arg) {
        System.out.println(arg);
    }
}
"#;
        let tree = parse_java(source);
        let plugin = JavaPlugin::new();
        let mut ctx = ExtractionContext::new(source, "MyClass.java", "test-repo", LanguageId::Java);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let class = result.nodes.iter().find(|n| n.kind == NodeKind::Class);
        assert!(class.is_some());
        assert_eq!(class.unwrap().name, Some("MyClass".to_string()));

        // Check for implements edge
        let impl_edge = result.edges.iter().find(|e| e.kind == EdgeKind::Implements);
        assert!(impl_edge.is_some());
    }

    #[test]
    fn test_extract_interface() {
        let source = r#"
public interface Service<T> {
    T process(T input);
}
"#;
        let tree = parse_java(source);
        let plugin = JavaPlugin::new();
        let mut ctx = ExtractionContext::new(source, "Service.java", "test-repo", LanguageId::Java);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let iface = result.nodes.iter().find(|n| n.kind == NodeKind::Interface);
        assert!(iface.is_some());
    }

    #[test]
    fn test_extract_enum() {
        let source = r#"
public enum Status {
    PENDING,
    ACTIVE,
    COMPLETED
}
"#;
        let tree = parse_java(source);
        let plugin = JavaPlugin::new();
        let mut ctx = ExtractionContext::new(source, "Status.java", "test-repo", LanguageId::Java);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let enum_node = result.nodes.iter().find(|n| n.kind == NodeKind::Enum);
        assert!(enum_node.is_some());

        let members: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::EnumMember)
            .collect();
        assert_eq!(members.len(), 3);
    }
}
