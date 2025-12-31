use super::abductive_inference::AbductiveEngine;
/// Bi-Abduction Strategy (SOTA Implementation)
///
/// Real bi-abduction using Separation Logic for compositional effect analysis.
///
/// Algorithm:
/// 1. For each function, infer precondition/postcondition via abduction
/// 2. Extract effects from inferred specs
/// 3. Cache specs for compositional analysis
///
/// Performance:
/// - Full analysis: O(F × AbductionCost) - slower than fixpoint
/// - Incremental: O(1) per function - VERY FAST (compositional!)
///
/// Reference: Facebook Infer, "Compositional Shape Analysis by means of Bi-Abduction"
use crate::features::cross_file::IRDocument;
use crate::features::effect_analysis::domain::{ports::*, EffectSet, EffectSource, EffectType};
use crate::features::effect_analysis::infrastructure::LocalEffectAnalyzer;
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::Instant;

/// Bi-abduction strategy (REAL implementation)
pub struct BiAbductionStrategy {
    local_analyzer: LocalEffectAnalyzer,
    /// Abductive inference engine
    engine: Mutex<AbductiveEngine>,
    metrics: Mutex<AnalysisMetrics>,
}

impl BiAbductionStrategy {
    pub fn new(local_analyzer: LocalEffectAnalyzer) -> Self {
        Self {
            local_analyzer,
            engine: Mutex::new(AbductiveEngine::new()),
            metrics: Mutex::new(AnalysisMetrics::new()),
        }
    }

    /// Bi-abduce: Infer effects using separation logic
    fn bi_abduce(&self, ir_doc: &IRDocument, func_node: &crate::shared::models::Node) -> EffectSet {
        let mut engine = self.engine.lock().unwrap();
        let result = engine.bi_abduce(ir_doc, func_node);

        // Convert inference effects to domain effects
        let domain_effects: HashSet<EffectType> = result
            .effects
            .iter()
            .map(|e| self.convert_effect(e))
            .collect();

        // Determine if function is idempotent (based on effects)
        let is_idempotent = domain_effects.contains(&EffectType::Pure)
            || (domain_effects.len() == 1 && domain_effects.contains(&EffectType::ReadState));

        // Determine effect source
        let source = if domain_effects.contains(&EffectType::Pure) {
            EffectSource::Inferred
        } else if domain_effects.contains(&EffectType::ExternalCall) {
            EffectSource::Unknown
        } else {
            EffectSource::Static
        };

        EffectSet::new(
            func_node.id.clone(),
            domain_effects,
            is_idempotent,
            result.confidence,
            source,
        )
    }

    /// Convert inference effect type to domain effect type
    fn convert_effect(&self, effect: &EffectType) -> EffectType {
        // No conversion needed - they're the same type now
        effect.clone()
    }
}

impl InterproceduralAnalysisPort for BiAbductionStrategy {
    fn analyze_all(&self, ir_doc: &IRDocument) -> HashMap<String, EffectSet> {
        let start = Instant::now();
        let mut result = HashMap::new();

        // PHASE 1: Bi-abduce each function (local analysis only)
        for node in &ir_doc.nodes {
            if matches!(
                node.kind,
                crate::shared::models::NodeKind::Function | crate::shared::models::NodeKind::Method
            ) {
                let effect_set = self.bi_abduce(ir_doc, node);
                result.insert(node.id.clone(), effect_set);
            }
        }

        // PHASE 2: Propagate effects through call graph
        let call_edges: Vec<_> = ir_doc
            .edges
            .iter()
            .filter(|e| matches!(e.kind, crate::shared::models::EdgeKind::Calls))
            .collect();

        // Iterate until fixpoint (effects stabilize)
        let mut changed = true;
        let mut iterations = 0;
        const MAX_ITERATIONS: usize = 100;

        while changed && iterations < MAX_ITERATIONS {
            changed = false;
            iterations += 1;

            for edge in &call_edges {
                let caller_id = &edge.source_id;
                let callee_id = &edge.target_id;

                // Get callee effects (clone to avoid borrow checker issues)
                let callee_effects_clone = result.get(callee_id).map(|e| e.effects.clone());

                if let Some(callee_effects) = callee_effects_clone {
                    if let Some(caller_effects) = result.get_mut(caller_id) {
                        let old_len = caller_effects.effects.len();

                        // Propagate callee effects to caller
                        for effect in &callee_effects {
                            if *effect == EffectType::Pure {
                                continue;
                            }
                            caller_effects.effects.insert(effect.clone());
                        }

                        // Remove Pure if there are other effects
                        if caller_effects.effects.len() > 1 {
                            caller_effects.effects.remove(&EffectType::Pure);
                        }

                        // Update idempotent flag
                        caller_effects.idempotent =
                            caller_effects.effects.contains(&EffectType::Pure)
                                || (caller_effects.effects.len() == 1
                                    && caller_effects.effects.contains(&EffectType::ReadState));

                        if caller_effects.effects.len() != old_len {
                            changed = true;
                        }
                    }
                }
            }
        }

        let elapsed = start.elapsed().as_secs_f64() * 1000.0;

        // Calculate average confidence
        let avg_confidence = if result.is_empty() {
            0.0
        } else {
            result.values().map(|e| e.confidence).sum::<f64>() / result.len() as f64
        };

        let mut metrics = self.metrics.lock().unwrap();
        metrics.total_time_ms = elapsed;
        metrics.functions_analyzed = result.len();
        metrics.avg_confidence = avg_confidence;

        result
    }

    fn analyze_incremental(
        &self,
        ir_doc: &IRDocument,
        changed_functions: &[String],
        cache: &HashMap<String, EffectSet>,
    ) -> HashMap<String, EffectSet> {
        let start = Instant::now();

        let mut result = cache.clone();
        let mut cache_misses = 0;

        // Only re-analyze changed functions (COMPOSITIONAL!)
        // This is the key advantage of bi-abduction
        for func_id in changed_functions {
            cache_misses += 1;

            // Find function node
            if let Some(func_node) = ir_doc.nodes.iter().find(|n| n.id == *func_id) {
                let effect_set = self.bi_abduce(ir_doc, func_node);
                result.insert(func_id.clone(), effect_set);
            }
        }

        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
        let cache_hits = result.len() - cache_misses;

        let mut metrics = self.metrics.lock().unwrap();
        metrics.total_time_ms = elapsed;
        metrics.functions_analyzed = changed_functions.len();
        metrics.cache_hits = cache_hits;
        metrics.cache_misses = cache_misses;

        result
    }

    fn strategy_name(&self) -> &'static str {
        "BiAbduction(SeparationLogic)"
    }

    fn metrics(&self) -> AnalysisMetrics {
        self.metrics.lock().unwrap().clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::{Edge, EdgeKind, Node, NodeKind, Span};

    fn create_test_function(id: &str, name: &str) -> Node {
        Node {
            id: id.to_string(),
            kind: NodeKind::Function,
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

    fn create_variable(id: &str, name: &str) -> Node {
        let mut node = create_test_function(id, name);
        node.kind = NodeKind::Variable;
        node
    }

    #[test]
    fn test_biabduction_strategy_creation() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let strategy = BiAbductionStrategy::new(local_analyzer);

        assert_eq!(strategy.strategy_name(), "BiAbduction(SeparationLogic)");
    }

    #[test]
    fn test_biabduction_empty_function() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let strategy = BiAbductionStrategy::new(local_analyzer);

        let func = create_test_function("func1", "empty_func");
        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func.clone()],
            edges: vec![],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 1);
        let effect_set = result.get("func1").unwrap();

        // Empty function should be Pure
        assert!(effect_set.effects.contains(&EffectType::Pure));
        assert_eq!(effect_set.confidence, 1.0);
    }

    #[test]
    fn test_biabduction_io_function() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let strategy = BiAbductionStrategy::new(local_analyzer);

        let func = create_test_function("func1", "print_func");
        let print_var = create_variable("var1", "print");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func.clone(), print_var],
            edges: vec![Edge::new(
                "func1".to_string(),
                "var1".to_string(),
                EdgeKind::Contains,
            )],
            repo_id: None,
        };

        let result = strategy.analyze_all(&ir_doc);

        assert_eq!(result.len(), 1);
        let effect_set = result.get("func1").unwrap();

        // Should detect I/O effect from "print"
        assert!(effect_set.effects.contains(&EffectType::Io));
        assert!(effect_set.confidence > 0.8);
    }

    #[test]
    fn test_biabduction_incremental() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let strategy = BiAbductionStrategy::new(local_analyzer);

        let func1 = create_test_function("func1", "foo");
        let func2 = create_test_function("func2", "bar");

        let ir_doc = IRDocument {
            file_path: "test.py".to_string(),
            nodes: vec![func1, func2],
            edges: vec![],
            repo_id: None,
        };

        // Full analysis
        let cache = strategy.analyze_all(&ir_doc);
        assert_eq!(cache.len(), 2);

        // Incremental: only func2 changed
        let changed = vec!["func2".to_string()];
        let result = strategy.analyze_incremental(&ir_doc, &changed, &cache);

        assert_eq!(result.len(), 2);

        let metrics = strategy.metrics();
        assert_eq!(metrics.cache_hits, 1); // func1 from cache
        assert_eq!(metrics.cache_misses, 1); // func2 re-analyzed
    }

    #[test]
    fn test_effect_conversion() {
        let local_analyzer = LocalEffectAnalyzer::new();
        let strategy = BiAbductionStrategy::new(local_analyzer);

        // Test all effect type conversions
        assert_eq!(strategy.convert_effect(&EffectType::Pure), EffectType::Pure);
        assert_eq!(strategy.convert_effect(&EffectType::Io), EffectType::Io);
        assert_eq!(
            strategy.convert_effect(&EffectType::Network),
            EffectType::Network
        );
    }
}
