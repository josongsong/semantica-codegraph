//! Rust Language Plugin
//!
//! Implements LanguagePlugin for Rust source code.
//! Supports: structs, enums, traits, impl blocks, lifetimes, macros

use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::features::parsing::ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, SpanExt,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Result};

/// Rust language plugin
pub struct RustPlugin;

impl RustPlugin {
    pub fn new() -> Self {
        Self
    }

    /// Extract struct definition
    fn extract_struct(
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
            format!("{}::{}", ctx.fqn_prefix(), name)
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Struct,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Extract type parameters (including lifetimes)
        self.extract_type_parameters(ctx, node, id_gen, result, &node_id);

        // Extract attributes (#[derive(...)])
        self.extract_attributes(ctx, node, result, &node_id);

        result.add_node(ir_node);

        // Extract fields
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        if let Some(body) = node.child_by_field_name("body") {
            self.extract_struct_fields(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract enum definition
    fn extract_enum(
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
            format!("{}::{}", ctx.fqn_prefix(), name)
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Enum,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Extract attributes
        self.extract_attributes(ctx, node, result, &node_id);

        result.add_node(ir_node);

        // Extract variants
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        if let Some(body) = node.child_by_field_name("body") {
            self.extract_enum_variants(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract trait definition
    fn extract_trait(
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
            format!("{}::{}", ctx.fqn_prefix(), name)
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Trait,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Extract supertraits (bounds)
        if let Some(bounds) = node.child_by_field_name("bounds") {
            let bounds_text = ctx.node_text(&bounds).to_string();
            for bound in bounds_text.split('+') {
                let bound = bound.trim();
                if !bound.is_empty() {
                    result.add_edge(Edge::new(
                        node_id.clone(),
                        format!("ref:{}", bound),
                        EdgeKind::Extends,
                    ));
                }
            }
        }

        result.add_node(ir_node);

        // Extract trait body
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        if let Some(body) = node.child_by_field_name("body") {
            self.extract_trait_body(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract impl block
    fn extract_impl(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Get type being implemented
        let type_name = node
            .child_by_field_name("type")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default();

        // Get trait being implemented (if any)
        let trait_name = node
            .child_by_field_name("trait")
            .map(|n| ctx.node_text(&n).to_string());

        let node_id = id_gen.next_node();
        let fqn = if let Some(ref trait_n) = trait_name {
            format!("impl {} for {}", trait_n, type_name)
        } else {
            format!("impl {}", type_name)
        };

        let kind = if trait_name.is_some() {
            NodeKind::TraitImpl
        } else {
            NodeKind::TraitImpl // inherent impl
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            kind,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(fqn.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Create implements edge
        if let Some(trait_n) = trait_name {
            result.add_edge(Edge::new(
                format!("ref:{}", type_name),
                format!("ref:{}", trait_n),
                EdgeKind::ImplementsTrait,
            ));
        }

        result.add_node(ir_node);

        // Extract impl body
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&type_name);

        if let Some(body) = node.child_by_field_name("body") {
            self.extract_impl_body(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract function/method
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
            format!("{}::{}", ctx.fqn_prefix(), name)
        };

        // Determine if it's a method (has self parameter)
        let is_method = self.has_self_parameter(node, ctx);
        let kind = if is_method {
            NodeKind::Method
        } else {
            NodeKind::Function
        };

        // Check if async function (async fn)
        // In tree-sitter-rust, async is part of function_modifiers
        let is_async = {
            // Check function text for "async fn" pattern
            let func_text = ctx.node_text(node);
            func_text.starts_with("async fn") || func_text.starts_with("pub async fn")
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

        if is_async {
            ir_node.is_async = Some(true);
        }

        // Add edges from parent
        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Defines,
            ));
        }

        // Extract doc comment
        if let Some(doc) = self.extract_docstring(node, ctx.source) {
            ir_node = ir_node.with_docstring(doc);
        }

        // Extract attributes
        self.extract_attributes(ctx, node, result, &node_id);

        result.add_node(ir_node);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }
    }

    /// Extract macro definition
    fn extract_macro(
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
            format!("{}!", name)
        } else {
            format!("{}::{}!", ctx.fqn_prefix(), name)
        };

        let mut ir_node = Node::new(
            node_id,
            NodeKind::Macro,
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

    /// Extract use/import statement
    fn extract_use(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();
        let use_text = ctx.node_text(node).to_string();

        let ir_node = Node::new(
            node_id,
            NodeKind::Import,
            format!("{}", use_text.trim()),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(use_text.trim().to_string());

        result.add_node(ir_node);
    }

    /// Extract module declaration
    fn extract_mod(
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
            format!("{}::{}", ctx.fqn_prefix(), name)
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Module,
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

        // Extract module body if inline
        if let Some(body) = node.child_by_field_name("body") {
            let old_parent = ctx.parent_id.take();
            ctx.parent_id = Some(node_id.clone());
            ctx.push_scope(&name);

            self.extract_body(ctx, &body, id_gen, result);

            ctx.pop_scope();
            ctx.parent_id = old_parent;
        }
    }

    // Helper methods

    fn extract_struct_fields(
        &self,
        ctx: &ExtractionContext,
        body_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = body_node.walk();
        for child in body_node.children(&mut cursor) {
            if child.kind() == "field_declaration" {
                if let Some(name_node) = child.child_by_field_name("name") {
                    let name = ctx.node_text(&name_node).to_string();
                    if name.is_empty() {
                        continue;
                    }

                    let node_id = id_gen.next_node();
                    let fqn = format!("{}::{}", ctx.fqn_prefix(), name);

                    let mut ir_node = Node::new(
                        node_id,
                        NodeKind::Field,
                        fqn,
                        ctx.file_path.to_string(),
                        child.to_span(),
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

    fn extract_enum_variants(
        &self,
        ctx: &ExtractionContext,
        body_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = body_node.walk();
        for child in body_node.children(&mut cursor) {
            if child.kind() == "enum_variant" {
                if let Some(name_node) = child.child_by_field_name("name") {
                    let name = ctx.node_text(&name_node).to_string();
                    if name.is_empty() {
                        continue;
                    }

                    let node_id = id_gen.next_node();
                    let fqn = format!("{}::{}", ctx.fqn_prefix(), name);

                    let mut ir_node = Node::new(
                        node_id,
                        NodeKind::EnumMember,
                        fqn,
                        ctx.file_path.to_string(),
                        child.to_span(),
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

    fn extract_trait_body(
        &self,
        ctx: &mut ExtractionContext,
        body_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = body_node.walk();
        for child in body_node.children(&mut cursor) {
            match child.kind() {
                "function_item" | "function_signature_item" => {
                    self.extract_function(ctx, &child, id_gen, result)
                }
                "associated_type" => self.extract_associated_type(ctx, &child, id_gen, result),
                _ => {}
            }
        }
    }

    fn extract_impl_body(
        &self,
        ctx: &mut ExtractionContext,
        body_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let mut cursor = body_node.walk();
        for child in body_node.children(&mut cursor) {
            match child.kind() {
                "function_item" => self.extract_function(ctx, &child, id_gen, result),
                "type_item" => self.extract_associated_type(ctx, &child, id_gen, result),
                _ => {}
            }
        }
    }

    fn extract_associated_type(
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
        let fqn = format!("{}::{}", ctx.fqn_prefix(), name);

        let mut ir_node = Node::new(
            node_id,
            NodeKind::AssociatedType,
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
                match child.kind() {
                    "type_identifier" => {
                        let name = ctx.node_text(&child).to_string();
                        let node_id = id_gen.next_node();

                        let mut ir_node = Node::new(
                            node_id,
                            NodeKind::TypeParameter,
                            format!("{}::{}", ctx.fqn_prefix(), name),
                            ctx.file_path.to_string(),
                            child.to_span(),
                        )
                        .with_language(ctx.language.name().to_string())
                        .with_name(name);

                        ir_node.parent_id = Some(parent_id.to_string());
                        result.add_node(ir_node);
                    }
                    "lifetime" => {
                        let name = ctx.node_text(&child).to_string();
                        let node_id = id_gen.next_node();

                        let mut ir_node = Node::new(
                            node_id,
                            NodeKind::Lifetime,
                            format!("{}::{}", ctx.fqn_prefix(), name),
                            ctx.file_path.to_string(),
                            child.to_span(),
                        )
                        .with_language(ctx.language.name().to_string())
                        .with_name(name);

                        ir_node.parent_id = Some(parent_id.to_string());
                        result.add_node(ir_node);
                    }
                    _ => {}
                }
            }
        }
    }

    fn extract_attributes(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        target_id: &str,
    ) {
        // Look for attribute_item siblings
        if let Some(parent) = node.parent() {
            let mut cursor = parent.walk();
            let mut found_self = false;
            for sibling in parent.children(&mut cursor) {
                if sibling.id() == node.id() {
                    found_self = true;
                    continue;
                }
                if found_self {
                    break;
                }
                if sibling.kind() == "attribute_item" {
                    let attr_text = ctx.node_text(&sibling).to_string();
                    result.add_edge(Edge::new(
                        target_id.to_string(),
                        format!("ref:{}", attr_text),
                        EdgeKind::AnnotatedWith,
                    ));
                }
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
            if child.kind() == "parameter" {
                if let Some(pattern) = child.child_by_field_name("pattern") {
                    let name = ctx.node_text(&pattern).to_string();
                    if name.is_empty() || name == "self" || name == "&self" || name == "&mut self" {
                        continue;
                    }

                    let node_id = id_gen.next_node();
                    let fqn = format!("{}::{}", ctx.fqn_prefix(), name);

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

    fn has_self_parameter(&self, node: &TSNode, ctx: &ExtractionContext) -> bool {
        if let Some(params) = node.child_by_field_name("parameters") {
            let text = ctx.node_text(&params);
            return text.contains("self");
        }
        false
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

    /// Extract panic! macro invocation
    fn extract_panic(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Extract panic message if present
        let panic_text = ctx.node_text(node).to_string();

        // Create Throw node (using Throw for panic! since it's similar to throwing)
        let mut throw_node = Node::new(
            node_id.clone(),
            NodeKind::Throw,
            format!("panic!"),
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

    /// Extract Result<T, E> return types and ? operator usage
    /// This helps track error propagation in Rust code
    fn extract_result_handling(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        func_id: &str,
    ) {
        // Check function return type for Result<>
        if let Some(return_type) = node.child_by_field_name("return_type") {
            let type_text = ctx.node_text(&return_type).to_string();
            if type_text.contains("Result") {
                // Add metadata indicating this function can return errors
                let mut metadata = serde_json::Map::new();
                metadata.insert("returns_result".to_string(), serde_json::Value::Bool(true));
                metadata.insert(
                    "return_type".to_string(),
                    serde_json::Value::String(type_text),
                );

                // This would be stored on the function node, but we don't have mutable access here
                // In practice, this would be done during function extraction
            }
        }

        // Scan function body for ? operator (error propagation)
        if let Some(body) = node.child_by_field_name("body") {
            self.scan_error_propagation(ctx, &body, result, func_id);
        }
    }

    /// Scan for ? operator (error propagation)
    fn scan_error_propagation(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        func_id: &str,
    ) {
        if node.kind() == "try_expression" {
            // The ? operator in Rust is represented as try_expression
            // This propagates errors up the call stack
            result.add_edge(Edge::new(
                func_id.to_string(),
                "error_propagation".to_string(),
                EdgeKind::Throws,
            ));
        }

        // Recurse
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            self.scan_error_propagation(ctx, &child, result, func_id);
        }
    }

    /// Extract closure expression
    /// Rust closures: |x, y| x + y, || {}, |x| -> i32 { x }
    fn extract_closure(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Generate synthetic name using line number
        let line = node.start_position().row + 1;
        let name = format!("closure_{}", line);

        let node_id = id_gen.next_node();
        let fqn = if ctx.fqn_prefix().is_empty() {
            name.clone()
        } else {
            format!("{}::{}", ctx.fqn_prefix(), name)
        };

        // Rust closures can be Fn, FnMut, or FnOnce - store in metadata
        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "closure_kind".to_string(),
            serde_json::Value::String("unknown".to_string()), // Could be inferred with type analysis
        );

        // Build closure node
        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Lambda,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        ir_node.metadata = Some(serde_json::to_string(&metadata).unwrap_or_default());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Add Captures edge (closures always capture)
        if let Some(ref parent_id) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent_id.clone(),
                node_id.clone(),
                EdgeKind::Captures,
            ));
        }

        result.add_node(ir_node);

        // Process closure
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_closure_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Extract body
        if let Some(body) = node.child_by_field_name("body") {
            self.extract_node(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract closure parameters
    fn extract_closure_parameters(
        &self,
        ctx: &ExtractionContext,
        params_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        closure_id: &str,
    ) {
        // Rust closure parameters: |x|, |x: i32|, |x, y|, etc.
        let mut cursor = params_node.walk();
        for child in params_node.children(&mut cursor) {
            if child.kind() == "closure_parameters" {
                // Nested closure_parameters node
                let mut inner_cursor = child.walk();
                for param in child.children(&mut inner_cursor) {
                    if param.kind() == "parameter" || param.kind() == "identifier" {
                        let name = if param.kind() == "identifier" {
                            ctx.node_text(&param).to_string()
                        } else {
                            param
                                .child_by_field_name("pattern")
                                .map(|p| ctx.node_text(&p).to_string())
                                .unwrap_or_default()
                        };

                        if name.is_empty() {
                            continue;
                        }

                        let node_id = id_gen.next_node();
                        let fqn = format!("{}::{}", ctx.fqn_prefix(), name);

                        let mut ir_node = Node::new(
                            node_id,
                            NodeKind::Parameter,
                            fqn,
                            ctx.file_path.to_string(),
                            param.to_span(),
                        )
                        .with_language(ctx.language.name().to_string())
                        .with_name(name);

                        ir_node.parent_id = Some(closure_id.to_string());
                        result.add_node(ir_node);
                    }
                }
            }
        }
    }

    fn extract_node(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        match node.kind() {
            "struct_item" => self.extract_struct(ctx, node, id_gen, result),
            "enum_item" => self.extract_enum(ctx, node, id_gen, result),
            "trait_item" => self.extract_trait(ctx, node, id_gen, result),
            "impl_item" => self.extract_impl(ctx, node, id_gen, result),
            "function_item" => self.extract_function(ctx, node, id_gen, result),
            "macro_definition" => self.extract_macro(ctx, node, id_gen, result),
            "use_declaration" => self.extract_use(ctx, node, id_gen, result),
            "mod_item" => self.extract_mod(ctx, node, id_gen, result),
            "macro_invocation" => {
                // Check if it's panic!, unwrap(), expect(), etc.
                let macro_text = ctx.node_text(node).to_string();
                if macro_text.starts_with("panic!") {
                    self.extract_panic(ctx, node, id_gen, result);
                } else {
                    // Recurse for other macros
                    let mut cursor = node.walk();
                    for child in node.children(&mut cursor) {
                        self.extract_node(ctx, &child, id_gen, result);
                    }
                }
            }
            "closure_expression" => self.extract_closure(ctx, node, id_gen, result),
            _ => {
                let mut cursor = node.walk();
                for child in node.children(&mut cursor) {
                    self.extract_node(ctx, &child, id_gen, result);
                }
            }
        }
    }
}

impl Default for RustPlugin {
    fn default() -> Self {
        Self::new()
    }
}

impl LanguagePlugin for RustPlugin {
    fn tree_sitter_language(&self) -> TSLanguage {
        tree_sitter_rust::language()
    }

    fn language_id(&self) -> LanguageId {
        LanguageId::Rust
    }

    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind> {
        match ts_kind {
            "struct_item" => Some(NodeKind::Struct),
            "enum_item" => Some(NodeKind::Enum),
            "trait_item" => Some(NodeKind::Trait),
            "impl_item" => Some(NodeKind::TraitImpl),
            "function_item" => Some(NodeKind::Function),
            "macro_definition" => Some(NodeKind::Macro),
            "use_declaration" => Some(NodeKind::Import),
            "mod_item" => Some(NodeKind::Module),
            "field_declaration" => Some(NodeKind::Field),
            "enum_variant" => Some(NodeKind::EnumMember),
            "parameter" => Some(NodeKind::Parameter),
            "type_identifier" => Some(NodeKind::TypeParameter),
            "lifetime" => Some(NodeKind::Lifetime),
            _ => None,
        }
    }

    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            "struct_item" | "enum_item" | "trait_item" => SyntaxKind::ClassDef,
            "function_item" => SyntaxKind::FunctionDef,
            "let_declaration" => SyntaxKind::AssignmentStmt,
            "use_declaration" => SyntaxKind::ImportDecl,
            "parameter" => SyntaxKind::ParameterDecl,
            "call_expression" => SyntaxKind::CallExpr,
            "identifier" => SyntaxKind::NameExpr,
            "field_expression" => SyntaxKind::AttributeExpr,
            "return_expression" => SyntaxKind::ReturnStmt,
            "if_expression" => SyntaxKind::IfStmt,
            "for_expression" => SyntaxKind::ForStmt,
            "while_expression" => SyntaxKind::WhileStmt,
            "match_expression" => SyntaxKind::IfStmt, // Similar to switch
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

        // Extract all items
        let root = tree.root_node();
        let mut cursor = root.walk();
        for child in root.children(&mut cursor) {
            self.extract_node(ctx, &child, &mut id_gen, &mut result);
        }

        Ok(result)
    }

    fn comment_patterns(&self) -> &[&str] {
        &["//", "/*"]
    }

    fn is_public(&self, _name: &str) -> bool {
        // Rust uses pub keyword, not naming
        true
    }

    fn extract_docstring(&self, node: &TSNode, source: &str) -> Option<String> {
        // Look for /// doc comments
        let mut comments = Vec::new();
        let mut current = node.prev_sibling();

        while let Some(prev) = current {
            if prev.kind() == "line_comment" {
                let text = source.get(prev.byte_range())?;
                if text.starts_with("///") || text.starts_with("//!") {
                    comments.push(
                        text.trim_start_matches("///")
                            .trim_start_matches("//!")
                            .trim(),
                    );
                } else {
                    break;
                }
            } else {
                break;
            }
            current = prev.prev_sibling();
        }

        if comments.is_empty() {
            None
        } else {
            comments.reverse();
            Some(comments.join("\n"))
        }
    }

    fn is_statement_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            // Variable declarations
            "let_declaration" | "const_item" | "static_item" |
            // Assignment
            "assignment_expression" |
            // Expression statements
            "expression_statement" |
            // Control flow
            "if_expression" | "match_expression" |
            "for_expression" | "while_expression" | "loop_expression" |
            // Other statements
            "return_expression" | "break_expression" | "continue_expression" |
            // Import statements
            "use_declaration" | "mod_item" |
            // Type declarations
            "struct_item" | "enum_item" | "trait_item" | "impl_item" |
            "function_item" | "macro_definition"
        )
    }

    fn is_control_flow_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            "if_expression"
                | "match_expression"
                | "for_expression"
                | "while_expression"
                | "loop_expression"
                | "match_arm"
        )
    }

    fn get_control_flow_type(
        &self,
        node: &TSNode,
    ) -> Option<crate::features::parsing::ports::ControlFlowType> {
        use crate::features::parsing::ports::ControlFlowType;
        match node.kind() {
            "if_expression" => Some(ControlFlowType::If),
            "for_expression" | "while_expression" | "loop_expression" => {
                Some(ControlFlowType::Loop)
            }
            "match_expression" => Some(ControlFlowType::Match),
            "return_expression" => Some(ControlFlowType::Return),
            "break_expression" => Some(ControlFlowType::Break),
            "continue_expression" => Some(ControlFlowType::Continue),
            _ => None,
        }
    }

    fn get_match_arms<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        let mut arms = Vec::new();
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "match_arm" {
                arms.push(child);
            }
        }
        arms
    }

    fn is_chained_condition(&self, node: &TSNode) -> bool {
        // Rust uses if expressions, chaining is done via else if pattern
        // Check if this if_expression is in the else branch of another if_expression
        node.kind() == "if_expression"
            && node
                .parent()
                .map(|p| {
                    p.kind() == "else_clause"
                        || (p.kind() == "block"
                            && p.parent()
                                .map(|pp| pp.kind() == "else_clause")
                                .unwrap_or(false))
                })
                .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    fn parse_rust(source: &str) -> Tree {
        let mut parser = Parser::new();
        parser.set_language(&tree_sitter_rust::language()).unwrap();
        parser.parse(source, None).unwrap()
    }

    #[test]
    fn test_extract_struct() {
        let source = r#"
pub struct User {
    id: u64,
    name: String,
}
"#;
        let tree = parse_rust(source);
        let plugin = RustPlugin::new();
        let mut ctx = ExtractionContext::new(source, "user.rs", "test-repo", LanguageId::Rust);

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
    fn test_extract_trait() {
        let source = r#"
pub trait Display {
    fn fmt(&self, f: &mut Formatter) -> Result;
}
"#;
        let tree = parse_rust(source);
        let plugin = RustPlugin::new();
        let mut ctx = ExtractionContext::new(source, "display.rs", "test-repo", LanguageId::Rust);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let trait_node = result.nodes.iter().find(|n| n.kind == NodeKind::Trait);
        assert!(trait_node.is_some());
    }

    #[test]
    fn test_extract_impl() {
        let source = r#"
impl Display for User {
    fn fmt(&self, f: &mut Formatter) -> Result {
        write!(f, "{}", self.name)
    }
}
"#;
        let tree = parse_rust(source);
        let plugin = RustPlugin::new();
        let mut ctx = ExtractionContext::new(source, "user.rs", "test-repo", LanguageId::Rust);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let impl_node = result.nodes.iter().find(|n| n.kind == NodeKind::TraitImpl);
        assert!(impl_node.is_some());

        let implements_edge = result
            .edges
            .iter()
            .find(|e| e.kind == EdgeKind::ImplementsTrait);
        assert!(implements_edge.is_some());
    }

    #[test]
    fn test_extract_enum() {
        let source = r#"
pub enum Status {
    Pending,
    Active,
    Completed,
}
"#;
        let tree = parse_rust(source);
        let plugin = RustPlugin::new();
        let mut ctx = ExtractionContext::new(source, "status.rs", "test-repo", LanguageId::Rust);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let enum_node = result.nodes.iter().find(|n| n.kind == NodeKind::Enum);
        assert!(enum_node.is_some());

        let variants: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::EnumMember)
            .collect();
        assert_eq!(variants.len(), 3);
    }
}
