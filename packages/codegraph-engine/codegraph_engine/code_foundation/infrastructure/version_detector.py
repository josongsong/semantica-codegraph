"""
Version Detection for Package Management Files

Extracts version information from:
- Python: pyproject.toml, setup.py, setup.cfg, __init__.py
- Java: pom.xml, build.gradle, build.gradle.kts
- TypeScript/JavaScript: package.json
"""

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import tomllib

logger = logging.getLogger(__name__)


class VersionDetector:
    """Detect package version from various files"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)

    def detect_version(self, language: str, package_name: str = "") -> str:
        """
        Detect version for given language

        Args:
            language: "python", "java", "typescript", "javascript"
            package_name: Optional package name for better detection

        Returns:
            Version string or "unknown"
        """
        if language == "python":
            return self._detect_python_version()
        elif language == "java":
            return self._detect_java_version()
        elif language in ["typescript", "javascript"]:
            return self._detect_nodejs_version()

        return "unknown"

    def _detect_python_version(self) -> str:
        """Detect Python package version"""
        # Try pyproject.toml (preferred)
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            version = self._parse_pyproject_toml(pyproject)
            if version:
                return version

        # Try setup.py
        setup_py = self.project_root / "setup.py"
        if setup_py.exists():
            version = self._parse_setup_py(setup_py)
            if version:
                return version

        # Try setup.cfg
        setup_cfg = self.project_root / "setup.cfg"
        if setup_cfg.exists():
            version = self._parse_setup_cfg(setup_cfg)
            if version:
                return version

        # Try __init__.py
        for init_file in self.project_root.rglob("__init__.py"):
            version = self._parse_init_py(init_file)
            if version:
                return version
            break  # Only check first __init__.py

        return "unknown"

    def _detect_java_version(self) -> str:
        """Detect Java package version"""
        # Try pom.xml (Maven)
        pom = self.project_root / "pom.xml"
        if pom.exists():
            version = self._parse_pom_xml(pom)
            if version:
                return version

        # Try build.gradle (Gradle)
        build_gradle = self.project_root / "build.gradle"
        if build_gradle.exists():
            version = self._parse_gradle(build_gradle)
            if version:
                return version

        # Try build.gradle.kts (Kotlin DSL)
        build_gradle_kts = self.project_root / "build.gradle.kts"
        if build_gradle_kts.exists():
            version = self._parse_gradle_kts(build_gradle_kts)
            if version:
                return version

        return "unknown"

    def _detect_nodejs_version(self) -> str:
        """Detect Node.js package version"""
        package_json = self.project_root / "package.json"
        if package_json.exists():
            version = self._parse_package_json(package_json)
            if version:
                return version

        return "unknown"

    def _parse_pyproject_toml(self, path: Path) -> str | None:
        """Parse pyproject.toml for version"""
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            # Poetry
            if "tool" in data and "poetry" in data["tool"]:
                return data["tool"]["poetry"].get("version")

            # PEP 621
            if "project" in data:
                return data["project"].get("version")

        except Exception as e:
            logger.debug("Failed to parse pyproject.toml: %s", e)

        return None

    def _parse_setup_py(self, path: Path) -> str | None:
        """Parse setup.py for version"""
        try:
            content = path.read_text()

            # Look for version= parameter
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

            # Look for __version__
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

        except Exception as e:
            logger.debug("Failed to parse setup.py: %s", e)

        return None

    def _parse_setup_cfg(self, path: Path) -> str | None:
        """Parse setup.cfg for version"""
        try:
            content = path.read_text()

            # Look for version under [metadata]
            match = re.search(r"\[metadata\].*?version\s*=\s*([^\n]+)", content, re.DOTALL)
            if match:
                return match.group(1).strip()

        except Exception as e:
            logger.debug("Failed to parse setup.cfg: %s", e)

        return None

    def _parse_init_py(self, path: Path) -> str | None:
        """Parse __init__.py for __version__"""
        try:
            content = path.read_text()

            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

        except Exception as e:
            logger.debug("Failed to parse __init__.py: %s", e)

        return None

    def _parse_pom_xml(self, path: Path) -> str | None:
        """Parse pom.xml for version"""
        try:
            tree = ET.parse(path)
            root = tree.getroot()

            # Handle namespace
            ns = {"maven": "http://maven.apache.org/POM/4.0.0"}

            # Try with namespace
            version = root.find("maven:version", ns)
            if version is not None and version.text:
                return version.text

            # Try without namespace
            version = root.find("version")
            if version is not None and version.text:
                return version.text

        except Exception as e:
            logger.debug("Failed to parse pom.xml: %s", e)

        return None

    def _parse_gradle(self, path: Path) -> str | None:
        """Parse build.gradle for version"""
        try:
            content = path.read_text()

            # Look for version = "x.y.z"
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

            # Look for version "x.y.z"
            match = re.search(r'version\s+["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

        except Exception as e:
            logger.debug("Failed to parse build.gradle: %s", e)

        return None

    def _parse_gradle_kts(self, path: Path) -> str | None:
        """Parse build.gradle.kts for version"""
        try:
            content = path.read_text()

            # Look for version = "x.y.z"
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)

        except Exception as e:
            logger.debug("Failed to parse build.gradle.kts: %s", e)

        return None

    def _parse_package_json(self, path: Path) -> str | None:
        """Parse package.json for version"""
        try:
            import json

            with open(path) as f:
                data = json.load(f)

            return data.get("version")

        except Exception as e:
            logger.debug("Failed to parse package.json: %s", e)

        return None
