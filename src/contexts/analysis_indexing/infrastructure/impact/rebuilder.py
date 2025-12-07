"""
Partial Graph Rebuilder

Rebuilds only affected parts of the graph based on impact analysis.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from .models import (
    RebuildStrategy,
)

logger = structlog.get_logger(__name__)


@dataclass
class RebuildMetrics:
    """Metrics for rebuild operation"""

    symbols_analyzed: int = 0
    symbols_rebuilt: int = 0
    symbols_skipped: int = 0

    cfg_rebuilds: int = 0
    dfg_rebuilds: int = 0
    cg_rebuilds: int = 0
    tg_rebuilds: int = 0

    time_ms: float = 0.0
    memory_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "symbols_analyzed": self.symbols_analyzed,
            "symbols_rebuilt": self.symbols_rebuilt,
            "symbols_skipped": self.symbols_skipped,
            "rebuild_ratio": (self.symbols_rebuilt / self.symbols_analyzed if self.symbols_analyzed > 0 else 0),
            "cfg_rebuilds": self.cfg_rebuilds,
            "dfg_rebuilds": self.dfg_rebuilds,
            "cg_rebuilds": self.cg_rebuilds,
            "tg_rebuilds": self.tg_rebuilds,
            "time_ms": self.time_ms,
            "memory_mb": self.memory_mb,
        }


@dataclass
class PartialGraphRebuilder:
    """
    Partial graph rebuilder

    Rebuilds only affected parts of the graph based on impact analysis.

    Example:
        # Analyze changes
        analyzer = ImpactAnalyzer()
        result = await analyzer.analyze_changes(base_ir, new_ir, call_graph)

        # Partial rebuild
        rebuilder = PartialGraphRebuilder(graph_store, ir_builder)
        metrics = await rebuilder.rebuild(result.strategy)

        print(f"Rebuilt {metrics.symbols_rebuilt}/{metrics.symbols_analyzed} symbols")
    """

    # Dependencies
    graph_store: Any | None = None
    ir_builder: Any | None = None

    # Metrics
    metrics: RebuildMetrics = field(default_factory=RebuildMetrics)

    async def rebuild(
        self,
        strategy: RebuildStrategy,
        ir_docs: dict[str, Any] | None = None,
    ) -> RebuildMetrics:
        """
        Execute partial rebuild based on strategy

        Args:
            strategy: RebuildStrategy from impact analysis
            ir_docs: Optional new IR documents

        Returns:
            RebuildMetrics with performance data
        """
        import time

        start_time = time.time()

        logger.info(
            "starting_partial_rebuild",
            symbols=len(strategy.rebuild_symbols),
            max_depth=strategy.max_depth,
        )

        self.metrics = RebuildMetrics()
        self.metrics.symbols_analyzed = len(strategy.rebuild_symbols)

        # Rebuild symbols
        if strategy.parallel:
            await self._rebuild_parallel(strategy, ir_docs)
        else:
            await self._rebuild_sequential(strategy, ir_docs)

        # Record metrics
        self.metrics.time_ms = (time.time() - start_time) * 1000

        logger.info(
            "partial_rebuild_complete",
            rebuilt=self.metrics.symbols_rebuilt,
            skipped=self.metrics.symbols_skipped,
            time_ms=self.metrics.time_ms,
        )

        return self.metrics

    async def _rebuild_sequential(
        self,
        strategy: RebuildStrategy,
        ir_docs: dict[str, Any] | None,
    ):
        """Rebuild symbols sequentially"""
        for symbol_id in strategy.rebuild_symbols:
            await self._rebuild_symbol(symbol_id, strategy)

    async def _rebuild_parallel(
        self,
        strategy: RebuildStrategy,
        ir_docs: dict[str, Any] | None,
    ):
        """Rebuild symbols in parallel"""
        # Batch symbols
        symbol_list = list(strategy.rebuild_symbols)
        batches = [symbol_list[i : i + strategy.batch_size] for i in range(0, len(symbol_list), strategy.batch_size)]

        for batch in batches:
            tasks = [self._rebuild_symbol(symbol_id, strategy) for symbol_id in batch]
            await asyncio.gather(*tasks)

    async def _rebuild_symbol(
        self,
        symbol_id: str,
        strategy: RebuildStrategy,
    ):
        """
        Rebuild a single symbol

        Rebuilds only the components specified in strategy:
        - CFG: Control flow graph
        - DFG: Data flow graph
        - CG: Call graph edges
        - TG: Type graph edges
        """
        logger.debug("rebuilding_symbol", symbol=symbol_id)

        # Check if symbol needs rebuild (could be filtered)
        if not self._should_rebuild(symbol_id, strategy):
            self.metrics.symbols_skipped += 1
            return

        # Rebuild CFG
        if strategy.rebuild_cfg:
            await self._rebuild_cfg(symbol_id)
            self.metrics.cfg_rebuilds += 1

        # Rebuild DFG
        if strategy.rebuild_dfg:
            await self._rebuild_dfg(symbol_id)
            self.metrics.dfg_rebuilds += 1

        # Rebuild call graph
        if strategy.rebuild_call_graph:
            await self._rebuild_call_graph(symbol_id)
            self.metrics.cg_rebuilds += 1

        # Rebuild type graph
        if strategy.rebuild_type_graph:
            await self._rebuild_type_graph(symbol_id)
            self.metrics.tg_rebuilds += 1

        self.metrics.symbols_rebuilt += 1

    def _should_rebuild(
        self,
        symbol_id: str,
        strategy: RebuildStrategy,
    ) -> bool:
        """Check if symbol should be rebuilt"""
        # For now, rebuild all in strategy
        return True

    async def _rebuild_cfg(self, symbol_id: str):
        """Rebuild control flow graph for symbol"""
        logger.debug("rebuilding_cfg", symbol=symbol_id)
        # In real impl, would rebuild CFG from AST
        # For now, placeholder
        pass

    async def _rebuild_dfg(self, symbol_id: str):
        """Rebuild data flow graph for symbol"""
        logger.debug("rebuilding_dfg", symbol=symbol_id)
        # In real impl, would rebuild DFG
        pass

    async def _rebuild_call_graph(self, symbol_id: str):
        """Rebuild call graph edges for symbol"""
        logger.debug("rebuilding_call_graph", symbol=symbol_id)
        # In real impl, would update call graph edges
        pass

    async def _rebuild_type_graph(self, symbol_id: str):
        """Rebuild type graph edges for symbol"""
        logger.debug("rebuilding_type_graph", symbol=symbol_id)
        # In real impl, would update type graph edges
        pass

    def estimate_savings(
        self,
        strategy: RebuildStrategy,
        total_symbols: int,
    ) -> dict[str, Any]:
        """
        Estimate savings from partial rebuild vs full rebuild

        Returns:
            {
                "full_rebuild_symbols": int,
                "partial_rebuild_symbols": int,
                "symbols_saved": int,
                "time_saved_pct": float,
                "memory_saved_pct": float,
            }
        """
        partial_count = len(strategy.rebuild_symbols)
        full_count = total_symbols

        symbols_saved = full_count - partial_count
        time_saved_pct = (symbols_saved / full_count * 100) if full_count > 0 else 0
        memory_saved_pct = time_saved_pct  # Approximate

        return {
            "full_rebuild_symbols": full_count,
            "partial_rebuild_symbols": partial_count,
            "symbols_saved": symbols_saved,
            "time_saved_pct": time_saved_pct,
            "memory_saved_pct": memory_saved_pct,
        }

    def __repr__(self) -> str:
        return f"PartialGraphRebuilder(rebuilt={self.metrics.symbols_rebuilt}, skipped={self.metrics.symbols_skipped})"
