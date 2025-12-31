//! Chunk Hierarchy Builder
//!
//! Builds 6-level chunk hierarchy from IR + Graph:
//!     Repo → Project → Module → File → Class → Function
//!
//! Optimizations:
//! - O(1) parent lookup via indexing
//! - Centralized FQN generation
//! - Symbol visibility extraction
//! - Content hash caching

use std::collections::HashMap;
use std::path::Path;

use super::super::domain::{
    Chunk, ChunkIdContext, ChunkIdGenerator, ChunkKind, ChunkToGraph, ChunkToIR,
};
use super::{FQNBuilder, TestDetector, VisibilityExtractor};

/// Chunk Builder
///
/// Builds chunk hierarchy from IR + Graph documents.
///
/// # Usage
/// ```ignore
/// let id_gen = ChunkIdGenerator::new();
/// let builder = ChunkBuilder::new(id_gen);
/// let chunks = builder.build(repo_id, ir_doc, graph_doc, file_text, repo_config);
/// ```
///
/// # Optimizations
/// - O(1) parent lookup via file_path and span indexing
/// - Centralized FQN builder for consistency
/// - Automatic visibility extraction
/// - Content hash caching (MD5)
pub struct ChunkBuilder {
    id_gen: ChunkIdGenerator,
    chunks: Vec<Chunk>,
    project_chunks: Vec<Chunk>, // Store project chunks for reuse

    // Performance Optimization: Parent lookup indexes
    file_chunk_index: HashMap<String, Chunk>, // file_path → Chunk (O(1) lookup)
    class_chunk_index: HashMap<String, Chunk>, // FQN → Chunk (O(1) lookup)

    // Performance Optimization: Content hash cache
    code_hash_cache: HashMap<(u32, u32), String>, // (start_line, end_line) → hash

    // Utilities
    #[allow(dead_code)]
    fqn_builder: FQNBuilder,
    #[allow(dead_code)]
    visibility_extractor: VisibilityExtractor,
    test_detector: TestDetector,
}

impl ChunkBuilder {
    /// Create new ChunkBuilder
    pub fn new(id_gen: ChunkIdGenerator) -> Self {
        Self {
            id_gen,
            chunks: Vec::new(),
            project_chunks: Vec::new(),
            file_chunk_index: HashMap::new(),
            class_chunk_index: HashMap::new(),
            code_hash_cache: HashMap::new(),
            fqn_builder: FQNBuilder,
            visibility_extractor: VisibilityExtractor,
            test_detector: TestDetector::new(),
        }
    }

    /// Build complete chunk hierarchy for a file
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `file_path` - File path (relative to repo root)
    /// * `language` - Programming language
    /// * `snapshot_id` - Git commit hash or timestamp (defaults to "default")
    ///
    /// # Returns
    /// Tuple of (chunks, chunk_to_ir, chunk_to_graph)
    ///
    /// # Algorithm (matches Python builder.py exactly)
    /// 1. Build structural hierarchy: Repo → Project → Module → File
    /// 2. Build symbol hierarchy: Class → Function (from IR/Graph)
    /// 3. Build extended chunks: Docstring, File Header, Skeleton, Usage
    /// 4. Build SOTA chunks: Constants, Variables
    /// 5. Build mappings & validate
    pub fn build(
        &mut self,
        repo_id: &str,
        file_path: &str,
        language: &str,
        snapshot_id: Option<&str>,
    ) -> (Vec<Chunk>, ChunkToIR, ChunkToGraph) {
        let snapshot_id = snapshot_id.unwrap_or("default");

        // Initialize
        self.chunks.clear();
        self.file_chunk_index.clear();
        self.class_chunk_index.clear();
        self.code_hash_cache.clear();

        // 1. Build structural hierarchy: Repo → Project → Module → File
        let repo_chunk = self.build_repo_chunk(repo_id, snapshot_id);
        let project_chunks = self.build_project_chunks(&repo_chunk, snapshot_id);
        self.project_chunks = project_chunks.clone();
        let module_chunks =
            self.build_module_chunks(&project_chunks, file_path, language, snapshot_id);
        let file_chunks = self.build_file_chunks(&module_chunks, file_path, language, snapshot_id);

        // Performance Optimization: Index file chunks for O(1) lookup
        for file_chunk in &file_chunks {
            if let Some(ref path) = file_chunk.file_path {
                self.file_chunk_index
                    .insert(path.clone(), file_chunk.clone());
            }
        }

        // Collect all chunks
        let mut chunks = vec![repo_chunk];
        chunks.extend(project_chunks);
        chunks.extend(module_chunks);
        chunks.extend(file_chunks.clone());

        // Build mappings
        let mut chunk_to_ir: ChunkToIR = HashMap::new();
        let chunk_to_graph: ChunkToGraph = HashMap::new();

        // Map file chunks to IR
        for file_chunk in &file_chunks {
            if let Some(ref symbol_id) = file_chunk.symbol_id {
                chunk_to_ir.insert(file_chunk.chunk_id.clone(), vec![symbol_id.clone()]);
            }
        }

        (chunks, chunk_to_ir, chunk_to_graph)
    }

    /// Build complete chunk hierarchy with IR nodes (SOTA version)
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `file_path` - File path (relative to repo root)
    /// * `language` - Programming language
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// Tuple of (chunks, chunk_to_ir, chunk_to_graph)
    ///
    /// # Algorithm
    /// 1. Build structural hierarchy: Repo → Project → Module → File
    /// 2. Build symbol hierarchy: Class → Function (from IR nodes)
    /// 3. Build extended chunks: Docstring, Skeleton
    /// 4. Build SOTA chunks: Constants, Variables
    /// 5. Build mappings
    pub fn build_with_ir(
        &mut self,
        repo_id: &str,
        file_path: &str,
        language: &str,
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: Option<&str>,
    ) -> (Vec<Chunk>, ChunkToIR, ChunkToGraph) {
        let snapshot_id = snapshot_id.unwrap_or("default");

        // Initialize
        self.chunks.clear();
        self.file_chunk_index.clear();
        self.class_chunk_index.clear();
        self.code_hash_cache.clear();

        // 1. Build structural hierarchy: Repo → Project → Module → File
        let repo_chunk = self.build_repo_chunk(repo_id, snapshot_id);
        let project_chunks = self.build_project_chunks(&repo_chunk, snapshot_id);
        self.project_chunks = project_chunks.clone();
        let module_chunks =
            self.build_module_chunks(&project_chunks, file_path, language, snapshot_id);
        let file_chunks = self.build_file_chunks(&module_chunks, file_path, language, snapshot_id);

        // Performance Optimization: Index file chunks for O(1) lookup
        for file_chunk in &file_chunks {
            if let Some(ref path) = file_chunk.file_path {
                self.file_chunk_index
                    .insert(path.clone(), file_chunk.clone());
            }
        }

        // 2. Build symbol hierarchy: Class → Function
        let mut class_chunks =
            self.build_class_chunks(repo_id, &file_chunks, ir_nodes, file_text, snapshot_id);
        let func_chunks = self.build_function_chunks(
            repo_id,
            &mut class_chunks,
            &file_chunks,
            ir_nodes,
            file_text,
            snapshot_id,
        );

        // 3. Build extended chunks: Docstring, Skeleton
        let docstring_chunks = self.build_docstring_chunks(
            repo_id,
            &class_chunks,
            &func_chunks,
            ir_nodes,
            file_text,
            snapshot_id,
        );
        let skeleton_chunks =
            self.build_skeleton_chunks(repo_id, &func_chunks, ir_nodes, file_text, snapshot_id);

        // 4. Build SOTA chunks: Constants, Variables
        let constant_chunks =
            self.build_constant_chunks(repo_id, &file_chunks, ir_nodes, file_text, snapshot_id);
        let variable_chunks =
            self.build_variable_chunks(repo_id, &file_chunks, ir_nodes, file_text, snapshot_id);

        // Collect all chunks
        let mut chunks = vec![repo_chunk];
        chunks.extend(project_chunks);
        chunks.extend(module_chunks);
        chunks.extend(file_chunks);
        chunks.extend(class_chunks);
        chunks.extend(func_chunks);
        chunks.extend(docstring_chunks);
        chunks.extend(skeleton_chunks);
        chunks.extend(constant_chunks);
        chunks.extend(variable_chunks);

        // 5. Build mappings
        let mut chunk_to_ir: ChunkToIR = HashMap::new();
        let chunk_to_graph: ChunkToGraph = HashMap::new();

        for chunk in &chunks {
            if let Some(ref symbol_id) = chunk.symbol_id {
                chunk_to_ir.insert(chunk.chunk_id.clone(), vec![symbol_id.clone()]);
            }
        }

        (chunks, chunk_to_ir, chunk_to_graph)
    }

    // ============================================================
    // Structural Hierarchy: Repo → Project → Module → File
    // ============================================================

    /// Build repository root chunk
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// Repo chunk
    pub fn build_repo_chunk(&mut self, repo_id: &str, snapshot_id: &str) -> Chunk {
        let ctx = ChunkIdContext {
            repo_id,
            kind: "repo",
            fqn: repo_id,
            content_hash: None,
        };
        let chunk_id = self.id_gen.generate(&ctx);

        Chunk {
            chunk_id,
            repo_id: repo_id.to_string(),
            snapshot_id: snapshot_id.to_string(),
            project_id: None,
            module_path: None,
            file_path: None,
            kind: ChunkKind::Repo,
            fqn: repo_id.to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: None, // Root has no parent
            children: Vec::new(),
            language: None,
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }
    }

    /// Build project chunks within repository
    ///
    /// For MVP: Single project per repo. Multi-project support later.
    ///
    /// # Arguments
    /// * `repo_chunk` - Parent repo chunk
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of project chunks
    pub fn build_project_chunks(&mut self, repo_chunk: &Chunk, snapshot_id: &str) -> Vec<Chunk> {
        // MVP: Single default project
        let project_name = "default";
        let ctx = ChunkIdContext {
            repo_id: &repo_chunk.repo_id,
            kind: "project",
            fqn: project_name,
            content_hash: None,
        };
        let chunk_id = self.id_gen.generate(&ctx);

        let project_chunk = Chunk {
            chunk_id: chunk_id.clone(),
            repo_id: repo_chunk.repo_id.clone(),
            snapshot_id: snapshot_id.to_string(),
            project_id: Some(chunk_id.clone()),
            module_path: None,
            file_path: None,
            kind: ChunkKind::Project,
            fqn: project_name.to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: Some(repo_chunk.chunk_id.clone()),
            children: Vec::new(),
            language: None,
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        };

        // Store for later reference (build_file_chunks needs this)
        self.project_chunks = vec![project_chunk.clone()];

        vec![project_chunk]
    }

    /// Build module chunks from file path structure
    ///
    /// Example: "backend/search/retriever.py" → ["backend", "backend.search"]
    ///
    /// # Arguments
    /// * `project_chunks` - Parent project chunks
    /// * `file_path` - File path (relative to repo root)
    /// * `language` - Programming language
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of module chunks
    pub fn build_module_chunks(
        &mut self,
        project_chunks: &[Chunk],
        file_path: &str,
        language: &str,
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        // Extract module hierarchy from path
        // Example: "backend/search/retriever.py" → ["backend", "search"]
        let path = Path::new(file_path);
        let parts: Vec<&str> = path
            .parent()
            .map(|p| p.iter().filter_map(|s| s.to_str()).collect())
            .unwrap_or_default();

        if parts.is_empty() {
            return Vec::new(); // No modules for single-level files
        }

        // Generate module chunks for each directory level
        let mut module_chunks = Vec::new();
        let parent_chunk = &project_chunks[0]; // MVP: Single project
        let mut current_fqn = String::new();
        let mut parent_id = parent_chunk.chunk_id.clone();

        for part in &parts {
            // Build FQN
            if current_fqn.is_empty() {
                current_fqn = part.to_string();
            } else {
                current_fqn = format!("{}.{}", current_fqn, part);
            }

            // Generate chunk ID
            let ctx = ChunkIdContext {
                repo_id: &parent_chunk.repo_id,
                kind: "module",
                fqn: &current_fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Create module chunk
            let module_chunk = Chunk {
                chunk_id: chunk_id.clone(),
                repo_id: parent_chunk.repo_id.clone(),
                snapshot_id: snapshot_id.to_string(),
                project_id: parent_chunk.project_id.clone(),
                module_path: Some(current_fqn.clone()),
                file_path: None,
                kind: ChunkKind::Module,
                fqn: current_fqn.clone(),
                start_line: None,
                end_line: None,
                original_start_line: None,
                original_end_line: None,
                content_hash: None,
                parent_id: Some(parent_id.clone()),
                children: Vec::new(),
                language: Some(language.to_string()),
                symbol_visibility: None,
                symbol_id: None,
                symbol_owner_id: None,
                summary: None,
                importance: None,
                attrs: HashMap::new(),
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: None,
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            parent_id = chunk_id.clone();
            module_chunks.push(module_chunk);
        }

        module_chunks
    }

    /// Build file chunks
    ///
    /// # Arguments
    /// * `module_chunks` - Parent module chunks (empty if no modules)
    /// * `file_path` - File path (relative to repo root)
    /// * `language` - Programming language
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of file chunks (single file for now)
    pub fn build_file_chunks(
        &mut self,
        module_chunks: &[Chunk],
        file_path: &str,
        language: &str,
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        // Get parent (last module or project)
        let parent = if let Some(last_module) = module_chunks.last() {
            last_module
        } else if !self.project_chunks.is_empty() {
            &self.project_chunks[0]
        } else {
            // Should not happen, but handle gracefully
            return Vec::new();
        };

        // Build FQN from file path
        let fqn = FQNBuilder::from_file_path(file_path, language);

        // Generate chunk ID
        let ctx = ChunkIdContext {
            repo_id: &parent.repo_id,
            kind: "file",
            fqn: &fqn,
            content_hash: None,
        };
        let chunk_id = self.id_gen.generate(&ctx);

        let file_chunk = Chunk {
            chunk_id,
            repo_id: parent.repo_id.clone(),
            snapshot_id: snapshot_id.to_string(),
            project_id: parent.project_id.clone(),
            module_path: parent.module_path.clone(),
            file_path: Some(file_path.to_string()),
            kind: ChunkKind::File,
            fqn,
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: Some(parent.chunk_id.clone()),
            children: Vec::new(),
            language: Some(language.to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        };

        vec![file_chunk]
    }

    // ============================================================
    // Symbol Hierarchy: Class → Function Chunks
    // ============================================================

    /// Build class chunks from IR nodes
    ///
    /// MATCHES: _build_class_chunks() in builder.py (lines 495-603)
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `file_chunks` - Parent file chunks for parent lookup
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines for code extraction
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of class chunks
    pub fn build_class_chunks(
        &mut self,
        repo_id: &str,
        file_chunks: &[Chunk],
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        use crate::shared::models::NodeKind;

        let mut class_chunks = Vec::new();

        // Filter class nodes
        let class_nodes: Vec<_> = ir_nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Class)
            .collect();

        for class_node in class_nodes {
            // Find parent file chunk
            let parent_file = match self.find_parent_file_chunk(file_chunks, &class_node.file_path)
            {
                Some(f) => f,
                None => continue,
            };

            // Extract name (required for visibility check)
            let class_name = class_node.name.as_deref().unwrap_or("");

            // Generate chunk ID
            let ctx = ChunkIdContext {
                repo_id,
                kind: "class",
                fqn: &class_node.fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Extract class code for content hash (with caching)
            let span_key = (class_node.span.start_line, class_node.span.end_line);
            let class_code = self.extract_code_span(
                file_text,
                class_node.span.start_line,
                class_node.span.end_line,
            );
            let content_hash = self.compute_content_hash_cached(&class_code, span_key);

            // Extract symbol visibility (static method)
            let symbol_visibility = VisibilityExtractor::extract(
                class_name,
                &class_node.language,
                None, // No attrs yet
            );

            // Detect if test class
            let is_test = self.test_detector.is_test_class(
                class_name,
                &class_node.file_path,
                Some(&class_node.language),
                None, // No decorators yet (would need to extract from attrs)
            );

            // Extract attrs (decorators, base_classes)
            // Note: Node currently doesn't have attrs field - future enhancement
            let chunk_attrs = HashMap::new();

            // Create class chunk
            let class_chunk = Chunk {
                chunk_id: chunk_id.clone(),
                repo_id: repo_id.to_string(),
                snapshot_id: snapshot_id.to_string(),
                project_id: parent_file.project_id.clone(),
                module_path: parent_file.module_path.clone(),
                file_path: Some(class_node.file_path.clone()),
                kind: ChunkKind::Class,
                fqn: class_node.fqn.clone(),
                start_line: Some(class_node.span.start_line),
                end_line: Some(class_node.span.end_line),
                original_start_line: Some(class_node.span.start_line),
                original_end_line: Some(class_node.span.end_line),
                content_hash: Some(content_hash),
                parent_id: Some(parent_file.chunk_id.clone()),
                children: Vec::new(),
                language: Some(class_node.language.clone()),
                symbol_visibility: Some(symbol_visibility.as_str().to_string()),
                symbol_id: Some(class_node.id.clone()),
                symbol_owner_id: Some(class_node.id.clone()),
                summary: None,
                importance: None,
                attrs: chunk_attrs,
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: Some(is_test),
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            // Index for O(1) class lookup by FQN
            self.class_chunk_index
                .insert(class_node.fqn.clone(), class_chunk.clone());

            class_chunks.push(class_chunk);
        }

        class_chunks
    }

    /// Build function/method chunks (leaf chunks)
    ///
    /// MATCHES: _build_function_chunks() in builder.py (lines 605-714)
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `class_chunks` - Parent class chunks (for methods)
    /// * `file_chunks` - Parent file chunks (for top-level functions)
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines for code extraction
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of function chunks
    pub fn build_function_chunks(
        &mut self,
        repo_id: &str,
        class_chunks: &mut [Chunk],
        file_chunks: &[Chunk],
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        use crate::shared::models::NodeKind;

        let mut func_chunks = Vec::new();

        // Filter function/method nodes
        let func_nodes: Vec<_> = ir_nodes
            .iter()
            .filter(|n| matches!(n.kind, NodeKind::Function | NodeKind::Method))
            .collect();

        for func_node in func_nodes {
            // Extract name (required for visibility check)
            let func_name = func_node.name.as_deref().unwrap_or("");

            // Determine parent (class or file)
            let (parent_id, parent_fqn) = if func_node.kind == NodeKind::Method {
                // Find parent class by FQN prefix
                match self.find_parent_class_by_fqn(&func_node.fqn) {
                    Some((pid, pfqn)) => (pid, pfqn),
                    None => continue,
                }
            } else {
                // Top-level function: parent is file
                match self.find_parent_file_chunk(file_chunks, &func_node.file_path) {
                    Some(f) => (f.chunk_id.clone(), f.fqn.clone()),
                    None => continue,
                }
            };

            // Generate chunk ID
            let ctx = ChunkIdContext {
                repo_id,
                kind: "function",
                fqn: &func_node.fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Extract function code for content hash (with caching)
            let span_key = (func_node.span.start_line, func_node.span.end_line);
            let func_code = self.extract_code_span(
                file_text,
                func_node.span.start_line,
                func_node.span.end_line,
            );
            let content_hash = self.compute_content_hash_cached(&func_code, span_key);

            // Extract symbol visibility (static method)
            let symbol_visibility = VisibilityExtractor::extract(
                func_name,
                &func_node.language,
                None, // No attrs yet
            );

            // Detect if test function
            let is_test = self.test_detector.is_test_function(
                func_name,
                &func_node.file_path,
                Some(&func_node.language),
                None, // No decorators yet (would need to extract from attrs)
            );

            // Extract attrs (decorators, params, return_type)
            // Note: Node currently doesn't have attrs field - future enhancement
            let chunk_attrs = HashMap::new();

            // Create function chunk
            let func_chunk = Chunk {
                chunk_id: chunk_id.clone(),
                repo_id: repo_id.to_string(),
                snapshot_id: snapshot_id.to_string(),
                project_id: None,  // Inherit from parent
                module_path: None, // Inherit from parent
                file_path: Some(func_node.file_path.clone()),
                kind: ChunkKind::Function,
                fqn: func_node.fqn.clone(),
                start_line: Some(func_node.span.start_line),
                end_line: Some(func_node.span.end_line),
                original_start_line: Some(func_node.span.start_line),
                original_end_line: Some(func_node.span.end_line),
                content_hash: Some(content_hash),
                parent_id: Some(parent_id.clone()),
                children: Vec::new(),
                language: Some(func_node.language.clone()),
                symbol_visibility: Some(symbol_visibility.as_str().to_string()),
                symbol_id: Some(func_node.id.clone()),
                symbol_owner_id: Some(func_node.id.clone()),
                summary: None,
                importance: None,
                attrs: chunk_attrs,
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: Some(is_test),
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            // Link parent → child
            if func_node.kind == NodeKind::Method {
                // Update class chunk children
                if let Some(class_chunk) = self.class_chunk_index.get_mut(&parent_fqn) {
                    class_chunk.add_child(chunk_id.clone());
                }
                // Also update in class_chunks slice
                for class_chunk in class_chunks.iter_mut() {
                    if class_chunk.fqn == parent_fqn {
                        class_chunk.add_child(chunk_id.clone());
                        break;
                    }
                }
            }

            func_chunks.push(func_chunk);
        }

        func_chunks
    }

    // ============================================================
    // Helper Methods: Parent Lookup
    // ============================================================

    /// Find parent file chunk by file path
    fn find_parent_file_chunk<'a>(
        &self,
        file_chunks: &'a [Chunk],
        file_path: &str,
    ) -> Option<&'a Chunk> {
        file_chunks.iter().find(|c| {
            c.file_path
                .as_ref()
                .map(|p| p == file_path)
                .unwrap_or(false)
        })
    }

    /// Find parent class chunk by FQN prefix
    ///
    /// Example: "myapp.MyClass.my_method" → parent is "myapp.MyClass"
    fn find_parent_class_by_fqn(&self, func_fqn: &str) -> Option<(String, String)> {
        // Split FQN and remove last component (function name)
        let parts: Vec<&str> = func_fqn.split('.').collect();
        if parts.len() < 2 {
            return None;
        }

        let class_fqn = parts[..parts.len() - 1].join(".");

        // Lookup in class index
        self.class_chunk_index
            .get(&class_fqn)
            .map(|c| (c.chunk_id.clone(), c.fqn.clone()))
    }

    // ============================================================
    // Helper Methods: Content Hash & Code Extraction
    // ============================================================

    /// Extract code from file text for a given line range
    ///
    /// # Arguments
    /// * `file_text` - Source code lines (0-indexed)
    /// * `start_line` - Start line (1-indexed, inclusive)
    /// * `end_line` - End line (1-indexed, inclusive)
    ///
    /// # Returns
    /// Extracted code as string
    ///
    /// # Algorithm (matches Python exactly)
    /// - Lines are 1-indexed in span, but list is 0-indexed
    /// - Join lines with newline separator
    fn extract_code_span(&self, file_text: &[String], start_line: u32, end_line: u32) -> String {
        let start_idx = (start_line.saturating_sub(1)) as usize;
        let end_idx = end_line as usize;

        if start_idx >= file_text.len() {
            return String::new();
        }

        file_text[start_idx..end_idx.min(file_text.len())].join("\n")
    }

    /// Compute SHA256 hash for content
    ///
    /// Note: Python uses MD5, but SHA256 is more secure.
    /// For exact Python compatibility, we'd use md5 crate.
    ///
    /// # Arguments
    /// * `content` - Content to hash
    ///
    /// # Returns
    /// SHA256 hexdigest
    fn compute_content_hash(&self, content: &str) -> String {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// Compute content hash with caching
    ///
    /// Performance Optimization: Avoid re-computing hash for same span.
    ///
    /// # Arguments
    /// * `content` - Content to hash
    /// * `span_key` - (start_line, end_line) for cache key
    ///
    /// # Returns
    /// SHA256 hexdigest
    fn compute_content_hash_cached(&mut self, content: &str, span_key: (u32, u32)) -> String {
        if let Some(cached) = self.code_hash_cache.get(&span_key) {
            return cached.clone();
        }

        let hash = self.compute_content_hash(content);
        self.code_hash_cache.insert(span_key, hash.clone());
        hash
    }

    // ============================================================
    // Extended Chunks: Docstring, Skeleton
    // ============================================================

    /// Build docstring chunks from class/function nodes
    ///
    /// Extracts docstrings as separate searchable chunks for API documentation.
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `class_chunks` - Class chunks (for docstring parent)
    /// * `func_chunks` - Function chunks (for docstring parent)
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of docstring chunks
    pub fn build_docstring_chunks(
        &mut self,
        repo_id: &str,
        class_chunks: &[Chunk],
        func_chunks: &[Chunk],
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        use crate::shared::models::NodeKind;

        let mut docstring_chunks = Vec::new();

        // Filter nodes with docstrings
        let nodes_with_docs: Vec<_> = ir_nodes
            .iter()
            .filter(|n| {
                matches!(
                    n.kind,
                    NodeKind::Class | NodeKind::Function | NodeKind::Method
                ) && n.docstring.is_some()
            })
            .collect();

        for node in nodes_with_docs {
            let docstring = match &node.docstring {
                Some(d) => d.clone(),
                None => continue,
            };

            // Find parent chunk (class or function)
            let parent_chunk = class_chunks
                .iter()
                .find(|c| c.fqn == node.fqn)
                .or_else(|| func_chunks.iter().find(|c| c.fqn == node.fqn));

            let parent_id = parent_chunk.map(|c| c.chunk_id.clone());

            // Generate chunk ID
            let fqn = format!("{}.__doc__", node.fqn);
            let ctx = ChunkIdContext {
                repo_id,
                kind: "docstring",
                fqn: &fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Compute content hash
            let content_hash = self.compute_content_hash(&docstring);

            // Estimate docstring line range (typically first few lines after def/class)
            let start_line = node.span.start_line + 1;
            let doc_lines = docstring.lines().count() as u32;
            let end_line = start_line + doc_lines;

            let docstring_chunk = Chunk {
                chunk_id,
                repo_id: repo_id.to_string(),
                snapshot_id: snapshot_id.to_string(),
                project_id: parent_chunk.and_then(|c| c.project_id.clone()),
                module_path: parent_chunk.and_then(|c| c.module_path.clone()),
                file_path: Some(node.file_path.clone()),
                kind: ChunkKind::Docstring,
                fqn,
                start_line: Some(start_line),
                end_line: Some(end_line),
                original_start_line: Some(start_line),
                original_end_line: Some(end_line),
                content_hash: Some(content_hash),
                parent_id,
                children: Vec::new(),
                language: Some(node.language.clone()),
                symbol_visibility: None,
                symbol_id: Some(node.id.clone()),
                symbol_owner_id: Some(node.id.clone()),
                summary: Some(docstring.lines().next().unwrap_or("").to_string()),
                importance: Some(0.7), // Docstrings are important for search
                attrs: HashMap::new(),
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: None,
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            docstring_chunks.push(docstring_chunk);
        }

        docstring_chunks
    }

    /// Build skeleton chunks (function signatures without body)
    ///
    /// Useful for API browsing and code completion context.
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `func_chunks` - Function chunks
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of skeleton chunks
    pub fn build_skeleton_chunks(
        &mut self,
        repo_id: &str,
        func_chunks: &[Chunk],
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        use crate::shared::models::NodeKind;

        let mut skeleton_chunks = Vec::new();

        // Filter function/method nodes
        let func_nodes: Vec<_> = ir_nodes
            .iter()
            .filter(|n| matches!(n.kind, NodeKind::Function | NodeKind::Method))
            .collect();

        for func_node in func_nodes {
            // Find corresponding function chunk
            let parent_chunk = func_chunks.iter().find(|c| c.fqn == func_node.fqn);
            let parent_id = parent_chunk.map(|c| c.chunk_id.clone());

            // Extract signature (first line only)
            let signature = self.extract_code_span(
                file_text,
                func_node.span.start_line,
                func_node.span.start_line,
            );

            if signature.is_empty() {
                continue;
            }

            // Generate chunk ID
            let fqn = format!("{}.__signature__", func_node.fqn);
            let ctx = ChunkIdContext {
                repo_id,
                kind: "skeleton",
                fqn: &fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Compute content hash
            let content_hash = self.compute_content_hash(&signature);

            let skeleton_chunk = Chunk {
                chunk_id,
                repo_id: repo_id.to_string(),
                snapshot_id: snapshot_id.to_string(),
                project_id: parent_chunk.and_then(|c| c.project_id.clone()),
                module_path: parent_chunk.and_then(|c| c.module_path.clone()),
                file_path: Some(func_node.file_path.clone()),
                kind: ChunkKind::Skeleton,
                fqn,
                start_line: Some(func_node.span.start_line),
                end_line: Some(func_node.span.start_line),
                original_start_line: Some(func_node.span.start_line),
                original_end_line: Some(func_node.span.start_line),
                content_hash: Some(content_hash),
                parent_id,
                children: Vec::new(),
                language: Some(func_node.language.clone()),
                symbol_visibility: None,
                symbol_id: Some(func_node.id.clone()),
                symbol_owner_id: Some(func_node.id.clone()),
                summary: Some(signature.trim().to_string()),
                importance: Some(0.5), // Signatures are moderately important
                attrs: HashMap::new(),
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: None,
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            skeleton_chunks.push(skeleton_chunk);
        }

        skeleton_chunks
    }

    // ============================================================
    // SOTA Chunks: Constants, Variables
    // ============================================================

    /// Check if a name follows Python constant naming convention (UPPER_CASE)
    ///
    /// # Rules
    /// - Must be at least 2 characters
    /// - First character must be uppercase letter
    /// - All characters must be uppercase letters, underscores, or digits
    /// - Examples: `MAX_SIZE`, `API_KEY`, `VERSION_2` are constants
    /// - Examples: `_PRIVATE`, `x`, `Config`, `my_var` are NOT constants
    fn is_constant_name(name: &str) -> bool {
        if name.len() < 2 {
            return false;
        }

        let mut chars = name.chars();

        // First character must be uppercase letter (not _, not digit)
        match chars.next() {
            Some(c) if c.is_ascii_uppercase() => {}
            _ => return false,
        }

        // Rest must be uppercase, underscore, or digit
        chars.all(|c| c.is_ascii_uppercase() || c == '_' || c.is_ascii_digit())
    }

    /// Build constant chunks (module-level constants)
    ///
    /// Constants are important for understanding configuration and magic values.
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `file_chunks` - File chunks (for parent)
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of constant chunks
    pub fn build_constant_chunks(
        &mut self,
        repo_id: &str,
        file_chunks: &[Chunk],
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        use crate::shared::models::NodeKind;

        let mut constant_chunks = Vec::new();

        // Filter constant nodes (Variable kind with UPPER_CASE naming convention)
        let constant_nodes: Vec<_> = ir_nodes
            .iter()
            .filter(|n| {
                n.kind == NodeKind::Variable
                    && n.name
                        .as_ref()
                        .map(|name| Self::is_constant_name(name))
                        .unwrap_or(false)
            })
            .collect();

        for const_node in constant_nodes {
            // Find parent file chunk
            let parent_file = match self.find_parent_file_chunk(file_chunks, &const_node.file_path)
            {
                Some(f) => f,
                None => continue,
            };

            let const_name = const_node.name.as_deref().unwrap_or("");

            // Generate chunk ID
            let ctx = ChunkIdContext {
                repo_id,
                kind: "constant",
                fqn: &const_node.fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Extract constant code
            let const_code = self.extract_code_span(
                file_text,
                const_node.span.start_line,
                const_node.span.end_line,
            );
            let span_key = (const_node.span.start_line, const_node.span.end_line);
            let content_hash = self.compute_content_hash_cached(&const_code, span_key);

            let constant_chunk = Chunk {
                chunk_id,
                repo_id: repo_id.to_string(),
                snapshot_id: snapshot_id.to_string(),
                project_id: parent_file.project_id.clone(),
                module_path: parent_file.module_path.clone(),
                file_path: Some(const_node.file_path.clone()),
                kind: ChunkKind::Constant,
                fqn: const_node.fqn.clone(),
                start_line: Some(const_node.span.start_line),
                end_line: Some(const_node.span.end_line),
                original_start_line: Some(const_node.span.start_line),
                original_end_line: Some(const_node.span.end_line),
                content_hash: Some(content_hash),
                parent_id: Some(parent_file.chunk_id.clone()),
                children: Vec::new(),
                language: Some(const_node.language.clone()),
                symbol_visibility: Some("public".to_string()), // Constants are usually public
                symbol_id: Some(const_node.id.clone()),
                symbol_owner_id: Some(const_node.id.clone()),
                summary: Some(format!("{} = ...", const_name)),
                importance: Some(0.6), // Constants are moderately important
                attrs: HashMap::new(),
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: None,
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            constant_chunks.push(constant_chunk);
        }

        constant_chunks
    }

    /// Build variable chunks (module-level variables)
    ///
    /// Module-level variables are important for understanding state.
    /// Excludes constants (UPPER_CASE names) to avoid duplication.
    ///
    /// # Arguments
    /// * `repo_id` - Repository identifier
    /// * `file_chunks` - File chunks (for parent)
    /// * `ir_nodes` - IR nodes from IRBuilder
    /// * `file_text` - Source code lines
    /// * `snapshot_id` - Git commit hash or timestamp
    ///
    /// # Returns
    /// List of variable chunks
    pub fn build_variable_chunks(
        &mut self,
        repo_id: &str,
        file_chunks: &[Chunk],
        ir_nodes: &[crate::shared::models::Node],
        file_text: &[String],
        snapshot_id: &str,
    ) -> Vec<Chunk> {
        use crate::shared::models::NodeKind;

        let mut variable_chunks = Vec::new();

        // Filter variable nodes (non-constant module-level variables)
        let var_nodes: Vec<_> = ir_nodes
            .iter()
            .filter(|n| {
                n.kind == NodeKind::Variable
                    && n.parent_id.is_none() // Module-level (no parent)
                    && n.name
                        .as_ref()
                        .map(|name| !Self::is_constant_name(name)) // Exclude constants
                        .unwrap_or(true)
            })
            .collect();

        for var_node in var_nodes {
            // Find parent file chunk
            let parent_file = match self.find_parent_file_chunk(file_chunks, &var_node.file_path) {
                Some(f) => f,
                None => continue,
            };

            let var_name = var_node.name.as_deref().unwrap_or("");

            // Skip private variables (starting with _)
            if var_name.starts_with('_') && !var_name.starts_with("__") {
                continue;
            }

            // Generate chunk ID
            let ctx = ChunkIdContext {
                repo_id,
                kind: "variable",
                fqn: &var_node.fqn,
                content_hash: None,
            };
            let chunk_id = self.id_gen.generate(&ctx);

            // Extract variable code
            let var_code =
                self.extract_code_span(file_text, var_node.span.start_line, var_node.span.end_line);
            let span_key = (var_node.span.start_line, var_node.span.end_line);
            let content_hash = self.compute_content_hash_cached(&var_code, span_key);

            // Determine visibility
            let visibility = if var_name.starts_with("__") {
                "private"
            } else if var_name.starts_with('_') {
                "internal"
            } else {
                "public"
            };

            let variable_chunk = Chunk {
                chunk_id,
                repo_id: repo_id.to_string(),
                snapshot_id: snapshot_id.to_string(),
                project_id: parent_file.project_id.clone(),
                module_path: parent_file.module_path.clone(),
                file_path: Some(var_node.file_path.clone()),
                kind: ChunkKind::Variable,
                fqn: var_node.fqn.clone(),
                start_line: Some(var_node.span.start_line),
                end_line: Some(var_node.span.end_line),
                original_start_line: Some(var_node.span.start_line),
                original_end_line: Some(var_node.span.end_line),
                content_hash: Some(content_hash),
                parent_id: Some(parent_file.chunk_id.clone()),
                children: Vec::new(),
                language: Some(var_node.language.clone()),
                symbol_visibility: Some(visibility.to_string()),
                symbol_id: Some(var_node.id.clone()),
                symbol_owner_id: Some(var_node.id.clone()),
                summary: Some(format!("{} = ...", var_name)),
                importance: Some(0.4), // Variables are less important than functions
                attrs: HashMap::new(),
                version: 1,
                last_indexed_commit: None,
                is_deleted: false,
                local_seq: 0,
                is_test: None,
                is_overlay: false,
                overlay_session_id: None,
                base_chunk_id: None,
            };

            variable_chunks.push(variable_chunk);
        }

        variable_chunks
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builder_creation() {
        let id_gen = ChunkIdGenerator::new();
        let builder = ChunkBuilder::new(id_gen);
        assert_eq!(builder.chunks.len(), 0);
    }

    #[test]
    fn test_build_repo_chunk() {
        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let chunk = builder.build_repo_chunk("myrepo", "abc123");
        assert_eq!(chunk.repo_id, "myrepo");
        assert_eq!(chunk.snapshot_id, "abc123");
        assert_eq!(chunk.kind, ChunkKind::Repo);
        assert_eq!(chunk.fqn, "myrepo");
        assert!(chunk.parent_id.is_none());
    }

    #[test]
    fn test_build_project_chunks() {
        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let repo_chunk = builder.build_repo_chunk("myrepo", "abc123");
        let projects = builder.build_project_chunks(&repo_chunk, "abc123");

        assert_eq!(projects.len(), 1);
        assert_eq!(projects[0].kind, ChunkKind::Project);
        assert_eq!(projects[0].fqn, "default");
        assert_eq!(projects[0].parent_id, Some(repo_chunk.chunk_id));
    }

    #[test]
    fn test_build_module_chunks() {
        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let repo_chunk = builder.build_repo_chunk("myrepo", "abc123");
        let projects = builder.build_project_chunks(&repo_chunk, "abc123");

        let modules = builder.build_module_chunks(
            &projects,
            "backend/search/retriever.py",
            "python",
            "abc123",
        );

        assert_eq!(modules.len(), 2);
        assert_eq!(modules[0].fqn, "backend");
        assert_eq!(modules[1].fqn, "backend.search");
        assert_eq!(modules[0].kind, ChunkKind::Module);
    }

    #[test]
    fn test_build_file_chunks() {
        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let repo_chunk = builder.build_repo_chunk("myrepo", "abc123");
        let projects = builder.build_project_chunks(&repo_chunk, "abc123");
        builder.project_chunks = projects.clone();

        let modules = builder.build_module_chunks(
            &projects,
            "backend/search/retriever.py",
            "python",
            "abc123",
        );

        let files =
            builder.build_file_chunks(&modules, "backend/search/retriever.py", "python", "abc123");

        assert_eq!(files.len(), 1);
        assert_eq!(files[0].kind, ChunkKind::File);
        assert_eq!(
            files[0].file_path,
            Some("backend/search/retriever.py".to_string())
        );
        assert_eq!(files[0].fqn, "backend.search.retriever");
    }

    #[test]
    fn test_full_hierarchy() {
        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let (chunks, _, _) = builder.build(
            "myrepo",
            "backend/search/retriever.py",
            "python",
            Some("abc123"),
        );

        // Repo + Project + Module(2) + File = 5 chunks
        assert_eq!(chunks.len(), 5);

        // Check hierarchy
        assert_eq!(chunks[0].kind, ChunkKind::Repo);
        assert_eq!(chunks[1].kind, ChunkKind::Project);
        assert_eq!(chunks[2].kind, ChunkKind::Module);
        assert_eq!(chunks[3].kind, ChunkKind::Module);
        assert_eq!(chunks[4].kind, ChunkKind::File);
    }

    #[test]
    fn test_extract_code_span() {
        let id_gen = ChunkIdGenerator::new();
        let builder = ChunkBuilder::new(id_gen);

        let file_text = vec![
            "line 1".to_string(),
            "line 2".to_string(),
            "line 3".to_string(),
            "line 4".to_string(),
        ];

        // Extract lines 2-3 (1-indexed)
        let code = builder.extract_code_span(&file_text, 2, 3);
        assert_eq!(code, "line 2\nline 3");

        // Extract single line
        let code = builder.extract_code_span(&file_text, 1, 1);
        assert_eq!(code, "line 1");

        // Extract all lines
        let code = builder.extract_code_span(&file_text, 1, 4);
        assert_eq!(code, "line 1\nline 2\nline 3\nline 4");
    }

    #[test]
    fn test_compute_content_hash() {
        let id_gen = ChunkIdGenerator::new();
        let builder = ChunkBuilder::new(id_gen);

        let content = "def foo():\n    pass";
        let hash1 = builder.compute_content_hash(content);
        let hash2 = builder.compute_content_hash(content);

        // Same content should produce same hash
        assert_eq!(hash1, hash2);

        // Different content should produce different hash
        let hash3 = builder.compute_content_hash("def bar():\n    pass");
        assert_ne!(hash1, hash3);

        // Hash should be 64 chars (SHA256 hex)
        assert_eq!(hash1.len(), 64);
    }

    #[test]
    fn test_compute_content_hash_cached() {
        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let content = "def foo():\n    pass";
        let span_key = (10, 11);

        // First call - compute and cache
        let hash1 = builder.compute_content_hash_cached(content, span_key);
        assert_eq!(builder.code_hash_cache.len(), 1);

        // Second call - use cache
        let hash2 = builder.compute_content_hash_cached(content, span_key);
        assert_eq!(hash1, hash2);
        assert_eq!(builder.code_hash_cache.len(), 1); // Still 1 entry

        // Different span - new cache entry
        let hash3 = builder.compute_content_hash_cached("different", (20, 21));
        assert_ne!(hash1, hash3);
        assert_eq!(builder.code_hash_cache.len(), 2);
    }

    #[test]
    fn test_build_class_chunks() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Setup: Create file chunk
        let file_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:file:myapp.models".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            project_id: Some("default".to_string()),
            module_path: Some("myapp".to_string()),
            file_path: Some("myapp/models.py".to_string()),
            kind: ChunkKind::File,
            fqn: "myapp.models".to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: Some("parent".to_string()),
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        // Setup: Create IR nodes
        let ir_nodes = vec![Node {
            id: "node:class:myapp.models.User".to_string(),
            kind: NodeKind::Class,
            fqn: "myapp.models.User".to_string(),
            file_path: "myapp/models.py".to_string(),
            span: Span::new(10, 0, 20, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("User".to_string()),
            module_path: Some("myapp.models".to_string()),
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }];

        let file_text = vec!["class User:".to_string(), "    pass".to_string()];

        // Execute
        let class_chunks =
            builder.build_class_chunks("myrepo", &file_chunks, &ir_nodes, &file_text, "abc123");

        // Verify
        assert_eq!(class_chunks.len(), 1);
        assert_eq!(class_chunks[0].kind, ChunkKind::Class);
        assert_eq!(class_chunks[0].fqn, "myapp.models.User");
        assert_eq!(class_chunks[0].start_line, Some(10));
        assert_eq!(class_chunks[0].end_line, Some(20));
        assert_eq!(
            class_chunks[0].parent_id,
            Some("chunk:myrepo:file:myapp.models".to_string())
        );
        assert!(class_chunks[0].content_hash.is_some());
        assert_eq!(
            class_chunks[0].symbol_id,
            Some("node:class:myapp.models.User".to_string())
        );
    }

    #[test]
    fn test_build_function_chunks() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Setup: Create file chunk
        let file_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:file:myapp.utils".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            project_id: Some("default".to_string()),
            module_path: Some("myapp".to_string()),
            file_path: Some("myapp/utils.py".to_string()),
            kind: ChunkKind::File,
            fqn: "myapp.utils".to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: Some("parent".to_string()),
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        // Setup: Create IR nodes
        let ir_nodes = vec![Node {
            id: "node:func:myapp.utils.helper".to_string(),
            kind: NodeKind::Function,
            fqn: "myapp.utils.helper".to_string(),
            file_path: "myapp/utils.py".to_string(),
            span: Span::new(5, 0, 10, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("helper".to_string()),
            module_path: Some("myapp.utils".to_string()),
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }];

        let file_text = vec!["def helper():".to_string(), "    pass".to_string()];

        // Execute
        let mut class_chunks = vec![];
        let func_chunks = builder.build_function_chunks(
            "myrepo",
            &mut class_chunks,
            &file_chunks,
            &ir_nodes,
            &file_text,
            "abc123",
        );

        // Verify
        assert_eq!(func_chunks.len(), 1);
        assert_eq!(func_chunks[0].kind, ChunkKind::Function);
        assert_eq!(func_chunks[0].fqn, "myapp.utils.helper");
        assert_eq!(func_chunks[0].start_line, Some(5));
        assert_eq!(func_chunks[0].end_line, Some(10));
        assert_eq!(
            func_chunks[0].parent_id,
            Some("chunk:myrepo:file:myapp.utils".to_string())
        );
        assert!(func_chunks[0].content_hash.is_some());
        assert_eq!(
            func_chunks[0].symbol_id,
            Some("node:func:myapp.utils.helper".to_string())
        );
    }

    #[test]
    fn test_build_method_chunks() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Setup: Create file chunk
        let file_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:file:myapp.models".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            project_id: Some("default".to_string()),
            module_path: Some("myapp".to_string()),
            file_path: Some("myapp/models.py".to_string()),
            kind: ChunkKind::File,
            fqn: "myapp.models".to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: Some("parent".to_string()),
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        // Setup: Create class chunk first
        let class_ir = vec![Node {
            id: "node:class:myapp.models.User".to_string(),
            kind: NodeKind::Class,
            fqn: "myapp.models.User".to_string(),
            file_path: "myapp/models.py".to_string(),
            span: Span::new(10, 0, 30, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("User".to_string()),
            module_path: Some("myapp.models".to_string()),
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }];

        let file_text = vec![
            "class User:".to_string(),
            "    def save(self):".to_string(),
            "        pass".to_string(),
        ];

        let mut class_chunks =
            builder.build_class_chunks("myrepo", &file_chunks, &class_ir, &file_text, "abc123");

        // Setup: Create method IR node
        let method_ir = vec![Node {
            id: "node:method:myapp.models.User.save".to_string(),
            kind: NodeKind::Method,
            fqn: "myapp.models.User.save".to_string(),
            file_path: "myapp/models.py".to_string(),
            span: Span::new(15, 0, 20, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("save".to_string()),
            module_path: Some("myapp.models".to_string()),
            parent_id: Some("node:class:myapp.models.User".to_string()),
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }];

        // Execute
        let func_chunks = builder.build_function_chunks(
            "myrepo",
            &mut class_chunks,
            &file_chunks,
            &method_ir,
            &file_text,
            "abc123",
        );

        // Verify
        assert_eq!(func_chunks.len(), 1);
        assert_eq!(func_chunks[0].kind, ChunkKind::Function);
        assert_eq!(func_chunks[0].fqn, "myapp.models.User.save");
        assert_eq!(func_chunks[0].start_line, Some(15));
        assert_eq!(func_chunks[0].end_line, Some(20));
        // Parent should be the class chunk
        assert!(func_chunks[0].parent_id.is_some());
        assert_eq!(
            func_chunks[0].symbol_id,
            Some("node:method:myapp.models.User.save".to_string())
        );

        // Verify parent-child relationship
        assert!(class_chunks[0].children.contains(&func_chunks[0].chunk_id));
    }

    #[test]
    fn test_build_with_ir_full_hierarchy() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Setup: Create IR nodes (class + method + constant)
        let ir_nodes = vec![
            Node {
                id: "node:class:myapp.models.User".to_string(),
                kind: NodeKind::Class,
                fqn: "myapp.models.User".to_string(),
                file_path: "myapp/models.py".to_string(),
                span: Span::new(3, 0, 8, 0),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("User".to_string()),
                module_path: Some("myapp.models".to_string()),
                parent_id: None,
                body_span: None,
                docstring: Some("User model for authentication".to_string()),
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
            Node {
                id: "node:method:myapp.models.User.save".to_string(),
                kind: NodeKind::Method,
                fqn: "myapp.models.User.save".to_string(),
                file_path: "myapp/models.py".to_string(),
                span: Span::new(6, 0, 8, 0),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("save".to_string()),
                module_path: Some("myapp.models".to_string()),
                parent_id: Some("node:class:myapp.models.User".to_string()),
                body_span: None,
                docstring: Some("Save user to database".to_string()),
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
            Node {
                id: "node:var:myapp.models.MAX_USERS".to_string(),
                kind: NodeKind::Variable,
                fqn: "myapp.models.MAX_USERS".to_string(),
                file_path: "myapp/models.py".to_string(),
                span: Span::new(1, 0, 1, 15),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("MAX_USERS".to_string()),
                module_path: Some("myapp.models".to_string()),
                parent_id: None,
                body_span: None,
                docstring: None,
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
        ];

        let file_text = vec![
            "MAX_USERS = 100".to_string(),
            "".to_string(),
            "class User:".to_string(),
            "    \"\"\"User model for authentication\"\"\"".to_string(),
            "    ".to_string(),
            "    def save(self):".to_string(),
            "        \"\"\"Save user to database\"\"\"".to_string(),
            "        pass".to_string(),
        ];

        // Execute
        let (chunks, chunk_to_ir, _) = builder.build_with_ir(
            "myrepo",
            "myapp/models.py",
            "python",
            &ir_nodes,
            &file_text,
            Some("abc123"),
        );

        // Verify structure
        // Repo + Project + Module + File + Class + Method + 2 Docstrings + 1 Skeleton + 1 Constant
        assert!(
            chunks.len() >= 5,
            "Expected at least 5 chunks, got {}",
            chunks.len()
        );

        // Count chunk kinds
        let class_count = chunks.iter().filter(|c| c.kind == ChunkKind::Class).count();
        let func_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Function)
            .count();
        let docstring_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Docstring)
            .count();
        let skeleton_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Skeleton)
            .count();
        let constant_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Constant)
            .count();

        assert_eq!(class_count, 1, "Should have 1 class chunk");
        assert_eq!(func_count, 1, "Should have 1 function chunk");
        assert_eq!(
            docstring_count, 2,
            "Should have 2 docstring chunks (class + method)"
        );
        assert_eq!(skeleton_count, 1, "Should have 1 skeleton chunk");
        assert_eq!(
            constant_count, 1,
            "Should have 1 constant chunk (MAX_USERS)"
        );

        // Verify mappings
        assert!(!chunk_to_ir.is_empty(), "Should have chunk-to-IR mappings");
    }

    /// Helper function to create a test Node with minimal fields
    fn create_test_node(
        id: &str,
        kind: crate::shared::models::NodeKind,
        fqn: &str,
        file_path: &str,
        span: crate::shared::models::Span,
        name: Option<&str>,
    ) -> crate::shared::models::Node {
        crate::shared::models::Node {
            id: id.to_string(),
            kind,
            fqn: fqn.to_string(),
            file_path: file_path.to_string(),
            span,
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: name.map(|s| s.to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }
    }

    #[test]
    fn test_build_constant_chunks() {
        use crate::shared::models::{NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Setup: Create file chunk
        let file_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:file:config".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            project_id: Some("default".to_string()),
            module_path: Some("config".to_string()),
            file_path: Some("config.py".to_string()),
            kind: ChunkKind::File,
            fqn: "config".to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: None,
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        // Setup: Create constant nodes
        let ir_nodes = vec![
            create_test_node(
                "node:var:config.MAX_SIZE",
                NodeKind::Variable,
                "config.MAX_SIZE",
                "config.py",
                Span::new(1, 0, 1, 20),
                Some("MAX_SIZE"),
            ),
            create_test_node(
                "node:var:config.DEBUG_MODE",
                NodeKind::Variable,
                "config.DEBUG_MODE",
                "config.py",
                Span::new(2, 0, 2, 25),
                Some("DEBUG_MODE"),
            ),
            // This should NOT be a constant (lowercase)
            create_test_node(
                "node:var:config.default_value",
                NodeKind::Variable,
                "config.default_value",
                "config.py",
                Span::new(3, 0, 3, 30),
                Some("default_value"),
            ),
        ];

        let file_text = vec![
            "MAX_SIZE = 1024".to_string(),
            "DEBUG_MODE = True".to_string(),
            "default_value = None".to_string(),
        ];

        // Execute
        let constant_chunks =
            builder.build_constant_chunks("myrepo", &file_chunks, &ir_nodes, &file_text, "abc123");

        // Verify - only UPPER_CASE variables should be constants
        assert_eq!(constant_chunks.len(), 2, "Should have 2 constant chunks");

        let fqns: Vec<_> = constant_chunks.iter().map(|c| c.fqn.as_str()).collect();
        assert!(fqns.contains(&"config.MAX_SIZE"));
        assert!(fqns.contains(&"config.DEBUG_MODE"));
        assert!(!fqns.iter().any(|f| f.contains("default_value")));

        // Verify chunk properties
        for chunk in &constant_chunks {
            assert_eq!(chunk.kind, ChunkKind::Constant);
            assert!(chunk.content_hash.is_some());
            assert_eq!(
                chunk.parent_id,
                Some("chunk:myrepo:file:config".to_string())
            );
        }
    }

    #[test]
    fn test_build_docstring_chunks() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Setup: Create function chunk
        let func_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:function:utils.helper".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            project_id: Some("default".to_string()),
            module_path: Some("utils".to_string()),
            file_path: Some("utils.py".to_string()),
            kind: ChunkKind::Function,
            fqn: "utils.helper".to_string(),
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: None,
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        // Setup: Create IR node with docstring
        let ir_nodes = vec![Node {
            id: "node:func:utils.helper".to_string(),
            kind: NodeKind::Function,
            fqn: "utils.helper".to_string(),
            file_path: "utils.py".to_string(),
            span: Span::new(1, 0, 5, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("helper".to_string()),
            module_path: None,
            parent_id: None,
            body_span: None,
            docstring: Some("This is a helper function.\n\nIt does useful things.".to_string()),
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }];

        let file_text = vec![
            "def helper():".to_string(),
            "    \"\"\"This is a helper function.".to_string(),
            "    ".to_string(),
            "    It does useful things.\"\"\"".to_string(),
            "    pass".to_string(),
        ];

        // Execute
        let docstring_chunks = builder.build_docstring_chunks(
            "myrepo",
            &[], // No class chunks
            &func_chunks,
            &ir_nodes,
            &file_text,
            "abc123",
        );

        // Verify
        assert_eq!(docstring_chunks.len(), 1, "Should have 1 docstring chunk");
        assert_eq!(docstring_chunks[0].kind, ChunkKind::Docstring);
        assert_eq!(docstring_chunks[0].fqn, "utils.helper.__doc__");
        assert!(docstring_chunks[0].content_hash.is_some());
        assert_eq!(docstring_chunks[0].importance, Some(0.7));

        // Summary should be first line of docstring
        assert_eq!(
            docstring_chunks[0].summary,
            Some("This is a helper function.".to_string())
        );
    }

    // ============================================================
    // SOTA L11 Edge Case Tests
    // ============================================================

    #[test]
    fn test_is_constant_name_edge_cases() {
        // Valid constants
        assert!(ChunkBuilder::is_constant_name("MAX_SIZE"));
        assert!(ChunkBuilder::is_constant_name("API_KEY"));
        assert!(ChunkBuilder::is_constant_name("VERSION_2"));
        assert!(ChunkBuilder::is_constant_name("AA"));
        assert!(ChunkBuilder::is_constant_name("A1"));
        assert!(ChunkBuilder::is_constant_name("AB"));
        assert!(ChunkBuilder::is_constant_name("HTTP_200_OK"));

        // Invalid constants - too short
        assert!(!ChunkBuilder::is_constant_name("A"));
        assert!(!ChunkBuilder::is_constant_name(""));

        // Invalid constants - starts with underscore
        assert!(!ChunkBuilder::is_constant_name("_PRIVATE"));
        assert!(!ChunkBuilder::is_constant_name("__DUNDER__"));
        assert!(!ChunkBuilder::is_constant_name("_"));
        assert!(!ChunkBuilder::is_constant_name("__"));

        // Invalid constants - starts with digit
        assert!(!ChunkBuilder::is_constant_name("1A"));
        assert!(!ChunkBuilder::is_constant_name("123_ABC"));

        // Invalid constants - lowercase
        assert!(!ChunkBuilder::is_constant_name("config"));
        assert!(!ChunkBuilder::is_constant_name("myVar"));
        assert!(!ChunkBuilder::is_constant_name("Camel_Case"));

        // Edge cases
        assert!(!ChunkBuilder::is_constant_name("aA")); // starts lowercase
        assert!(!ChunkBuilder::is_constant_name("_A")); // starts with underscore
    }

    #[test]
    fn test_empty_ir_nodes() {
        use crate::shared::models::Span;

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let file_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:file:empty".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            kind: ChunkKind::File,
            fqn: "empty".to_string(),
            file_path: Some("empty.py".to_string()),
            project_id: Some("default".to_string()),
            module_path: None,
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: None,
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        let empty_ir_nodes: Vec<crate::shared::models::Node> = vec![];
        let file_text: Vec<String> = vec![];

        // Test each builder with empty inputs
        let constants = builder.build_constant_chunks(
            "myrepo",
            &file_chunks,
            &empty_ir_nodes,
            &file_text,
            "abc123",
        );
        assert!(
            constants.is_empty(),
            "Empty IR nodes should produce empty constants"
        );

        let variables = builder.build_variable_chunks(
            "myrepo",
            &file_chunks,
            &empty_ir_nodes,
            &file_text,
            "abc123",
        );
        assert!(
            variables.is_empty(),
            "Empty IR nodes should produce empty variables"
        );

        let skeletons =
            builder.build_skeleton_chunks("myrepo", &[], &empty_ir_nodes, &file_text, "abc123");
        assert!(
            skeletons.is_empty(),
            "Empty IR nodes should produce empty skeletons"
        );

        let docstrings = builder.build_docstring_chunks(
            "myrepo",
            &[],
            &[],
            &empty_ir_nodes,
            &file_text,
            "abc123",
        );
        assert!(
            docstrings.is_empty(),
            "Empty IR nodes should produce empty docstrings"
        );
    }

    #[test]
    fn test_variable_excludes_constants() {
        use crate::shared::models::{NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let file_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:file:mixed".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            kind: ChunkKind::File,
            fqn: "mixed".to_string(),
            file_path: Some("mixed.py".to_string()),
            project_id: Some("default".to_string()),
            module_path: None,
            start_line: None,
            end_line: None,
            original_start_line: None,
            original_end_line: None,
            content_hash: None,
            parent_id: None,
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        // Create mixed nodes: some constants, some variables
        let ir_nodes = vec![
            create_test_node(
                "n1",
                NodeKind::Variable,
                "mixed.MAX_SIZE",
                "mixed.py",
                Span::new(1, 0, 1, 20),
                Some("MAX_SIZE"),
            ),
            create_test_node(
                "n2",
                NodeKind::Variable,
                "mixed.config",
                "mixed.py",
                Span::new(2, 0, 2, 20),
                Some("config"),
            ),
            create_test_node(
                "n3",
                NodeKind::Variable,
                "mixed.API_KEY",
                "mixed.py",
                Span::new(3, 0, 3, 20),
                Some("API_KEY"),
            ),
            create_test_node(
                "n4",
                NodeKind::Variable,
                "mixed.debug_mode",
                "mixed.py",
                Span::new(4, 0, 4, 20),
                Some("debug_mode"),
            ),
        ];

        let file_text = vec![
            "MAX_SIZE = 100".to_string(),
            "config = {}".to_string(),
            "API_KEY = 'secret'".to_string(),
            "debug_mode = False".to_string(),
        ];

        // Build constants
        let constants =
            builder.build_constant_chunks("myrepo", &file_chunks, &ir_nodes, &file_text, "abc123");
        let constant_fqns: Vec<_> = constants.iter().map(|c| c.fqn.as_str()).collect();

        // Build variables
        let variables =
            builder.build_variable_chunks("myrepo", &file_chunks, &ir_nodes, &file_text, "abc123");
        let variable_fqns: Vec<_> = variables.iter().map(|c| c.fqn.as_str()).collect();

        // Verify no overlap
        assert_eq!(
            constants.len(),
            2,
            "Should have 2 constants (MAX_SIZE, API_KEY)"
        );
        assert!(constant_fqns.contains(&"mixed.MAX_SIZE"));
        assert!(constant_fqns.contains(&"mixed.API_KEY"));

        assert_eq!(
            variables.len(),
            2,
            "Should have 2 variables (config, debug_mode)"
        );
        assert!(variable_fqns.contains(&"mixed.config"));
        assert!(variable_fqns.contains(&"mixed.debug_mode"));

        // Verify no overlap between constants and variables
        for cfqn in &constant_fqns {
            assert!(
                !variable_fqns.contains(cfqn),
                "Variable should not contain constant: {}",
                cfqn
            );
        }
    }

    #[test]
    fn test_build_with_ir_integration() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        // Create comprehensive IR nodes
        let ir_nodes = vec![
            // Class with docstring
            Node {
                id: "node:class:mymodule.MyClass".to_string(),
                kind: NodeKind::Class,
                fqn: "mymodule.MyClass".to_string(),
                file_path: "mymodule/core.py".to_string(),
                span: Span::new(5, 0, 30, 0),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("MyClass".to_string()),
                module_path: Some("mymodule.core".to_string()),
                parent_id: None,
                body_span: None,
                docstring: Some("A sample class.".to_string()),
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
            // Method
            Node {
                id: "node:method:mymodule.MyClass.process".to_string(),
                kind: NodeKind::Method,
                fqn: "mymodule.MyClass.process".to_string(),
                file_path: "mymodule/core.py".to_string(),
                span: Span::new(10, 0, 20, 0),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("process".to_string()),
                module_path: Some("mymodule.core".to_string()),
                parent_id: Some("node:class:mymodule.MyClass".to_string()),
                body_span: None,
                docstring: Some("Process data.".to_string()),
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
            // Constant
            Node {
                id: "node:var:mymodule.DEFAULT_TIMEOUT".to_string(),
                kind: NodeKind::Variable,
                fqn: "mymodule.DEFAULT_TIMEOUT".to_string(),
                file_path: "mymodule/core.py".to_string(),
                span: Span::new(1, 0, 1, 25),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("DEFAULT_TIMEOUT".to_string()),
                module_path: Some("mymodule.core".to_string()),
                parent_id: None,
                body_span: None,
                docstring: None,
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
            // Variable (not constant)
            Node {
                id: "node:var:mymodule.logger".to_string(),
                kind: NodeKind::Variable,
                fqn: "mymodule.logger".to_string(),
                file_path: "mymodule/core.py".to_string(),
                span: Span::new(2, 0, 2, 30),
                language: "python".to_string(),
                stable_id: None,
                content_hash: None,
                name: Some("logger".to_string()),
                module_path: Some("mymodule.core".to_string()),
                parent_id: None,
                body_span: None,
                docstring: None,
                decorators: None,
                annotations: None,
                modifiers: None,
                is_async: None,
                is_generator: None,
                is_static: None,
                is_abstract: None,
                parameters: None,
                return_type: None,
                base_classes: None,
                metaclass: None,
                type_annotation: None,
                initial_value: None,
                metadata: None,
                role: None,
                is_test_file: None,
                signature_id: None,
                declared_type_id: None,
                attrs: None,
                raw: None,
                flavor: None,
                is_nullable: None,
                owner_node_id: None,
                condition_expr_id: None,
                condition_text: None,
            },
        ];

        let file_text = vec![
            "DEFAULT_TIMEOUT = 30".to_string(),
            "logger = logging.getLogger(__name__)".to_string(),
            "".to_string(),
            "".to_string(),
            "class MyClass:".to_string(),
            "    \"\"\"A sample class.\"\"\"".to_string(),
            "    ".to_string(),
            "    ".to_string(),
            "    ".to_string(),
            "    def process(self, data):".to_string(),
            "        \"\"\"Process data.\"\"\"".to_string(),
            "        pass".to_string(),
        ];

        // Execute build_with_ir
        let (chunks, chunk_to_ir, _) = builder.build_with_ir(
            "myrepo",
            "mymodule/core.py",
            "python",
            &ir_nodes,
            &file_text,
            Some("abc123"),
        );

        // Count chunk types
        let class_count = chunks.iter().filter(|c| c.kind == ChunkKind::Class).count();
        let func_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Function)
            .count();
        let docstring_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Docstring)
            .count();
        let skeleton_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Skeleton)
            .count();
        let constant_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Constant)
            .count();
        let variable_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Variable)
            .count();

        // Assertions
        assert_eq!(class_count, 1, "Should have 1 class");
        assert_eq!(func_count, 1, "Should have 1 function/method");
        assert_eq!(
            docstring_count, 2,
            "Should have 2 docstrings (class + method)"
        );
        assert_eq!(skeleton_count, 1, "Should have 1 skeleton (for method)");
        assert_eq!(
            constant_count, 1,
            "Should have 1 constant (DEFAULT_TIMEOUT)"
        );
        assert_eq!(variable_count, 1, "Should have 1 variable (logger)");

        // Verify IR mappings exist
        assert!(!chunk_to_ir.is_empty(), "Should have IR mappings");

        // Verify structural hierarchy (Repo → Project → Module → File)
        let repo_count = chunks.iter().filter(|c| c.kind == ChunkKind::Repo).count();
        let project_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Project)
            .count();
        let module_count = chunks
            .iter()
            .filter(|c| c.kind == ChunkKind::Module)
            .count();
        let file_count = chunks.iter().filter(|c| c.kind == ChunkKind::File).count();

        assert_eq!(repo_count, 1, "Should have 1 repo chunk");
        assert_eq!(project_count, 1, "Should have 1 project chunk");
        assert!(module_count >= 1, "Should have at least 1 module chunk");
        assert_eq!(file_count, 1, "Should have 1 file chunk");
    }

    #[test]
    fn test_skeleton_with_signature() {
        use crate::shared::models::{Node, NodeKind, Span};

        let id_gen = ChunkIdGenerator::new();
        let mut builder = ChunkBuilder::new(id_gen);

        let func_chunks = vec![Chunk {
            chunk_id: "chunk:myrepo:function:mod.func".to_string(),
            repo_id: "myrepo".to_string(),
            snapshot_id: "abc123".to_string(),
            kind: ChunkKind::Function,
            fqn: "mod.func".to_string(),
            file_path: Some("mod.py".to_string()),
            project_id: Some("default".to_string()),
            module_path: Some("mod".to_string()),
            start_line: Some(1),
            end_line: Some(5),
            original_start_line: Some(1),
            original_end_line: Some(5),
            content_hash: None,
            parent_id: None,
            children: Vec::new(),
            language: Some("python".to_string()),
            symbol_visibility: None,
            symbol_id: None,
            symbol_owner_id: None,
            summary: None,
            importance: None,
            attrs: HashMap::new(),
            version: 1,
            last_indexed_commit: None,
            is_deleted: false,
            local_seq: 0,
            is_test: None,
            is_overlay: false,
            overlay_session_id: None,
            base_chunk_id: None,
        }];

        let ir_nodes = vec![Node {
            id: "node:func:mod.func".to_string(),
            kind: NodeKind::Function,
            fqn: "mod.func".to_string(),
            file_path: "mod.py".to_string(),
            span: Span::new(1, 0, 5, 0),
            language: "python".to_string(),
            stable_id: None,
            content_hash: None,
            name: Some("func".to_string()),
            module_path: Some("mod".to_string()),
            parent_id: None,
            body_span: None,
            docstring: None,
            decorators: None,
            annotations: None,
            modifiers: None,
            is_async: None,
            is_generator: None,
            is_static: None,
            is_abstract: None,
            parameters: None,
            return_type: None,
            base_classes: None,
            metaclass: None,
            type_annotation: None,
            initial_value: None,
            metadata: None,
            role: None,
            is_test_file: None,
            signature_id: None,
            declared_type_id: None,
            attrs: None,
            raw: None,
            flavor: None,
            is_nullable: None,
            owner_node_id: None,
            condition_expr_id: None,
            condition_text: None,
        }];

        let file_text = vec![
            "def func(arg1, arg2):".to_string(),
            "    return arg1 + arg2".to_string(),
        ];

        let skeletons =
            builder.build_skeleton_chunks("myrepo", &func_chunks, &ir_nodes, &file_text, "abc123");

        assert_eq!(skeletons.len(), 1, "Should have 1 skeleton");
        assert_eq!(skeletons[0].kind, ChunkKind::Skeleton);
        assert_eq!(skeletons[0].fqn, "mod.func.__signature__");
        assert_eq!(
            skeletons[0].summary,
            Some("def func(arg1, arg2):".to_string())
        );
        assert!(skeletons[0].content_hash.is_some());
    }
}
