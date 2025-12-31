//! Slicing Application Layer
//!
//! Use cases for program slicing.
//! Implementation: see `infrastructure/slicer.rs` (1,115 LOC)
//!
//! Main entry point: `ProgramSlicer::slice()`

pub use crate::features::slicing::infrastructure::{
    CodeFragment, ProgramSlicer, SliceConfig, SliceResult,
};
