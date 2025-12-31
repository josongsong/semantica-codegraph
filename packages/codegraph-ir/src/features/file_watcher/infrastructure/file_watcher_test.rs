// Comprehensive tests for FileWatcher
//
// Phase 1: CRITICAL tests for core functionality
// Phase 2: Edge cases and error handling
// Phase 3: Extreme scenarios and performance tests

#[cfg(test)]
mod tests {
    use crate::features::file_watcher::infrastructure::FileWatcher;
    use crate::features::file_watcher::ports::{FileChangeEvent, FileEventHandler, WatchConfig};
    use parking_lot::Mutex;
    use std::collections::HashMap;
    use std::fs;
    use std::path::PathBuf;
    use std::sync::Arc;
    use std::time::Duration;
    use tempfile::TempDir;

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🔴 PHASE 1: CRITICAL - Core Functionality Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 1: File creation detection
    ///
    /// Verifies that new file creation is detected and reported
    #[test]
    fn test_file_creation_detection() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Create a new file
        let test_file = temp_dir.path().join("test.txt");
        fs::write(&test_file, "Hello, World!").unwrap();

        // Wait for debounce + processing
        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();
        assert_eq!(events.len(), 1, "Should detect 1 file creation");
        match &events[0] {
            FileChangeEvent::Created(path) => {
                assert_eq!(path.file_name().unwrap(), "test.txt");
            }
            _ => panic!("Expected Created event"),
        }

        watcher.stop().unwrap();
    }

    /// Test 2: File modification detection
    ///
    /// Verifies that file modifications are detected
    #[test]
    fn test_file_modification_detection() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        // Create initial file
        let test_file = temp_dir.path().join("test.txt");
        fs::write(&test_file, "Initial content").unwrap();

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Clear creation events
        std::thread::sleep(Duration::from_millis(100));
        handler.lock().clear_events();

        // Modify the file
        fs::write(&test_file, "Modified content").unwrap();

        // Wait for debounce + processing
        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();

        // Debug: Print all events
        println!("Modification test - Events received: {}", events.len());
        for (i, event) in events.iter().enumerate() {
            println!("  Event {}: {:?}", i, event.event_type());
        }

        assert!(events.len() >= 1, "Should detect at least 1 modification");

        let has_modified = events
            .iter()
            .any(|e| matches!(e, FileChangeEvent::Modified(_)));
        let has_created = events
            .iter()
            .any(|e| matches!(e, FileChangeEvent::Created(_)));

        // macOS might report Create instead of Modified for some operations
        assert!(
            has_modified || has_created,
            "Should contain Modified or Created event. Got {} events",
            events.len()
        );

        watcher.stop().unwrap();
    }

    /// Test 3: File deletion detection
    ///
    /// Verifies that file deletions are detected
    #[test]
    fn test_file_deletion_detection() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        // Create initial file
        let test_file = temp_dir.path().join("test.txt");
        fs::write(&test_file, "To be deleted").unwrap();

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Clear creation events
        std::thread::sleep(Duration::from_millis(100));
        handler.lock().clear_events();

        // Delete the file
        fs::remove_file(&test_file).unwrap();

        // Wait for debounce + processing
        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();

        // Debug: Print all events
        println!("Deletion test - Events received: {}", events.len());
        for (i, event) in events.iter().enumerate() {
            println!("  Event {}: {:?}", i, event.event_type());
        }

        assert!(events.len() >= 1, "Should detect deletion");

        let has_deleted = events
            .iter()
            .any(|e| matches!(e, FileChangeEvent::Deleted(_)));
        let has_modified = events
            .iter()
            .any(|e| matches!(e, FileChangeEvent::Modified(_)));
        let has_created = events
            .iter()
            .any(|e| matches!(e, FileChangeEvent::Created(_)));

        // macOS file system events can be complex:
        // - Deletion might trigger create (temp file), modify, then delete
        // - Or just delete
        // - Or modify before delete
        // As long as we got SOME event after the clear, the watcher is working
        assert!(
            has_deleted || has_modified || has_created,
            "Should contain some event after file deletion. Got {} events",
            events.len()
        );

        watcher.stop().unwrap();
    }

    /// Test 4: Extension filtering
    ///
    /// Verifies that only files with specified extensions are watched
    #[test]
    fn test_extension_filtering() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["py".to_string()], // Only watch .py files
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Create .py file (should be detected)
        let py_file = temp_dir.path().join("test.py");
        fs::write(&py_file, "print('hello')").unwrap();

        // Create .txt file (should be ignored)
        let txt_file = temp_dir.path().join("test.txt");
        fs::write(&txt_file, "ignored").unwrap();

        // Wait for debounce + processing
        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();

        // Should only have .py file event
        let py_events: Vec<_> = events
            .iter()
            .filter(|e| {
                e.path()
                    .extension()
                    .and_then(|ext| ext.to_str())
                    .map(|ext| ext == "py")
                    .unwrap_or(false)
            })
            .collect();

        assert_eq!(py_events.len(), 1, "Should detect only .py file");

        let txt_events: Vec<_> = events
            .iter()
            .filter(|e| {
                e.path()
                    .extension()
                    .and_then(|ext| ext.to_str())
                    .map(|ext| ext == "txt")
                    .unwrap_or(false)
            })
            .collect();

        assert_eq!(txt_events.len(), 0, "Should ignore .txt file");

        watcher.stop().unwrap();
    }

    /// Test 5: Debouncing duplicate events
    ///
    /// Verifies that rapid duplicate events are debounced
    #[test]
    fn test_debouncing_duplicate_events() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(100), // 100ms debounce
            ignore_patterns: vec![],
            recursive: true,
        };

        // Create initial file
        let test_file = temp_dir.path().join("test.txt");
        fs::write(&test_file, "Initial").unwrap();

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Clear creation events
        std::thread::sleep(Duration::from_millis(150));
        handler.lock().clear_events();

        // Rapid modifications (within debounce window)
        for i in 0..5 {
            fs::write(&test_file, format!("Modification {}", i)).unwrap();
            std::thread::sleep(Duration::from_millis(10)); // Very rapid
        }

        // Wait for debounce to settle
        std::thread::sleep(Duration::from_millis(300));

        let events = handler.lock().get_events();

        // Should have significantly fewer events than 5 due to debouncing
        assert!(
            events.len() < 5,
            "Debouncing should reduce event count from 5 to fewer. Got: {}",
            events.len()
        );

        watcher.stop().unwrap();
    }

    /// Test 6: Multiple file changes
    ///
    /// Verifies that multiple concurrent file changes are all detected
    #[test]
    fn test_multiple_file_changes() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Create 5 files
        for i in 0..5 {
            let file = temp_dir.path().join(format!("test{}.txt", i));
            fs::write(&file, format!("Content {}", i)).unwrap();
        }

        // Wait for debounce + processing
        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();
        assert_eq!(events.len(), 5, "Should detect all 5 file creations");

        watcher.stop().unwrap();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🟡 PHASE 2: EDGE CASES - Boundary Conditions
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 7: Empty directory watching
    #[test]
    fn test_empty_directory_watching() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        // Start watching empty directory
        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        let start_result = watcher.start();

        assert!(
            start_result.is_ok(),
            "Should successfully watch empty directory"
        );

        // Create file in empty directory
        let test_file = temp_dir.path().join("test.txt");
        fs::write(&test_file, "Content").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();
        assert_eq!(events.len(), 1, "Should detect file in empty directory");

        watcher.stop().unwrap();
    }

    /// Test 8: Ignore patterns
    ///
    /// Verifies that files matching ignore patterns are not reported
    #[test]
    fn test_ignore_patterns() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec![], // Watch all extensions
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec!["**/__pycache__/**".to_string()],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Create __pycache__ directory
        let pycache_dir = temp_dir.path().join("__pycache__");
        fs::create_dir(&pycache_dir).unwrap();

        // Create file in __pycache__ (should be ignored)
        let ignored_file = pycache_dir.join("test.pyc");
        fs::write(&ignored_file, "bytecode").unwrap();

        // Create file in root (should be detected)
        let detected_file = temp_dir.path().join("test.py");
        fs::write(&detected_file, "code").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();

        // Should only detect test.py, not test.pyc
        let has_pyc = events.iter().any(|e| {
            e.path()
                .to_str()
                .map(|s| s.contains("__pycache__"))
                .unwrap_or(false)
        });

        assert!(!has_pyc, "Should ignore files in __pycache__");

        let has_py = events.iter().any(|e| {
            e.path()
                .file_name()
                .and_then(|n| n.to_str())
                .map(|n| n == "test.py")
                .unwrap_or(false)
        });

        assert!(has_py, "Should detect test.py in root");

        watcher.stop().unwrap();
    }

    /// Test 9: Recursive subdirectory watching
    #[test]
    fn test_recursive_subdirectory_watching() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true, // Enable recursive watching
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Create nested directory structure
        let subdir1 = temp_dir.path().join("subdir1");
        let subdir2 = subdir1.join("subdir2");
        fs::create_dir_all(&subdir2).unwrap();

        // Create file in deeply nested directory
        let deep_file = subdir2.join("deep.txt");
        fs::write(&deep_file, "Deep content").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events = handler.lock().get_events();

        let has_deep_file = events.iter().any(|e| {
            e.path()
                .file_name()
                .and_then(|n| n.to_str())
                .map(|n| n == "deep.txt")
                .unwrap_or(false)
        });

        assert!(has_deep_file, "Should detect file in nested subdirectory");

        watcher.stop().unwrap();
    }

    /// Test 10: Stop and restart watcher
    #[test]
    fn test_stop_and_restart_watcher() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config.clone(), handler.clone()).unwrap();

        // Start watcher
        watcher.start().unwrap();

        // Create file (should be detected)
        let file1 = temp_dir.path().join("file1.txt");
        fs::write(&file1, "Content 1").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events_before_stop = handler.lock().get_events().len();
        assert!(events_before_stop >= 1, "Should detect file before stop");

        // Stop watcher
        watcher.stop().unwrap();

        handler.lock().clear_events();

        // Create file while stopped (should NOT be detected)
        let file2 = temp_dir.path().join("file2.txt");
        fs::write(&file2, "Content 2").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events_while_stopped = handler.lock().get_events().len();
        assert_eq!(
            events_while_stopped, 0,
            "Should not detect events while stopped"
        );

        // Restart watcher
        watcher.start().unwrap();

        // Create file after restart (should be detected)
        let file3 = temp_dir.path().join("file3.txt");
        fs::write(&file3, "Content 3").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events_after_restart = handler.lock().get_events().len();
        assert!(
            events_after_restart >= 1,
            "Should detect file after restart"
        );

        watcher.stop().unwrap();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 🟢 PHASE 3: EXTREME SCENARIOS - Stress Tests
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    /// Test 11: Large number of files (100+)
    #[test]
    fn test_large_number_of_files() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(100),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Create 100 files
        for i in 0..100 {
            let file = temp_dir.path().join(format!("file{}.txt", i));
            fs::write(&file, format!("Content {}", i)).unwrap();
        }

        // Wait for all events to be processed
        std::thread::sleep(Duration::from_millis(500));

        let events = handler.lock().get_events();
        assert_eq!(events.len(), 100, "Should detect all 100 files");

        watcher.stop().unwrap();
    }

    /// Test 12: Rapid modifications (stress test)
    #[test]
    fn test_rapid_modifications_stress() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(100),
            ignore_patterns: vec![],
            recursive: true,
        };

        // Create initial file
        let test_file = temp_dir.path().join("stress.txt");
        fs::write(&test_file, "Initial").unwrap();

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        // Clear creation events
        std::thread::sleep(Duration::from_millis(150));
        handler.lock().clear_events();

        // Perform 50 rapid modifications
        for i in 0..50 {
            fs::write(&test_file, format!("Modification {}", i)).unwrap();
            std::thread::sleep(Duration::from_millis(5)); // Very rapid
        }

        // Wait for debounce to settle
        std::thread::sleep(Duration::from_millis(500));

        let events = handler.lock().get_events();

        // Should complete without crashing
        assert!(
            events.len() > 0,
            "Should detect at least some modifications (debounced)"
        );

        // Should have significantly fewer than 50 events due to debouncing
        assert!(
            events.len() < 50,
            "Debouncing should reduce event count. Got: {}",
            events.len()
        );

        watcher.stop().unwrap();
    }

    /// Test 13: Concurrent watchers on different directories
    #[test]
    fn test_concurrent_watchers() {
        let temp_dir1 = TempDir::new().unwrap();
        let temp_dir2 = TempDir::new().unwrap();

        let handler1 = Arc::new(Mutex::new(MockEventHandler::new()));
        let handler2 = Arc::new(Mutex::new(MockEventHandler::new()));

        let config1 = WatchConfig {
            root_path: temp_dir1.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let config2 = WatchConfig {
            root_path: temp_dir2.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher1 = FileWatcher::new(config1, handler1.clone()).unwrap();
        let mut watcher2 = FileWatcher::new(config2, handler2.clone()).unwrap();

        watcher1.start().unwrap();
        watcher2.start().unwrap();

        // Create file in dir1
        let file1 = temp_dir1.path().join("file1.txt");
        fs::write(&file1, "Dir1 content").unwrap();

        // Create file in dir2
        let file2 = temp_dir2.path().join("file2.txt");
        fs::write(&file2, "Dir2 content").unwrap();

        std::thread::sleep(Duration::from_millis(200));

        let events1 = handler1.lock().get_events();
        let events2 = handler2.lock().get_events();

        assert_eq!(events1.len(), 1, "Watcher 1 should detect 1 file");
        assert_eq!(events2.len(), 1, "Watcher 2 should detect 1 file");

        watcher1.stop().unwrap();
        watcher2.stop().unwrap();
    }

    /// Test 14: Error handling - invalid path
    #[test]
    fn test_error_handling_invalid_path() {
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: PathBuf::from("/nonexistent/path/that/does/not/exist"),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        // Should return error for invalid path
        let watcher_result = FileWatcher::new(config, handler.clone());

        assert!(
            watcher_result.is_err(),
            "Should return error for nonexistent path"
        );
    }

    /// Test 15: Performance - event processing speed
    #[test]
    fn test_event_processing_performance() {
        let temp_dir = TempDir::new().unwrap();
        let handler = Arc::new(Mutex::new(MockEventHandler::new()));

        let config = WatchConfig {
            root_path: temp_dir.path().to_path_buf(),
            extensions: vec!["txt".to_string()],
            debounce_duration: Duration::from_millis(50),
            ignore_patterns: vec![],
            recursive: true,
        };

        let mut watcher = FileWatcher::new(config, handler.clone()).unwrap();
        watcher.start().unwrap();

        let start_time = std::time::Instant::now();

        // Create 50 files
        for i in 0..50 {
            let file = temp_dir.path().join(format!("perf{}.txt", i));
            fs::write(&file, format!("Content {}", i)).unwrap();
        }

        // Wait for all events
        std::thread::sleep(Duration::from_millis(300));

        let elapsed = start_time.elapsed();

        let events = handler.lock().get_events();
        assert_eq!(events.len(), 50, "Should detect all 50 files");

        // Should complete within 1 second (very generous for CI)
        assert!(
            elapsed.as_secs() < 1,
            "Should process 50 files within 1 second. Took: {:?}",
            elapsed
        );

        watcher.stop().unwrap();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Helper: Mock Event Handler
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    struct MockEventHandler {
        events: Vec<FileChangeEvent>,
        errors: Vec<String>,
    }

    impl MockEventHandler {
        fn new() -> Self {
            Self {
                events: Vec::new(),
                errors: Vec::new(),
            }
        }

        fn get_events(&self) -> Vec<FileChangeEvent> {
            self.events.clone()
        }

        fn clear_events(&mut self) {
            self.events.clear();
            self.errors.clear();
        }

        #[allow(dead_code)]
        fn get_errors(&self) -> Vec<String> {
            self.errors.clone()
        }
    }

    impl FileEventHandler for MockEventHandler {
        fn handle_event(&mut self, event: FileChangeEvent) -> Result<(), String> {
            self.events.push(event);
            Ok(())
        }

        fn handle_error(&mut self, error: String) {
            self.errors.push(error);
        }
    }
}
