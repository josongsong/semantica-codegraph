"""
Package Metadata Models

Tracks external dependencies and their versions.
SCIP-compatible package information.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PackageMetadata:
    """
    External package/dependency metadata.

    Tracks information about external dependencies:
    - Python: pip packages (requests, numpy, etc.)
    - TypeScript: npm packages (@types/node, etc.)
    - Go: go modules (github.com/...)
    - Java: Maven coordinates

    Example:
        PackageMetadata(
            name="requests",
            version="2.31.0",
            manager="pip",
            registry="https://pypi.org/project/requests/2.31.0/",
            license="Apache-2.0",
        )
    """

    # Core fields
    name: str  # Package name (e.g., "requests", "@types/node")
    version: str  # Version string (e.g., "2.31.0", "^16.0.0")
    manager: str  # Package manager ("pip", "npm", "go", "maven", etc.)

    # Optional metadata
    registry: str | None = None  # Registry URL (pypi.org, npmjs.com, etc.)
    license: str | None = None  # License (MIT, Apache-2.0, etc.)
    homepage: str | None = None  # Project homepage
    description: str | None = None  # Short description

    # Import mapping (for symbol resolution)
    # e.g., {"requests": "requests", "requests.get": "requests.api.get"}
    import_map: dict[str, str] = field(default_factory=dict)

    # Dependency info
    dependencies: list[str] = field(default_factory=list)  # Transitive deps

    # Extensibility
    attrs: dict[str, Any] = field(default_factory=dict)

    def get_full_name(self) -> str:
        """Get full package identifier (name@version)"""
        return f"{self.name}@{self.version}"

    def get_moniker(self) -> str:
        """
        Get SCIP-style moniker.

        Returns:
            Moniker string (e.g., "pypi:requests@2.31.0")
        """
        manager_prefix = {
            "pip": "pypi",
            "npm": "npm",
            "go": "go",
            "maven": "maven",
        }.get(self.manager, self.manager)

        return f"{manager_prefix}:{self.name}@{self.version}"


@dataclass
class PackageIndex:
    """
    Index of external packages.

    Provides fast lookup for:
    - Package by name
    - Packages by manager (all pip packages, all npm packages, etc.)
    - Import resolution (import name → package)
    """

    # Primary indexes
    by_name: dict[str, PackageMetadata] = field(default_factory=dict)  # name → package
    by_manager: dict[str, list[str]] = field(default_factory=dict)  # manager → [package_name]
    by_import: dict[str, str] = field(default_factory=dict)  # import_name → package_name

    # Stats
    total_packages: int = 0

    def add(self, package: PackageMetadata) -> None:
        """Add package to index"""
        # Store by name
        self.by_name[package.name] = package

        # Index by manager
        self.by_manager.setdefault(package.manager, []).append(package.name)

        # Index imports
        for import_name in package.import_map.keys():
            self.by_import[import_name] = package.name

        self.total_packages += 1

    def get(self, package_name: str) -> PackageMetadata | None:
        """Get package by name"""
        return self.by_name.get(package_name)

    def get_by_manager(self, manager: str) -> list[PackageMetadata]:
        """Get all packages for a manager (e.g., all pip packages)"""
        package_names = self.by_manager.get(manager, [])
        return [self.by_name[name] for name in package_names if name in self.by_name]

    def resolve_import(self, import_name: str) -> PackageMetadata | None:
        """
        Resolve import to package.

        Example:
            resolve_import("requests.get") → requests package

        Args:
            import_name: Import statement (e.g., "requests", "requests.get")

        Returns:
            PackageMetadata if found, else None
        """
        # Direct lookup
        if import_name in self.by_import:
            package_name = self.by_import[import_name]
            return self.by_name.get(package_name)

        # Try base module (e.g., "requests.get" → "requests")
        base_module = import_name.split(".")[0]
        if base_module in self.by_import:
            package_name = self.by_import[base_module]
            return self.by_name.get(package_name)

        # Try direct name match
        if import_name in self.by_name:
            return self.by_name[import_name]

        return None

    def get_stats(self) -> dict[str, Any]:
        """Get package statistics"""
        return {
            "total_packages": self.total_packages,
            "by_manager": {mgr: len(pkgs) for mgr, pkgs in self.by_manager.items()},
            "total_imports": len(self.by_import),
        }

    def clear(self) -> None:
        """Clear all indexes"""
        self.by_name.clear()
        self.by_manager.clear()
        self.by_import.clear()
        self.total_packages = 0


def create_package(
    name: str,
    version: str,
    manager: str,
    import_names: list[str] | None = None,
) -> PackageMetadata:
    """
    Helper: Create a package metadata entry.

    Args:
        name: Package name
        version: Version string
        manager: Package manager
        import_names: List of import names (e.g., ["requests", "requests.get"])

    Returns:
        PackageMetadata
    """
    import_map = {}
    if import_names:
        for import_name in import_names:
            import_map[import_name] = name  # Map import → package

    return PackageMetadata(
        name=name,
        version=version,
        manager=manager,
        import_map=import_map,
    )
