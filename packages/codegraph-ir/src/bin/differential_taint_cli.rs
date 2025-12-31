/*
 * RFC-001: Differential Taint Analysis CLI
 *
 * Command-line tool for CI/CD integration.
 *
 * Usage:
 *   differential-taint-cli --repo . --base HEAD~1 --head HEAD
 *   differential-taint-cli --repo . --base main --head feature-branch
 *
 * Output formats:
 *   --format json    JSON output (for CI parsing)
 *   --format text    Human-readable output (default)
 *   --format github  GitHub Actions annotations
 */

use std::path::PathBuf;
use std::process::ExitCode;

use codegraph_ir::features::taint_analysis::infrastructure::differential::{
    GitDifferentialAnalyzer, Severity,
};

/// CLI arguments
struct Args {
    /// Repository path
    repo_path: PathBuf,

    /// Base commit reference
    base: String,

    /// Head commit reference
    head: String,

    /// Output format
    format: OutputFormat,

    /// Enable debug output
    debug: bool,

    /// Fail on high-severity regressions
    fail_on_high: bool,

    /// Enable parallel file analysis
    parallel: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum OutputFormat {
    Text,
    Json,
    GitHub,
}

impl Args {
    fn parse() -> Result<Self, String> {
        let args: Vec<String> = std::env::args().collect();

        let mut repo_path = PathBuf::from(".");
        let mut base = String::from("HEAD~1");
        let mut head = String::from("HEAD");
        let mut format = OutputFormat::Text;
        let mut debug = false;
        let mut fail_on_high = false;
        let mut parallel = false;

        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--repo" | "-r" => {
                    i += 1;
                    repo_path = PathBuf::from(&args[i]);
                }
                "--base" | "-b" => {
                    i += 1;
                    base = args[i].clone();
                }
                "--head" | "-h" => {
                    i += 1;
                    head = args[i].clone();
                }
                "--format" | "-f" => {
                    i += 1;
                    format = match args[i].as_str() {
                        "json" => OutputFormat::Json,
                        "github" => OutputFormat::GitHub,
                        "text" | _ => OutputFormat::Text,
                    };
                }
                "--debug" | "-d" => {
                    debug = true;
                }
                "--fail-on-high" => {
                    fail_on_high = true;
                }
                "--parallel" | "-p" => {
                    parallel = true;
                }
                "--help" => {
                    print_help();
                    std::process::exit(0);
                }
                _ => {}
            }
            i += 1;
        }

        Ok(Self {
            repo_path,
            base,
            head,
            format,
            debug,
            fail_on_high,
            parallel,
        })
    }
}

fn print_help() {
    println!(
        r#"
RFC-001 Differential Taint Analysis CLI

USAGE:
    differential-taint-cli [OPTIONS]

OPTIONS:
    -r, --repo <PATH>       Repository path (default: .)
    -b, --base <REF>        Base commit reference (default: HEAD~1)
    -h, --head <REF>        Head commit reference (default: HEAD)
    -f, --format <FORMAT>   Output format: text, json, github (default: text)
    -d, --debug             Enable debug output
    -p, --parallel          Enable parallel file analysis (5-10x faster)
    --fail-on-high          Exit with error on high-severity regressions
    --help                  Print this help

EXAMPLES:
    # Compare last commit
    differential-taint-cli --repo . --base HEAD~1 --head HEAD

    # Compare branches
    differential-taint-cli --repo . --base main --head feature-branch

    # CI/CD with JSON output
    differential-taint-cli --format json --fail-on-high

OUTPUT:
    Exit code 0: No high-severity regressions
    Exit code 1: High-severity regressions detected (with --fail-on-high)
"#
    );
}

fn main() -> ExitCode {
    let args = match Args::parse() {
        Ok(args) => args,
        Err(e) => {
            eprintln!("Error: {}", e);
            return ExitCode::FAILURE;
        }
    };

    if args.debug {
        eprintln!("[DEBUG] Repository: {}", args.repo_path.display());
        eprintln!("[DEBUG] Base: {}", args.base);
        eprintln!("[DEBUG] Head: {}", args.head);
    }

    // Create analyzer
    let mut analyzer = match GitDifferentialAnalyzer::new(&args.repo_path) {
        Ok(a) => a.with_debug(args.debug),
        Err(e) => {
            eprintln!("Error opening repository: {}", e);
            return ExitCode::FAILURE;
        }
    };

    // Run analysis (parallel or sequential)
    let result = if args.parallel {
        if args.debug {
            eprintln!("[DEBUG] Using parallel analysis");
        }
        match analyzer.compare_commits_parallel(&args.base, &args.head) {
            Ok(r) => r,
            Err(e) => {
                eprintln!("Analysis error: {}", e);
                return ExitCode::FAILURE;
            }
        }
    } else {
        if args.debug {
            eprintln!("[DEBUG] Using sequential analysis");
        }
        match analyzer.compare_commits(&args.base, &args.head) {
            Ok(r) => r,
            Err(e) => {
                eprintln!("Analysis error: {}", e);
                return ExitCode::FAILURE;
            }
        }
    };

    // Output results
    match args.format {
        OutputFormat::Json => {
            // JSON output for CI parsing
            let output = serde_json::json!({
                "new_vulnerabilities": result.new_vulnerabilities.len(),
                "fixed_vulnerabilities": result.fixed_vulnerabilities.len(),
                "removed_sanitizers": result.removed_sanitizers.len(),
                "files_analyzed": result.stats.files_analyzed,
                "files_changed": result.stats.files_changed,
                "analysis_time_ms": result.stats.analysis_time_ms,
                "has_high_severity": result.has_high_severity_regression(),
                "regression_count": result.regression_count(),
                "vulnerabilities": result.new_vulnerabilities.iter().map(|v| {
                    serde_json::json!({
                        "severity": format!("{:?}", v.severity),
                        "source": v.source.name,
                        "sink": v.sink.name,
                        "description": v.description,
                        "file": v.source.file_path,
                        "line": v.source.line,
                    })
                }).collect::<Vec<_>>(),
            });
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
        }

        OutputFormat::GitHub => {
            // GitHub Actions annotations
            println!("::group::Differential Taint Analysis Results");
            println!("Files analyzed: {}", result.stats.files_analyzed);
            println!("New vulnerabilities: {}", result.new_vulnerabilities.len());
            println!(
                "Fixed vulnerabilities: {}",
                result.fixed_vulnerabilities.len()
            );
            println!("::endgroup::");

            // Output annotations for each vulnerability
            for vuln in &result.new_vulnerabilities {
                let level = match vuln.severity {
                    Severity::Critical | Severity::High => "error",
                    Severity::Medium => "warning",
                    _ => "notice",
                };

                let file = vuln.source.file_path.as_deref().unwrap_or("unknown");
                let line = vuln.source.line;

                println!(
                    "::{level} file={file},line={line}::{desc}",
                    level = level,
                    file = file,
                    line = line,
                    desc = vuln.description
                );
            }

            // Summary
            if result.has_high_severity_regression() {
                println!("::error::High-severity security regressions detected!");
            } else if result.new_vulnerabilities.is_empty() {
                println!("::notice::No security regressions detected ✅");
            }
        }

        OutputFormat::Text => {
            // Human-readable output
            println!("╔══════════════════════════════════════════════════════════════╗");
            println!("║        RFC-001 Differential Taint Analysis Results           ║");
            println!("╠══════════════════════════════════════════════════════════════╣");
            println!(
                "║ Files Changed:    {:>5}                                      ║",
                result.stats.files_changed
            );
            println!(
                "║ Files Analyzed:   {:>5}                                      ║",
                result.stats.files_analyzed
            );
            println!(
                "║ Analysis Time:    {:>5}ms                                    ║",
                result.stats.analysis_time_ms
            );
            println!("╠══════════════════════════════════════════════════════════════╣");
            println!(
                "║ New Vulnerabilities:   {:>3}                                   ║",
                result.new_vulnerabilities.len()
            );
            println!(
                "║ Fixed Vulnerabilities: {:>3}                                   ║",
                result.fixed_vulnerabilities.len()
            );
            println!(
                "║ Removed Sanitizers:    {:>3}                                   ║",
                result.removed_sanitizers.len()
            );
            println!("╚══════════════════════════════════════════════════════════════╝");

            if !result.new_vulnerabilities.is_empty() {
                println!("\n⚠️  NEW VULNERABILITIES:");
                for (i, vuln) in result.new_vulnerabilities.iter().enumerate() {
                    println!(
                        "  {}. [{:?}] {} → {}",
                        i + 1,
                        vuln.severity,
                        vuln.source.name,
                        vuln.sink.name
                    );
                    println!("     {}", vuln.description);
                    if let Some(ref file) = vuln.source.file_path {
                        println!("     📁 {}:{}", file, vuln.source.line);
                    }
                }
            }

            if !result.fixed_vulnerabilities.is_empty() {
                println!("\n✅ FIXED VULNERABILITIES:");
                for (i, vuln) in result.fixed_vulnerabilities.iter().enumerate() {
                    println!(
                        "  {}. [{:?}] {} → {}",
                        i + 1,
                        vuln.severity,
                        vuln.source.name,
                        vuln.sink.name
                    );
                }
            }

            // Summary
            println!();
            if result.has_high_severity_regression() {
                println!("❌ HIGH-SEVERITY SECURITY REGRESSIONS DETECTED!");
            } else if result.new_vulnerabilities.is_empty() {
                println!("✅ No security regressions detected.");
            } else {
                println!(
                    "⚠️  {} new potential issue(s) detected.",
                    result.new_vulnerabilities.len()
                );
            }
        }
    }

    // Exit code
    if args.fail_on_high && result.has_high_severity_regression() {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}
