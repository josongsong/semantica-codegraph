// Domain: EdgeSelector - Type-safe edge filtering
// Maps to Python: src/contexts/code_foundation/domain/query/selectors.py

use serde::{Deserialize, Serialize};

/// Edge types (matches Python EdgeType)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EdgeType {
    /// Data flow graph edges (def-use)
    DFG,
    /// Control flow graph edges
    CFG,
    /// Call graph edges
    Call,
    /// All edge types (union)
    All,
}

/// Edge selector with direction and depth
/// Matches Python: EdgeSelector dataclass
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EdgeSelector {
    pub edge_type: EdgeType,
    pub backward: bool,
    pub min_depth: usize,
    pub max_depth: usize,
}

impl EdgeSelector {
    pub fn new(edge_type: EdgeType) -> Self {
        Self {
            edge_type,
            backward: false,
            min_depth: 1,
            max_depth: 10,
        }
    }

    pub fn backward(mut self) -> Self {
        self.backward = true;
        self
    }

    pub fn depth(mut self, max: usize, min: usize) -> Self {
        self.max_depth = max;
        self.min_depth = min;
        self
    }

    pub fn is_forward(&self) -> bool {
        !self.backward
    }
}

impl Default for EdgeSelector {
    fn default() -> Self {
        Self::new(EdgeType::All)
    }
}

// Bitwise OR for union (E.DFG | E.CALL)
impl std::ops::BitOr for EdgeType {
    type Output = EdgeTypeSet;

    fn bitor(self, rhs: Self) -> Self::Output {
        EdgeTypeSet {
            types: vec![self, rhs],
        }
    }
}

/// Set of edge types for union operations
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EdgeTypeSet {
    pub types: Vec<EdgeType>,
}

impl EdgeTypeSet {
    pub fn contains(&self, edge_type: EdgeType) -> bool {
        self.types.contains(&edge_type)
    }

    pub fn matches(&self, edge_type: EdgeType) -> bool {
        self.types.contains(&edge_type) || self.types.contains(&EdgeType::All)
    }
}

impl std::ops::BitOr<EdgeType> for EdgeTypeSet {
    type Output = EdgeTypeSet;

    fn bitor(mut self, rhs: EdgeType) -> Self::Output {
        if !self.types.contains(&rhs) {
            self.types.push(rhs);
        }
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_edge_selector_creation() {
        let selector = EdgeSelector::new(EdgeType::DFG);
        assert_eq!(selector.edge_type, EdgeType::DFG);
        assert!(!selector.backward);
        assert_eq!(selector.max_depth, 10);
    }

    #[test]
    fn test_edge_selector_modifiers() {
        let selector = EdgeSelector::new(EdgeType::CFG).backward().depth(5, 1);

        assert!(selector.backward);
        assert_eq!(selector.max_depth, 5);
        assert_eq!(selector.min_depth, 1);
    }

    #[test]
    fn test_edge_type_union() {
        let union = EdgeType::DFG | EdgeType::Call;
        assert!(union.contains(EdgeType::DFG));
        assert!(union.contains(EdgeType::Call));
        assert!(!union.contains(EdgeType::CFG));
    }

    #[test]
    fn test_edge_type_set_chaining() {
        let union = EdgeType::DFG | EdgeType::Call | EdgeType::CFG;
        assert_eq!(union.types.len(), 3);
        assert!(union.matches(EdgeType::DFG));
        assert!(union.matches(EdgeType::Call));
        assert!(union.matches(EdgeType::CFG));
    }
}
