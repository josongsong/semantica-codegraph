#!/bin/bash
# Create PyO3 Bindings for TRCR
#
# Purpose: Create Rust bindings to call TRCR from Rust
# Target: packages/codegraph-ir/src/adapters/pyo3/trcr_bindings.rs

set -e

echo "🔧 Creating PyO3 TRCR Bindings"
echo "=============================="

CODEGRAPH_IR="packages/codegraph-ir"
BINDINGS_DIR="$CODEGRAPH_IR/src/adapters/pyo3"
BINDINGS_FILE="$BINDINGS_DIR/trcr_bindings.rs"

# Create bindings directory if needed
mkdir -p "$BINDINGS_DIR"

# Create Rust bindings file
cat > "$BINDINGS_FILE" << 'RUSTEOF'
//! PyO3 Bindings for TRCR (Taint Rule Compiler & Runtime)
//!
//! This module provides Rust bindings to call Python TRCR from Rust code.
//!
//! Architecture:
//! ```
//! Rust (L14 Taint Analysis)
//!   ↓ PyO3
//! Python (TRCR)
//!   ↓ Executes
//! 488 Atoms + CWE Rules
//! ```

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;

use crate::shared::models::Node;
use crate::errors::CodegraphError;

/// TRCR Match Result
#[derive(Debug, Clone)]
pub struct TRCRMatch {
    pub rule_id: String,
    pub entity_id: String,
    pub effect_kind: String,  // "source", "sink", "sanitizer"
    pub confidence: f64,
}

/// TRCR Bridge - Interface to Python TRCR
pub struct TRCRBridge {
    compiler: PyObject,
    executor: Option<PyObject>,
}

impl TRCRBridge {
    /// Create new TRCR bridge
    pub fn new() -> Result<Self, CodegraphError> {
        Python::with_gil(|py| {
            // Import TRCR
            let trcr = py.import("trcr").map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to import TRCR: {}", e))
            })?;

            // Create compiler
            let compiler_class = trcr.getattr("TaintRuleCompiler").map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to get TaintRuleCompiler: {}", e))
            })?;
            let compiler = compiler_class.call0().map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to create compiler: {}", e))
            })?;

            Ok(TRCRBridge {
                compiler: compiler.into(),
                executor: None,
            })
        })
    }

    /// Compile rules from CWE catalog
    pub fn compile_cwe_rules(&mut self, cwe_ids: &[&str]) -> Result<(), CodegraphError> {
        Python::with_gil(|py| {
            let compiler = self.compiler.as_ref(py);

            // Path to CWE catalog
            let catalog_base = std::env::current_dir()
                .map_err(|e| CodegraphError::TaintAnalysisError(format!("Failed to get cwd: {}", e)))?
                .join("packages/codegraph-trcr/catalog/cwe");

            let mut all_executables = Vec::new();

            // Compile each CWE
            for cwe_id in cwe_ids {
                let cwe_file = catalog_base.join(format!("{}.yaml", cwe_id));
                if !cwe_file.exists() {
                    eprintln!("⚠️  CWE file not found: {:?}", cwe_file);
                    continue;
                }

                let file_path = cwe_file.to_str().ok_or_else(|| {
                    CodegraphError::TaintAnalysisError("Invalid CWE path".to_string())
                })?;

                let executables = compiler
                    .call_method1("compile_file", (file_path,))
                    .map_err(|e| CodegraphError::TaintAnalysisError(format!("Compilation failed: {}", e)))?;

                all_executables.push(executables.into());
            }

            // Create executor with all rules
            let trcr = py.import("trcr").map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to import TRCR: {}", e))
            })?;
            let executor_class = trcr.getattr("TaintRuleExecutor").map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to get TaintRuleExecutor: {}", e))
            })?;

            // Flatten executables
            let all_rules = PyList::empty(py);
            for exec_list in &all_executables {
                let exec_list = exec_list.as_ref(py);
                for item in exec_list.iter().map_err(|e| {
                    CodegraphError::TaintAnalysisError(format!("Failed to iterate executables: {}", e))
                })? {
                    all_rules.append(item).map_err(|e| {
                        CodegraphError::TaintAnalysisError(format!("Failed to append rule: {}", e))
                    })?;
                }
            }

            let kwargs = PyDict::new(py);
            kwargs.set_item("enable_cache", true).map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to set enable_cache: {}", e))
            })?;

            let executor = executor_class
                .call((all_rules,), Some(kwargs))
                .map_err(|e| CodegraphError::TaintAnalysisError(format!("Executor creation failed: {}", e)))?;

            self.executor = Some(executor.into());

            eprintln!("[TRCR] Compiled {} CWE rules", cwe_ids.len());
            Ok(())
        })
    }

    /// Execute rules against IR nodes
    pub fn execute(&self, nodes: &[Node]) -> Result<Vec<TRCRMatch>, CodegraphError> {
        let executor = self.executor.as_ref().ok_or_else(|| {
            CodegraphError::TaintAnalysisError("Executor not initialized. Call compile_cwe_rules first.".to_string())
        })?;

        Python::with_gil(|py| {
            let executor = executor.as_ref(py);

            // Convert Rust nodes to Python entities
            let entities = self.nodes_to_entities(py, nodes)?;

            // Execute rules
            let matches = executor
                .call_method1("execute", (entities,))
                .map_err(|e| CodegraphError::TaintAnalysisError(format!("Execution failed: {}", e)))?;

            // Convert Python matches to Rust
            self.convert_matches(py, matches)
        })
    }

    /// Convert Rust nodes to Python MockEntity objects
    fn nodes_to_entities<'py>(
        &self,
        py: Python<'py>,
        nodes: &[Node],
    ) -> Result<&'py PyList, CodegraphError> {
        let trcr = py.import("trcr.runtime.entity").map_err(|e| {
            CodegraphError::TaintAnalysisError(format!("Failed to import MockEntity: {}", e))
        })?;
        let mock_entity_class = trcr.getattr("MockEntity").map_err(|e| {
            CodegraphError::TaintAnalysisError(format!("Failed to get MockEntity: {}", e))
        })?;

        let entities = PyList::empty(py);

        for node in nodes {
            let kwargs = PyDict::new(py);
            kwargs.set_item("entity_id", &node.id).unwrap();
            kwargs.set_item("kind", "call").unwrap();  // Simplified for now

            // Set FQN as call name
            if !node.fqn.is_empty() {
                kwargs.set_item("call", &node.fqn).unwrap();

                // Extract base_type from FQN (e.g., "sqlite3.Cursor.execute" → base_type="sqlite3.Cursor")
                if let Some(dot_pos) = node.fqn.rfind('.') {
                    let base_type = &node.fqn[..dot_pos];
                    let call_name = &node.fqn[dot_pos + 1..];
                    kwargs.set_item("base_type", base_type).unwrap();
                    kwargs.set_item("call", call_name).unwrap();
                }
            }

            let entity = mock_entity_class.call((), Some(kwargs)).map_err(|e| {
                CodegraphError::TaintAnalysisError(format!("Failed to create MockEntity: {}", e))
            })?;

            entities.append(entity).unwrap();
        }

        Ok(entities)
    }

    /// Convert Python matches to Rust TRCRMatch
    fn convert_matches(
        &self,
        py: Python,
        matches: &PyAny,
    ) -> Result<Vec<TRCRMatch>, CodegraphError> {
        let mut results = Vec::new();

        for match_obj in matches.iter().map_err(|e| {
            CodegraphError::TaintAnalysisError(format!("Failed to iterate matches: {}", e))
        })? {
            let rule_id = match_obj
                .getattr("rule_id")
                .and_then(|v| v.extract::<String>())
                .unwrap_or_default();

            let entity_id = match_obj
                .getattr("entity_id")
                .and_then(|v| v.extract::<String>())
                .unwrap_or_default();

            let effect_kind = match_obj
                .getattr("effect_kind")
                .and_then(|v| v.extract::<String>())
                .unwrap_or_default();

            let confidence = match_obj
                .getattr("confidence")
                .and_then(|v| v.extract::<f64>())
                .unwrap_or(1.0);

            results.push(TRCRMatch {
                rule_id,
                entity_id,
                effect_kind,
                confidence,
            });
        }

        Ok(results)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trcr_bridge_creation() {
        let result = TRCRBridge::new();
        assert!(result.is_ok(), "Failed to create TRCR bridge");
    }
}
RUSTEOF

echo "✅ Created: $BINDINGS_FILE"

# Update mod.rs to include new bindings
MOD_FILE="$BINDINGS_DIR/mod.rs"

if [ -f "$MOD_FILE" ]; then
    echo ""
    echo "📝 Update $MOD_FILE to include:"
    echo "   pub mod trcr_bindings;"
else
    echo ""
    echo "⚠️  mod.rs not found at: $MOD_FILE"
    echo "   Create it manually with: pub mod trcr_bindings;"
fi

echo ""
echo "✅ PyO3 bindings created!"
echo ""
echo "Next steps:"
echo "  1. Add to Cargo.toml: pyo3 = { version = \"0.20\", features = [\"auto-initialize\"] }"
echo "  2. Add module export in mod.rs"
echo "  3. Test with: cargo test --package codegraph-ir trcr"
