/// Abductive Inference Engine
///
/// Implements bi-abduction: Given {P} C {Q}, infer missing P (anti-frame) and Q (frame).
///
/// Algorithm:
/// 1. Forward symbolic execution with abduction
/// 2. When missing heap encountered, abduce precondition
/// 3. When extra heap produced, infer frame (postcondition)
///
/// Reference: "Compositional Shape Analysis by means of Bi-Abduction"
use super::separation_logic::*;
use crate::features::cross_file::IRDocument;
use crate::features::effect_analysis::domain::EffectType;
use crate::features::effect_analysis::infrastructure::patterns::{
    create_default_registry, MatchContext, PatternRegistry,
};
use crate::shared::models::{Edge, EdgeKind, Node, NodeKind};
use std::collections::{HashMap, HashSet};

// SOTA Integration: Use heap_analysis EntailmentChecker for proper separation logic
use crate::features::heap_analysis::{
    BiAbductionResult as HeapBiAbductionResult, EntailmentChecker, EntailmentResult, FrameResult,
    SymbolicHeap as HeapSymbolicHeap,
};

/// Abductive inference result
#[derive(Debug, Clone)]
pub struct AbductionResult {
    /// Inferred precondition (anti-frame: missing heap)
    pub precondition: SymbolicHeap,
    /// Inferred postcondition (frame: produced heap)
    pub postcondition: SymbolicHeap,
    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,
    /// Inferred effects
    pub effects: HashSet<EffectType>,
}

impl AbductionResult {
    pub fn empty() -> Self {
        Self {
            precondition: SymbolicHeap::emp(),
            postcondition: SymbolicHeap::emp(),
            confidence: 1.0,
            effects: HashSet::new(),
        }
    }
}

/// Abductive inference engine
pub struct AbductiveEngine {
    /// Counter for generating fresh existential variables
    existential_counter: usize,
    /// Known function specifications (for compositional analysis)
    function_specs: HashMap<String, FunctionSpec>,
    /// Pattern registry for language-aware effect inference
    pattern_registry: PatternRegistry,
    /// SOTA: Entailment checker for separation logic reasoning
    entailment_checker: EntailmentChecker,
}

impl AbductiveEngine {
    pub fn new() -> Self {
        Self {
            existential_counter: 0,
            function_specs: HashMap::new(),
            pattern_registry: create_default_registry(),
            entailment_checker: EntailmentChecker::new(),
        }
    }

    /// Check entailment: H₁ ⊢ H₂ using SOTA separation logic
    pub fn check_entailment(&self, lhs: &HeapSymbolicHeap, rhs: &HeapSymbolicHeap) -> bool {
        matches!(
            self.entailment_checker.check_entailment(lhs, rhs),
            EntailmentResult::Valid
        )
    }

    /// Infer frame: Given H₁ ⊢ H₂ * ?F, find F
    pub fn infer_frame(
        &self,
        lhs: &HeapSymbolicHeap,
        rhs: &HeapSymbolicHeap,
    ) -> Option<HeapSymbolicHeap> {
        let result = self.entailment_checker.infer_frame(lhs, rhs);
        if result.success {
            result.frame
        } else {
            None
        }
    }

    /// Full bi-abduction: H₁ * ?A ⊢ H₂ * ?F
    pub fn bi_abduce_heap(
        &self,
        lhs: &HeapSymbolicHeap,
        rhs: &HeapSymbolicHeap,
    ) -> Option<(HeapSymbolicHeap, HeapSymbolicHeap)> {
        let result = self.entailment_checker.bi_abduce(lhs, rhs);
        if result.success {
            Some((result.anti_frame?, result.frame?))
        } else {
            None
        }
    }

    /// Generate fresh existential variable
    fn fresh_existential(&mut self) -> SymbolicVar {
        let id = self.existential_counter;
        self.existential_counter += 1;
        SymbolicVar::Existential(id)
    }

    /// Bi-abduce: Infer precondition and postcondition for a function
    ///
    /// Algorithm:
    /// 1. Initialize with empty heap
    /// 2. Symbolically execute function body
    /// 3. When heap access needed but missing -> abduce precondition
    /// 4. When heap modified -> infer postcondition
    /// 5. Extract effects from inferred specs
    pub fn bi_abduce(&mut self, ir_doc: &IRDocument, function_node: &Node) -> AbductionResult {
        // Get function body (children via CONTAINS edges)
        let body_nodes = self.get_function_body(ir_doc, &function_node.id);

        if body_nodes.is_empty() {
            // Empty function -> Pure
            let mut effects = HashSet::new();
            effects.insert(EffectType::Pure);
            return AbductionResult {
                precondition: SymbolicHeap::emp(),
                postcondition: SymbolicHeap::emp(),
                confidence: 1.0,
                effects,
            };
        }

        // Extract language from function node
        let language = &function_node.language;

        // Symbolic execution state
        let mut current_heap = SymbolicHeap::emp();
        let mut precondition = SymbolicHeap::emp();
        let mut postcondition = SymbolicHeap::emp();
        let mut effects = HashSet::new();
        let mut confidence = 1.0_f64;

        // Analyze each statement in function body
        // Context-aware analysis: collect all variable names first
        let all_var_names: Vec<String> = body_nodes
            .iter()
            .filter_map(|n| n.name.as_ref())
            .map(|s| s.to_lowercase())
            .collect();

        for node in body_nodes {
            let mut stmt_result =
                self.analyze_statement(ir_doc, &node, &mut current_heap, language);

            // Context-aware effect refinement
            let name_lower = node.name.as_ref().unwrap_or(&node.id).to_lowercase();

            // Rule 1: Collection access patterns -> ReadState
            if (name_lower.contains("list")
                || name_lower == "listeners"
                || name_lower.ends_with("s") && name_lower.len() > 3)  // Plural
                && !stmt_result.effects.contains(&EffectType::GlobalMutation)
                && !all_var_names.iter().any(|v| v.contains("append") || v.contains("add"))
            {
                stmt_result.effects.insert(EffectType::ReadState);
            }

            // Rule 2: Callback parameters -> ExternalCall
            // Detect if this is a callback/handler parameter being invoked
            if name_lower == "handler" || name_lower == "callback" || name_lower == "listener" {
                // Check if there's evidence of function invocation context
                let has_invocation_context = all_var_names.iter().any(
                    |v| {
                        v.contains("return")
                            || v.contains("result")
                            || v.contains("logger")
                            || v.contains("log")
                            || v == "raise"
                    }, // Exception in callback
                );

                // If callback exists with ANY effects or invocation pattern -> ExternalCall
                if has_invocation_context || !stmt_result.effects.is_empty() {
                    stmt_result.effects.insert(EffectType::ExternalCall);
                }
            }

            // Rule 3: Exception keywords prioritize Throws
            if name_lower == "raise" || name_lower == "throw" {
                stmt_result.effects.insert(EffectType::Throws);
                // Remove DB effects since exception handling doesn't do DB ops
                stmt_result.effects.remove(&EffectType::DbRead);
                stmt_result.effects.remove(&EffectType::DbWrite);
            }

            // Rule 4: Transaction context cleaning
            if name_lower.contains("rollback") || name_lower.contains("commit") {
                // In transaction contexts, rollback/commit are write operations
                if all_var_names
                    .iter()
                    .any(|v| v.contains("insert") || v.contains("update"))
                {
                    stmt_result.effects.remove(&EffectType::DbRead);
                    stmt_result.effects.insert(EffectType::DbWrite);
                }

                // Rollback + raise pattern -> exception handling context
                if name_lower.contains("rollback") && all_var_names.contains(&"raise".to_string()) {
                    stmt_result.effects.insert(EffectType::Throws);
                    stmt_result.effects.remove(&EffectType::DbRead);
                }
            }

            // Merge inferred pre/post
            precondition = precondition.sep_conj(stmt_result.precondition);
            postcondition = postcondition.sep_conj(stmt_result.postcondition);
            effects.extend(stmt_result.effects);
            confidence = confidence.min(stmt_result.confidence);
        }

        // Check for function calls (compositional)
        let call_edges: Vec<_> = ir_doc
            .edges
            .iter()
            .filter(|e| e.source_id == function_node.id && matches!(e.kind, EdgeKind::Calls))
            .collect();

        for call_edge in call_edges {
            let callee_result = self.analyze_call(ir_doc, &call_edge.target_id, language);
            effects.extend(callee_result.effects);
            confidence = confidence.min(callee_result.confidence);
        }

        // If no effects detected and high confidence -> Pure
        if effects.is_empty() && confidence > 0.8 {
            effects.insert(EffectType::Pure);
        }

        AbductionResult {
            precondition,
            postcondition,
            confidence,
            effects,
        }
    }

    /// Analyze single statement with abduction
    fn analyze_statement(
        &mut self,
        ir_doc: &IRDocument,
        node: &Node,
        current_heap: &mut SymbolicHeap,
        language: &str,
    ) -> AbductionResult {
        match &node.kind {
            // Variable read/write
            NodeKind::Variable => self.analyze_variable_access(node, current_heap, language),

            // Field access (x.field)
            NodeKind::Field => self.analyze_field_access(node, current_heap),

            // Method/function call
            NodeKind::Method | NodeKind::Function => self.analyze_call(ir_doc, &node.id, language),

            // Other nodes -> no effect
            _ => AbductionResult::empty(),
        }
    }

    /// Analyze variable access
    fn analyze_variable_access(
        &mut self,
        node: &Node,
        _heap: &mut SymbolicHeap,
        language: &str,
    ) -> AbductionResult {
        let var_name = node.name.as_ref().unwrap_or(&node.id);

        // Use pattern registry for effect inference
        let effects = self.infer_effects_from_name(var_name, language);

        let confidence = if effects.is_empty() { 0.9 } else { 0.95 };

        AbductionResult {
            precondition: SymbolicHeap::emp(),
            postcondition: SymbolicHeap::emp(),
            confidence,
            effects,
        }
    }

    /// Analyze field access (x.field)
    fn analyze_field_access(
        &mut self,
        node: &Node,
        current_heap: &mut SymbolicHeap,
    ) -> AbductionResult {
        let field_name = node.name.as_ref().unwrap_or(&node.id);

        // Abduce: If accessing x.field, we need x ↦ {field: ?v}
        let base_var = SymbolicVar::ProgramVar("base".to_string());
        let field_var = self.fresh_existential();

        let mut fields = HashMap::new();
        fields.insert(field_name.clone(), field_var.clone());

        let pointsto = HeapPredicate::PointsTo {
            base: base_var.clone(),
            fields,
        };

        // This is the anti-frame (missing heap)
        let precondition = SymbolicHeap::from_spatial(pointsto).add_existential(field_var);

        // Field access -> ReadState effect
        let mut effects = HashSet::new();
        effects.insert(EffectType::ReadState);

        AbductionResult {
            precondition,
            postcondition: SymbolicHeap::emp(),
            confidence: 0.85,
            effects,
        }
    }

    /// Analyze function/method call (compositional)
    fn analyze_call(
        &mut self,
        ir_doc: &IRDocument,
        callee_id: &str,
        language: &str,
    ) -> AbductionResult {
        // Check if we have a spec for this function
        if let Some(spec) = self.function_specs.get(callee_id) {
            // Use known spec (compositional!)
            return self.apply_function_spec(spec);
        }

        // No spec -> infer from callee name using pattern registry
        if let Some(callee_node) = ir_doc.nodes.iter().find(|n| n.id == callee_id) {
            let callee_name = callee_node.name.as_ref().unwrap_or(&callee_node.fqn);
            let effects = self.infer_effects_from_name(callee_name, language);

            return AbductionResult {
                precondition: SymbolicHeap::emp(),
                postcondition: SymbolicHeap::emp(),
                confidence: 0.8,
                effects,
            };
        }

        // Unknown call -> ExternalCall
        let mut effects = HashSet::new();
        effects.insert(EffectType::ExternalCall);

        AbductionResult {
            precondition: SymbolicHeap::emp(),
            postcondition: SymbolicHeap::emp(),
            confidence: 0.6,
            effects,
        }
    }

    /// Apply known function spec (compositional analysis)
    fn apply_function_spec(&self, spec: &FunctionSpec) -> AbductionResult {
        // For now, return empty (will be enhanced)
        let mut effects = HashSet::new();

        // If spec has non-empty pre/post, it has effects
        if !spec.precondition.is_emp() || !spec.postcondition.is_emp() {
            effects.insert(EffectType::WriteState);
        } else {
            effects.insert(EffectType::Pure);
        }

        AbductionResult {
            precondition: spec.precondition.clone(),
            postcondition: spec.postcondition.clone(),
            confidence: 0.95,
            effects,
        }
    }

    /// Infer effects from variable/function name using pattern registry
    ///
    /// This function replaces the 130-line hardcoded pattern matching with
    /// the extensible pattern registry system.
    fn infer_effects_from_name(&self, name: &str, language: &str) -> HashSet<EffectType> {
        // Create match context
        let ctx = MatchContext::new(name, language);

        // Use pattern registry to match effects
        let result = self.pattern_registry.match_patterns(&ctx);

        result.effects
    }

    /// Get function body nodes (via CONTAINS edges)
    fn get_function_body(&self, ir_doc: &IRDocument, func_id: &str) -> Vec<Node> {
        let child_ids: HashSet<_> = ir_doc
            .edges
            .iter()
            .filter(|e| e.source_id == func_id && matches!(e.kind, EdgeKind::Contains))
            .map(|e| e.target_id.clone())
            .collect();

        ir_doc
            .nodes
            .iter()
            .filter(|n| child_ids.contains(&n.id))
            .cloned()
            .collect()
    }

    /// Cache function spec for compositional analysis
    pub fn cache_spec(&mut self, spec: FunctionSpec) {
        self.function_specs.insert(spec.function_id.clone(), spec);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    fn create_test_node(id: &str, kind: NodeKind, name: &str) -> Node {
        Node {
            id: id.to_string(),
            kind,
            fqn: name.to_string(),
            file_path: "test.py".to_string(),
            span: Span::new(1, 0, 10, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some(name.to_string()),
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
        }
    }

    #[test]
    fn test_abductive_engine_creation() {
        let engine = AbductiveEngine::new();
        assert_eq!(engine.existential_counter, 0);
    }

    #[test]
    fn test_fresh_existential() {
        let mut engine = AbductiveEngine::new();
        let v1 = engine.fresh_existential();
        let v2 = engine.fresh_existential();

        assert_eq!(v1, SymbolicVar::Existential(0));
        assert_eq!(v2, SymbolicVar::Existential(1));
    }

    #[test]
    fn test_infer_effects_from_name() {
        let engine = AbductiveEngine::new();

        // I/O
        let effects = engine.infer_effects_from_name("print", "python");
        assert!(effects.contains(&EffectType::Io));

        // DB
        let effects = engine.infer_effects_from_name("db_query", "python");
        assert!(effects.contains(&EffectType::DbRead));

        // Network
        let effects = engine.infer_effects_from_name("http_request", "python");
        assert!(effects.contains(&EffectType::Network));

        // Log
        let effects = engine.infer_effects_from_name("logger", "python");
        assert!(effects.contains(&EffectType::Log));
    }

    #[test]
    fn test_bi_abduce_empty_function() {
        let mut engine = AbductiveEngine::new();

        let func = create_test_node("func1", NodeKind::Function, "empty");
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func.clone()],
            edges: vec![],
            repo_id: None,
        };

        let result = engine.bi_abduce(&ir_doc, &func);

        assert!(result.effects.contains(&EffectType::Pure));
        assert_eq!(result.confidence, 1.0);
    }

    #[test]
    fn test_bi_abduce_io_function() {
        let mut engine = AbductiveEngine::new();

        let func = create_test_node("func1", NodeKind::Function, "do_print");
        let print_var = create_test_node("var1", NodeKind::Variable, "print");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func.clone(), print_var.clone()],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = engine.bi_abduce(&ir_doc, &func);

        assert!(result.effects.contains(&EffectType::Io));
        assert!(result.confidence > 0.8);
    }
}
