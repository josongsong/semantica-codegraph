"""Tests for IR Pipeline v3

Test coverage:
- Protocol (StageContext, PipelineStage)
- Orchestrator (sequential and parallel execution)
- Builder (profiles, customization, hooks)
- Pipeline (execution, metrics, errors)
- Stages (Cache, Structural, LSP, CrossFile, Retrieval, Provenance)
- Compatibility (LayeredIRBuilderAdapter)

Run tests:
    pytest packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/pipeline/tests/ -v
"""
