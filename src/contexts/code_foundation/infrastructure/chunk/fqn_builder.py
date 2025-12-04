"""
FQN (Fully Qualified Name) Builder

Provides centralized, consistent FQN generation for all chunk types.

Ensures:
- Consistent FQN format across all chunk levels
- Language-specific handling
- Proper dotted notation
"""


class FQNBuilder:
    """
    Centralized FQN builder for chunks.

    Ensures consistent FQN generation across:
    - Repo → Project → Module → File → Class → Function
    """

    # Language-specific file extensions
    LANGUAGE_EXTENSIONS = {
        "python": ".py",
        "typescript": ".ts",
        "javascript": ".js",
        "go": ".go",
        "rust": ".rs",
        "java": ".java",
        "cpp": ".cpp",
        "c": ".c",
    }

    @staticmethod
    def from_file_path(file_path: str, language: str) -> str:
        """
        Generate FQN from file path.

        Args:
            file_path: File path (e.g., "backend/api/routes.py")
            language: Programming language

        Returns:
            FQN (e.g., "backend.api.routes")

        Examples:
            >>> FQNBuilder.from_file_path("backend/api/routes.py", "python")
            "backend.api.routes"
            >>> FQNBuilder.from_file_path("src/main.ts", "typescript")
            "src.main"
        """
        # Remove extension
        ext = FQNBuilder.LANGUAGE_EXTENSIONS.get(language, ".py")
        fqn = file_path
        if fqn.endswith(ext):
            fqn = fqn[: -len(ext)]

        # Replace path separators with dots
        fqn = fqn.replace("/", ".")
        fqn = fqn.replace("\\", ".")  # Windows support

        return fqn

    @staticmethod
    def from_module_path(parts: list[str]) -> str:
        """
        Generate FQN from module path parts.

        Args:
            parts: Module path components (e.g., ["backend", "api"])

        Returns:
            FQN (e.g., "backend.api")

        Examples:
            >>> FQNBuilder.from_module_path(["backend", "api"])
            "backend.api"
        """
        return ".".join(parts)

    @staticmethod
    def from_symbol(parent_fqn: str, symbol_name: str) -> str:
        """
        Generate FQN for a symbol (class/function).

        Args:
            parent_fqn: Parent's FQN (e.g., "backend.api.routes")
            symbol_name: Symbol name (e.g., "UserController")

        Returns:
            FQN (e.g., "backend.api.routes.UserController")

        Examples:
            >>> FQNBuilder.from_symbol("backend.api.routes", "UserController")
            "backend.api.routes.UserController"
            >>> FQNBuilder.from_symbol("backend.api.routes.UserController", "get_user")
            "backend.api.routes.UserController.get_user"
        """
        if not parent_fqn:
            return symbol_name
        return f"{parent_fqn}.{symbol_name}"

    @staticmethod
    def get_parent_fqn(fqn: str) -> str | None:
        """
        Extract parent FQN from a full FQN.

        Args:
            fqn: Full FQN (e.g., "backend.api.routes.UserController")

        Returns:
            Parent FQN (e.g., "backend.api.routes") or None if root

        Examples:
            >>> FQNBuilder.get_parent_fqn("backend.api.routes.UserController")
            "backend.api.routes"
            >>> FQNBuilder.get_parent_fqn("backend")
            None
        """
        parts = fqn.split(".")
        if len(parts) <= 1:
            return None
        return ".".join(parts[:-1])

    @staticmethod
    def get_symbol_name(fqn: str) -> str:
        """
        Extract symbol name from FQN.

        Args:
            fqn: Full FQN (e.g., "backend.api.routes.UserController")

        Returns:
            Symbol name (e.g., "UserController")

        Examples:
            >>> FQNBuilder.get_symbol_name("backend.api.routes.UserController")
            "UserController"
            >>> FQNBuilder.get_symbol_name("backend")
            "backend"
        """
        return fqn.split(".")[-1]
