"""Compatibility shim: old `raptor` module.

This module remains to preserve backwards compatibility. Use
`codegraph.chunking.hcr.HCRChunker` and the `Chunk` dataclass going forward.
"""

from warnings import warn

warn("codegraph.chunking.raptor is deprecated; use codegraph.chunking.hcr", DeprecationWarning)

from core.chunking.hcr import HCRChunker

# Provide old name for compatibility
RaptorChunker = HCRChunker
