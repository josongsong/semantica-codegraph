//! Python Language Plugin
//!
//! Implements LanguagePlugin for Python source code.

use tree_sitter::{Language as TSLanguage, Node as TSNode, Tree};

use crate::features::parsing::domain::SyntaxKind;
use crate::features::parsing::ports::{
    ExtractionContext, ExtractionResult, IdGenerator, LanguageId, LanguagePlugin, SpanExt,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Result};

/// Python language plugin
pub struct PythonPlugin;

impl PythonPlugin {
    pub fn new() -> Self {
        Self
    }

    /// Extract function definition
    fn extract_function(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Get function name
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

        // Determine if method, nested function (closure), or top-level function
        let is_inside_class = ctx.scope_stack.iter().any(|s| {
            // Inside a class
            s.chars().next().map(|c| c.is_uppercase()).unwrap_or(false)
        });
        let is_inside_function = ctx.scope_stack.iter().any(|s| {
            // Inside a function (nested function = closure)
            s.chars().next().map(|c| c.is_lowercase()).unwrap_or(false)
        });

        let kind = if is_inside_class {
            NodeKind::Method
        } else if is_inside_function {
            NodeKind::Lambda // Nested function is a closure
        } else {
            NodeKind::Function
        };

        // Extract docstring
        let docstring = self.extract_docstring(node, ctx.source);

        // Check if async function
        let is_async = {
            let mut cursor = node.walk();
            let mut found_async = false;
            for child in node.children(&mut cursor) {
                if child.kind() == "async" {
                    found_async = true;
                    break;
                }
            }
            found_async
        };

        // Check if generator function (contains yield)
        let is_generator = if let Some(body) = node.child_by_field_name("body") {
            self.contains_yield(&body, ctx)
        } else {
            false
        };

        // Build node
        let mut ir_node = Node::new(
            node_id.clone(),
            kind.clone(),
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(doc) = docstring {
            ir_node = ir_node.with_docstring(doc);
        }
        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }
        if is_async {
            ir_node.is_async = Some(true);
        }
        if is_generator {
            ir_node.is_generator = Some(true);
        }

        // Extract decorators
        self.extract_decorators(ctx, node, result, &node_id);

        // Add defines edge from parent
        if let Some(ref parent_id) = ctx.parent_id {
            let edge_kind = if kind == NodeKind::Lambda {
                EdgeKind::Captures // Closures capture variables from outer scope
            } else {
                EdgeKind::Defines
            };
            let edge = Edge::new(parent_id.clone(), node_id.clone(), edge_kind);
            result.add_edge(edge);
        }

        result.add_node(ir_node);

        // Process body
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        // Extract parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Extract body statements
        if let Some(body) = node.child_by_field_name("body") {
            self.extract_body(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract class definition
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

        // Extract docstring
        let docstring = self.extract_docstring(node, ctx.source);

        let mut ir_node = Node::new(
            node_id.clone(),
            NodeKind::Class,
            fqn.clone(),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(name.clone());

        if let Some(doc) = docstring {
            ir_node = ir_node.with_docstring(doc);
        }
        if let Some(ref parent) = ctx.parent_id {
            ir_node.parent_id = Some(parent.clone());
        }

        // Extract decorators
        self.extract_decorators(ctx, node, result, &node_id);

        // Add defines edge from parent
        if let Some(ref parent_id) = ctx.parent_id {
            let edge = Edge::new(parent_id.clone(), node_id.clone(), EdgeKind::Defines);
            result.add_edge(edge);
        }

        // Extract inheritance
        if let Some(bases) = node.child_by_field_name("superclasses") {
            self.extract_base_classes(ctx, &bases, id_gen, result, &node_id);
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

    /// Extract import statement
    fn extract_import(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();
        let import_text = ctx.node_text(node).to_string();

        // Parse import text to get module name
        let module_name = if node.kind() == "import_statement" {
            // import foo
            node.child_by_field_name("name")
                .map(|n| ctx.node_text(&n).to_string())
                .unwrap_or_else(|| import_text.clone())
        } else {
            // from foo import bar
            node.child_by_field_name("module_name")
                .map(|n| ctx.node_text(&n).to_string())
                .unwrap_or_else(|| import_text.clone())
        };

        let ir_node = Node::new(
            node_id.clone(),
            NodeKind::Import,
            format!("import:{}", module_name),
            ctx.file_path.to_string(),
            node.to_span(),
        )
        .with_language(ctx.language.name().to_string())
        .with_name(module_name);

        result.add_node(ir_node);
    }

    /// Extract variable assignment
    fn extract_assignment(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Get left side (target)
        if let Some(left) = node.child_by_field_name("left") {
            let name = ctx.node_text(&left).to_string();
            if name.is_empty() || name.contains('.') {
                return; // Skip attribute assignments
            }

            let node_id = id_gen.next_node();
            let fqn = if ctx.fqn_prefix().is_empty() {
                name.clone()
            } else {
                format!("{}.{}", ctx.fqn_prefix(), name)
            };

            let kind = if ctx.scope_stack.is_empty() {
                NodeKind::Variable
            } else if ctx
                .scope_stack
                .last()
                .map(|s| s.chars().next().map(|c| c.is_uppercase()).unwrap_or(false))
                .unwrap_or(false)
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
                left.to_span(),
            )
            .with_language(ctx.language.name().to_string())
            .with_name(name);

            if let Some(ref parent) = ctx.parent_id {
                ir_node.parent_id = Some(parent.clone());
            }

            result.add_node(ir_node);
        }

        // Process the right side (value) to extract any function calls
        // e.g., "x = eval(user_input)" should extract the eval() call
        if let Some(right) = node.child_by_field_name("right") {
            self.extract_node(ctx, &right, id_gen, result);
        }
    }

    /// Extract parameters from function
    fn extract_parameters(
        &self,
        ctx: &mut ExtractionContext,
        params_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        func_id: &str,
    ) {
        let mut cursor = params_node.walk();
        for child in params_node.children(&mut cursor) {
            let kind = child.kind();
            if kind == "identifier" || kind == "typed_parameter" || kind == "default_parameter" {
                let name = if kind == "identifier" {
                    ctx.node_text(&child).to_string()
                } else {
                    child
                        .child_by_field_name("name")
                        .map(|n| ctx.node_text(&n).to_string())
                        .unwrap_or_default()
                };

                if name.is_empty() || name == "self" || name == "cls" {
                    continue;
                }

                let node_id = id_gen.next_node();
                let fqn = format!("{}.{}", ctx.fqn_prefix(), name);

                let mut ir_node = Node::new(
                    node_id.clone(),
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

    /// Extract base classes
    fn extract_base_classes(
        &self,
        ctx: &ExtractionContext,
        bases_node: &TSNode,
        _id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        class_id: &str,
    ) {
        let mut cursor = bases_node.walk();
        for child in bases_node.children(&mut cursor) {
            if child.kind() == "identifier" || child.kind() == "attribute" {
                let base_name = ctx.node_text(&child).to_string();
                if !base_name.is_empty() {
                    // Create inheritance edge
                    let edge = Edge::new(
                        class_id.to_string(),
                        format!("ref:{}", base_name),
                        EdgeKind::Inherits,
                    );
                    result.add_edge(edge);
                }
            }
        }
    }

    /// Extract function call with FQN resolution
    fn extract_call(
        &self,
        ctx: &mut ExtractionContext,
        call_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        use crate::features::parsing::infrastructure::extractors::fqn_resolver::FqnResolver;

        // Get the function being called
        let function_node = call_node.child_by_field_name("function");
        if let Some(function_node) = function_node {
            let callee_name = ctx.node_text(&function_node).to_string();

            if !callee_name.is_empty() && ctx.parent_id.is_some() {
                // Check if it's a locally defined function
                let local_fqn = if ctx.fqn_prefix().is_empty() {
                    callee_name.clone()
                } else {
                    format!("{}.{}", ctx.fqn_prefix(), callee_name)
                };

                let is_local = result.nodes.iter().any(|n| {
                    n.name.as_ref() == Some(&callee_name)
                        || n.fqn == callee_name
                        || n.fqn == local_fqn
                });

                let callee_fqn = if is_local {
                    // Local function: use module.function
                    local_fqn
                } else {
                    // Not local: resolve via FqnResolver (built-ins, stdlib, external)
                    let fqn_resolver = FqnResolver::new();
                    fqn_resolver.resolve(&callee_name)
                };

                // Create CALLS edge from current function/method to the callee
                // SAFETY: parent_id is guaranteed to be Some by the check on line 405
                let edge = Edge::new(
                    ctx.parent_id.as_ref().unwrap().clone(),
                    callee_fqn.clone(),
                    EdgeKind::Calls,
                );

                result.add_edge(edge);
            }
        }

        // Also recurse into arguments (for nested calls like eval(compile(...)))
        let mut cursor = call_node.walk();
        for child in call_node.children(&mut cursor) {
            self.extract_node(ctx, &child, id_gen, result);
        }
    }

    /// Extract function body (recursive)
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

    /// Extract try/except/finally statement
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

        // Extract except/catch handlers
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "except_clause" {
                self.extract_except(ctx, &child, id_gen, result, &node_id);
            } else if child.kind() == "finally_clause" {
                self.extract_finally(ctx, &child, id_gen, result, &node_id);
            }
        }
    }

    /// Extract except/catch clause
    fn extract_except(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        try_id: &str,
    ) {
        let node_id = id_gen.next_node();

        // Get exception type(s)
        let exception_types = if let Some(type_node) = node.child_by_field_name("type") {
            vec![ctx.node_text(&type_node).to_string()]
        } else {
            vec![] // Catch all
        };

        // Get exception variable name (as exc:)
        let exception_var = node
            .child_by_field_name("name")
            .map(|n| ctx.node_text(&n).to_string());

        // Create Catch node
        let mut catch_node = Node::new(
            node_id.clone(),
            NodeKind::Catch,
            format!("except {}", exception_types.join(", ")),
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

        // Extract except body
        if let Some(body) = node.child_by_field_name("consequence") {
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

    /// Extract raise statement
    fn extract_raise(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let node_id = id_gen.next_node();

        // Get exception type being raised
        let exception_type = node
            .child(0)
            .filter(|child| child.kind() != "raise")
            .map(|child| {
                // Get exception class name
                if child.kind() == "call" {
                    // raise ValueError("msg")
                    child
                        .child_by_field_name("function")
                        .map(|f| ctx.node_text(&f).to_string())
                        .unwrap_or_else(|| "Exception".to_string())
                } else {
                    // raise exc or raise
                    ctx.node_text(&child).to_string()
                }
            })
            .unwrap_or_else(|| "Exception".to_string());

        // Create Raise node
        let mut raise_node = Node::new(
            node_id.clone(),
            NodeKind::Raise,
            format!("raise {}", exception_type),
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
        raise_node.metadata = Some(serde_json::to_string(&metadata).unwrap_or_default());

        if let Some(ref parent) = ctx.parent_id {
            result.add_edge(Edge::new(
                parent.clone(),
                node_id.clone(),
                EdgeKind::Contains,
            ));
        }

        result.add_node(raise_node);
    }

    /// Extract lambda expression
    fn extract_lambda(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        // Generate synthetic name for lambda using line number
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

        // Add Captures edge from parent (lambda is always a closure)
        if let Some(ref parent_id) = ctx.parent_id {
            let edge = Edge::new(parent_id.clone(), node_id.clone(), EdgeKind::Captures);
            result.add_edge(edge);
        }

        result.add_node(ir_node);

        // Process lambda body
        let old_parent = ctx.parent_id.take();
        ctx.parent_id = Some(node_id.clone());
        ctx.push_scope(&name);

        // Extract lambda parameters
        if let Some(params) = node.child_by_field_name("parameters") {
            self.extract_lambda_parameters(ctx, &params, id_gen, result, &node_id);
        }

        // Extract lambda body
        if let Some(body) = node.child_by_field_name("body") {
            self.extract_node(ctx, &body, id_gen, result);
        }

        ctx.pop_scope();
        ctx.parent_id = old_parent;
    }

    /// Extract lambda parameters (simpler than function parameters)
    fn extract_lambda_parameters(
        &self,
        ctx: &ExtractionContext,
        params_node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
        lambda_id: &str,
    ) {
        // Lambda parameters are just identifiers, not full parameter declarations
        let mut cursor = params_node.walk();
        for child in params_node.children(&mut cursor) {
            if child.kind() == "identifier" {
                let name = ctx.node_text(&child).to_string();
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

    /// Extract decorators from function or class
    /// Python decorators: @decorator, @decorator(args)
    fn extract_decorators(
        &self,
        ctx: &ExtractionContext,
        node: &TSNode,
        result: &mut ExtractionResult,
        target_id: &str,
    ) {
        // Look for decorator nodes before the definition
        // In tree-sitter-python, decorators are siblings before function_definition/class_definition
        if let Some(parent) = node.parent() {
            let mut cursor = parent.walk();
            for sibling in parent.children(&mut cursor) {
                if sibling.kind() == "decorator" {
                    // Get decorator name (skip @ symbol)
                    let decorator_text = ctx.node_text(&sibling).to_string();
                    let decorator_name = decorator_text.trim_start_matches('@').trim();

                    if !decorator_name.is_empty() {
                        result.add_edge(Edge::new(
                            target_id.to_string(),
                            format!("ref:@{}", decorator_name),
                            EdgeKind::DecoratedWith,
                        ));
                    }
                }
                // Stop when we reach the actual definition
                if sibling.id() == node.id() {
                    break;
                }
            }
        }
    }

    /// Check if node contains yield expression (recursive)
    fn contains_yield(&self, node: &TSNode, ctx: &ExtractionContext) -> bool {
        // Check if this node is a yield expression
        if node.kind() == "yield" || node.kind() == "yield_expression" {
            return true;
        }

        // Don't recurse into nested function definitions (they have their own generator status)
        if node.kind() == "function_definition" || node.kind() == "lambda" {
            return false;
        }

        // Recursively check children
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if self.contains_yield(&child, ctx) {
                return true;
            }
        }
        false
    }

    /// Extract a single node
    fn extract_node(
        &self,
        ctx: &mut ExtractionContext,
        node: &TSNode,
        id_gen: &mut IdGenerator,
        result: &mut ExtractionResult,
    ) {
        let kind = node.kind();

        match kind {
            "function_definition" => self.extract_function(ctx, node, id_gen, result),
            "class_definition" => self.extract_class(ctx, node, id_gen, result),
            "lambda" => self.extract_lambda(ctx, node, id_gen, result),
            "import_statement" | "import_from_statement" => {
                self.extract_import(ctx, node, id_gen, result)
            }
            "assignment" => self.extract_assignment(ctx, node, id_gen, result),
            "call" => {
                self.extract_call(ctx, node, id_gen, result);
            }
            "try_statement" => self.extract_try(ctx, node, id_gen, result),
            "raise_statement" => self.extract_raise(ctx, node, id_gen, result),
            _ => {
                // Recurse into children for nested definitions
                let mut cursor = node.walk();
                for child in node.children(&mut cursor) {
                    self.extract_node(ctx, &child, id_gen, result);
                }
            }
        }
    }
}

impl Default for PythonPlugin {
    fn default() -> Self {
        Self::new()
    }
}

impl LanguagePlugin for PythonPlugin {
    fn tree_sitter_language(&self) -> TSLanguage {
        tree_sitter_python::language()
    }

    fn language_id(&self) -> LanguageId {
        LanguageId::Python
    }

    fn map_node_kind(&self, ts_kind: &str) -> Option<NodeKind> {
        match ts_kind {
            "function_definition" => Some(NodeKind::Function),
            "class_definition" => Some(NodeKind::Class),
            "lambda" => Some(NodeKind::Lambda),
            "import_statement" | "import_from_statement" => Some(NodeKind::Import),
            "assignment" => Some(NodeKind::Variable),
            "parameter" | "typed_parameter" | "default_parameter" => Some(NodeKind::Parameter),
            _ => None,
        }
    }

    fn map_syntax_kind(&self, ts_kind: &str) -> SyntaxKind {
        match ts_kind {
            "function_definition" => SyntaxKind::FunctionDef,
            "class_definition" => SyntaxKind::ClassDef,
            "lambda" => SyntaxKind::LambdaDef,
            "assignment" => SyntaxKind::AssignmentStmt,
            "parameter" | "typed_parameter" | "default_parameter" => SyntaxKind::ParameterDecl,
            "import_statement" | "import_from_statement" => SyntaxKind::ImportDecl,
            "call" => SyntaxKind::CallExpr,
            "identifier" => SyntaxKind::NameExpr,
            "attribute" => SyntaxKind::AttributeExpr,
            "return_statement" => SyntaxKind::ReturnStmt,
            "if_statement" => SyntaxKind::IfStmt,
            "for_statement" => SyntaxKind::ForStmt,
            "while_statement" => SyntaxKind::WhileStmt,
            "try_statement" => SyntaxKind::TryStmt,
            "with_statement" => SyntaxKind::WithStmt,
            "break_statement" => SyntaxKind::BreakStmt,
            "continue_statement" => SyntaxKind::ContinueStmt,
            "raise_statement" => SyntaxKind::RaiseStmt,
            "yield" => SyntaxKind::YieldExpr,
            "await" => SyntaxKind::AwaitExpr,
            "block" | "module" => SyntaxKind::Block,
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

        // Extract all top-level definitions
        let root = tree.root_node();
        let mut cursor = root.walk();
        for child in root.children(&mut cursor) {
            self.extract_node(ctx, &child, &mut id_gen, &mut result);
        }

        Ok(result)
    }

    fn comment_patterns(&self) -> &[&str] {
        &["#"]
    }

    fn is_public(&self, name: &str) -> bool {
        !name.starts_with('_') || name.starts_with("__")
    }

    fn extract_docstring(&self, node: &TSNode, source: &str) -> Option<String> {
        // Python docstring is the first expression_statement in body containing a string
        if let Some(body) = node.child_by_field_name("body") {
            let mut cursor = body.walk();
            // Only check the first statement (docstring must be first)
            let first_child = body.children(&mut cursor).next();
            if let Some(child) = first_child {
                if child.kind() == "expression_statement" {
                    if let Some(string_node) = child.child(0) {
                        if string_node.kind() == "string" {
                            let text = source.get(string_node.byte_range())?;
                            // Remove quotes
                            let trimmed = text.trim_matches(|c| c == '"' || c == '\'');
                            return Some(trimmed.to_string());
                        }
                    }
                }
            };
        }
        None
    }

    fn is_statement_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            // Assignment statements
            "assignment" | "augmented_assignment" | "expression_statement" |
            // Control flow statements
            "if_statement" | "for_statement" | "while_statement" |
            "try_statement" | "with_statement" | "match_statement" |
            // Other statements
            "return_statement" | "break_statement" | "continue_statement" |
            "raise_statement" | "pass_statement" | "del_statement" |
            "assert_statement" | "global_statement" | "nonlocal_statement" |
            // Import statements
            "import_statement" | "import_from_statement" |
            // Function and class definitions
            "function_definition" | "class_definition" |
            // Decorated definitions
            "decorated_definition"
        )
    }

    fn is_control_flow_node(&self, node: &TSNode) -> bool {
        matches!(
            node.kind(),
            "if_statement"
                | "for_statement"
                | "while_statement"
                | "try_statement"
                | "with_statement"
                | "match_statement"
                | "elif_clause"
                | "else_clause"
                | "except_clause"
                | "finally_clause"
                | "case_clause"
        )
    }

    fn get_control_flow_type(
        &self,
        node: &TSNode,
    ) -> Option<crate::features::parsing::ports::ControlFlowType> {
        use crate::features::parsing::ports::ControlFlowType;
        match node.kind() {
            "if_statement" => Some(ControlFlowType::If),
            "for_statement" | "while_statement" => Some(ControlFlowType::Loop),
            "match_statement" => Some(ControlFlowType::Match),
            "try_statement" => Some(ControlFlowType::Try),
            "yield" => Some(ControlFlowType::Yield),
            "return_statement" => Some(ControlFlowType::Return),
            "break_statement" => Some(ControlFlowType::Break),
            "continue_statement" => Some(ControlFlowType::Continue),
            "raise_statement" => Some(ControlFlowType::Raise),
            _ => None,
        }
    }

    fn get_match_arms<'a>(&self, node: &TSNode<'a>) -> Vec<TSNode<'a>> {
        let mut arms = Vec::new();
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "case_clause" {
                arms.push(child);
            }
        }
        arms
    }

    fn is_chained_condition(&self, node: &TSNode) -> bool {
        node.kind() == "elif_clause"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tree_sitter::Parser;

    fn parse_python(source: &str) -> Tree {
        let mut parser = Parser::new();
        parser
            .set_language(&tree_sitter_python::language())
            .unwrap();
        parser.parse(source, None).unwrap()
    }

    #[test]
    fn test_extract_function() {
        let source = r#"
def hello(name):
    """Say hello."""
    print(f"Hello, {name}!")
"#;
        let tree = parse_python(source);
        let plugin = PythonPlugin::new();
        let mut ctx = ExtractionContext::new(source, "test.py", "test-repo", LanguageId::Python);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        // Should have file + function + parameter
        assert!(result.nodes.len() >= 2);

        let func = result.nodes.iter().find(|n| n.kind == NodeKind::Function);
        assert!(func.is_some());
        assert_eq!(func.unwrap().name, Some("hello".to_string()));
    }

    #[test]
    fn test_extract_class() {
        let source = r#"
class MyClass(BaseClass):
    """A simple class."""

    def method(self, x):
        return x * 2
"#;
        let tree = parse_python(source);
        let plugin = PythonPlugin::new();
        let mut ctx = ExtractionContext::new(source, "test.py", "test-repo", LanguageId::Python);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let class = result.nodes.iter().find(|n| n.kind == NodeKind::Class);
        assert!(class.is_some());
        assert_eq!(class.unwrap().name, Some("MyClass".to_string()));

        let method = result.nodes.iter().find(|n| n.kind == NodeKind::Method);
        assert!(method.is_some());
    }

    #[test]
    #[ignore]
    fn test_extract_try_except() {
        let source = r#"
def test_func():
    try:
        risky_operation()
    except ValueError as e:
        handle_error(e)
    except Exception:
        handle_generic()
    finally:
        cleanup()
"#;
        let tree = parse_python(source);
        let plugin = PythonPlugin::new();
        let mut ctx = ExtractionContext::new(source, "test.py", "test-repo", LanguageId::Python);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        // Should have: file, function, try, 2x catch, finally
        assert!(result.nodes.len() >= 5);

        // Check for Try node
        let try_node = result.nodes.iter().find(|n| n.kind == NodeKind::Try);
        assert!(try_node.is_some(), "Should have Try node");

        // Check for Catch nodes
        let catch_nodes: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Catch)
            .collect();
        assert_eq!(catch_nodes.len(), 2, "Should have 2 Catch nodes");

        // Check first catch has exception type
        let first_catch = &catch_nodes[0];
        if let Some(metadata_str) = &first_catch.metadata {
            if let Ok(metadata) = serde_json::from_str::<serde_json::Value>(metadata_str) {
                if let Some(obj) = metadata.as_object() {
                    let exc_types = obj.get("exception_types");
                    assert!(exc_types.is_some(), "Should have exception_types metadata");
                }
            }
        }

        // Check for Finally node
        let finally_node = result.nodes.iter().find(|n| n.kind == NodeKind::Finally);
        assert!(finally_node.is_some(), "Should have Finally node");

        // Check edges
        let try_id = try_node.unwrap().id.clone();
        let catches_edges: Vec<_> = result
            .edges
            .iter()
            .filter(|e| e.kind == EdgeKind::Catches && e.source_id == try_id)
            .collect();
        assert_eq!(catches_edges.len(), 2, "Should have 2 Catches edges");

        let finally_edges: Vec<_> = result
            .edges
            .iter()
            .filter(|e| e.kind == EdgeKind::Finally && e.source_id == try_id)
            .collect();
        assert_eq!(finally_edges.len(), 1, "Should have 1 Finally edge");
    }

    #[test]
    #[ignore]
    fn test_extract_raise() {
        let source = r#"
def validate(x):
    if x < 0:
        raise ValueError("x must be positive")
    if x > 100:
        raise RuntimeError
"#;
        let tree = parse_python(source);
        let plugin = PythonPlugin::new();
        let mut ctx = ExtractionContext::new(source, "test.py", "test-repo", LanguageId::Python);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        // Should have Raise nodes
        let raise_nodes: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Raise)
            .collect();
        assert_eq!(raise_nodes.len(), 2, "Should have 2 Raise nodes");

        // Check first raise has exception type metadata
        let first_raise = &raise_nodes[0];
        if let Some(metadata_str) = &first_raise.metadata {
            if let Ok(metadata) = serde_json::from_str::<serde_json::Value>(metadata_str) {
                if let Some(obj) = metadata.as_object() {
                    let exc_type = obj.get("exception_type").and_then(|v| v.as_str());
                    assert_eq!(exc_type, Some("ValueError"), "Should have ValueError type");
                }
            }
        }
    }

    #[test]
    fn test_extract_import() {
        let source = r#"
import os
from pathlib import Path
"#;
        let tree = parse_python(source);
        let plugin = PythonPlugin::new();
        let mut ctx = ExtractionContext::new(source, "test.py", "test-repo", LanguageId::Python);

        let result = plugin.extract(&mut ctx, &tree).unwrap();

        let imports: Vec<_> = result
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Import)
            .collect();
        assert_eq!(imports.len(), 2);
    }
}
