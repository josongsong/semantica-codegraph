"""
Python Import Resolver

Resolves Python import statements to actual module paths, handling:
- Absolute imports: import module, from module import name
- Relative imports: from . import x, from .. import y
- Standard library detection
- Third-party package detection
"""

from pathlib import Path

from src.contexts.code_foundation.infrastructure.dependency.models import DependencyKind


class PythonResolver:
    """
    Resolves Python imports to module paths and classifies them.

    Example:
        ```python
        resolver = PythonResolver(repo_root="/path/to/repo")

        # Resolve absolute import
        kind, resolved = resolver.resolve_import(
            "src.foundation.ir.models",
            current_file="src/foundation/graph/builder.py"
        )
        # Returns: (DependencyKind.INTERNAL, "src.foundation.ir.models")

        # Resolve relative import
        kind, resolved = resolver.resolve_import(
            "..ir.models",
            current_file="src/foundation/graph/builder.py"
        )
        # Returns: (DependencyKind.INTERNAL, "src.foundation.ir.models")

        # Resolve stdlib
        kind, resolved = resolver.resolve_import("os.path")
        # Returns: (DependencyKind.EXTERNAL_STDLIB, "os.path")
        ```
    """

    # Python standard library modules (Python 3.10+)
    STDLIB_MODULES = {
        "__future__",
        "abc",
        "aifc",
        "argparse",
        "array",
        "ast",
        "asynchat",
        "asyncio",
        "asyncore",
        "atexit",
        "audioop",
        "base64",
        "bdb",
        "binascii",
        "binhex",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cgi",
        "cgitb",
        "chunk",
        "cmath",
        "cmd",
        "code",
        "codecs",
        "codeop",
        "collections",
        "colorsys",
        "compileall",
        "concurrent",
        "configparser",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "crypt",
        "csv",
        "ctypes",
        "curses",
        "dataclasses",
        "datetime",
        "dbm",
        "decimal",
        "difflib",
        "dis",
        "distutils",
        "doctest",
        "email",
        "encodings",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "formatter",
        "fractions",
        "ftplib",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "graphlib",
        "grp",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "imaplib",
        "imghdr",
        "imp",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "lib2to3",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "mailbox",
        "mailcap",
        "marshal",
        "math",
        "mimetypes",
        "mmap",
        "modulefinder",
        "msilib",
        "msvcrt",
        "multiprocessing",
        "netrc",
        "nis",
        "nntplib",
        "numbers",
        "operator",
        "optparse",
        "os",
        "ossaudiodev",
        "pathlib",
        "pdb",
        "pickle",
        "pickletools",
        "pipes",
        "pkgutil",
        "platform",
        "plistlib",
        "poplib",
        "posix",
        "posixpath",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "pyclbr",
        "pydoc",
        "queue",
        "quopri",
        "random",
        "re",
        "readline",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "smtpd",
        "smtplib",
        "sndhdr",
        "socket",
        "socketserver",
        "spwd",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "sunau",
        "symbol",
        "symtable",
        "sys",
        "sysconfig",
        "syslog",
        "tabnanny",
        "tarfile",
        "telnetlib",
        "tempfile",
        "termios",
        "test",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "tomllib",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "turtle",
        "turtledemo",
        "types",
        "typing",
        "typing_extensions",
        "unicodedata",
        "unittest",
        "urllib",
        "uu",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "winreg",
        "winsound",
        "wsgiref",
        "xdrlib",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
        "zoneinfo",
    }

    def __init__(self, repo_root: Path):
        """
        Initialize resolver.

        Args:
            repo_root: Absolute path to repository root
        """
        self.repo_root = Path(repo_root).resolve()

    def resolve_import(
        self,
        import_path: str,
        current_file: str | Path | None = None,
        current_module: str | None = None,
    ) -> tuple[DependencyKind, str]:
        """
        Resolve an import statement to its actual module path and classify it.

        Args:
            import_path: Import path (e.g., "src.foundation.ir.models" or "..ir.models")
            current_file: Absolute path to file containing the import (for relative imports)
            current_module: Module path of importing file (e.g., "src.foundation.graph.builder")

        Returns:
            Tuple of (DependencyKind, resolved_module_path)
        """
        # Handle relative imports
        if import_path.startswith("."):
            return self._resolve_relative_import(import_path, current_file, current_module)

        # Handle absolute imports
        return self._resolve_absolute_import(import_path)

    def _resolve_relative_import(
        self,
        import_path: str,
        current_file: str | Path | None,
        current_module: str | None,
    ) -> tuple[DependencyKind, str]:
        """
        Resolve relative import (from . import x, from .. import y).

        Args:
            import_path: Relative import path (starts with ".")
            current_file: File containing the import
            current_module: Module path of importing file

        Returns:
            Tuple of (DependencyKind, resolved_module_path)
        """
        # Count leading dots
        level = 0
        for char in import_path:
            if char == ".":
                level += 1
            else:
                break

        # Get remaining path after dots
        remaining = import_path[level:]

        # Use current_module if available
        if current_module:
            module_parts = current_module.split(".")
            # Go up 'level' levels
            if level > len(module_parts):
                # Invalid relative import (goes above root)
                return (DependencyKind.UNRESOLVED, import_path)

            # Get parent package at the right level
            parent_parts = module_parts[: len(module_parts) - level]

            # Add remaining path
            if remaining:
                resolved_parts = parent_parts + remaining.split(".")
            else:
                resolved_parts = parent_parts

            resolved = ".".join(resolved_parts)

            # Check if it's internal
            if self._is_internal_module(resolved):
                return (DependencyKind.INTERNAL, resolved)
            else:
                return (DependencyKind.UNRESOLVED, import_path)

        # Fallback: use file path
        if current_file:
            current_path = Path(current_file).resolve()

            # Make relative to repo root
            try:
                rel_path = current_path.relative_to(self.repo_root)
            except ValueError:
                # File is outside repo
                return (DependencyKind.UNRESOLVED, import_path)

            # Convert to module path (remove .py extension)
            module_parts = list(rel_path.parts[:-1]) + [rel_path.stem]

            # Go up 'level' levels
            if level > len(module_parts):
                return (DependencyKind.UNRESOLVED, import_path)

            parent_parts = module_parts[: len(module_parts) - level]

            # Add remaining path
            if remaining:
                resolved_parts = parent_parts + remaining.split(".")
            else:
                resolved_parts = parent_parts

            resolved = ".".join(resolved_parts)

            # Check if it's internal
            if self._is_internal_module(resolved):
                return (DependencyKind.INTERNAL, resolved)
            else:
                return (DependencyKind.UNRESOLVED, import_path)

        # Can't resolve without context
        return (DependencyKind.UNRESOLVED, import_path)

    def _resolve_absolute_import(self, import_path: str) -> tuple[DependencyKind, str]:
        """
        Resolve absolute import.

        Args:
            import_path: Absolute import path (e.g., "src.foundation.ir.models")

        Returns:
            Tuple of (DependencyKind, resolved_module_path)
        """
        # Check if it's a standard library module
        root_module = import_path.split(".")[0]
        if self._is_stdlib_module(root_module):
            return (DependencyKind.EXTERNAL_STDLIB, import_path)

        # Check if it's an internal module
        if self._is_internal_module(import_path):
            return (DependencyKind.INTERNAL, import_path)

        # Otherwise, it's an external package
        return (DependencyKind.EXTERNAL_PACKAGE, import_path)

    def _is_stdlib_module(self, module_name: str) -> bool:
        """
        Check if a module is part of the Python standard library.

        Args:
            module_name: Root module name (first part of dotted path)

        Returns:
            True if it's a stdlib module
        """
        return module_name in self.STDLIB_MODULES

    def _is_internal_module(self, module_path: str) -> bool:
        """
        Check if a module path corresponds to an internal (same-repo) module.

        Args:
            module_path: Dotted module path

        Returns:
            True if the module exists in the repository
        """
        # Try to find the file
        # Convert module path to file path
        parts = module_path.split(".")

        # Try as a file
        file_path = self.repo_root / Path(*parts[:-1]) / f"{parts[-1]}.py"
        if file_path.exists():
            return True

        # Try as a package
        package_path = self.repo_root / Path(*parts) / "__init__.py"
        if package_path.exists():
            return True

        # Try without last part as file (for submodules)
        if len(parts) > 1:
            file_path = self.repo_root / Path(*parts) / "__init__.py"
            if file_path.exists():
                return True

        return False

    def get_module_file_path(self, module_path: str) -> Path | None:
        """
        Get the file path for an internal module.

        Args:
            module_path: Dotted module path

        Returns:
            Absolute path to the module file, or None if not found
        """
        parts = module_path.split(".")

        # Try as a file
        file_path = self.repo_root / Path(*parts[:-1]) / f"{parts[-1]}.py"
        if file_path.exists():
            return file_path.resolve()

        # Try as a package
        package_path = self.repo_root / Path(*parts) / "__init__.py"
        if package_path.exists():
            return package_path.resolve()

        # Try without last part (for submodules)
        if len(parts) > 1:
            file_path = self.repo_root / Path(*parts) / "__init__.py"
            if file_path.exists():
                return file_path.resolve()

        return None

    def extract_package_name(self, module_path: str) -> str:
        """
        Extract the package name from a module path.

        For external packages, this returns the root package name.
        For internal modules, returns the first component.

        Args:
            module_path: Dotted module path

        Returns:
            Package name (root component)
        """
        return module_path.split(".")[0]


def _example_usage():
    """Example demonstrating Python import resolution."""
    resolver = PythonResolver(repo_root=Path.cwd())

    # Test various imports
    test_cases = [
        ("src.foundation.ir.models", None, None),
        ("os.path", None, None),
        ("numpy", None, None),
        ("..ir.models", "src/foundation/graph/builder.py", "src.foundation.graph.builder"),
        (".models", "src/foundation/ir/builder.py", "src.foundation.ir.builder"),
    ]

    print("=== Python Import Resolution ===")
    for import_path, current_file, current_module in test_cases:
        kind, resolved = resolver.resolve_import(import_path, current_file, current_module)
        print(f"\nImport: {import_path}")
        if current_file:
            print(f"  From: {current_file}")
        print(f"  Kind: {kind.value}")
        print(f"  Resolved: {resolved}")

        if kind == DependencyKind.INTERNAL:
            file_path = resolver.get_module_file_path(resolved)
            if file_path:
                print(f"  File: {file_path}")


if __name__ == "__main__":
    _example_usage()
