//! Tantivy Schema Definition
//!
//! # 7-Field Schema (FINAL - DO NOT CHANGE)
//!
//! 1. `content` - Code body (STORED, indexed)
//! 2. `string_literals` - String literals (NOT STORED, indexed)
//! 3. `comments` - Comments (NOT STORED, indexed)
//! 4. `docstring` - Docstrings (NOT STORED, indexed)
//! 5. `file_path` - File path (STORED, keyword)
//! 6. `repo_id` - Repository ID (STORED, keyword)
//! 7. `indexed_at` - Indexing timestamp (STORED, date)

use tantivy::schema::{
    Field, IndexRecordOption, Schema, TextFieldIndexing, TextOptions, STORED, TEXT,
};

// Field name constants (for type-safe access)
pub const FIELD_CONTENT: &str = "content";
pub const FIELD_STRING_LITERALS: &str = "string_literals";
pub const FIELD_COMMENTS: &str = "comments";
pub const FIELD_DOCSTRING: &str = "docstring";
pub const FIELD_FILE_PATH: &str = "file_path";
pub const FIELD_REPO_ID: &str = "repo_id";
pub const FIELD_INDEXED_AT: &str = "indexed_at";

/// Build Tantivy schema (7-field FINAL)
pub fn build_schema() -> Schema {
    let mut schema_builder = Schema::builder();

    // 1. content - Code body (STORED for snippet, indexed for search)
    schema_builder.add_text_field(FIELD_CONTENT, TEXT | STORED);

    // 2-4. Searchable fields (NOT STORED to save space)
    schema_builder.add_text_field(FIELD_STRING_LITERALS, TEXT);
    schema_builder.add_text_field(FIELD_COMMENTS, TEXT);
    schema_builder.add_text_field(FIELD_DOCSTRING, TEXT);

    // 5-6. Metadata (STORED, keyword for exact matching)
    let opts = TextOptions::default()
        .set_indexing_options(
            TextFieldIndexing::default()
                .set_tokenizer("raw") // No tokenization (exact match)
                .set_index_option(IndexRecordOption::Basic),
        )
        .set_stored();

    schema_builder.add_text_field(FIELD_FILE_PATH, opts.clone());
    schema_builder.add_text_field(FIELD_REPO_ID, opts);

    // 7. indexed_at - Timestamp (STORED)
    schema_builder.add_date_field(FIELD_INDEXED_AT, STORED);

    schema_builder.build()
}

/// Field handles (cached for performance)
#[derive(Debug, Clone)]
pub struct SchemaFields {
    pub schema: Schema,
    pub content: Field,
    pub string_literals: Field,
    pub comments: Field,
    pub docstring: Field,
    pub file_path: Field,
    pub repo_id: Field,
    pub indexed_at: Field,
}

impl SchemaFields {
    pub fn new() -> Self {
        let schema = build_schema();

        Self {
            content: schema.get_field(FIELD_CONTENT).expect("content field"),
            string_literals: schema
                .get_field(FIELD_STRING_LITERALS)
                .expect("string_literals field"),
            comments: schema.get_field(FIELD_COMMENTS).expect("comments field"),
            docstring: schema.get_field(FIELD_DOCSTRING).expect("docstring field"),
            file_path: schema.get_field(FIELD_FILE_PATH).expect("file_path field"),
            repo_id: schema.get_field(FIELD_REPO_ID).expect("repo_id field"),
            indexed_at: schema
                .get_field(FIELD_INDEXED_AT)
                .expect("indexed_at field"),
            schema,
        }
    }
}

impl Default for SchemaFields {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_schema_has_7_fields() {
        let schema = build_schema();
        assert_eq!(schema.fields().count(), 7);
    }

    #[test]
    fn test_schema_fields_cached() {
        let fields = SchemaFields::new();
        assert!(fields.schema.fields().count() == 7);
    }

    #[test]
    fn test_content_is_stored() {
        let schema = build_schema();
        let field = schema.get_field(FIELD_CONTENT).unwrap();
        let entry = schema.get_field_entry(field);
        assert!(entry.is_stored());
    }

    #[test]
    fn test_string_literals_not_stored() {
        let schema = build_schema();
        let field = schema.get_field(FIELD_STRING_LITERALS).unwrap();
        let entry = schema.get_field_entry(field);
        assert!(!entry.is_stored());
    }
}
