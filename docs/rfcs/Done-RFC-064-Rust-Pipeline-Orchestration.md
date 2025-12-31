# RFC-064: Rust DAG Pipeline Orchestration Architecture

## Status
- **Status**: Draft
- **Author**: Development Team
- **Created**: 2025-12-27
- **Updated**: 2025-12-27 (Revised for SQLite + DAG)

## Summary

This RFC proposes a **complete Rust implementation** of a DAG-based pipeline orchestration system, inspired by `semantica-task-engine`, replacing the Python `analysis_indexing` module with a high-performance, single-node job orchestration framework.

**Goal**: 5-10x performance improvement in pipeline throughput with production-grade reliability, using SQLite for persistence and explicit DAG stage resolution.

---

## Motivation

### Current Python Implementation Analysis

The Python `ParallelIndexingOrchestrator` (semantica-task-engine) demonstrates a successful pattern:

**Strengths** ✅:
- Phase-based DAG execution (L1∥L3 → L2 → L4)
- Cache-key dependency resolution
- Error classification (Transient/Permanent/Infrastructure)
- Zero-copy optimization (DictWrapper)

**Limitations** 🔴:
1. **Performance Bottlenecks**:
   - Python GIL limits true parallelism
   - Heavy dict/list allocations
   - AsyncIO overhead for simple coordination
   - Inefficient checkpoint serialization

2. **Reliability Concerns**:
   - In-memory caches (no persistence)
   - Manual error recovery
   - Limited observability
   - Race conditions in distributed mode

3. **Scalability Limits**:
   - Hard-coded phase dependencies
   - No dynamic DAG resolution
   - Manual parallelism control

### Expected Benefits of Rust Implementation

| Metric | Python (Current) | Rust (Target) | Improvement |
|--------|-----------------|---------------|-------------|
| **Pipeline Throughput** | 100 files/sec | 500-1000 files/sec | **5-10x** |
| **Memory Usage** | 2-4 GB | 500 MB - 1 GB | **2-4x less** |
| **Job Latency** | 5-10s | 1-2s | **5x faster** |
| **Error Recovery** | Manual retry | Automatic | ∞ |
| **DAG Resolution** | Hard-coded | Dynamic | ∞ |

---

## Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Job Orchestrator                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Job State Machine (SQLite)               │   │
│  │  QUEUED → RUNNING → COMPLETED/FAILED/CANCELLED   │   │
│  └──────────────────────────────────────────────────┘   │
│                          ↓                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │         DAG Pipeline Resolver                    │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  Stage Dependency Graph:                   │  │   │
│  │  │                                            │  │   │
│  │  │    L1 (IR)     L3 (Lexical)               │  │   │
│  │  │       ↓            (parallel)              │  │   │
│  │  │    L2 (Chunk)                              │  │   │
│  │  │       ↓                                    │  │   │
│  │  │    L4 (Vector) [optional]                 │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  │                                                  │   │
│  │  Features:                                       │   │
│  │  - Topological sort for execution order         │   │
│  │  - Cache-key dependency tracking                │   │
│  │  - Parallel execution of independent stages     │   │
│  │  - Early exit on failure                        │   │
│  └──────────────────────────────────────────────────┘   │
│                          ↓                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Pipeline Stages (Pluggable)              │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  L1: IR Generation ← RUST (Rayon)          │  │   │
│  │  │  L2: Chunking ← RUST (RFC-063)             │  │   │
│  │  │  L3: Lexical Index (Tantivy)               │  │   │
│  │  │  L4: Vector Index (Qdrant)                 │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
│                          ↓                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Checkpoint/Resume System                 │   │
│  │  - SQLite-backed cache persistence               │   │
│  │  - Stage-level checkpoints                       │   │
│  │  - Crash recovery (resume from last stage)       │   │
│  │  - Idempotent retries                            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Key Design Principles** (from semantica-task-engine):
1. **Phase-based parallelism**: Explicit dependency encoding (L1∥L3 → L2 → L4)
2. **Cache-key dependencies**: `ir_cache_key`, `chunk_cache_key` for data flow
3. **Early exit**: Fail fast on stage failure
4. **Zero-copy**: Rust ownership eliminates unnecessary copies
5. **Single-node**: No distributed locking (SQLite for persistence)

---

## Component Design

### 1. Job State Machine (SQLite)

#### States
```rust
pub enum JobState {
    Queued {
        queued_at: DateTime<Utc>,
        priority: i32,
    },
    Running {
        started_at: DateTime<Utc>,
        worker_id: String,
        current_stage: StageId,
        checkpoint_id: Option<CheckpointId>,
    },
    Completed {
        started_at: DateTime<Utc>,
        completed_at: DateTime<Utc>,
        duration_ms: u64,
        files_processed: usize,
        result: PipelineResult,
    },
    Failed {
        started_at: DateTime<Utc>,
        failed_at: DateTime<Utc>,
        error: String,
        error_category: ErrorCategory,
        failed_stage: StageId,
        retry_count: u32,
        next_retry_at: Option<DateTime<Utc>>,
    },
    Cancelled {
        cancelled_at: DateTime<Utc>,
        reason: String,
    },
}

pub enum ErrorCategory {
    Transient,       // Retry automatically (e.g., timeout)
    Permanent,       // Don't retry (e.g., invalid input)
    Infrastructure,  // Alert ops (e.g., OOM)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum StageId {
    L1_IR,
    L2_Chunk,
    L3_Lexical,
    L4_Vector,
}
```

#### SQLite Schema
```sql
-- Job state table
CREATE TABLE indexing_jobs (
    id TEXT PRIMARY KEY,  -- UUID as TEXT
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    priority INTEGER DEFAULT 0,

    -- Timestamps
    queued_at TEXT NOT NULL,  -- ISO 8601
    started_at TEXT,
    completed_at TEXT,
    failed_at TEXT,
    cancelled_at TEXT,

    -- Running state
    worker_id TEXT,
    current_stage TEXT,  -- 'L1_IR', 'L2_Chunk', etc.
    checkpoint_id TEXT REFERENCES checkpoints(id),

    -- Completion state
    duration_ms INTEGER,
    files_processed INTEGER,
    result_json TEXT,  -- PipelineResult as JSON

    -- Failure state
    error TEXT,
    error_category TEXT CHECK (error_category IN ('transient', 'permanent', 'infrastructure')),
    failed_stage TEXT,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TEXT,  -- ISO 8601

    -- Metadata
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(repo_id, snapshot_id)
);

CREATE INDEX idx_jobs_state_priority ON indexing_jobs(state, priority DESC, queued_at);
CREATE INDEX idx_jobs_repo_state ON indexing_jobs(repo_id, state);
CREATE INDEX idx_jobs_retry ON indexing_jobs(state, next_retry_at) WHERE state = 'failed';

-- Checkpoint table (stage-level caches)
CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES indexing_jobs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    cache_key TEXT NOT NULL,  -- e.g., "ir:repo_id:snapshot_id"
    cache_data BLOB,          -- Serialized stage output (bincode)
    created_at TEXT NOT NULL,

    UNIQUE(job_id, stage)
);

CREATE INDEX idx_checkpoints_job ON checkpoints(job_id);
CREATE INDEX idx_checkpoints_cache_key ON checkpoints(cache_key);

-- Pipeline stage metadata
CREATE TABLE pipeline_stages (
    id TEXT PRIMARY KEY,  -- 'L1_IR', 'L2_Chunk', etc.
    name TEXT NOT NULL,
    dependencies TEXT NOT NULL,  -- JSON array: ["L1_IR"] for L2
    parallel_group INTEGER,      -- NULL if sequential, 0 for first parallel group
    optional BOOLEAN DEFAULT FALSE,
    timeout_ms INTEGER,

    UNIQUE(name)
);

-- Insert default pipeline stages
INSERT INTO pipeline_stages (id, name, dependencies, parallel_group, optional, timeout_ms) VALUES
('L1_IR',      'IR Generation',     '[]',          0, FALSE, 300000),
('L3_Lexical', 'Lexical Indexing',  '[]',          0, FALSE, 300000),
('L2_Chunk',   'Chunk Building',    '["L1_IR"]',   NULL, FALSE, 180000),
('L4_Vector',  'Vector Indexing',   '["L2_Chunk"]', NULL, TRUE, 600000);
```

**Key SQLite Optimizations**:
- WAL mode for concurrent reads: `PRAGMA journal_mode=WAL;`
- Busy timeout for write contention: `PRAGMA busy_timeout=5000;`
- Foreign keys enabled: `PRAGMA foreign_keys=ON;`

---

### 2. DAG Pipeline Resolver

#### Dependency Graph Definition
```rust
use std::collections::{HashMap, HashSet};

pub struct PipelineDAG {
    stages: HashMap<StageId, StageNode>,
    execution_order: Vec<Vec<StageId>>,  // Vec of parallel groups
}

pub struct StageNode {
    id: StageId,
    name: &'static str,
    dependencies: Vec<StageId>,
    handler: Arc<dyn StageHandler>,
    optional: bool,
    timeout: Duration,
}

impl PipelineDAG {
    /// Build DAG from database config
    pub async fn from_db(db: &SqlitePool) -> Result<Self> {
        let stages_raw = sqlx::query!(
            "SELECT id, name, dependencies, parallel_group, optional, timeout_ms
             FROM pipeline_stages ORDER BY parallel_group NULLS LAST"
        )
        .fetch_all(db)
        .await?;

        let mut stages = HashMap::new();
        for row in stages_raw {
            let id = StageId::from_str(&row.id)?;
            let dependencies: Vec<StageId> = serde_json::from_str(&row.dependencies)?;

            stages.insert(id, StageNode {
                id,
                name: row.name.leak(),  // Static lifetime
                dependencies,
                handler: Self::get_handler(id),
                optional: row.optional,
                timeout: Duration::from_millis(row.timeout_ms as u64),
            });
        }

        // Topological sort to get execution order
        let execution_order = Self::topological_sort(&stages)?;

        Ok(PipelineDAG { stages, execution_order })
    }

    /// Topological sort with parallel group detection
    fn topological_sort(
        stages: &HashMap<StageId, StageNode>
    ) -> Result<Vec<Vec<StageId>>> {
        let mut in_degree: HashMap<StageId, usize> = stages
            .keys()
            .map(|&id| (id, 0))
            .collect();

        // Calculate in-degrees
        for stage in stages.values() {
            for &dep in &stage.dependencies {
                *in_degree.get_mut(&dep).unwrap() += 1;
            }
        }

        let mut result = Vec::new();
        let mut processed = HashSet::new();

        while processed.len() < stages.len() {
            // Find all stages with in-degree 0 (can run in parallel)
            let ready: Vec<StageId> = in_degree
                .iter()
                .filter(|(id, &degree)| degree == 0 && !processed.contains(id))
                .map(|(&id, _)| id)
                .collect();

            if ready.is_empty() {
                return Err(anyhow!("Cycle detected in DAG"));
            }

            result.push(ready.clone());

            // Mark as processed and decrement dependents
            for &stage_id in &ready {
                processed.insert(stage_id);
                in_degree.remove(&stage_id);

                // Decrement dependents
                for dependent in stages.values() {
                    if dependent.dependencies.contains(&stage_id) {
                        *in_degree.get_mut(&dependent.id).unwrap() -= 1;
                    }
                }
            }
        }

        Ok(result)
    }

    /// Get execution order (for logging)
    pub fn execution_plan(&self) -> String {
        self.execution_order
            .iter()
            .enumerate()
            .map(|(i, group)| {
                let stage_names: Vec<_> = group
                    .iter()
                    .map(|id| self.stages[id].name)
                    .collect();

                if group.len() > 1 {
                    format!("Phase {}: {} (parallel)", i + 1, stage_names.join(" ∥ "))
                } else {
                    format!("Phase {}: {}", i + 1, stage_names[0])
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
    }
}
```

#### Cache-Key Dependency System (from semantica-task-engine)
```rust
pub struct CacheKeyManager {
    repo_id: String,
    snapshot_id: String,
}

impl CacheKeyManager {
    pub fn ir_key(&self) -> String {
        format!("ir:{}:{}", self.repo_id, self.snapshot_id)
    }

    pub fn chunk_key(&self) -> String {
        format!("chunks:{}:{}", self.repo_id, self.snapshot_id)
    }

    pub fn lexical_key(&self) -> String {
        format!("lexical:{}:{}", self.repo_id, self.snapshot_id)
    }

    pub fn vector_key(&self) -> String {
        format!("vector:{}:{}", self.repo_id, self.snapshot_id)
    }

    /// Get cache key for a stage
    pub fn key_for_stage(&self, stage: StageId) -> String {
        match stage {
            StageId::L1_IR => self.ir_key(),
            StageId::L2_Chunk => self.chunk_key(),
            StageId::L3_Lexical => self.lexical_key(),
            StageId::L4_Vector => self.vector_key(),
        }
    }
}
```

---

### 3. Pipeline Stage Trait

```rust
#[async_trait]
pub trait StageHandler: Send + Sync {
    /// Stage identifier
    fn stage_id(&self) -> StageId;

    /// Can this stage be skipped? (e.g., cache hit)
    async fn can_skip(&self, ctx: &StageContext) -> bool {
        false
    }

    /// Execute stage
    async fn execute(
        &self,
        input: StageInput,
        ctx: &mut StageContext,
    ) -> Result<StageOutput>;

    /// Get required cache keys from dependencies
    fn required_cache_keys(&self, ctx: &StageContext) -> Vec<String> {
        vec![]
    }

    /// Output cache key
    fn output_cache_key(&self, ctx: &StageContext) -> String;
}

pub struct StageInput {
    pub files: Vec<PathBuf>,
    pub cache: HashMap<String, Vec<u8>>,  // Dependency outputs
    pub config: StageConfig,
}

pub struct StageOutput {
    pub cache_data: Vec<u8>,  // Serialized output (bincode)
    pub metrics: StageMetrics,
}

pub struct StageContext {
    pub job_id: Uuid,
    pub repo_id: String,
    pub snapshot_id: String,
    pub db: SqlitePool,
    pub cache_keys: CacheKeyManager,
}

#[derive(Default)]
pub struct StageMetrics {
    pub files_processed: usize,
    pub nodes_created: usize,
    pub chunks_created: usize,
    pub duration_ms: u64,
    pub errors: Vec<String>,
}
```

---

### 4. Checkpoint/Resume System

```rust
pub struct CheckpointManager {
    db: SqlitePool,
}

impl CheckpointManager {
    /// Save stage output to checkpoint
    pub async fn save_checkpoint(
        &self,
        job_id: Uuid,
        stage: StageId,
        cache_key: String,
        data: Vec<u8>,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO checkpoints (id, job_id, stage, cache_key, cache_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, stage) DO UPDATE
            SET cache_data = excluded.cache_data, created_at = excluded.created_at
            "#,
            Uuid::new_v4().to_string(),
            job_id.to_string(),
            stage.to_string(),
            cache_key,
            data,
            Utc::now().to_rfc3339(),
        )
        .execute(&self.db)
        .await?;

        Ok(())
    }

    /// Load checkpoint by cache key
    pub async fn load_checkpoint(
        &self,
        cache_key: &str,
    ) -> Result<Option<Vec<u8>>> {
        let row = sqlx::query!(
            "SELECT cache_data FROM checkpoints WHERE cache_key = ? ORDER BY created_at DESC LIMIT 1",
            cache_key
        )
        .fetch_optional(&self.db)
        .await?;

        Ok(row.map(|r| r.cache_data))
    }

    /// Get completed stages for a job
    pub async fn completed_stages(&self, job_id: Uuid) -> Result<HashSet<StageId>> {
        let rows = sqlx::query!(
            "SELECT stage FROM checkpoints WHERE job_id = ?",
            job_id.to_string()
        )
        .fetch_all(&self.db)
        .await?;

        rows.into_iter()
            .map(|r| StageId::from_str(&r.stage))
            .collect()
    }
}
```

---

### 5. Pipeline Orchestrator (Inspired by ParallelIndexingOrchestrator)

```rust
pub struct PipelineOrchestrator {
    dag: Arc<PipelineDAG>,
    db: SqlitePool,
    checkpoint_mgr: Arc<CheckpointManager>,
}

impl PipelineOrchestrator {
    pub async fn execute_job(&self, job_id: Uuid) -> Result<PipelineResult> {
        // 1. Load job
        let mut job = self.load_job(job_id).await?;

        // 2. Transition: QUEUED → RUNNING
        self.update_job_state(
            job_id,
            JobState::Running {
                started_at: Utc::now(),
                worker_id: self.worker_id(),
                current_stage: StageId::L1_IR,
                checkpoint_id: None,
            },
        )
        .await?;

        // 3. Get completed stages (for resume)
        let completed = self.checkpoint_mgr.completed_stages(job_id).await?;

        // 4. Execute DAG phases
        let result = self.run_dag(job_id, &completed).await;

        // 5. Update final state
        match result {
            Ok(ref output) => {
                self.update_job_state(
                    job_id,
                    JobState::Completed {
                        started_at: job.started_at.unwrap(),
                        completed_at: Utc::now(),
                        duration_ms: output.duration_ms,
                        files_processed: output.files_processed,
                        result: output.clone(),
                    },
                )
                .await?;
            }
            Err(ref e) => {
                self.update_job_state(
                    job_id,
                    JobState::Failed {
                        started_at: job.started_at.unwrap(),
                        failed_at: Utc::now(),
                        error: e.to_string(),
                        error_category: self.classify_error(e),
                        failed_stage: self.current_stage,
                        retry_count: job.retry_count + 1,
                        next_retry_at: self.calculate_retry_time(job.retry_count),
                    },
                )
                .await?;
            }
        }

        result
    }

    /// Execute DAG with parallel phases (like ParallelIndexingOrchestrator)
    async fn run_dag(
        &self,
        job_id: Uuid,
        completed: &HashSet<StageId>,
    ) -> Result<PipelineResult> {
        let mut ctx = StageContext {
            job_id,
            repo_id: self.repo_id.clone(),
            snapshot_id: self.snapshot_id.clone(),
            db: self.db.clone(),
            cache_keys: CacheKeyManager::new(&self.repo_id, &self.snapshot_id),
        };

        let mut overall_result = PipelineResult::default();

        // Execute each phase in order
        for (phase_idx, parallel_group) in self.dag.execution_order.iter().enumerate() {
            log::info!(
                "Job {}: Starting phase {} - {} stages in parallel",
                job_id,
                phase_idx + 1,
                parallel_group.len()
            );

            // Skip completed stages
            let to_execute: Vec<_> = parallel_group
                .iter()
                .filter(|id| !completed.contains(id))
                .collect();

            if to_execute.is_empty() {
                log::info!("Job {}: Phase {} already completed, skipping", job_id, phase_idx + 1);
                continue;
            }

            // Execute stages in parallel using tokio::spawn
            let mut tasks = Vec::new();
            for &&stage_id in &to_execute {
                let stage = self.dag.stages[&stage_id].clone();
                let mut stage_ctx = ctx.clone();

                tasks.push(tokio::spawn(async move {
                    Self::execute_stage(stage, &mut stage_ctx).await
                }));
            }

            // Wait for all parallel tasks (like asyncio.gather)
            let results = futures::future::try_join_all(tasks).await?;

            // Check for failures (early exit like semantica-task-engine)
            for (i, result) in results.iter().enumerate() {
                let stage_id = to_execute[i];

                match result {
                    Ok(output) => {
                        // Save checkpoint
                        let cache_key = ctx.cache_keys.key_for_stage(*stage_id);
                        self.checkpoint_mgr
                            .save_checkpoint(job_id, *stage_id, cache_key, output.cache_data.clone())
                            .await?;

                        // Merge metrics
                        overall_result.merge(&output.metrics);
                    }
                    Err(e) => {
                        log::error!("Job {}: Stage {:?} failed: {}", job_id, stage_id, e);
                        return Err(anyhow!("Stage {:?} failed: {}", stage_id, e));
                    }
                }
            }
        }

        Ok(overall_result)
    }

    /// Execute a single stage
    async fn execute_stage(
        stage: StageNode,
        ctx: &mut StageContext,
    ) -> Result<StageOutput> {
        log::info!("Executing stage: {}", stage.name);

        // Load dependency cache data
        let mut cache = HashMap::new();
        for cache_key in stage.handler.required_cache_keys(ctx) {
            if let Some(data) = ctx.checkpoint_mgr.load_checkpoint(&cache_key).await? {
                cache.insert(cache_key, data);
            } else {
                return Err(anyhow!("Missing required cache: {}", cache_key));
            }
        }

        // Build input
        let input = StageInput {
            files: self.enumerate_files()?,
            cache,
            config: StageConfig::default(),
        };

        // Execute with timeout
        let result = tokio::time::timeout(
            stage.timeout,
            stage.handler.execute(input, ctx),
        )
        .await??;

        Ok(result)
    }

    /// Classify error for retry logic (from semantica-task-engine)
    fn classify_error(&self, error: &anyhow::Error) -> ErrorCategory {
        let error_str = error.to_string();

        if error_str.contains("timeout") || error_str.contains("connection") {
            ErrorCategory::Transient
        } else if error_str.contains("OOM") || error_str.contains("out of memory") {
            ErrorCategory::Infrastructure
        } else if error_str.contains("parse error") || error_str.contains("invalid") {
            ErrorCategory::Permanent
        } else {
            ErrorCategory::Transient  // Default to retry
        }
    }

    /// Calculate exponential backoff retry time
    fn calculate_retry_time(&self, retry_count: u32) -> Option<DateTime<Utc>> {
        if retry_count >= 3 {
            return None;  // Max retries exceeded
        }

        let backoff_secs = 2u64.pow(retry_count);  // 2s, 4s, 8s
        Some(Utc::now() + chrono::Duration::seconds(backoff_secs as i64))
    }
}

#[derive(Default, Clone)]
pub struct PipelineResult {
    pub files_processed: usize,
    pub nodes_created: usize,
    pub chunks_created: usize,
    pub duration_ms: u64,
    pub errors: Vec<String>,
}

impl PipelineResult {
    pub fn merge(&mut self, other: &StageMetrics) {
        self.files_processed += other.files_processed;
        self.nodes_created += other.nodes_created;
        self.chunks_created += other.chunks_created;
        self.duration_ms += other.duration_ms;
        self.errors.extend(other.errors.clone());
    }
}
```

---

## Stage Implementations

### L1: IR Generation Stage (Rust)

```rust
pub struct IRStage {
    ir_builder: Arc<LayeredIRBuilder>,
}

#[async_trait]
impl StageHandler for IRStage {
    fn stage_id(&self) -> StageId {
        StageId::L1_IR
    }

    async fn execute(&self, input: StageInput, ctx: &mut StageContext) -> Result<StageOutput> {
        let start = Instant::now();

        // Use Rayon for parallel file processing (like Rust LayeredOrchestrator)
        let results: Vec<_> = input.files
            .par_iter()
            .map(|file_path| {
                let source = std::fs::read_to_string(file_path)?;
                self.ir_builder.process_file(file_path.to_str().unwrap(), &source)
            })
            .collect::<Result<Vec<_>>>()?;

        // Aggregate all IR nodes
        let all_nodes: Vec<IRNode> = results.into_iter().flatten().collect();

        // Serialize for cache
        let cache_data = bincode::serialize(&all_nodes)?;

        Ok(StageOutput {
            cache_data,
            metrics: StageMetrics {
                files_processed: input.files.len(),
                nodes_created: all_nodes.len(),
                duration_ms: start.elapsed().as_millis() as u64,
                ..Default::default()
            },
        })
    }

    fn output_cache_key(&self, ctx: &StageContext) -> String {
        ctx.cache_keys.ir_key()
    }
}
```

### L2: Chunk Building Stage (Rust)

```rust
pub struct ChunkStage {
    chunk_builder: Arc<ChunkBuilder>,
}

#[async_trait]
impl StageHandler for ChunkStage {
    fn stage_id(&self) -> StageId {
        StageId::L2_Chunk
    }

    fn required_cache_keys(&self, ctx: &StageContext) -> Vec<String> {
        vec![ctx.cache_keys.ir_key()]
    }

    async fn execute(&self, input: StageInput, ctx: &mut StageContext) -> Result<StageOutput> {
        let start = Instant::now();

        // Load IR from cache
        let ir_data = input.cache
            .get(&ctx.cache_keys.ir_key())
            .ok_or_else(|| anyhow!("Missing IR cache"))?;

        let ir_nodes: Vec<IRNode> = bincode::deserialize(ir_data)?;

        // Build chunks (RFC-063 implementation)
        let chunks = self.chunk_builder.build_chunks(&ir_nodes)?;

        // Serialize
        let cache_data = bincode::serialize(&chunks)?;

        Ok(StageOutput {
            cache_data,
            metrics: StageMetrics {
                files_processed: input.files.len(),
                chunks_created: chunks.len(),
                duration_ms: start.elapsed().as_millis() as u64,
                ..Default::default()
            },
        })
    }

    fn output_cache_key(&self, ctx: &StageContext) -> String {
        ctx.cache_keys.chunk_key()
    }
}
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

**Goal**: Job state machine + DAG resolver

- [x] Create `codegraph-orchestration` crate
- [ ] Implement `JobStateMachine` with SQLite
- [ ] Implement `PipelineDAG` with topological sort
- [ ] Implement `CacheKeyManager`
- [ ] Setup SQLite schema and migrations
- [ ] **Integration Tests**:
  - Job state transitions (QUEUED → RUNNING → COMPLETED)
  - DAG topological sort (detect cycles)
  - SQLite concurrent access (WAL mode)
  - Cache key generation

### Phase 2: Checkpointing (Week 3)

**Goal**: SQLite-backed cache system

- [ ] Implement `CheckpointManager`
- [ ] Implement checkpoint save/load with bincode
- [ ] Add checkpoint pruning (delete old checkpoints on success)
- [ ] **Integration Tests**:
  - Save checkpoint mid-pipeline
  - Resume from checkpoint (skip completed stages)
  - Cache miss handling (PERMANENT error)
  - Checkpoint cleanup on job completion

### Phase 3: Pipeline Stages (Week 4-6)

**Goal**: Implement core stages

- [ ] Define `StageHandler` trait
- [ ] Implement `IRStage` (Rust Rayon parallelism)
- [ ] Implement `ChunkStage` (RFC-063)
- [ ] Implement `LexicalStage` (Tantivy wrapper)
- [ ] Implement `VectorStage` (Qdrant wrapper)
- [ ] **Integration Tests**:
  - L1 IR stage (parallel processing with Rayon)
  - L2 Chunk stage (cache dependency)
  - L3 Lexical stage (parallel with L1)
  - L4 Vector stage (optional, skippable)
  - End-to-end pipeline (small repo, 10 files)

### Phase 4: Orchestration (Week 7-8)

**Goal**: Complete orchestrator

- [ ] Implement `PipelineOrchestrator`
- [ ] Implement parallel phase execution (tokio::spawn + join_all)
- [ ] Add retry logic (exponential backoff)
- [ ] Add error classification (Transient/Permanent/Infrastructure)
- [ ] **Integration Tests**:
  - Full pipeline execution (L1∥L3 → L2 → L4)
  - Early exit on failure
  - Retry logic (3 attempts max)
  - Concurrent job handling (multiple repos)
  - Crash recovery (resume from last stage)

### Phase 5: Performance (Week 9-10)

**Goal**: Optimization & benchmarking

- [ ] Profile with `flamegraph`
- [ ] Optimize hot paths (bincode serialization, SQLite queries)
- [ ] Add Criterion benchmarks
- [ ] Compare vs Python baseline (ParallelIndexingOrchestrator)
- [ ] **Benchmarks**:
  - Job throughput (jobs/sec)
  - Pipeline latency (small/medium/large repos)
  - Memory usage (RSS)
  - SQLite query performance (checkpoint load/save)
  - DAG resolution time

---

## Testing Strategy

### Unit Tests
```rust
#[cfg(test)]
mod tests {
    #[test]
    fn test_dag_topological_sort_simple() {
        let dag = PipelineDAG::new(vec![
            (StageId::L1_IR, vec![]),
            (StageId::L2_Chunk, vec![StageId::L1_IR]),
        ]);

        let order = dag.execution_order;
        assert_eq!(order.len(), 2);
        assert_eq!(order[0], vec![StageId::L1_IR]);
        assert_eq!(order[1], vec![StageId::L2_Chunk]);
    }

    #[test]
    fn test_dag_parallel_detection() {
        let dag = PipelineDAG::new(vec![
            (StageId::L1_IR, vec![]),
            (StageId::L3_Lexical, vec![]),
        ]);

        let order = dag.execution_order;
        assert_eq!(order.len(), 1);
        assert_eq!(order[0].len(), 2);  // Both in same parallel group
    }

    #[test]
    fn test_cache_key_generation() {
        let mgr = CacheKeyManager::new("repo123", "snap456");
        assert_eq!(mgr.ir_key(), "ir:repo123:snap456");
        assert_eq!(mgr.chunk_key(), "chunks:repo123:snap456");
    }
}
```

### Integration Tests
```rust
// tests/integration/test_orchestrator.rs
#[tokio::test]
async fn test_full_pipeline_execution() {
    let db = setup_test_db().await;
    let orchestrator = PipelineOrchestrator::new(db).await.unwrap();

    // Create job
    let job_id = orchestrator.create_job("test-repo", "snapshot-1").await.unwrap();

    // Execute
    let result = orchestrator.execute_job(job_id).await.unwrap();

    // Verify all stages completed
    assert!(result.files_processed > 0);
    assert!(result.nodes_created > 0);
    assert!(result.chunks_created > 0);

    // Verify job state
    let job = orchestrator.get_job(job_id).await.unwrap();
    assert!(matches!(job.state, JobState::Completed { .. }));
}

#[tokio::test]
async fn test_crash_recovery_resumes_from_checkpoint() {
    let db = setup_test_db().await;
    let orch1 = PipelineOrchestrator::new(db.clone()).await.unwrap();

    // Start job and simulate crash after L1
    let job_id = orch1.create_job("test-repo", "snapshot-1").await.unwrap();

    // Execute L1 only
    orch1.execute_stage(job_id, StageId::L1_IR).await.unwrap();
    drop(orch1);  // Simulate crash

    // Resume with new orchestrator
    let orch2 = PipelineOrchestrator::new(db).await.unwrap();
    let result = orch2.execute_job(job_id).await.unwrap();

    // Should skip L1, execute L2-L4
    assert!(result.files_processed > 0);
}

#[tokio::test]
async fn test_parallel_phase_execution() {
    let db = setup_test_db().await;
    let orchestrator = PipelineOrchestrator::new(db).await.unwrap();

    let job_id = orchestrator.create_job("test-repo", "snapshot-1").await.unwrap();

    // Execute and verify L1 + L3 run in parallel
    let start = Instant::now();
    let result = orchestrator.execute_job(job_id).await.unwrap();
    let duration = start.elapsed();

    // L1 and L3 should run concurrently, not sequentially
    // If sequential: ~600ms, if parallel: ~300ms
    assert!(duration.as_millis() < 400);
}
```

---

## Performance Targets

| Metric | Python (Baseline) | Rust (Target) | Test Method |
|--------|------------------|---------------|-------------|
| Job creation | 100ms | 10ms | Criterion benchmark |
| DAG resolution | 50ms | 1ms | Criterion benchmark |
| Pipeline latency (100 files) | 10s | 2s | Integration test |
| Throughput | 100 files/sec | 500 files/sec | Stress test |
| Memory (1000 files) | 2 GB | 500 MB | RSS measurement |
| Checkpoint save | 200ms | 20ms | Criterion benchmark |
| Crash recovery | Manual | <1s | Integration test |

---

## Key Differences from Original RFC

| Aspect | Original (PostgreSQL + Redis) | Revised (SQLite + DAG) |
|--------|------------------------------|------------------------|
| **State Store** | PostgreSQL (distributed) | SQLite (single-node) |
| **Locking** | Redis distributed locks | None (single-process) |
| **DAG Resolution** | Hard-coded stages | Dynamic topological sort |
| **Parallelism** | Worker-based | Phase-based (tokio::spawn) |
| **Checkpoints** | PostgreSQL table | SQLite with bincode |
| **Cache** | In-memory (Redis) | SQLite BLOB |
| **Complexity** | High (distributed) | Low (single-node) |
| **Inspiration** | General distributed systems | semantica-task-engine |

---

## Risks & Mitigation

### Risk 1: SQLite Write Contention
**Impact**: Slow checkpoint saves under high concurrency
**Mitigation**: WAL mode + batched writes + busy_timeout=5000ms

### Risk 2: Large Checkpoint Bloat
**Impact**: Slow resume
**Mitigation**: Bincode compression + delta encoding for incremental saves

### Risk 3: DAG Complexity
**Impact**: Hard to debug failures
**Mitigation**: Extensive logging + execution plan visualization

---

## Future Enhancements

### Multi-Node Coordination (if needed)
```rust
// Use PostgreSQL instead of SQLite
// Add distributed locking with pg_advisory_lock
pub trait DistributedOrchestrator {
    async fn acquire_job(&self) -> Option<JobId>;
    async fn heartbeat(&self, job_id: JobId) -> Result<()>;
}
```

### Dynamic Stage Registration
```rust
// Plugin-based stages
pub trait StagePlugin {
    fn register(&self, dag: &mut PipelineDAG) -> Result<()>;
}
```

---

## Conclusion

This RFC proposes a **SOTA-level Rust DAG orchestration system** inspired by `semantica-task-engine`, featuring:

✅ **5-10x performance** vs Python
✅ **Automatic crash recovery** (SQLite checkpoints)
✅ **Dynamic DAG resolution** (topological sort)
✅ **Phase-based parallelism** (L1∥L3 → L2 → L4)
✅ **Cache-key dependencies** (ir_cache_key, chunk_cache_key)
✅ **Comprehensive testing** (unit + integration + benchmarks)
✅ **Single-node simplicity** (no Redis, no distributed complexity)

**Timeline**: 10 weeks
**Risk**: Low (proven pattern from semantica-task-engine)
**Impact**: Foundation for all future Rust optimizations
