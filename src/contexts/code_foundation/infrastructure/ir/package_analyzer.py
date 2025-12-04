"""
Package Analyzer

Analyzes external dependencies and populates PackageIndex.
"""

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.models.package import (
    PackageIndex,
    PackageMetadata,
    create_package,
)

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)


class PackageAnalyzer:
    """
    Analyzes external package dependencies.

    Supports:
    - Python: pip (requirements.txt, pyproject.toml)
    - TypeScript: npm (package.json)
    - Go: go.mod
    - Java: pom.xml, build.gradle
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = get_logger(__name__)

    def analyze(self, ir_docs: dict[str, "IRDocument"]) -> PackageIndex:
        """
        Analyze project dependencies.

        Args:
            ir_docs: Mapping of file_path → IRDocument

        Returns:
            PackageIndex with all discovered packages
        """
        package_index = PackageIndex()

        self.logger.info("Analyzing package dependencies...")

        # Detect project type and analyze
        if (self.project_root / "requirements.txt").exists():
            packages = self._analyze_requirements_txt()
            for pkg in packages:
                package_index.add(pkg)

        if (self.project_root / "pyproject.toml").exists():
            packages = self._analyze_pyproject_toml()
            for pkg in packages:
                package_index.add(pkg)

        if (self.project_root / "package.json").exists():
            packages = self._analyze_package_json()
            for pkg in packages:
                package_index.add(pkg)

        if (self.project_root / "go.mod").exists():
            packages = self._analyze_go_mod()
            for pkg in packages:
                package_index.add(pkg)

        # Add import mapping from actual IR imports
        self._add_import_mapping_from_ir(package_index, ir_docs)

        stats = package_index.get_stats()
        self.logger.info(f"Found {stats['total_packages']} packages, {stats['total_imports']} import mappings")

        return package_index

    def _analyze_requirements_txt(self) -> list[PackageMetadata]:
        """Parse requirements.txt"""
        packages = []
        requirements_file = self.project_root / "requirements.txt"

        try:
            with open(requirements_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Parse "package==version" or "package>=version"
                    if "==" in line:
                        name, version = line.split("==", 1)
                    elif ">=" in line:
                        name, version = line.split(">=", 1)
                    elif "<=" in line:
                        name, version = line.split("<=", 1)
                    else:
                        name, version = line, "unknown"

                    name = name.strip()
                    version = version.strip()

                    # Create package
                    pkg = create_package(
                        name=name,
                        version=version,
                        manager="pip",
                        import_names=[name],  # Basic mapping
                    )
                    pkg.registry = f"https://pypi.org/project/{name}/"
                    packages.append(pkg)

        except Exception as e:
            self.logger.warning(f"Failed to parse requirements.txt: {e}")

        return packages

    def _analyze_pyproject_toml(self) -> list[PackageMetadata]:
        """Parse pyproject.toml"""
        packages = []
        pyproject_file = self.project_root / "pyproject.toml"

        try:
            # Try importing toml (if available)
            try:
                import tomli as toml
            except ImportError:
                try:
                    import toml  # type: ignore
                except ImportError:
                    self.logger.debug("toml library not available, skipping pyproject.toml")
                    return packages

            with open(pyproject_file, "rb") as f:
                data = toml.load(f)

            # Parse dependencies
            deps = data.get("project", {}).get("dependencies", [])
            for dep in deps:
                # Parse "package>=version"
                if ">=" in dep:
                    name, version = dep.split(">=", 1)
                elif "==" in dep:
                    name, version = dep.split("==", 1)
                else:
                    name, version = dep, "unknown"

                name = name.strip()
                version = version.strip()

                pkg = create_package(
                    name=name,
                    version=version,
                    manager="pip",
                    import_names=[name],
                )
                pkg.registry = f"https://pypi.org/project/{name}/"
                packages.append(pkg)

        except Exception as e:
            self.logger.warning(f"Failed to parse pyproject.toml: {e}")

        return packages

    def _analyze_package_json(self) -> list[PackageMetadata]:
        """Parse package.json (npm)"""
        packages = []
        package_json = self.project_root / "package.json"

        try:
            with open(package_json) as f:
                data = json.load(f)

            # Parse dependencies
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

            for name, version in deps.items():
                pkg = create_package(
                    name=name,
                    version=version,
                    manager="npm",
                    import_names=[name],
                )
                pkg.registry = f"https://www.npmjs.com/package/{name}"
                packages.append(pkg)

        except Exception as e:
            self.logger.warning(f"Failed to parse package.json: {e}")

        return packages

    def _analyze_go_mod(self) -> list[PackageMetadata]:
        """Parse go.mod"""
        packages = []
        go_mod = self.project_root / "go.mod"

        try:
            with open(go_mod) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("require "):
                        # Parse "require github.com/foo/bar v1.2.3"
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[1]
                            version = parts[2]

                            pkg = create_package(
                                name=name,
                                version=version,
                                manager="go",
                                import_names=[name],
                            )
                            packages.append(pkg)

        except Exception as e:
            self.logger.warning(f"Failed to parse go.mod: {e}")

        return packages

    def _add_import_mapping_from_ir(
        self,
        package_index: PackageIndex,
        ir_docs: dict[str, "IRDocument"],
    ):
        """
        Add import mappings from actual IR imports.

        For example, if we see "from requests.api import get",
        we map "requests.api" → "requests" package.
        """
        for ir_doc in ir_docs.values():
            for node in ir_doc.nodes:
                if node.kind.value == "Import":
                    # Extract import name from node
                    import_name = node.name or node.fqn
                    if not import_name:
                        continue

                    # Try to find matching package
                    # e.g., "requests.api.get" → try "requests"
                    parts = import_name.split(".")
                    base_module = parts[0]

                    # If base module matches a package, add mapping
                    if package_index.get(base_module):
                        pkg = package_index.get(base_module)
                        if pkg and import_name not in pkg.import_map:
                            pkg.import_map[import_name] = pkg.name
                            package_index.by_import[import_name] = pkg.name
