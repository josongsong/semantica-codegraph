//! Terminal (pretty-print) report generation

use crate::benchmark::BenchmarkReport;

pub struct TerminalReporter;

impl TerminalReporter {
    pub fn print(report: &BenchmarkReport) {
        println!("\n┌──────────────────────────────────────────────────────────┐");
        println!("│ Performance Summary                                      │");
        println!("├──────────────────────────────────────────────────────────┤");
        println!(
            "│  Duration:     {:.2}s                                     │",
            report.avg_result.duration.as_secs_f64()
        );
        println!(
            "│  Throughput:   {:.0} LOC/sec                              │",
            report.avg_result.throughput_loc_per_sec
        );
        println!(
            "│  Memory:       {:.1} MB                                    │",
            report.avg_result.memory_mb
        );
        println!(
            "│  Nodes:        {}                                          │",
            report.avg_result.total_nodes
        );
        println!(
            "│  Edges:        {}                                          │",
            report.avg_result.total_edges
        );
        println!(
            "│  Chunks:       {}                                          │",
            report.avg_result.total_chunks
        );
        println!(
            "│  Symbols:      {}                                          │",
            report.avg_result.total_symbols
        );
        println!("└──────────────────────────────────────────────────────────┘");

        if let Some(validation) = &report.validation {
            println!("\n┌──────────────────────────────────────────────────────────┐");
            println!("│ Ground Truth Validation                                  │");
            println!("├──────────────────────────────────────────────────────────┤");
            for line in validation.summary.lines() {
                println!("│  {:<54}  │", line);
            }
            println!("└──────────────────────────────────────────────────────────┘");
        }
    }
}
