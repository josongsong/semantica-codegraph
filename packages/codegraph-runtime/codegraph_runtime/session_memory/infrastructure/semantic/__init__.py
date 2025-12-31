"""
Semantic Memory - Modular Implementation

This package contains specialized managers for semantic memory:
- BugPatternManager: Bug pattern storage and matching
- CodePatternManager: Code refactoring pattern storage
- StyleAnalyzer: Code style analysis and inference
- CodeRuleManager: Learned transformation rules
- ProjectKnowledgeManager: Project-specific knowledge tracking
- SemanticMemoryManager: Main facade (re-exported from parent)
"""

from codegraph_runtime.session_memory.infrastructure.semantic.bug_pattern_manager import BugPatternManager
from codegraph_runtime.session_memory.infrastructure.semantic.code_pattern_manager import CodePatternManager
from codegraph_runtime.session_memory.infrastructure.semantic.code_rule_manager import CodeRuleManager
from codegraph_runtime.session_memory.infrastructure.semantic.project_knowledge_manager import ProjectKnowledgeManager
from codegraph_runtime.session_memory.infrastructure.semantic.semantic_memory_manager import SemanticMemoryManager
from codegraph_runtime.session_memory.infrastructure.semantic.style_analyzer import StyleAnalyzer

__all__ = [
    "BugPatternManager",
    "CodePatternManager",
    "StyleAnalyzer",
    "CodeRuleManager",
    "ProjectKnowledgeManager",
    "SemanticMemoryManager",
]
