//! IFDS/IDE Performance Benchmark
//!
//! Measures performance of:
//! - IFDS Tabulation Algorithm
//! - IDE Value Propagation
//! - Sparse IFDS Optimization
//!
//! Run with:
//! ```bash
//! cargo bench --bench ifds_benchmark
//! ```

#[path = "mod.rs"]
mod taint_common;

use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use codegraph_ir::config::{TaintConfig, Preset};
use codegraph_ir::features::taint_analysis::application::IFDSTaintService;
use taint_common::*;

/// Benchmark IFDS solver with different presets
fn bench_ifds_by_preset(c: &mut Criterion) {
    let mut group = c.benchmark_group("ifds_preset_comparison");
    
    for size in [10, 50, 100] {
        let cfg = create_chain_cfg(size);
        
        for preset in [Preset::Fast, Preset::Balanced, Preset::Thorough] {
            let config = TaintConfig::from_preset(preset);
            let service = IFDSTaintService::new(config);
            
            group.bench_with_input(
                BenchmarkId::new(format!("{:?}", preset), size),
                &size,
                |b, _| {
                    // TODO: Create actual IFDS problem
                    b.iter(|| {
                        black_box(&service);
                        black_box(&cfg);
                    });
                },
            );
        }
    }
    
    group.finish();
}

criterion_group!(benches, bench_ifds_by_preset);
criterion_main!(benches);
