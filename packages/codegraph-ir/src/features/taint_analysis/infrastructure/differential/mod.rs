/*
 * Differential Taint Analysis
 *
 * Detects security regressions between code versions by comparing taint analysis results.
 *
 * Key capabilities:
 * 1. New vulnerability detection (not in base, present in modified)
 * 2. Fixed vulnerability detection (in base, not in modified)
 * 3. Sanitizer change detection (added/removed security controls)
 * 4. Regression reporting (net change in security posture)
 *
 * Example workflow:
 *   // Base version (safe)
 *   def process(input):
 *       clean = sanitize(input)
 *       execute(clean)
 *
 *   // Modified version (vulnerable)
 *   def process(input):
 *       execute(input)  # Sanitization removed!
 *
 *   // Differential analysis detects:
 *   // [REGRESSION] New taint flow: input → execute (sanitize removed)
 *
 * Performance target: < 3 minutes for typical PR (50 files)
 *
 * Reference:
 * - RFC-001: Differential Taint Analysis
 * - "Differential Security Analysis" (Livshits & Lam, 2005)
 */

pub mod analyzer;
pub mod cache;
pub mod cicd;
pub mod error;
pub mod git_integration;
pub mod ir_integration;
pub mod result;

pub use analyzer::DifferentialTaintAnalyzer;
pub use cicd::{
    CIExitCode, GitHubActionsReporter, GitLabCIReporter, PRCommentFormatter, SarifReport,
};
pub use error::{DifferentialError, DifferentialResult};
pub use git_integration::{ChangeType, ChangedFile, GitDiffConfig, GitDifferentialAnalyzer};
pub use ir_integration::IRTaintAnalyzer;
pub use result::{
    DiffStats, DifferentialTaintResult, PartialFix, SanitizerInfo, Severity, TaintSink,
    TaintSource, Vulnerability, VulnerabilityCategory,
};
