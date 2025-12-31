/*
 * Domain Layer - Pure business logic
 *
 * HEXAGONAL ARCHITECTURE:
 * - No external dependencies (tree-sitter, PyO3, etc.)
 * - Only domain types and logic
 * - Testable without infrastructure
 */

pub mod models;
pub mod ports;

