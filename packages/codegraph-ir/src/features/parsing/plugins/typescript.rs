//! TypeScript/JavaScript Language Plugin
//!
//! Implements LanguagePlugin for TypeScript/JavaScript source code.
//! Supports: classes, interfaces, types, functions, decorators, React components

use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::features::parsing::ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, SpanExt,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Result};

/// TypeScript language plugin
pub struct TypeScriptPlugin {
    /// Whether to use TypeScript or JavaScript grammar
    use_typescript: bool,
}

impl TypeScriptPlugin {
    pub fn new() -> Self {
        Self {
            use_typescript: true,
        }
    }

    pub fn javascript() -> Self {
        Self {
            use_typescript: false,
        }
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

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Class,
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

        // Extract decorators
        self.extract_decorators(ctx, node, result, &node_id);

        // Extract heritage (extends/implements)
        if let Some(heritage) = node.child_by_field_name("heritage") {
            self.extract_heritage(ctx, &heritage, result, &node_id);
        }

        // Extract type parameters
        self.extract_type_parameters(ctx, node, id_gen, result, &node_id);

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

    /// Extract interface declaration (TypeScript)
    fn extract_interface(
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
            NodeKind::Interface,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Extract extends
        if let Some(extends) = node.child_by_field_name("extends") {
            let mut cursor = extends.walk();
            for child in extends.children(&mut cursor) {
                if child.kind() == "type_identifier" || child.kind() == "generic_type" {
                    let base_name = ctx.node_text(&child).to_string();
                    result.add_edge(Edge::new(
                        node_id.clone(),
                        format!("ref:{}", base_name),
                        EdgeKind::Extends,
                    ));
                }
            }
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

    /// Extract type alias (TypeScript)
    fn extract_type_alias(
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

        let mut ir_node = Node::new(
            node_id,
            NodeKind::TypeAlias,
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

    /// Extract enum declaration (TypeScript)
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
            format!("{}.{}", ctx.fqn_prefix(), name)
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

        result.add_node(ir_node);

        // Extract members
        if let Some(body) = node.child_by_field_name("body") {
            let mut cursor = body.walk();
            for child in body.children(&mut cursor) {
                if child.kind() == "enum_member" {
                    if let Some(name_node) = child.child_by_field_name("name") {
                        let member_name = ctx.node_text(&name_node).to_string();
                        let member_id = id_gen.next_node();
                        let member_fqn = format!("{}.{}", fqn, member_name);

                        let mut member_node = Node::new(
                            member_id.clone(),
                            NodeKind::EnumMember,
                            member_fqn,
                            ctx.file_path.to_string(),
                            child.to_span(),
                        )
                        .with_language(ctx.language.name().to_string())
                        .with_name(member_name);

                        member_node.parent_id = Some(node_id.clone());
                        result.add_node(member_node);
                    }
                }
            }
        }
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

        // Handle anonymous functions
        if name.is_empty() && node.kind() != "arrow_function" {
            return;
        }

        let node_id = id_gen.next_node();
        let func_name = if name.is_empty() {
            format!("anonymous_{}", id_gen.next("anon"))
        } else {
            name.clone()
        };

        let fqn = if ctx.fqn_prefix().is_empty() {
            func_name.clone()
        } else {
            format!("{}.{}", ctx.fqn_prefix(), func_name)
        };

        // Determine kind - check for class, nested function, or arrow function
        let is_inside_class = ctx
            .scope_stack
            .iter()
            .any(|s| s.chars().next().map(|c| c.is_uppercase()).unwrap_or(false));
        let is_inside_function = ctx
            .scope_stack
            .iter()
            .any(|s| s.chars().next().map(|c| c.is_lowercase()).unwrap_or(false));

        let kind = if is_inside_class {
            NodeKind::Method
        } else if node.kind() == "arrow_function" || is_inside_function {
            NodeKind::Lambda // Arrow functions and nested functions are closures
        } else {
            NodeKind::Function
        };

        // Check if async function (async keyword before function/method)
        let is_async = {
            let mut cursor = node.walk();
            let mut found_async = false;
            for child in node.children(&mut cursor) {
                let child_kind = child.kind();
                if child_kind == "async" {
                    found_async = true;
                    break;
                }
                // Stop if we reach function/arrow marker
                if child_kind == "function" || child_kind == "=>" {
                    break;
                }
            }
            found_async
        };

        // Check for generator function (function*)
        let is_generator = {
            let mut cursor = node.walk();
            let mut found_generator = false;
            for child in node.children(&mut cursor) {
                if child.kind() == "*" || child.kind() == "generator" {
                    found_generator = true;
                    break;
                }
            }
            found_generator
        };

        let mut ir_node = Node::new(
            node_id.clone(),
            kind.clone(),
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(func_name.clone());

        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        if is_async {
            ir_node.is_async = Some(true);
        }
        if is_generator {
            ir_node.is_generator = Some(true);
        }

        // Add edges from parent
        if let Some(ref parent) = ctx.parent_id {
            // Use Captures edge for closures (arrow functions and nested functions)
            let edge_kind = if kind == NodeKind::Lambda {
                EdgeKind::Captures
            } else {
                EdgeKind::Defines
            };

            result.add_edge(Edge::new(parent.clone(), node_id.clone(), edge_kind));
        }

        // Extract decorators
        self.extract_decorators(ctx, node, result, &node_id);

        result.add_node(ir_node);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }
    }

    /// Extract variable/const/let declaration
    fn extract_variable(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
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

                    // Check if it's an exported const (could be a component)
                    let kind = if self.is_react_component(&name, &child, ctx.source) {
                        NodeKind::Function // React functional component
                    } else {
                        NodeKind::Variable
                    };

                    let mut ir_node = Node::new(
                        node_id.clone(),
                        kind,
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

    /// Extract import statement
    fn extract_import(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Get the source module
        let source_module = node
            .child_by_field_name("source")
            .map(|n| ctx.node_text(&n).to_string())
            .unwrap_or_default()
            .trim_matches(|c| c == '"' || c == '\'')
            .to_string();

        let ir_node = Node::new(
            node_id,
            NodeKind::Import,
            format!("import:{}", source_module),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(source_module);

        result.add_node(ir_node);
    }

    /// Extract export statement
    fn extract_export(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Process the exported declaration
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            self.extract_node(ctx, &child, id_gen, result);
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
            let kind = child.kind();
            if kind == "required_parameter"
                || kind == "optional_parameter"
                || kind == "rest_parameter"
                || kind == "identifier"
            {
                let name = if kind == "identifier" {
                    ctx.node_text(&child).to_string()
                } else {
                    child
                        .child_by_field_name("pattern")
                        .or_else(|| child.child_by_field_name("name"))
                        .map(|n| ctx.node_text(&n).to_string())
                        .unwrap_or_default()
                };

                if name.is_empty() || name == "this" {
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

    /// Extract decorators
    fn extract_decorators(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        target_id: &str,
    ) {
        // Look for decorator nodes before the declaration
        if let Some(parent) = node.parent() {
            let mut cursor = parent.walk();
            for sibling in parent.children(&mut cursor) {
                if sibling.kind() == "decorator" {
                    let deco_text = ctx.node_text(&sibling).to_string();
                    result.add_edge(Edge::new(
                        target_id.to_string(),
                        format!("ref:{}", deco_text),
                        EdgeKind::DecoratedWith,
                    ));
                }
            }
        }
    }

    /// Extract heritage clause (extends/implements)
    fn extract_heritage(
        &self,
        ctx: &ExtractionContext,
        heritage_node: &TSNode,
        result: &mut ExtractionResult,
        class_id: &str,
    ) {
        let mut cursor = heritage_node.walk();
        for child in heritage_node.children(&mut cursor) {
            if child.kind() == "extends_clause" {
                if let Some(type_node) = child.child(1) {
                    let base = ctx.node_text(&type_node).to_string();
                    result.add_edge(Edge::new(
                        class_id.to_string(),
                        format!("ref:{}", base),
                        EdgeKind::Extends,
                    ));
                }
            } else if child.kind() == "implements_clause" {
                let mut impl_cursor = child.walk();
                for impl_child in child.children(&mut impl_cursor) {
                    if impl_child.kind() == "type_identifier" || impl_child.kind() == "generic_type"
                    {
                        let iface = ctx.node_text(&impl_child).to_string();
                        result.add_edge(Edge::new(
                            class_id.to_string(),
                            format!("ref:{}", iface),
                            EdgeKind::Implements,
                        ));
                    }
                }
            }
        }
    }

    /// Extract type parameters
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
                    let name = child
                        .child_by_field_name("name")
                        .map(|n| ctx.node_text(&n).to_string())
                        .unwrap_or_default();

                    if name.is_empty() {
                        continue;
                    }

                    let node_id = id_gen.next_node();
                    let mut ir_node = Node::new(
                        node_id.clone(),
                        NodeKind::TypeParameter,
                        format!("{}.{}", ctx.fqn_prefix(), name),
                        ctx.file_path.to_string(),
                        child.to_span(),
                    )
                    .with_language(ctx.language.name().to_string())
                    .with_name(name);

                    ir_node.parent_id = Some(parent_id.to_string());
                    result.add_node(ir_node);

                    // Extract constraint
                    if let Some(constraint) = child.child_by_field_name("constraint") {
                        let bound = ctx.node_text(&constraint).to_string();
                        result.add_edge(Edge::new(
                            node_id,
                            format!("ref:{}", bound),
                            EdgeKind::BoundedBy,
                        ));
                    }
                }
            }
        }
    }

    /// Check if a const is a React functional component
    fn is_react_component(&self, name: &str, node: &TSNode, source: &str) -> bool {
        // PascalCase name
        if !name
            .chars()
            .next()
            .map(|c| c.is_uppercase())
            .unwrap_or(false)
        {
            return false;
        }

        // Check if value is an arrow function or function that returns JSX
        if let Some(value) = node.child_by_field_name("value") {
            let text = source.get(value.byte_range()).unwrap_or("");
            return text.contains("=>") && (text.contains("<") || text.contains("React."));
        }

        false
    }

    /// Extract body
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
            "class_declaration" | "class" => self.extract_class(ctx, node, id_gen, result),
            "interface_declaration" => self.extract_interface(ctx, node, id_gen, result),
            "type_alias_declaration" => self.extract_type_alias(ctx, node, id_gen, result),
            "enum_declaration" => self.extract_enum(ctx, node, id_gen, result),
            "function_declaration" | "method_definition" | "arrow_function" => {
                self.extract_function(ctx, node, id_gen, result)
            }
            "lexical_declaration" | "variable_declaration" => {
                self.extract_variable(ctx, node, id_gen, result)
            }
            "import_statement" => self.extract_import(ctx, node, id_gen, result),
            "export_statement" => self.extract_export(ctx, node, id_gen, result),
            "try_statement" => self.extract_try(ctx, node, id_gen, result),
            "throw_statement" => self.extract_throw(ctx, node, id_gen, result),
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

        // Extract catch and finally clauses
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "catch_clause" {
                self.extract_catch(ctx, &child, id_gen, result, &node_id);
            } else if child.kind() == "finally_clause" {
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

        // Get exception parameter
        let (exception_types, exception_var) =
            if let Some(param) = node.child_by_field_name("parameter") {
                let var_name = if param.kind() == "identifier" {
                    Some(ctx.node_text(&param).to_string())
                } else {
                    param
                        .child_by_field_name("name")
                        .map(|n| ctx.node_text(&n).to_string())
                };

                // Get type annotation if present: catch (e: Error)
                let types = if let Some(type_node) = param.child_by_field_name("type") {
                    vec![ctx.node_text(&type_node).to_string()]
                } else {
                    vec![] // catch all (any type)
                };

                (types, var_name)
            } else {
                (vec![], None) // catch without parameter
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
            .map(|child| {
                if child.kind() == "new_expression" {
                    // throw new Error("msg")
                    child
                        .child_by_field_name("constructor")
                        .map(|c| ctx.node_text(&c).to_string())
                        .unwrap_or_else(|| "Error".to_string())
                } else {
                    // throw error
                    ctx.node_text(&child).to_string()
                }
            })
            .unwrap_or_else(|| "Error".to_string());

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
}

impl Default for TypeScriptPlugin {
    fn default() -> Self {
        Self::new()
    }
}

impl LanguagePlugin for TypeScriptPlugin {
    fn tree_sitter_language(&self) -> TSLanguage {
        if self.use_typescript {
            tree_sitter_typescript::language_typescript()
        } else {
            tree_sitter_typescript::language_typescript() // JS uses same grammar
        }
    }

    fn language_id(&self) -> LanguageId {
        if self.use_typescript {
            LanguageId::TypeScript
        } else {
            LanguageId::JavaScript
        }
    }

    fn extensions(&self) -> &[&str] {
        if self.use_typescript {
            &["ts", "tsx"]
        } else {
            &["js", "jsx", "mjs", "cjs"]
        }
    }

    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind> {
        match ts_kind {
            "class_declaration" | "class" => Some(NodeKind::Class),
            "interface_declaration" => Some(NodeKind::Interface),
            "type_alias_declaration" => Some(NodeKind::TypeAlias),
            "enum_declaration" => Some(NodeKind::Enum),
            "enum_member" => Some(NodeKind::EnumMember),
            "function_declaration" => Some(NodeKind::Function),
            "method_definition" => Some(NodeKind::Method),
            "arrow_function" => Some(NodeKind::Lambda),
            "lexical_declaration" | "variable_declaration" => Some(NodeKind::Variable),
            "import_statement" => Some(NodeKind::Import),
            "required_parameter" | "optional_parameter" => Some(NodeKind::Parameter),
            "type_parameter" => Some(NodeKind::TypeParameter),
            "property_definition" => Some(NodeKind::Field),
            _ => None,
        }
    }

    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            "class_declaration" | "class" => SyntaxKind::ClassDef,
            "function_declaration" | "method_definition" | "arrow_function" => {
                SyntaxKind::FunctionDef
            }
            "lexical_declaration" | "variable_declaration" => SyntaxKind::AssignmentStmt,
            "import_statement" => SyntaxKind::ImportDecl,
            "required_parameter" | "optional_parameter" => SyntaxKind::ParameterDecl,
            "call_expression" => SyntaxKind::CallExpr,
            "identifier" => SyntaxKind::NameExpr,
            "member_expression" => SyntaxKind::AttributeExpr,
            "return_statement" => SyntaxKind::ReturnStmt,
            "if_statement" => SyntaxKind::IfStmt,
            "for_statement" | "for_in_statement" | "for_of_statement" => SyntaxKind::ForStmt,
            "while_statement" => SyntaxKind::WhileStmt,
            "try_statement" => SyntaxKind::TryStmt,
            "throw_statement" => SyntaxKind::RaiseStmt,
            "await_expression" => SyntaxKind::AwaitExpr,
            "yield_expression" => SyntaxKind::YieldExpr,
            "statement_block" => SyntaxKind::Block,
            "comment" => SyntaxKind::Comment,
            "decorator" => SyntaxKind::Decorator,
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

        // Extract all top-level declarations
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

    fn is_public(&self, name: &str) -> bool {
        // In JS/TS, export determines visibility, not naming
        !name.starts_with('_')
    }

    fn extract_docstring(&self, node: &TSNode, source: &str) -> Option<String> {
        // Look for JSDoc comment before the node
        if let Some(prev) = node.prev_sibling() {
            if prev.kind() == "comment" {
                let text = source.get(prev.byte_range())?;
                if text.starts_with("/**") {
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
        }
        None
    }

    fn is_statement_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            // Variable declarations
            "lexical_declaration" | "variable_declaration" |
            // Assignment expressions
            "assignment_expression" | "augmented_assignment_expression" |
            // Expression statements
            "expression_statement" |
            // Control flow statements
            "if_statement" | "for_statement" | "for_in_statement" |
            "while_statement" | "do_statement" | "switch_statement" |
            "try_statement" |
            // Other statements
            "return_statement" | "break_statement" | "continue_statement" |
            "throw_statement" | "debugger_statement" | "empty_statement" |
            // Import/Export
            "import_statement" | "export_statement" |
            // Function and class declarations
            "function_declaration" | "class_declaration" |
            "method_definition" | "interface_declaration" | "type_alias_declaration" |
            "enum_declaration"
        )
    }

    fn is_control_flow_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            "if_statement"
                | "for_statement"
                | "for_in_statement"
                | "while_statement"
                | "do_statement"
                | "switch_statement"
                | "try_statement"
                | "catch_clause"
                | "finally_clause"
                | "else_clause"
                | "case_clause"
                | "default_clause"
        )
    }

    fn get_control_flow_type(
        &self,
        node: &TSNode,
    ) -> Option<crate::features::parsing::ports::ControlFlowType> {
        use crate::features::parsing::ports::ControlFlowType;
        match node.kind() {
            "if_statement" => Some(ControlFlowType::If),
            "for_statement" | "for_in_statement" | "for_of_statement" | "while_statement"
            | "do_statement" => Some(ControlFlowType::Loop),
            "switch_statement" => Some(ControlFlowType::Match),
            "try_statement" => Some(ControlFlowType::Try),
            "yield_expression" => Some(ControlFlowType::Yield),
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
            if matches!(child.kind(), "case_clause" | "default_clause") {
                arms.push(child);
            }
        }
        arms
    }

    fn is_chained_condition(&self, node: &TSNode) -> bool {
        // TypeScript doesn't have explicit elif, but can have if_statement inside else_clause
        node.kind() == "if_statement"
            && node
                .parent()
                .map(|p| p.kind() == "else_clause")
                .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    fn parse_typescript(source: &str) -> Tree {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_typescript::language_typescript())
            .unwrap();
        parser.parse(source, None).unwrap()
    }

    #[test]
    fn test_extract_class() {
        let source = r#"
class MyClass extends BaseClass implements IService {
    private field: string;

    constructor(value: string) {
        this.field = value;
    }

    public method(arg: number): void {
        console.log(arg);
    }
}
"#;
        let tree = parse_typescript(source);
        let plugin = TypeScriptPlugin::new();
        let mut ctx =
            ExtractionContext::new(source, "test.ts", "test-repo", LanguageId::TypeScript);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let class = result.nodes.iter().find(|n| n.kind == NodeKind::Class);
        assert!(class.is_some());
        assert_eq!(class.unwrap().name, Some("MyClass".to_string()));
    }

    #[test]
    fn test_extract_interface() {
        let source = r#"
interface Service<T> {
    process(input: T): T;
}
"#;
        let tree = parse_typescript(source);
        let plugin = TypeScriptPlugin::new();
        let mut ctx =
            ExtractionContext::new(source, "test.ts", "test-repo", LanguageId::TypeScript);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let iface = result.nodes.iter().find(|n| n.kind == NodeKind::Interface);
        assert!(iface.is_some());
    }

    #[test]
    fn test_extract_type_alias() {
        let source = r#"
type Handler<T> = (input: T) => Promise<T>;
"#;
        let tree = parse_typescript(source);
        let plugin = TypeScriptPlugin::new();
        let mut ctx =
            ExtractionContext::new(source, "test.ts", "test-repo", LanguageId::TypeScript);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let type_alias = result.nodes.iter().find(|n| n.kind == NodeKind::TypeAlias);
        assert!(type_alias.is_some());
    }

    #[test]
    fn test_extract_function() {
        let source = r#"
function greet(name: string): string {
    return `Hello, ${name}!`;
}

const arrowFunc = (x: number) => x * 2;
"#;
        let tree = parse_typescript(source);
        let plugin = TypeScriptPlugin::new();
        let mut ctx =
            ExtractionContext::new(source, "test.ts", "test-repo", LanguageId::TypeScript);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let funcs: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Function)
            .collect();
        assert!(!funcs.is_empty());
    }
}
