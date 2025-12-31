//! Data Flow infrastructure

pub mod advanced_dfg_builder; // SOTA: Python Last-Def algorithm
pub mod dfg;
pub mod errors;
pub mod reads;

pub use advanced_dfg_builder::*;
pub use dfg::*;
pub use errors::*;
pub use reads::*;
