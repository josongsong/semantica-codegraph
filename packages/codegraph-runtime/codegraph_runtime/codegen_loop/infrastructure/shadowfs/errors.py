"""
ShadowFS Exception Types

All exceptions raised by ShadowFS infrastructure.
"""


class ShadowFSError(Exception):
    """Base exception for all ShadowFS errors"""

    pass


class ExternalDriftError(ShadowFSError):
    """
    File modified externally during transaction

    Raised when:
        - File mtime changed
        - File size changed
        - File content hash changed

    Recovery:
        - Abort transaction
        - Retry with fresh snapshot

    Examples:
        >>> raise ExternalDriftError(
        ...     "File main.py modified externally during transaction.\n"
        ...     "Expected hash: abc123...\n"
        ...     "Current hash: def456..."
        ... )
    """

    pass


class GeneratedFileError(ShadowFSError):
    """
    Attempt to modify generated file

    Raised when:
        - File has generated marker (@generated, DO NOT EDIT)
        - File extension is generated (.pb.py, .g.dart)
        - File is in generated directory (build/, dist/)

    Recovery:
        - Skip modification
        - Inform user

    Examples:
        >>> raise GeneratedFileError(
        ...     "Cannot modify generated file: src/proto/api_pb2.py"
        ... )
    """

    pass


class SecurityError(ShadowFSError):
    """
    Path outside project root

    Raised when:
        - Path resolves outside project_root
        - Symlink escapes jail
        - Path traversal attempt (..)

    Recovery:
        - Reject operation
        - Log security incident

    Examples:
        >>> raise SecurityError(
        ...     "Path /etc/passwd outside project root /project"
        ... )
    """

    pass


class DiskFullError(ShadowFSError):
    """
    Insufficient disk space

    Raised when:
        - Available disk space < required * 2
        - Filesystem full

    Recovery:
        - Abort transaction
        - Request user to free space

    Examples:
        >>> raise DiskFullError(
        ...     "Insufficient disk space for transaction. "
        ...     "Required: 10MB, Available: 5MB"
        ... )
    """

    pass


class CyclicSymlinkError(ShadowFSError):
    """
    Circular symlink detected

    Raised when:
        - Symlink points to itself (directly or indirectly)
        - Inode visited twice during resolution

    Recovery:
        - Skip file
        - Log warning

    Examples:
        >>> raise CyclicSymlinkError(
        ...     "Cyclic symlink detected: src/link1 -> src/link2 -> src/link1"
        ... )
    """

    pass


class ParseTimeout(ShadowFSError):
    """
    Parse exceeded timeout

    Raised when:
        - IR parsing takes > config.parse_timeout seconds
        - AST generation hangs

    Recovery:
        - Create error document
        - Continue with opaque blob

    Examples:
        >>> raise ParseTimeout(
        ...     "Parse timeout for main.py (exceeded 2.0s)"
        ... )
    """

    pass
