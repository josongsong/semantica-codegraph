//! Heap Analysis - SOTA Memory Safety & Security (Hexagonal Architecture)
//!
//! Port of Python heap analysis (11,206 lines) to Rust for performance.
//!
//! ## Hexagonal Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────────┐
//! │                    Application Layer                            │
//! │  ┌─────────────────────────────────────────────────────────┐   │
//! │  │ HeapAnalysisService, ContextSensitiveHeapService        │   │
//! │  └─────────────────────────────────────────────────────────┘   │
//! │                         ▲                                       │
//! │                         │ uses                                  │
//! │                         ▼                                       │
//! │  ┌─────────────────────────────────────────────────────────┐   │
//! │  │                   Domain Layer                          │   │
//! │  │ EscapeState, OwnershipState, HeapIssue, HeapObject      │   │
//! │  └─────────────────────────────────────────────────────────┘   │
//! │                         ▲                                       │
//! │                         │ defines                               │
//! │                         ▼                                       │
//! │  ┌─────────────────────────────────────────────────────────┐   │
//! │  │                   Ports Layer                           │   │
//! │  │ MemoryCheckerPort, EscapeAnalyzerPort, ...              │   │
//! │  └─────────────────────────────────────────────────────────┘   │
//! │                         ▲                                       │
//! │                         │ implements                            │
//! │                         ▼                                       │
//! │  ┌─────────────────────────────────────────────────────────┐   │
//! │  │                Infrastructure Layer                     │   │
//! │  │ NullCheckerAdapter, EscapeAnalyzerAdapter, ...          │   │
//! │  └─────────────────────────────────────────────────────────┘   │
//! └─────────────────────────────────────────────────────────────────┘
//! ```
//!
//! ## Academic SOTA
//! - **Separation Logic**: Reynolds (2002), O'Hearn (2004)
//! - **Symbolic Execution**: King (1976), Cadar et al. (2008)
//! - **Null Safety**: Fähndrich & Leino (2003), Chalin & James (2007)
//! - **Escape Analysis**: Choi et al. (1999)
//! - **Ownership**: Weiss et al. (2019) "Oxide"
//!
//! ## Industry SOTA
//! - **Meta Infer**: Bi-abduction, separation logic (C/C++/Java)
//! - **Microsoft SLAM**: Predicate abstraction
//! - **Coverity**: Pattern-based + symbolic execution
//! - **Kotlin**: Nullable types (T vs T?)
//! - **Rust**: Ownership system (compile-time memory safety)
//!
//! ## SOLID Compliance
//! - **S**: Each module has single responsibility
//! - **O**: New checkers implement MemoryCheckerPort trait
//! - **L**: All checkers are substitutable via trait
//! - **I**: Minimal port interfaces
//! - **D**: Application depends on ports, not infrastructure
//!
//! ## Features
//!
//! ### 1. Separation Logic (1,169 lines Python)
//! - Symbolic heap model: `x ↦ {f₁: v₁, ...}`
//! - Separating conjunction: `H₁ * H₂`
//! - Frame inference
//! - Entailment checking
//!
//! ### 2. Memory Safety Checkers (531 lines Python)
//! - **Null Dereference**: NPE detection with path sensitivity
//! - **Use-After-Free**: Lifetime tracking for heap objects
//! - **Double Free**: Free count tracking
//! - **Buffer Overflow**: Array bounds checking via SMT
//! - **Spatial Safety**: OOB pointer arithmetic detection
//!
//! ### 3. Deep Security (1,336 lines Python)
//! - **OWASP Top 10**: SQL Injection, XSS, CSRF, etc.
//! - Taint-based vulnerability scanning
//! - Sanitizer detection
//!
//! ## Usage
//!
//! ```rust,ignore
//! use heap_analysis::{
//!     application::HeapAnalysisService,
//!     infrastructure::*,
//! };
//! use config::HeapConfig;
//!
//! let config = HeapConfig::from_preset(Preset::Balanced);
//! let mut service = HeapAnalysisService::new(config)
//!     .with_memory_checker(Box::new(NullCheckerAdapter::new()))
//!     .with_memory_checker(Box::new(UAFCheckerAdapter::new()))
//!     .with_escape_analyzer(Box::new(EscapeAnalyzerAdapter::new()));
//!
//! let result = service.analyze(&nodes, &edges);
//! println!("Found {} issues", result.total_issues());
//! ```

// ═══════════════════════════════════════════════════════════════════════════
// Hexagonal Architecture Layers
// ═══════════════════════════════════════════════════════════════════════════

/// Application Layer - Use cases and services
pub mod application;

/// Domain Layer - Business logic and models
pub mod domain;

/// Ports Layer - Interface definitions
pub mod ports;

/// Infrastructure Layer - Port implementations
pub mod infrastructure;

// ═══════════════════════════════════════════════════════════════════════════
// Legacy Modules (to be migrated to infrastructure)
// ═══════════════════════════════════════════════════════════════════════════

pub mod separation_logic;
pub mod memory_safety;
pub mod security;
pub mod escape_analysis;
pub mod context_sensitive;
pub mod symbolic_memory;
pub mod ownership;

// ═══════════════════════════════════════════════════════════════════════════
// Re-exports
// ═══════════════════════════════════════════════════════════════════════════

// New hexagonal exports
pub use application::HeapAnalysisService;
pub use domain::{EscapeState, HeapIssue, HeapObject, IssueCategory, IssueSeverity, OwnershipState};
pub use ports::{
    EscapeAnalyzerPort, HeapAnalysisResult, HeapAnalyzerPort, MemoryCheckerPort,
    OwnershipAnalyzerPort, SecurityAnalyzerPort,
};
// Re-export infrastructure adapters
pub use infrastructure::{
    NullCheckerAdapter, UAFCheckerAdapter, DoubleFreeCheckerAdapter,
    BufferOverflowCheckerAdapter, SpatialCheckerAdapter,
    EscapeAnalyzerAdapter, OwnershipAnalyzerAdapter, SecurityAnalyzerAdapter,
};

// Legacy exports (for backward compatibility)
pub use separation_logic::*;
pub use memory_safety::*;
pub use security::*;
pub use escape_analysis::*;
pub use context_sensitive::*;
pub use symbolic_memory::*;
pub use ownership::*;
