"""
Tests for Import Resolution Engine
"""

import pytest
from pathlib import Path
from src.contexts.code_foundation.infrastructure.import_resolver import (
    ImportResolver,
    ImportStatement,
    ResolvedImport,
)


class TestImportParsing:
    """Test import statement parsing"""

    def test_parse_python_simple_import(self):
        """Parse: import os"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import os", "python", "test.py")

        assert stmt is not None
        assert stmt.module_path == "os"
        assert stmt.imported_names == ["os"]
        assert not stmt.is_wildcard

    def test_parse_python_import_as(self):
        """Parse: import numpy as np"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import numpy as np", "python", "test.py")

        assert stmt is not None
        assert stmt.module_path == "numpy"
        assert stmt.aliases == {"numpy": "np"}

    def test_parse_python_from_import(self):
        """Parse: from os import path"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("from os import path", "python", "test.py")

        assert stmt is not None
        assert stmt.module_path == "os"
        assert stmt.imported_names == ["path"]

    def test_parse_python_from_import_multiple(self):
        """Parse: from typing import List, Dict, Optional"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("from typing import List, Dict, Optional", "python", "test.py")

        assert stmt is not None
        assert stmt.module_path == "typing"
        assert set(stmt.imported_names) == {"List", "Dict", "Optional"}

    def test_parse_python_from_import_as(self):
        """Parse: from typing import List as L"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("from typing import List as L", "python", "test.py")

        assert stmt is not None
        assert stmt.module_path == "typing"
        assert stmt.imported_names == ["List"]
        assert stmt.aliases == {"List": "L"}

    def test_parse_python_wildcard(self):
        """Parse: from os import *"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("from os import *", "python", "test.py")

        assert stmt is not None
        assert stmt.module_path == "os"
        assert stmt.is_wildcard

    def test_parse_java_import(self):
        """Parse: import java.util.List;"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import java.util.List;", "java", "Test.java")

        assert stmt is not None
        assert stmt.module_path == "java.util.List"
        assert stmt.imported_names == ["List"]

    def test_parse_java_wildcard(self):
        """Parse: import java.util.*;"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import java.util.*;", "java", "Test.java")

        assert stmt is not None
        assert stmt.module_path == "java.util"
        assert stmt.is_wildcard

    def test_parse_typescript_named_import(self):
        """Parse: import { Component } from '@angular/core'"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import { Component } from '@angular/core'", "typescript", "test.ts")

        assert stmt is not None
        assert stmt.module_path == "@angular/core"
        assert stmt.imported_names == ["Component"]

    def test_parse_typescript_multiple_named(self):
        """Parse: import { A, B as C } from 'module'"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import { useState, useEffect as effect } from 'react'", "typescript", "test.ts")

        assert stmt is not None
        assert stmt.module_path == "react"
        assert set(stmt.imported_names) == {"useState", "useEffect"}
        assert stmt.aliases == {"useEffect": "effect"}

    def test_parse_typescript_default_import(self):
        """Parse: import React from 'react'"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import React from 'react'", "typescript", "test.ts")

        assert stmt is not None
        assert stmt.module_path == "react"
        assert stmt.imported_names == ["React"]

    def test_parse_typescript_wildcard(self):
        """Parse: import * as Utils from './utils'"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import * as Utils from './utils'", "typescript", "test.ts")

        assert stmt is not None
        assert stmt.module_path == "./utils"
        assert stmt.is_wildcard
        assert stmt.aliases == {"*": "Utils"}


class TestImportResolution:
    """Test import resolution"""

    def test_resolve_external_python(self):
        """Resolve external Python package"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = ImportStatement(
            source_file="test.py",
            module_path="numpy",
            imported_names=["array"],
            language="python",
        )

        resolved = resolver.resolve_import(stmt)

        assert resolved.is_external
        assert resolved.target_package == "numpy"
        assert resolved.confidence > 0.5

    def test_resolve_stdlib_python(self):
        """Resolve Python standard library"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = ImportStatement(
            source_file="test.py",
            module_path="os.path",
            imported_names=["join"],
            language="python",
        )

        resolved = resolver.resolve_import(stmt)

        assert resolved.is_external  # stdlib is external
        assert resolved.target_package == "os"

    def test_resolve_external_java(self):
        """Resolve external Java package"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = ImportStatement(
            source_file="Test.java",
            module_path="org.springframework.boot.SpringApplication",
            imported_names=["SpringApplication"],
            language="java",
        )

        resolved = resolver.resolve_import(stmt)

        assert resolved.is_external
        assert resolved.target_package == "org"

    def test_resolve_external_typescript(self):
        """Resolve external TypeScript package"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = ImportStatement(
            source_file="test.ts",
            module_path="@angular/core",
            imported_names=["Component"],
            language="typescript",
        )

        resolved = resolver.resolve_import(stmt)

        assert resolved.is_external
        assert resolved.target_package == "@angular/core"

    def test_resolve_project_file_python(self, tmp_path):
        """Resolve project-local Python file"""
        # Create project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        utils_file = src_dir / "utils.py"
        utils_file.write_text("def helper(): pass")

        resolver = ImportResolver(project_root=str(tmp_path))

        stmt = ImportStatement(
            source_file="test.py",
            module_path="src.utils",
            imported_names=["helper"],
            language="python",
        )

        resolved = resolver.resolve_import(stmt)

        assert not resolved.is_external
        assert resolved.target_file is not None
        assert "utils.py" in resolved.target_file
        assert resolved.confidence == 1.0


class TestAliasing:
    """Test aliasing support"""

    def test_get_effective_name(self):
        """Test alias resolution"""
        stmt = ImportStatement(
            source_file="test.py",
            module_path="numpy",
            imported_names=["array"],
            aliases={"array": "arr"},
            language="python",
        )

        assert stmt.get_effective_name("array") == "arr"
        assert stmt.get_effective_name("other") == "other"


class TestResolveAllImports:
    """Test batch import resolution"""

    def test_resolve_all_python(self):
        """Resolve all imports from Python code"""
        code = """
import os
import numpy as np
from typing import List, Dict
from pathlib import Path

def main():
    pass
"""

        resolver = ImportResolver(project_root="/tmp")

        resolved = resolver.resolve_all_imports(code, "python", "test.py")

        assert len(resolved) == 4

        # Check each import
        modules = [r.import_stmt.module_path for r in resolved]
        assert "os" in modules
        assert "numpy" in modules
        assert "typing" in modules
        assert "pathlib" in modules

    def test_resolve_all_java(self):
        """Resolve all imports from Java code"""
        code = """
package com.example;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;

public class Main {
}
"""

        resolver = ImportResolver(project_root="/tmp")

        resolved = resolver.resolve_all_imports(code, "java", "Main.java")

        assert len(resolved) == 3

        modules = [r.import_stmt.module_path for r in resolved]
        assert "java.util.List" in modules
        assert "java.util.Map" in modules
        assert "org.springframework.boot.SpringApplication" in modules

    def test_resolve_all_typescript(self):
        """Resolve all imports from TypeScript code"""
        code = """
import React from 'react';
import { Component } from '@angular/core';
import { useState, useEffect } from 'react';

export const App = () => {};
"""

        resolver = ImportResolver(project_root="/tmp")

        resolved = resolver.resolve_all_imports(code, "typescript", "app.ts")

        assert len(resolved) == 3

        modules = [r.import_stmt.module_path for r in resolved]
        assert "react" in modules
        assert "@angular/core" in modules


class TestEdgeCases:
    """Test edge cases"""

    def test_empty_code(self):
        """Empty source code"""
        resolver = ImportResolver(project_root="/tmp")

        resolved = resolver.resolve_all_imports("", "python", "test.py")

        assert len(resolved) == 0

    def test_no_imports(self):
        """Code without imports"""
        code = """
def main():
    print("Hello")
"""

        resolver = ImportResolver(project_root="/tmp")

        resolved = resolver.resolve_all_imports(code, "python", "test.py")

        assert len(resolved) == 0

    def test_malformed_import(self):
        """Malformed import statement"""
        resolver = ImportResolver(project_root="/tmp")

        stmt = resolver.parse_import("import", "python", "test.py")

        assert stmt is None
