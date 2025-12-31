//! Markdown report generation

use crate::benchmark::{BenchmarkReport, BenchmarkResult2};
use std::path::PathBuf;

pub struct MarkdownReporter;

impl MarkdownReporter {
    pub fn save(report: &BenchmarkReport, output_dir: &PathBuf) -> BenchmarkResult2<PathBuf> {
        let path = output_dir.join("report.md");
        let md = Self::generate(report);
        std::fs::write(&path, md)?;
        Ok(path)
    }

    fn generate(report: &BenchmarkReport) -> String {
        format!(
            r#"# Benchmark Report: {}

**Repository**: {} ({:?}, {} LOC)
**Configuration**: {}
**Timestamp**: {}
**Git Commit**: {}

## Summary

| Metric | Value |
|--------|-------|
| Duration | {:.2}s |
| Throughput | {:.0} LOC/sec |
| Memory | {:.1} MB |
| Nodes | {} |
| Edges | {} |
| Chunks | {} |
| Symbols | {} |

## Ground Truth Validation

{}

## Stage Breakdown

| Stage | Duration | % of Total |
|-------|----------|------------|
{}
"#,
            report.repo.name,
            report.repo.id,
            report.repo.category,
            report.repo.total_loc,
            report.config_name,
            report.timestamp,
            report
                .avg_result
                .git_commit
                .as_ref()
                .unwrap_or(&"N/A".to_string()),
            report.avg_result.duration.as_secs_f64(),
            report.avg_result.throughput_loc_per_sec,
            report.avg_result.memory_mb,
            report.avg_result.total_nodes,
            report.avg_result.total_edges,
            report.avg_result.total_chunks,
            report.avg_result.total_symbols,
            report
                .validation
                .as_ref()
                .map(|v| v.summary.clone())
                .unwrap_or_else(|| "N/A".to_string()),
            report
                .avg_result
                .stage_durations
                .iter()
                .map(|(stage, dur)| {
                    let pct =
                        (dur.as_secs_f64() / report.avg_result.duration.as_secs_f64()) * 100.0;
                    format!("| {} | {:.2}s | {:.1}% |", stage, dur.as_secs_f64(), pct)
                })
                .collect::<Vec<_>>()
                .join("\n")
        )
    }
}
