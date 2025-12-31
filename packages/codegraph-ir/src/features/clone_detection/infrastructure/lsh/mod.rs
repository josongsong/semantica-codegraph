//! Locality-Sensitive Hashing (LSH) for Clone Detection
//!
//! Implements MinHash LSH for fast candidate retrieval in clone detection.
//!
//! # Components
//!
//! - `minhash`: MinHash signatures for similarity estimation
//! - `index`: LSH index for sub-linear nearest neighbor search
//! - `graph_kernel`: Weisfeiler-Lehman graph kernels for structural similarity
//!
//! # Usage
//!
//! ```ignore
//! use codegraph_ir::features::clone_detection::infrastructure::lsh::{
//!     MinHashSignature, LSHIndex
//! };
//!
//! // Create signatures
//! let sig1 = MinHashSignature::from_text("def foo(): pass", 5, 128);
//! let sig2 = MinHashSignature::from_text("def bar(): pass", 5, 128);
//!
//! // Build index
//! let mut index = LSHIndex::new(16, 8);
//! index.insert(&sig1, 0);
//! index.insert(&sig2, 1);
//!
//! // Query candidates
//! let candidates = index.query(&sig1);
//! ```

pub mod graph_kernel;
pub mod index;
pub mod minhash;

pub use graph_kernel::{GraphLSHIndex, GraphLSHIndexStats, WLSignature};
pub use index::{LSHIndex, LSHIndexStats};
pub use minhash::MinHashSignature;
