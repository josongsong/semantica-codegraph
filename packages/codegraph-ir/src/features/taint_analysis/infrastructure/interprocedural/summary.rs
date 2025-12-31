//! Function Summary - Captures taint behavior of a function
//!
//! SOTA: Field-sensitive taint tracking

use std::collections::{HashMap, HashSet};

/// Function summary capturing taint behavior
///
/// Tracks parameter-level and field-level taint information for interprocedural analysis.
#[derive(Debug, Clone)]
pub struct FunctionSummary {
    /// Function name
    pub name: String,

    /// Indices of tainted parameters
    pub tainted_params: HashSet<usize>,

    /// Named variables that are tainted (for heap aliasing)
    pub tainted_vars: HashSet<String>,

    /// Variables that have been sanitized (false positive prevention)
    pub sanitized_vars: HashSet<String>,

    /// Field-level taint: {(param_idx, field_name): is_tainted}
    pub param_field_tainted: HashMap<(usize, String), bool>,

    /// Whether return value is tainted
    pub return_tainted: bool,

    /// Field-level taint for return: {field_name: is_tainted}
    pub return_field_tainted: HashMap<String, bool>,

    /// Calls that receive tainted args: {callee: {arg_indices}}
    pub tainted_calls: HashMap<String, HashSet<usize>>,

    /// Side effects (writes, etc.)
    pub side_effects: Vec<String>,

    /// Analysis confidence level (0.0-1.0)
    pub confidence: f64,
}

impl FunctionSummary {
    /// Create new empty summary
    pub fn new(name: String) -> Self {
        Self {
            name,
            tainted_params: HashSet::new(),
            tainted_vars: HashSet::new(),
            sanitized_vars: HashSet::new(),
            param_field_tainted: HashMap::new(),
            return_tainted: false,
            return_field_tainted: HashMap::new(),
            tainted_calls: HashMap::new(),
            side_effects: Vec::new(),
            confidence: 1.0,
        }
    }

    /// Convert to domain FunctionTaintSummary
    ///
    /// Maps infrastructure (field-sensitive) summary to domain (basic) summary.
    /// Field-sensitive information is projected to parameter-level.
    pub fn to_domain_summary(
        &self,
    ) -> crate::features::taint_analysis::domain::FunctionTaintSummary {
        use crate::features::taint_analysis::domain::FunctionTaintSummary as DomainSummary;

        let mut summary = DomainSummary::new(self.name.clone());

        // Copy basic taint info
        summary.tainted_params = self.tainted_params.clone();
        summary.tainted_return = self.return_tainted;
        summary.confidence = self.confidence as f32;

        // Map tainted_vars to tainted_globals
        summary.tainted_globals = self.tainted_vars.clone();

        // Check if function sanitizes (if any variables are sanitized)
        summary.sanitizes = !self.sanitized_vars.is_empty();

        summary
    }

    /// Create from domain FunctionTaintSummary
    ///
    /// Maps domain (basic) summary to infrastructure (field-sensitive) summary.
    /// Creates baseline summary without field-level details.
    pub fn from_domain_summary(
        domain: &crate::features::taint_analysis::domain::FunctionTaintSummary,
    ) -> Self {
        let mut summary = Self::new(domain.function_id.clone());

        // Copy basic taint info
        summary.tainted_params = domain.tainted_params.clone();
        summary.return_tainted = domain.tainted_return;
        summary.confidence = domain.confidence as f64;

        // Map tainted_globals to tainted_vars
        summary.tainted_vars = domain.tainted_globals.clone();

        // Map tainted_attributes to tainted_vars (flattened)
        summary
            .tainted_vars
            .extend(domain.tainted_attributes.iter().cloned());

        summary
    }

    /// Mark parameter as tainted
    pub fn taint_param(&mut self, idx: usize) {
        self.tainted_params.insert(idx);
    }

    /// Mark variable as tainted
    pub fn taint_var(&mut self, var: String) {
        self.tainted_vars.insert(var);
    }

    /// Mark variable as sanitized
    pub fn sanitize_var(&mut self, var: String) {
        self.sanitized_vars.insert(var.clone());
        self.tainted_vars.remove(&var);
    }

    /// Mark return as tainted
    pub fn taint_return(&mut self) {
        self.return_tainted = true;
    }

    /// Check if parameter is tainted
    pub fn is_param_tainted(&self, idx: usize) -> bool {
        self.tainted_params.contains(&idx)
    }

    /// Check if variable is tainted
    pub fn is_var_tainted(&self, var: &str) -> bool {
        self.tainted_vars.contains(var)
    }

    /// Check if variable is sanitized
    pub fn is_var_sanitized(&self, var: &str) -> bool {
        self.sanitized_vars.contains(var)
    }
}
