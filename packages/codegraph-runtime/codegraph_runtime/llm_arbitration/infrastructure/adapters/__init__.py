"""
Adapters for RFC-027/028 Integration

Converts analysis results to RFC-027 ResultEnvelope format.

Architecture:
- Infrastructure Layer (Hexagonal)
- Stateless adapters (thread-safe)
- Pure functions (deterministic)

Adapters:
- TaintAdapter: TaintAnalysisService → ResultEnvelope (RFC-027 Section 18.B.1)
- SCCPAdapter: SCCP results → ResultEnvelope (RFC-027)
- CostAdapter: CostAnalyzer → ResultEnvelope (RFC-028 Phase 1)
- RaceAdapter: AsyncRaceDetector → ResultEnvelope (RFC-028 Phase 2)
- DiffAdapter: DifferentialAnalyzer → ResultEnvelope (RFC-028 Phase 3)
- ReasoningAdapter: ReasoningResult → Conclusion (RFC-027 Section 18.B)
- RiskAdapter: RiskReport → Claim (RFC-027 Section 18.B)
- DeepReasoningAdapter: DeepReasoningResult → ResultEnvelope

Helper:
- AnalyzerResultAdapter: Strategy pattern dispatcher
"""

from .analyzer_adapter import AnalyzerResultAdapter
from .cost_adapter import CostAdapter
from .deep_reasoning_adapter import DeepReasoningAdapter
from .diff_adapter import DiffAdapter
from .race_adapter import RaceAdapter
from .reasoning_adapter import ReasoningAdapter
from .risk_adapter import RiskAdapter
from .sccp_adapter import SCCPAdapter
from .taint_adapter import TaintAdapter

__all__ = [
    # Core adapters
    "TaintAdapter",
    "SCCPAdapter",
    "CostAdapter",
    "RaceAdapter",
    "DiffAdapter",
    # Meta adapters
    "ReasoningAdapter",
    "RiskAdapter",
    "DeepReasoningAdapter",
    # Dispatcher
    "AnalyzerResultAdapter",
]
