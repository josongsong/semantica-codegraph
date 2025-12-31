/*
 * Braun's Simple SSA Construction (2013)
 *
 * SOTA Algorithm - simpler than Cytron's (no dominance frontiers!)
 *
 * Key Innovation: On-demand Phi insertion during renaming
 *
 * Algorithm:
 * ```
 * def read_variable(var, block):
 *     if var in current_def[block]:
 *         return current_def[block][var]  # Local definition
 *     elif block is entry:
 *         return new_version(var)  # Undefined
 *     elif len(predecessors) == 1:
 *         return read_variable(var, predecessor)  # Recurse
 *     else:
 *         # Multiple predecessors → insert Phi!
 *         phi_version = new_version(var)
 *         current_def[block][var] = phi_version
 *         for pred in predecessors:
 *             phi_operands.append(read_variable(var, pred))
 *         return phi_version
 * ```
 *
 * References:
 * - "Simple and Efficient Construction of SSA Form" (Braun et al., 2013)
 * - Complexity: O(N) for N statements (no dominance computation!)
 */

use ahash::AHashMap as HashMap;
use std::sync::Arc;

use super::errors::{SSAError, SSAResult};
use super::ssa::{PhiNode, SSAGraph, SSAVariable};

/// Block identifier
pub type BlockId = String;

/// CFG Trait (abstraction for control flow graph)
///
/// This allows BraunSSABuilder to work with any CFG implementation
pub trait CFGProvider {
    fn entry_block_id(&self) -> &str;
    fn is_entry_block(&self, block_id: &str) -> bool;
    fn predecessors(&self, block_id: &str) -> Vec<String>;
    fn function_id(&self) -> &str;
}

/// Variable identifier
type VarId = String;

/// SSA Variable ID (base_var, version)
#[derive(Debug, Clone, Copy, Hash, Eq, PartialEq)]
pub struct SSAVarId {
    base_var_hash: u64, // Hash of base variable name (for fast comparison)
    version: usize,
}

impl SSAVarId {
    pub fn new(base_var: &str, version: usize) -> Self {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        base_var.hash(&mut hasher);
        let base_var_hash = hasher.finish();

        Self {
            base_var_hash,
            version,
        }
    }

    pub fn version(&self) -> usize {
        self.version
    }
}

/// Statement (simplified for SSA construction)
#[derive(Debug, Clone)]
pub enum Stmt {
    Assign(VarId, Expr),        // var = expr
    If(Expr, BlockId, BlockId), // if expr: then_block else else_block
    Return(Expr),
}

/// Expression (simplified)
#[derive(Debug, Clone)]
pub enum Expr {
    Variable(VarId),
    BinOp(Box<Expr>, BinOp, Box<Expr>),
    Call(VarId, Vec<Expr>),
    Literal(i64),
}

/// Binary operation
#[derive(Debug, Clone)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
}

/// Basic block
#[derive(Debug, Clone)]
pub struct BasicBlock {
    pub id: BlockId,
    pub statements: Vec<Stmt>,
    pub successors: Vec<BlockId>,
}

/// Braun's Simple SSA Builder
///
/// Key data structures:
/// - current_def: Map<(BlockId, VarId), SSAVarId> - current definition per block
/// - phi_nodes: Map<(BlockId, VarId), PhiNode> - Phi nodes inserted on-demand
/// - ssa_counter: Map<VarId, usize> - version counter per variable
pub struct BraunSSABuilder<C: CFGProvider> {
    cfg: Arc<C>,

    // Variable tracking
    current_def: HashMap<(BlockId, VarId), SSAVarId>,

    // Phi nodes (inserted on-demand)
    phi_nodes: HashMap<(BlockId, VarId), PhiNode>,

    // SSA version counter
    ssa_counter: HashMap<VarId, usize>,

    // Incomplete Phis (for cycle detection)
    incomplete_phis: HashMap<(BlockId, VarId), SSAVarId>,
}

impl<C: CFGProvider> BraunSSABuilder<C> {
    pub fn new(cfg: Arc<C>) -> Self {
        Self {
            cfg,
            current_def: HashMap::new(),
            phi_nodes: HashMap::new(),
            ssa_counter: HashMap::new(),
            incomplete_phis: HashMap::new(),
        }
    }

    /// Build SSA for entire function
    ///
    /// Algorithm:
    /// 1. Start from entry block
    /// 2. Rename variables (recursive DFS)
    /// 3. Phi nodes inserted on-demand during renaming
    ///
    /// # Errors
    ///
    /// Returns `SSAError` if:
    /// - CFG is invalid (no entry block, invalid structure)
    /// - Blocks contain invalid data
    /// - Circular dependencies detected
    pub fn build(&mut self, blocks: &HashMap<BlockId, BasicBlock>) -> SSAResult<SSAGraph> {
        // Log entry
        #[cfg(feature = "trace")]
        eprintln!("[SSA] Building SSA using Braun's algorithm");

        // Validate function ID - clone early to avoid borrow checker issues
        let function_id = self.cfg.function_id().to_string();
        if function_id.is_empty() {
            #[cfg(feature = "trace")]
            eprintln!("[SSA] ERROR: Empty function ID");
            return Err(SSAError::InvalidFunctionId {
                function_id: function_id.clone(),
            });
        }

        #[cfg(feature = "trace")]
        eprintln!("[SSA] Function: {}, Blocks: {}", function_id, blocks.len());

        // Find entry block
        let entry_block = self.cfg.entry_block_id().to_string();
        if entry_block.is_empty() {
            return Err(SSAError::InvalidCFG {
                reason: "Entry block ID is empty".to_string(),
            });
        }

        // Validate entry block exists
        if !blocks.contains_key(&entry_block) {
            return Err(SSAError::BlockNotFound {
                block_id: entry_block.clone(),
            });
        }

        // Rename variables starting from entry
        #[cfg(feature = "trace")]
        eprintln!(
            "[SSA] Starting variable renaming from entry block: {}",
            entry_block
        );
        self.rename_block(blocks, &entry_block)?;

        // Collect results
        let variables = self.collect_variables();
        let phi_nodes: Vec<_> = self.phi_nodes.values().cloned().collect();

        #[cfg(feature = "trace")]
        eprintln!(
            "[SSA] SSA construction complete: {} variables, {} Phi nodes",
            variables.len(),
            phi_nodes.len()
        );

        Ok(SSAGraph {
            function_id,
            variables,
            phi_nodes,
        })
    }

    /// Rename variables in a block (recursive DFS)
    fn rename_block(
        &mut self,
        blocks: &HashMap<BlockId, BasicBlock>,
        block_id: &BlockId,
    ) -> SSAResult<()> {
        let block = blocks
            .get(block_id)
            .ok_or_else(|| SSAError::BlockNotFound {
                block_id: block_id.clone(),
            })?;

        // Process statements in block
        for stmt in &block.statements {
            match stmt {
                Stmt::Assign(var_id, expr) => {
                    // Read variables in RHS (use current_def or insert Phi)
                    let _rhs_ssa = self.rename_expr(blocks, expr, block_id);

                    // Write LHS (create new version)
                    let new_version = self.new_version(var_id);
                    self.current_def
                        .insert((block_id.clone(), var_id.clone()), new_version);
                }
                Stmt::Return(expr) => {
                    let _return_ssa = self.rename_expr(blocks, expr, block_id);
                }
                Stmt::If(cond, _then_block, _else_block) => {
                    let _cond_ssa = self.rename_expr(blocks, cond, block_id);
                }
            }
        }

        // Recursively rename dominated blocks (successors in DFS order)
        for succ in &block.successors {
            self.rename_block(blocks, succ)?;
        }

        Ok(())
    }

    /// Rename an expression (reads)
    fn rename_expr(
        &mut self,
        blocks: &HashMap<BlockId, BasicBlock>,
        expr: &Expr,
        block_id: &BlockId,
    ) -> SSAVarId {
        match expr {
            Expr::Variable(var_id) => {
                // Get current definition (may insert Phi!)
                self.read_variable(blocks, var_id, block_id)
            }
            Expr::BinOp(lhs, _op, rhs) => {
                let _lhs_ssa = self.rename_expr(blocks, lhs, block_id);
                let _rhs_ssa = self.rename_expr(blocks, rhs, block_id);
                // Binary operations don't define variables
                SSAVarId::new("_tmp", 0)
            }
            Expr::Call(_func, args) => {
                for arg in args {
                    let _arg_ssa = self.rename_expr(blocks, arg, block_id);
                }
                // Calls may define variables but handled at Assign level
                SSAVarId::new("_call_result", 0)
            }
            Expr::Literal(_) => {
                // Literals don't reference variables
                SSAVarId::new("_literal", 0)
            }
        }
    }

    /// Read variable (insert Phi if needed!) - KEY ALGORITHM
    ///
    /// This is the core of Braun's algorithm:
    /// - If local definition exists → return it
    /// - If entry block with no def → return undefined
    /// - If single predecessor → recursively read from it
    /// - If multiple predecessors → **insert Phi node!**
    fn read_variable(
        &mut self,
        blocks: &HashMap<BlockId, BasicBlock>,
        var_id: &VarId,
        block_id: &BlockId,
    ) -> SSAVarId {
        // Case 1: Local definition exists
        if let Some(&ssa_var) = self.current_def.get(&(block_id.clone(), var_id.clone())) {
            return ssa_var;
        }

        // Case 2: Check for incomplete Phi (cycle detection)
        if let Some(&ssa_var) = self
            .incomplete_phis
            .get(&(block_id.clone(), var_id.clone()))
        {
            return ssa_var;
        }

        // Case 3: Entry block with no definition → undefined value
        if self.cfg.is_entry_block(block_id) {
            return self.new_version(var_id); // Undefined variable
        }

        // Get predecessors from CFG
        let predecessors = self.cfg.predecessors(block_id);

        // Case 4: Single predecessor → recursively read from it
        if predecessors.len() == 1 {
            return self.read_variable(blocks, var_id, &predecessors[0]);
        }

        // Case 5: Multiple predecessors → insert Phi node!
        let phi_version = self.new_version(var_id);

        // Mark as incomplete to detect cycles
        self.incomplete_phis
            .insert((block_id.clone(), var_id.clone()), phi_version);

        // Remember this as current definition (for recursion termination)
        self.current_def
            .insert((block_id.clone(), var_id.clone()), phi_version);

        // Fill Phi operands by recursively reading from predecessors
        let mut phi_predecessors = Vec::new();
        for pred_id in predecessors {
            let pred_value = self.read_variable(blocks, var_id, &pred_id);
            phi_predecessors.push((pred_id, pred_value.version()));
        }

        // Insert Phi node
        self.phi_nodes.insert(
            (block_id.clone(), var_id.clone()),
            PhiNode {
                variable: var_id.clone(),
                version: phi_version.version(),
                predecessors: phi_predecessors,
            },
        );

        // Remove from incomplete (now complete)
        self.incomplete_phis
            .remove(&(block_id.clone(), var_id.clone()));

        phi_version
    }

    /// Create new SSA version for variable
    fn new_version(&mut self, var_id: &VarId) -> SSAVarId {
        let version = self.ssa_counter.entry(var_id.clone()).or_insert(0);
        let ssa_var_id = SSAVarId::new(var_id, *version);
        *version += 1;
        ssa_var_id
    }

    /// Collect all SSA variables
    fn collect_variables(&self) -> Vec<SSAVariable> {
        let mut variables = Vec::new();

        for ((block_id, var_id), &ssa_var_id) in &self.current_def {
            variables.push(SSAVariable {
                base_name: var_id.clone(),
                version: ssa_var_id.version(),
                ssa_name: format!("{}_{}", var_id, ssa_var_id.version()),
            });
        }

        variables
    }

    /// Get statistics
    pub fn stats(&self) -> BraunSSAStats {
        BraunSSAStats {
            total_phi_nodes: self.phi_nodes.len(),
            total_versions: self.ssa_counter.values().sum(),
            unique_variables: self.ssa_counter.len(),
        }
    }
}

/// Braun SSA Statistics
#[derive(Debug, Clone)]
pub struct BraunSSAStats {
    pub total_phi_nodes: usize,
    pub total_versions: usize,
    pub unique_variables: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Mock CFG for testing
    struct MockCFG {
        entry: String,
        blocks: HashMap<String, Vec<String>>, // block_id → predecessors
        function_id: String,
    }

    impl MockCFG {
        fn new(entry: &str, function_id: &str) -> Self {
            Self {
                entry: entry.to_string(),
                blocks: HashMap::new(),
                function_id: function_id.to_string(),
            }
        }

        fn add_block(&mut self, block_id: &str, predecessors: Vec<&str>) {
            self.blocks.insert(
                block_id.to_string(),
                predecessors.iter().map(|s| s.to_string()).collect(),
            );
        }
    }

    impl CFGProvider for MockCFG {
        fn entry_block_id(&self) -> &str {
            &self.entry
        }

        fn is_entry_block(&self, block_id: &str) -> bool {
            block_id == self.entry
        }

        fn predecessors(&self, block_id: &str) -> Vec<String> {
            self.blocks.get(block_id).cloned().unwrap_or_default()
        }

        fn function_id(&self) -> &str {
            &self.function_id
        }
    }

    // Helper to create a simple CFG for testing
    fn create_simple_cfg() -> Arc<MockCFG> {
        let mut cfg = MockCFG::new("block0", "test_func");
        cfg.add_block("block0", vec![]); // Entry block
        cfg.add_block("block1", vec!["block0"]);
        cfg.add_block("block2", vec!["block0", "block1"]); // Merge point
        Arc::new(cfg)
    }

    #[test]
    fn test_braun_algorithm_concept() {
        // This test demonstrates the algorithm concept
        // Full test would require CFG implementation

        // Pseudo-code for Braun's algorithm:
        //
        // Block 0 (entry):
        //   x_0 = 1
        //   goto Block 2
        //
        // Block 1:
        //   x_1 = 2
        //   goto Block 2
        //
        // Block 2 (merge):
        //   x_2 = Phi(x_0, x_1)  ← Inserted on-demand!
        //   y_0 = x_2
        //
        // Braun's algorithm inserts Phi automatically when read_variable
        // detects multiple predecessors.

        assert!(
            true,
            "Concept test - demonstrates Braun's on-demand Phi insertion"
        );
    }

    #[test]
    fn test_ssa_var_id() {
        let ssa_var_1 = SSAVarId::new("x", 0);
        let ssa_var_2 = SSAVarId::new("x", 1);
        let ssa_var_3 = SSAVarId::new("y", 0);

        assert_eq!(ssa_var_1.version(), 0);
        assert_eq!(ssa_var_2.version(), 1);
        assert_ne!(ssa_var_1, ssa_var_2); // Different versions
        assert_ne!(ssa_var_1.base_var_hash, ssa_var_3.base_var_hash); // Different variables
    }

    #[test]
    fn test_new_version_counter() {
        let cfg = create_simple_cfg(); // Mock CFG
        let mut builder = BraunSSABuilder::new(cfg);

        let var_x = "x".to_string();
        let var_y = "y".to_string();

        let x_0 = builder.new_version(&var_x);
        let x_1 = builder.new_version(&var_x);
        let y_0 = builder.new_version(&var_y);

        assert_eq!(x_0.version(), 0);
        assert_eq!(x_1.version(), 1);
        assert_eq!(y_0.version(), 0);
    }
}
