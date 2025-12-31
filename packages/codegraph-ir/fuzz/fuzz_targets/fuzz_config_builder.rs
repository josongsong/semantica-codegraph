#![no_main]

use libfuzzer_sys::fuzz_target;
use codegraph_ir::config::{PipelineConfig, Preset};
use arbitrary::Arbitrary;

#[derive(Arbitrary, Debug)]
struct FuzzInput {
    preset_idx: u8,
    taint_depth: usize,
    taint_paths: usize,
    pta_threshold: usize,
    chunk_max: usize,
    chunk_min: usize,
    enable_taint: bool,
    enable_pta: bool,
    enable_clone: bool,
}

fuzz_target!(|input: FuzzInput| {
    let preset = match input.preset_idx % 4 {
        0 => Preset::Fast,
        1 => Preset::Balanced,
        2 => Preset::Thorough,
        _ => Preset::Custom,
    };

    let mut builder = PipelineConfig::preset(preset);

    // Apply random stage overrides
    if input.enable_taint {
        builder = builder.stages(|s| s.enable(StageId::Taint));
        builder = builder.taint(|c| {
            c.max_depth(input.taint_depth.min(1000).max(1))
                .max_paths(input.taint_paths.min(100000).max(1))
        });
    }

    if input.enable_pta {
        builder = builder.stages(|s| s.enable(StageId::Pta));
        builder = builder.pta(|c| {
            c.auto_threshold(input.pta_threshold.min(1_000_000).max(100))
        });
    }

    if input.enable_clone {
        builder = builder.stages(|s| s.enable(StageId::Clone));
    }

    builder = builder.chunking(|c| {
        c.max_chunk_size(input.chunk_max.min(10000).max(100))
            .min_chunk_size(input.chunk_min.min(5000).max(50))
    });

    // Build should never panic - may fail validation
    let _ = builder.build();
});
