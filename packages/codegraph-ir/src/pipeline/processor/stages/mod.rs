//! Pipeline stages (L1-L7)
//!
//! Each stage represents a layer in the analysis pipeline:
//! - L1-L2: IR generation and occurrences (ir_generation)
//! - L3: Flow graphs and type resolution (flow_types)
//! - L4-L5: Data flow and SSA (data_flow)
//! - L6: Advanced analyses - PDG, taint, points-to (advanced)
//! - L7: Heap analysis - memory safety, security (heap)

pub mod advanced;
pub mod data_flow;
pub mod flow_types;
pub mod heap;
pub mod ir_generation;

// Re-export all IR generation functions
pub use ir_generation::{
    generate_occurrences, process_class, process_function, process_with_bfg, traverse_node,
};

// Re-export flow/type functions
pub use flow_types::{extract_bfg_graphs, extract_bfg_graphs_with_nodes};

// Re-export data flow functions
pub use data_flow::{build_dfg_graphs, build_ssa_graphs, build_ssa_graphs_with_extraction};

// Re-export advanced analysis functions
pub use advanced::{build_pdg_summaries, run_points_to_analysis, run_taint_analysis};

// Re-export heap analysis functions
pub use heap::run_heap_analysis;
