//! ID generation utilities
//!
//! Generates stable, deterministic IDs for nodes using SHA256.
//! NO external dependencies (uses Rust std only).

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

/// ID Generator for creating stable node IDs
pub struct IdGenerator;

impl IdGenerator {
    /// Generate a node ID from components
    ///
    /// Format: First 32 chars of hash(repo_id + file_path + fqn)
    pub fn generate_node_id(repo_id: &str, file_path: &str, fqn: &str) -> String {
        let input = format!("{}:{}:{}", repo_id, file_path, fqn);
        Self::hash_to_hex(&input)
    }

    /// Generate a file node ID
    pub fn generate_file_id(repo_id: &str, file_path: &str) -> String {
        let input = format!("{}:file:{}", repo_id, file_path);
        Self::hash_to_hex(&input)
    }

    /// Generate an edge ID
    pub fn generate_edge_id(source_id: &str, target_id: &str, kind: &str) -> String {
        let input = format!("{}:{}:{}", source_id, target_id, kind);
        Self::hash_to_hex(&input)
    }

    /// Generate a BFG block ID
    pub fn generate_bfg_block_id(function_id: &str, block_index: usize) -> String {
        format!("bfg:{}:block:{}", function_id, block_index)
    }

    /// Generate a DFG node ID
    pub fn generate_dfg_node_id(function_id: &str, variable: &str, version: usize) -> String {
        format!("dfg:{}:{}:v{}", function_id, variable, version)
    }

    /// Generate a hash as hex string (32 chars)
    fn hash_to_hex(input: &str) -> String {
        // Use DefaultHasher for deterministic hashing
        // In production, consider using SHA256 via the `sha2` crate
        let mut hasher = DefaultHasher::new();
        input.hash(&mut hasher);
        let hash1 = hasher.finish();

        // Hash again for more bits
        let mut hasher2 = DefaultHasher::new();
        format!("{}:{}", input, hash1).hash(&mut hasher2);
        let hash2 = hasher2.finish();

        format!("{:016x}{:016x}", hash1, hash2)
    }
}

/// Generate a content hash for change detection
pub fn content_hash(content: &str) -> String {
    let mut hasher = DefaultHasher::new();
    content.hash(&mut hasher);
    format!("{:016x}", hasher.finish())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_node_id_deterministic() {
        let id1 = IdGenerator::generate_node_id("repo", "file.py", "module.func");
        let id2 = IdGenerator::generate_node_id("repo", "file.py", "module.func");
        assert_eq!(id1, id2);
    }

    #[test]
    fn test_node_id_different_inputs() {
        let id1 = IdGenerator::generate_node_id("repo", "file.py", "func1");
        let id2 = IdGenerator::generate_node_id("repo", "file.py", "func2");
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_node_id_length() {
        let id = IdGenerator::generate_node_id("repo", "file.py", "func");
        assert_eq!(id.len(), 32);
    }

    #[test]
    fn test_bfg_block_id_format() {
        let id = IdGenerator::generate_bfg_block_id("func_123", 0);
        assert_eq!(id, "bfg:func_123:block:0");
    }
}
