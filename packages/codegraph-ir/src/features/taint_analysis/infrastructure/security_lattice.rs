/*
 * Security Lattice for Information Flow Analysis
 *
 * Implements lattice-based security typing for confidentiality/integrity analysis.
 *
 * Security Lattice (Denning 1976):
 * - Confidentiality: Public ⊏ Confidential ⊏ Secret ⊏ TopSecret
 * - Integrity: Untrusted ⊏ Trusted ⊏ HighlyTrusted
 *
 * Non-interference (Goguen & Meseguer 1982):
 * - Program satisfies non-interference if low-security outputs depend only on
 *   low-security inputs, regardless of high-security inputs.
 *
 * Example:
 * ```python
 * # Confidentiality violation:
 * secret = get_password()   # Secret
 * public = secret           # Error: Secret → Public flow
 *
 * # Integrity violation:
 * untrusted = user_input()  # Untrusted
 * execute(untrusted)        # Error: Untrusted → Trusted sink
 * ```
 *
 * References:
 * - Denning (1976): "A Lattice Model of Secure Information Flow"
 * - Goguen & Meseguer (1982): "Security Policies and Security Models"
 * - Sabelfeld & Myers (2003): "Language-based Information-Flow Security"
 */

use rustc_hash::{FxHashMap, FxHashSet};
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};

// ============================================================================
// Security Level Definitions
// ============================================================================

/// Confidentiality level (higher = more secret)
/// Forms a lattice: Public ⊑ Confidential ⊑ Secret ⊑ TopSecret
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ConfidentialityLevel {
    /// Public: can be revealed to anyone
    Public,
    /// Confidential: internal use only
    Confidential,
    /// Secret: restricted access
    Secret,
    /// TopSecret: highest classification
    TopSecret,
}

impl ConfidentialityLevel {
    /// Numeric level for comparison (higher = more confidential)
    fn level(&self) -> u8 {
        match self {
            ConfidentialityLevel::Public => 0,
            ConfidentialityLevel::Confidential => 1,
            ConfidentialityLevel::Secret => 2,
            ConfidentialityLevel::TopSecret => 3,
        }
    }

    /// Join (least upper bound): ⊔
    pub fn join(&self, other: &Self) -> Self {
        if self.level() >= other.level() {
            *self
        } else {
            *other
        }
    }

    /// Meet (greatest lower bound): ⊓
    pub fn meet(&self, other: &Self) -> Self {
        if self.level() <= other.level() {
            *self
        } else {
            *other
        }
    }

    /// Check if self ⊑ other (flows-to relation)
    /// Data at level `self` can flow to level `other`
    pub fn flows_to(&self, other: &Self) -> bool {
        self.level() <= other.level()
    }

    /// Bottom of lattice
    pub fn bottom() -> Self {
        ConfidentialityLevel::Public
    }

    /// Top of lattice
    pub fn top() -> Self {
        ConfidentialityLevel::TopSecret
    }
}

impl PartialOrd for ConfidentialityLevel {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for ConfidentialityLevel {
    fn cmp(&self, other: &Self) -> Ordering {
        self.level().cmp(&other.level())
    }
}

/// Integrity level (higher = more trusted)
/// Forms a lattice: Untrusted ⊑ Trusted ⊑ HighlyTrusted
/// Note: Integrity flows DOWN (opposite of confidentiality)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntegrityLevel {
    /// Untrusted: user input, external data
    Untrusted,
    /// Trusted: validated/sanitized data
    Trusted,
    /// HighlyTrusted: system-generated, cryptographically verified
    HighlyTrusted,
}

impl IntegrityLevel {
    /// Numeric level (higher = more trusted)
    fn level(&self) -> u8 {
        match self {
            IntegrityLevel::Untrusted => 0,
            IntegrityLevel::Trusted => 1,
            IntegrityLevel::HighlyTrusted => 2,
        }
    }

    /// Join for integrity (least upper bound)
    pub fn join(&self, other: &Self) -> Self {
        // For integrity, join is MIN (less trusted wins)
        if self.level() <= other.level() {
            *self
        } else {
            *other
        }
    }

    /// Meet for integrity (greatest lower bound)
    pub fn meet(&self, other: &Self) -> Self {
        if self.level() >= other.level() {
            *self
        } else {
            *other
        }
    }

    /// Check if data at `self` level can flow to `other` level
    /// Integrity flows DOWN: Trusted → Untrusted is OK
    pub fn flows_to(&self, other: &Self) -> bool {
        self.level() >= other.level()
    }

    /// Bottom: most trusted (integrity starts high)
    pub fn bottom() -> Self {
        IntegrityLevel::HighlyTrusted
    }

    /// Top: least trusted
    pub fn top() -> Self {
        IntegrityLevel::Untrusted
    }
}

/// Combined security label (Confidentiality × Integrity)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SecurityLabel {
    pub confidentiality: ConfidentialityLevel,
    pub integrity: IntegrityLevel,
}

impl SecurityLabel {
    pub fn new(confidentiality: ConfidentialityLevel, integrity: IntegrityLevel) -> Self {
        Self {
            confidentiality,
            integrity,
        }
    }

    /// Public & trusted (safe default)
    pub fn public_trusted() -> Self {
        Self {
            confidentiality: ConfidentialityLevel::Public,
            integrity: IntegrityLevel::Trusted,
        }
    }

    /// Secret & trusted (internal secret)
    pub fn secret_trusted() -> Self {
        Self {
            confidentiality: ConfidentialityLevel::Secret,
            integrity: IntegrityLevel::Trusted,
        }
    }

    /// Public & untrusted (user input)
    pub fn public_untrusted() -> Self {
        Self {
            confidentiality: ConfidentialityLevel::Public,
            integrity: IntegrityLevel::Untrusted,
        }
    }

    /// Join: combines two labels (point-wise join)
    pub fn join(&self, other: &Self) -> Self {
        Self {
            confidentiality: self.confidentiality.join(&other.confidentiality),
            integrity: self.integrity.join(&other.integrity),
        }
    }

    /// Meet: point-wise meet
    pub fn meet(&self, other: &Self) -> Self {
        Self {
            confidentiality: self.confidentiality.meet(&other.confidentiality),
            integrity: self.integrity.meet(&other.integrity),
        }
    }

    /// Check if data at `self` label can flow to `other` label
    /// Both confidentiality and integrity must allow the flow
    pub fn flows_to(&self, other: &Self) -> bool {
        self.confidentiality.flows_to(&other.confidentiality)
            && self.integrity.flows_to(&other.integrity)
    }

    /// Bottom element (Public, HighlyTrusted)
    pub fn bottom() -> Self {
        Self {
            confidentiality: ConfidentialityLevel::bottom(),
            integrity: IntegrityLevel::bottom(),
        }
    }

    /// Top element (TopSecret, Untrusted)
    pub fn top() -> Self {
        Self {
            confidentiality: ConfidentialityLevel::top(),
            integrity: IntegrityLevel::top(),
        }
    }
}

impl Default for SecurityLabel {
    fn default() -> Self {
        Self::public_trusted()
    }
}

// ============================================================================
// Security Typing Environment
// ============================================================================

/// Variable security context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityContext {
    /// Variable → Security label
    labels: FxHashMap<String, SecurityLabel>,

    /// Program counter label (implicit flow tracking)
    pc_label: SecurityLabel,

    /// Declassification points (where explicit downgrading is allowed)
    declassification_points: FxHashSet<String>,

    /// Endorsement points (where integrity can be upgraded)
    endorsement_points: FxHashSet<String>,
}

impl SecurityContext {
    pub fn new() -> Self {
        Self {
            labels: FxHashMap::default(),
            pc_label: SecurityLabel::bottom(),
            declassification_points: FxHashSet::default(),
            endorsement_points: FxHashSet::default(),
        }
    }

    /// Set security label for a variable
    pub fn set_label(&mut self, var: impl Into<String>, label: SecurityLabel) {
        self.labels.insert(var.into(), label);
    }

    /// Get security label for a variable
    pub fn get_label(&self, var: &str) -> SecurityLabel {
        self.labels.get(var).copied().unwrap_or_default()
    }

    /// Update PC label (entering conditional)
    pub fn push_pc(&mut self, condition_label: SecurityLabel) {
        self.pc_label = self.pc_label.join(&condition_label);
    }

    /// Restore PC label (exiting conditional)
    pub fn pop_pc(&mut self, saved_label: SecurityLabel) {
        self.pc_label = saved_label;
    }

    /// Current PC label
    pub fn pc_label(&self) -> SecurityLabel {
        self.pc_label
    }

    /// Add declassification point
    pub fn add_declassification(&mut self, point: impl Into<String>) {
        self.declassification_points.insert(point.into());
    }

    /// Check if point allows declassification
    pub fn is_declassification_point(&self, point: &str) -> bool {
        self.declassification_points.contains(point)
    }

    /// Add endorsement point
    pub fn add_endorsement(&mut self, point: impl Into<String>) {
        self.endorsement_points.insert(point.into());
    }

    /// Check if point allows endorsement
    pub fn is_endorsement_point(&self, point: &str) -> bool {
        self.endorsement_points.contains(point)
    }

    /// Compute label for an expression
    /// Joins labels of all variables used in expression
    pub fn compute_expr_label(&self, used_vars: &[&str]) -> SecurityLabel {
        let mut result = self.pc_label; // Include implicit flow
        for var in used_vars {
            result = result.join(&self.get_label(var));
        }
        result
    }
}

impl Default for SecurityContext {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Non-interference Checker
// ============================================================================

/// Information flow violation types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FlowViolation {
    /// Confidentiality leak: high → low
    ConfidentialityLeak {
        source_var: String,
        source_label: SecurityLabel,
        sink_var: String,
        sink_label: SecurityLabel,
        location: String,
    },

    /// Integrity violation: untrusted → trusted sink
    IntegrityViolation {
        source_var: String,
        source_label: SecurityLabel,
        sink_var: String,
        sink_label: SecurityLabel,
        location: String,
    },

    /// Implicit flow through control dependency
    ImplicitFlow {
        condition_var: String,
        condition_label: SecurityLabel,
        affected_var: String,
        location: String,
    },
}

impl FlowViolation {
    /// Human-readable description
    pub fn description(&self) -> String {
        match self {
            FlowViolation::ConfidentialityLeak {
                source_var,
                source_label,
                sink_var,
                sink_label,
                location,
            } => {
                format!(
                    "Confidentiality leak at {}: {} ({:?}) flows to {} ({:?})",
                    location,
                    source_var,
                    source_label.confidentiality,
                    sink_var,
                    sink_label.confidentiality
                )
            }
            FlowViolation::IntegrityViolation {
                source_var,
                source_label,
                sink_var,
                sink_label,
                location,
            } => {
                format!(
                    "Integrity violation at {}: {} ({:?}) flows to {} ({:?})",
                    location, source_var, source_label.integrity, sink_var, sink_label.integrity
                )
            }
            FlowViolation::ImplicitFlow {
                condition_var,
                condition_label,
                affected_var,
                location,
            } => {
                format!(
                    "Implicit flow at {}: condition {} ({:?}) affects {}",
                    location, condition_var, condition_label.confidentiality, affected_var
                )
            }
        }
    }

    /// Severity level (1-5)
    pub fn severity(&self) -> u8 {
        match self {
            FlowViolation::ConfidentialityLeak { source_label, .. } => {
                match source_label.confidentiality {
                    ConfidentialityLevel::TopSecret => 5,
                    ConfidentialityLevel::Secret => 4,
                    ConfidentialityLevel::Confidential => 3,
                    ConfidentialityLevel::Public => 1,
                }
            }
            FlowViolation::IntegrityViolation { sink_label, .. } => match sink_label.integrity {
                IntegrityLevel::HighlyTrusted => 5,
                IntegrityLevel::Trusted => 4,
                IntegrityLevel::Untrusted => 2,
            },
            FlowViolation::ImplicitFlow {
                condition_label, ..
            } => match condition_label.confidentiality {
                ConfidentialityLevel::TopSecret => 4,
                ConfidentialityLevel::Secret => 3,
                _ => 2,
            },
        }
    }
}

/// Non-interference checker
///
/// Verifies that a program satisfies non-interference:
/// - High-security inputs do not affect low-security outputs
/// - Untrusted inputs do not flow to trusted sinks
#[derive(Debug, Clone)]
pub struct NonInterferenceChecker {
    context: SecurityContext,
    violations: Vec<FlowViolation>,
    /// Track variables that have been declassified
    declassified: FxHashSet<String>,
    /// Track variables that have been endorsed
    endorsed: FxHashSet<String>,
}

impl NonInterferenceChecker {
    pub fn new() -> Self {
        Self {
            context: SecurityContext::new(),
            violations: Vec::new(),
            declassified: FxHashSet::default(),
            endorsed: FxHashSet::default(),
        }
    }

    pub fn with_context(context: SecurityContext) -> Self {
        Self {
            context,
            violations: Vec::new(),
            declassified: FxHashSet::default(),
            endorsed: FxHashSet::default(),
        }
    }

    /// Check assignment: target := source_expr
    pub fn check_assignment(
        &mut self,
        target: &str,
        target_label: SecurityLabel,
        source_vars: &[&str],
        location: &str,
    ) {
        let source_label = self.context.compute_expr_label(source_vars);

        // Check if flow is allowed
        if !source_label.flows_to(&target_label) {
            // Determine violation type
            if !source_label
                .confidentiality
                .flows_to(&target_label.confidentiality)
            {
                self.violations.push(FlowViolation::ConfidentialityLeak {
                    source_var: source_vars
                        .first()
                        .map(|s| s.to_string())
                        .unwrap_or_default(),
                    source_label,
                    sink_var: target.to_string(),
                    sink_label: target_label,
                    location: location.to_string(),
                });
            }

            if !source_label.integrity.flows_to(&target_label.integrity) {
                self.violations.push(FlowViolation::IntegrityViolation {
                    source_var: source_vars
                        .first()
                        .map(|s| s.to_string())
                        .unwrap_or_default(),
                    source_label,
                    sink_var: target.to_string(),
                    sink_label: target_label,
                    location: location.to_string(),
                });
            }
        }

        // Check implicit flow via PC
        let pc = self.context.pc_label();
        if !pc.flows_to(&target_label) {
            self.violations.push(FlowViolation::ImplicitFlow {
                condition_var: "PC".to_string(),
                condition_label: pc,
                affected_var: target.to_string(),
                location: location.to_string(),
            });
        }

        // Update target label
        self.context.set_label(target, source_label);
    }

    /// Declassify a variable (explicit downgrade)
    pub fn declassify(
        &mut self,
        var: &str,
        new_level: ConfidentialityLevel,
        location: &str,
    ) -> bool {
        if self.context.is_declassification_point(location) {
            let mut label = self.context.get_label(var);
            label.confidentiality = new_level;
            self.context.set_label(var, label);
            self.declassified.insert(var.to_string());
            true
        } else {
            false
        }
    }

    /// Endorse a variable (explicit integrity upgrade)
    pub fn endorse(&mut self, var: &str, new_level: IntegrityLevel, location: &str) -> bool {
        if self.context.is_endorsement_point(location) {
            let mut label = self.context.get_label(var);
            label.integrity = new_level;
            self.context.set_label(var, label);
            self.endorsed.insert(var.to_string());
            true
        } else {
            false
        }
    }

    /// Enter conditional (update PC)
    pub fn enter_conditional(&mut self, condition_vars: &[&str]) -> SecurityLabel {
        let saved = self.context.pc_label();
        let condition_label = self.context.compute_expr_label(condition_vars);
        self.context.push_pc(condition_label);
        saved
    }

    /// Exit conditional (restore PC)
    pub fn exit_conditional(&mut self, saved_pc: SecurityLabel) {
        self.context.pop_pc(saved_pc);
    }

    /// Get all violations
    pub fn violations(&self) -> &[FlowViolation] {
        &self.violations
    }

    /// Check if program satisfies non-interference
    pub fn is_secure(&self) -> bool {
        self.violations.is_empty()
    }

    /// Get context for further inspection
    pub fn context(&self) -> &SecurityContext {
        &self.context
    }

    /// Mutable context access
    pub fn context_mut(&mut self) -> &mut SecurityContext {
        &mut self.context
    }
}

impl Default for NonInterferenceChecker {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Security Type Inference
// ============================================================================

/// Inferred security annotations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityAnnotation {
    pub var: String,
    pub inferred_label: SecurityLabel,
    pub sources: Vec<String>,
    pub confidence: f64,
}

/// Security type inference engine
#[derive(Debug)]
pub struct SecurityTypeInference {
    /// Known security sources (e.g., `get_password` → Secret)
    known_sources: FxHashMap<String, SecurityLabel>,
    /// Known security sinks (e.g., `print` → Public)
    known_sinks: FxHashMap<String, SecurityLabel>,
    /// Inferred annotations
    annotations: Vec<SecurityAnnotation>,
}

impl SecurityTypeInference {
    pub fn new() -> Self {
        let mut engine = Self {
            known_sources: FxHashMap::default(),
            known_sinks: FxHashMap::default(),
            annotations: Vec::new(),
        };
        engine.init_default_sources();
        engine.init_default_sinks();
        engine
    }

    /// Initialize common security sources
    fn init_default_sources(&mut self) {
        // Confidentiality sources
        self.known_sources.insert(
            "get_password".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Secret, IntegrityLevel::Trusted),
        );
        self.known_sources.insert(
            "read_secret".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Secret, IntegrityLevel::Trusted),
        );
        self.known_sources.insert(
            "decrypt".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Secret, IntegrityLevel::Trusted),
        );
        self.known_sources.insert(
            "get_api_key".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Secret, IntegrityLevel::Trusted),
        );

        // Untrusted sources (integrity)
        self.known_sources.insert(
            "input".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Untrusted),
        );
        self.known_sources.insert(
            "request.get".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Untrusted),
        );
        self.known_sources.insert(
            "os.environ.get".to_string(),
            SecurityLabel::new(
                ConfidentialityLevel::Confidential,
                IntegrityLevel::Untrusted,
            ),
        );
    }

    /// Initialize common security sinks
    fn init_default_sinks(&mut self) {
        // Public sinks (confidentiality)
        self.known_sinks.insert(
            "print".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Untrusted),
        );
        self.known_sinks.insert(
            "log".to_string(),
            SecurityLabel::new(
                ConfidentialityLevel::Confidential,
                IntegrityLevel::Untrusted,
            ),
        );
        self.known_sinks.insert(
            "response.send".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Untrusted),
        );

        // Trusted sinks (integrity)
        self.known_sinks.insert(
            "execute".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Trusted),
        );
        self.known_sinks.insert(
            "sql.execute".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Trusted),
        );
        self.known_sinks.insert(
            "eval".to_string(),
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::HighlyTrusted),
        );
    }

    /// Add custom source
    pub fn add_source(&mut self, name: impl Into<String>, label: SecurityLabel) {
        self.known_sources.insert(name.into(), label);
    }

    /// Add custom sink
    pub fn add_sink(&mut self, name: impl Into<String>, label: SecurityLabel) {
        self.known_sinks.insert(name.into(), label);
    }

    /// Get source label
    pub fn source_label(&self, name: &str) -> Option<SecurityLabel> {
        self.known_sources.get(name).copied()
    }

    /// Get sink label (expected label for data flowing to sink)
    pub fn sink_label(&self, name: &str) -> Option<SecurityLabel> {
        self.known_sinks.get(name).copied()
    }

    /// Infer label for variable based on data flow
    pub fn infer_label(
        &mut self,
        var: &str,
        sources: &[&str],
        context: &SecurityContext,
    ) -> SecurityLabel {
        let label = context.compute_expr_label(sources);

        self.annotations.push(SecurityAnnotation {
            var: var.to_string(),
            inferred_label: label,
            sources: sources.iter().map(|s| s.to_string()).collect(),
            confidence: 0.9, // High confidence for direct inference
        });

        label
    }

    /// Get all annotations
    pub fn annotations(&self) -> &[SecurityAnnotation] {
        &self.annotations
    }
}

impl Default for SecurityTypeInference {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_confidentiality_flows_to() {
        // Public → Confidential → Secret → TopSecret
        assert!(ConfidentialityLevel::Public.flows_to(&ConfidentialityLevel::Secret));
        assert!(ConfidentialityLevel::Secret.flows_to(&ConfidentialityLevel::Secret));
        assert!(!ConfidentialityLevel::Secret.flows_to(&ConfidentialityLevel::Public));
    }

    #[test]
    fn test_integrity_flows_to() {
        // HighlyTrusted → Trusted → Untrusted (downward flow)
        assert!(IntegrityLevel::HighlyTrusted.flows_to(&IntegrityLevel::Untrusted));
        assert!(IntegrityLevel::Trusted.flows_to(&IntegrityLevel::Untrusted));
        assert!(!IntegrityLevel::Untrusted.flows_to(&IntegrityLevel::Trusted));
    }

    #[test]
    fn test_security_label_flows_to() {
        let public_trusted = SecurityLabel::public_trusted();
        let secret_trusted = SecurityLabel::secret_trusted();
        let public_untrusted = SecurityLabel::public_untrusted();

        // Public, Trusted → Secret, Trusted (OK: going more confidential)
        assert!(public_trusted.flows_to(&secret_trusted));

        // Secret, Trusted → Public, Trusted (FAIL: confidentiality leak)
        assert!(!secret_trusted.flows_to(&public_trusted));

        // Public, Untrusted → Public, Trusted (FAIL: integrity violation)
        assert!(!public_untrusted.flows_to(&public_trusted));
    }

    #[test]
    fn test_noninterference_confidentiality() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("secret", SecurityLabel::secret_trusted());
        ctx.set_label("public", SecurityLabel::public_trusted());

        let mut checker = NonInterferenceChecker::with_context(ctx);

        // public := secret (should fail)
        checker.check_assignment(
            "public",
            SecurityLabel::public_trusted(),
            &["secret"],
            "line:10",
        );

        assert!(!checker.is_secure());
        assert_eq!(checker.violations().len(), 1);
        assert!(matches!(
            &checker.violations()[0],
            FlowViolation::ConfidentialityLeak { .. }
        ));
    }

    #[test]
    fn test_noninterference_integrity() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("untrusted", SecurityLabel::public_untrusted());

        let mut checker = NonInterferenceChecker::with_context(ctx);

        // execute(untrusted) → trusted sink
        checker.check_assignment(
            "sql_param",
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Trusted),
            &["untrusted"],
            "line:20",
        );

        assert!(!checker.is_secure());
        assert!(matches!(
            &checker.violations()[0],
            FlowViolation::IntegrityViolation { .. }
        ));
    }

    #[test]
    fn test_implicit_flow() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("secret", SecurityLabel::secret_trusted());

        let mut checker = NonInterferenceChecker::with_context(ctx);

        // if (secret) { public := 1 }
        let saved = checker.enter_conditional(&["secret"]);
        checker.check_assignment(
            "public",
            SecurityLabel::public_trusted(),
            &[], // No direct source
            "line:15",
        );
        checker.exit_conditional(saved);

        assert!(!checker.is_secure());
        // Check that ImplicitFlow is detected (may not be first due to source label check)
        assert!(checker
            .violations()
            .iter()
            .any(|v| matches!(v, FlowViolation::ImplicitFlow { .. })));
    }

    #[test]
    fn test_declassification() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("secret", SecurityLabel::secret_trusted());
        ctx.add_declassification("sanitize_line:30");

        let mut checker = NonInterferenceChecker::with_context(ctx);

        // Declassify at allowed point
        let success =
            checker.declassify("secret", ConfidentialityLevel::Public, "sanitize_line:30");
        assert!(success);

        // Now secret → public is OK
        checker.check_assignment(
            "public",
            SecurityLabel::public_trusted(),
            &["secret"],
            "line:35",
        );

        assert!(checker.is_secure());
    }

    #[test]
    fn test_security_type_inference() {
        let mut inference = SecurityTypeInference::new();

        // Check default sources
        let pwd_label = inference.source_label("get_password").unwrap();
        assert_eq!(pwd_label.confidentiality, ConfidentialityLevel::Secret);

        let input_label = inference.source_label("input").unwrap();
        assert_eq!(input_label.integrity, IntegrityLevel::Untrusted);

        // Check default sinks
        let print_label = inference.sink_label("print").unwrap();
        assert_eq!(print_label.confidentiality, ConfidentialityLevel::Public);

        let exec_label = inference.sink_label("execute").unwrap();
        assert_eq!(exec_label.integrity, IntegrityLevel::Trusted);
    }

    #[test]
    fn test_label_join_meet() {
        let public = ConfidentialityLevel::Public;
        let secret = ConfidentialityLevel::Secret;

        // Join: least upper bound
        assert_eq!(public.join(&secret), secret);
        assert_eq!(secret.join(&public), secret);

        // Meet: greatest lower bound
        assert_eq!(public.meet(&secret), public);
        assert_eq!(secret.meet(&public), public);
    }

    // =========================================================================
    // SOTA L11 Edge Cases - Security Lattice Comprehensive Tests
    // =========================================================================

    /// Edge Case: Lattice boundary values (Bottom/Top)
    #[test]
    fn test_lattice_boundary_values() {
        // Confidentiality boundary
        let bottom = ConfidentialityLevel::bottom();
        let top = ConfidentialityLevel::top();
        
        assert_eq!(bottom, ConfidentialityLevel::Public);
        assert_eq!(top, ConfidentialityLevel::TopSecret);
        
        // Bottom flows to everything
        assert!(bottom.flows_to(&ConfidentialityLevel::Public));
        assert!(bottom.flows_to(&ConfidentialityLevel::Confidential));
        assert!(bottom.flows_to(&ConfidentialityLevel::Secret));
        assert!(bottom.flows_to(&ConfidentialityLevel::TopSecret));
        
        // Nothing flows to bottom except itself
        assert!(bottom.flows_to(&bottom));
        assert!(!ConfidentialityLevel::Confidential.flows_to(&bottom));
        assert!(!ConfidentialityLevel::Secret.flows_to(&bottom));
        assert!(!top.flows_to(&bottom));
        
        // Top flows only to itself
        assert!(top.flows_to(&top));
        assert!(!top.flows_to(&ConfidentialityLevel::Secret));
    }

    /// Edge Case: Integrity lattice is inverted (higher = more trusted)
    #[test]
    fn test_integrity_inverted_lattice() {
        // Integrity flows DOWN: HighlyTrusted → Trusted → Untrusted
        let highly_trusted = IntegrityLevel::HighlyTrusted;
        let trusted = IntegrityLevel::Trusted;
        let untrusted = IntegrityLevel::Untrusted;
        
        // High integrity can flow to lower
        assert!(highly_trusted.flows_to(&trusted));
        assert!(highly_trusted.flows_to(&untrusted));
        assert!(trusted.flows_to(&untrusted));
        
        // Low integrity cannot flow to higher
        assert!(!untrusted.flows_to(&trusted));
        assert!(!untrusted.flows_to(&highly_trusted));
        assert!(!trusted.flows_to(&highly_trusted));
        
        // Verify bottom/top are inverted
        assert_eq!(IntegrityLevel::bottom(), IntegrityLevel::HighlyTrusted);
        assert_eq!(IntegrityLevel::top(), IntegrityLevel::Untrusted);
    }

    /// Edge Case: Combined label with conflicting directions
    #[test]
    fn test_combined_label_conflicting_flow() {
        // Secret + HighlyTrusted (restricted but trusted)
        let secret_trusted = SecurityLabel::new(
            ConfidentialityLevel::Secret,
            IntegrityLevel::HighlyTrusted,
        );
        
        // Public + Untrusted (open but untrusted)
        let public_untrusted = SecurityLabel::public_untrusted();
        
        // Secret,HighlyTrusted → Public,Untrusted
        // Confidentiality: Secret → Public (FAIL)
        // Integrity: HighlyTrusted → Untrusted (OK)
        assert!(!secret_trusted.flows_to(&public_untrusted));
        
        // Public,Untrusted → Secret,HighlyTrusted
        // Confidentiality: Public → Secret (OK)
        // Integrity: Untrusted → HighlyTrusted (FAIL)
        assert!(!public_untrusted.flows_to(&secret_trusted));
    }

    /// Base Case: Self-flow (reflexivity)
    #[test]
    fn test_self_flow_reflexivity() {
        for conf in [
            ConfidentialityLevel::Public,
            ConfidentialityLevel::Confidential,
            ConfidentialityLevel::Secret,
            ConfidentialityLevel::TopSecret,
        ] {
            assert!(conf.flows_to(&conf), "Reflexivity failed for {:?}", conf);
        }
        
        for integ in [
            IntegrityLevel::Untrusted,
            IntegrityLevel::Trusted,
            IntegrityLevel::HighlyTrusted,
        ] {
            assert!(integ.flows_to(&integ), "Reflexivity failed for {:?}", integ);
        }
        
        // Combined
        let label = SecurityLabel::secret_trusted();
        assert!(label.flows_to(&label));
    }

    /// Extreme Case: All levels transitivity
    #[test]
    fn test_transitivity_all_levels() {
        // If A → B and B → C, then A → C
        let levels = [
            ConfidentialityLevel::Public,
            ConfidentialityLevel::Confidential,
            ConfidentialityLevel::Secret,
            ConfidentialityLevel::TopSecret,
        ];
        
        for (i, a) in levels.iter().enumerate() {
            for (j, b) in levels.iter().enumerate() {
                for (k, c) in levels.iter().enumerate() {
                    if a.flows_to(b) && b.flows_to(c) {
                        assert!(
                            a.flows_to(c),
                            "Transitivity failed: {:?} → {:?} → {:?}",
                            a, b, c
                        );
                    }
                }
            }
        }
    }

    /// Extreme Case: PC label propagation in nested conditionals
    #[test]
    fn test_nested_conditional_pc_propagation() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("secret", SecurityLabel::secret_trusted());
        ctx.set_label("top_secret", SecurityLabel::new(
            ConfidentialityLevel::TopSecret,
            IntegrityLevel::Trusted,
        ));
        
        let mut checker = NonInterferenceChecker::with_context(ctx);
        
        // Nested: if (secret) { if (top_secret) { public := 1 } }
        let saved1 = checker.enter_conditional(&["secret"]);
        let saved2 = checker.enter_conditional(&["top_secret"]);
        
        // PC should be TopSecret (join of Secret and TopSecret)
        assert_eq!(
            checker.context().pc_label().confidentiality,
            ConfidentialityLevel::TopSecret
        );
        
        // Assign to public under TopSecret PC
        checker.check_assignment(
            "result",
            SecurityLabel::public_trusted(),
            &[],
            "line:100",
        );
        
        checker.exit_conditional(saved2);
        checker.exit_conditional(saved1);
        
        // Should have violation (TopSecret → Public implicit flow)
        assert!(!checker.is_secure());
        assert!(checker.violations().iter().any(|v| matches!(
            v,
            FlowViolation::ImplicitFlow { .. }
        )));
    }

    /// Extreme Case: Multiple violations in single statement
    #[test]
    fn test_multiple_violations_single_statement() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("secret", SecurityLabel::new(
            ConfidentialityLevel::Secret,
            IntegrityLevel::Untrusted, // Secret AND Untrusted!
        ));
        
        let mut checker = NonInterferenceChecker::with_context(ctx);
        
        // target expects Public AND Trusted
        checker.check_assignment(
            "sensitive_output",
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Trusted),
            &["secret"],
            "line:50",
        );
        
        // Should have BOTH violations
        assert_eq!(checker.violations().len(), 2);
        
        let has_conf_leak = checker.violations().iter().any(|v| matches!(
            v,
            FlowViolation::ConfidentialityLeak { .. }
        ));
        let has_integ_viol = checker.violations().iter().any(|v| matches!(
            v,
            FlowViolation::IntegrityViolation { .. }
        ));
        
        assert!(has_conf_leak, "Missing confidentiality leak");
        assert!(has_integ_viol, "Missing integrity violation");
    }

    /// Edge Case: Declassification at wrong location fails
    #[test]
    fn test_declassification_wrong_location() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("secret", SecurityLabel::secret_trusted());
        ctx.add_declassification("allowed_point");
        
        let mut checker = NonInterferenceChecker::with_context(ctx);
        
        // Try declassification at wrong location
        let success = checker.declassify("secret", ConfidentialityLevel::Public, "wrong_point");
        assert!(!success, "Declassification should fail at wrong location");
        
        // Variable should still be secret
        assert_eq!(
            checker.context().get_label("secret").confidentiality,
            ConfidentialityLevel::Secret
        );
    }

    /// Edge Case: Endorsement upgrades integrity
    #[test]
    fn test_endorsement_upgrades_integrity() {
        let mut ctx = SecurityContext::new();
        ctx.set_label("user_input", SecurityLabel::public_untrusted());
        ctx.add_endorsement("sanitizer");
        
        let mut checker = NonInterferenceChecker::with_context(ctx);
        
        // Endorse at allowed location
        let success = checker.endorse("user_input", IntegrityLevel::Trusted, "sanitizer");
        assert!(success);
        
        // Now should be Trusted
        assert_eq!(
            checker.context().get_label("user_input").integrity,
            IntegrityLevel::Trusted
        );
        
        // Can now flow to trusted sink
        checker.check_assignment(
            "sql_param",
            SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::Trusted),
            &["user_input"],
            "line:200",
        );
        
        assert!(checker.is_secure(), "Should be secure after endorsement");
    }

    /// Extreme Case: Large number of variables
    #[test]
    fn test_large_scale_context() {
        let mut ctx = SecurityContext::new();
        
        // Add 1000 variables with varying labels
        for i in 0..1000 {
            let label = match i % 4 {
                0 => SecurityLabel::public_trusted(),
                1 => SecurityLabel::secret_trusted(),
                2 => SecurityLabel::public_untrusted(),
                _ => SecurityLabel::new(ConfidentialityLevel::Confidential, IntegrityLevel::Trusted),
            };
            ctx.set_label(format!("var_{}", i), label);
        }
        
        // Verify all are accessible
        for i in 0..1000 {
            let label = ctx.get_label(&format!("var_{}", i));
            assert!(
                label.confidentiality != ConfidentialityLevel::TopSecret,
                "Unexpected TopSecret label"
            );
        }
        
        // Compute label from multiple sources (simplified test)
        let _combined = ctx.compute_expr_label(&["var_0", "var_1", "var_2"]);
        
        // Verify combined label is the join of all
        assert!(
            _combined.confidentiality >= ConfidentialityLevel::Confidential,
            "Combined should include Secret from var_1"
        );
    }

    /// Edge Case: Severity scoring
    #[test]
    fn test_violation_severity_scoring() {
        // TopSecret leak = severity 5
        let top_secret_leak = FlowViolation::ConfidentialityLeak {
            source_var: "key".to_string(),
            source_label: SecurityLabel::new(ConfidentialityLevel::TopSecret, IntegrityLevel::Trusted),
            sink_var: "output".to_string(),
            sink_label: SecurityLabel::public_trusted(),
            location: "line:1".to_string(),
        };
        assert_eq!(top_secret_leak.severity(), 5);
        
        // Secret leak = severity 4
        let secret_leak = FlowViolation::ConfidentialityLeak {
            source_var: "pwd".to_string(),
            source_label: SecurityLabel::secret_trusted(),
            sink_var: "log".to_string(),
            sink_label: SecurityLabel::public_trusted(),
            location: "line:2".to_string(),
        };
        assert_eq!(secret_leak.severity(), 4);
        
        // HighlyTrusted integrity = severity 5
        let high_integ = FlowViolation::IntegrityViolation {
            source_var: "input".to_string(),
            source_label: SecurityLabel::public_untrusted(),
            sink_var: "eval".to_string(),
            sink_label: SecurityLabel::new(ConfidentialityLevel::Public, IntegrityLevel::HighlyTrusted),
            location: "line:3".to_string(),
        };
        assert_eq!(high_integ.severity(), 5);
        
        // Implicit flow with Secret = severity 3
        let implicit = FlowViolation::ImplicitFlow {
            condition_var: "secret".to_string(),
            condition_label: SecurityLabel::secret_trusted(),
            affected_var: "output".to_string(),
            location: "line:4".to_string(),
        };
        assert_eq!(implicit.severity(), 3);
    }

    /// Base Case: Default labels
    #[test]
    fn test_default_labels() {
        let ctx = SecurityContext::new();
        
        // Unknown variable should return default (Public, Trusted)
        let unknown = ctx.get_label("nonexistent");
        assert_eq!(unknown.confidentiality, ConfidentialityLevel::Public);
        assert_eq!(unknown.integrity, IntegrityLevel::Trusted);
        
        // Default SecurityLabel
        let default_label = SecurityLabel::default();
        assert_eq!(default_label, SecurityLabel::public_trusted());
    }
}
