//! Taint Analysis Benchmarks
//!
//! Consolidated benchmarks for all taint analysis techniques:
//! - Legacy: Interprocedural taint (worklist-based)
//! - IFDS: IFDS tabulation algorithm
//! - IDE: IDE value propagation
//! - Sparse: Sparse IFDS optimization

pub mod fixtures;

use codegraph_ir::features::taint_analysis::infrastructure::{
    IFDSCFG, CFGEdge, CFGEdgeKind,
};
use std::collections::HashMap;

/// Create a simple chain CFG for testing
///
/// Structure: n0 → n1 → n2 → ... → nN
pub fn create_chain_cfg(size: usize) -> IFDSCFG {
    let mut cfg = IFDSCFG::new();
    
    cfg.add_entry(format!("n0"));
    
    for i in 0..size {
        let from = format!("n{}", i);
        let to = format!("n{}", i + 1);
        cfg.add_edge(CFGEdge::normal(from, to));
    }
    
    cfg.add_exit(format!("n{}", size));
    cfg
}

/// Create a diamond CFG for testing
///
/// Structure:
/// ```
///     n0
///    /  \
///   n1  n2
///    \  /
///     n3
/// ```
pub fn create_diamond_cfg() -> IFDSCFG {
    let mut cfg = IFDSCFG::new();
    
    cfg.add_entry("n0".to_string());
    cfg.add_edge(CFGEdge::normal("n0", "n1"));
    cfg.add_edge(CFGEdge::normal("n0", "n2"));
    cfg.add_edge(CFGEdge::normal("n1", "n3"));
    cfg.add_edge(CFGEdge::normal("n2", "n3"));
    cfg.add_exit("n3".to_string());
    
    cfg
}

/// Create an interprocedural CFG
///
/// Structure: main → call foo → return
pub fn create_interprocedural_cfg() -> IFDSCFG {
    let mut cfg = IFDSCFG::new();
    
    cfg.add_entry("main_entry".to_string());
    cfg.add_edge(CFGEdge::call("main_call", "foo_entry"));
    cfg.add_edge(CFGEdge::normal("foo_entry", "foo_body"));
    cfg.add_edge(CFGEdge::return_edge("foo_exit", "main_return", "main_call"));
    cfg.add_edge(CFGEdge::call_to_return("main_call", "main_return"));
    cfg.add_exit("main_exit".to_string());
    
    cfg
}
