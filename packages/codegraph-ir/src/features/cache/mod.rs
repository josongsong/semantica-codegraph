//! RFC-RUST-CACHE-001: SOTA Rust Cache System
//!
//! Python RFC-039의 3-Tier Cache를 Rust로 포팅하되 학계/산업계 SOTA 수준으로 개선:
//!
//! - **L0 (Session Cache)**: DashMap (lock-free) + Blake3 fingerprint + Bloom filter
//! - **L1 (Adaptive Cache)**: moka (ARC eviction + TTL)
//! - **L2 (Disk Cache)**: rkyv (zero-copy) + mmap + RocksDB index
//! - **L3 (CAS Store)**: Content-addressable storage (optional)
//!
//! Performance targets:
//! - Watch mode: <5ms (Python: ~10ms) → 2x faster
//! - L0 check (10K files): <1ms (Python: 10ms) → 10x faster
//! - L2 disk I/O: <0.5ms (Python: 1-5ms) → 10x faster

mod bloom;
mod error;
mod fingerprint;
mod metrics;
mod types;

pub mod config;
mod dependency_graph;
mod l0_session_cache;
mod l1_adaptive_cache;
mod l2_disk_cache;
mod tiered_cache;

pub use error::*;
pub use fingerprint::*;
pub use metrics::*;
pub use types::*;

pub use config::*;
pub use dependency_graph::DependencyGraph;
pub use l0_session_cache::SessionCache;
pub use l1_adaptive_cache::{AdaptiveCache, EstimateSize};
pub use l2_disk_cache::DiskCache;
pub use tiered_cache::TieredCache;
