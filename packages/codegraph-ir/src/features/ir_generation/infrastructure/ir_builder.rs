/*
 * IR Builder - Converts AST to IR (Node + Edge)
 *
 * MATCHES: packages/codegraph-engine/.../generators/python_generator.py
 *
 * Responsibilities:
 * - Generate Node IDs (hash-based, stable)
 * - Build FQNs (Fully Qualified Names)
 * - Create Nodes with complete metadata
 * - Create Edges (CONTAINS, CALLS, READS, WRITES, INHERITS)
 * - Manage scope stack (module → class → function)
 *
 * PRODUCTION REQUIREMENTS:
 * - No fake data
 * - All fields validated
 * - Type safety enforced
 * - Error handling complete
 */

use crate::features::type_resolution::domain::type_entity::TypeEntity;
use crate::features::type_resolution::infrastructure::type_resolver::TypeResolver;
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};
use sha2::{Digest, Sha256};

/// Scope context for FQN building
#[derive(Debug, Clone)]
struct ScopeFrame {
    kind: ScopeKind,
    name: String,
    node_id: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ScopeKind {
    Module,
    Class,
    Function,
}

/// IR Builder - Stateful builder for IR generation
pub struct IRBuilder {
    // Context
    repo_id: String,
    file_path: String,
    language: String,

    // Scope stack
    scope_stack: Vec<ScopeFrame>,

    // Type resolution
    type_resolver: TypeResolver,

    // Output
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    type_entities: Vec<TypeEntity>,

    // Counters for unique IDs
    edge_counter: usize,
}

impl IRBuilder {
    /// Create new IR builder
    ///
    /// # Arguments
    /// * `repo_id` - Repository ID
    /// * `file_path` - File path (relative to repo root)
    /// * `language` - Language (e.g., "python")
    /// * `module_path` - Module FQN (e.g., "myapp.services.user")
    pub fn new(repo_id: String, file_path: String, language: String, module_path: String) -> Self {
        let type_resolver = TypeResolver::new(repo_id.clone());

        let mut builder = Self {
            repo_id,
            file_path: file_path.clone(),
            language,
            scope_stack: Vec::new(),
            type_resolver,
            nodes: Vec::new(),
            edges: Vec::new(),
            type_entities: Vec::new(),
            edge_counter: 0,
        };

        // Initialize with module scope
        builder.push_scope(ScopeKind::Module, module_path.clone());

        builder
    }

    /// Push new scope
    fn push_scope(&mut self, kind: ScopeKind, name: String) {
        self.scope_stack.push(ScopeFrame {
            kind,
            name,
            node_id: None,
        });
    }

    /// Pop scope
    fn pop_scope(&mut self) {
        self.scope_stack.pop();
    }

    /// Set node ID for current scope
    fn set_current_scope_node_id(&mut self, node_id: String) {
        if let Some(frame) = self.scope_stack.last_mut() {
            frame.node_id = Some(node_id);
        }
    }

    /// Get current parent node ID
    fn current_parent_id(&self) -> Option<String> {
        self.scope_stack.last()?.node_id.clone()
    }

    /// Build FQN from scope stack
    fn build_fqn(&self, name: &str) -> String {
        let mut parts: Vec<&str> = self.scope_stack.iter().map(|f| f.name.as_str()).collect();
        parts.push(name);
        parts.join(".")
    }

    /// Get current module path
    fn module_path(&self) -> String {
        self.scope_stack
            .first()
            .map(|f| f.name.clone())
            .unwrap_or_default()
    }

    /// Generate Node ID (hash-based, stable)
    ///
    /// MATCHES: generate_python_node_id() in id_utils.py
    ///
    /// Format: {kind}:{repo_id}:{file_path}:{fqn}
    fn generate_node_id(&self, kind: NodeKind, fqn: &str) -> String {
        let key = format!(
            "{}:{}:{}:{}",
            kind.as_str(),
            self.repo_id,
            self.file_path,
            fqn
        );

        let mut hasher = Sha256::new();
        hasher.update(key.as_bytes());
        let hash = hasher.finalize();

        // Take first 16 bytes (32 hex chars)
        format!("{:x}", hash)[..32].to_string()
    }

    /// Generate Edge ID
    fn generate_edge_id(&mut self, kind: EdgeKind, source_id: &str, target_id: &str) -> String {
        self.edge_counter += 1;
        format!(
            "edge:{}:{}→{}@{}",
            kind.as_str().to_lowercase(),
            source_id,
            target_id,
            self.edge_counter
        )
    }

    /// Generate content hash (SHA256)
    fn generate_content_hash(&self, content: &str) -> String {
        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// Add CONTAINS edge
    pub fn add_contains_edge(&mut self, parent_id: String, child_id: String, span: Span) {
        self.edges.push(Edge {
            source_id: parent_id,
            target_id: child_id,
            kind: EdgeKind::Contains,
            span: Some(span),
            metadata: None,
            attrs: None,
        });
    }

    /// Add CALLS edge
    pub fn add_calls_edge(&mut self, caller_id: String, callee_fqn: String, span: Span) {
        self.edges.push(Edge {
            source_id: caller_id,
            target_id: callee_fqn,
            kind: EdgeKind::Calls,
            span: Some(span),
            metadata: None,
            attrs: None,
        });
    }

    /// Add READS edge
    pub fn add_reads_edge(&mut self, reader_id: String, variable_fqn: String, span: Span) {
        self.edges.push(Edge {
            source_id: reader_id,
            target_id: variable_fqn,
            kind: EdgeKind::Reads,
            span: Some(span),
            metadata: None,
            attrs: None,
        });
    }

    /// Add WRITES edge
    pub fn add_writes_edge(&mut self, writer_id: String, variable_fqn: String, span: Span) {
        self.edges.push(Edge {
            source_id: writer_id,
            target_id: variable_fqn,
            kind: EdgeKind::Writes,
            span: Some(span),
            metadata: None,
            attrs: None,
        });
    }

    /// Add INHERITS edge
    pub fn add_inherits_edge(&mut self, child_id: String, parent_fqn: String, span: Span) {
        self.edges.push(Edge {
            source_id: child_id,
            target_id: parent_fqn,
            kind: EdgeKind::Inherits,
            span: Some(span),
            metadata: None,
            attrs: None,
        });
    }

    /// Add IMPORTS edge (RFC-062: SOTA cross-file resolution)
    ///
    /// Creates an edge from the importing context (module/function) to the imported symbol.
    /// This enables:
    /// - Cross-file dependency tracking
    /// - Import resolution in GlobalContext
    /// - File dependency graph construction
    ///
    /// # Arguments
    /// * `importer_id` - Node ID of the importing context (module or function)
    /// * `imported_fqn` - FQN of the imported symbol (e.g., "os.path.join")
    /// * `span` - Source location of the import statement
    /// * `alias` - Optional alias (e.g., "import numpy as np" → alias = "np")
    /// * `is_from_import` - True for "from x import y" style
    pub fn add_imports_edge(
        &mut self,
        importer_id: String,
        imported_fqn: String,
        span: Span,
        alias: Option<String>,
        _is_from_import: bool,
    ) {
        use crate::shared::models::EdgeMetadata;

        self.edges.push(Edge {
            source_id: importer_id,
            target_id: imported_fqn,
            kind: EdgeKind::Imports,
            span: Some(span),
            metadata: Some(EdgeMetadata {
                alias,
                ..Default::default()
            }),
            attrs: None,
        });
    }

    /// Create Import Node (RFC-062: SOTA import tracking)
    ///
    /// Creates a node representing an import statement.
    /// Used for:
    /// - Import occurrence tracking
    /// - Symbol resolution
    /// - Dependency analysis
    ///
    /// # Arguments
    /// * `module_name` - Imported module (e.g., "os.path")
    /// * `imported_names` - Specific names imported (e.g., ["join", "exists"])
    /// * `alias` - Module alias if any
    /// * `span` - Source location
    /// * `is_from_import` - True for "from x import y" style
    pub fn create_import_node(
        &mut self,
        module_name: String,
        imported_names: Vec<(String, Option<String>)>, // (name, alias)
        alias: Option<String>,
        span: Span,
        is_from_import: bool,
    ) -> Vec<String> {
        // For module-level imports, use module path as importer
        let parent_id = self
            .current_parent_id()
            .or_else(|| Some(self.module_path()));
        let mut created_ids = Vec::new();

        if is_from_import {
            // "from module import name1, name2 as alias2"
            for (name, name_alias) in imported_names {
                let fqn = format!("{}.{}", module_name, name);
                let node_id = self.generate_node_id(NodeKind::Import, &fqn);

                let node = Node::new(
                    node_id.clone(),
                    NodeKind::Import,
                    fqn.clone(),
                    self.file_path.clone(),
                    span,
                )
                .with_language(self.language.clone())
                .with_name(name_alias.clone().unwrap_or(name.clone()))
                .with_module_path(self.module_path());

                let mut node = node;
                node.parent_id = parent_id.clone();

                self.nodes.push(node);

                // Add IMPORTS edge
                if let Some(ref p_id) = parent_id {
                    self.add_imports_edge(p_id.clone(), fqn, span, name_alias, true);
                }

                created_ids.push(node_id);
            }
        } else {
            // "import module" or "import module as alias"
            let fqn = module_name.clone();
            let node_id = self.generate_node_id(NodeKind::Import, &fqn);

            let node = Node::new(
                node_id.clone(),
                NodeKind::Import,
                fqn.clone(),
                self.file_path.clone(),
                span,
            )
            .with_language(self.language.clone())
            .with_name(alias.clone().unwrap_or(module_name.clone()))
            .with_module_path(self.module_path());

            let mut node = node;
            node.parent_id = parent_id.clone();

            self.nodes.push(node);

            // Add IMPORTS edge
            if let Some(ref p_id) = parent_id {
                self.add_imports_edge(p_id.clone(), fqn, span, alias, false);
            }

            created_ids.push(node_id);
        }

        created_ids
    }

    /// Create Function/Method Node
    ///
    /// MATCHES: FunctionAnalyzer.process_function()
    pub fn create_function_node(
        &mut self,
        name: String,
        span: Span,
        body_span: Option<Span>,
        is_method: bool,
        docstring: Option<String>,
        source_text: &str,
        return_type_annotation: Option<String>,
    ) -> Result<String, String> {
        // Validate inputs
        if name.is_empty() {
            return Err("Function name cannot be empty".to_string());
        }

        // Build FQN
        let fqn = self.build_fqn(&name);

        // Determine kind
        let kind = if is_method {
            NodeKind::Method
        } else {
            NodeKind::Function
        };

        // Generate node ID
        let node_id = self.generate_node_id(kind, &fqn);

        // Generate content hash
        let content_hash = self.generate_content_hash(source_text);

        // Get parent ID
        let parent_id = self.current_parent_id();

        // Resolve return type for type tracking
        let return_type = return_type_annotation.clone();

        // Create node using builder pattern
        let mut node = Node::new(
            node_id.clone(),
            kind,
            fqn.clone(),
            self.file_path.clone(),
            span,
        )
        .with_language(self.language.clone())
        .with_name(name.clone())
        .with_module_path(self.module_path());

        node.content_hash = Some(content_hash);
        node.parent_id = parent_id.clone();
        node.body_span = body_span;
        node.docstring = docstring;
        node.return_type = return_type;

        self.nodes.push(node);

        // Add CONTAINS edge from parent
        if let Some(parent) = parent_id {
            self.add_contains_edge(parent, node_id.clone(), span);
        }

        // Push function scope
        self.push_scope(ScopeKind::Function, name);
        self.set_current_scope_node_id(node_id.clone());

        Ok(node_id)
    }

    /// Create Class Node
    ///
    /// MATCHES: ClassAnalyzer.process_class()
    pub fn create_class_node(
        &mut self,
        name: String,
        span: Span,
        body_span: Option<Span>,
        base_classes: Vec<String>,
        docstring: Option<String>,
        source_text: &str,
    ) -> Result<String, String> {
        // Validate inputs
        if name.is_empty() {
            return Err("Class name cannot be empty".to_string());
        }

        // Build FQN
        let fqn = self.build_fqn(&name);

        // Generate node ID
        let node_id = self.generate_node_id(NodeKind::Class, &fqn);

        // Generate content hash
        let content_hash = self.generate_content_hash(source_text);

        // Get parent ID
        let parent_id = self.current_parent_id();

        // Create node using builder pattern
        let mut node = Node::new(
            node_id.clone(),
            NodeKind::Class,
            fqn.clone(),
            self.file_path.clone(),
            span,
        )
        .with_language(self.language.clone())
        .with_name(name.clone())
        .with_module_path(self.module_path());

        node.content_hash = Some(content_hash);
        node.parent_id = parent_id.clone();
        node.body_span = body_span;
        node.docstring = docstring;
        node.base_classes = if base_classes.is_empty() {
            None
        } else {
            Some(base_classes.clone())
        };

        self.nodes.push(node);

        // Add CONTAINS edge from parent
        if let Some(parent) = parent_id {
            self.add_contains_edge(parent, node_id.clone(), span);
        }

        // Add INHERITS edges
        for base_class in base_classes {
            // Resolve base class FQN (simplified - full resolution needs type system)
            let base_fqn = if base_class.contains('.') {
                base_class
            } else {
                // Assume same module for simple names
                format!("{}.{}", self.module_path(), base_class)
            };

            self.add_inherits_edge(node_id.clone(), base_fqn, span);
        }

        // Push class scope
        self.push_scope(ScopeKind::Class, name);
        self.set_current_scope_node_id(node_id.clone());

        Ok(node_id)
    }

    /// Finish function/class processing (pop scope)
    pub fn finish_scope(&mut self) {
        self.pop_scope();
    }

    /// Get all nodes
    pub fn nodes(&self) -> &[Node] {
        &self.nodes
    }

    /// Get all edges
    pub fn edges(&self) -> &[Edge] {
        &self.edges
    }

    /// Create Variable Node
    ///
    /// MATCHES: PythonVariableAnalyzer._process_assignment()
    pub fn create_variable_node(
        &mut self,
        name: String,
        span: Span,
        parent_id: String,
        type_annotation: Option<String>,
    ) -> Result<String, String> {
        // Validate
        if name.is_empty() {
            return Err("Variable name cannot be empty".to_string());
        }

        // Build FQN (parent.variable)
        let fqn = format!(
            "{}.{}",
            self.scope_stack
                .last()
                .map(|f| f.name.as_str())
                .unwrap_or(""),
            name
        );

        // Generate node ID
        let node_id = self.generate_node_id(NodeKind::Variable, &fqn);

        // Create node using builder pattern
        let mut node = Node::new(
            node_id.clone(),
            NodeKind::Variable,
            fqn,
            self.file_path.clone(),
            span,
        )
        .with_language(self.language.clone())
        .with_name(name)
        .with_module_path(self.module_path())
        .with_parent(parent_id.clone());

        node.type_annotation = type_annotation;

        self.nodes.push(node);

        // Add CONTAINS edge from parent
        self.add_contains_edge(parent_id, node_id.clone(), span);

        Ok(node_id)
    }

    /// Consume builder and return (nodes, edges)
    pub fn build(self) -> (Vec<Node>, Vec<Edge>, Vec<TypeEntity>) {
        (self.nodes, self.edges, self.type_entities)
    }

    /// Resolve type annotation and store TypeEntity
    pub fn resolve_type(&mut self, type_annotation: &str) -> Option<String> {
        if type_annotation.is_empty() {
            return None;
        }

        let type_entity = self.type_resolver.resolve_type(type_annotation);
        let type_id = type_entity.id.clone();
        self.type_entities.push(type_entity);
        Some(type_id)
    }

    /// Register local class for type resolution
    pub fn register_local_class(&mut self, name: String, node_id: String) {
        self.type_resolver.register_local_class(name, node_id);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fqn_building() {
        let mut builder = IRBuilder::new(
            "test-repo".to_string(),
            "src/main.py".to_string(),
            "python".to_string(),
            "myapp.main".to_string(),
        );

        // Module level
        assert_eq!(builder.build_fqn("func1"), "myapp.main.func1");

        // Class level
        builder.push_scope(ScopeKind::Class, "MyClass".to_string());
        assert_eq!(builder.build_fqn("method1"), "myapp.main.MyClass.method1");

        // Function level
        builder.push_scope(ScopeKind::Function, "method1".to_string());
        assert_eq!(builder.build_fqn("var1"), "myapp.main.MyClass.method1.var1");
    }

    #[test]
    fn test_node_id_stability() {
        let builder1 = IRBuilder::new(
            "repo1".to_string(),
            "file1.py".to_string(),
            "python".to_string(),
            "mod1".to_string(),
        );

        let builder2 = IRBuilder::new(
            "repo1".to_string(),
            "file1.py".to_string(),
            "python".to_string(),
            "mod1".to_string(),
        );

        let id1 = builder1.generate_node_id(NodeKind::Function, "mod1.func1");
        let id2 = builder2.generate_node_id(NodeKind::Function, "mod1.func1");

        assert_eq!(id1, id2, "Node IDs should be stable");
    }

    #[test]
    fn test_function_node_creation() {
        let mut builder = IRBuilder::new(
            "test-repo".to_string(),
            "src/main.py".to_string(),
            "python".to_string(),
            "myapp.main".to_string(),
        );

        let span = Span::new(10, 0, 15, 0);
        let result = builder.create_function_node(
            "my_function".to_string(),
            span,
            Some(Span::new(11, 4, 15, 0)),
            false,
            Some("My docstring".to_string()),
            "def my_function(): pass",
            None, // return_type
        );

        assert!(result.is_ok());

        let nodes = builder.nodes();
        assert_eq!(nodes.len(), 1);

        let node = &nodes[0];
        assert_eq!(node.kind, NodeKind::Function);
        assert_eq!(node.name, Some("my_function".to_string()));
        assert_eq!(node.fqn, "myapp.main.my_function");
        assert_eq!(node.docstring, Some("My docstring".to_string()));
    }

    #[test]
    fn test_class_node_with_inheritance() {
        let mut builder = IRBuilder::new(
            "test-repo".to_string(),
            "src/main.py".to_string(),
            "python".to_string(),
            "myapp.main".to_string(),
        );

        let span = Span::new(5, 0, 10, 0);
        let base_classes = vec!["BaseClass".to_string(), "Mixin".to_string()];

        let result = builder.create_class_node(
            "MyClass".to_string(),
            span,
            Some(Span::new(6, 4, 10, 0)),
            base_classes,
            Some("Class docstring".to_string()),
            "class MyClass(BaseClass, Mixin): pass",
        );

        assert!(result.is_ok());

        let nodes = builder.nodes();
        assert_eq!(nodes.len(), 1);

        let node = &nodes[0];
        assert_eq!(node.kind, NodeKind::Class);
        assert_eq!(node.name, Some("MyClass".to_string()));

        // Check INHERITS edges
        let edges = builder.edges();
        let inherits_edges: Vec<_> = edges
            .iter()
            .filter(|e| e.kind == EdgeKind::Inherits)
            .collect();
        assert_eq!(inherits_edges.len(), 2);
    }

    #[test]
    fn test_empty_name_validation() {
        let mut builder = IRBuilder::new(
            "test-repo".to_string(),
            "src/main.py".to_string(),
            "python".to_string(),
            "myapp.main".to_string(),
        );

        let span = Span::new(1, 0, 2, 0);
        let result = builder.create_function_node(
            "".to_string(),
            span,
            None,
            false,
            None,
            "",
            None, // return_type
        );

        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "Function name cannot be empty");
    }
}
