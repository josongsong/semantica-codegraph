"""
Unit tests for Jupyter Notebook parser.
"""

import pytest
from codegraph_parsers import NotebookParser


class TestNotebookParser:
    """Test Jupyter Notebook parser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return NotebookParser()

    def test_simple_notebook(self, parser):
        """Test parsing simple notebook."""
        # Minimal valid notebook JSON
        content = """{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": ["# Title"]
  },
  {
   "cell_type": "code",
   "execution_count": 1,
   "metadata": {},
   "source": ["print('hello')"],
   "outputs": []
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("test.ipynb", content)

        assert result.file_path == "test.ipynb"
        assert len(result.sections) >= 2

    def test_code_cells(self, parser):
        """Test parsing code cells."""
        content = """{
 "cells": [
  {
   "cell_type": "code",
   "source": ["import numpy as np", "import pandas as pd"],
   "metadata": {},
   "outputs": []
  },
  {
   "cell_type": "code",
   "source": ["df = pd.DataFrame()"],
   "metadata": {},
   "outputs": []
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("data.ipynb", content)

        # Should find code cells
        code_sections = [s for s in result.sections if s.section_type == "CODE"]
        assert len(code_sections) >= 2

    def test_markdown_cells(self, parser):
        """Test parsing markdown cells."""
        content = """{
 "cells": [
  {
   "cell_type": "markdown",
   "source": ["# Analysis Report", "## Overview"]
  },
  {
   "cell_type": "markdown",
   "source": ["This is the analysis."]
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("report.ipynb", content)

        # Should find markdown sections
        assert len(result.sections) >= 2

    def test_mixed_cells(self, parser):
        """Test notebook with mixed cell types."""
        content = """{
 "cells": [
  {
   "cell_type": "markdown",
   "source": ["# Data Analysis"]
  },
  {
   "cell_type": "code",
   "source": ["import pandas as pd"],
   "outputs": []
  },
  {
   "cell_type": "markdown",
   "source": ["Load data:"]
  },
  {
   "cell_type": "code",
   "source": ["df = pd.read_csv('data.csv')"],
   "outputs": []
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("analysis.ipynb", content)

        assert result.file_path == "analysis.ipynb"
        assert len(result.sections) >= 4

    def test_empty_notebook(self, parser):
        """Test empty notebook."""
        content = """{
 "cells": [],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("empty.ipynb", content)

        assert result.file_path == "empty.ipynb"
        assert len(result.sections) == 0

    def test_multiline_code(self, parser):
        """Test code cell with multiple lines."""
        content = """{
 "cells": [
  {
   "cell_type": "code",
   "source": [
     "def calculate(x, y):",
     "    result = x + y",
     "    return result"
   ],
   "outputs": []
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("functions.ipynb", content)

        code_sections = [s for s in result.sections if s.section_type == "CODE"]
        assert len(code_sections) >= 1

    def test_raw_cells(self, parser):
        """Test raw cell type."""
        content = """{
 "cells": [
  {
   "cell_type": "raw",
   "source": ["Raw content here"]
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("raw.ipynb", content)

        assert result.file_path == "raw.ipynb"

    def test_cell_outputs(self, parser):
        """Test cells with outputs."""
        content = """{
 "cells": [
  {
   "cell_type": "code",
   "source": ["print('hello')"],
   "outputs": [
    {
     "output_type": "stream",
     "name": "stdout",
     "text": ["hello\\n"]
    }
   ]
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("output.ipynb", content)

        assert result.file_path == "output.ipynb"

    def test_complex_notebook(self, parser):
        """Test complex notebook with various features."""
        content = """{
 "cells": [
  {
   "cell_type": "markdown",
   "source": ["# Machine Learning Notebook"]
  },
  {
   "cell_type": "code",
   "source": ["import numpy as np", "import sklearn"],
   "outputs": []
  },
  {
   "cell_type": "markdown",
   "source": ["## Load Data"]
  },
  {
   "cell_type": "code",
   "source": ["X, y = load_data()"],
   "outputs": []
  },
  {
   "cell_type": "markdown",
   "source": ["## Train Model"]
  },
  {
   "cell_type": "code",
   "source": ["model.fit(X, y)"],
   "outputs": []
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

        result = parser.parse("ml.ipynb", content)

        assert len(result.sections) >= 6
