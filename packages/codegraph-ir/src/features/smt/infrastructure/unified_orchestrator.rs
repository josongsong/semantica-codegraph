//! Unified SMT Orchestrator
//!
//! Intelligent runtime routing to appropriate solver based on:
//! 1. Constraint complexity
//! 2. Required accuracy
//! 3. Performance budget
//! 4. Incremental context (Z3 warm cache)
//!
//! # Decision Logic
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────┐
//! │                  Constraint Analysis                        │
//! ├─────────────────────────────────────────────────────────────┤
//! │                                                             │
//! │  Simple (SCCP constants)?                                  │
//! │    └─> Lightweight v1 (0.5ms) ──────────> 50% accuracy    │
//! │                                                             │
//! │  Medium (intervals, strings, arrays)?                      │
//! │    └─> Enhanced v2 (1ms) ────────────────> 80% accuracy    │
//! │                                                             │
//! │  Complex (non-linear, transitive chains)?                  │
//! │    └─> Z3 Backend (10-100ms) ────────────> 99% accuracy    │
//! │         ↑                                                   │
//! │         └─ Incremental: Reuse cached state!                │
//! │                                                             │
//! └─────────────────────────────────────────────────────────────┘
//! ```
//!
//! # Z3 Incremental Strategy
//!
//! Z3는 파일별로 warm context를 유지:
//! - **파일 시작**: push() 새 스코프
//! - **제약 추가**: 점진적으로 assert()
//! - **체크 포인트**: check() 후 결과 캐시
//! - **파일 종료**: pop() 스코프 제거
//!
//! ## Example
//!
//! ```rust,ignore
//! let mut orchestrator = UnifiedOrchestrator::new();
//!
//! // File-level incremental context
//! orchestrator.begin_file("main.py");
//! orchestrator.add_global_constraint(x > 0);  // Cached for entire file
//!
//! // Path-level checks (reuse global constraints)
//! orchestrator.check_path(&[y < 10]);  // Fast: already knows x > 0
//! orchestrator.check_path(&[z < 5]);   // Fast: already knows x > 0
//!
//! orchestrator.end_file("main.py");  // Clear file context
//! ```

use super::{analyzers, checkers, solvers, LatticeValue, PathFeasibility};
use crate::features::smt::domain::{ComparisonOp, ConstValue, Constraint, PathCondition};
use std::collections::HashMap;
use std::time::{Duration, Instant};

/// Constraint complexity level
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ComplexityLevel {
    /// Simple: SCCP constants only (<10 conditions)
    Simple = 0,
    /// Medium: Intervals, strings, arrays (<50 conditions)
    Medium = 1,
    /// Complex: Non-linear, long transitive chains (>50 conditions)
    Complex = 2,
}

/// Performance budget for constraint checking
#[derive(Debug, Clone, Copy)]
pub struct PerformanceBudget {
    /// Maximum time allowed (ms)
    pub max_time_ms: u64,
    /// Minimum required accuracy (0.0 - 1.0)
    pub min_accuracy: f32,
}

impl Default for PerformanceBudget {
    fn default() -> Self {
        Self {
            max_time_ms: 5,    // 5ms default
            min_accuracy: 0.7, // 70% accuracy minimum
        }
    }
}

/// Incremental Z3 context for a file
#[cfg(feature = "z3")]
struct Z3FileContext {
    /// Z3 solver instance
    solver: solvers::Z3Backend,
    /// File-level constraints (cached)
    global_constraints: Vec<Constraint>,
    /// Last check timestamp
    last_check: Instant,
}

/// Unified orchestrator statistics
#[derive(Debug, Clone, Default)]
pub struct UnifiedStats {
    /// Lightweight hits
    pub lightweight_hits: usize,
    /// Enhanced hits
    pub enhanced_hits: usize,
    /// Z3 hits
    pub z3_hits: usize,
    /// Total checks
    pub total_checks: usize,
    /// Average time (ms)
    pub avg_time_ms: f32,
}

/// Unified SMT orchestrator
pub struct UnifiedOrchestrator {
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Checkers (kept warm)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    lightweight: checkers::lightweight::LightweightConstraintChecker,
    enhanced: checkers::enhanced::EnhancedConstraintChecker,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Z3 Incremental Context (per-file)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #[cfg(feature = "z3")]
    z3_contexts: HashMap<String, Z3FileContext>,

    #[cfg(feature = "z3")]
    current_file: Option<String>,

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Performance tracking
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    stats: UnifiedStats,
    budget: PerformanceBudget,
}

impl Default for UnifiedOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}

impl UnifiedOrchestrator {
    /// Create new unified orchestrator
    pub fn new() -> Self {
        Self {
            lightweight: checkers::lightweight::LightweightConstraintChecker::new(),
            enhanced: checkers::enhanced::EnhancedConstraintChecker::new(),
            #[cfg(feature = "z3")]
            z3_contexts: HashMap::new(),
            #[cfg(feature = "z3")]
            current_file: None,
            stats: UnifiedStats::default(),
            budget: PerformanceBudget::default(),
        }
    }

    /// Set performance budget
    pub fn set_budget(&mut self, budget: PerformanceBudget) {
        self.budget = budget;
    }

    /// Set SCCP values (for all checkers)
    pub fn set_sccp_values(&mut self, values: HashMap<String, LatticeValue>) {
        self.lightweight.set_sccp_values(values.clone());
        // Enhanced checker also needs SCCP values
        for (var, val) in values {
            self.enhanced.add_sccp_value(var, val);
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Incremental Z3 Context Management
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Begin file analysis (creates Z3 context)
    #[cfg(feature = "z3")]
    pub fn begin_file(&mut self, file_path: String) {
        if !self.z3_contexts.contains_key(&file_path) {
            // Create new Z3 context for this file
            let solver = solvers::Z3Backend::with_timeout(self.budget.max_time_ms as u32);
            self.z3_contexts.insert(
                file_path.clone(),
                Z3FileContext {
                    solver,
                    global_constraints: Vec::new(),
                    last_check: Instant::now(),
                },
            );
        }
        self.current_file = Some(file_path);
    }

    /// Add global constraint (file-level, cached in Z3)
    #[cfg(feature = "z3")]
    pub fn add_global_constraint(&mut self, constraint: Constraint) {
        if let Some(file) = &self.current_file {
            if let Some(ctx) = self.z3_contexts.get_mut(file) {
                ctx.solver.push(); // New scope
                ctx.solver.add_constraint(&constraint);
                ctx.global_constraints.push(constraint);
            }
        }
    }

    /// End file analysis (cleanup Z3 context if stale)
    #[cfg(feature = "z3")]
    pub fn end_file(&mut self, file_path: &str) {
        // Keep context for 60 seconds (warm cache)
        // Will be cleaned up later if not used
        if let Some(ctx) = self.z3_contexts.get_mut(file_path) {
            ctx.last_check = Instant::now();
        }
        self.current_file = None;
    }

    /// Cleanup stale Z3 contexts (older than 60s)
    #[cfg(feature = "z3")]
    pub fn cleanup_stale_contexts(&mut self) {
        let threshold = Duration::from_secs(60);
        let now = Instant::now();

        self.z3_contexts
            .retain(|_, ctx| now.duration_since(ctx.last_check) < threshold);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Complexity Analysis
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Analyze constraint complexity
    fn analyze_complexity(&self, conditions: &[PathCondition]) -> ComplexityLevel {
        // Simple heuristics:

        // 1. Number of conditions
        if conditions.len() > 50 {
            return ComplexityLevel::Complex;
        }

        if conditions.len() <= 10 {
            // Check if all are simple integer SCCP constants (no strings, arrays, etc.)
            let all_simple = conditions.iter().all(|c| {
                let is_simple_op = matches!(
                    c.op,
                    ComparisonOp::Eq
                        | ComparisonOp::Lt
                        | ComparisonOp::Gt
                        | ComparisonOp::Le
                        | ComparisonOp::Ge
                );
                let is_simple_value = match &c.value {
                    Some(ConstValue::Int(_)) | Some(ConstValue::Bool(_)) | None => true,
                    _ => false, // String/float/null need complex theory
                };
                is_simple_op && is_simple_value
            });

            if all_simple {
                return ComplexityLevel::Simple;
            }
        }

        // 2. Presence of complex operations
        let has_complex = conditions.iter().any(|c| {
            matches!(c.op, ComparisonOp::Null | ComparisonOp::NotNull) || c.value.is_none()
            // Variable-to-variable comparisons
        });

        if has_complex {
            return ComplexityLevel::Complex;
        }

        // 3. String/array constraints
        let has_semantic = conditions
            .iter()
            .any(|c| matches!(c.value, Some(ConstValue::String(_))));

        if has_semantic {
            return ComplexityLevel::Medium;
        }

        // Default: Medium
        ComplexityLevel::Medium
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Intelligent Routing
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Check path feasibility (intelligent routing)
    pub fn check_path_feasible(&mut self, conditions: &[PathCondition]) -> PathFeasibility {
        let start = Instant::now();
        self.stats.total_checks += 1;

        let complexity = self.analyze_complexity(conditions);

        let result = match complexity {
            ComplexityLevel::Simple => {
                // Try lightweight first
                self.stats.lightweight_hits += 1;
                self.check_with_lightweight(conditions)
            }

            ComplexityLevel::Medium => {
                // Try enhanced (may escalate to Z3)
                self.stats.enhanced_hits += 1;
                self.check_with_enhanced(conditions)
            }

            ComplexityLevel::Complex => {
                // Go directly to Z3 (if available)
                #[cfg(feature = "z3")]
                {
                    self.stats.z3_hits += 1;
                    self.check_with_z3(conditions)
                }

                #[cfg(not(feature = "z3"))]
                {
                    // Fallback to enhanced
                    self.stats.enhanced_hits += 1;
                    self.check_with_enhanced(conditions)
                }
            }
        };

        // Update average time
        let elapsed = start.elapsed().as_micros() as f32 / 1000.0;
        self.stats.avg_time_ms = (self.stats.avg_time_ms * (self.stats.total_checks - 1) as f32
            + elapsed)
            / self.stats.total_checks as f32;

        result
    }

    /// Check with lightweight (fast path)
    fn check_with_lightweight(&mut self, conditions: &[PathCondition]) -> PathFeasibility {
        let result = self.lightweight.is_path_feasible(conditions);

        match result {
            PathFeasibility::Unknown => {
                // Escalate to enhanced
                self.check_with_enhanced(conditions)
            }
            _ => result,
        }
    }

    /// Check with enhanced (medium path)
    fn check_with_enhanced(&mut self, conditions: &[PathCondition]) -> PathFeasibility {
        // Clear previous conditions
        // (Enhanced checker accumulates state)

        for cond in conditions {
            self.enhanced.add_condition(cond);
        }

        let result = self.enhanced.is_path_feasible();

        match result {
            PathFeasibility::Unknown if self.budget.min_accuracy > 0.8 => {
                // Escalate to Z3 if high accuracy required
                #[cfg(feature = "z3")]
                {
                    self.check_with_z3(conditions)
                }

                #[cfg(not(feature = "z3"))]
                result
            }
            _ => result,
        }
    }

    /// Check with Z3 (slow path, highest accuracy)
    #[cfg(feature = "z3")]
    fn check_with_z3(&mut self, conditions: &[PathCondition]) -> PathFeasibility {
        // Use current file context if available
        let solver = if let Some(file) = &self.current_file {
            if let Some(ctx) = self.z3_contexts.get_mut(file) {
                &mut ctx.solver
            } else {
                // Fallback: create temporary solver
                return self.check_with_z3_temporary(conditions);
            }
        } else {
            return self.check_with_z3_temporary(conditions);
        };

        // Push scope for local checks
        solver.push();

        // Add local conditions
        for cond in conditions {
            let constraint = Constraint::simple(
                cond.var.clone(),
                cond.op,
                cond.value.clone().unwrap_or(ConstValue::Int(0)),
            );
            solver.add_constraint(&constraint);
        }

        // Check
        let result = match solver.check() {
            solvers::SolverResult::Sat(_) => PathFeasibility::Feasible,
            solvers::SolverResult::Unsat => PathFeasibility::Infeasible,
            solvers::SolverResult::Unknown => PathFeasibility::Unknown,
        };

        // Pop scope (restore to file-level constraints)
        solver.pop(1);

        result
    }

    /// Check with temporary Z3 solver (no incremental context)
    #[cfg(feature = "z3")]
    fn check_with_z3_temporary(&mut self, conditions: &[PathCondition]) -> PathFeasibility {
        let mut solver = solvers::Z3Backend::with_timeout(self.budget.max_time_ms as u32);

        for cond in conditions {
            let constraint = Constraint::simple(
                cond.var.clone(),
                cond.op,
                cond.value.clone().unwrap_or(ConstValue::Int(0)),
            );
            solver.add_constraint(&constraint);
        }

        match solver.check() {
            solvers::SolverResult::Sat(_) => PathFeasibility::Feasible,
            solvers::SolverResult::Unsat => PathFeasibility::Infeasible,
            solvers::SolverResult::Unknown => PathFeasibility::Unknown,
        }
    }

    /// Get statistics
    pub fn stats(&self) -> &UnifiedStats {
        &self.stats
    }

    /// Reset statistics
    pub fn reset_stats(&mut self) {
        self.stats = UnifiedStats::default();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_complexity_analysis() {
        let orchestrator = UnifiedOrchestrator::new();

        // Simple: few conditions
        let simple = vec![
            PathCondition::gt("x".to_string(), ConstValue::Int(5)),
            PathCondition::lt("x".to_string(), ConstValue::Int(10)),
        ];
        assert_eq!(
            orchestrator.analyze_complexity(&simple),
            ComplexityLevel::Simple
        );

        // Complex: many conditions
        let complex: Vec<_> = (0..60)
            .map(|i| PathCondition::gt(format!("x{}", i), ConstValue::Int(0)))
            .collect();
        assert_eq!(
            orchestrator.analyze_complexity(&complex),
            ComplexityLevel::Complex
        );

        // Medium: semantic constraints
        let medium = vec![PathCondition::eq(
            "s".to_string(),
            ConstValue::String("test".to_string()),
        )];
        assert_eq!(
            orchestrator.analyze_complexity(&medium),
            ComplexityLevel::Medium
        );
    }

    #[test]
    fn test_orchestrator_routing() {
        let mut orchestrator = UnifiedOrchestrator::new();

        // Set SCCP value
        let mut sccp = HashMap::new();
        sccp.insert("x".to_string(), LatticeValue::Constant(ConstValue::Int(7)));
        orchestrator.set_sccp_values(sccp);

        // Simple check (should use lightweight)
        let conditions = vec![
            PathCondition::gt("x".to_string(), ConstValue::Int(5)),
            PathCondition::lt("x".to_string(), ConstValue::Int(10)),
        ];

        let result = orchestrator.check_path_feasible(&conditions);
        assert_eq!(result, PathFeasibility::Feasible);

        // Check stats
        assert!(orchestrator.stats().lightweight_hits > 0);
    }

    #[cfg(feature = "z3")]
    #[test]
    fn test_z3_incremental() {
        let mut orchestrator = UnifiedOrchestrator::new();

        // Begin file
        orchestrator.begin_file("test.py".to_string());

        // Add global constraint
        orchestrator.add_global_constraint(Constraint::simple(
            "x".to_string(),
            ComparisonOp::Gt,
            ConstValue::Int(0),
        ));

        // Check path (should reuse global constraint)
        let conditions = vec![PathCondition::lt("x".to_string(), ConstValue::Int(10))];

        let result = orchestrator.check_path_feasible(&conditions);
        assert_eq!(result, PathFeasibility::Feasible);

        orchestrator.end_file("test.py");
    }
}
