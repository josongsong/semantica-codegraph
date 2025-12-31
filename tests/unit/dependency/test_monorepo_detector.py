"""
Tests for Monorepo Workspace Boundary Detection

SOTA-grade testing for multi-workspace-type monorepo detection.
"""

import json
import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.dependency.monorepo_detector import (
    MonorepoDetector,
    PackageVisibility,
    WorkspaceBoundary,
    WorkspacePackage,
    WorkspaceType,
    validate_workspace_imports,
)


class TestMonorepoDetector:
    """Tests for MonorepoDetector class."""

    def setup_method(self):
        """Setup test fixtures."""
        self.detector = MonorepoDetector()

    # ========================================
    # npm Workspace Tests
    # ========================================

    def test_npm_workspace_detection(self, tmp_path: Path):
        """Test npm workspace detection with packages/* pattern."""
        # Create npm workspace structure
        root_pkg = {"name": "monorepo", "workspaces": ["packages/*"]}
        (tmp_path / "package.json").write_text(json.dumps(root_pkg))

        # Create packages
        (tmp_path / "packages" / "core").mkdir(parents=True)
        core_pkg = {"name": "@myorg/core", "dependencies": {}}
        (tmp_path / "packages" / "core" / "package.json").write_text(json.dumps(core_pkg))

        (tmp_path / "packages" / "utils").mkdir(parents=True)
        utils_pkg = {"name": "@myorg/utils", "dependencies": {"@myorg/core": "^1.0.0"}}
        (tmp_path / "packages" / "utils" / "package.json").write_text(json.dumps(utils_pkg))

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.NPM
        assert len(boundary.packages) == 2
        assert "@myorg/core" in boundary.packages
        assert "@myorg/utils" in boundary.packages
        assert "@myorg/core" in boundary.packages["@myorg/utils"].dependencies

    def test_npm_workspace_yarn_format(self, tmp_path: Path):
        """Test yarn workspace format: { packages: [...] }."""
        root_pkg = {"name": "monorepo", "workspaces": {"packages": ["packages/*", "apps/*"]}}
        (tmp_path / "package.json").write_text(json.dumps(root_pkg))

        (tmp_path / "packages" / "lib").mkdir(parents=True)
        (tmp_path / "packages" / "lib" / "package.json").write_text(json.dumps({"name": "lib"}))

        (tmp_path / "apps" / "web").mkdir(parents=True)
        (tmp_path / "apps" / "web" / "package.json").write_text(json.dumps({"name": "web"}))

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert len(boundary.packages) == 2

    def test_npm_workspace_visibility(self, tmp_path: Path):
        """Test package visibility detection."""
        root_pkg = {"name": "monorepo", "workspaces": ["packages/*"]}
        (tmp_path / "package.json").write_text(json.dumps(root_pkg))

        # Public package
        (tmp_path / "packages" / "public-pkg").mkdir(parents=True)
        public_pkg = {"name": "public-pkg", "private": False}
        (tmp_path / "packages" / "public-pkg" / "package.json").write_text(json.dumps(public_pkg))

        # Private package
        (tmp_path / "packages" / "private-pkg").mkdir(parents=True)
        private_pkg = {"name": "private-pkg", "private": True}
        (tmp_path / "packages" / "private-pkg" / "package.json").write_text(json.dumps(private_pkg))

        boundary = self.detector.detect(tmp_path)

        assert boundary.packages["public-pkg"].visibility == PackageVisibility.PUBLIC
        assert boundary.packages["private-pkg"].visibility == PackageVisibility.PRIVATE

    # ========================================
    # Cargo Workspace Tests
    # ========================================

    def test_cargo_workspace_detection(self, tmp_path: Path):
        """Test Cargo workspace detection."""
        cargo_toml = """
[workspace]
members = [
    "crates/core",
    "crates/cli",
]
"""
        (tmp_path / "Cargo.toml").write_text(cargo_toml)

        (tmp_path / "crates" / "core").mkdir(parents=True)
        core_toml = """
[package]
name = "myapp-core"
version = "0.1.0"

[dependencies]
serde = "1.0"
"""
        (tmp_path / "crates" / "core" / "Cargo.toml").write_text(core_toml)

        (tmp_path / "crates" / "cli").mkdir(parents=True)
        cli_toml = """
[package]
name = "myapp-cli"
version = "0.1.0"

[dependencies]
myapp-core = { path = "../core" }
"""
        (tmp_path / "crates" / "cli" / "Cargo.toml").write_text(cli_toml)

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.CARGO
        assert len(boundary.packages) == 2
        assert "myapp-core" in boundary.packages
        assert "myapp-cli" in boundary.packages

    # ========================================
    # Go Workspace Tests
    # ========================================

    def test_go_work_detection(self, tmp_path: Path):
        """Test go.work file detection."""
        go_work = """
go 1.21

use (
    ./cmd/api
    ./pkg/shared
)
"""
        (tmp_path / "go.work").write_text(go_work)

        (tmp_path / "cmd" / "api").mkdir(parents=True)
        (tmp_path / "cmd" / "api" / "go.mod").write_text("module github.com/myorg/api\n\ngo 1.21")

        (tmp_path / "pkg" / "shared").mkdir(parents=True)
        (tmp_path / "pkg" / "shared" / "go.mod").write_text("module github.com/myorg/shared\n\ngo 1.21")

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.GO
        assert len(boundary.packages) == 2

    def test_go_implicit_workspace(self, tmp_path: Path):
        """Test implicit Go workspace (multiple go.mod files)."""
        (tmp_path / "service-a").mkdir()
        (tmp_path / "service-a" / "go.mod").write_text("module github.com/myorg/service-a\n")

        (tmp_path / "service-b").mkdir()
        (tmp_path / "service-b" / "go.mod").write_text("module github.com/myorg/service-b\n")

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.GO
        assert len(boundary.packages) == 2

    # ========================================
    # Turborepo / Lerna / Nx Tests
    # ========================================

    def test_turborepo_detection(self, tmp_path: Path):
        """Test Turborepo workspace detection."""
        (tmp_path / "turbo.json").write_text("{}")
        root_pkg = {"name": "turborepo", "workspaces": ["packages/*"]}
        (tmp_path / "package.json").write_text(json.dumps(root_pkg))

        (tmp_path / "packages" / "ui").mkdir(parents=True)
        (tmp_path / "packages" / "ui" / "package.json").write_text(json.dumps({"name": "ui"}))

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.TURBOREPO

    def test_lerna_detection(self, tmp_path: Path):
        """Test Lerna workspace detection."""
        lerna_json = {"packages": ["packages/*"]}
        (tmp_path / "lerna.json").write_text(json.dumps(lerna_json))

        (tmp_path / "packages" / "a").mkdir(parents=True)
        (tmp_path / "packages" / "a" / "package.json").write_text(json.dumps({"name": "a"}))

        boundary = self.detector.detect(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.LERNA

    # ========================================
    # Import Validation Tests
    # ========================================

    def test_import_validation_allowed(self, tmp_path: Path):
        """Test import validation - allowed case."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
        )
        boundary.packages["@myorg/shared"] = WorkspacePackage(
            name="@myorg/shared",
            path=tmp_path / "packages" / "shared",
            visibility=PackageVisibility.PUBLIC,
        )
        boundary.packages["@myorg/app"] = WorkspacePackage(
            name="@myorg/app",
            path=tmp_path / "packages" / "app",
            dependencies={"@myorg/shared"},
        )

        # Create test file
        (tmp_path / "packages" / "app" / "src").mkdir(parents=True)
        test_file = tmp_path / "packages" / "app" / "src" / "index.ts"
        test_file.write_text("// test")

        allowed, reason = boundary.is_import_allowed(test_file, "@myorg/shared")

        assert allowed is True
        assert reason is None

    def test_import_validation_no_dependency(self, tmp_path: Path):
        """Test import validation - missing dependency."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
            strict_boundaries=True,
        )
        boundary.packages["@myorg/backend"] = WorkspacePackage(
            name="@myorg/backend",
            path=tmp_path / "packages" / "backend",
            visibility=PackageVisibility.PRIVATE,
        )
        boundary.packages["@myorg/frontend"] = WorkspacePackage(
            name="@myorg/frontend",
            path=tmp_path / "packages" / "frontend",
            dependencies=set(),  # No dependencies!
        )

        # Create test file
        (tmp_path / "packages" / "frontend" / "src").mkdir(parents=True)
        test_file = tmp_path / "packages" / "frontend" / "src" / "app.ts"
        test_file.write_text("// test")

        allowed, reason = boundary.is_import_allowed(test_file, "@myorg/backend")

        assert allowed is False
        assert "not accessible" in reason

    def test_validate_workspace_imports_batch(self, tmp_path: Path):
        """Test batch import validation."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
            strict_boundaries=True,
        )
        boundary.packages["pkg-a"] = WorkspacePackage(
            name="pkg-a",
            path=tmp_path / "packages" / "a",
            visibility=PackageVisibility.PUBLIC,
        )
        boundary.packages["pkg-b"] = WorkspacePackage(
            name="pkg-b",
            path=tmp_path / "packages" / "b",
            dependencies={"pkg-a"},
        )
        boundary.packages["pkg-c"] = WorkspacePackage(
            name="pkg-c",
            path=tmp_path / "packages" / "c",
            dependencies=set(),
        )

        # Create files
        for pkg in ["a", "b", "c"]:
            (tmp_path / "packages" / pkg / "src").mkdir(parents=True)
            (tmp_path / "packages" / pkg / "src" / "index.ts").write_text("// test")

        imports = [
            (tmp_path / "packages" / "b" / "src" / "index.ts", "pkg-a"),  # Allowed
            (tmp_path / "packages" / "c" / "src" / "index.ts", "pkg-a"),  # Violation
        ]

        violations = validate_workspace_imports(boundary, imports)

        assert len(violations) == 1
        assert violations[0][1] == "pkg-a"


class TestWorkspacePackage:
    """Tests for WorkspacePackage class."""

    def test_public_visibility(self):
        """Test public package can be imported by anyone."""
        pkg = WorkspacePackage(
            name="public-pkg",
            path=Path("."),
            visibility=PackageVisibility.PUBLIC,
        )

        assert pkg.can_be_imported_by("any-package") is True

    def test_private_visibility(self):
        """Test private package cannot be imported."""
        pkg = WorkspacePackage(
            name="private-pkg",
            path=Path("."),
            visibility=PackageVisibility.PRIVATE,
        )

        assert pkg.can_be_imported_by("any-package") is False

    def test_restricted_visibility_allowed(self):
        """Test restricted package allows specific dependents."""
        pkg = WorkspacePackage(
            name="restricted-pkg",
            path=Path("."),
            visibility=PackageVisibility.RESTRICTED,
            allowed_dependents={"allowed-pkg", "another-allowed"},
        )

        assert pkg.can_be_imported_by("allowed-pkg") is True
        assert pkg.can_be_imported_by("another-allowed") is True
        assert pkg.can_be_imported_by("not-allowed") is False


class TestWorkspaceBoundary:
    """Tests for WorkspaceBoundary class."""

    def test_get_package_for_path(self, tmp_path: Path):
        """Test finding package for a file path."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
        )

        pkg_path = tmp_path / "packages" / "myapp"
        pkg_path.mkdir(parents=True)

        boundary.packages["myapp"] = WorkspacePackage(
            name="myapp",
            path=pkg_path,
        )

        # Create nested file
        (pkg_path / "src" / "lib").mkdir(parents=True)
        nested_file = pkg_path / "src" / "lib" / "utils.ts"
        nested_file.write_text("// test")

        found_pkg = boundary.get_package_for_path(nested_file)

        assert found_pkg is not None
        assert found_pkg.name == "myapp"

    def test_get_package_for_path_not_found(self, tmp_path: Path):
        """Test returns None for file outside packages."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
        )

        outside_file = tmp_path / "scripts" / "build.js"
        outside_file.parent.mkdir(parents=True)
        outside_file.write_text("// test")

        found_pkg = boundary.get_package_for_path(outside_file)

        assert found_pkg is None

    def test_non_strict_boundaries(self, tmp_path: Path):
        """Test non-strict mode allows all imports."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
            strict_boundaries=False,  # Non-strict
        )
        boundary.packages["pkg-a"] = WorkspacePackage(
            name="pkg-a",
            path=tmp_path / "packages" / "a",
            visibility=PackageVisibility.PRIVATE,
        )

        # Even private packages are accessible in non-strict mode
        allowed, _ = boundary.is_import_allowed(tmp_path / "packages" / "b" / "index.ts", "pkg-a")

        assert allowed is True
