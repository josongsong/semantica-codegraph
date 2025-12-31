//! Pipeline orchestrator
//!
//! Coordinates all features into a unified processing pipeline.

use super::config::PipelineConfig;
use super::result::ProcessResult;
use crate::features::{
    data_flow::ports::DFGAnalyzer, flow_graph::ports::FlowAnalyzer,
    ir_generation::ports::IRGenerator, parsing::ports::Parser, ssa::ports::SSABuilder,
    type_resolution::ports::TypeResolver,
};
use crate::shared::models::{OccurrenceGenerator, Result};

/// Pipeline orchestrator
pub struct Orchestrator<P, G, F, T, D, S>
where
    P: Parser,
    G: IRGenerator,
    F: FlowAnalyzer,
    T: TypeResolver,
    D: DFGAnalyzer,
    S: SSABuilder,
{
    parser: P,
    ir_generator: G,
    flow_analyzer: F,
    type_resolver: T,
    dfg_analyzer: D,
    ssa_builder: S,
    config: PipelineConfig,
}

impl<P, G, F, T, D, S> Orchestrator<P, G, F, T, D, S>
where
    P: Parser,
    G: IRGenerator,
    F: FlowAnalyzer,
    T: TypeResolver,
    D: DFGAnalyzer,
    S: SSABuilder,
{
    pub fn new(
        parser: P,
        ir_generator: G,
        flow_analyzer: F,
        type_resolver: T,
        dfg_analyzer: D,
        ssa_builder: S,
        config: PipelineConfig,
    ) -> Self {
        Self {
            parser,
            ir_generator,
            flow_analyzer,
            type_resolver,
            dfg_analyzer,
            ssa_builder,
            config,
        }
    }

    /// Process a single file through the pipeline
    pub fn process(&self, source: &str, file_path: &str, repo_id: &str) -> Result<ProcessResult> {
        // L1: Parse
        let parsed = self.parser.parse(source, file_path)?;

        // L2: Generate IR
        let ir = self.ir_generator.generate(&parsed, repo_id)?;

        // L3a: Build Flow Graphs
        let (bfg, cfg) = if self.config.enable_flow_graph {
            let bfg = self.flow_analyzer.build_bfg(&ir)?;
            let cfg = self.flow_analyzer.build_cfg(&bfg)?;
            (bfg, cfg)
        } else {
            (Vec::new(), Vec::new())
        };

        // L3b: Resolve Types
        let types = if self.config.enable_type_resolution {
            self.type_resolver.resolve(&ir)?
        } else {
            Vec::new()
        };

        // L4: Build DFG
        let dfg = if self.config.enable_dfg {
            self.dfg_analyzer.build_dfg(&ir, &bfg)?
        } else {
            Vec::new()
        };

        // L5: Build SSA
        let ssa = if self.config.enable_ssa {
            self.ssa_builder.build_ssa(&ir, &dfg)?
        } else {
            Vec::new()
        };

        // 🚀 SOTA: Generate occurrences in L1 (instead of Python L2)
        let occurrences = if self.config.enable_occurrences {
            let mut gen = OccurrenceGenerator::new();
            gen.generate(&ir.nodes, &ir.edges)
        } else {
            Vec::new()
        };

        Ok(ProcessResult {
            ir,
            bfg,
            cfg,
            types,
            dfg,
            ssa,
            occurrences,
        })
    }
}
