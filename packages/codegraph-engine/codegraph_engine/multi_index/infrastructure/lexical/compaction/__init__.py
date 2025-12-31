"""Compaction Manager - Two-Phase Base 재인덱싱."""

from codegraph_engine.multi_index.infrastructure.lexical.compaction.freeze_buffer import FreezeBuffer
from codegraph_engine.multi_index.infrastructure.lexical.compaction.manager import CompactionManager

__all__ = [
    "CompactionManager",
    "FreezeBuffer",
]
