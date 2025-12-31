/// Git blame information
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Blame information for a single line
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BlameInfo {
    pub line_number: u32,
    pub line_content: String,
    pub commit_hash: String,
    pub author_name: String,
    pub author_email: String,
    pub author_date: DateTime<Utc>,
    pub committer_name: String,
    pub committer_email: String,
    pub committer_date: DateTime<Utc>,
    pub commit_summary: String,
}
