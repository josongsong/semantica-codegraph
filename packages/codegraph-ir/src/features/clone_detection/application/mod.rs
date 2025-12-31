//! Clone Detection Application Layer (UseCase)
//!
//! Hexagonal Architecture - Application layer for clone detection.

mod clone_usecase;

pub use clone_usecase::{
    CloneDetectionInput, CloneDetectionOutput, CloneDetectionStats, CloneDetectionUseCase,
    CloneDetectionUseCaseImpl,
};
