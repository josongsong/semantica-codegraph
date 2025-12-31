//! Codegraph Benchmark CLI
//!
//! RFC-002: SOTA Benchmark System with Ground Truth Regression Testing
//!
//! # Usage
//!
//! ```bash
//! # Run benchmark with default config
//! cargo run --bin bench-codegraph --release -- run --repo tools/benchmark/repo-test/small/typer
//!
//! # Save ground truth
//! cargo run --bin bench-codegraph --release -- save-gt --repo typer
//!
//! # List all ground truths
//! cargo run --bin bench-codegraph --release -- list-gt
//! ```

use clap::{Parser, Subcommand};
use codegraph_ir::benchmark::report::{JsonReporter, MarkdownReporter, TerminalReporter};
use codegraph_ir::benchmark::{
    BenchmarkConfig, BenchmarkRunner, GroundTruth, GroundTruthStore, Repository,
};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "bench-codegraph")]
#[command(about = "Codegraph Benchmark - SOTA Performance Testing with Ground Truth", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run benchmark
    Run {
        /// Repository path
        #[arg(short, long)]
        repo: PathBuf,

        /// Skip ground truth validation
        #[arg(long)]
        skip_validation: bool,

        /// Number of warmup runs
        #[arg(long, default_value = "1")]
        warmup: usize,

        /// Number of measured runs
        #[arg(long, default_value = "3")]
        runs: usize,

        /// Output directory
        #[arg(short, long, default_value = "target/benchmark_results")]
        output: PathBuf,
    },

    /// Save ground truth baseline
    SaveGt {
        /// Repository path
        #[arg(short, long)]
        repo: PathBuf,

        /// Reason for saving/updating
        #[arg(short = 'r', long)]
        reason: String,

        /// Number of runs to average
        #[arg(long, default_value = "3")]
        runs: usize,
    },

    /// List all ground truths
    ListGt,

    /// Update existing ground truth
    UpdateGt {
        /// Repository ID
        #[arg(short, long)]
        repo: String,

        /// Reason for update (required)
        #[arg(short = 'r', long)]
        reason: String,
    },

    /// Run regression test suite (validate all ground truths)
    Regression {
        /// Fail on first regression
        #[arg(long)]
        fail_fast: bool,
    },
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Run {
            repo,
            skip_validation,
            warmup,
            runs,
            output,
        } => {
            run_benchmark(repo, skip_validation, warmup, runs, output)?;
        }
        Commands::SaveGt { repo, reason, runs } => {
            save_ground_truth(repo, reason, runs)?;
        }
        Commands::ListGt => {
            list_ground_truths()?;
        }
        Commands::UpdateGt { repo, reason } => {
            update_ground_truth(repo, reason)?;
        }
        Commands::Regression { fail_fast } => {
            run_regression(fail_fast)?;
        }
    }

    Ok(())
}

fn run_benchmark(
    repo_path: PathBuf,
    skip_validation: bool,
    warmup: usize,
    runs: usize,
    output: PathBuf,
) -> Result<(), Box<dyn std::error::Error>> {
    // Discover repository
    let repo = Repository::from_path(repo_path)?;

    // Create config
    let mut config = BenchmarkConfig::new()
        .warmup_runs(warmup)
        .measured_runs(runs)
        .output_dir(output.clone());

    if skip_validation {
        config = config.skip_validation();
    }

    // Run benchmark
    let runner = BenchmarkRunner::new(config, repo.clone());
    let report = runner.run()?;

    // Print terminal report
    TerminalReporter::print(&report);

    // Save reports
    let output_dir = output.join(&repo.id).join("default");
    std::fs::create_dir_all(&output_dir)?;

    let json_path = JsonReporter::save(&report, &output_dir)?;
    println!("\n📄 JSON saved: {:?}", json_path);

    let md_path = MarkdownReporter::save(&report, &output_dir)?;
    println!("📄 Markdown saved: {:?}", md_path);

    // Check validation status
    if let Some(validation) = &report.validation {
        if validation.status == codegraph_ir::benchmark::ValidationStatus::Fail {
            eprintln!("\n❌ Performance regression detected!");
            std::process::exit(1);
        }
    }

    println!("\n✅ Benchmark complete!");
    Ok(())
}

fn save_ground_truth(
    repo_path: PathBuf,
    reason: String,
    runs: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("🔥 Saving ground truth baseline...");
    println!("  Reason: {}", reason);
    println!("  Runs: {}", runs);
    println!();

    // Discover repository
    let repo = Repository::from_path(repo_path)?;

    // Run benchmark
    let config = BenchmarkConfig::new().measured_runs(runs).skip_validation();

    let runner = BenchmarkRunner::new(config, repo.clone());
    let report = runner.run()?;

    // Create ground truth from results
    let gt = GroundTruth::from_results(
        repo.id.clone(),
        "default".to_string(), // TODO: get from config
        &report.results,
        reason,
    );

    // Save ground truth
    let store = GroundTruthStore::default();
    store.save(&gt)?;

    println!("\n✅ Ground truth saved: {}", gt.id);
    println!("   Duration:   {:.2}s", gt.expected.duration_sec);
    println!(
        "   Throughput: {:.0} LOC/sec",
        gt.expected.throughput_loc_per_sec
    );
    println!("   Memory:     {:.1} MB", gt.expected.memory_mb);

    Ok(())
}

fn list_ground_truths() -> Result<(), Box<dyn std::error::Error>> {
    let store = GroundTruthStore::default();
    let gts = store.list()?;

    if gts.is_empty() {
        println!("No ground truths found.");
        return Ok(());
    }

    println!("╔══════════════════════════════════════════════════════════╗");
    println!("║  Ground Truth Baselines                                  ║");
    println!("╚══════════════════════════════════════════════════════════╝");
    println!();

    for gt in gts {
        println!("ID: {}", gt.id);
        println!("  Repo:       {}", gt.repo_id);
        println!("  Config:     {}", gt.config_name);
        println!("  Duration:   {:.2}s", gt.expected.duration_sec);
        println!(
            "  Throughput: {:.0} LOC/sec",
            gt.expected.throughput_loc_per_sec
        );
        println!("  Memory:     {:.1} MB", gt.expected.memory_mb);
        println!("  Updated:    {}", gt.update_reason);
        println!();
    }

    Ok(())
}

fn update_ground_truth(_repo: String, _reason: String) -> Result<(), Box<dyn std::error::Error>> {
    println!("🚧 Update ground truth not yet implemented");
    println!("   Use save-gt with the same repo to overwrite");
    Ok(())
}

fn run_regression(_fail_fast: bool) -> Result<(), Box<dyn std::error::Error>> {
    println!("🚧 Regression test suite not yet implemented");
    Ok(())
}
