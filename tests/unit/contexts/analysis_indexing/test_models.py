"""
Analysis Indexing Models Tests

Test Coverage:
- Enums: Layer, IndexingMode, JobStatus, TriggerType
- Models: IndexJob, MODE_LAYER_CONFIG
- Edge cases: Job lifecycle, checkpoints
"""

from datetime import datetime

import pytest

from codegraph_engine.analysis_indexing.infrastructure.models.job import (
    IndexJob,
    IndexJobCheckpoint,
    JobStatus,
    TriggerType,
)
from codegraph_engine.analysis_indexing.infrastructure.models.mode import (
    MODE_LAYER_CONFIG,
    IndexingMode,
    Layer,
    LayerThreshold,
    ModeScopeLimit,
)


class TestLayer:
    """Layer enum tests"""

    def test_all_layers_defined(self):
        """All layers L0-L4 exist"""
        assert Layer.L0.value == "l0"
        assert Layer.L1.value == "l1"
        assert Layer.L2.value == "l2"
        assert Layer.L3.value == "l3"
        assert Layer.L4.value == "l4"

    def test_l3_summary_exists(self):
        """L3 summary layer exists"""
        assert Layer.L3_SUMMARY.value == "l3_summary"


class TestIndexingMode:
    """IndexingMode enum tests"""

    def test_all_modes_defined(self):
        """All indexing modes exist"""
        assert IndexingMode.FAST.value == "fast"
        assert IndexingMode.BALANCED.value == "balanced"
        assert IndexingMode.DEEP.value == "deep"
        assert IndexingMode.BOOTSTRAP.value == "bootstrap"
        assert IndexingMode.REPAIR.value == "repair"


class TestModeLayerConfig:
    """Mode to layer mapping tests"""

    def test_fast_mode_layers(self):
        """Fast mode uses L1, L2"""
        layers = MODE_LAYER_CONFIG[IndexingMode.FAST]
        assert Layer.L1 in layers
        assert Layer.L2 in layers
        assert Layer.L3 not in layers

    def test_balanced_mode_layers(self):
        """Balanced mode uses L1, L2, L3"""
        layers = MODE_LAYER_CONFIG[IndexingMode.BALANCED]
        assert Layer.L1 in layers
        assert Layer.L2 in layers
        assert Layer.L3 in layers

    def test_deep_mode_layers(self):
        """Deep mode uses L1, L2, L3, L4"""
        layers = MODE_LAYER_CONFIG[IndexingMode.DEEP]
        assert Layer.L4 in layers

    def test_bootstrap_mode_uses_l3_summary(self):
        """Bootstrap mode uses L3_SUMMARY"""
        layers = MODE_LAYER_CONFIG[IndexingMode.BOOTSTRAP]
        assert Layer.L3_SUMMARY in layers

    def test_repair_mode_is_dynamic(self):
        """Repair mode has empty config (dynamic)"""
        layers = MODE_LAYER_CONFIG[IndexingMode.REPAIR]
        assert len(layers) == 0


class TestLayerThreshold:
    """LayerThreshold constants tests"""

    def test_l3_thresholds(self):
        """L3 thresholds defined"""
        assert LayerThreshold.L3_CFG_MAX_NODES == 100
        assert LayerThreshold.L3_DFG_SCOPE == "single_function"

    def test_l4_thresholds(self):
        """L4 thresholds defined"""
        assert LayerThreshold.L4_CFG_UNLIMITED is True
        assert LayerThreshold.L4_DFG_SCOPE == "cross_function"


class TestJobStatus:
    """JobStatus enum tests"""

    def test_all_statuses_defined(self):
        """All job statuses exist"""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_special_statuses(self):
        """Special status values"""
        assert JobStatus.DEDUPED.value == "deduped"
        assert JobStatus.SUPERSEDED.value == "superseded"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestTriggerType:
    """TriggerType enum tests"""

    def test_all_triggers_defined(self):
        """All trigger types exist"""
        assert TriggerType.GIT_COMMIT.value == "git_commit"
        assert TriggerType.FS_EVENT.value == "fs_event"
        assert TriggerType.MANUAL.value == "manual"


class TestIndexJobCheckpoint:
    """IndexJobCheckpoint enum tests"""

    def test_checkpoint_order(self):
        """Checkpoints in execution order"""
        checkpoints = list(IndexJobCheckpoint)
        names = [c.name for c in checkpoints]
        assert names.index("STARTED") < names.index("COMPLETED")


class TestIndexJob:
    """IndexJob model tests"""

    def test_create_default_job(self):
        """Create job with defaults"""
        job = IndexJob()
        assert job.id is not None
        assert job.status == JobStatus.QUEUED
        assert job.trigger_type == TriggerType.MANUAL
        assert isinstance(job.created_at, datetime)

    def test_create_job_with_params(self):
        """Create job with parameters"""
        job = IndexJob(
            repo_id="test-repo",
            snapshot_id="abc123",
            trigger_type=TriggerType.GIT_COMMIT,
        )
        assert job.repo_id == "test-repo"
        assert job.snapshot_id == "abc123"
        assert job.trigger_type == TriggerType.GIT_COMMIT

    def test_job_with_scope_paths(self):
        """Job with specific scope paths"""
        job = IndexJob(
            repo_id="repo",
            snapshot_id="snap",
            scope_paths=["src/main.py", "src/utils.py"],
        )
        assert len(job.scope_paths) == 2

    def test_job_unique_id(self):
        """Each job has unique ID"""
        job1 = IndexJob()
        job2 = IndexJob()
        assert job1.id != job2.id


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_scope_paths(self):
        """Empty scope paths means full repo"""
        job = IndexJob(scope_paths=[])
        assert job.scope_paths == []

    def test_none_scope_paths(self):
        """None scope paths means full repo"""
        job = IndexJob(scope_paths=None)
        assert job.scope_paths is None

    def test_job_status_transition(self):
        """Job status can be changed"""
        job = IndexJob()
        assert job.status == JobStatus.QUEUED
        job.status = JobStatus.RUNNING
        assert job.status == JobStatus.RUNNING

    def test_job_with_trigger_metadata(self):
        """Job with trigger metadata"""
        job = IndexJob(
            trigger_metadata={"commit_sha": "abc123", "author": "user@example.com"},
        )
        assert job.trigger_metadata["commit_sha"] == "abc123"

    def test_mode_scope_limits(self):
        """Mode scope limits defined"""
        assert ModeScopeLimit.BALANCED_MAX_NEIGHBORS == 100
        assert ModeScopeLimit.DEEP_SUBSET_MAX_FILES == 500
