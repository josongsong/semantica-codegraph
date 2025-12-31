//! Fingerprint utilities with Blake3 SIMD hashing

use crate::features::cache::{CacheError, CacheResult, Fingerprint};
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;
use std::time::SystemTime;

impl Fingerprint {
    /// Compute from file path (read + hash)
    pub fn from_file(path: impl AsRef<Path>) -> CacheResult<Self> {
        let mut file = File::open(path.as_ref())?;
        let mut hasher = blake3::Hasher::new();

        // Read file in chunks and update hasher
        let mut buffer = [0u8; 8192];
        loop {
            let n = file.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            hasher.update(&buffer[..n]);
        }

        Ok(Self(hasher.finalize()))
    }

    /// Compute from file with metadata (fast path check first)
    pub fn from_file_with_metadata(path: impl AsRef<Path>) -> CacheResult<(Self, u64, u64)> {
        let path = path.as_ref();
        let metadata = path.metadata()?;

        // Extract mtime (nanoseconds)
        let mtime_ns = metadata
            .modified()?
            .duration_since(SystemTime::UNIX_EPOCH)
            .map_err(|e| CacheError::Other(format!("Invalid mtime: {}", e)))?
            .as_nanos() as u64;

        let size_bytes = metadata.len();

        // Compute content hash
        let mut file = File::open(path)?;
        let mut hasher = blake3::Hasher::new();

        // Read file in chunks and update hasher
        let mut buffer = [0u8; 8192];
        loop {
            let n = file.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            hasher.update(&buffer[..n]);
        }

        Ok((Self(hasher.finalize()), mtime_ns, size_bytes))
    }

    /// Check if two fingerprints match
    pub fn matches(&self, other: &Fingerprint) -> bool {
        self.0 == other.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_fingerprint_from_content() {
        let content = b"fn main() { println!(\"hello\"); }";

        let fp1 = Fingerprint::compute(content);
        let fp2 = Fingerprint::compute(content);

        assert_eq!(fp1, fp2);

        // Different content → different fingerprint
        let fp3 = Fingerprint::compute(b"other content");
        assert_ne!(fp1, fp3);
    }

    #[test]
    fn test_fingerprint_from_file() -> CacheResult<()> {
        let mut temp = NamedTempFile::new()?;
        temp.write_all(b"test content")?;
        temp.flush()?;

        let fp1 = Fingerprint::from_file(temp.path())?;
        let fp2 = Fingerprint::from_file(temp.path())?;

        assert_eq!(fp1, fp2);

        Ok(())
    }

    #[test]
    fn test_fingerprint_from_file_with_metadata() -> CacheResult<()> {
        let mut temp = NamedTempFile::new()?;
        temp.write_all(b"test content")?;
        temp.flush()?;

        let (fp, mtime, size) = Fingerprint::from_file_with_metadata(temp.path())?;

        assert!(mtime > 0);
        assert_eq!(size, 12); // "test content" = 12 bytes
        assert_eq!(fp, Fingerprint::compute(b"test content"));

        Ok(())
    }

    #[test]
    fn test_fingerprint_metadata_fast_path() {
        let mtime = 1234567890_000_000_000; // nanoseconds
        let size = 42;

        let fp1 = Fingerprint::from_metadata(mtime, size);
        let fp2 = Fingerprint::from_metadata(mtime, size);

        assert_eq!(fp1, fp2);

        // Different mtime → different fingerprint
        let fp3 = Fingerprint::from_metadata(mtime + 1, size);
        assert_ne!(fp1, fp3);

        // Different size → different fingerprint
        let fp4 = Fingerprint::from_metadata(mtime, size + 1);
        assert_ne!(fp1, fp4);
    }

    #[test]
    fn test_fingerprint_hex_roundtrip() {
        let fp = Fingerprint::compute(b"test");
        let hex = fp.to_hex();
        let fp2 = Fingerprint::from_hex(&hex).unwrap();

        assert_eq!(fp, fp2);
    }

    #[test]
    fn test_fingerprint_zero() {
        let zero = Fingerprint::zero();
        assert_eq!(zero.as_bytes(), &[0u8; 32]);
    }

    #[test]
    fn test_blake3_simd_performance() {
        // Test that Blake3 is using SIMD (indirectly via speed)
        let large_content = vec![0u8; 1024 * 1024]; // 1MB

        let start = std::time::Instant::now();
        for _ in 0..10 {
            let _ = Fingerprint::compute(&large_content);
        }
        let elapsed = start.elapsed();

        // Should be < 100ms for 10MB (SIMD should give ~1GB/s)
        assert!(elapsed.as_millis() < 100, "Too slow: {:?}", elapsed);
    }
}
