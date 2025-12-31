//! Custom Tokenizers for Code Search
//!
//! # Tokenization Strategy
//!
//! 1. **3-gram Tokenizer**: Partial matching (e.g., "getUserName" → ["get", "etU", "tUs", ...])
//! 2. **CamelCase Tokenizer**: Code identifier splitting (e.g., "getUserName" → ["get", "User", "Name"])
//! 3. **Lowercase Filter**: Case-insensitive search
//!
//! This combination enables:
//! - Fuzzy matching for typos
//! - Identifier-aware search
//! - Case-insensitive queries

use tantivy::tokenizer::{
    LowerCaser, NgramTokenizer, SimpleTokenizer, TextAnalyzer, Token, TokenStream, Tokenizer,
};

/// CamelCase/snake_case tokenizer for code identifiers.
///
/// Splits:
/// - `getUserName` → `["get", "User", "Name"]`
/// - `get_user_name` → `["get", "user", "name"]`
/// - `HTTPSConnection` → `["HTTPS", "Connection"]`
#[derive(Clone)]
pub struct CamelCaseTokenizer;

impl Tokenizer for CamelCaseTokenizer {
    type TokenStream<'a> = CamelCaseTokenStream<'a>;

    fn token_stream<'a>(&'a mut self, text: &'a str) -> Self::TokenStream<'a> {
        CamelCaseTokenStream {
            text,
            offset: 0,
            tokens: Vec::new(),
            current_index: 0,
        }
    }
}

pub struct CamelCaseTokenStream<'a> {
    text: &'a str,
    offset: usize,
    tokens: Vec<Token>,
    current_index: usize,
}

impl<'a> CamelCaseTokenStream<'a> {
    fn split_identifiers(&mut self) {
        let text = self.text;
        let mut current_start = 0;
        let mut last_was_upper = false;
        let mut last_was_lower = false;

        for (i, ch) in text.char_indices() {
            let is_upper = ch.is_uppercase();
            let is_lower = ch.is_lowercase();
            let is_digit = ch.is_ascii_digit();
            let is_underscore = ch == '_';

            // Split conditions:
            // 1. Transition from lower to upper: "camelCase" → ["camel", "Case"]
            // 2. Consecutive uppercase followed by lowercase: "HTTPSConnection" → ["HTTPS", "Connection"]
            // 3. Underscore separator: "snake_case" → ["snake", "case"]
            let should_split = if is_underscore {
                true
            } else if last_was_lower && is_upper {
                // camelCase boundary
                true
            } else if last_was_upper && is_lower && i > current_start + 1 {
                // HTTPSConnection: split before 'C' (i-1)
                // Emit "HTTPS" and start "Connection"
                if current_start < i - 1 {
                    let token_text = &text[current_start..i - 1];
                    if !token_text.is_empty() {
                        self.tokens.push(Token {
                            offset_from: current_start,
                            offset_to: i - 1,
                            position: self.tokens.len(),
                            text: token_text.to_string(),
                            position_length: 1,
                        });
                    }
                    current_start = i - 1; // Start of "Connection"
                }
                false
            } else {
                false
            };

            if should_split {
                let token_text = &text[current_start..i];
                if !token_text.is_empty() && token_text != "_" {
                    self.tokens.push(Token {
                        offset_from: current_start,
                        offset_to: i,
                        position: self.tokens.len(),
                        text: token_text.to_string(),
                        position_length: 1,
                    });
                }
                current_start = if is_underscore { i + 1 } else { i };
            }

            last_was_upper = is_upper;
            last_was_lower = is_lower;
        }

        // Emit final token
        if current_start < text.len() {
            let token_text = &text[current_start..];
            if !token_text.is_empty() && token_text != "_" {
                self.tokens.push(Token {
                    offset_from: current_start,
                    offset_to: text.len(),
                    position: self.tokens.len(),
                    text: token_text.to_string(),
                    position_length: 1,
                });
            }
        }
    }
}

impl<'a> TokenStream for CamelCaseTokenStream<'a> {
    fn advance(&mut self) -> bool {
        if self.tokens.is_empty() && self.current_index == 0 {
            self.split_identifiers();
        }

        if self.current_index < self.tokens.len() {
            self.current_index += 1;
            true
        } else {
            false
        }
    }

    fn token(&self) -> &Token {
        &self.tokens[self.current_index - 1]
    }

    fn token_mut(&mut self) -> &mut Token {
        &mut self.tokens[self.current_index - 1]
    }
}

/// Build the default code analyzer.
///
/// Pipeline:
/// 1. CamelCaseTokenizer - Split camelCase/snake_case (main tokenizer)
/// 2. LowerCaser - Normalize case
///
/// For 3-gram indexing, use `build_ngram_analyzer()`.
pub fn build_code_analyzer() -> TextAnalyzer {
    TextAnalyzer::builder(CamelCaseTokenizer)
        .filter(LowerCaser)
        .build()
}

/// Build 3-gram analyzer for fuzzy matching.
///
/// Generates overlapping 3-character sequences:
/// - "getUserName" → ["get", "etU", "tUs", "Use", "ser", "erN", "rNa", "Nam", "ame"]
///
/// Use for partial/fuzzy matching in string literals and comments.
pub fn build_ngram_analyzer() -> TextAnalyzer {
    TextAnalyzer::builder(NgramTokenizer::new(3, 3, false).unwrap())
        .filter(LowerCaser)
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_camel_case_tokenizer() {
        let mut tokenizer = CamelCaseTokenizer;
        let mut stream = tokenizer.token_stream("getUserName");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        assert_eq!(tokens, vec!["get", "User", "Name"]);
    }

    #[test]
    fn test_snake_case_tokenizer() {
        let mut tokenizer = CamelCaseTokenizer;
        let mut stream = tokenizer.token_stream("get_user_name");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        assert_eq!(tokens, vec!["get", "user", "name"]);
    }

    #[test]
    fn test_https_connection() {
        let mut tokenizer = CamelCaseTokenizer;
        let mut stream = tokenizer.token_stream("HTTPSConnection");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        assert_eq!(tokens, vec!["HTTPS", "Connection"]);
    }

    #[test]
    fn test_mixed_case() {
        let mut tokenizer = CamelCaseTokenizer;
        let mut stream = tokenizer.token_stream("parseJSON_ToObject");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        assert_eq!(tokens, vec!["parse", "JSON", "To", "Object"]);
    }

    #[test]
    fn test_code_analyzer() {
        let mut analyzer = build_code_analyzer();
        let mut stream = analyzer.token_stream("getUserName");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        // CamelCase + LowerCaser
        assert_eq!(tokens, vec!["get", "user", "name"]);
    }

    #[test]
    fn test_ngram_analyzer() {
        let mut analyzer = build_ngram_analyzer();
        let mut stream = analyzer.token_stream("abc");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        // 3-gram generates only 1 token for "abc"
        assert_eq!(tokens, vec!["abc"]);
    }

    #[test]
    fn test_ngram_longer_text() {
        let mut analyzer = build_ngram_analyzer();
        let mut stream = analyzer.token_stream("hello");

        let mut tokens = Vec::new();
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        // "hello" → ["hel", "ell", "llo"]
        assert_eq!(tokens, vec!["hel", "ell", "llo"]);
    }
}
