"""Test file for import statements"""

import os
import sys
from typing import List, Dict


class TestClass:
    """Test class with imports"""

    def __init__(self):
        self.data = []

    def process_data(self, items: List[str]) -> Dict[str, int]:
        """Process items and return counts"""
        result = {}
        for item in items:
            result[item] = len(item)
        return result
