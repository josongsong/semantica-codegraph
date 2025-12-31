/// Effect set model
use super::EffectType;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

/// Effect source (how was this effect determined?)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EffectSource {
    /// Static analysis from code
    Static,
    /// From trusted library database
    Allowlist,
    /// Inferred from patterns
    Inferred,
    /// Unknown (pessimistic default)
    Unknown,
}

/// Effect set for a function
///
/// Tracks all effects a function may have.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EffectSet {
    /// Symbol ID (function FQN)
    pub symbol_id: String,

    /// Set of effects
    pub effects: HashSet<EffectType>,

    /// Whether the function is idempotent
    /// (calling multiple times has same effect as calling once)
    pub idempotent: bool,

    /// Confidence (0.0-1.0)
    /// - 1.0: Static analysis (certain)
    /// - 0.95: Allowlist (high confidence)
    /// - 0.8: Inferred (medium confidence)
    /// - 0.5: Unknown (low confidence)
    pub confidence: f64,

    /// Source of this effect set
    pub source: EffectSource,
}

impl EffectSet {
    /// Create a new effect set
    pub fn new(
        symbol_id: String,
        effects: HashSet<EffectType>,
        idempotent: bool,
        confidence: f64,
        source: EffectSource,
    ) -> Self {
        Self {
            symbol_id,
            effects,
            idempotent,
            confidence,
            source,
        }
    }

    /// Create a pure effect set
    pub fn pure(symbol_id: String) -> Self {
        let mut effects = HashSet::new();
        effects.insert(EffectType::Pure);

        Self {
            symbol_id,
            effects,
            idempotent: true,
            confidence: 1.0,
            source: EffectSource::Static,
        }
    }

    /// Check if this is a pure function
    pub fn is_pure(&self) -> bool {
        self.effects.len() == 1 && self.effects.contains(&EffectType::Pure)
    }

    /// Check if this has side effects
    pub fn has_side_effects(&self) -> bool {
        self.effects.iter().any(|e| e.is_side_effect())
    }

    /// Get maximum severity score
    pub fn max_severity(&self) -> u8 {
        self.effects
            .iter()
            .map(|e| e.severity_score())
            .max()
            .unwrap_or(0)
    }

    /// Merge with another effect set
    ///
    /// Takes union of effects and minimum confidence.
    pub fn merge(&mut self, other: &EffectSet) {
        self.effects.extend(&other.effects);
        self.confidence = self.confidence.min(other.confidence);

        if !other.idempotent {
            self.idempotent = false;
        }

        // Remove Pure if there are other effects
        if self.effects.len() > 1 {
            self.effects.remove(&EffectType::Pure);
        }
    }

    /// Get human-readable summary
    pub fn summary(&self) -> String {
        if self.is_pure() {
            return "PURE".to_string();
        }

        let mut effect_names: Vec<_> = self
            .effects
            .iter()
            .filter(|e| **e != EffectType::Pure)
            .map(|e| e.to_string())
            .collect();

        effect_names.sort();
        effect_names.join(", ")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pure_effect_set() {
        let effect_set = EffectSet::pure("test.func".to_string());

        assert!(effect_set.is_pure());
        assert!(!effect_set.has_side_effects());
        assert_eq!(effect_set.max_severity(), 0);
        assert_eq!(effect_set.summary(), "PURE");
    }

    #[test]
    fn test_side_effects() {
        let mut effects = HashSet::new();
        effects.insert(EffectType::Io);
        effects.insert(EffectType::DbWrite);

        let effect_set = EffectSet::new(
            "test.func".to_string(),
            effects,
            false,
            1.0,
            EffectSource::Static,
        );

        assert!(!effect_set.is_pure());
        assert!(effect_set.has_side_effects());
        assert_eq!(effect_set.max_severity(), 9); // DbWrite
    }

    #[test]
    fn test_merge() {
        let mut set1 = EffectSet::pure("test.func1".to_string());

        let mut effects2 = HashSet::new();
        effects2.insert(EffectType::Io);
        let set2 = EffectSet::new(
            "test.func2".to_string(),
            effects2,
            true,
            0.8,
            EffectSource::Inferred,
        );

        set1.merge(&set2);

        assert!(!set1.is_pure());
        assert!(set1.effects.contains(&EffectType::Io));
        assert!(!set1.effects.contains(&EffectType::Pure)); // Pure removed
        assert_eq!(set1.confidence, 0.8); // Min confidence
    }

    #[test]
    fn test_idempotent_merge() {
        let mut set1 = EffectSet::pure("test.func1".to_string());
        assert!(set1.idempotent);

        let mut effects2 = HashSet::new();
        effects2.insert(EffectType::Io);
        let set2 = EffectSet::new(
            "test.func2".to_string(),
            effects2,
            false, // Not idempotent
            1.0,
            EffectSource::Static,
        );

        set1.merge(&set2);
        assert!(!set1.idempotent); // Idempotent lost
    }
}
