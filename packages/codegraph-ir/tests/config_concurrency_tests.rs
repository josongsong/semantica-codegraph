//! Concurrency tests for RFC-CONFIG
//!
//! Tests thread-safety and concurrent access patterns using Loom.
//! These tests ensure the config system is safe under concurrent usage.

use codegraph_ir::config::*;

// ============================================================================
// Loom-based Tests (Formal Verification)
// ============================================================================

#[cfg(loom)]
mod loom_tests {
    use super::*;
    use loom::sync::Arc;
    use loom::thread;

    #[test]
    fn concurrent_config_build() {
        loom::model(|| {
            let preset = Arc::new(Preset::Balanced);

            let handles: Vec<_> = (0..2)
                .map(|_| {
                    let preset = Arc::clone(&preset);
                    thread::spawn(move || {
                        let config = PipelineConfig::preset(*preset).build();
                        assert!(config.is_ok());
                    })
                })
                .collect();

            for handle in handles {
                handle.join().unwrap();
            }
        });
    }

    #[test]
    fn concurrent_yaml_parse() {
        loom::model(|| {
            let yaml = Arc::new(
                r#"
            preset: Balanced
            stages:
              taint: true
              pta: true
            taint:
              max_depth: 50
            "#
                .to_string(),
            );

            let handles: Vec<_> = (0..2)
                .map(|_| {
                    let yaml = Arc::clone(&yaml);
                    thread::spawn(move || {
                        let config = PipelineConfig::from_yaml_str(&yaml);
                        assert!(config.is_ok());
                    })
                })
                .collect();

            for handle in handles {
                handle.join().unwrap();
            }
        });
    }

    #[test]
    fn concurrent_config_modification() {
        loom::model(|| {
            let handles: Vec<_> = (0..2)
                .map(|i| {
                    thread::spawn(move || {
                        let depth = 50 + i * 10;
                        let config = PipelineConfig::preset(Preset::Fast)
                            .taint(|c| c.max_depth(depth))
                            .build();
                        assert!(config.is_ok());
                    })
                })
                .collect();

            for handle in handles {
                handle.join().unwrap();
            }
        });
    }

    #[test]
    fn concurrent_validation() {
        loom::model(|| {
            let config = Arc::new(
                TaintConfig::from_preset(Preset::Fast)
                    .max_depth(100)
                    .max_paths(1000),
            );

            let handles: Vec<_> = (0..2)
                .map(|_| {
                    let config = Arc::clone(&config);
                    thread::spawn(move || {
                        let result = config.validate();
                        assert!(result.is_ok());
                    })
                })
                .collect();

            for handle in handles {
                handle.join().unwrap();
            }
        });
    }
}

// ============================================================================
// Regular concurrency tests (without loom)
// ============================================================================

#[cfg(not(loom))]
mod stress_concurrency {
    use super::*;
    use std::sync::Arc;
    use std::thread;

    #[test]
    fn stress_concurrent_build_100_threads() {
        let handles: Vec<_> = (0..100)
            .map(|i| {
                thread::spawn(move || {
                    let preset = match i % 3 {
                        0 => Preset::Fast,
                        1 => Preset::Balanced,
                        _ => Preset::Thorough,
                    };
                    let config = PipelineConfig::preset(preset).build();
                    assert!(config.is_ok());
                })
            })
            .collect();

        for handle in handles {
            handle.join().unwrap();
        }
    }

    #[test]
    fn stress_concurrent_yaml_parse() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Barrier;

        let yaml_content = r#"version: 1
preset: Balanced
stages:
  taint: true
  pta: true
overrides:
  taint:
    max_depth: 50
"#;

        // Write YAML to temp file once
        let yaml_path = "/tmp/test_concurrent_config.yaml";
        std::fs::write(yaml_path, yaml_content).unwrap();

        let counter = Arc::new(AtomicUsize::new(0));
        let barrier = Arc::new(Barrier::new(50));

        let handles: Vec<_> = (0..50)
            .map(|_| {
                let counter = Arc::clone(&counter);
                let barrier = Arc::clone(&barrier);
                let yaml_path = yaml_path.to_string();
                thread::spawn(move || {
                    barrier.wait(); // All threads wait here
                    let config = PipelineConfig::from_yaml(&yaml_path);
                    match config {
                        Ok(_) => {
                            counter.fetch_add(1, Ordering::SeqCst);
                        }
                        Err(e) => {
                            eprintln!("Parse error: {:?}", e);
                        }
                    }
                })
            })
            .collect();

        for handle in handles {
            handle.join().unwrap();
        }

        std::fs::remove_file(yaml_path).ok();
        assert_eq!(counter.load(Ordering::SeqCst), 50);
    }

    #[test]
    fn stress_concurrent_validation() {
        let config = Arc::new(
            PipelineConfig::preset(Preset::Balanced)
                .taint(|c| c.max_depth(100).max_paths(1000))
                .build()
                .unwrap(),
        );

        let handles: Vec<_> = (0..100)
            .map(|_| {
                let config = Arc::clone(&config);
                thread::spawn(move || {
                    let inner = config.as_inner();
                    let _ = inner.describe();
                })
            })
            .collect();

        for handle in handles {
            handle.join().unwrap();
        }
    }

    #[test]
    fn stress_mixed_operations() {
        use std::sync::atomic::{AtomicUsize, Ordering};

        let success_count = Arc::new(AtomicUsize::new(0));

        let handles: Vec<_> = (0..200)
            .map(|i| {
                let success_count = Arc::clone(&success_count);
                thread::spawn(move || {
                    let result = match i % 4 {
                        0 => {
                            // Build from preset
                            PipelineConfig::preset(Preset::Fast).build().map(|_| ())
                        }
                        1 => {
                            // Build with override
                            PipelineConfig::preset(Preset::Balanced)
                                .taint(|c| c.max_depth(50))
                                .build()
                                .map(|_| ())
                        }
                        2 => {
                            // Validate config
                            let cfg = TaintConfig::from_preset(Preset::Fast);
                            cfg.validate()
                        }
                        _ => {
                            // Build with custom settings
                            PipelineConfig::preset(Preset::Thorough)
                                .pta(|c| c.auto_threshold(10000))
                                .build()
                                .map(|_| ())
                        }
                    };

                    if result.is_ok() {
                        success_count.fetch_add(1, Ordering::SeqCst);
                    }
                })
            })
            .collect();

        for handle in handles {
            handle.join().unwrap();
        }

        assert_eq!(success_count.load(Ordering::SeqCst), 200);
    }
}
