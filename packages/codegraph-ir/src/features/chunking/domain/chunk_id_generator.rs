//! Chunk ID Generator
//!
//! Generates unique chunk IDs with collision resolution.
//!
//! MATCHES: Python ChunkIdGenerator in chunk/id_generator.py
//!
//! ID format: chunk:{repo_id}:{kind}:{fqn}[:{hash_suffix}]
//!
//! Thread Safety:
//! - Uses `parking_lot::Mutex` for lock-free performance
//! - Safe for concurrent use from multiple threads (Rayon parallel processing)

use parking_lot::Mutex;
use std::collections::HashSet;
use std::sync::Arc;

/// Context for generating a chunk ID
///
/// MATCHES: Python ChunkIdContext
#[derive(Debug, Clone)]
pub struct ChunkIdContext<'a> {
    /// Repository identifier
    pub repo_id: &'a str,
    /// Chunk kind (repo/project/module/file/class/function)
    pub kind: &'a str,
    /// Fully qualified name (dotted notation)
    pub fqn: &'a str,
    /// Optional content hash for collision resolution (first 8 chars used)
    pub content_hash: Option<&'a str>,
}

/// Chunk ID generator with collision resolution
///
/// Thread-safe implementation using `parking_lot::Mutex` for high-performance locking.
/// All public methods are thread-safe and can be called from multiple Rayon threads.
///
/// # Example
///
/// ```
/// use codegraph_ir::features::chunking::domain::chunk_id_generator::{ChunkIdGenerator, ChunkIdContext};
///
/// let gen = ChunkIdGenerator::new();
/// let ctx = ChunkIdContext {
///     repo_id: "myrepo",
///     kind: "function",
///     fqn: "main.foo",
///     content_hash: None,
/// };
/// let id = gen.generate(&ctx);
/// assert_eq!(id, "chunk:myrepo:function:main.foo");
/// ```
///
/// # Collision Handling
///
/// If the same (repo_id, kind, fqn) combination is seen twice, appends content_hash suffix:
/// ```
/// use codegraph_ir::features::chunking::domain::chunk_id_generator::{ChunkIdGenerator, ChunkIdContext};
///
/// let gen = ChunkIdGenerator::new();
/// // First call creates base ID
/// let ctx1 = ChunkIdContext {
///     repo_id: "myrepo",
///     kind: "function",
///     fqn: "main.foo",
///     content_hash: None,
/// };
/// let _id1 = gen.generate(&ctx1);
///
/// // Second call with same FQN appends hash suffix
/// let ctx2 = ChunkIdContext {
///     repo_id: "myrepo",
///     kind: "function",
///     fqn: "main.foo",  // Same FQN!
///     content_hash: Some("a1b2c3d4e5f6g7h8"),
/// };
/// let id2 = gen.generate(&ctx2);
/// assert_eq!(id2, "chunk:myrepo:function:main.foo:a1b2c3d4");  // First 8 chars of hash
/// ```
#[derive(Debug, Clone)]
pub struct ChunkIdGenerator {
    /// Set of already-generated IDs (for uniqueness)
    ///
    /// Uses `Arc<Mutex<HashSet>>` for thread-safe sharing across Rayon threads
    seen: Arc<Mutex<HashSet<String>>>,
}

impl ChunkIdGenerator {
    /// Create a new chunk ID generator
    pub fn new() -> Self {
        Self {
            seen: Arc::new(Mutex::new(HashSet::new())),
        }
    }

    /// Generate a unique chunk ID from context
    ///
    /// Thread-safe: Uses `parking_lot::Mutex` for lock-free performance.
    ///
    /// # Algorithm
    ///
    /// 1. Generate base ID: `chunk:{repo_id}:{kind}:{fqn}`
    /// 2. If base ID not seen before:
    ///    - Add to seen set
    ///    - Return base ID
    /// 3. If collision detected:
    ///    - Append content_hash suffix (first 8 chars)
    ///    - Add to seen set
    ///    - Return `{base}:{hash_suffix}`
    ///
    /// # Arguments
    ///
    /// * `ctx` - Chunk ID context
    ///
    /// # Returns
    ///
    /// Unique chunk ID string
    pub fn generate(&self, ctx: &ChunkIdContext) -> String {
        // Generate base ID
        let base = format!("chunk:{}:{}:{}", ctx.repo_id, ctx.kind, ctx.fqn);

        // Lock and check/insert (RAII lock guard)
        let mut seen = self.seen.lock();

        // No collision - return base ID
        if !seen.contains(&base) {
            seen.insert(base.clone());
            return base;
        }

        // Collision detected - append hash suffix
        let suffix = ctx.content_hash.map(|h| &h[..8.min(h.len())]).unwrap_or("");

        let candidate = format!("{}:{}", base, suffix);
        seen.insert(candidate.clone());
        candidate
    }

    /// Reset the seen set (for testing or incremental updates)
    ///
    /// Thread-safe: Uses mutex for safe concurrent access.
    pub fn reset(&self) {
        let mut seen = self.seen.lock();
        seen.clear();
    }

    /// Check if a chunk ID has already been generated
    ///
    /// Thread-safe: Uses mutex for safe concurrent access.
    ///
    /// # Arguments
    ///
    /// * `chunk_id` - Chunk ID to check
    ///
    /// # Returns
    ///
    /// `true` if chunk ID exists in seen set
    pub fn contains(&self, chunk_id: &str) -> bool {
        let seen = self.seen.lock();
        seen.contains(chunk_id)
    }

    /// Get total number of generated IDs
    ///
    /// Thread-safe: Uses mutex for safe concurrent access.
    pub fn len(&self) -> usize {
        let seen = self.seen.lock();
        seen.len()
    }

    /// Check if no IDs have been generated
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl Default for ChunkIdGenerator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_basic() {
        let gen = ChunkIdGenerator::new();
        let ctx = ChunkIdContext {
            repo_id: "myrepo",
            kind: "function",
            fqn: "main.foo",
            content_hash: None,
        };

        let id = gen.generate(&ctx);
        assert_eq!(id, "chunk:myrepo:function:main.foo");
    }

    #[test]
    fn test_generate_collision() {
        let gen = ChunkIdGenerator::new();

        // First call - no collision
        let ctx1 = ChunkIdContext {
            repo_id: "myrepo",
            kind: "function",
            fqn: "main.foo",
            content_hash: None,
        };
        let id1 = gen.generate(&ctx1);
        assert_eq!(id1, "chunk:myrepo:function:main.foo");

        // Second call - collision, use hash suffix
        let ctx2 = ChunkIdContext {
            repo_id: "myrepo",
            kind: "function",
            fqn: "main.foo",
            content_hash: Some("a1b2c3d4e5f6g7h8"),
        };
        let id2 = gen.generate(&ctx2);
        assert_eq!(id2, "chunk:myrepo:function:main.foo:a1b2c3d4");
    }

    #[test]
    fn test_contains() {
        let gen = ChunkIdGenerator::new();
        let ctx = ChunkIdContext {
            repo_id: "myrepo",
            kind: "function",
            fqn: "main.foo",
            content_hash: None,
        };

        assert!(!gen.contains("chunk:myrepo:function:main.foo"));

        let id = gen.generate(&ctx);
        assert!(gen.contains(&id));
    }

    #[test]
    fn test_reset() {
        let gen = ChunkIdGenerator::new();
        let ctx = ChunkIdContext {
            repo_id: "myrepo",
            kind: "function",
            fqn: "main.foo",
            content_hash: None,
        };

        gen.generate(&ctx);
        assert_eq!(gen.len(), 1);

        gen.reset();
        assert_eq!(gen.len(), 0);
    }

    #[test]
    fn test_thread_safety() {
        use rayon::prelude::*;

        let gen = Arc::new(ChunkIdGenerator::new());
        let gen_clone = gen.clone();

        // Generate 1000 IDs in parallel
        let ids: Vec<String> = (0..1000)
            .into_par_iter()
            .map(|i| {
                let ctx = ChunkIdContext {
                    repo_id: "myrepo",
                    kind: "function",
                    fqn: &format!("main.func_{}", i),
                    content_hash: None,
                };
                gen_clone.generate(&ctx)
            })
            .collect();

        // All IDs should be unique
        let unique_ids: HashSet<_> = ids.iter().collect();
        assert_eq!(unique_ids.len(), 1000);

        // All IDs should be in seen set
        assert_eq!(gen.len(), 1000);
    }

    #[test]
    fn test_hash_suffix_truncation() {
        let gen = ChunkIdGenerator::new();

        // Generate first ID (no collision)
        let ctx1 = ChunkIdContext {
            repo_id: "repo",
            kind: "func",
            fqn: "foo",
            content_hash: None,
        };
        gen.generate(&ctx1);

        // Generate second ID (collision, truncate hash to 8 chars)
        let ctx2 = ChunkIdContext {
            repo_id: "repo",
            kind: "func",
            fqn: "foo",
            content_hash: Some("abcdefghijklmnop"), // 16 chars
        };
        let id2 = gen.generate(&ctx2);

        // Should only use first 8 chars
        assert_eq!(id2, "chunk:repo:func:foo:abcdefgh");
    }

    #[test]
    fn test_empty_hash_suffix() {
        let gen = ChunkIdGenerator::new();

        // Generate first ID
        let ctx1 = ChunkIdContext {
            repo_id: "repo",
            kind: "func",
            fqn: "foo",
            content_hash: None,
        };
        gen.generate(&ctx1);

        // Collision with empty hash
        let ctx2 = ChunkIdContext {
            repo_id: "repo",
            kind: "func",
            fqn: "foo",
            content_hash: Some(""),
        };
        let id2 = gen.generate(&ctx2);

        // Should append empty suffix (colon only)
        assert_eq!(id2, "chunk:repo:func:foo:");
    }
}
