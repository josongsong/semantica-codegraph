/// Git history analysis errors
use thiserror::Error;

#[derive(Debug, Error)]
pub enum GitError {
    #[error("Not a git repository: {0}")]
    NotARepository(String),

    #[error("Git command failed: {0}")]
    CommandFailed(String),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, GitError>;
