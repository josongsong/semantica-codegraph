/// Trusted library database
///
/// Pre-defined effect specs for common libraries (Python builtins, NumPy, etc.)
use super::{EffectSet, EffectSource, EffectType};
use lazy_static::lazy_static;
use std::collections::{HashMap, HashSet};

/// Trusted library database
///
/// Contains pre-defined effect specs for trusted libraries.
pub struct TrustedLibraryDB {
    specs: HashMap<String, EffectSet>,
}

impl TrustedLibraryDB {
    /// Create a new trusted library database
    pub fn new() -> Self {
        let mut db = Self {
            specs: HashMap::new(),
        };
        db.load_builtin_specs();
        db
    }

    /// Load builtin library specifications
    fn load_builtin_specs(&mut self) {
        // Helper macro for creating single-effect sets
        macro_rules! single_effect {
            ($effect:expr) => {{
                let mut set = HashSet::new();
                set.insert($effect);
                set
            }};
        }

        // Python builtins
        self.add("builtins.print", single_effect!(EffectType::Io), true);
        self.add("builtins.len", single_effect!(EffectType::Pure), true);
        self.add("builtins.sum", single_effect!(EffectType::Pure), true);
        self.add("builtins.max", single_effect!(EffectType::Pure), true);
        self.add("builtins.min", single_effect!(EffectType::Pure), true);
        self.add("builtins.abs", single_effect!(EffectType::Pure), true);
        self.add("builtins.range", single_effect!(EffectType::Pure), true);

        // NumPy (pure functions)
        self.add("numpy.array", single_effect!(EffectType::Pure), true);
        self.add("numpy.sum", single_effect!(EffectType::Pure), true);
        self.add("numpy.dot", single_effect!(EffectType::Pure), true);
        self.add("numpy.mean", single_effect!(EffectType::Pure), true);
        self.add("numpy.std", single_effect!(EffectType::Pure), true);

        // Logging
        self.add("logging.info", single_effect!(EffectType::Log), true);
        self.add("logging.error", single_effect!(EffectType::Log), true);
        self.add("logging.warning", single_effect!(EffectType::Log), true);
        self.add("logging.debug", single_effect!(EffectType::Log), true);

        // Redis
        self.add("redis.set", single_effect!(EffectType::WriteState), true); // Idempotent
        self.add("redis.get", single_effect!(EffectType::ReadState), true);
        self.add("redis.incr", single_effect!(EffectType::WriteState), false); // Not idempotent
        self.add("redis.delete", single_effect!(EffectType::WriteState), true); // Idempotent

        // SQLAlchemy
        self.add("sqlalchemy.query", single_effect!(EffectType::DbRead), true);
        self.add("sqlalchemy.add", single_effect!(EffectType::DbWrite), false);
        self.add(
            "sqlalchemy.commit",
            single_effect!(EffectType::DbWrite),
            false,
        );
        self.add(
            "sqlalchemy.rollback",
            single_effect!(EffectType::DbWrite),
            true,
        );

        // Requests (HTTP)
        self.add("requests.get", single_effect!(EffectType::Network), true);
        self.add("requests.post", single_effect!(EffectType::Network), false);
        self.add("requests.put", single_effect!(EffectType::Network), true);
        self.add("requests.delete", single_effect!(EffectType::Network), true);

        // File I/O
        self.add("builtins.open", single_effect!(EffectType::Io), false);
        self.add(
            "pathlib.Path.read_text",
            single_effect!(EffectType::Io),
            true,
        );
        self.add(
            "pathlib.Path.write_text",
            single_effect!(EffectType::Io),
            false,
        );
    }

    /// Add a library spec
    fn add(&mut self, fqn: &str, effects: HashSet<EffectType>, idempotent: bool) {
        self.specs.insert(
            fqn.to_string(),
            EffectSet::new(
                fqn.to_string(),
                effects,
                idempotent,
                0.95, // Allowlist confidence
                EffectSource::Allowlist,
            ),
        );
    }

    /// Get effect spec for FQN
    pub fn get(&self, fqn: &str) -> Option<&EffectSet> {
        self.specs.get(fqn)
    }

    /// Check if FQN is in allowlist
    pub fn contains(&self, fqn: &str) -> bool {
        self.specs.contains_key(fqn)
    }

    /// Get all known library FQNs
    pub fn known_libraries(&self) -> Vec<&str> {
        self.specs.keys().map(|s| s.as_str()).collect()
    }
}

impl Default for TrustedLibraryDB {
    fn default() -> Self {
        Self::new()
    }
}

// Global instance
lazy_static! {
    /// Global trusted library database
    pub static ref TRUSTED_LIBRARIES: TrustedLibraryDB = TrustedLibraryDB::new();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trusted_db_creation() {
        let db = TrustedLibraryDB::new();
        assert!(!db.specs.is_empty());
    }

    #[test]
    fn test_builtin_specs() {
        let db = TrustedLibraryDB::new();

        // Check Python builtins
        let print_spec = db.get("builtins.print").unwrap();
        assert!(print_spec.effects.contains(&EffectType::Io));
        assert!(print_spec.idempotent);

        let len_spec = db.get("builtins.len").unwrap();
        assert!(len_spec.is_pure());
    }

    #[test]
    fn test_numpy_specs() {
        let db = TrustedLibraryDB::new();

        let array_spec = db.get("numpy.array").unwrap();
        assert!(array_spec.is_pure());
        assert_eq!(array_spec.confidence, 0.95);
    }

    #[test]
    fn test_logging_specs() {
        let db = TrustedLibraryDB::new();

        let info_spec = db.get("logging.info").unwrap();
        assert!(info_spec.effects.contains(&EffectType::Log));
        assert!(info_spec.idempotent);
    }

    #[test]
    fn test_redis_specs() {
        let db = TrustedLibraryDB::new();

        // SET is idempotent
        let set_spec = db.get("redis.set").unwrap();
        assert!(set_spec.idempotent);

        // INCR is not idempotent
        let incr_spec = db.get("redis.incr").unwrap();
        assert!(!incr_spec.idempotent);
    }

    #[test]
    fn test_contains() {
        let db = TrustedLibraryDB::new();

        assert!(db.contains("builtins.print"));
        assert!(db.contains("numpy.array"));
        assert!(!db.contains("unknown.function"));
    }

    #[test]
    fn test_known_libraries() {
        let db = TrustedLibraryDB::new();
        let known = db.known_libraries();

        assert!(known.contains(&"builtins.print"));
        assert!(known.contains(&"numpy.array"));
        assert!(known.len() > 20); // Should have many specs
    }

    #[test]
    fn test_global_instance() {
        let spec = TRUSTED_LIBRARIES.get("builtins.print");
        assert!(spec.is_some());
    }
}
