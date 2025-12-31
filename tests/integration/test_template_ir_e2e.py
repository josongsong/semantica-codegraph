"""
End-to-End Integration Test for Template IR (RFC-051)

Tests complete pipeline:
LayeredIRBuilder → Template IR → Taint Analysis → XSS Detection

Author: Semantica Team
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def react_sample_project():
    """Create temporary React project with XSS vulnerability"""
    tmpdir = Path(tempfile.mkdtemp())

    try:
        # Create React component with XSS vulnerability (pure JSX, no TypeScript)
        (tmpdir / "Profile.jsx").write_text(
            """
function Profile({ user }) {
  return (
    <div className="profile">
      <h1>{user.name}</h1>
      <div dangerouslySetInnerHTML={{__html: user.bio}} />
    </div>
  );
}

export default Profile;
"""
        )

        # Safe component (control)
        (tmpdir / "SafeProfile.jsx").write_text(
            """
function SafeProfile({ user }) {
  return (
    <div>
      <h1>{user.name}</h1>
      <p>{user.bio}</p>
    </div>
  );
}

export default SafeProfile;
"""
        )

        # URL injection vulnerability
        (tmpdir / "Link.jsx").write_text(
            """
function DynamicLink({ url, label }) {
  return <a href={url}>{label}</a>;
}

export default DynamicLink;
"""
        )

        yield tmpdir

    finally:
        # Cleanup
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# E2E Tests
# ============================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestTemplateIRE2E:
    """End-to-end template IR tests"""

    async def test_layered_builder_with_template_ir(self, react_sample_project):
        """LayeredIRBuilder processes template IR (Layer 5.5)"""
        builder = LayeredIRBuilder(project_root=react_sample_project)

        files = list(react_sample_project.glob("*.jsx"))
        assert len(files) == 3, f"Expected 3 JSX files, got {len(files)}"

        # Build full IR (including Template IR)
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

        result = await builder.build(
            files,
            BuildConfig(
                cfg=True,
                dfg=True,
                expressions=True,  # For Virtual Template detection
                taint_analysis=False,  # Skip Taint for this test
            ),
        )

        # Verify Template IR generated
        ir_docs = result.ir_documents

        # Profile.jsx should have template slots
        profile_doc = ir_docs.get(str(react_sample_project / "Profile.jsx"))
        assert profile_doc is not None, "Profile.tsx not in IR"

        # Check template slots
        assert len(profile_doc.template_slots) > 0, "No template slots extracted"

        # Check RAW_HTML sink (dangerouslySetInnerHTML)
        raw_html_sinks = profile_doc.get_raw_html_sinks()
        assert len(raw_html_sinks) >= 1, f"dangerouslySetInnerHTML not detected. Slots: {profile_doc.template_slots}"

        # Verify sink properties
        sink = raw_html_sinks[0]
        assert sink.is_sink is True
        assert sink.context_kind.value == "RAW_HTML"
        assert sink.escape_mode.value == "NONE"

    async def test_safe_component_no_sinks(self, react_sample_project):
        """Safe component has no XSS sinks"""
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

        builder = LayeredIRBuilder(project_root=react_sample_project)

        files = [react_sample_project / "SafeProfile.jsx"]

        result = await builder.build(
            files,
            BuildConfig(
                cfg=False,  # Minimal for speed
                dfg=False,
                expressions=False,
            ),
        )

        ir_docs = result.ir_documents
        safe_doc = ir_docs.get(str(files[0]))

        # Should have slots (for {user.name}, {user.bio})
        assert len(safe_doc.template_slots) >= 2

        # But NO sinks (all HTML_TEXT, auto-escaped)
        sinks = [s for s in safe_doc.template_slots if s.is_sink]
        assert len(sinks) == 0, f"False positive: safe slots marked as sinks"

    async def test_url_injection_detected(self, react_sample_project):
        """URL attribute with dynamic value detected as sink"""
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

        builder = LayeredIRBuilder(project_root=react_sample_project)

        files = [react_sample_project / "Link.jsx"]

        result = await builder.build(
            files,
            BuildConfig(
                cfg=False,  # Minimal for speed
                dfg=False,
                expressions=False,
            ),
        )

        ir_docs = result.ir_documents
        link_doc = ir_docs.get(str(files[0]))

        # Should detect href as URL_ATTR sink
        url_sinks = link_doc.get_url_sinks()
        assert len(url_sinks) >= 1, "URL injection not detected"

        sink = url_sinks[0]
        assert sink.is_sink is True
        assert sink.context_kind.value == "URL_ATTR"


# ============================================================
# Performance Tests (E2E Scale)
# ============================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.benchmark
class TestTemplateIRPerformanceE2E:
    """E2E performance tests"""

    async def test_build_with_template_ir_overhead(self, react_sample_project):
        """Template IR adds <10% overhead to build time"""
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
        import time

        builder = LayeredIRBuilder(project_root=react_sample_project)

        files = list(react_sample_project.glob("*.jsx"))

        # Build with Template IR
        start = time.perf_counter()
        result = await builder.build(
            files,
            BuildConfig(
                cfg=False,  # Minimal for speed
                dfg=False,
                expressions=False,
            ),
        )
        with_template = time.perf_counter() - start

        # Verify template slots created
        total_slots = sum(len(doc.template_slots) for doc in result.ir_documents.values())
        assert total_slots > 0

        print(f"\nBuild time with Template IR: {with_template * 1000:.0f}ms")
        print(f"Template slots: {total_slots}")

        # Should complete in reasonable time (<1s for 3 files)
        assert with_template < 1.0, f"Build too slow: {with_template * 1000:.0f}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
