//! SMT Infrastructure
//!
//! Infrastructure layer for constraint checking and path feasibility.
//!
//! # Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────┐
//! │                  SMT Infrastructure                         │
//! ├─────────────────────────────────────────────────────────────┤
//! │                                                             │
//! │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
//! │  │  Solvers    │  │  Analyzers  │  │  Checkers   │        │
//! │  │  (Core SMT) │  │  (Semantic) │  │  (Fast Path)│        │
//! │  └─────────────┘  └─────────────┘  └─────────────┘        │
//! │        │                 │                 │                │
//! │        └─────────────────┴─────────────────┘                │
//! │                          │                                  │
//! │                ┌─────────▼─────────┐                        │
//! │                │   Orchestrator    │                        │
//! │                │  (Unified Entry)  │                        │
//! │                └───────────────────┘                        │
//! │                                                             │
//! └─────────────────────────────────────────────────────────────┘
//! ```
//!
//! # Modules
//!
//! ## Solvers (Low-level constraint solving)
//! - `solvers::simplex` - Linear arithmetic solver (Simplex algorithm)
//! - `solvers::z3` - Z3 SMT solver backend (optional, feature-gated)
//!
//! ## Analyzers (Semantic analysis)
//! - `analyzers::interval` - Interval/range tracking (open/closed bounds)
//! - `analyzers::constraint_prop` - Transitive constraint propagation
//! - `analyzers::dataflow` - Dataflow constraint propagation (SCCP integration)
//! - `analyzers::string` - String constraint solver (XSS/SQLi detection)
//! - `analyzers::array_bounds` - Array bounds checker (multi-dimensional)
//! - `analyzers::null_safety` - Null safety checker
//!
//! ## Checkers (Fast path checking)
//! - `checkers::lightweight` - Basic constraint checker (v1, <0.5ms)
//! - `checkers::enhanced` - Enhanced checker (v2, <1ms, integrates all analyzers)
//!
//! ## Orchestrator (Unified entry point)
//! - `orchestrator` - Routes to appropriate solver/analyzer based on complexity
//!
//! ## Concolic Testing (NEW)
//! - `concolic` - KLEE-style concolic execution for test generation

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Core Shared Types
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

use crate::features::smt::domain::ConstValue;

/// Path feasibility result
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PathFeasibility {
    /// Path is definitely feasible
    Feasible,
    /// Path is definitely infeasible (contradiction detected)
    Infeasible,
    /// Cannot determine (too complex or insufficient information)
    Unknown,
}

/// SCCP lattice value (for constant propagation integration)
#[derive(Debug, Clone, PartialEq)]
pub enum LatticeValue {
    /// Bottom (unreachable/undefined)
    Bottom,
    /// Constant value
    Constant(ConstValue),
    /// Top (non-constant/varies)
    Top,
}

impl LatticeValue {
    /// Check if value is a constant
    pub fn is_constant(&self) -> bool {
        matches!(self, LatticeValue::Constant(_))
    }

    /// Get constant value if available
    pub fn as_const(&self) -> Option<&ConstValue> {
        match self {
            LatticeValue::Constant(v) => Some(v),
            _ => None,
        }
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Solvers (Low-level constraint solving)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pub mod solvers;

pub use solvers::{ConstraintSolver, Model, ModelValue, SolverResult};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Analyzers (Semantic analysis)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pub mod analyzers {
    //! Semantic analyzers for constraint tracking

    // Interval tracking
    pub mod interval {
        //! Interval/range tracking with open/closed bounds
        pub use super::super::interval_tracker::*;
        pub use super::super::range_analysis::*;
    }

    // Constraint propagation
    pub mod constraint_prop {
        //! Transitive constraint propagation
        pub use super::super::constraint_propagator::*;
    }

    // Inter-variable relationships (NEW: Phase 1)
    pub mod inter_variable {
        //! Inter-variable relationship tracking with transitive inference
        pub use super::super::inter_variable_tracker::*;
    }

    // Arithmetic operations (NEW: Phase 2)
    pub mod arithmetic {
        //! Limited arithmetic reasoning for linear expressions
        pub use super::super::arithmetic_expression_tracker::*;
    }

    // Advanced string theory (NEW: Phase 3)
    pub mod advanced_string {
        //! Advanced string operations beyond basic pattern matching
        pub use super::super::advanced_string_theory::*;
    }

    // Dataflow analysis
    pub mod dataflow {
        //! Dataflow constraint propagation (SCCP integration)
        pub use super::super::dataflow_propagator::*;
    }

    // String analysis
    pub mod string {
        //! String constraint solver (security-focused)
        pub use super::super::string_constraint_solver::*;
    }

    // Array bounds
    pub mod array_bounds {
        //! Array bounds checker (multi-dimensional)
        pub use super::super::array_bounds_checker::*;
    }

    // Null safety
    pub mod null_safety {
        //! Null safety checker
        pub use super::super::null_safety::*;
    }

    // Fallback strategy (NEW: Z3 Integration)
    pub mod fallback {
        //! Z3 fallback strategy for complex constraints
        pub use super::super::fallback_strategy::*;
    }
}

// Re-export analyzers at top level for convenience
pub use analyzers::advanced_string::{
    AdvancedStringTheory, IndexOfConstraint, StringOperation, SubstringConstraint,
};
pub use analyzers::arithmetic::{ArithmeticExpressionTracker, IntervalBound, LinearExpression};
pub use analyzers::array_bounds::{ArrayBoundsChecker, ArraySize, IndexConstraint};
pub use analyzers::constraint_prop::{ConstraintPropagator, ConstraintPropagatorConfig};
pub use analyzers::dataflow::{BinaryOperator, DataflowConstraintPropagator, Definition};
pub use analyzers::fallback::{FallbackDecision, FallbackReason, FallbackStats, FallbackStrategy};
pub use analyzers::inter_variable::{InterVariableTracker, Relation};
pub use analyzers::interval::{IntInterval, IntRange, IntervalTracker, RangeAnalyzer};
pub use analyzers::null_safety::{DereferenceCheck, NullSafetyChecker, Nullability};
pub use analyzers::string::{StringConstraintSolver, StringLengthBound, StringPattern};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Checkers (Fast path checking)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pub mod checkers {
    //! Fast constraint checkers

    // Lightweight checker v1 (basic, <0.5ms)
    pub mod lightweight {
        //! Basic constraint checker (v1)
        pub use super::super::lightweight_checker::*;
    }

    // Enhanced checker v2 (comprehensive, <1ms)
    pub mod enhanced {
        //! Enhanced constraint checker (v2, SOTA)
        pub use super::super::lightweight_checker_v2::*;
    }
}

// Re-export checkers at top level
pub use checkers::enhanced::EnhancedConstraintChecker;
pub use checkers::lightweight::LightweightConstraintChecker;

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Orchestrators (Unified entry points)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pub mod orchestrator; // Original orchestrator
pub mod unified_orchestrator; // NEW: Intelligent routing + Z3 incremental

pub use orchestrator::{HitRates, OrchestratorStats, SmtOrchestrator};
pub use unified_orchestrator::{
    ComplexityLevel, PerformanceBudget, UnifiedOrchestrator, UnifiedStats,
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Concolic Testing (KLEE-style)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pub mod concolic;

pub use concolic::{
    BranchCondition, ConcolicConfig, ConcolicEngine, ConcolicState, ConcreteValue, ErrorKind,
    ErrorReport, ExplorationResult, ExplorationStats, SearchStrategy, TestExpectation, TestInput,
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Internal modules (implementation details)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// These are implementation modules, exposed through public facades above
mod advanced_string_theory; // NEW: Phase 3
mod arithmetic_expression_tracker; // NEW: Phase 2
mod array_bounds_checker;
mod constraint_propagator;
mod dataflow_propagator;
mod fallback_strategy;
mod inter_variable_tracker;
mod interval_tracker;
mod lightweight_checker;
mod lightweight_checker_v2;
mod null_safety;
mod range_analysis;
mod string_constraint_solver; // NEW: Z3 Fallback
