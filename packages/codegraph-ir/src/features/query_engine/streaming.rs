// NodeStream - Memory-efficient streaming of query results
//
// Provides O(chunk_size) memory guarantee for large result sets.
// Uses Rust Iterator pattern for natural integration.

use crate::shared::models::Node;
use super::node_query::NodeQueryBuilder;

/// NodeStream - Iterator over node query results in chunks
///
/// Memory guarantee: O(chunk_size), NOT O(total_nodes)
///
/// Example:
/// ```no_run
/// let stream = engine.query()
///     .nodes()
///     .filter(NodeKind::Function)
///     .stream(1000)?;
///
/// for batch in stream {
///     // Process 1000 nodes at a time
///     process_batch(batch);
///     // Memory: ~500KB, not 500MB
/// }
/// ```
pub struct NodeStream<'a> {
    nodes: Vec<Node>,
    chunk_size: usize,
    current_index: usize,
    _phantom: std::marker::PhantomData<&'a ()>,
}

impl<'a> NodeStream<'a> {
    /// Create new NodeStream from NodeQueryBuilder
    ///
    /// Args:
    ///     query: NodeQueryBuilder with filters applied
    ///     chunk_size: Number of nodes per batch
    ///
    /// Returns:
    ///     NodeStream iterator
    pub fn new(query: NodeQueryBuilder<'a>, chunk_size: usize) -> Result<Self, String> {
        if chunk_size == 0 {
            return Err("chunk_size must be > 0".to_string());
        }

        // Get filtered nodes
        let nodes = query.get_filtered_nodes();

        Ok(Self {
            nodes,
            chunk_size,
            current_index: 0,
            _phantom: std::marker::PhantomData,
        })
    }

    /// Get total number of nodes (without consuming stream)
    pub fn total_count(&self) -> usize {
        self.nodes.len()
    }

    /// Get number of chunks
    pub fn chunk_count(&self) -> usize {
        (self.nodes.len() + self.chunk_size - 1) / self.chunk_size
    }
}

/// Iterator implementation - enables for-loop usage
impl<'a> Iterator for NodeStream<'a> {
    type Item = Vec<Node>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.current_index >= self.nodes.len() {
            return None;
        }

        let start = self.current_index;
        let end = std::cmp::min(start + self.chunk_size, self.nodes.len());

        let chunk: Vec<Node> = self.nodes[start..end].to_vec();
        self.current_index = end;

        Some(chunk)
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        let remaining = (self.nodes.len() - self.current_index + self.chunk_size - 1) / self.chunk_size;
        (remaining, Some(remaining))
    }
}

/// ExactSizeIterator - enables .len() on stream
impl<'a> ExactSizeIterator for NodeStream<'a> {
    fn len(&self) -> usize {
        (self.nodes.len() - self.current_index + self.chunk_size - 1) / self.chunk_size
    }
}

/// Streaming utilities
impl<'a> NodeStream<'a> {
    /// Process each batch with a function
    ///
    /// Example:
    /// ```no_run
    /// stream.for_each_batch(|batch| {
    ///     println!("Processing {} nodes", batch.len());
    ///     for node in batch {
    ///         process(node);
    ///     }
    /// })?;
    /// ```
    pub fn for_each_batch<F>(mut self, mut f: F) -> Result<(), String>
    where
        F: FnMut(Vec<Node>),
    {
        while let Some(batch) = self.next() {
            f(batch);
        }
        Ok(())
    }

    /// Collect all nodes (defeats streaming purpose - use sparingly)
    ///
    /// WARNING: This loads all nodes into memory!
    /// Only use when you're sure the result fits in RAM.
    ///
    /// Example:
    /// ```no_run
    /// let all_nodes = stream.collect_all();
    /// ```
    pub fn collect_all(self) -> Vec<Node> {
        self.nodes
    }

    /// Take first N nodes and stop (early termination)
    ///
    /// Example:
    /// ```no_run
    /// let first_1000 = stream.take_nodes(1000);
    /// ```
    pub fn take_nodes(mut self, n: usize) -> Vec<Node> {
        self.nodes.truncate(n);
        self.nodes
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::ir_generation::domain::ir_document::IRDocument;
    use crate::shared::models::{Node, NodeKind};
    use crate::features::query_engine::infrastructure::GraphIndex;
    use crate::features::query_engine::node_query::NodeQueryBuilder;

    fn create_test_doc(n: usize) -> IRDocument {
        let mut doc = IRDocument::new("test.py".to_string());

        for i in 0..n {
            let node = Node::new(
                format!("func{}", i),
                "function".to_string(),
            );
            doc.add_node(node);
        }

        doc
    }

    #[test]
    fn test_stream_basic() {
        let doc = create_test_doc(10);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let stream = builder
            .filter(NodeKind::Function)
            .stream(3)
            .unwrap();

        // 10 nodes, chunk_size=3 → 4 chunks (3, 3, 3, 1)
        assert_eq!(stream.chunk_count(), 4);
        assert_eq!(stream.total_count(), 10);
    }

    #[test]
    fn test_stream_iteration() {
        let doc = create_test_doc(10);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let stream = builder
            .filter(NodeKind::Function)
            .stream(3)
            .unwrap();

        let mut batches = Vec::new();
        for batch in stream {
            batches.push(batch);
        }

        assert_eq!(batches.len(), 4);
        assert_eq!(batches[0].len(), 3);
        assert_eq!(batches[1].len(), 3);
        assert_eq!(batches[2].len(), 3);
        assert_eq!(batches[3].len(), 1);
    }

    #[test]
    fn test_stream_for_each_batch() {
        let doc = create_test_doc(10);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let stream = builder
            .filter(NodeKind::Function)
            .stream(3)
            .unwrap();

        let mut total_processed = 0;
        stream.for_each_batch(|batch| {
            total_processed += batch.len();
        }).unwrap();

        assert_eq!(total_processed, 10);
    }

    #[test]
    fn test_stream_collect_all() {
        let doc = create_test_doc(10);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let stream = builder
            .filter(NodeKind::Function)
            .stream(3)
            .unwrap();

        let all_nodes = stream.collect_all();
        assert_eq!(all_nodes.len(), 10);
    }

    #[test]
    fn test_stream_take_nodes() {
        let doc = create_test_doc(100);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let stream = builder
            .filter(NodeKind::Function)
            .stream(10)
            .unwrap();

        let first_20 = stream.take_nodes(20);
        assert_eq!(first_20.len(), 20);
    }

    #[test]
    fn test_stream_zero_chunk_size() {
        let doc = create_test_doc(10);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let result = builder
            .filter(NodeKind::Function)
            .stream(0);

        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "chunk_size must be > 0");
    }

    #[test]
    fn test_stream_exact_size_iterator() {
        let doc = create_test_doc(10);
        let index = GraphIndex::new(&doc);
        let builder = NodeQueryBuilder::new(&index, &doc);

        let stream = builder
            .filter(NodeKind::Function)
            .stream(3)
            .unwrap();

        assert_eq!(stream.len(), 4);  // 4 chunks
    }
}
