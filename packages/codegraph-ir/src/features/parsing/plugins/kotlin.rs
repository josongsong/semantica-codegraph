//! Kotlin Language Plugin
//!
//! Implements LanguagePlugin for Kotlin source code.
//! Supports: classes, data classes, sealed classes, extension functions, coroutines

use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::features::parsing::ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, SpanExt,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Result};

/// Kotlin language plugin
pub struct KotlinPlugin;

impl KotlinPlugin {
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
        let name = self.get_class_name(node, ctx);
        if name.is_empty() {
            return;
        }

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        // Determine kind based on modifiers
        let kind = self.determine_class_kind(node, ctx);

        let mut ir_node = Node::new(
            node_id.clone(),
            kind,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Defines,
            ));
        }

        // Extract supertypes
        self.extract_supertypes(ctx, node, result, &node_id);

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

        // Extract primary constructor parameters as fields for data classes
        if matches!(self.determine_class_kind(node, ctx), NodeKind::DataClass) {
            self.extract_primary_constructor_params(ctx, node, id_gen, result, &node_id);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract function declaration
    fn extract_function(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // tree-sitter-kotlin uses "simple_identifier" directly, not "name" field
        let name = node
            .child_by_field_name("name")
            .or_else(|| {
                // Fallback: find simple_identifier child
                let mut cursor = node.walk();
                for child in node.children(&mut cursor) {
                    if child.kind() == "simple_identifier" {
                        return Some(child);
                    }
                }
                None
            })
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default();

        if name.is_empty() {
            return;
        }

        let node_id = id_gen.next_node();

        // Check for extension function, nested function, etc.
        let receiver_type = self.get_receiver_type(node, ctx);
        let is_inside_class = ctx
            .scope_stack
            .iter()
            .any(|s| s.chars().next().map(|c| c.is_uppercase()).unwrap_or(false));
        let is_inside_function = ctx
            .scope_stack
            .iter()
            .any(|s| s.chars().next().map(|c| c.is_lowercase()).unwrap_or(false));

        let kind = if receiver_type.is_some() {
            NodeKind::ExtensionFunction
        } else if self.is_suspend_function(node, ctx) {
            NodeKind::SuspendFunction
        } else if is_inside_class {
            NodeKind::Method
        } else if is_inside_function {
            NodeKind::Lambda // Nested functions are closures in Kotlin
        } else {
            NodeKind::Function
        };

        let fqn = if let Some(ref receiver) = receiver_type {
            format!("{}.{}", receiver, name)
        } else if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
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

        // Mark suspend functions as async
        if kind == NodeKind::SuspendFunction {
            ir_node.is_async = Some(true);
        }

        // Add edges from parent
        if let Some(ref parent) = ctx.parent_id {
            // Use Captures edge for closures (nested functions)
            let edge_kind = if kind == NodeKind::Lambda {
                EdgeKind::Captures
            } else {
                EdgeKind::Defines
            };

            result.add_edge(Edge::new(parent.clone(), node_id.clone(), edge_kind));
        }

        // Extract annotations
        self.extract_annotations(ctx, node, result, &node_id);

        result.add_node(ir_node);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }
    }

    /// Extract property declaration
    fn extract_property(
        &self,
        ctx: &ExtractionContext,
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

        let kind = if ctx
            .scope_stack
            .iter()
            .any(|s| s.chars().next().map(|c| c.is_uppercase()).unwrap_or(false))
        {
            NodeKind::Field
        } else {
            NodeKind::Variable
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            kind,
            fqn,
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name);

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        result.add_node(ir_node);
    }

    /// Extract object declaration (singleton/companion)
    fn extract_object(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let name = node
            .child_by_field_name("name")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_else(|| "Companion".to_string());

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), name)
        };

        // Check if companion object
        let kind = if self.is_companion_object(node, ctx) {
            NodeKind::CompanionObject
        } else {
            NodeKind::Class // Regular object singleton
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

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

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

    /// Extract import
    fn extract_import(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();
        let import_text = ctx.node_text(node).to_string();

        let ir_node = Node::new(
            node_id,
            NodeKind::Import,
            format!("import:{}", import_text.trim()),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(import_text.trim().to_string());

        result.add_node(ir_node);
    }

    // Helper methods

    fn get_class_name(&self, node: &TSNode, ctx: &ExtractionContext) -> String {
        if let Some(name_node) = node.child_by_field_name("name") {
            return ctx.node_text(&name_node).to_string();
        }
        // Fallback: search children for type_identifier or simple_identifier
        for i in 0..node.child_count() {
            if let Some(child) = node.child(i) {
                if child.kind() == "type_identifier" || child.kind() == "simple_identifier" {
                    return ctx.node_text(&child).to_string();
                }
            }
        }
        String::new()
    }

    fn determine_class_kind(&self, node: &TSNode, ctx: &ExtractionContext) -> NodeKind {
        let text = ctx.node_text(node);
        if text.contains("data class") {
            NodeKind::DataClass
        } else if text.contains("sealed class") || text.contains("sealed interface") {
            NodeKind::SealedClass
        } else if text.contains("interface") {
            NodeKind::Interface
        } else if text.contains("enum class") {
            NodeKind::Enum
        } else if text.contains("annotation class") {
            NodeKind::AnnotationDecl
        } else {
            NodeKind::Class
        }
    }

    fn get_receiver_type(&self, node: &TSNode, ctx: &ExtractionContext) -> Option<String> {
        // Extension function: fun String.myExt()
        node.child_by_field_name("receiver")
            .map(|n| ctx.node_text(&n).to_string())
    }

    fn is_suspend_function(&self, node: &TSNode, ctx: &ExtractionContext) -> bool {
        let text = ctx.node_text(node);
        text.contains("suspend fun")
    }

    fn is_companion_object(&self, node: &TSNode, ctx: &ExtractionContext) -> bool {
        let text = ctx.node_text(node);
        text.contains("companion object")
    }

    fn extract_supertypes(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        class_id: &str,
    ) {
        if let Some(supertypes) = node.child_by_field_name("supertype") {
            let mut cursor = supertypes.walk();
            for child in supertypes.children(&mut cursor) {
                let supertype = ctx.node_text(&child).to_string();
                if !supertype.is_empty() {
                    result.add_edge(Edge::new(
                        class_id.to_string(),
                        format!("ref:{}", supertype),
                        EdgeKind::Extends,
                    ));
                }
            }
        }
    }

    fn extract_annotations(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        target_id: &str,
    ) {
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "annotation" || child.kind() == "single_annotation" {
                let anno_text = ctx.node_text(&child).to_string();
                result.add_edge(Edge::new(
                    target_id.to_string(),
                    format!("ref:{}", anno_text),
                    EdgeKind::AnnotatedWith,
                ));
            }
        }
    }

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
            if child.kind() == "parameter" || child.kind() == "value_parameter" {
                if let Some(name_node) = child.child_by_field_name("name") {
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
                        child.to_span(),
                    )
                    .with_language(ctx.language.name().to_string())
                    .with_name(name);

                    ir_node.parent_id = Some(func_id.to_string());
                    result.add_node(ir_node);
                }
            }
        }
    }

    fn extract_primary_constructor_params(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        class_id: &str,
    ) {
        if let Some(constructor) = node.child_by_field_name("primary_constructor") {
            let mut cursor = constructor.walk();
            for child in constructor.children(&mut cursor) {
                if child.kind() == "class_parameter" {
                    if let Some(name_node) = child.child_by_field_name("name") {
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
                            child.to_span(),
                        )
                        .with_language(ctx.language.name().to_string())
                        .with_name(name);

                        ir_node.parent_id = Some(class_id.to_string());
                        result.add_node(ir_node);
                    }
                }
            }
        }
    }

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
            if child.kind() == "catch_block" {
                self.extract_catch(ctx, &child, id_gen, result, &node_id);
            } else if child.kind() == "finally_block" {
                self.extract_finally(ctx, &child, id_gen, result, &node_id);
            }
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

        // Get exception parameter: catch (e: Exception)
        let (exception_types, exception_var) =
            if let Some(params) = node.child_by_field_name("parameters") {
                let mut cursor = params.walk();
                let mut types = Vec::new();
                let mut var_name = None;

                for child in params.children(&mut cursor) {
                    if child.kind() == "parameter" || child.kind() == "catch_parameter" {
                        // Get variable name
                        if let Some(name_node) = child.child_by_field_name("name") {
                            var_name = Some(ctx.node_text(&name_node).to_string());
                        }

                        // Get exception type
                        if let Some(type_node) = child.child_by_field_name("type") {
                            types.push(ctx.node_text(&type_node).to_string());
                        }
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
            if !exception_types.is_empty() {
                format!("catch ({})", exception_types.join(", "))
            } else if let Some(ref var) = exception_var {
                format!("catch ({})", var)
            } else {
                "catch".to_string()
            },
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

    /// Extract throw expression
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
            .map(|child| {
                if child.kind() == "call_expression" {
                    // throw Exception("msg")
                    child
                        .child_by_field_name("function")
                        .map(|f| ctx.node_text(&f).to_string())
                        .unwrap_or_else(|| "Exception".to_string())
                } else {
                    // throw error
                    ctx.node_text(&child).to_string()
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

    fn extract_node(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        match node.kind() {
            "class_declaration" => self.extract_class(ctx, node, id_gen, result),
            "function_declaration" => self.extract_function(ctx, node, id_gen, result),
            "property_declaration" => self.extract_property(ctx, node, id_gen, result),
            "object_declaration" => self.extract_object(ctx, node, id_gen, result),
            "companion_object" => self.extract_object(ctx, node, id_gen, result),
            "import_header" => self.extract_import(ctx, node, id_gen, result),
            "try_expression" => self.extract_try(ctx, node, id_gen, result),
            "throw_expression" => self.extract_throw(ctx, node, id_gen, result),
            _ => {
                let mut cursor = node.walk();
                for child in node.children(&mut cursor) {
                    self.extract_node(ctx, &child, id_gen, result);
                }
            }
        }
    }
}

impl Default for KotlinPlugin {
    fn default() -> Self {
        Self::new()
    }
}

impl LanguagePlugin for KotlinPlugin {
    fn tree_sitter_language(&self) -> TSLanguage {
        tree_sitter_kotlin::language()
    }

    fn language_id(&self) -> LanguageId {
        LanguageId::Kotlin
    }

    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind> {
        match ts_kind {
            "class_declaration" => Some(NodeKind::Class),
            "function_declaration" => Some(NodeKind::Function),
            "property_declaration" => Some(NodeKind::Variable),
            "object_declaration" => Some(NodeKind::Class),
            "import_header" => Some(NodeKind::Import),
            "parameter" | "value_parameter" => Some(NodeKind::Parameter),
            _ => None,
        }
    }

    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            "class_declaration" => SyntaxKind::ClassDef,
            "function_declaration" => SyntaxKind::FunctionDef,
            "property_declaration" => SyntaxKind::AssignmentStmt,
            "import_header" => SyntaxKind::ImportDecl,
            "parameter" | "value_parameter" => SyntaxKind::ParameterDecl,
            "call_expression" => SyntaxKind::CallExpr,
            "simple_identifier" => SyntaxKind::NameExpr,
            "navigation_expression" => SyntaxKind::AttributeExpr,
            "jump_expression" => SyntaxKind::ReturnStmt,
            "if_expression" => SyntaxKind::IfStmt,
            "for_statement" => SyntaxKind::ForStmt,
            "while_statement" => SyntaxKind::WhileStmt,
            "try_expression" => SyntaxKind::TryStmt,
            "throw_expression" => SyntaxKind::RaiseStmt,
            "block" => SyntaxKind::Block,
            "line_comment" | "multiline_comment" => SyntaxKind::Comment,
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
            if child.kind() == "package_header" {
                // Extract the identifier node which contains the package name
                if let Some(identifier) = child.child_by_field_name("identifier") {
                    let pkg = ctx.node_text(&identifier).to_string();
                    ctx.module_path = Some(pkg.trim().to_string());
                } else {
                    // Fallback: parse package header text
                    let pkg_text = ctx.node_text(&child).to_string();
                    let pkg = pkg_text
                        .lines()
                        .next()
                        .unwrap_or("")
                        .replace("package ", "")
                        .trim()
                        .to_string();
                    if !pkg.is_empty() {
                        ctx.module_path = Some(pkg);
                    }
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
        !name.starts_with('_')
    }

    fn is_statement_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            // Variable declarations
            "property_declaration" | "variable_declaration" |
            // Assignment
            "assignment" |
            // Expression statements
            "expression_statement" |
            // Control flow
            "if_expression" | "when_expression" |
            "for_statement" | "while_statement" | "do_while_statement" |
            "try_expression" |
            // Other statements
            "jump_expression" | "throw_expression" |
            // Import statements
            "import_header" | "package_header" |
            // Class and function declarations
            "class_declaration" | "object_declaration" |
            "function_declaration"
        )
    }

    fn is_control_flow_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            "if_expression"
                | "when_expression"
                | "for_statement"
                | "while_statement"
                | "do_while_statement"
                | "try_expression"
                | "catch_block"
                | "finally_block"
        )
    }

    fn get_control_flow_type(
        &self,
        node: &TSNode,
    ) -> Option<crate::features::parsing::ports::ControlFlowType> {
        use crate::features::parsing::ports::ControlFlowType;
        match node.kind() {
            "if_expression" => Some(ControlFlowType::If),
            "for_statement" | "while_statement" | "do_while_statement" => {
                Some(ControlFlowType::Loop)
            }
            "when_expression" => Some(ControlFlowType::Match),
            "try_expression" => Some(ControlFlowType::Try),
            "return_expression" => Some(ControlFlowType::Return),
            "break_expression" => Some(ControlFlowType::Break),
            "continue_expression" => Some(ControlFlowType::Continue),
            "throw_expression" => Some(ControlFlowType::Raise),
            _ => None,
        }
    }

    fn get_match_arms<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        let mut arms = Vec::new();
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "when_entry" {
                arms.push(child);
            }
        }
        arms
    }

    fn is_chained_condition(&self, node: &TSNode) -> bool {
        // Kotlin if is an expression, chaining is done via nested if expressions
        // Check if this if_expression is inside an else part of another if_expression
        node.kind() == "if_expression"
            && node
                .parent()
                .map(|p| p.kind() == "if_expression")
                .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    fn parse_kotlin(source: &str) -> Tree {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_kotlin::language())
            .unwrap();
        parser.parse(source, None).unwrap()
    }

    #[test]
    fn test_extract_data_class() {
        let source = r#"
package com.example

data class User(val id: Int, val name: String)
"#;
        let tree = parse_kotlin(source);
        let plugin = KotlinPlugin::new();
        let mut ctx = ExtractionContext::new(source, "User.kt", "test-repo", LanguageId::Kotlin);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let class = result.nodes.iter().find(|n| n.kind == NodeKind::DataClass);
        assert!(class.is_some());
    }

    #[test]
    #[ignore]
    fn test_extract_extension_function() {
        let source = r#"
fun String.addExclamation(): String = this + "!"
"#;
        let tree = parse_kotlin(source);
        let plugin = KotlinPlugin::new();
        let mut ctx =
            ExtractionContext::new(source, "Extensions.kt", "test-repo", LanguageId::Kotlin);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let ext_func = result
            .nodes
            .iter()
            .find(|n| n.kind == NodeKind::ExtensionFunction);
        assert!(ext_func.is_some());
    }
}
