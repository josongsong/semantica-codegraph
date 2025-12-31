//! P5: RESOLVE - Symbol Resolution Primitive
//!
//! RFC-071: Mathematical basis - Lambda Calculus (Church 1936)
//!
//! Covers:
//! - Definition lookup
//! - Reference finding
//! - Type lookup
//! - Scope query
//! - Callers/Callees
//!
//! Performance: 5-20x faster than Python (HashMap-based indices)

use std::collections::{HashMap, HashSet};
use serde::{Deserialize, Serialize};

use super::session::AnalysisSession;
use crate::shared::models::{Node, Edge, EdgeKind, NodeKind, Span};

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

/// Resolution query type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ResolveQuery {
    Definition,  // Find where symbol is defined
    References,  // Find all references to symbol
    Type,        // Get type information
    Scope,       // Get enclosing scope
    Callers,     // Functions that call this
    Callees,     // Functions called by this
}

impl ResolveQuery {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "definition" | "def" => ResolveQuery::Definition,
            "references" | "refs" | "usages" => ResolveQuery::References,
            "type" | "typeof" => ResolveQuery::Type,
            "scope" | "enclosing" => ResolveQuery::Scope,
            "callers" | "called_by" => ResolveQuery::Callers,
            "callees" | "calls" => ResolveQuery::Callees,
            _ => ResolveQuery::Definition,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            ResolveQuery::Definition => "definition",
            ResolveQuery::References => "references",
            ResolveQuery::Type => "type",
            ResolveQuery::Scope => "scope",
            ResolveQuery::Callers => "callers",
            ResolveQuery::Callees => "callees",
        }
    }
}

/// Symbol location
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolLocation {
    pub node_id: String,
    pub file_path: String,
    pub start_line: u32,
    pub start_col: u32,
    pub end_line: u32,
    pub end_col: u32,
    pub kind: String,
    pub name: String,
    pub fqn: String,
}

impl SymbolLocation {
    pub fn from_node(node: &Node) -> Self {
        Self {
            node_id: node.id.clone(),
            file_path: node.file_path.clone(),
            start_line: node.span.start_line,
            start_col: node.span.start_col,
            end_line: node.span.end_line,
            end_col: node.span.end_col,
            kind: node.kind.as_str().to_string(),
            name: node.name.clone().unwrap_or_default(),
            fqn: node.fqn.clone(),
        }
    }
}

/// Type information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeInfo {
    pub type_name: String,
    pub type_fqn: String,
    pub is_optional: bool,
    pub is_generic: bool,
    pub type_args: Vec<String>,
}

/// Scope information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScopeInfo {
    pub scope_id: String,
    pub scope_kind: String,  // "function", "class", "module", "block"
    pub scope_name: String,
    pub nesting_level: usize,
    pub parent_scope: Option<String>,
}

/// Resolve result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolveResult {
    pub query: String,
    pub target: String,
    pub success: bool,
    pub definition: Option<SymbolLocation>,
    pub references: Vec<SymbolLocation>,
    pub type_info: Option<TypeInfo>,
    pub scope: Option<ScopeInfo>,
    pub callers: Vec<SymbolLocation>,
    pub callees: Vec<SymbolLocation>,
    pub total_results: usize,
}

impl ResolveResult {
    pub fn new(query: ResolveQuery, target: &str) -> Self {
        Self {
            query: query.as_str().to_string(),
            target: target.to_string(),
            success: false,
            definition: None,
            references: Vec::new(),
            type_info: None,
            scope: None,
            callers: Vec::new(),
            callees: Vec::new(),
            total_results: 0,
        }
    }

    pub fn with_definition(mut self, def: SymbolLocation) -> Self {
        self.definition = Some(def);
        self.success = true;
        self.total_results = 1;
        self
    }

    pub fn with_references(mut self, refs: Vec<SymbolLocation>) -> Self {
        self.total_results = refs.len();
        self.success = !refs.is_empty();
        self.references = refs;
        self
    }

    /// Serialize to msgpack
    pub fn to_msgpack(&self) -> Result<Vec<u8>, String> {
        rmp_serde::to_vec_named(self)
            .map_err(|e| format!("Failed to serialize ResolveResult: {}", e))
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// P5: RESOLVE Implementation
// ═══════════════════════════════════════════════════════════════════════════

/// P5: Symbol Resolution
///
/// Mathematical basis: Lambda calculus (Church 1936)
/// - Free/bound variable resolution
/// - Lexical scoping
/// - Name binding
///
/// # Arguments
/// * `session` - Analysis session with IR
/// * `query` - Type of resolution query
/// * `target` - Target symbol (node ID, name, or FQN)
///
/// # Returns
/// * ResolveResult with query-specific data
pub fn resolve(
    session: &AnalysisSession,
    query: ResolveQuery,
    target: &str,
) -> ResolveResult {
    match query {
        ResolveQuery::Definition => resolve_definition(session, target),
        ResolveQuery::References => resolve_references(session, target),
        ResolveQuery::Type => resolve_type(session, target),
        ResolveQuery::Scope => resolve_scope(session, target),
        ResolveQuery::Callers => resolve_callers(session, target),
        ResolveQuery::Callees => resolve_callees(session, target),
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Query Implementations
// ═══════════════════════════════════════════════════════════════════════════

/// Find definition of a symbol
fn resolve_definition(session: &AnalysisSession, target: &str) -> ResolveResult {
    let mut result = ResolveResult::new(ResolveQuery::Definition, target);

    // First, try direct node ID lookup
    if let Some(node) = session.get_node(target) {
        result = result.with_definition(SymbolLocation::from_node(node));
        return result;
    }

    // Try by name/FQN
    let nodes = session.ir().get_nodes_by_symbol(target);
    if let Some(node) = nodes.first() {
        result = result.with_definition(SymbolLocation::from_node(node));
        return result;
    }

    // Try to find definition via edges (DefUse edge targets are definitions)
    for edge in session.edges() {
        if matches!(edge.kind, EdgeKind::DefUse) && edge.source_id == target {
            if let Some(def_node) = session.get_node(&edge.target_id) {
                result = result.with_definition(SymbolLocation::from_node(def_node));
                return result;
            }
        }
    }

    result
}

/// Find all references to a symbol
fn resolve_references(session: &AnalysisSession, target: &str) -> ResolveResult {
    let mut result = ResolveResult::new(ResolveQuery::References, target);
    let mut refs = Vec::new();
    let mut seen = HashSet::new();

    // Find all nodes that reference the target via edges
    for edge in session.edges() {
        // References point TO the definition
        if edge.target_id == target && !seen.contains(&edge.source_id) {
            if let Some(ref_node) = session.get_node(&edge.source_id) {
                refs.push(SymbolLocation::from_node(ref_node));
                seen.insert(edge.source_id.clone());
            }
        }
    }

    // Also look for nodes with matching name that aren't the definition
    for node in session.nodes() {
        let node_name = node.name.as_deref().unwrap_or("");
        if node_name == target && node.id != target && !seen.contains(&node.id) {
            refs.push(SymbolLocation::from_node(node));
            seen.insert(node.id.clone());
        }
    }

    result = result.with_references(refs);
    result
}

/// Get type information for a symbol
fn resolve_type(session: &AnalysisSession, target: &str) -> ResolveResult {
    let mut result = ResolveResult::new(ResolveQuery::Type, target);

    // Find type annotation edges
    for edge in session.edges() {
        if edge.source_id == target && matches!(edge.kind, EdgeKind::TypeAnnotation) {
            if let Some(type_node) = session.get_node(&edge.target_id) {
                let type_name = type_node.name.clone().unwrap_or_default();
                result.type_info = Some(TypeInfo {
                    type_name: type_name.clone(),
                    type_fqn: type_node.fqn.clone(),
                    is_optional: type_name.starts_with("Optional")
                        || type_name.contains("| None"),
                    is_generic: type_name.contains("["),
                    type_args: extract_type_args(&type_name),
                });
                result.success = true;
                result.total_results = 1;
                break;
            }
        }
    }

    result
}

/// Get enclosing scope for a symbol
fn resolve_scope(session: &AnalysisSession, target: &str) -> ResolveResult {
    let mut result = ResolveResult::new(ResolveQuery::Scope, target);

    // Find parent via Contains edges (reversed)
    let mut current = target.to_string();
    let mut nesting_level = 0;

    loop {
        let mut found_parent = false;

        for edge in session.edges() {
            if matches!(edge.kind, EdgeKind::Contains) && edge.target_id == current {
                if let Some(parent_node) = session.get_node(&edge.source_id) {
                    let scope_kind = match parent_node.kind {
                        NodeKind::Function => "function",
                        NodeKind::Method => "method",
                        NodeKind::Class => "class",
                        NodeKind::Module => "module",
                        _ => "block",
                    };

                    result.scope = Some(ScopeInfo {
                        scope_id: parent_node.id.clone(),
                        scope_kind: scope_kind.to_string(),
                        scope_name: parent_node.name.clone().unwrap_or_default(),
                        nesting_level,
                        parent_scope: None,  // Could recurse for full chain
                    });
                    result.success = true;
                    result.total_results = 1;
                    current = parent_node.id.clone();
                    nesting_level += 1;
                    found_parent = true;
                    break;
                }
            }
        }

        if !found_parent {
            break;
        }
    }

    result
}

/// Find all callers of a function
fn resolve_callers(session: &AnalysisSession, target: &str) -> ResolveResult {
    let mut result = ResolveResult::new(ResolveQuery::Callers, target);
    let mut callers = Vec::new();

    for edge in session.edges() {
        if edge.target_id == target && matches!(edge.kind, EdgeKind::Calls | EdgeKind::Invokes) {
            if let Some(caller_node) = session.get_node(&edge.source_id) {
                callers.push(SymbolLocation::from_node(caller_node));
            }
        }
    }

    result.total_results = callers.len();
    result.success = !callers.is_empty();
    result.callers = callers;
    result
}

/// Find all callees of a function
fn resolve_callees(session: &AnalysisSession, target: &str) -> ResolveResult {
    let mut result = ResolveResult::new(ResolveQuery::Callees, target);
    let mut callees = Vec::new();

    for edge in session.edges() {
        if edge.source_id == target && matches!(edge.kind, EdgeKind::Calls | EdgeKind::Invokes) {
            if let Some(callee_node) = session.get_node(&edge.target_id) {
                callees.push(SymbolLocation::from_node(callee_node));
            }
        }
    }

    result.total_results = callees.len();
    result.success = !callees.is_empty();
    result.callees = callees;
    result
}

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

/// Extract type arguments from generic type string
/// e.g., "List[int]" -> ["int"], "Dict[str, int]" -> ["str", "int"]
fn extract_type_args(type_name: &str) -> Vec<String> {
    if let Some(start) = type_name.find('[') {
        if let Some(end) = type_name.rfind(']') {
            let args_str = &type_name[start + 1..end];
            return args_str
                .split(',')
                .map(|s| s.trim().to_string())
                .collect();
        }
    }
    Vec::new()
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_session() -> AnalysisSession {
        let nodes = vec![
            Node::new(
                "module1".to_string(),
                NodeKind::Module,
                "mymodule".to_string(),
                "mymodule.py".to_string(),
                Span::new(1, 0, 100, 0),
            ).with_name("mymodule"),
            Node::new(
                "class1".to_string(),
                NodeKind::Class,
                "mymodule.MyClass".to_string(),
                "mymodule.py".to_string(),
                Span::new(5, 0, 50, 0),
            ).with_name("MyClass"),
            Node::new(
                "method1".to_string(),
                NodeKind::Method,
                "mymodule.MyClass.process".to_string(),
                "mymodule.py".to_string(),
                Span::new(10, 4, 20, 4),
            ).with_name("process"),
            Node::new(
                "func1".to_string(),
                NodeKind::Function,
                "mymodule.helper".to_string(),
                "mymodule.py".to_string(),
                Span::new(55, 0, 65, 0),
            ).with_name("helper"),
            Node::new(
                "var1".to_string(),
                NodeKind::Variable,
                "mymodule.MyClass.process.x".to_string(),
                "mymodule.py".to_string(),
                Span::new(12, 8, 12, 12),
            ).with_name("x"),
            Node::new(
                "var1_ref".to_string(),
                NodeKind::Variable,
                "mymodule.MyClass.process.x".to_string(),
                "mymodule.py".to_string(),
                Span::new(15, 8, 15, 9),
            ).with_name("x"),
            Node::new(
                "type_int".to_string(),
                NodeKind::Type,
                "builtins.int".to_string(),
                "".to_string(),
                Span::new(0, 0, 0, 0),
            ).with_name("int"),
        ];

        let edges = vec![
            // Module contains class
            Edge::new("module1".to_string(), "class1".to_string(), EdgeKind::Contains),
            // Class contains method
            Edge::new("class1".to_string(), "method1".to_string(), EdgeKind::Contains),
            // Module contains function
            Edge::new("module1".to_string(), "func1".to_string(), EdgeKind::Contains),
            // Method contains variable
            Edge::new("method1".to_string(), "var1".to_string(), EdgeKind::Contains),
            // Variable reference points to definition
            Edge::new("var1_ref".to_string(), "var1".to_string(), EdgeKind::DefUse),
            // Type annotation
            Edge::new("var1".to_string(), "type_int".to_string(), EdgeKind::TypeAnnotation),
            // Method calls function
            Edge::new("method1".to_string(), "func1".to_string(), EdgeKind::Calls),
        ];

        AnalysisSession::new("mymodule.py".to_string(), nodes, edges, None)
    }

    #[test]
    fn test_resolve_definition_by_id() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Definition, "method1");

        assert!(result.success);
        assert!(result.definition.is_some());
        let def = result.definition.unwrap();
        assert_eq!(def.node_id, "method1");
        assert_eq!(def.name, "process");
    }

    #[test]
    fn test_resolve_definition_by_name() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Definition, "helper");

        assert!(result.success);
        assert!(result.definition.is_some());
        let def = result.definition.unwrap();
        assert_eq!(def.name, "helper");
    }

    #[test]
    fn test_resolve_definition_not_found() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Definition, "nonexistent");

        assert!(!result.success);
        assert!(result.definition.is_none());
    }

    #[test]
    fn test_resolve_references() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::References, "var1");

        assert!(result.success);
        assert!(!result.references.is_empty());
        // Should find var1_ref which references var1
        assert!(result.references.iter().any(|r| r.node_id == "var1_ref"));
    }

    #[test]
    fn test_resolve_type() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Type, "var1");

        assert!(result.success);
        assert!(result.type_info.is_some());
        let type_info = result.type_info.unwrap();
        assert_eq!(type_info.type_name, "int");
    }

    #[test]
    fn test_resolve_scope() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Scope, "var1");

        assert!(result.success);
        assert!(result.scope.is_some());
        let scope = result.scope.unwrap();
        assert_eq!(scope.scope_id, "method1");
        assert_eq!(scope.scope_kind, "method");
    }

    #[test]
    fn test_resolve_callers() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Callers, "func1");

        assert!(result.success);
        assert!(!result.callers.is_empty());
        assert!(result.callers.iter().any(|c| c.node_id == "method1"));
    }

    #[test]
    fn test_resolve_callees() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Callees, "method1");

        assert!(result.success);
        assert!(!result.callees.is_empty());
        assert!(result.callees.iter().any(|c| c.node_id == "func1"));
    }

    #[test]
    fn test_resolve_query_from_str() {
        assert_eq!(ResolveQuery::from_str("definition"), ResolveQuery::Definition);
        assert_eq!(ResolveQuery::from_str("def"), ResolveQuery::Definition);
        assert_eq!(ResolveQuery::from_str("references"), ResolveQuery::References);
        assert_eq!(ResolveQuery::from_str("refs"), ResolveQuery::References);
        assert_eq!(ResolveQuery::from_str("type"), ResolveQuery::Type);
        assert_eq!(ResolveQuery::from_str("scope"), ResolveQuery::Scope);
        assert_eq!(ResolveQuery::from_str("callers"), ResolveQuery::Callers);
        assert_eq!(ResolveQuery::from_str("callees"), ResolveQuery::Callees);
    }

    #[test]
    fn test_extract_type_args() {
        assert_eq!(extract_type_args("List[int]"), vec!["int"]);
        assert_eq!(extract_type_args("Dict[str, int]"), vec!["str", "int"]);
        assert_eq!(extract_type_args("Tuple[str, int, bool]"), vec!["str", "int", "bool"]);
        assert!(extract_type_args("int").is_empty());
    }

    #[test]
    fn test_resolve_result_serialization() {
        let session = create_test_session();

        let result = resolve(&session, ResolveQuery::Definition, "method1");

        let bytes = result.to_msgpack().expect("Should serialize");
        assert!(!bytes.is_empty());

        let deserialized: ResolveResult = rmp_serde::from_slice(&bytes)
            .expect("Should deserialize");

        assert_eq!(deserialized.query, "definition");
        assert!(deserialized.success);
    }

    #[test]
    fn test_symbol_location_from_node() {
        let node = Node::new(
            "test".to_string(),
            NodeKind::Function,
            "module.test".to_string(),
            "test.py".to_string(),
            Span::new(10, 4, 20, 0),
        ).with_name("test");

        let loc = SymbolLocation::from_node(&node);

        assert_eq!(loc.node_id, "test");
        assert_eq!(loc.file_path, "test.py");
        assert_eq!(loc.start_line, 10);
        assert_eq!(loc.kind, "Function");  // NodeKind::as_str() returns PascalCase
    }
}
