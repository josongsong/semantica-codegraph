/// Git command executor
use super::error::{GitError, Result};
use std::path::{Path, PathBuf};
use std::process::Command;

/// Git command executor
///
/// Executes git commands in a repository.
pub struct GitExecutor {
    repo_path: PathBuf,
}

impl GitExecutor {
    /// Create new git executor
    pub fn new(repo_path: impl AsRef<Path>) -> Result<Self> {
        let path = repo_path.as_ref().to_path_buf();

        if !path.join(".git").exists() {
            return Err(GitError::NotARepository(path.display().to_string()));
        }

        Ok(Self { repo_path: path })
    }

    /// Run git command
    pub fn run_command(&self, args: &[&str]) -> Result<String> {
        let output = Command::new("git")
            .args(args)
            .current_dir(&self.repo_path)
            .output()?;

        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            Err(GitError::CommandFailed(
                String::from_utf8_lossy(&output.stderr).to_string(),
            ))
        }
    }

    /// Get repository path
    pub fn repo_path(&self) -> &Path {
        &self.repo_path
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_git_executor_invalid_repo() {
        let result = GitExecutor::new("/tmp/not_a_repo");
        assert!(result.is_err());
    }
}
