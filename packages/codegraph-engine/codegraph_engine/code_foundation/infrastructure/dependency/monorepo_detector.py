"""
Monorepo Workspace Boundary Detection

SOTA-grade monorepo detection supporting:
- npm/yarn/pnpm workspaces (package.json)
- Cargo workspaces (Cargo.toml)
- Go workspaces (go.work, go.mod)
- Python monorepos (pyproject.toml, setup.py)
- Lerna/Nx/Turborepo configurations

Features:
- Workspace boundary detection
- Package dependency validation
- Cross-package import violation detection
- Workspace member enumeration
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class WorkspaceType(str, Enum):
    """Type of monorepo workspace."""

    NPM = "npm"  # npm/yarn/pnpm workspaces
    CARGO = "cargo"  # Rust Cargo workspaces
    GO = "go"  # Go workspaces (go.work)
    PYTHON = "python"  # Python monorepo
    LERNA = "lerna"  # Lerna managed
    NX = "nx"  # Nx managed
    TURBOREPO = "turborepo"  # Turborepo managed
    UNKNOWN = "unknown"


class PackageVisibility(str, Enum):
    """Visibility/accessibility of a package."""

    PUBLIC = "public"  # Can be imported by anyone
    PRIVATE = "private"  # Internal package, not publishable
    RESTRICTED = "restricted"  # Can only be imported by specific packages


@dataclass
class WorkspacePackage:
    """Represents a package within a monorepo workspace."""

    name: str
    path: Path
    visibility: PackageVisibility = PackageVisibility.PRIVATE
    dependencies: set[str] = field(default_factory=set)
    dev_dependencies: set[str] = field(default_factory=set)
    allowed_dependents: set[str] = field(default_factory=set)  # Who can depend on this

    def can_be_imported_by(self, importer: str) -> bool:
        """Check if this package can be imported by another package."""
        if self.visibility == PackageVisibility.PUBLIC:
            return True
        if self.visibility == PackageVisibility.PRIVATE:
            return False
        # RESTRICTED: check allowed_dependents
        return importer in self.allowed_dependents or not self.allowed_dependents


@dataclass
class WorkspaceBoundary:
    """Represents a workspace boundary in a monorepo."""

    root: Path
    workspace_type: WorkspaceType
    packages: dict[str, WorkspacePackage] = field(default_factory=dict)

    # Dependency rules
    allow_circular: bool = False
    strict_boundaries: bool = True  # Enforce package boundaries

    def get_package_for_path(self, file_path: Path) -> WorkspacePackage | None:
        """Find which package a file belongs to."""
        try:
            abs_path = file_path.resolve()
            for pkg in self.packages.values():
                pkg_path = pkg.path.resolve()
                try:
                    abs_path.relative_to(pkg_path)
                    return pkg
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def is_import_allowed(self, from_path: Path, to_package: str) -> tuple[bool, str | None]:
        """
        Check if an import from a file to a package is allowed.

        Returns:
            (is_allowed, violation_reason)
        """
        if not self.strict_boundaries:
            return True, None

        from_pkg = self.get_package_for_path(from_path)
        if from_pkg is None:
            return True, None  # Not in a package, allow

        if from_pkg.name == to_package:
            return True, None  # Same package, always allowed

        to_pkg = self.packages.get(to_package)
        if to_pkg is None:
            return True, None  # External package, allow

        # Check if target package allows this import
        if not to_pkg.can_be_imported_by(from_pkg.name):
            return False, f"Package '{to_package}' is not accessible from '{from_pkg.name}'"

        # Check if source package declares dependency
        if to_package not in from_pkg.dependencies and to_package not in from_pkg.dev_dependencies:
            return False, f"Package '{from_pkg.name}' does not declare dependency on '{to_package}'"

        return True, None


class MonorepoDetector:
    """
    SOTA Monorepo Workspace Detector

    Detects and parses various monorepo configurations to establish
    workspace boundaries for dependency validation.

    Usage:
        detector = MonorepoDetector()
        boundary = detector.detect(project_root)

        if boundary:
            allowed, reason = boundary.is_import_allowed(
                from_path=Path("packages/frontend/src/app.ts"),
                to_package="@myorg/backend"
            )
            if not allowed:
                print(f"Boundary violation: {reason}")
    """

    def detect(self, root: Path) -> WorkspaceBoundary | None:
        """
        Detect monorepo workspace configuration.

        Args:
            root: Project root directory

        Returns:
            WorkspaceBoundary if monorepo detected, None otherwise
        """
        root = root.resolve()

        # Try each detector in order of specificity
        detectors = [
            self._detect_nx,
            self._detect_turborepo,
            self._detect_lerna,
            self._detect_npm_workspace,
            self._detect_cargo_workspace,
            self._detect_go_workspace,
            self._detect_python_workspace,
        ]

        for detector in detectors:
            try:
                boundary = detector(root)
                if boundary:
                    logger.info(
                        f"Detected {boundary.workspace_type.value} workspace at {root} "
                        f"with {len(boundary.packages)} packages"
                    )
                    return boundary
            except Exception as e:
                logger.debug(f"Detector {detector.__name__} failed: {e}")

        return None

    def _detect_npm_workspace(self, root: Path) -> WorkspaceBoundary | None:
        """Detect npm/yarn/pnpm workspaces."""
        package_json = root / "package.json"
        if not package_json.exists():
            return None

        try:
            with open(package_json) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        # Check for workspaces field
        workspaces = data.get("workspaces")
        if not workspaces:
            return None

        # Normalize workspaces format
        workspace_patterns: list[str] = []
        if isinstance(workspaces, list):
            workspace_patterns = workspaces
        elif isinstance(workspaces, dict):
            # yarn workspaces format: { packages: [...] }
            workspace_patterns = workspaces.get("packages", [])

        if not workspace_patterns:
            return None

        boundary = WorkspaceBoundary(
            root=root,
            workspace_type=WorkspaceType.NPM,
        )

        # Find all packages matching patterns
        for pattern in workspace_patterns:
            self._find_npm_packages(root, pattern, boundary)

        return boundary if boundary.packages else None

    def _find_npm_packages(self, root: Path, pattern: str, boundary: WorkspaceBoundary) -> None:
        """Find npm packages matching a glob pattern."""

        # Handle glob patterns like "packages/*" or "apps/**"
        if "**" in pattern:
            search_pattern = pattern.replace("**", "*")
            recursive = True
        else:
            search_pattern = pattern
            recursive = False

        base_dir = root
        parts = search_pattern.split("/")

        # Find the base directory (non-glob part)
        for part in parts[:-1]:
            if "*" in part:
                break
            base_dir = base_dir / part

        if not base_dir.exists():
            return

        # Search for package.json files
        if recursive:
            package_jsons = base_dir.rglob("package.json")
        else:
            glob_part = parts[-1] if parts else "*"
            package_jsons = [p / "package.json" for p in base_dir.glob(glob_part) if (p / "package.json").exists()]

        for pkg_json in package_jsons:
            if pkg_json == root / "package.json":
                continue  # Skip root package.json

            try:
                with open(pkg_json) as f:
                    pkg_data = json.load(f)

                name = pkg_data.get("name", pkg_json.parent.name)
                deps = set(pkg_data.get("dependencies", {}).keys())
                dev_deps = set(pkg_data.get("devDependencies", {}).keys())

                # Determine visibility
                visibility = PackageVisibility.PRIVATE
                if pkg_data.get("private") is False:
                    visibility = PackageVisibility.PUBLIC

                boundary.packages[name] = WorkspacePackage(
                    name=name,
                    path=pkg_json.parent,
                    visibility=visibility,
                    dependencies=deps,
                    dev_dependencies=dev_deps,
                )
            except (OSError, json.JSONDecodeError) as e:
                logger.debug(f"Failed to parse {pkg_json}: {e}")

    def _detect_cargo_workspace(self, root: Path) -> WorkspaceBoundary | None:
        """Detect Rust Cargo workspaces."""
        cargo_toml = root / "Cargo.toml"
        if not cargo_toml.exists():
            return None

        try:
            # Simple TOML parsing (avoid toml dependency)
            content = cargo_toml.read_text()
            if "[workspace]" not in content:
                return None

            boundary = WorkspaceBoundary(
                root=root,
                workspace_type=WorkspaceType.CARGO,
            )

            # Parse workspace members
            members = self._parse_toml_array(content, "members")
            exclude = self._parse_toml_array(content, "exclude")

            for pattern in members:
                self._find_cargo_packages(root, pattern, boundary, exclude)

            return boundary if boundary.packages else None

        except Exception as e:
            logger.debug(f"Failed to parse Cargo.toml: {e}")
            return None

    def _parse_toml_array(self, content: str, key: str) -> list[str]:
        """Simple TOML array parser."""
        # Match: members = ["path1", "path2"]
        pattern = rf"{key}\s*=\s*\[(.*?)\]"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return []

        array_content = match.group(1)
        # Extract quoted strings
        items = re.findall(r'"([^"]*)"', array_content)
        return items

    def _find_cargo_packages(
        self,
        root: Path,
        pattern: str,
        boundary: WorkspaceBoundary,
        exclude: list[str],
    ) -> None:
        """Find Cargo packages matching a pattern."""
        # Handle glob patterns
        if "*" in pattern:
            base = root
            for part in pattern.split("/"):
                if "*" in part:
                    break
                base = base / part

            if base.exists():
                for cargo_toml in base.glob("*/Cargo.toml"):
                    rel_path = str(cargo_toml.parent.relative_to(root))
                    if rel_path not in exclude:
                        self._add_cargo_package(cargo_toml, boundary)
        else:
            cargo_toml = root / pattern / "Cargo.toml"
            if cargo_toml.exists():
                self._add_cargo_package(cargo_toml, boundary)

    def _add_cargo_package(self, cargo_toml: Path, boundary: WorkspaceBoundary) -> None:
        """Add a Cargo package to the boundary."""
        try:
            content = cargo_toml.read_text()

            # Parse package name
            name_match = re.search(r'name\s*=\s*"([^"]*)"', content)
            name = name_match.group(1) if name_match else cargo_toml.parent.name

            # Parse dependencies (simplified)
            deps: set[str] = set()
            in_deps = False
            for line in content.split("\n"):
                if line.strip().startswith("[dependencies"):
                    in_deps = True
                    continue
                elif line.strip().startswith("["):
                    in_deps = False
                elif in_deps and "=" in line:
                    dep_name = line.split("=")[0].strip()
                    if dep_name:
                        deps.add(dep_name)

            boundary.packages[name] = WorkspacePackage(
                name=name,
                path=cargo_toml.parent,
                dependencies=deps,
            )
        except Exception as e:
            logger.debug(f"Failed to parse {cargo_toml}: {e}")

    def _detect_go_workspace(self, root: Path) -> WorkspaceBoundary | None:
        """Detect Go workspaces (go.work or multiple go.mod)."""
        go_work = root / "go.work"

        if go_work.exists():
            return self._parse_go_work(root, go_work)

        # Check for multiple go.mod files (implicit workspace)
        go_mods = list(root.rglob("go.mod"))
        if len(go_mods) > 1:
            return self._create_implicit_go_workspace(root, go_mods)

        return None

    def _parse_go_work(self, root: Path, go_work: Path) -> WorkspaceBoundary | None:
        """Parse go.work file."""
        try:
            content = go_work.read_text()
            boundary = WorkspaceBoundary(
                root=root,
                workspace_type=WorkspaceType.GO,
            )

            # Parse use directives
            use_pattern = r"use\s+\(\s*(.*?)\s*\)|use\s+(\S+)"
            for match in re.finditer(use_pattern, content, re.DOTALL):
                if match.group(1):
                    # Multi-line use block
                    paths = match.group(1).strip().split("\n")
                else:
                    # Single use
                    paths = [match.group(2)]

                for path in paths:
                    path = path.strip().strip("./")
                    if path:
                        mod_path = root / path
                        if mod_path.exists():
                            self._add_go_module(mod_path, boundary)

            return boundary if boundary.packages else None

        except Exception as e:
            logger.debug(f"Failed to parse go.work: {e}")
            return None

    def _create_implicit_go_workspace(self, root: Path, go_mods: list[Path]) -> WorkspaceBoundary:
        """Create workspace from multiple go.mod files."""
        boundary = WorkspaceBoundary(
            root=root,
            workspace_type=WorkspaceType.GO,
        )

        for go_mod in go_mods:
            self._add_go_module(go_mod.parent, boundary)

        return boundary

    def _add_go_module(self, mod_path: Path, boundary: WorkspaceBoundary) -> None:
        """Add a Go module to the boundary."""
        go_mod = mod_path / "go.mod"
        if not go_mod.exists():
            return

        try:
            content = go_mod.read_text()

            # Parse module name
            module_match = re.search(r"module\s+(\S+)", content)
            name = module_match.group(1) if module_match else mod_path.name

            # Parse require (dependencies)
            deps: set[str] = set()
            require_pattern = r"require\s+\(\s*(.*?)\s*\)|require\s+(\S+)\s+v"
            for match in re.finditer(require_pattern, content, re.DOTALL):
                if match.group(1):
                    for line in match.group(1).split("\n"):
                        parts = line.strip().split()
                        if parts:
                            deps.add(parts[0])
                elif match.group(2):
                    deps.add(match.group(2))

            boundary.packages[name] = WorkspacePackage(
                name=name,
                path=mod_path,
                dependencies=deps,
            )
        except Exception as e:
            logger.debug(f"Failed to parse {go_mod}: {e}")

    def _detect_python_workspace(self, root: Path) -> WorkspaceBoundary | None:
        """Detect Python monorepo (pyproject.toml with tool.poetry.packages or similar)."""
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        try:
            content = pyproject.read_text()

            # Check for poetry workspaces or packages
            if "[tool.poetry]" not in content:
                return None

            # Look for packages configuration
            packages_match = re.search(r"packages\s*=\s*\[(.*?)\]", content, re.DOTALL)
            if not packages_match:
                return None

            boundary = WorkspaceBoundary(
                root=root,
                workspace_type=WorkspaceType.PYTHON,
            )

            # Parse package paths
            packages_content = packages_match.group(1)
            for match in re.finditer(r'include\s*=\s*"([^"]*)"', packages_content):
                pkg_path = root / match.group(1)
                if pkg_path.exists():
                    name = pkg_path.name
                    boundary.packages[name] = WorkspacePackage(
                        name=name,
                        path=pkg_path,
                    )

            return boundary if boundary.packages else None

        except Exception as e:
            logger.debug(f"Failed to parse pyproject.toml: {e}")
            return None

    def _detect_nx(self, root: Path) -> WorkspaceBoundary | None:
        """Detect Nx workspace."""
        nx_json = root / "nx.json"
        if not nx_json.exists():
            return None

        try:
            with open(nx_json) as f:
                json.load(f)

            boundary = WorkspaceBoundary(
                root=root,
                workspace_type=WorkspaceType.NX,
            )

            # Nx stores projects in workspace.json or project.json files
            workspace_json = root / "workspace.json"
            if workspace_json.exists():
                with open(workspace_json) as f:
                    ws_data = json.load(f)
                    projects = ws_data.get("projects", {})

                    for name, config in projects.items():
                        if isinstance(config, str):
                            pkg_path = root / config
                        else:
                            pkg_path = root / config.get("root", name)

                        boundary.packages[name] = WorkspacePackage(
                            name=name,
                            path=pkg_path,
                        )
            else:
                # Look for project.json files
                for project_json in root.rglob("project.json"):
                    if project_json.parent == root:
                        continue
                    with open(project_json) as f:
                        proj_data = json.load(f)
                        name = proj_data.get("name", project_json.parent.name)
                        boundary.packages[name] = WorkspacePackage(
                            name=name,
                            path=project_json.parent,
                        )

            return boundary if boundary.packages else None

        except Exception as e:
            logger.debug(f"Failed to parse nx.json: {e}")
            return None

    def _detect_turborepo(self, root: Path) -> WorkspaceBoundary | None:
        """Detect Turborepo workspace."""
        turbo_json = root / "turbo.json"
        if not turbo_json.exists():
            return None

        # Turborepo uses npm/yarn/pnpm workspaces, so delegate
        boundary = self._detect_npm_workspace(root)
        if boundary:
            boundary.workspace_type = WorkspaceType.TURBOREPO

        return boundary

    def _detect_lerna(self, root: Path) -> WorkspaceBoundary | None:
        """Detect Lerna workspace."""
        lerna_json = root / "lerna.json"
        if not lerna_json.exists():
            return None

        try:
            with open(lerna_json) as f:
                data = json.load(f)

            boundary = WorkspaceBoundary(
                root=root,
                workspace_type=WorkspaceType.LERNA,
            )

            # Get packages patterns
            patterns = data.get("packages", ["packages/*"])

            for pattern in patterns:
                self._find_npm_packages(root, pattern, boundary)

            return boundary if boundary.packages else None

        except Exception as e:
            logger.debug(f"Failed to parse lerna.json: {e}")
            return None


def validate_workspace_imports(
    boundary: WorkspaceBoundary,
    imports: list[tuple[Path, str]],
) -> list[tuple[Path, str, str]]:
    """
    Validate a list of imports against workspace boundaries.

    Args:
        boundary: Workspace boundary configuration
        imports: List of (from_file, to_package) tuples

    Returns:
        List of violations: (from_file, to_package, reason)
    """
    violations = []

    for from_path, to_package in imports:
        allowed, reason = boundary.is_import_allowed(from_path, to_package)
        if not allowed:
            violations.append((from_path, to_package, reason or "Unknown violation"))

    return violations
