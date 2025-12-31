//! Repository metadata and discovery

use crate::benchmark::{BenchmarkError, BenchmarkResult2};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Repository size category
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum RepoCategory {
    Small,  // < 10k LOC
    Medium, // 10k - 100k LOC
    Large,  // > 100k LOC
}

/// Programming language
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum Language {
    Python,
    Rust,
    JavaScript,
    TypeScript,
    Go,
    Java,
    Kotlin,
}

/// Repository metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Repository {
    /// Unique identifier (e.g., "typer", "django")
    pub id: String,

    /// Display name
    pub name: String,

    /// Path to repository
    pub path: PathBuf,

    /// Size category
    pub category: RepoCategory,

    /// Source files (auto-discovered)
    pub files: Vec<PathBuf>,

    /// Total LOC
    pub total_loc: usize,

    /// Primary language
    pub language: Language,
}

impl Repository {
    /// Auto-discover repository from path
    pub fn from_path(path: PathBuf) -> BenchmarkResult2<Self> {
        if !path.exists() {
            return Err(BenchmarkError::InvalidRepo(format!(
                "Path does not exist: {:?}",
                path
            )));
        }

        let id = path
            .file_name()
            .ok_or_else(|| BenchmarkError::InvalidRepo("Invalid path".to_string()))?
            .to_string_lossy()
            .to_string();

        // Scan files
        let files = Self::scan_files(&path)?;
        let total_loc = Self::count_loc(&files)?;

        let category = match total_loc {
            0..=10_000 => RepoCategory::Small,
            10_001..=100_000 => RepoCategory::Medium,
            _ => RepoCategory::Large,
        };

        Ok(Self {
            id: id.clone(),
            name: id,
            path,
            category,
            files,
            total_loc,
            language: Language::Python, // TODO: detect from extensions
        })
    }

    /// Scan for source files
    fn scan_files(path: &PathBuf) -> BenchmarkResult2<Vec<PathBuf>> {
        let mut files = Vec::new();
        Self::scan_files_recursive(path, &mut files)?;
        Ok(files)
    }

    fn scan_files_recursive(path: &PathBuf, files: &mut Vec<PathBuf>) -> BenchmarkResult2<()> {
        for entry in std::fs::read_dir(path)? {
            let entry = entry?;
            let path = entry.path();
            let metadata = entry.metadata()?;

            if metadata.is_file() {
                // Check if it's a supported file type
                if let Some(ext) = path.extension() {
                    let ext_str = ext.to_string_lossy();
                    if matches!(
                        ext_str.as_ref(),
                        "py" | "rs" | "js" | "ts" | "go" | "java" | "kt"
                    ) {
                        files.push(path);
                    }
                }
            } else if metadata.is_dir() {
                let name = entry.file_name();
                let name_str = name.to_string_lossy();

                // Skip common ignore patterns
                if !name_str.starts_with('.')
                    && !matches!(
                        name_str.as_ref(),
                        "node_modules"
                            | "__pycache__"
                            | "target"
                            | "venv"
                            | ".venv"
                            | "build"
                            | "dist"
                    )
                {
                    Self::scan_files_recursive(&path, files)?;
                }
            }
        }
        Ok(())
    }

    /// Count total LOC (non-empty lines)
    fn count_loc(files: &[PathBuf]) -> BenchmarkResult2<usize> {
        let mut total = 0;
        for file in files {
            if let Ok(content) = std::fs::read_to_string(file) {
                total += content
                    .lines()
                    .filter(|line| !line.trim().is_empty())
                    .count();
            }
        }
        Ok(total)
    }

    /// Calculate repository size in MB
    pub fn size_mb(&self) -> f64 {
        let mut total_bytes = 0u64;
        for file in &self.files {
            if let Ok(metadata) = std::fs::metadata(file) {
                total_bytes += metadata.len();
            }
        }
        total_bytes as f64 / 1_048_576.0
    }
}
