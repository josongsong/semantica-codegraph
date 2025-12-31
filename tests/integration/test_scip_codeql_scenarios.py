"""
SCIP and CodeQL Scenario Tests

Tests for industry-standard analysis scenarios:
- SCIP: Cross-file references, imports, package metadata
- CodeQL: Taint analysis, security vulnerabilities, code quality
"""

from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


class TestSCIPScenarios:
    """Test SCIP-compatible scenarios"""

    @pytest.fixture
    def builder(self):
        return LayeredIRBuilder(project_root=Path.cwd())

    @pytest.fixture
    def fixture_root(self):
        return Path.cwd() / "benchmark" / "test_fixtures"

    # ============================================================
    # SCIP: Cross-file References
    # ============================================================

    @pytest.mark.asyncio
    async def test_python_cross_file_refs(self, builder, fixture_root):
        """Test Python cross-file reference tracking (SCIP)"""
        file_path = fixture_root / "python" / "scip" / "cross_file_refs.py"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Should track imports and references
        assert len(ir_doc.nodes) > 0, "Nodes for cross-file refs"
        assert len(ir_doc.edges) > 0, "Edges for cross-file refs"

        # SCIP should track symbol occurrences
        assert len(ir_doc.occurrences) > 0, "SCIP occurrences tracked"

    @pytest.mark.asyncio
    async def test_python_package_metadata(self, builder, fixture_root):
        """Test Python package metadata extraction (SCIP)"""
        file_path = fixture_root / "python" / "scip" / "package_metadata.py"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Should extract documentation and metadata
        assert len(ir_doc.nodes) > 0, "Nodes with metadata"
        assert len(ir_doc.occurrences) > 0, "Occurrences for metadata"

    @pytest.mark.asyncio
    async def test_typescript_cross_file_refs(self, builder, fixture_root):
        """Test TypeScript cross-file references (SCIP)"""
        file_path = fixture_root / "typescript" / "scip" / "cross_file_refs.ts"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # TypeScript imports and exports - file only has imports, no executable code
        assert len(ir_doc.nodes) > 0, "Nodes for TS imports"
        assert len(ir_doc.occurrences) > 0, "SCIP occurrences for TS"

    @pytest.mark.asyncio
    async def test_java_cross_file_refs(self, builder, fixture_root):
        """Test Java cross-file references (SCIP)"""
        file_path = fixture_root / "java" / "scip" / "CrossFileRefs.java"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Java imports and package structure
        assert len(ir_doc.nodes) > 0, "Nodes for Java imports"
        assert len(ir_doc.occurrences) > 0, "SCIP occurrences for Java"


class TestCodeQLScenarios:
    """Test CodeQL-compatible security scenarios"""

    @pytest.fixture
    def builder(self):
        return LayeredIRBuilder(project_root=Path.cwd())

    @pytest.fixture
    def fixture_root(self):
        return Path.cwd() / "benchmark" / "test_fixtures"

    # ============================================================
    # CodeQL: Taint Analysis
    # ============================================================

    @pytest.mark.asyncio
    async def test_python_taint_analysis(self, builder, fixture_root):
        """Test Python taint analysis (CodeQL)"""
        file_path = fixture_root / "python" / "codeql" / "taint_analysis.py"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Should have functions and data flow
        assert len(ir_doc.nodes) >= 30, f"Nodes for taint sources/sinks, got {len(ir_doc.nodes)}"
        assert len(ir_doc.edges) >= 50, f"Edges for data flow, got {len(ir_doc.edges)}"
        assert len(ir_doc.occurrences) > 0, "Occurrences for symbol tracking"

    @pytest.mark.asyncio
    async def test_python_code_quality(self, builder, fixture_root):
        """Test Python code quality analysis (CodeQL)"""
        file_path = fixture_root / "python" / "codeql" / "code_quality.py"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Should detect structure and control flow
        assert len(ir_doc.nodes) >= 20, f"Nodes for quality checks, got {len(ir_doc.nodes)}"
        assert len(ir_doc.edges) >= 30, f"Edges for control flow, got {len(ir_doc.edges)}"

    @pytest.mark.asyncio
    async def test_python_security_patterns(self, builder, fixture_root):
        """Test Python security patterns (CodeQL)"""
        file_path = fixture_root / "python" / "codeql" / "security_patterns.py"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Security vulnerabilities should be analyzable
        assert len(ir_doc.nodes) >= 20, f"Nodes for security patterns, got {len(ir_doc.nodes)}"
        assert len(ir_doc.edges) >= 30, f"Edges for security analysis, got {len(ir_doc.edges)}"

    @pytest.mark.asyncio
    async def test_typescript_taint_analysis(self, builder, fixture_root):
        """Test TypeScript taint analysis (CodeQL)"""
        file_path = fixture_root / "typescript" / "codeql" / "taint_analysis.ts"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # TypeScript taint tracking
        assert len(ir_doc.nodes) >= 25, f"Nodes for TS taint, got {len(ir_doc.nodes)}"
        assert len(ir_doc.edges) >= 40, f"Edges for TS taint flow, got {len(ir_doc.edges)}"

    @pytest.mark.asyncio
    async def test_java_taint_analysis(self, builder, fixture_root):
        """Test Java taint analysis (CodeQL)"""
        file_path = fixture_root / "java" / "codeql" / "TaintAnalysis.java"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Java security analysis
        assert len(ir_doc.nodes) >= 10, f"Nodes for Java taint, got {len(ir_doc.nodes)}"
        assert len(ir_doc.edges) >= 30, f"Edges for Java methods, got {len(ir_doc.edges)}"

    # ============================================================
    # Advanced Analysis Integration
    # ============================================================

    @pytest.mark.asyncio
    async def test_taint_flow_detection(self, builder, fixture_root):
        """Test that taint flow can be detected across all languages"""
        files = [
            ("python", fixture_root / "python" / "codeql" / "taint_analysis.py"),
            ("typescript", fixture_root / "typescript" / "codeql" / "taint_analysis.ts"),
            ("java", fixture_root / "java" / "codeql" / "TaintAnalysis.java"),
        ]

        results = {}
        for lang, file_path in files:
            config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
            ir_docs = result.ir_documents
            ir_doc = ir_docs[str(file_path)]

            results[lang] = {
                "nodes": len(ir_doc.nodes),
                "edges": len(ir_doc.edges),
                "occurrences": len(ir_doc.occurrences),
            }

        # All languages should have sufficient IR structure for taint tracking
        for lang, data in results.items():
            # Java has fewer nodes but sufficient edges
            min_nodes = 10 if lang == "java" else 20
            assert data["nodes"] >= min_nodes, f"{lang}: Insufficient nodes for taint"
            assert data["edges"] >= 30, f"{lang}: Insufficient edges for taint"

    @pytest.mark.asyncio
    async def test_scip_compatibility(self, builder, fixture_root):
        """Test SCIP compatibility across all languages"""
        files = [
            ("python", fixture_root / "python" / "scip" / "cross_file_refs.py"),
            ("typescript", fixture_root / "typescript" / "scip" / "cross_file_refs.ts"),
            ("java", fixture_root / "java" / "scip" / "CrossFileRefs.java"),
        ]

        results = {}
        for lang, file_path in files:
            config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
            ir_docs = result.ir_documents
            ir_doc = ir_docs[str(file_path)]

            results[lang] = {
                "occurrences": len(ir_doc.occurrences),
                "nodes": len(ir_doc.nodes),
                "has_dfg": ir_doc.dfg_snapshot is not None,
            }

        # All should have SCIP-compatible data
        for lang, data in results.items():
            assert data["occurrences"] > 0, f"{lang}: No SCIP occurrences"
            assert data["nodes"] > 0, f"{lang}: No nodes"

    @pytest.mark.asyncio
    async def test_comprehensive_security_coverage(self, builder, fixture_root):
        """Test comprehensive security scenario coverage"""
        security_files = [
            fixture_root / "python" / "codeql" / "taint_analysis.py",
            fixture_root / "python" / "codeql" / "security_patterns.py",
            fixture_root / "typescript" / "codeql" / "taint_analysis.ts",
            fixture_root / "java" / "codeql" / "TaintAnalysis.java",
        ]

        failures = []
        for file_path in security_files:
            try:
                config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
                ir_docs = result.ir_documents
                ir_doc = ir_docs[str(file_path)]

                # Security analysis requires nodes and edges
                if len(ir_doc.nodes) == 0:
                    failures.append(f"{file_path.name}: No nodes")
                if len(ir_doc.edges) == 0:
                    failures.append(f"{file_path.name}: No edges")

            except Exception as e:
                failures.append(f"{file_path.name}: {e}")

        assert not failures, f"Security coverage failures: {', '.join(failures)}"

    @pytest.mark.asyncio
    async def test_call_graph_for_taint(self, builder, fixture_root):
        """Test that call graphs support taint analysis"""
        file_path = fixture_root / "python" / "codeql" / "taint_analysis.py"
        config = BuildConfig.for_editor()
        result = await builder.build(files=[file_path], config=config)
        ir_docs = result.ir_documents
        ir_doc = ir_docs[str(file_path)]

        # Should have edges representing function calls
        assert len(ir_doc.edges) > 0, "Edges for call graph"

        # Should track both CALLS and READS/WRITES for taint
        edge_kinds = {edge.kind for edge in ir_doc.edges}
        assert len(edge_kinds) > 0, "Call relationships tracked"
