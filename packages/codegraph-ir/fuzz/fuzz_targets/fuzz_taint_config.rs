#![no_main]

use libfuzzer_sys::fuzz_target;
use codegraph_ir::config::{TaintConfig, Preset};
use arbitrary::Arbitrary;

#[derive(Arbitrary, Debug)]
struct FuzzTaintConfig {
    preset_idx: u8,
    max_depth: usize,
    max_paths: usize,
    worklist_iterations: usize,
    use_points_to: bool,
    track_sanitizers: bool,
}

fuzz_target!(|input: FuzzTaintConfig| {
    let preset = match input.preset_idx % 4 {
        0 => Preset::Fast,
        1 => Preset::Balanced,
        2 => Preset::Thorough,
        _ => Preset::Custom,
    };

    let config = TaintConfig::from_preset(preset)
        .max_depth(input.max_depth)
        .max_paths(input.max_paths)
        .worklist_max_iterations(input.worklist_iterations)
        .use_points_to(input.use_points_to)
        .track_sanitizers(input.track_sanitizers);

    // Validation should never panic
    let _ = config.validate();

    // to_yaml should never panic
    if config.validate().is_ok() {
        let yaml = config.to_yaml();
        if let Ok(yaml_str) = yaml {
            // Roundtrip should be consistent
            let _ = TaintConfig::from_yaml_str(&yaml_str);
        }
    }
});
