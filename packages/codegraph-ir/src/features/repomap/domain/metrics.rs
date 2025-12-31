//! Metrics for RepoMap nodes

use serde::{Deserialize, Serialize};

/// Metrics associated with a RepoMap node
///
/// Tracks various code quality and importance indicators.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RepoMapMetrics {
    /// Lines of code (excluding comments/blanks)
    pub loc: usize,

    /// Number of symbols (functions, classes, etc.)
    pub symbol_count: usize,

    /// Cyclomatic complexity (for functions)
    pub complexity: usize,

    /// PageRank importance score (0.0-1.0)
    pub pagerank: f64,

    /// HITS authority score (0.0-1.0)
    pub authority_score: Option<f64>,

    /// HITS hub score (0.0-1.0)
    pub hub_score: Option<f64>,

    /// Git change frequency (commits in last N days)
    pub change_frequency: Option<f64>,

    /// Last modified timestamp (Unix epoch)
    pub last_modified: Option<u64>,

    /// Code churn (lines added + deleted)
    pub code_churn: Option<usize>,

    /// Number of unique authors
    pub author_count: Option<usize>,
}

impl RepoMapMetrics {
    /// Create metrics with LOC only
    pub fn with_loc(loc: usize) -> Self {
        Self {
            loc,
            ..Default::default()
        }
    }

    /// Set symbol count
    pub fn with_symbol_count(mut self, symbol_count: usize) -> Self {
        self.symbol_count = symbol_count;
        self
    }

    /// Set complexity
    pub fn with_complexity(mut self, complexity: usize) -> Self {
        self.complexity = complexity;
        self
    }

    /// Set PageRank score
    pub fn with_pagerank(mut self, pagerank: f64) -> Self {
        self.pagerank = pagerank;
        self
    }

    /// Set HITS scores
    pub fn with_hits(mut self, authority: f64, hub: f64) -> Self {
        self.authority_score = Some(authority);
        self.hub_score = Some(hub);
        self
    }

    /// Set Git metrics
    pub fn with_git_metrics(
        mut self,
        change_frequency: f64,
        last_modified: u64,
        code_churn: usize,
    ) -> Self {
        self.change_frequency = Some(change_frequency);
        self.last_modified = Some(last_modified);
        self.code_churn = Some(code_churn);
        self
    }

    /// Calculate combined importance score
    ///
    /// Weighted combination of PageRank, authority, and change frequency.
    pub fn combined_importance(&self, weights: &ImportanceWeights) -> f64 {
        let authority = self.authority_score.unwrap_or(0.0);
        let change_freq = self.change_frequency.unwrap_or(0.0);

        weights.pagerank * self.pagerank
            + weights.authority * authority
            + weights.change_frequency * change_freq
    }
}

/// Weights for importance score calculation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportanceWeights {
    pub pagerank: f64,
    pub authority: f64,
    pub change_frequency: f64,
}

impl Default for ImportanceWeights {
    fn default() -> Self {
        Self {
            pagerank: 0.5,
            authority: 0.3,
            change_frequency: 0.2,
        }
    }
}
