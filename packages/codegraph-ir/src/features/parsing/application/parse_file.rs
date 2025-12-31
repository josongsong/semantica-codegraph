//! Parse file use case

use crate::features::parsing::domain::ParsedTree;
use crate::features::parsing::ports::Parser;
use crate::shared::models::Result;

/// Parse file use case
pub struct ParseFileUseCase<P: Parser> {
    parser: P,
}

impl<P: Parser> ParseFileUseCase<P> {
    pub fn new(parser: P) -> Self {
        Self { parser }
    }

    /// Execute the parse operation
    pub fn execute(&self, source: &str, file_path: &str) -> Result<ParsedTree> {
        self.parser.parse(source, file_path)
    }

    /// Execute for multiple files
    pub fn execute_batch(&self, files: &[(String, String)]) -> Vec<Result<ParsedTree>> {
        files
            .iter()
            .map(|(path, source)| self.parser.parse(source, path))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::parsing::domain::{ParsedTree, SyntaxKind, SyntaxNode};
    use crate::shared::models::{CodegraphError, Span};

    // Mock parser for testing
    struct MockParser;

    impl Parser for MockParser {
        fn parse(&self, source: &str, file_path: &str) -> Result<ParsedTree> {
            let root = SyntaxNode::new(SyntaxKind::Block, Span::zero());
            Ok(ParsedTree::new(
                root,
                source.to_string(),
                file_path.to_string(),
                "python".to_string(),
            ))
        }

        fn supports_extension(&self, ext: &str) -> bool {
            ext == "py"
        }

        fn language_name(&self) -> &'static str {
            "python"
        }
    }

    #[test]
    fn test_parse_file_use_case() {
        let use_case = ParseFileUseCase::new(MockParser);
        let result = use_case.execute("def foo(): pass", "test.py");
        assert!(result.is_ok());
    }
}
