//! Core types for SOTA cache system

use blake3::Hash as Blake3Hash;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

/// Language enum (interned)
#[derive(Debug, Clone, Copy, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub enum Language {
    Python,
    TypeScript,
    JavaScript,
    Rust,
    Java,
    Kotlin,
    Go,
}

impl Language {
    pub fn as_str(&self) -> &'static str {
        match self {
            Language::Python => "python",
            Language::TypeScript => "typescript",
            Language::JavaScript => "javascript",
            Language::Rust => "rust",
            Language::Java => "java",
            Language::Kotlin => "kotlin",
            Language::Go => "go",
        }
    }
}

/// File identifier (interned path + language)
///
/// Uses Arc<str> for zero-copy string deduplication across cache layers.
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub struct FileId {
    /// Interned file path (deduplication)
    pub path: Arc<str>,

    /// Programming language
    pub language: Language,
}

impl FileId {
    pub fn new(path: impl Into<Arc<str>>, language: Language) -> Self {
        Self {
            path: path.into(),
            language,
        }
    }

    pub fn from_path_str(path: &str, language: Language) -> Self {
        Self {
            path: Arc::from(path),
            language,
        }
    }
}

/// Content fingerprint (Blake3 hash)
///
/// Blake3 provides:
/// - SIMD acceleration (AVX2/AVX-512 on x86_64)
/// - 3x faster than xxHash3
/// - Cryptographically secure (collision resistance)
#[derive(Debug, Clone, Copy, Hash, Eq, PartialEq)]
pub struct Fingerprint(pub Blake3Hash); // Public for construction

impl Fingerprint {
    /// Compute fingerprint from file content (SIMD-accelerated)
    pub fn compute(content: &[u8]) -> Self {
        Self(blake3::hash(content))
    }

    /// Fast path: from file metadata (mtime + size)
    ///
    /// This is a probabilistic fingerprint - two different files with same
    /// mtime+size will have same fingerprint. Use only for fast path checks,
    /// always verify with content hash on cache hit.
    pub fn from_metadata(mtime_ns: u64, size_bytes: u64) -> Self {
        let mut hasher = blake3::Hasher::new();
        hasher.update(&mtime_ns.to_le_bytes());
        hasher.update(&size_bytes.to_le_bytes());
        Self(hasher.finalize())
    }

    /// Create fingerprint from Blake3 hash (for deserialization)
    pub fn new(hash: Blake3Hash) -> Self {
        Self(hash)
    }

    /// Zero fingerprint (placeholder)
    pub fn zero() -> Self {
        Self(blake3::Hash::from_bytes([0u8; 32]))
    }

    /// Convert to hex string
    pub fn to_hex(&self) -> String {
        self.0.to_hex().to_string()
    }

    /// From hex string
    pub fn from_hex(hex: &str) -> Result<Self, blake3::HexError> {
        Ok(Self(blake3::Hash::from_hex(hex)?))
    }

    /// As bytes (for storage)
    pub fn as_bytes(&self) -> &[u8; 32] {
        self.0.as_bytes()
    }
}

// Custom serde implementation for Fingerprint (Blake3Hash doesn't implement serde)
impl Serialize for Fingerprint {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        // Serialize as hex string
        serializer.serialize_str(&self.to_hex())
    }
}

impl<'de> Deserialize<'de> for Fingerprint {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let hex_str = String::deserialize(deserializer)?;
        Self::from_hex(&hex_str).map_err(serde::de::Error::custom)
    }
}

/// File metadata (for L0 fast path)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMetadata {
    /// Last modified time (nanoseconds since Unix epoch)
    pub mtime_ns: u64,

    /// File size in bytes
    pub size_bytes: u64,

    /// Content fingerprint (Blake3)
    pub fingerprint: Fingerprint,
}

impl FileMetadata {
    pub fn new(mtime_ns: u64, size_bytes: u64, fingerprint: Fingerprint) -> Self {
        Self {
            mtime_ns,
            size_bytes,
            fingerprint,
        }
    }

    /// Check if metadata matches (fast path)
    pub fn matches_fast(&self, mtime_ns: u64, size_bytes: u64) -> bool {
        self.mtime_ns == mtime_ns && self.size_bytes == size_bytes
    }
}

/// Cache key (file + fingerprint)
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub struct CacheKey {
    pub file_id: FileId,
    pub fingerprint: Fingerprint,
}

impl CacheKey {
    pub fn new(file_id: FileId, fingerprint: Fingerprint) -> Self {
        Self {
            file_id,
            fingerprint,
        }
    }

    /// Create key from path, language, and content
    pub fn from_content(path: &str, language: Language, content: &[u8]) -> Self {
        Self {
            file_id: FileId::from_path_str(path, language),
            fingerprint: Fingerprint::compute(content),
        }
    }

    /// Extract FileId from cache key
    pub fn to_file_id(&self) -> FileId {
        self.file_id.clone()
    }

    /// Create key from FileId (with zero fingerprint)
    pub fn from_file_id(file_id: FileId) -> Self {
        Self {
            file_id,
            fingerprint: Fingerprint::zero(),
        }
    }

    /// Serialize to bytes (for disk cache file naming)
    pub fn as_bytes(&self) -> Vec<u8> {
        // Combine file_id path + language + fingerprint
        let mut bytes = Vec::new();
        bytes.extend_from_slice(self.file_id.path.as_bytes());
        bytes.push(self.file_id.language as u8);
        bytes.extend_from_slice(self.fingerprint.as_bytes());
        bytes
    }

    /// Get language from cache key
    pub fn language(&self) -> Language {
        self.file_id.language
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fingerprint_deterministic() {
        let content = b"print('hello')";

        let fp1 = Fingerprint::compute(content);
        let fp2 = Fingerprint::compute(content);

        assert_eq!(fp1, fp2);
    }

    #[test]
    fn test_fingerprint_metadata_fast_path() {
        let mtime = 1234567890;
        let size = 42;

        let fp1 = Fingerprint::from_metadata(mtime, size);
        let fp2 = Fingerprint::from_metadata(mtime, size);

        assert_eq!(fp1, fp2);

        // Different metadata → different fingerprint
        let fp3 = Fingerprint::from_metadata(mtime + 1, size);
        assert_ne!(fp1, fp3);
    }

    #[test]
    fn test_cache_key_equality() {
        let key1 = CacheKey::from_content("a.py", Language::Python, b"code");
        let key2 = CacheKey::from_content("a.py", Language::Python, b"code");

        assert_eq!(key1, key2);

        // Different content → different key
        let key3 = CacheKey::from_content("a.py", Language::Python, b"other");
        assert_ne!(key1, key3);
    }
}
