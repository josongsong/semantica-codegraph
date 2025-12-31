/// Co-change pattern
use serde::{Deserialize, Serialize};

/// Co-change pattern between two files
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CoChangePattern {
    pub file_a: String,
    pub file_b: String,
    pub cochange_count: u32,
    pub file_a_changes: u32,
    pub file_b_changes: u32,
    pub coupling_strength: f64, // Jaccard similarity
    pub confidence_a_to_b: f64, // P(B changes | A changes)
    pub confidence_b_to_a: f64, // P(A changes | B changes)
}

impl CoChangePattern {
    pub fn calculate_metrics(&mut self) {
        if self.file_a_changes > 0 {
            self.confidence_a_to_b = self.cochange_count as f64 / self.file_a_changes as f64;
        }
        if self.file_b_changes > 0 {
            self.confidence_b_to_a = self.cochange_count as f64 / self.file_b_changes as f64;
        }
        let total = self.file_a_changes + self.file_b_changes - self.cochange_count;
        if total > 0 {
            self.coupling_strength = self.cochange_count as f64 / total as f64;
        }
    }
}
