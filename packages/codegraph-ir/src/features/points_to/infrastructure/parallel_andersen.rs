//! Parallel Andersen's Points-to Analysis Solver
//!
//! Parallel implementation using Rayon for multi-threaded constraint solving.
//!
//! # Implementation Details
//! - **Worklist**: Mutex-based queue (NOT lock-free)
//! - **Points-to sets**: RwLock-protected SparseBitmap
//! - **Parallelization**: Rayon parallel iterators for batch processing
//! - **Termination**: Polling-based (NOT work-stealing)
//!
//! # Performance Characteristics
//! - Moderate speedup on multi-core systems (depends on contention)
//! - Best for constraint sets > 1000 (parallel overhead otherwise)
//! - May have lock contention on high-core-count systems
//!
//! # Limitations
//! - Not truly lock-free (uses Mutex for worklist)
//! - No work-stealing (uses busy-wait polling)
//! - Consider using sequential solver for small constraint sets
//!
//! # References
//! - Hardekopf & Lin "Semi-sparse Flow-Sensitive Pointer Analysis" (POPL 2009)
//! - Mendez-Lojo et al. "Parallel Inclusion-based Points-to Analysis" (OOPSLA 2010)

use super::andersen_solver::{AndersenConfig, AndersenResult, AndersenStats};
use super::sparse_bitmap::SparseBitmap;
use super::scc_detector::{tarjan_scc, SCCResult};
use crate::features::points_to::domain::{
    abstract_location::{AbstractLocation, LocationFactory, LocationId},
    constraint::{Constraint, ConstraintKind, ConstraintSet, VarId},
    points_to_graph::PointsToGraph,
};
use std::sync::Mutex;
use std::collections::VecDeque;

/// Thread-safe queue using Mutex (simpler alternative to crossbeam::SegQueue)
///
/// Note: This is NOT lock-free. Each push/pop acquires a mutex lock.
/// For truly lock-free implementation, consider using crossbeam::SegQueue.
struct SegQueue<T> {
    inner: Mutex<VecDeque<T>>,
}

impl<T> SegQueue<T> {
    fn new() -> Self {
        Self { inner: Mutex::new(VecDeque::new()) }
    }

    fn push(&self, item: T) {
        self.inner.lock().unwrap().push_back(item);
    }

    fn pop(&self) -> Option<T> {
        self.inner.lock().unwrap().pop_front()
    }

    fn is_empty(&self) -> bool {
        self.inner.lock().unwrap().is_empty()
    }
}
use rayon::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, RwLock};
use std::time::Instant;

/// Thread-safe points-to set using RwLock
///
/// Note: Despite the name, this is NOT truly atomic/lock-free.
/// Uses RwLock which allows concurrent reads but exclusive writes.
///
/// Design:
/// - Read-heavy workload: most operations are union checks
/// - Writes acquire exclusive lock
/// - RwLock allows concurrent reads, exclusive writes
struct AtomicPointsToSet {
    inner: Arc<RwLock<SparseBitmap>>,
}

impl AtomicPointsToSet {
    fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(SparseBitmap::new())),
        }
    }

    /// Try to union with another bitmap
    /// Returns true if the set was modified
    fn union_with(&self, other: &SparseBitmap) -> bool {
        let mut pts = self.inner.write().unwrap();
        let old_len = pts.len();
        pts.union_with(other);
        pts.len() > old_len
    }

    /// Get a clone for reading
    fn clone_set(&self) -> SparseBitmap {
        self.inner.read().unwrap().clone()
    }

    /// Insert a single location
    fn insert(&self, loc: LocationId) -> bool {
        let mut pts = self.inner.write().unwrap();
        pts.insert(loc)
    }

    fn len(&self) -> usize {
        self.inner.read().unwrap().len()
    }
}

impl Clone for AtomicPointsToSet {
    fn clone(&self) -> Self {
        Self {
            inner: Arc::clone(&self.inner),
        }
    }
}

/// Concurrent worklist with atomic membership tracking
///
/// Note: The queue itself uses Mutex (not lock-free), but membership
/// checks use atomic flags to reduce contention.
///
/// Termination uses polling (busy-wait), not work-stealing.
struct ConcurrentWorklist {
    queue: Arc<SegQueue<VarId>>,
    in_queue: Arc<Vec<AtomicBool>>,
    max_var: usize,
}

impl ConcurrentWorklist {
    fn new(max_var: usize) -> Self {
        let mut in_queue = Vec::with_capacity(max_var + 1);
        for _ in 0..=max_var {
            in_queue.push(AtomicBool::new(false));
        }

        Self {
            queue: Arc::new(SegQueue::new()),
            in_queue: Arc::new(in_queue),
            max_var,
        }
    }

    /// Try to push variable to worklist
    /// Returns true if added, false if already in queue
    fn push(&self, var: VarId) -> bool {
        let idx = var as usize;
        if idx > self.max_var {
            return false;
        }

        // Atomic compare-and-swap: only add if not already in queue
        if self.in_queue[idx]
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .is_ok()
        {
            self.queue.push(var);
            true
        } else {
            false
        }
    }

    /// Pop variable from worklist
    fn pop(&self) -> Option<VarId> {
        self.queue.pop().map(|var| {
            self.in_queue[var as usize].store(false, Ordering::Release);
            var
        })
    }

    fn is_empty(&self) -> bool {
        self.queue.is_empty()
    }

    fn len(&self) -> usize {
        // Approximate (SegQueue doesn't track size efficiently)
        self.in_queue
            .iter()
            .filter(|flag| flag.load(Ordering::Relaxed))
            .count()
    }
}

/// Parallel Andersen solver
pub struct ParallelAndersenSolver {
    /// Configuration
    config: AndersenConfig,

    /// Constraints
    constraints: ConstraintSet,

    /// Points-to sets (thread-safe)
    points_to: Arc<FxHashMap<VarId, AtomicPointsToSet>>,

    /// Copy edges (rhs → lhs successors)
    copy_edges: Arc<FxHashMap<VarId, FxHashSet<VarId>>>,

    /// Complex constraints (LOAD/STORE)
    complex_constraints: Arc<Vec<Constraint>>,

    /// SCC result
    scc_result: Option<SCCResult>,

    /// Locations
    locations: Arc<RwLock<FxHashMap<LocationId, AbstractLocation>>>,
    location_factory: LocationFactory,

    /// Statistics
    stats: AndersenStats,
}

impl ParallelAndersenSolver {
    pub fn new(config: AndersenConfig) -> Self {
        Self {
            config,
            constraints: ConstraintSet::new(),
            points_to: Arc::new(FxHashMap::default()),
            copy_edges: Arc::new(FxHashMap::default()),
            complex_constraints: Arc::new(Vec::new()),
            scc_result: None,
            locations: Arc::new(RwLock::new(FxHashMap::default())),
            location_factory: LocationFactory::new(),
            stats: AndersenStats::default(),
        }
    }

    pub fn add_constraint(&mut self, constraint: Constraint) {
        self.constraints.add(constraint);
    }

    pub fn add_constraints(&mut self, constraints: impl IntoIterator<Item = Constraint>) {
        for c in constraints {
            self.add_constraint(c);
        }
    }

    /// Solve in parallel
    pub fn solve(mut self) -> AndersenResult {
        let total_start = Instant::now();

        // Phase 1: SCC detection (sequential - Tarjan is hard to parallelize)
        if self.config.enable_scc {
            let scc_start = Instant::now();
            self.detect_sccs();
            self.stats.duration_scc_ms = scc_start.elapsed().as_secs_f64() * 1000.0;
        }

        // Phase 2: Process ALLOC constraints (parallel)
        self.process_allocs_parallel();

        // Phase 3: Build copy edges (parallel)
        self.build_copy_edges_parallel();

        // Phase 4: Solve with parallel worklist
        let solve_start = Instant::now();
        self.solve_parallel_worklist();
        self.stats.duration_solve_ms = solve_start.elapsed().as_secs_f64() * 1000.0;

        // Phase 5: Build final graph
        let graph = self.build_graph();

        self.stats.duration_ms = total_start.elapsed().as_secs_f64() * 1000.0;
        self.stats.constraints_total = self.constraints.len();

        AndersenResult { graph, stats: self.stats }
    }

    /// Detect SCCs in the constraint graph
    fn detect_sccs(&mut self) {
        let edges: Vec<(u32, u32)> = self.constraints
            .copies()
            .map(|c| (c.rhs, c.lhs))
            .collect();

        if edges.is_empty() {
            return;
        }

        let result = tarjan_scc(&edges);
        self.stats.scc_count = result.stats.scc_count;
        self.stats.scc_collapsed = result.stats.collapsed_nodes;
        self.scc_result = Some(result);
    }

    /// Get SCC representative
    fn get_rep(&self, var: VarId) -> VarId {
        self.scc_result
            .as_ref()
            .and_then(|scc| scc.var_to_rep.get(&var).copied())
            .unwrap_or(var)
    }

    /// Process ALLOC constraints in parallel
    fn process_allocs_parallel(&mut self) {
        let alloc_results: Vec<_> = self.constraints
            .allocs()
            .collect::<Vec<_>>()
            .par_iter()
            .map(|c| {
                let var = self.get_rep(c.lhs);
                let loc_id = c.rhs;
                (var, loc_id)
            })
            .collect();

        // Merge results (sequential - needs mutable access)
        let mut points_to_map = FxHashMap::default();
        for (var, loc_id) in alloc_results {
            // Create location
            let mut locs = self.locations.write().unwrap();
            if !locs.contains_key(&loc_id) {
                let loc = self.location_factory.create(format!("alloc:{}", loc_id));
                locs.insert(loc.id, loc);
            }
            drop(locs);

            // Add to points-to set
            points_to_map
                .entry(var)
                .or_insert_with(AtomicPointsToSet::new)
                .insert(loc_id);
        }

        self.points_to = Arc::new(points_to_map);
    }

    /// Build copy edges in parallel
    fn build_copy_edges_parallel(&mut self) {
        // Collect copy edges
        let copy_edges: FxHashMap<VarId, FxHashSet<VarId>> = self.constraints
            .copies()
            .collect::<Vec<_>>()
            .par_iter()
            .fold(
                || FxHashMap::<VarId, FxHashSet<VarId>>::default(),
                |mut acc, c| {
                    let lhs = self.get_rep(c.lhs);
                    let rhs = self.get_rep(c.rhs);
                    if lhs != rhs {
                        acc.entry(rhs).or_default().insert(lhs);
                    }
                    acc
                },
            )
            .reduce(|| FxHashMap::default(), |mut acc, map| {
                for (k, v) in map {
                    acc.entry(k).or_default().extend(v);
                }
                acc
            });

        self.copy_edges = Arc::new(copy_edges);

        // Collect complex constraints
        let complex: Vec<_> = self.constraints
            .complex()
            .map(|c| {
                let mut c_clone = c.clone();
                c_clone.lhs = self.get_rep(c_clone.lhs);
                c_clone.rhs = self.get_rep(c_clone.rhs);
                c_clone
            })
            .collect();

        self.complex_constraints = Arc::new(complex);
    }

    /// Parallel worklist algorithm
    fn solve_parallel_worklist(&mut self) {
        let max_var = self.points_to.keys().max().copied().unwrap_or(0) as usize;
        let worklist = ConcurrentWorklist::new(max_var);

        // Initialize worklist
        for &var in self.points_to.keys() {
            worklist.push(var);
        }

        let max_iters = if self.config.max_iterations > 0 {
            self.config.max_iterations
        } else {
            self.constraints.len() * 10 + 10000
        };

        let iterations = Arc::new(AtomicUsize::new(0));
        let propagations = Arc::new(AtomicUsize::new(0));

        // Parallel processing with work-stealing
        let num_workers = rayon::current_num_threads();
        let batch_size = 10; // Process in batches for better cache locality

        (0..num_workers).into_par_iter().for_each(|_worker_id| {
            loop {
                // Check termination
                if iterations.load(Ordering::Relaxed) > max_iters {
                    break;
                }

                if worklist.is_empty() {
                    // All workers must see empty queue before terminating
                    std::thread::sleep(std::time::Duration::from_micros(10));
                    if worklist.is_empty() {
                        break;
                    }
                }

                // Process batch
                let mut batch = Vec::with_capacity(batch_size);
                for _ in 0..batch_size {
                    if let Some(var) = worklist.pop() {
                        batch.push(var);
                    } else {
                        break;
                    }
                }

                if batch.is_empty() {
                    continue;
                }

                for var in batch {
                    iterations.fetch_add(1, Ordering::Relaxed);

                    // Get current points-to set
                    let current_pts = match self.points_to.get(&var) {
                        Some(pts) => pts.clone_set(),
                        None => continue,
                    };

                    // Propagate via COPY edges
                    if let Some(succs) = self.copy_edges.get(&var) {
                        for &succ in succs {
                            if let Some(succ_pts) = self.points_to.get(&succ) {
                                if succ_pts.union_with(&current_pts) {
                                    propagations.fetch_add(1, Ordering::Relaxed);
                                    worklist.push(succ);
                                }
                            }
                        }
                    }

                    // Process LOAD/STORE (complex constraints)
                    for constraint in self.complex_constraints.iter() {
                        match constraint.kind {
                            ConstraintKind::Load if constraint.rhs == var => {
                                // lhs = *rhs: For each o in pts(rhs), add pts(o) to pts(lhs)
                                for loc in current_pts.iter() {
                                    if let Some(loc_pts) = self.points_to.get(&loc) {
                                        if let Some(lhs_pts) = self.points_to.get(&constraint.lhs) {
                                            if lhs_pts.union_with(&loc_pts.clone_set()) {
                                                propagations.fetch_add(1, Ordering::Relaxed);
                                                worklist.push(constraint.lhs);
                                            }
                                        }
                                    }
                                }
                            }
                            ConstraintKind::Store if constraint.lhs == var => {
                                // *lhs = rhs: For each o in pts(lhs), add pts(rhs) to pts(o)
                                if let Some(rhs_pts) = self.points_to.get(&constraint.rhs) {
                                    let rhs_set = rhs_pts.clone_set();
                                    for loc in current_pts.iter() {
                                        if let Some(loc_pts) = self.points_to.get(&loc) {
                                            if loc_pts.union_with(&rhs_set) {
                                                propagations.fetch_add(1, Ordering::Relaxed);
                                                worklist.push(loc);
                                            }
                                        }
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
        });

        self.stats.iterations = iterations.load(Ordering::Relaxed);
        self.stats.propagations = propagations.load(Ordering::Relaxed);

        if self.stats.iterations > max_iters {
            eprintln!(
                "[WARN] Parallel Andersen: max iterations reached ({})",
                max_iters
            );
        }
    }

    /// Build the final points-to graph
    fn build_graph(&self) -> PointsToGraph {
        let mut graph = PointsToGraph::with_capacity(
            self.points_to.len(),
            self.locations.read().unwrap().len(),
        );

        // Add locations
        for (_, loc) in self.locations.read().unwrap().iter() {
            graph.add_location(loc.clone());
        }

        // Add SCC mappings
        if let Some(ref scc) = self.scc_result {
            graph.set_scc_bulk(scc.var_to_rep.iter().map(|(&k, &v)| (k, v)));
        }

        // Add points-to facts
        for (&var, pts) in self.points_to.iter() {
            for loc in pts.clone_set().iter() {
                graph.add_points_to(var, loc);
            }
        }

        graph.update_stats();
        graph
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parallel_simple() {
        let config = AndersenConfig::default();
        let mut solver = ParallelAndersenSolver::new(config);

        // x = new A()
        solver.add_constraint(Constraint::alloc(1, 100));
        // y = x
        solver.add_constraint(Constraint::copy(2, 1));

        let result = solver.solve();
        assert!(result.graph.may_alias(1, 2));
    }

    #[test]
    fn test_parallel_performance() {
        let config = AndersenConfig::default();
        let mut solver = ParallelAndersenSolver::new(config);

        // Generate large constraint set
        for i in 0..1000 {
            solver.add_constraint(Constraint::alloc(i, i + 10000));
        }
        for i in 0..999 {
            solver.add_constraint(Constraint::copy(i + 1, i));
        }

        let start = Instant::now();
        let result = solver.solve();
        let elapsed = start.elapsed();

        println!(
            "Parallel solve: {} vars, {} iterations, {:.2}ms",
            result.graph.stats.total_variables,
            result.stats.iterations,
            elapsed.as_secs_f64() * 1000.0
        );
    }
}
