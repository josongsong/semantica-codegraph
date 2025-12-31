#![no_main]

use libfuzzer_sys::fuzz_target;
use codegraph_ir::config::PipelineConfig;

fuzz_target!(|data: &[u8]| {
    // Convert bytes to string (may be invalid UTF-8)
    if let Ok(yaml_str) = std::str::from_utf8(data) {
        // Try to parse as YAML - should never panic
        let _ = PipelineConfig::from_yaml_str(yaml_str);
    }
});
