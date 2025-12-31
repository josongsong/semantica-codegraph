/// Churn metrics
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Churn metrics for a file
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ChurnMetrics {
    pub total_commits: u32,
    pub total_additions: u32,
    pub total_deletions: u32,
    pub total_changes: u32,
    pub first_commit_date: Option<DateTime<Utc>>,
    pub last_commit_date: Option<DateTime<Utc>>,
    pub days_active: u32,
    pub churn_rate: f64,       // changes per day
    pub commit_frequency: f64, // commits per week
}

impl ChurnMetrics {
    pub fn calculate_derived(&mut self) {
        if let (Some(first), Some(last)) = (self.first_commit_date, self.last_commit_date) {
            let delta = last.signed_duration_since(first);
            self.days_active = delta.num_days().max(1) as u32;
            self.churn_rate = self.total_changes as f64 / self.days_active as f64;
            let weeks = self.days_active as f64 / 7.0;
            self.commit_frequency = self.total_commits as f64 / weeks.max(1.0);
        }
    }
}
