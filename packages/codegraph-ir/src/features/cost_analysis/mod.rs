//! RFC-028: Cost Analysis
//!
//! Analyzes computational complexity of functions by:
//! - Finding loops in CFG
//! - Inferring loop bounds
//! - Calculating Big-O complexity
//! - Identifying performance hotspots
//!
//! # Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────┐
//! │ Domain Layer                            │
//! │  - ComplexityClass (O(n), O(n²), ...)  │
//! │  - BoundResult (loop bound inference)   │
//! │  - CostResult (analysis result)         │
//! └─────────────────────────────────────────┘
//!                   ▲
//!                   │
//! ┌─────────────────────────────────────────┐
//! │ Infrastructure Layer                    │
//! │  - CostAnalyzer (main analyzer)        │
//! │  - ComplexityCalculator (complexity)   │
//! └─────────────────────────────────────────┘
//! ```
//!
//! # Performance
//!
//! - **Target**: <10ms per function
//! - **Throughput**: 10-20x faster than Python
//! - **Complexity**: O(CFG blocks + edges)
//!
//! # Example
//!
//! ```rust,ignore
//! use codegraph_ir::features::cost_analysis::CostAnalyzer;
//!
//! let mut analyzer = CostAnalyzer::new(true);
//! let result = analyzer.analyze_function(
//!     &nodes,
//!     &cfg_blocks,
//!     &cfg_edges,
//!     "myapp.process_data"
//! )?;
//!
//! println!("Complexity: {}", result.complexity.as_str());
//! println!("Confidence: {:.2}", result.confidence);
//! ```

pub mod application;
pub mod domain;
pub mod infrastructure;

// Re-export application layer
pub use application::{CostAnalysisUseCase, CostAnalysisUseCaseImpl};

// Re-exports for convenience
pub use domain::{BoundResult, ComplexityClass, CostResult, Hotspot, InferenceMethod, Verdict};

// Re-export infrastructure (internal use - prefer application layer)
#[doc(hidden)]
pub use infrastructure::{ComplexityCalculator, CostAnalyzer};
