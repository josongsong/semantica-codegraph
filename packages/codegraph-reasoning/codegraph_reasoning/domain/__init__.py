"""
Domain Layer - Reasoning Engine

비즈니스 로직과 도메인 모델 정의.
외부 인프라에 의존하지 않는 순수한 도메인 객체들.

모델 구조:
- models.py: 레거시 호환성 (impact_propagator, impact_classifier, effect_system용)
- effect_models.py: Effect 분석 모델 (권장)
- impact_models.py: Impact 분석 모델 (권장)
- speculative_models.py: Speculative 실행 모델 (권장)
"""

# RFC-021 Phase 0: SliceResult moved to shared_kernel
from codegraph_shared.kernel.slice.models import SliceResult

# Legacy models (for backward compatibility with hash-based rebuild system)
# Primary models (use these for new code)
from .effect_models import (
    EffectDiff,
    EffectSet,
    EffectSeverity,
    EffectType,
)
from .impact_models import (
    ImpactLevel,
    ImpactNode,
    ImpactPath,
    ImpactReport,
    PropagationType,
)
from .models import (
    ChangeType,
    DeltaLayer,
    ErrorSnapshot,
    HashBasedImpactLevel,  # For hash-based impact analysis (different from impact_models.ImpactLevel)
    ImpactType,
    PatchMetadata,
    RelevanceScore,
    SemanticDiff,
    SliceNode,
    SymbolHash,
)
from .speculative_models import (
    Delta,
    DeltaOperation,
    PatchType,
    RiskLevel,
    RiskReport,
    SpeculativePatch,
)

# SOTA Reasoning Engine (RFC-101, RFC-102)
from .reasoning_context import ReasoningContext, compute_input_hash
from .evidence_bundle import (
    Evidence,
    EvidenceBundle,
    EvidenceType,
    DecisionType,
)
from .boundary_models import (
    BoundaryType,
    HTTPMethod,
    BoundarySpec,
    BoundaryCandidate,
    BoundaryMatchResult,
)
from .llm_refactoring_models import (
    RefactoringType,
    VerificationLevel,
    RefactoringContext,
    LLMPatch,
    VerificationResult,
    LLMRefactoringResult,
    BoundaryIntegrityCheck,
    LLMGenerationConfig,
)
from .language_detector import (
    Language,
    FrameworkType,
    DetectorPattern,
    BoundaryDetectionContext,
    DetectedBoundary,
    IBoundaryDetector,
    ILanguageDetectorRegistry,
)

__all__ = [
    # Primary Effect Models
    "EffectType",
    "EffectSet",
    "EffectDiff",
    "EffectSeverity",
    # Primary Impact Models
    "ImpactLevel",
    "ImpactNode",
    "ImpactPath",
    "ImpactReport",
    "PropagationType",
    # Primary Speculative Models
    "SpeculativePatch",
    "RiskLevel",
    "RiskReport",
    "Delta",
    "DeltaOperation",
    "PatchType",
    # Legacy Models (for hash-based incremental rebuild)
    "SymbolHash",
    "HashBasedImpactLevel",  # NOT the same as ImpactLevel above
    "ImpactType",
    "SemanticDiff",
    "ChangeType",
    "DeltaLayer",
    "PatchMetadata",
    "ErrorSnapshot",
    "SliceResult",
    "SliceNode",
    "RelevanceScore",
    # SOTA Reasoning Engine
    "ReasoningContext",
    "compute_input_hash",
    "Evidence",
    "EvidenceBundle",
    "EvidenceType",
    "DecisionType",
    # SOTA Boundary Matching (RFC-101 Phase 1)
    "BoundaryType",
    "HTTPMethod",
    "BoundarySpec",
    "BoundaryCandidate",
    "BoundaryMatchResult",
    # SOTA LLM Refactoring (RFC-101 Phase 2)
    "RefactoringType",
    "VerificationLevel",
    "RefactoringContext",
    "LLMPatch",
    "VerificationResult",
    "LLMRefactoringResult",
    "BoundaryIntegrityCheck",
    "LLMGenerationConfig",
    # Cross-Language Support (RFC-101 Cross-Language)
    "Language",
    "FrameworkType",
    "DetectorPattern",
    "BoundaryDetectionContext",
    "DetectedBoundary",
    "IBoundaryDetector",
    "ILanguageDetectorRegistry",
]
