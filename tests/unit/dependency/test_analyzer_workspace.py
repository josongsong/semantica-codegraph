"""
Tests for DependencyAnalyzer workspace boundary integration.

SOTA monorepo support - validates cross-package imports.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegraph_engine.code_foundation.infrastructure.dependency.analyzer import (
    DependencyAnalyzer,
)
from codegraph_engine.code_foundation.infrastructure.dependency.models import (
    DependencyEdge,
    DependencyEdgeKind,
    DependencyGraph,
    DependencyKind,
    DependencyNode,
)
from codegraph_engine.code_foundation.infrastructure.dependency.monorepo_detector import (
    PackageVisibility,
    WorkspaceBoundary,
    WorkspacePackage,
    WorkspaceType,
)


@pytest.fixture
def sample_graph() -> DependencyGraph:
    """Create a sample dependency graph."""
    graph = DependencyGraph(repo_id="test-repo", snapshot_id="HEAD")

    # Add nodes - simulating a monorepo structure
    nodes = [
        DependencyNode(
            module_path="@org/frontend",
            kind=DependencyKind.INTERNAL,
            file_path="/repo/packages/frontend/src/app.ts",
        ),
        DependencyNode(
            module_path="@org/backend",
            kind=DependencyKind.INTERNAL,
            file_path="/repo/packages/backend/src/index.ts",
        ),
        DependencyNode(
            module_path="@org/shared",
            kind=DependencyKind.INTERNAL,
            file_path="/repo/packages/shared/src/utils.ts",
        ),
    ]

    for node in nodes:
        graph.add_node(node)

    # Add edges
    edges = [
        DependencyEdge(
            source="@org/frontend",
            target="@org/shared",
            kind=DependencyEdgeKind.IMPORT_MODULE,
        ),
        DependencyEdge(
            source="@org/frontend",
            target="@org/backend",  # Undeclared dependency
            kind=DependencyEdgeKind.IMPORT_MODULE,
        ),
        DependencyEdge(
            source="@org/backend",
            target="@org/shared",
            kind=DependencyEdgeKind.IMPORT_MODULE,
        ),
    ]

    for edge in edges:
        graph.add_edge(edge)

    return graph


@pytest.fixture
def workspace_boundary(tmp_path: Path) -> WorkspaceBoundary:
    """Create a sample workspace boundary."""
    # Create directory structure
    frontend_path = tmp_path / "packages" / "frontend"
    backend_path = tmp_path / "packages" / "backend"
    shared_path = tmp_path / "packages" / "shared"

    for p in [frontend_path, backend_path, shared_path]:
        p.mkdir(parents=True, exist_ok=True)

    boundary = WorkspaceBoundary(
        root=tmp_path,
        workspace_type=WorkspaceType.NPM,
        strict_boundaries=True,
    )

    # frontend depends on shared only
    boundary.packages["@org/frontend"] = WorkspacePackage(
        name="@org/frontend",
        path=frontend_path,
        visibility=PackageVisibility.PRIVATE,
        dependencies={"@org/shared"},
    )

    # backend depends on shared
    boundary.packages["@org/backend"] = WorkspacePackage(
        name="@org/backend",
        path=backend_path,
        visibility=PackageVisibility.PRIVATE,
        dependencies={"@org/shared"},
    )

    # shared is public
    boundary.packages["@org/shared"] = WorkspacePackage(
        name="@org/shared",
        path=shared_path,
        visibility=PackageVisibility.PUBLIC,
        dependencies=set(),
    )

    return boundary


class TestDependencyAnalyzerWorkspace:
    """Test workspace boundary integration."""

    def test_set_workspace_boundary(self, sample_graph: DependencyGraph, workspace_boundary: WorkspaceBoundary):
        """Test setting workspace boundary."""
        analyzer = DependencyAnalyzer(sample_graph)

        assert analyzer.get_workspace_boundary() is None

        analyzer.set_workspace_boundary(workspace_boundary)

        assert analyzer.get_workspace_boundary() is not None
        assert analyzer.get_workspace_boundary().workspace_type == WorkspaceType.NPM

    def test_validate_workspace_imports_no_boundary(self, sample_graph: DependencyGraph):
        """Test validation without boundary returns empty."""
        analyzer = DependencyAnalyzer(sample_graph)

        violations = analyzer.validate_workspace_imports()

        assert violations == []

    def test_validate_workspace_imports_detects_violations(
        self, sample_graph: DependencyGraph, workspace_boundary: WorkspaceBoundary, tmp_path: Path
    ):
        """Test validation detects undeclared dependencies."""
        # Update file paths to match workspace structure
        sample_graph.nodes["@org/frontend"].file_path = str(tmp_path / "packages" / "frontend" / "src" / "app.ts")
        sample_graph.nodes["@org/backend"].file_path = str(tmp_path / "packages" / "backend" / "src" / "index.ts")
        sample_graph.nodes["@org/shared"].file_path = str(tmp_path / "packages" / "shared" / "src" / "utils.ts")

        # Create the actual files for path resolution
        for node in sample_graph.nodes.values():
            p = Path(node.file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

        analyzer = DependencyAnalyzer(sample_graph)
        analyzer.set_workspace_boundary(workspace_boundary)

        violations = analyzer.validate_workspace_imports()

        # frontend -> backend is a violation (either private_package or undeclared_dependency)
        assert len(violations) >= 1

        # Check the violation details
        backend_violation = next((v for v in violations if v["to_module"] == "@org/backend"), None)
        assert backend_violation is not None
        assert "@org/frontend" in backend_violation["from_module"] or "frontend" in backend_violation["from_file"]
        # Violation can be either private_package (backend is PRIVATE) or undeclared_dependency
        assert backend_violation["violation_type"] in ("private_package", "undeclared_dependency")

    def test_classify_violation_types(self, sample_graph: DependencyGraph):
        """Test violation classification."""
        analyzer = DependencyAnalyzer(sample_graph)

        assert analyzer._classify_violation("not accessible") == "private_package"
        assert analyzer._classify_violation("does not declare dependency") == "undeclared_dependency"
        assert analyzer._classify_violation("restricted access") == "restricted_access"
        assert analyzer._classify_violation("some other reason") == "boundary_violation"
        assert analyzer._classify_violation(None) == "unknown"

    def test_get_cross_package_dependencies(
        self, sample_graph: DependencyGraph, workspace_boundary: WorkspaceBoundary, tmp_path: Path
    ):
        """Test cross-package dependency calculation."""
        # Setup paths
        sample_graph.nodes["@org/frontend"].file_path = str(tmp_path / "packages" / "frontend" / "src" / "app.ts")
        sample_graph.nodes["@org/backend"].file_path = str(tmp_path / "packages" / "backend" / "src" / "index.ts")
        sample_graph.nodes["@org/shared"].file_path = str(tmp_path / "packages" / "shared" / "src" / "utils.ts")

        for node in sample_graph.nodes.values():
            p = Path(node.file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

        analyzer = DependencyAnalyzer(sample_graph)
        analyzer.set_workspace_boundary(workspace_boundary)

        cross_deps = analyzer.get_cross_package_dependencies()

        # frontend imports from shared and backend
        assert "@org/frontend" in cross_deps
        # backend imports from shared
        assert "@org/backend" in cross_deps

    def test_get_workspace_metrics(
        self, sample_graph: DependencyGraph, workspace_boundary: WorkspaceBoundary, tmp_path: Path
    ):
        """Test workspace metrics calculation."""
        sample_graph.nodes["@org/frontend"].file_path = str(tmp_path / "packages" / "frontend" / "src" / "app.ts")
        sample_graph.nodes["@org/backend"].file_path = str(tmp_path / "packages" / "backend" / "src" / "index.ts")
        sample_graph.nodes["@org/shared"].file_path = str(tmp_path / "packages" / "shared" / "src" / "utils.ts")

        for node in sample_graph.nodes.values():
            p = Path(node.file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

        analyzer = DependencyAnalyzer(sample_graph)
        analyzer.set_workspace_boundary(workspace_boundary)

        metrics = analyzer.get_workspace_metrics()

        assert metrics["workspace_type"] == "npm"
        assert metrics["package_count"] == 3
        assert "@org/frontend" in metrics["packages"]
        assert "@org/backend" in metrics["packages"]
        assert "@org/shared" in metrics["packages"]
        assert metrics["strict_boundaries"] is True
        assert "boundary_violation_count" in metrics

    def test_workspace_metrics_no_boundary(self, sample_graph: DependencyGraph):
        """Test metrics without boundary returns error."""
        analyzer = DependencyAnalyzer(sample_graph)

        metrics = analyzer.get_workspace_metrics()

        assert "error" in metrics

    def test_detect_workspace_boundary_integration(self, sample_graph: DependencyGraph, tmp_path: Path):
        """Test auto-detection of workspace boundary."""
        # Create npm workspace structure
        root_pkg = tmp_path / "package.json"
        root_pkg.write_text('{"workspaces": ["packages/*"]}')

        # Create packages
        for pkg in ["frontend", "backend", "shared"]:
            pkg_dir = tmp_path / "packages" / pkg
            pkg_dir.mkdir(parents=True, exist_ok=True)
            (pkg_dir / "package.json").write_text(f'{{"name": "@org/{pkg}", "dependencies": {{}}}}')

        analyzer = DependencyAnalyzer(sample_graph)
        boundary = analyzer.detect_workspace_boundary(tmp_path)

        assert boundary is not None
        assert boundary.workspace_type == WorkspaceType.NPM
        assert len(boundary.packages) == 3
        assert analyzer.get_workspace_boundary() == boundary


class TestPrivatePackageAccess:
    """Test private package accessibility."""

    def test_private_package_not_accessible(self, tmp_path: Path):
        """Test that private packages are not accessible."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
            strict_boundaries=True,
        )

        # Create private internal package
        internal_path = tmp_path / "packages" / "internal"
        internal_path.mkdir(parents=True)

        boundary.packages["@org/internal"] = WorkspacePackage(
            name="@org/internal",
            path=internal_path,
            visibility=PackageVisibility.PRIVATE,
            dependencies=set(),
        )

        # Try to import from another package
        frontend_path = tmp_path / "packages" / "frontend"
        frontend_path.mkdir(parents=True)

        boundary.packages["@org/frontend"] = WorkspacePackage(
            name="@org/frontend",
            path=frontend_path,
            visibility=PackageVisibility.PRIVATE,
            dependencies=set(),  # No declared dependency on internal
        )

        # Create test file
        test_file = frontend_path / "src" / "app.ts"
        test_file.parent.mkdir(parents=True)
        test_file.touch()

        allowed, reason = boundary.is_import_allowed(test_file, "@org/internal")

        assert not allowed
        assert "not accessible" in reason or "does not declare" in reason


class TestRestrictedPackageAccess:
    """Test restricted package accessibility."""

    def test_restricted_package_allowed_dependents(self, tmp_path: Path):
        """Test that restricted packages only allow specified dependents."""
        boundary = WorkspaceBoundary(
            root=tmp_path,
            workspace_type=WorkspaceType.NPM,
            strict_boundaries=True,
        )

        # Create restricted package
        restricted_path = tmp_path / "packages" / "restricted"
        restricted_path.mkdir(parents=True)

        boundary.packages["@org/restricted"] = WorkspacePackage(
            name="@org/restricted",
            path=restricted_path,
            visibility=PackageVisibility.RESTRICTED,
            dependencies=set(),
            allowed_dependents={"@org/admin"},  # Only admin can access
        )

        # Admin package
        admin_path = tmp_path / "packages" / "admin"
        admin_path.mkdir(parents=True)

        boundary.packages["@org/admin"] = WorkspacePackage(
            name="@org/admin",
            path=admin_path,
            visibility=PackageVisibility.PRIVATE,
            dependencies={"@org/restricted"},
        )

        # Frontend package (not allowed)
        frontend_path = tmp_path / "packages" / "frontend"
        frontend_path.mkdir(parents=True)

        boundary.packages["@org/frontend"] = WorkspacePackage(
            name="@org/frontend",
            path=frontend_path,
            visibility=PackageVisibility.PRIVATE,
            dependencies={"@org/restricted"},  # Declared but not allowed
        )

        # Admin can access
        admin_file = admin_path / "src" / "index.ts"
        admin_file.parent.mkdir(parents=True)
        admin_file.touch()

        allowed, _ = boundary.is_import_allowed(admin_file, "@org/restricted")
        assert allowed

        # Frontend cannot access (not in allowed_dependents)
        frontend_file = frontend_path / "src" / "app.ts"
        frontend_file.parent.mkdir(parents=True)
        frontend_file.touch()

        allowed, reason = boundary.is_import_allowed(frontend_file, "@org/restricted")
        assert not allowed
        assert "not accessible" in reason
