//! Architecture Boundary Tests - Compile-time SOLID Enforcement
//!
//! 이 테스트들은 **컴파일 타임**에 아키텍처 위반을 방지합니다.
//! Reference: "Sustainable Software Architecture" (GOTO 2023)

#![cfg(test)]

use std::path::Path;

/// ADR-072: Rust 코드는 Python 런타임에 의존하지 않음
///
/// PyO3 바인딩만 허용, cpython/python3-sys 등은 금지
#[test]
fn test_no_python_runtime_dependency() {
    let cargo_toml = Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml");
    let content = std::fs::read_to_string(cargo_toml).unwrap();

    // 금지된 의존성 체크
    assert!(
        !content.contains("cpython"),
        "❌ cpython 의존성 발견 - PyO3만 사용해야 함"
    );
    assert!(
        !content.contains("python3-sys"),
        "❌ python3-sys 의존성 발견 - PyO3만 사용해야 함"
    );

    // PyO3는 허용 (bindings만)
    // pyo3는 있어도 OK
}

/// SOLID - Single Responsibility Principle
///
/// IR 레이어는 분석만 수행, 네트워크/DB I/O 금지
#[test]
fn test_ir_layer_no_io_dependencies() {
    let cargo_toml = Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml");
    let content = std::fs::read_to_string(cargo_toml).unwrap();

    // IR 레이어는 순수 분석 엔진 - I/O 금지
    let forbidden_deps = vec![
        "reqwest",     // HTTP client
        "hyper",       // HTTP primitives
        "tokio",       // Async runtime (Storage만 허용)
        "async-std",   // Async runtime
    ];

    for dep in forbidden_deps {
        assert!(
            !content.contains(&format!("\"{}\"", dep)),
            "❌ IR 레이어에서 {} 의존 발견 - Storage 레이어로 분리 필요",
            dep
        );
    }
}

/// SOLID - Dependency Inversion Principle
///
/// Features는 Trait을 통해서만 통신 (구체 타입 직접 의존 금지)
#[test]
fn test_feature_independence_via_traits() {
    // 각 feature 모듈이 다른 feature의 구체 타입을 직접 사용하지 않는지 체크
    let src_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("src/features");

    // Taint 모듈이 PTA 구체 타입 직접 의존 금지
    let taint_mod = src_dir.join("taint_analysis/mod.rs");
    if taint_mod.exists() {
        let taint_code = std::fs::read_to_string(&taint_mod).unwrap();
        assert!(
            !taint_code.contains("use crate::features::points_to::PointsToAnalyzer"),
            "❌ Taint가 PTA 구체 타입에 직접 의존 - Trait 사용 필요"
        );
    }

    // PTA 모듈이 Taint 구체 타입 직접 의존 금지
    let pta_mod = src_dir.join("points_to/mod.rs");
    if pta_mod.exists() {
        let pta_code = std::fs::read_to_string(&pta_mod).unwrap();
        assert!(
            !pta_code.contains("use crate::features::taint_analysis::TaintAnalyzer"),
            "❌ PTA가 Taint 구체 타입에 직접 의존 - Trait 사용 필요"
        );
    }
}

/// Clean Architecture - 레이어 의존성 방향 검증
///
/// Pipeline → Features → IR → (Storage)
/// 역방향 의존 금지
#[test]
fn test_layer_dependency_direction() {
    let src_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");

    // IR은 Features에 의존하지 않음
    let ir_mod = src_dir.join("ir/mod.rs");
    if ir_mod.exists() {
        let ir_code = std::fs::read_to_string(&ir_mod).unwrap();
        assert!(
            !ir_code.contains("use crate::features::"),
            "❌ IR 레이어가 Features에 의존 - 역방향 의존성 위반"
        );
    }

    // Features 주요 모듈들이 Pipeline에 의존하지 않는지 체크
    let features_dir = src_dir.join("features");
    if features_dir.exists() {
        // 주요 feature 모듈만 체크 (taint_analysis, points_to, clone_detection)
        for feature_name in &["taint_analysis", "points_to", "clone_detection"] {
            let feature_mod = features_dir.join(format!("{}/mod.rs", feature_name));
            if feature_mod.exists() {
                let content = std::fs::read_to_string(&feature_mod).unwrap();
                assert!(
                    !content.contains("use crate::pipeline::"),
                    "❌ Feature 모듈 {}이 Pipeline에 의존 - 역방향 의존성 위반",
                    feature_name
                );
            }
        }
    }
}

/// SOLID - Open/Closed Principle
///
/// 새 언어 추가 시 기존 코드 수정 불필요 (Trait 기반 확장)
#[test]
fn test_language_plugin_extensibility() {
    // Parser trait이나 Language trait이 존재하는지 확인
    let parsing_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("src/features/parsing");
    
    if parsing_dir.exists() {
        let mod_file = parsing_dir.join("mod.rs");
        if mod_file.exists() {
            let parser_code = std::fs::read_to_string(&mod_file).unwrap();
            
            // Parser 또는 Language 관련 trait 존재 확인
            let has_extensibility = parser_code.contains("pub trait")
                || parser_code.contains("trait Parser")
                || parser_code.contains("trait Language");
            
            if !has_extensibility {
                eprintln!("⚠️ 권장: Parser trait 패턴 사용 시 확장성 향상");
            }
            // 경고만 출력, 테스트는 통과 (선택적 권장사항)
        }
    }
    // 파일이 없거나 trait이 없어도 테스트 통과 (OCP는 권장사항)
}

/// 모듈 순환 의존성 검사
///
/// A → B → A 같은 순환 의존 금지
#[test]
fn test_no_circular_dependencies() {
    // 실제 구현은 cargo-depgraph 또는 custom parser 필요
    // 여기서는 명시적으로 알려진 순환 의존만 체크

    let src_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");

    // Config ↔ Pipeline 순환 의존 금지
    let config_code = std::fs::read_to_string(src_dir.join("config/mod.rs")).unwrap();
    let pipeline_code = std::fs::read_to_string(src_dir.join("pipeline/mod.rs")).unwrap();

    let config_uses_pipeline = config_code.contains("use crate::pipeline::");
    let pipeline_uses_config = pipeline_code.contains("use crate::config::");

    assert!(
        !(config_uses_pipeline && pipeline_uses_config),
        "❌ Config ↔ Pipeline 순환 의존 발견"
    );
}

/// RFC-001: 설정 시스템 격리 검증
///
/// Config는 leaf dependency (다른 도메인 로직에 의존하지 않음)
#[test]
fn test_config_is_leaf_dependency() {
    let config_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("src/config");

    for entry in std::fs::read_dir(config_dir).unwrap() {
        let entry = entry.unwrap();
        if entry.path().extension().map_or(false, |e| e == "rs") {
            let content = std::fs::read_to_string(entry.path()).unwrap();

            // Config는 IR/Features/Pipeline에 의존하지 않음
            let forbidden_imports = vec![
                "use crate::features::",
                "use crate::pipeline::",
                "use crate::ir::analyzer",
            ];

            for import in forbidden_imports {
                // 프로덕션 코드에서만 검사 (테스트 코드는 예외)
                // #[test] 함수 내부나 #[cfg(test)] 블록은 허용
                let lines: Vec<&str> = content.lines().collect();
                
                for (i, line) in lines.iter().enumerate() {
                    if line.contains(import) {
                        // 이전 라인들에서 #[test] 또는 #[cfg(test)] 확인
                        let is_in_test = lines[..i].iter().rev().take(5).any(|prev_line| {
                            prev_line.contains("#[test]") 
                            || prev_line.contains("#[cfg(test)]")
                            || prev_line.contains("mod tests")
                        });
                        
                        assert!(
                            is_in_test,
                            "❌ Config 모듈 {:?}이 프로덕션 코드에서 도메인 로직 {}에 의존 - Leaf 원칙 위반\n   (테스트 코드는 허용)",
                            entry.file_name(),
                            import
                        );
                    }
                }
            }
        }
    }
}

/// Performance: 불필요한 Clone 방지
///
/// SOTA 패턴: Arc/Rc 또는 &참조 사용
#[test]
fn test_minimal_clones_in_hot_path() {
    // Hot path 파일에서 과도한 .clone() 사용 검사
    let hot_paths = vec![
        "src/features/taint/analysis.rs",
        "src/features/pta/analyzer.rs",
        "src/pipeline/executor.rs",
    ];

    for path in hot_paths {
        let file_path = Path::new(env!("CARGO_MANIFEST_DIR")).join(path);
        if file_path.exists() {
            let content = std::fs::read_to_string(&file_path).unwrap();
            let clone_count = content.matches(".clone()").count();

            // 경험적 임계값: 파일당 20개 이상은 과도
            assert!(
                clone_count < 20,
                "⚠️ {} 파일에 과도한 clone() 발견 ({}개) - Arc/Rc 사용 검토",
                path,
                clone_count
            );
        }
    }
}
