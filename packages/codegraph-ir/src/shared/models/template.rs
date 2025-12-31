//! Template Parsing Models
//!
//! SOTA 2025: Template/Document parsing domain models
//!
//! Supports:
//! - React JSX/TSX (via Python JSXTemplateParser)
//! - Vue SFC (via Python VueSFCParser)
//! - Markdown (via Python MarkdownParser)
//! - Jupyter Notebook (via Python NotebookParser)
//!
//! Architecture:
//! - Python parsers handle AST parsing (flexible, well-tested)
//! - Rust handles IR conversion and analysis (fast, memory-safe)
//! - PyO3 bridge for zero-copy data transfer

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Template document parsed from source file
///
/// Represents the result of parsing a template/document file
/// (JSX, Vue, Markdown, etc.) via Python parsers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateDoc {
    /// Document identifier (e.g., "template:path/to/file.tsx")
    pub doc_id: String,

    /// Parser engine used ("react-jsx", "vue-sfc", "markdown", etc.)
    pub engine: String,

    /// Source file path
    pub file_path: String,

    /// Root element IDs (top-level elements)
    pub root_element_ids: Vec<String>,

    /// All template slots (dynamic expressions)
    pub slots: Vec<TemplateSlot>,

    /// All template elements (HTML/JSX elements)
    pub elements: Vec<TemplateElement>,

    /// Whether parsing was partial (had errors)
    pub is_partial: bool,

    /// Whether this is a virtual template (innerHTML, etc.)
    pub is_virtual: bool,

    /// Additional metadata
    pub attrs: HashMap<String, String>,
}

/// Template slot - dynamic expression in template
///
/// Examples:
/// - React: `<div dangerouslySetInnerHTML={{__html: user.bio}} />`
/// - Vue: `<div v-html="user.bio"></div>`
/// - Vue: `{{ user.name }}`
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateSlot {
    /// Slot identifier
    pub slot_id: String,

    /// Host element/node ID
    pub host_node_id: String,

    /// Raw expression text
    pub expr_raw: String,

    /// Expression span (byte offsets)
    pub expr_span: (usize, usize),

    /// Context kind (security classification)
    pub context_kind: SlotContextKind,

    /// Escape mode (how output is escaped)
    pub escape_mode: EscapeMode,

    /// Name hint (variable name extracted from expression)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name_hint: Option<String>,

    /// Whether this is a security sink (XSS, SSRF, etc.)
    pub is_sink: bool,

    /// Framework identifier ("react", "vue", etc.)
    pub framework: String,

    /// Additional attributes
    #[serde(skip_serializing_if = "HashMap::is_empty", default)]
    pub attrs: HashMap<String, String>,
}

/// Template element - HTML/JSX element
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateElement {
    /// Element identifier
    pub element_id: String,

    /// Tag name (e.g., "div", "MyComponent")
    pub tag_name: String,

    /// Byte span in source file
    pub span: (usize, usize),

    /// Element attributes (static values)
    pub attributes: HashMap<String, String>,

    /// Whether this is a custom component (PascalCase)
    pub is_component: bool,

    /// Whether this is self-closing (<img />)
    pub is_self_closing: bool,

    /// Event handlers (onClick, @click, etc.)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_handlers: Option<HashMap<String, String>>,
}

/// Slot context kind - security classification
///
/// Based on OWASP XSS prevention:
/// - RAW_HTML: Unescaped HTML (CRITICAL sink)
/// - URL_ATTR: URL attributes (SSRF/XSS risk)
/// - HTML_ATTR: Regular HTML attributes
/// - HTML_TEXT: Text content (usually auto-escaped)
/// - CSS_INLINE: Inline CSS (CSS injection risk)
/// - JS_INLINE: Inline JavaScript (code injection)
/// - EVENT_HANDLER: Event handlers (limited risk)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SlotContextKind {
    /// Raw HTML insertion (v-html, dangerouslySetInnerHTML)
    /// CRITICAL: XSS sink if user-controlled
    #[serde(rename = "RAW_HTML")]
    RawHtml,

    /// URL attribute (href, src, action, etc.)
    /// HIGH: SSRF/XSS risk (javascript:, data:)
    #[serde(rename = "URL_ATTR")]
    UrlAttr,

    /// Regular HTML attribute
    /// MEDIUM: Limited XSS risk
    #[serde(rename = "HTML_ATTR")]
    HtmlAttr,

    /// HTML text content ({{ }}, {expr})
    /// LOW: Usually auto-escaped by framework
    #[serde(rename = "HTML_TEXT")]
    HtmlText,

    /// Inline CSS (style attribute)
    /// MEDIUM: CSS injection risk
    #[serde(rename = "CSS_INLINE")]
    CssInline,

    /// Inline JavaScript
    /// CRITICAL: Code injection
    #[serde(rename = "JS_INLINE")]
    JsInline,

    /// Event handler (onClick, @click, etc.)
    /// LOW: Usually sanitized by framework
    #[serde(rename = "EVENT_HANDLER")]
    EventHandler,

    /// Unknown/other context
    #[serde(rename = "UNKNOWN")]
    Unknown,
}

impl SlotContextKind {
    /// Check if this context is a security sink
    pub fn is_security_sink(&self) -> bool {
        matches!(
            self,
            SlotContextKind::RawHtml | SlotContextKind::UrlAttr | SlotContextKind::JsInline
        )
    }

    /// Get severity level (0=safe, 5=critical)
    pub fn severity_level(&self) -> u8 {
        match self {
            SlotContextKind::RawHtml | SlotContextKind::JsInline => 5,
            SlotContextKind::UrlAttr => 4,
            SlotContextKind::CssInline => 3,
            SlotContextKind::HtmlAttr => 2,
            SlotContextKind::EventHandler => 1,
            SlotContextKind::HtmlText => 0,
            SlotContextKind::Unknown => 0,
        }
    }
}

/// Escape mode - how output is escaped
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EscapeMode {
    /// No escaping (dangerous!)
    #[serde(rename = "NONE")]
    None,

    /// Automatic escaping by framework
    #[serde(rename = "AUTO")]
    Auto,

    /// Manual escaping required
    #[serde(rename = "MANUAL")]
    Manual,

    /// Unknown escaping behavior
    #[serde(rename = "UNKNOWN")]
    Unknown,
}

/// Parsed document (Markdown, RST, etc.)
///
/// Non-code documents that need to be indexed for search
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedDocument {
    /// File path
    pub file_path: String,

    /// Document type
    pub doc_type: DocumentType,

    /// Raw content
    pub raw_content: String,

    /// Sections (headings, paragraphs, code blocks)
    pub sections: Vec<DocumentSection>,

    /// Code blocks extracted from document
    pub code_blocks: Vec<CodeBlock>,

    /// Additional metadata
    pub metadata: HashMap<String, String>,
}

/// Document type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DocumentType {
    #[serde(rename = "MARKDOWN")]
    Markdown,

    #[serde(rename = "RST")]
    Rst,

    #[serde(rename = "TEXT")]
    Text,

    #[serde(rename = "NOTEBOOK")]
    Notebook,

    #[serde(rename = "PDF")]
    Pdf,
}

/// Document section
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentSection {
    /// Section type
    pub section_type: SectionType,

    /// Section content
    pub content: String,

    /// Heading level (1-6 for headings)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub level: Option<usize>,

    /// Line range in source file
    pub line_start: usize,
    pub line_end: usize,

    /// Additional metadata
    #[serde(skip_serializing_if = "HashMap::is_empty", default)]
    pub metadata: HashMap<String, String>,
}

/// Section type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SectionType {
    #[serde(rename = "HEADING")]
    Heading,

    #[serde(rename = "PARAGRAPH")]
    Paragraph,

    #[serde(rename = "CODE_BLOCK")]
    CodeBlock,

    #[serde(rename = "LIST")]
    List,

    #[serde(rename = "RAW")]
    Raw,
}

/// Code block in document
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeBlock {
    /// Programming language (if specified)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,

    /// Code content
    pub code: String,

    /// Line range in source file
    pub line_start: usize,
    pub line_end: usize,
}

// ============================================================================
// Conversion helpers for PyO3
// ============================================================================

impl TemplateDoc {
    /// Create from Python dict (via PyO3)
    ///
    /// Used when receiving TemplateDocContract from Python parsers
    pub fn from_python_dict(data: HashMap<String, serde_json::Value>) -> Result<Self, String> {
        serde_json::from_value(serde_json::Value::Object(data.into_iter().collect()))
            .map_err(|e| format!("Failed to deserialize TemplateDoc: {}", e))
    }

    /// Convert to Python dict (via PyO3)
    pub fn to_python_dict(&self) -> HashMap<String, serde_json::Value> {
        let json = serde_json::to_value(self).expect("Failed to serialize TemplateDoc");
        if let serde_json::Value::Object(map) = json {
            map.into_iter().collect()
        } else {
            HashMap::new()
        }
    }
}

impl ParsedDocument {
    /// Create from Python dict
    pub fn from_python_dict(data: HashMap<String, serde_json::Value>) -> Result<Self, String> {
        serde_json::from_value(serde_json::Value::Object(data.into_iter().collect()))
            .map_err(|e| format!("Failed to deserialize ParsedDocument: {}", e))
    }

    /// Convert to Python dict
    pub fn to_python_dict(&self) -> HashMap<String, serde_json::Value> {
        let json = serde_json::to_value(self).expect("Failed to serialize ParsedDocument");
        if let serde_json::Value::Object(map) = json {
            map.into_iter().collect()
        } else {
            HashMap::new()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_slot_context_kind_severity() {
        assert_eq!(SlotContextKind::RawHtml.severity_level(), 5);
        assert_eq!(SlotContextKind::UrlAttr.severity_level(), 4);
        assert_eq!(SlotContextKind::HtmlText.severity_level(), 0);

        assert!(SlotContextKind::RawHtml.is_security_sink());
        assert!(SlotContextKind::UrlAttr.is_security_sink());
        assert!(!SlotContextKind::HtmlText.is_security_sink());
    }

    #[test]
    fn test_template_doc_serialization() {
        let doc = TemplateDoc {
            doc_id: "template:test.tsx".to_string(),
            engine: "react-jsx".to_string(),
            file_path: "test.tsx".to_string(),
            root_element_ids: vec!["elem:1".to_string()],
            slots: vec![TemplateSlot {
                slot_id: "slot:1".to_string(),
                host_node_id: "elem:1".to_string(),
                expr_raw: "user.name".to_string(),
                expr_span: (10, 20),
                context_kind: SlotContextKind::HtmlText,
                escape_mode: EscapeMode::Auto,
                name_hint: Some("user".to_string()),
                is_sink: false,
                framework: "react".to_string(),
                attrs: HashMap::new(),
            }],
            elements: vec![],
            is_partial: false,
            is_virtual: false,
            attrs: HashMap::new(),
        };

        // Serialize to JSON
        let json = serde_json::to_string(&doc).unwrap();
        assert!(json.contains("react-jsx"));

        // Deserialize back
        let doc2: TemplateDoc = serde_json::from_str(&json).unwrap();
        assert_eq!(doc2.engine, "react-jsx");
        assert_eq!(doc2.slots.len(), 1);
    }
}
