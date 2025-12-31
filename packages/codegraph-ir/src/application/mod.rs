/*
 * Application Layer - Use cases and orchestration
 *
 * HEXAGONAL ARCHITECTURE:
 * - Implements domain ports
 * - Orchestrates domain logic
 * - No infrastructure details
 */

pub mod ir_processor;
pub mod ir_builder;

pub use ir_processor::DefaultIrProcessor;
pub use ir_builder::IRBuilder;

