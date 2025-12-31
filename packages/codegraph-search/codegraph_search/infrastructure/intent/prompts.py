"""
LLM Intent Classification Prompts

Defines prompt templates for LLM-based query intent classification.
"""

INTENT_CLASSIFICATION_PROMPT = """Classify the following code search query into one of these intents:

**Intent Types:**
- **code_search**: Find specific code implementation, search for code patterns or functionality
- **symbol_nav**: Navigate to definition/references of a specific symbol (function, class, variable)
- **concept_search**: Understand high-level concepts, architecture, or design patterns
- **flow_trace**: Trace execution flow, call chains, or data flow
- **repo_overview**: Get repository structure, entry points, or high-level organization

**Query:** "{query}"

**Response format (JSON only):**
```json
{{
  "intent": "<intent_kind>",
  "symbol_names": ["symbol1", "symbol2"],
  "file_paths": ["path1.py"],
  "module_paths": ["module.submodule"],
  "confidence": 0.95
}}
```

**Guidelines:**
- Extract any symbol names mentioned (functions, classes, variables)
- Extract any file or module paths mentioned
- Set confidence based on query clarity (0.0-1.0)
- Use "code_search" if unclear

Respond with JSON only, no additional text."""


INTENT_EXAMPLES = """
**Example 1:**
Query: "find the authenticate function"
Response:
```json
{
  "intent": "symbol_nav",
  "symbol_names": ["authenticate"],
  "file_paths": [],
  "module_paths": [],
  "confidence": 0.95
}
```

**Example 2:**
Query: "how does the authentication system work?"
Response:
```json
{
  "intent": "concept_search",
  "symbol_names": [],
  "file_paths": [],
  "module_paths": ["authentication"],
  "confidence": 0.90
}
```

**Example 3:**
Query: "trace the call chain from login to database"
Response:
```json
{
  "intent": "flow_trace",
  "symbol_names": ["login"],
  "file_paths": [],
  "module_paths": [],
  "confidence": 0.92
}
```

**Example 4:**
Query: "show me the main entry points"
Response:
```json
{
  "intent": "repo_overview",
  "symbol_names": [],
  "file_paths": [],
  "module_paths": [],
  "confidence": 0.88
}
```

**Example 5:**
Query: "user registration implementation in auth.py"
Response:
```json
{
  "intent": "code_search",
  "symbol_names": ["registration"],
  "file_paths": ["auth.py"],
  "module_paths": [],
  "confidence": 0.93
}
```
"""


def build_classification_prompt(query: str, include_examples: bool = False) -> str:
    """
    Build LLM prompt for intent classification.

    Args:
        query: User query to classify
        include_examples: Whether to include few-shot examples

    Returns:
        Complete prompt string
    """
    prompt = INTENT_CLASSIFICATION_PROMPT.format(query=query)

    if include_examples:
        prompt = INTENT_EXAMPLES + "\n\n" + prompt

    return prompt
