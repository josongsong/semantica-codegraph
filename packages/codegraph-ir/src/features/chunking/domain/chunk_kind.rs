//! Chunk kind enumeration
//!
//! Represents the 6-level chunk hierarchy:
//! Repo → Project → Module → File → Class → Function
//!
//! MATCHES: Python ChunkKind in chunk/models.py

use serde::{Deserialize, Serialize};
use std::fmt;

/// Chunk kind enumeration
///
/// Represents hierarchical code structure from repository down to function level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ChunkKind {
    /// Repository root (top-level)
    Repo,
    /// Project within repository (for monorepos)
    Project,
    /// Module (file without extension: "pkg/mod.py" → "pkg.mod")
    Module,
    /// File (actual source file)
    File,
    /// Class/Interface/Struct
    Class,
    /// Function/Method
    Function,

    // Extended chunk types (P1/P2 features)
    /// Docstring chunk (API documentation)
    Docstring,
    /// File header chunk (license, imports summary)
    FileHeader,
    /// Skeleton chunk (signature without body)
    Skeleton,
    /// Usage chunk (call site)
    Usage,
    /// Constant chunk (global const/enum)
    Constant,
    /// Variable chunk (module-level var)
    Variable,
}

impl ChunkKind {
    /// Convert to string representation for ID generation
    pub fn as_str(&self) -> &'static str {
        match self {
            ChunkKind::Repo => "repo",
            ChunkKind::Project => "project",
            ChunkKind::Module => "module",
            ChunkKind::File => "file",
            ChunkKind::Class => "class",
            ChunkKind::Function => "function",
            ChunkKind::Docstring => "docstring",
            ChunkKind::FileHeader => "file_header",
            ChunkKind::Skeleton => "skeleton",
            ChunkKind::Usage => "usage",
            ChunkKind::Constant => "constant",
            ChunkKind::Variable => "variable",
        }
    }

    /// Get hierarchy level (0 = repo, 5 = function)
    pub fn hierarchy_level(&self) -> usize {
        match self {
            ChunkKind::Repo => 0,
            ChunkKind::Project => 1,
            ChunkKind::Module => 2,
            ChunkKind::File => 3,
            ChunkKind::Class => 4,
            ChunkKind::Function => 5,
            // Extended types are at same level as their semantic kind
            ChunkKind::Docstring | ChunkKind::Skeleton => 5, // Function-level
            ChunkKind::FileHeader => 3,                      // File-level
            ChunkKind::Usage => 5,                           // Function-level
            ChunkKind::Constant | ChunkKind::Variable => 3,  // File-level
        }
    }

    /// Check if this is a structural chunk (part of 6-level hierarchy)
    pub fn is_structural(&self) -> bool {
        matches!(
            self,
            ChunkKind::Repo
                | ChunkKind::Project
                | ChunkKind::Module
                | ChunkKind::File
                | ChunkKind::Class
                | ChunkKind::Function
        )
    }

    /// Check if this is an extended chunk (P1/P2 features)
    pub fn is_extended(&self) -> bool {
        !self.is_structural()
    }
}

impl fmt::Display for ChunkKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl std::str::FromStr for ChunkKind {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "repo" => Ok(ChunkKind::Repo),
            "project" => Ok(ChunkKind::Project),
            "module" => Ok(ChunkKind::Module),
            "file" => Ok(ChunkKind::File),
            "class" => Ok(ChunkKind::Class),
            "function" => Ok(ChunkKind::Function),
            "docstring" => Ok(ChunkKind::Docstring),
            "file_header" => Ok(ChunkKind::FileHeader),
            "skeleton" => Ok(ChunkKind::Skeleton),
            "usage" => Ok(ChunkKind::Usage),
            "constant" => Ok(ChunkKind::Constant),
            "variable" => Ok(ChunkKind::Variable),
            _ => Err(format!("Unknown chunk kind: {}", s)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chunk_kind_as_str() {
        assert_eq!(ChunkKind::Repo.as_str(), "repo");
        assert_eq!(ChunkKind::Function.as_str(), "function");
        assert_eq!(ChunkKind::Docstring.as_str(), "docstring");
    }

    #[test]
    fn test_hierarchy_level() {
        assert_eq!(ChunkKind::Repo.hierarchy_level(), 0);
        assert_eq!(ChunkKind::Project.hierarchy_level(), 1);
        assert_eq!(ChunkKind::Module.hierarchy_level(), 2);
        assert_eq!(ChunkKind::File.hierarchy_level(), 3);
        assert_eq!(ChunkKind::Class.hierarchy_level(), 4);
        assert_eq!(ChunkKind::Function.hierarchy_level(), 5);
    }

    #[test]
    fn test_is_structural() {
        assert!(ChunkKind::Repo.is_structural());
        assert!(ChunkKind::Function.is_structural());
        assert!(!ChunkKind::Docstring.is_structural());
        assert!(!ChunkKind::Usage.is_structural());
    }

    #[test]
    fn test_from_str() {
        assert_eq!("repo".parse::<ChunkKind>().unwrap(), ChunkKind::Repo);
        assert_eq!(
            "function".parse::<ChunkKind>().unwrap(),
            ChunkKind::Function
        );
        assert!("invalid".parse::<ChunkKind>().is_err());
    }
}
