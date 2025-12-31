/*
 * DFG (Data Flow Graph) Module
 *
 * Tracks data flow through variables:
 * - Definitions (where variables are assigned)
 * - Uses (where variables are read)
 * - Def-use chains
 * - Use-def chains
 *
 * PRODUCTION GRADE:
 * - Accurate tracking
 * - All definitions/uses
 * - No fake data
 */

use crate::shared::models::Span;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Data flow node (variable at specific location)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DFNode {
    pub variable_name: String,
    pub span: Span,
    pub is_definition: bool, // true = def, false = use
}

/// Data flow graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataFlowGraph {
    pub function_id: String,
    pub nodes: Vec<DFNode>,
    pub def_use_edges: Vec<(usize, usize)>, // (def_idx, use_idx)
}

/// Build DFG from variable assignments and reads
pub fn build_dfg(
    function_id: String,
    definitions: &[(String, Span)], // (var_name, span)
    uses: &[(String, Span)],        // (var_name, span)
) -> DataFlowGraph {
    let mut nodes = Vec::new();
    let mut def_use_edges = Vec::new();

    // Add definition nodes
    let mut def_indices: HashMap<String, Vec<usize>> = HashMap::new();
    for (var_name, span) in definitions {
        let idx = nodes.len();
        nodes.push(DFNode {
            variable_name: var_name.clone(),
            span: *span,
            is_definition: true,
        });

        def_indices
            .entry(var_name.clone())
            .or_insert_with(Vec::new)
            .push(idx);
    }

    // Add use nodes and create edges
    for (var_name, span) in uses {
        let use_idx = nodes.len();
        nodes.push(DFNode {
            variable_name: var_name.clone(),
            span: *span,
            is_definition: false,
        });

        // Find reaching definition (most recent def before this use)
        // CRITICAL: Compare by span line number, not node index!
        if let Some(def_idxs) = def_indices.get(var_name) {
            let mut reaching_def: Option<(usize, u32)> = None; // (idx, line)

            for &def_idx in def_idxs {
                let def_span = &nodes[def_idx].span;
                let def_line = def_span.start_line;
                let def_col = def_span.start_col;
                let use_line = span.start_line;
                let use_col = span.start_col;

                // Only consider defs before this use (by line number OR column if same line)
                let def_before_use = if def_line == use_line {
                    // Same line: check column position
                    def_col < use_col
                } else {
                    // Different lines: def must be on earlier line
                    def_line < use_line
                };

                if def_before_use {
                    // Update to most recent (highest line/column)
                    match reaching_def {
                        None => reaching_def = Some((def_idx, def_line)),
                        Some((_, prev_line)) if def_line > prev_line => {
                            reaching_def = Some((def_idx, def_line));
                        }
                        Some((prev_idx, prev_line))
                            if def_line == prev_line
                                && def_col > nodes[prev_idx].span.start_col =>
                        {
                            // Same line: prefer later column
                            reaching_def = Some((def_idx, def_line));
                        }
                        _ => {}
                    }
                }
            }

            // Create edge from reaching definition
            if let Some((def_idx, _def_line)) = reaching_def {
                def_use_edges.push((def_idx, use_idx));
            }
        }
    }

    DataFlowGraph {
        function_id,
        nodes,
        def_use_edges,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shared::models::Span;

    #[test]
    fn test_simple_def_use() {
        let defs = vec![("x".to_string(), Span::new(1, 0, 1, 5))];
        let uses = vec![("x".to_string(), Span::new(2, 0, 2, 1))];

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        assert_eq!(dfg.nodes.len(), 2); // 1 def + 1 use
        assert_eq!(dfg.def_use_edges.len(), 1); // 1 edge
    }

    #[test]
    fn test_multiple_uses() {
        let defs = vec![("x".to_string(), Span::new(1, 0, 1, 5))];
        let uses = vec![
            ("x".to_string(), Span::new(2, 0, 2, 1)),
            ("x".to_string(), Span::new(3, 0, 3, 1)),
        ];

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        assert_eq!(dfg.nodes.len(), 3); // 1 def + 2 uses
        assert_eq!(dfg.def_use_edges.len(), 2); // 2 edges
    }

    // EDGE CASE: Empty inputs
    #[test]
    fn test_empty_dfg() {
        let defs = vec![];
        let uses = vec![];

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        assert_eq!(dfg.nodes.len(), 0);
        assert_eq!(dfg.def_use_edges.len(), 0);
    }

    // EDGE CASE: Use before def (undefined variable)
    #[test]
    fn test_use_before_def() {
        let defs = vec![];
        let uses = vec![("x".to_string(), Span::new(1, 0, 1, 1))];

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        assert_eq!(dfg.nodes.len(), 1); // 1 use node
        assert_eq!(dfg.def_use_edges.len(), 0); // No edges (no def)
    }

    // EDGE CASE: Multiple defs, multiple uses (complex)
    #[test]
    fn test_multiple_defs_multiple_uses() {
        let defs = vec![
            ("x".to_string(), Span::new(1, 0, 1, 5)),
            ("x".to_string(), Span::new(3, 0, 3, 5)), // Redefinition
        ];
        let uses = vec![
            ("x".to_string(), Span::new(2, 0, 2, 1)), // After first def
            ("x".to_string(), Span::new(4, 0, 4, 1)), // After second def
        ];

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        // Node layout: [def0(idx=0), def1(idx=1), use0(idx=2), use1(idx=3)]
        assert_eq!(dfg.nodes.len(), 4); // 2 defs + 2 uses

        // Correct reaching definition:
        // - use0 at line 2: reaches def0 at line 1
        // - use1 at line 4: reaches def1 at line 3 (most recent)
        assert_eq!(dfg.def_use_edges.len(), 2);

        // Verify edges
        assert!(dfg.def_use_edges.contains(&(0, 2))); // def0->use0
        assert!(dfg.def_use_edges.contains(&(1, 3))); // def1->use1
    }

    // EDGE CASE: Different variables
    #[test]
    fn test_different_variables() {
        let defs = vec![
            ("x".to_string(), Span::new(1, 0, 1, 5)),
            ("y".to_string(), Span::new(2, 0, 2, 5)),
        ];
        let uses = vec![
            ("x".to_string(), Span::new(3, 0, 3, 1)),
            ("y".to_string(), Span::new(4, 0, 4, 1)),
        ];

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        assert_eq!(dfg.nodes.len(), 4); // 2 defs + 2 uses
        assert_eq!(dfg.def_use_edges.len(), 2); // x->x, y->y (no cross edges)
    }

    // EXTREME CASE: Large scale
    #[test]
    fn test_large_scale_dfg() {
        let mut defs = vec![];
        let mut uses = vec![];

        // 100 variables, 100 uses each
        for i in 0..100 {
            let var_name = format!("var_{}", i);
            defs.push((var_name.clone(), Span::new(i as u32, 0, i as u32, 5)));
            uses.push((
                var_name,
                Span::new((i + 100) as u32, 0, (i + 100) as u32, 1),
            ));
        }

        let dfg = build_dfg("func".to_string(), &defs, &uses);

        assert_eq!(dfg.nodes.len(), 200); // 100 defs + 100 uses
        assert_eq!(dfg.def_use_edges.len(), 100); // 100 edges
    }
}
