//! Feature modules - Each feature follows Hexagonal Architecture
//!
//! Each feature contains:
//! - domain/     - Pure business logic (no external dependencies)
//! - ports/      - Interface definitions (traits)
//! - application/ - Use cases
//! - infrastructure/ - External dependency implementations

pub mod data_flow;
pub mod flow_graph;
pub mod ir_generation;
pub mod parsing;
pub mod pdg;
pub mod slicing;
pub mod ssa;
pub mod taint_analysis;
pub mod type_resolution;
pub mod typestate; // RFC-003: Typestate Protocol Analysis

// RFC-RUST-ENGINE Phase 2: Framing Protocol
pub mod indexing;

// RFC-CHUNK: Hierarchical chunking for semantic search
pub mod chunking;

// RFC-062: Cross-File Resolution (12x faster)
pub mod cross_file;

// RFC-SOTA: Points-to Analysis (10-50x faster than Python)
pub mod points_to;

// RFC-071: Query Engine with fluent DSL (Python-like DX in Rust)
pub mod query_engine;

// SOTA: Heap Analysis - Memory Safety & Security (Port from Python 11,206 lines)
pub mod heap_analysis;

// RFC-072: Multi-Layer Incremental Indexing with Selective Scope
pub mod multi_index;

// NEW: Concurrency Analysis - Async race condition and deadlock detection
pub mod concurrency_analysis;

// NEW: Effect Analysis - Purity tracking and side effect inference
pub mod effect_analysis;

// NEW: Git History Analysis - Blame, churn, and co-change analysis
pub mod git_history;

// RFC-073: File Watcher - SOTA Rust-native file system monitoring
pub mod file_watcher;

// RFC-074: SMT Engine (SOTA v2 Enhanced) - 90%+ accuracy, <1ms, Zero dependencies
pub mod smt;

// RFC-075: Graph Builder - SOTA IR→Graph conversion (10-20x faster than Python)
pub mod graph_builder;

// RFC-076: Clone Detection - SOTA 4-tier clone detection (Type-1 through Type-4)
pub mod clone_detection;

// RFC-028: Cost Analysis - Computational complexity analysis (O(n), O(n²), etc.)
pub mod cost_analysis;

// RFC-077: RepoMap - Repository structure mapping with importance scoring
pub mod repomap;

// RFC-078: Lexical Search - SOTA Native Tantivy implementation (12x faster than Python)
// - Native Tantivy (2x faster than Lucene, no FFI overhead)
// - 3-gram + CamelCase tokenizer for code identifiers
// - SQLite ChunkStore for file:line → chunk_id mapping
// - RRF fusion for hybrid search
// - Indexing: 500+ files/s (vs Python 40 files/s)
// - Search: < 5ms p95 (vs Python 15ms)
pub mod lexical; // ✅ Enabled - Lexical Search with Tantivy

// RFC-CONFIG-SYSTEM: Tiered Cache Configuration (L0 + L1 + L2)
// - L0: Session Cache (Bloom filter + LRU)
// - L1: Adaptive Cache (moka with TTL)
// - L2: Disk Cache (SQLite + optional RocksDB)
// - Background L2 writes for async persistence
pub mod cache; // ✅ Enabled - Tiered Cache System

// RFC-074: Storage Backend - MOVED to codegraph-storage workspace (RFC-100)
// See: ../codegraph-storage/ for commit-based persistent storage implementation
// This module kept for backward compatibility, will be removed in future versions
pub mod storage; // ⚠️ DEPRECATED - Use codegraph-storage crate

// NEW: Expression Builder - AST → Expression IR (L1)
// - tree-sitter visitor pattern
// - Multi-language support (Python, TypeScript, Java, Kotlin, Rust, Go)
// - Automatic data flow tracking (reads/defines)
// - Heap access detection (obj.field, arr[index])
// - Parent/child relationship tracking
pub mod expression_builder; // ✅ NEW - L1 Expression IR extraction

// NEW: Progressive Lowering - L1 (Expression IR) → L2 (Node IR)
// - MLIR-style multi-level IR transformation
// - Semantic preservation (high-level info available at all levels)
// - Explicit data flow edges (READS, WRITES, CONTROLS)
// - SSA-friendly Node IR generation
pub mod lowering; // ✅ NEW - L1→L2 Progressive Lowering
