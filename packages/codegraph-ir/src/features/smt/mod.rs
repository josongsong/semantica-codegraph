//! SMT (Satisfiability Modulo Theories) Module
//!
//! Provides constraint checking and path feasibility analysis for security analysis.
//!
//! ## Features
//!
//! - **Lightweight Constraint Checker**: Basic path feasibility without Z3
//! - **SCCP Integration**: Leverages constant propagation results
//! - **Sanitizer Detection**: Pattern-based sanitizer effect modeling
//! - **Path Condition Modeling**: Constraint representation and evaluation
//!
//! ## Architecture
//!
//! ```text
//! SMT
//! ├── domain/               # Domain models
//! │   ├── path_condition    # Path constraints
//! │   └── sanitizer_db      # Sanitizer patterns
//! └── infrastructure/       # Implementation
//!     └── lightweight_checker # Constraint checker
//! ```
//!
//! ## Usage
//!
//! ```text
//! use codegraph_ir::features::smt::{
//!     LightweightConstraintChecker,
//!     PathCondition,
//!     ConstValue,
//!     PathFeasibility,
//! };
//!
//! let mut checker = LightweightConstraintChecker::new();
//!
//! // Add SCCP constant: x = 5
//! checker.add_sccp_value(
//!     "x".to_string(),
//!     LatticeValue::Constant(ConstValue::Int(5)),
//! );
//!
//! // Check path: x < 10
//! let conditions = vec![
//!     PathCondition::lt("x".to_string(), ConstValue::Int(10)),
//! ];
//!
//! assert_eq!(
//!     checker.is_path_feasible(&conditions),
//!     PathFeasibility::Feasible
//! );
//! ```
//!
//! ## Integration with Security Analysis
//!
//! The SMT module is designed to integrate with taint analysis for:
//!
//! 1. **False Positive Reduction**: Eliminate infeasible taint paths
//! 2. **Sanitizer Verification**: Verify sanitizers actually block taint
//! 3. **Path-Sensitive Analysis**: Track constraints along execution paths

pub mod application;
pub mod domain;
pub mod infrastructure;

// Re-export application layer
pub use application::{SmtUseCase, SmtUseCaseImpl};

// Re-exports for convenience

// Domain models
pub use domain::{
    ComparisonOp, ConstValue, Constraint, PathCondition, SanitizerDB, SanitizerEffect, TaintType,
    Theory, VarId,
};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{
    BinaryOperator,
    ConcolicConfig,
    ConcolicEngine,
    // RFC-001: Externalized Configs
    ConstraintPropagator,
    ConstraintPropagatorConfig,
    ConstraintSolver,
    DataflowConstraintPropagator,
    Definition,
    HitRates,
    LatticeValue,
    LightweightConstraintChecker,
    Model,
    ModelValue,
    OrchestratorStats,
    PathFeasibility,
    SearchStrategy,
    SmtOrchestrator,
    SolverResult,
};
