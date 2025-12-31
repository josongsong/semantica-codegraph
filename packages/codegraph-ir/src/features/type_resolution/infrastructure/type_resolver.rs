/*
 * Type Resolver - Local type inference
 *
 * MATCHES: TypeResolver in typing/resolver.py
 *
 * PRODUCTION GRADE:
 * - No Pyright dependency
 * - Local resolution only
 * - BUILTIN/LOCAL/MODULE/PROJECT/EXTERNAL
 * - Generic parameter parsing
 *
 * SOTA INTEGRATION:
 * - Hindley-Milner constraint-based inference via ConstraintSolver
 * - InferTypeResolver for advanced type inference
 * - Supports type variable propagation
 *
 * NO FAKE DATA!
 */

use crate::features::type_resolution::domain::{TypeEntity, TypeFlavor, TypeResolutionLevel};
use lazy_static::lazy_static;
use std::collections::{HashMap, HashSet};

// SOTA: Import constraint solver for type inference
use super::constraint_solver::{
    Constraint, ConstraintSolver, InferType, SolverError, Substitution,
};
use crate::features::type_resolution::domain::type_system::Type;

lazy_static! {
    /// Python builtin types (matches Python BUILTIN_TYPES)
    static ref BUILTIN_TYPES: HashSet<&'static str> = {
        let mut set = HashSet::new();
        // Primitives
        set.insert("int");
        set.insert("str");
        set.insert("float");
        set.insert("bool");
        set.insert("bytes");
        set.insert("None");
        // Collections
        set.insert("list");
        set.insert("List");
        set.insert("dict");
        set.insert("Dict");
        set.insert("set");
        set.insert("Set");
        set.insert("tuple");
        set.insert("Tuple");
        // Typing
        set.insert("Any");
        set.insert("Optional");
        set.insert("Union");
        set.insert("Callable");
        set.insert("Type");
        set
    };

    /// Stdlib types (matches Python STDLIB_TYPES)
    static ref STDLIB_TYPES: HashSet<&'static str> = {
        let mut set = HashSet::new();
        set.insert("Path");
        set.insert("datetime");
        set.insert("UUID");
        set.insert("Decimal");
        set.insert("Logger");
        set
    };
}

/// Type Resolver with SOTA Hindley-Milner Inference
///
/// Combines simple type resolution (builtin/local/module/project/external)
/// with SOTA constraint-based type inference for complex cases.
pub struct TypeResolver {
    repo_id: String,
    local_classes: HashMap<String, String>, // name → node_id
    module_types: HashMap<String, String>,  // name → node_id
    project_types: HashMap<String, String>, // fqn → node_id

    // SOTA: Constraint solver for Hindley-Milner inference
    constraint_solver: ConstraintSolver,
    infer_cache: HashMap<String, InferType>, // Cached inference results
}

impl TypeResolver {
    pub fn new(repo_id: String) -> Self {
        Self {
            repo_id,
            local_classes: HashMap::new(),
            module_types: HashMap::new(),
            project_types: HashMap::new(),
            constraint_solver: ConstraintSolver::new(),
            infer_cache: HashMap::new(),
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // SOTA: Hindley-Milner Type Inference API
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Create a fresh type variable for inference
    pub fn fresh_type_var(&mut self) -> InferType {
        let var_id = self.constraint_solver.fresh_var();
        InferType::Variable(var_id)
    }

    /// Add equality constraint: T1 = T2
    pub fn add_equality_constraint(&mut self, t1: InferType, t2: InferType) {
        self.constraint_solver
            .add_constraint(Constraint::Equality(t1, t2));
    }

    /// Add callable constraint: T is a function (params) -> return
    pub fn add_callable_constraint(
        &mut self,
        t: InferType,
        params: Vec<InferType>,
        ret: InferType,
    ) {
        self.constraint_solver
            .add_constraint(Constraint::Callable(t, params, ret));
    }

    /// Add generic constraint: T = Base[Params]
    pub fn add_generic_constraint(&mut self, t: InferType, base: String, params: Vec<InferType>) {
        self.constraint_solver
            .add_constraint(Constraint::Generic(t, base, params));
    }

    /// Solve all constraints and get substitution
    ///
    /// Returns the substitution map if successful.
    /// After solving, you can use `apply_substitution` to get concrete types.
    pub fn solve_constraints(&mut self) -> Result<Substitution, SolverError> {
        self.constraint_solver.solve()
    }

    /// Apply substitution to an inference type and get concrete type
    pub fn apply_substitution(&self, infer_type: &InferType, subst: &Substitution) -> Option<Type> {
        infer_type.to_concrete(subst)
    }

    /// Convert raw type string to InferType
    pub fn to_infer_type(&mut self, raw_type: &str) -> InferType {
        // Check cache first
        if let Some(cached) = self.infer_cache.get(raw_type) {
            return cached.clone();
        }

        let normalized = raw_type.trim();
        let infer_type = self.parse_to_infer_type(normalized);

        // Cache result
        self.infer_cache
            .insert(raw_type.to_string(), infer_type.clone());
        infer_type
    }

    /// Parse type string into InferType
    fn parse_to_infer_type(&mut self, type_str: &str) -> InferType {
        let normalized = type_str.trim();

        // Empty or whitespace → fresh variable
        if normalized.is_empty() {
            return self.fresh_type_var();
        }

        // Check for generics
        if let Some(open_bracket) = normalized.find('[') {
            if let Some(close_bracket) = normalized.rfind(']') {
                let base = normalized[..open_bracket].trim();
                let params_str = &normalized[open_bracket + 1..close_bracket];
                let param_strs = self.split_params(params_str);

                // Recursively parse parameters
                let params: Vec<InferType> = param_strs
                    .iter()
                    .map(|p| self.parse_to_infer_type(p))
                    .collect();

                // Check if base is Callable
                if base == "Callable" && params.len() >= 2 {
                    // Callable[[params], return]
                    let ret = params
                        .last()
                        .cloned()
                        .unwrap_or_else(|| self.fresh_type_var());
                    let fn_params = if params.len() > 1 {
                        params[..params.len() - 1].to_vec()
                    } else {
                        Vec::new()
                    };
                    return InferType::CallableInfer {
                        params: fn_params,
                        return_type: Box::new(ret),
                    };
                }

                // Check if base is Union
                if base == "Union" {
                    return InferType::UnionInfer(params);
                }

                // Generic type
                return InferType::GenericInfer {
                    base: base.to_string(),
                    params,
                };
            }
        }

        // Check for Union syntax (T | U)
        if normalized.contains(" | ") {
            let parts: Vec<&str> = normalized.split(" | ").collect();
            let union_types: Vec<InferType> = parts
                .iter()
                .map(|p| self.parse_to_infer_type(p.trim()))
                .collect();
            return InferType::UnionInfer(union_types);
        }

        // Simple type → concrete
        InferType::Concrete(Type::simple(normalized))
    }

    /// Reset constraint solver for new inference session
    pub fn reset_inference(&mut self) {
        self.constraint_solver = ConstraintSolver::new();
        self.infer_cache.clear();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Original API (preserved for backward compatibility)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    pub fn register_local_class(&mut self, name: String, node_id: String) {
        self.local_classes.insert(name, node_id);
    }

    pub fn register_module_type(&mut self, name: String, node_id: String) {
        self.module_types.insert(name, node_id);
    }

    pub fn register_project_type(&mut self, fqn: String, node_id: String) {
        self.project_types.insert(fqn.clone(), node_id.clone());

        // Also register by simple name
        if let Some(simple) = fqn.split('.').next_back() {
            self.project_types
                .entry(simple.to_string())
                .or_insert(node_id);
        }
    }

    /// Resolve type annotation
    ///
    /// PRODUCTION: No fake data, accurate classification
    pub fn resolve_type(&self, raw_type: &str) -> TypeEntity {
        let normalized = raw_type.trim();

        // Generate ID
        let type_id = self.generate_type_id(normalized);

        // Classify
        let (flavor, level, target) = self.classify_type(normalized);

        // Check nullable
        let is_nullable = self.is_nullable(normalized);

        // Parse generics
        let generic_params = self.extract_generic_params(normalized);

        TypeEntity {
            id: type_id,
            raw: normalized.to_string(),
            flavor,
            is_nullable,
            resolution_level: level,
            resolved_target: target,
            generic_param_ids: generic_params,
        }
    }

    fn generate_type_id(&self, type_str: &str) -> String {
        use sha2::{Digest, Sha256};

        let key = format!("type:{}:{}", self.repo_id, type_str);
        let mut hasher = Sha256::new();
        hasher.update(key.as_bytes());
        format!("{:x}", hasher.finalize())[..32].to_string()
    }

    fn classify_type(&self, type_str: &str) -> (TypeFlavor, TypeResolutionLevel, Option<String>) {
        // Extract base type (before '[')
        let base_type = type_str.split('[').next().unwrap_or(type_str).trim();

        // 1. Builtin
        if BUILTIN_TYPES.contains(base_type) {
            return (TypeFlavor::Builtin, TypeResolutionLevel::Builtin, None);
        }

        // 2. Local
        if let Some(node_id) = self.local_classes.get(base_type) {
            return (
                TypeFlavor::User,
                TypeResolutionLevel::Local,
                Some(node_id.clone()),
            );
        }

        // 3. Module
        if let Some(node_id) = self.module_types.get(base_type) {
            return (
                TypeFlavor::User,
                TypeResolutionLevel::Module,
                Some(node_id.clone()),
            );
        }

        // 4. Project
        if let Some(node_id) = self.project_types.get(base_type) {
            return (
                TypeFlavor::User,
                TypeResolutionLevel::Project,
                Some(node_id.clone()),
            );
        }

        // 5. Stdlib
        if STDLIB_TYPES.contains(base_type) {
            return (TypeFlavor::External, TypeResolutionLevel::External, None);
        }

        // 6. Unresolved
        (TypeFlavor::External, TypeResolutionLevel::Raw, None)
    }

    fn is_nullable(&self, type_str: &str) -> bool {
        type_str.contains("Optional[") || type_str.contains("| None") || type_str.contains("None |")
    }

    fn extract_generic_params(&self, type_str: &str) -> Vec<String> {
        if !type_str.contains('[') {
            return Vec::new();
        }

        // Find content between '[' and ']'
        let start = match type_str.find('[') {
            Some(i) => i,
            None => return Vec::new(),
        };

        let end = match type_str.rfind(']') {
            Some(i) => i,
            None => return Vec::new(),
        };

        if start >= end {
            return Vec::new();
        }

        let params_str = &type_str[start + 1..end];

        // Split by comma (respecting nested brackets)
        let params = self.split_params(params_str);

        // Recursively resolve
        params.iter().map(|p| self.resolve_type(p).id).collect()
    }

    fn split_params(&self, params_str: &str) -> Vec<String> {
        let mut params = Vec::new();
        let mut current = String::new();
        let mut depth = 0;

        for ch in params_str.chars() {
            match ch {
                '[' => {
                    depth += 1;
                    current.push(ch);
                }
                ']' => {
                    depth -= 1;
                    current.push(ch);
                }
                ',' if depth == 0 => {
                    let param = current.trim().to_string();
                    if !param.is_empty() {
                        params.push(param);
                    }
                    current.clear();
                }
                _ => current.push(ch),
            }
        }

        let param = current.trim().to_string();
        if !param.is_empty() {
            params.push(param);
        }

        params
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builtin_types() {
        let resolver = TypeResolver::new("test".to_string());

        let int_type = resolver.resolve_type("int");
        assert_eq!(int_type.flavor, TypeFlavor::Builtin);
        assert_eq!(int_type.resolution_level, TypeResolutionLevel::Builtin);

        let str_type = resolver.resolve_type("str");
        assert_eq!(str_type.flavor, TypeFlavor::Builtin);
    }

    #[test]
    fn test_local_class() {
        let mut resolver = TypeResolver::new("test".to_string());
        resolver.register_local_class("MyClass".to_string(), "node123".to_string());

        let my_type = resolver.resolve_type("MyClass");
        assert_eq!(my_type.flavor, TypeFlavor::User);
        assert_eq!(my_type.resolution_level, TypeResolutionLevel::Local);
        assert_eq!(my_type.resolved_target, Some("node123".to_string()));
    }

    #[test]
    fn test_generic_params() {
        let resolver = TypeResolver::new("test".to_string());

        let list_str = resolver.resolve_type("List[str]");
        assert!(!list_str.generic_param_ids.is_empty());
        assert_eq!(list_str.generic_param_ids.len(), 1);
    }

    #[test]
    fn test_nested_generics() {
        let resolver = TypeResolver::new("test".to_string());

        let dict_type = resolver.resolve_type("Dict[str, List[int]]");
        assert!(!dict_type.generic_param_ids.is_empty());
        assert_eq!(dict_type.generic_param_ids.len(), 2);
    }

    #[test]
    fn test_nullable() {
        let resolver = TypeResolver::new("test".to_string());

        let opt_int = resolver.resolve_type("Optional[int]");
        assert!(opt_int.is_nullable);

        let union_none = resolver.resolve_type("int | None");
        assert!(union_none.is_nullable);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // EDGE CASES - SOTA Level Coverage
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    #[test]
    fn test_empty_and_whitespace() {
        let resolver = TypeResolver::new("test".to_string());

        // Empty string
        let empty = resolver.resolve_type("");
        assert_eq!(empty.raw, "");
        assert_eq!(empty.resolution_level, TypeResolutionLevel::Raw);

        // Whitespace only
        let ws = resolver.resolve_type("   ");
        assert_eq!(ws.raw, "");

        // Whitespace around type
        let padded = resolver.resolve_type("  int  ");
        assert_eq!(padded.raw, "int");
        assert_eq!(padded.flavor, TypeFlavor::Builtin);
    }

    #[test]
    fn test_malformed_generics() {
        let resolver = TypeResolver::new("test".to_string());

        // Unclosed bracket
        let unclosed = resolver.resolve_type("List[str");
        assert!(unclosed.generic_param_ids.is_empty());

        // No closing bracket
        let no_close = resolver.resolve_type("Dict[str, int");
        assert!(no_close.generic_param_ids.is_empty());

        // Empty generics
        let empty_gen = resolver.resolve_type("List[]");
        assert!(empty_gen.generic_param_ids.is_empty());

        // Mismatched brackets
        let mismatch = resolver.resolve_type("List]str[");
        assert_eq!(mismatch.resolution_level, TypeResolutionLevel::Raw);
    }

    #[test]
    fn test_complex_nested_generics() {
        let resolver = TypeResolver::new("test".to_string());

        // Triple nesting
        let triple = resolver.resolve_type("Dict[str, List[Tuple[int, str]]]");
        assert!(!triple.generic_param_ids.is_empty());
        assert_eq!(triple.generic_param_ids.len(), 2);

        // Multiple params with nesting
        let multi = resolver.resolve_type("Callable[[int, str], Dict[str, List[int]]]");
        assert!(!multi.generic_param_ids.is_empty());

        // Union with generics
        let union_gen = resolver.resolve_type("Union[List[int], Dict[str, str]]");
        assert!(!union_gen.generic_param_ids.is_empty());
    }

    #[test]
    fn test_resolution_priority() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Register same name at different levels
        resolver.register_local_class("MyType".to_string(), "local123".to_string());
        resolver.register_module_type("MyType".to_string(), "module456".to_string());
        resolver.register_project_type("pkg.MyType".to_string(), "project789".to_string());

        // Local should win
        let resolved = resolver.resolve_type("MyType");
        assert_eq!(resolved.resolution_level, TypeResolutionLevel::Local);
        assert_eq!(resolved.resolved_target, Some("local123".to_string()));
    }

    #[test]
    fn test_fqn_resolution() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Register FQN
        resolver.register_project_type("mypackage.MyClass".to_string(), "node999".to_string());

        // Should resolve by simple name
        let simple = resolver.resolve_type("MyClass");
        assert_eq!(simple.resolution_level, TypeResolutionLevel::Project);
        assert_eq!(simple.resolved_target, Some("node999".to_string()));

        // Should also resolve by FQN
        let fqn = resolver.resolve_type("mypackage.MyClass");
        assert_eq!(fqn.resolution_level, TypeResolutionLevel::Project);
    }

    #[test]
    fn test_stdlib_types() {
        let resolver = TypeResolver::new("test".to_string());

        let path = resolver.resolve_type("Path");
        assert_eq!(path.flavor, TypeFlavor::External);
        assert_eq!(path.resolution_level, TypeResolutionLevel::External);

        let datetime = resolver.resolve_type("datetime");
        assert_eq!(datetime.flavor, TypeFlavor::External);

        let uuid = resolver.resolve_type("UUID");
        assert_eq!(uuid.flavor, TypeFlavor::External);
    }

    #[test]
    fn test_nullable_variations() {
        let resolver = TypeResolver::new("test".to_string());

        // Optional[T]
        let opt = resolver.resolve_type("Optional[str]");
        assert!(opt.is_nullable);

        // T | None
        let union1 = resolver.resolve_type("str | None");
        assert!(union1.is_nullable);

        // None | T
        let union2 = resolver.resolve_type("None | str");
        assert!(union2.is_nullable);

        // Not nullable
        let not_null = resolver.resolve_type("str");
        assert!(!not_null.is_nullable);

        // Union without None
        let union_no_none = resolver.resolve_type("int | str");
        assert!(!union_no_none.is_nullable);
    }

    #[test]
    fn test_generic_with_spaces() {
        let resolver = TypeResolver::new("test".to_string());

        // Spaces in generics
        let spaced = resolver.resolve_type("Dict[str , int]");
        assert!(!spaced.generic_param_ids.is_empty());
        assert_eq!(spaced.generic_param_ids.len(), 2);

        // Multiple spaces
        let multi_space = resolver.resolve_type("List[  str  ]");
        assert!(!multi_space.generic_param_ids.is_empty());
        assert_eq!(multi_space.generic_param_ids.len(), 1);
    }

    #[test]
    fn test_type_id_consistency() {
        let resolver = TypeResolver::new("test".to_string());

        // Same type should generate same ID
        let type1 = resolver.resolve_type("List[str]");
        let type2 = resolver.resolve_type("List[str]");
        assert_eq!(type1.id, type2.id);

        // Different types should generate different IDs
        let type3 = resolver.resolve_type("List[int]");
        assert_ne!(type1.id, type3.id);

        // Whitespace shouldn't affect ID (after normalization)
        let type4 = resolver.resolve_type("  List[str]  ");
        assert_eq!(type1.id, type4.id);
    }

    #[test]
    fn test_unresolved_types() {
        let resolver = TypeResolver::new("test".to_string());

        // Unknown type
        let unknown = resolver.resolve_type("UnknownType");
        assert_eq!(unknown.flavor, TypeFlavor::External);
        assert_eq!(unknown.resolution_level, TypeResolutionLevel::Raw);
        assert_eq!(unknown.resolved_target, None);

        // Third-party type (not registered)
        let third_party = resolver.resolve_type("numpy.ndarray");
        assert_eq!(third_party.resolution_level, TypeResolutionLevel::Raw);
    }

    #[test]
    fn test_generic_with_builtin_and_user() {
        let mut resolver = TypeResolver::new("test".to_string());
        resolver.register_local_class("MyClass".to_string(), "node111".to_string());

        // Mix builtin and user types
        let mixed = resolver.resolve_type("Dict[str, MyClass]");
        assert!(!mixed.generic_param_ids.is_empty());
        assert_eq!(mixed.generic_param_ids.len(), 2);

        // Verify nested resolution
        let params = &mixed.generic_param_ids;
        let str_type = resolver.resolve_type("str");
        let my_type = resolver.resolve_type("MyClass");
        assert_eq!(params[0], str_type.id);
        assert_eq!(params[1], my_type.id);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // SOTA: Hindley-Milner Type Inference Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    #[test]
    fn test_infer_type_variable() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Create fresh type variable
        let var = resolver.fresh_type_var();

        // Should be InferType::Variable
        match var {
            InferType::Variable(id) => assert_eq!(id, 0),
            _ => panic!("Expected Variable"),
        }

        // Second variable should have different ID
        let var2 = resolver.fresh_type_var();
        match var2 {
            InferType::Variable(id) => assert_eq!(id, 1),
            _ => panic!("Expected Variable"),
        }
    }

    #[test]
    fn test_to_infer_type_simple() {
        let mut resolver = TypeResolver::new("test".to_string());

        let int_type = resolver.to_infer_type("int");
        match int_type {
            InferType::Concrete(t) => assert_eq!(t.to_string(), "int"),
            _ => panic!("Expected Concrete type"),
        }
    }

    #[test]
    fn test_to_infer_type_generic() {
        let mut resolver = TypeResolver::new("test".to_string());

        let list_int = resolver.to_infer_type("List[int]");
        match list_int {
            InferType::GenericInfer { base, params } => {
                assert_eq!(base, "List");
                assert_eq!(params.len(), 1);
            }
            _ => panic!("Expected GenericInfer"),
        }
    }

    #[test]
    fn test_to_infer_type_callable() {
        let mut resolver = TypeResolver::new("test".to_string());

        let callable = resolver.to_infer_type("Callable[int, str]");
        match callable {
            InferType::CallableInfer {
                params,
                return_type,
            } => {
                assert_eq!(params.len(), 1); // int param
                assert!(matches!(*return_type, InferType::Concrete(_))); // str return
            }
            _ => panic!("Expected CallableInfer"),
        }
    }

    #[test]
    fn test_to_infer_type_union() {
        let mut resolver = TypeResolver::new("test".to_string());

        let union = resolver.to_infer_type("int | str");
        match union {
            InferType::UnionInfer(types) => {
                assert_eq!(types.len(), 2);
            }
            _ => panic!("Expected UnionInfer"),
        }
    }

    #[test]
    fn test_constraint_solving_equality() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Create: T1 = int, T2 = T1
        let t1 = resolver.fresh_type_var();
        let t2 = resolver.fresh_type_var();
        let int_type = InferType::Concrete(Type::simple("int"));

        resolver.add_equality_constraint(t1.clone(), int_type.clone());
        resolver.add_equality_constraint(t2.clone(), t1.clone());

        // Solve
        let subst = resolver.solve_constraints().expect("Should solve");

        // T2 should resolve to int
        let resolved = resolver.apply_substitution(&t2, &subst);
        assert!(resolved.is_some());
        assert_eq!(resolved.unwrap().to_string(), "int");
    }

    #[test]
    fn test_constraint_solving_generic() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Create: T = List[int]
        let t = resolver.fresh_type_var();
        let int_type = InferType::Concrete(Type::simple("int"));

        resolver.add_generic_constraint(t.clone(), "List".to_string(), vec![int_type]);

        // Solve
        let subst = resolver.solve_constraints().expect("Should solve");

        // T should resolve to List[int]
        let resolved = resolver.apply_substitution(&t, &subst);
        assert!(resolved.is_some());
        assert_eq!(resolved.unwrap().to_string(), "List[int]");
    }

    #[test]
    fn test_constraint_solving_callable() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Create: T is callable (int, str) -> bool
        let t = resolver.fresh_type_var();
        let int_type = InferType::Concrete(Type::simple("int"));
        let str_type = InferType::Concrete(Type::simple("str"));
        let bool_type = InferType::Concrete(Type::simple("bool"));

        resolver.add_callable_constraint(t.clone(), vec![int_type, str_type], bool_type);

        // Solve
        let subst = resolver.solve_constraints().expect("Should solve");

        // T should resolve to (int, str) -> bool
        let resolved = resolver.apply_substitution(&t, &subst);
        assert!(resolved.is_some());
        assert_eq!(resolved.unwrap().to_string(), "(int, str) -> bool");
    }

    #[test]
    fn test_reset_inference() {
        let mut resolver = TypeResolver::new("test".to_string());

        // Create and cache some types
        let _ = resolver.fresh_type_var();
        let _ = resolver.to_infer_type("int");

        // Reset
        resolver.reset_inference();

        // Fresh var should start at 0 again
        let var = resolver.fresh_type_var();
        match var {
            InferType::Variable(id) => assert_eq!(id, 0),
            _ => panic!("Expected Variable with id 0"),
        }
    }
}
