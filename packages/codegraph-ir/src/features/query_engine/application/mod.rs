//! Query Engine Application Layer (UseCase)
//!
//! Hexagonal Architecture - Application layer provides:
//! - Clean entry point for external callers
//! - UseCase orchestration
//! - No direct infrastructure dependencies exposed
//!
//! # Architecture
//! ```text
//! External (Pipeline/Adapters)
//!           ↓
//! application/ (this module)
//!           ↓
//! domain/ (entities, value objects)
//!           ↓
//! infrastructure/ (implementations)
//! ```

mod query_usecase;

pub use query_usecase::{
    QueryInput, QueryOutput, QueryUseCase, QueryUseCaseImpl,
};
