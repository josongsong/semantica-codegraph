"""
Tests for Version Detector
"""

from pathlib import Path

import pytest

from src.contexts.code_foundation.infrastructure.version_detector import VersionDetector


class TestPythonVersionDetection:
    """Test Python version detection"""

    def test_pyproject_toml_poetry(self, tmp_path):
        """Detect version from pyproject.toml (Poetry)"""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.poetry]
name = "myproject"
version = "1.2.3"
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("python")

        assert version == "1.2.3"

    def test_pyproject_toml_pep621(self, tmp_path):
        """Detect version from pyproject.toml (PEP 621)"""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "myproject"
version = "2.0.0"
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("python")

        assert version == "2.0.0"

    def test_setup_py(self, tmp_path):
        """Detect version from setup.py"""
        setup_py = tmp_path / "setup.py"
        setup_py.write_text("""
from setuptools import setup

setup(
    name="myproject",
    version="3.0.0",
)
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("python")

        assert version == "3.0.0"

    def test_init_py(self, tmp_path):
        """Detect version from __init__.py"""
        init_py = tmp_path / "__init__.py"
        init_py.write_text('__version__ = "4.0.0"\n')

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("python")

        assert version == "4.0.0"


class TestJavaVersionDetection:
    """Test Java version detection"""

    def test_pom_xml(self, tmp_path):
        """Detect version from pom.xml"""
        pom = tmp_path / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project>
    <groupId>com.example</groupId>
    <artifactId>myapp</artifactId>
    <version>1.5.0</version>
</project>
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("java")

        assert version == "1.5.0"

    def test_build_gradle(self, tmp_path):
        """Detect version from build.gradle"""
        gradle = tmp_path / "build.gradle"
        gradle.write_text("""
version = '2.1.0'

dependencies {
}
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("java")

        assert version == "2.1.0"

    def test_build_gradle_kts(self, tmp_path):
        """Detect version from build.gradle.kts"""
        gradle_kts = tmp_path / "build.gradle.kts"
        gradle_kts.write_text("""
version = "3.0.0-SNAPSHOT"

dependencies {
}
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("java")

        assert version == "3.0.0-SNAPSHOT"


class TestNodeJSVersionDetection:
    """Test Node.js version detection"""

    def test_package_json(self, tmp_path):
        """Detect version from package.json"""
        package_json = tmp_path / "package.json"
        package_json.write_text("""{
  "name": "myapp",
  "version": "1.0.0",
  "dependencies": {}
}
""")

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("typescript")

        assert version == "1.0.0"

    def test_package_json_javascript(self, tmp_path):
        """Detect version for JavaScript"""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "myapp", "version": "2.3.4"}')

        detector = VersionDetector(str(tmp_path))
        version = detector.detect_version("javascript")

        assert version == "2.3.4"


class TestFallback:
    """Test fallback behavior"""

    def test_no_version_file(self, tmp_path):
        """Return 'unknown' when no version file exists"""
        detector = VersionDetector(str(tmp_path))

        assert detector.detect_version("python") == "unknown"
        assert detector.detect_version("java") == "unknown"
        assert detector.detect_version("typescript") == "unknown"

    def test_unsupported_language(self, tmp_path):
        """Return 'unknown' for unsupported language"""
        detector = VersionDetector(str(tmp_path))

        assert detector.detect_version("ruby") == "unknown"
        assert detector.detect_version("go") == "unknown"
