//! TypeScript AST extractors
//!
//! This module provides extractors for TypeScript symbols:
//! - Classes (with decorators, generics, access modifiers)
//! - Interfaces (with extends, type parameters)
//! - Functions (regular, arrow, async, generators)
//! - Variables (with type annotations)
//! - Imports/Exports (ESM modules)
//! - Types (union, intersection, generic)
//!
//! Design: Each extractor is independent and testable.

pub mod class;
pub mod function;
pub mod import;
pub mod interface;
pub mod r#type;
pub mod variable;
pub mod common;

pub use class::*;
pub use function::*;
pub use import::*;
pub use interface::*;
pub use r#type::*;
pub use variable::*;
pub use common::*;
