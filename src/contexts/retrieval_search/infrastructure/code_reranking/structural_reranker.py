"""
Structural Similarity Reranker

AST-based structural similarity scoring for code.
"""

import ast

from src.contexts.retrieval_search.infrastructure.code_reranking.models import (
    ASTSimilarity,
    CodeRerankedChunk,
    StructuralFeature,
)


class StructuralReranker:
    """
    Reranks results based on AST structural similarity.

    Uses code structure patterns (function signatures, class hierarchy, etc.)
    to boost results that are structurally similar to the query context.
    """

    def __init__(
        self,
        feature_weights: dict[StructuralFeature, float] | None = None,
        boost_factor: float = 0.15,
    ):
        """
        Initialize structural reranker.

        Args:
            feature_weights: Weights for different structural features
            boost_factor: Max boost to apply (0-1)
        """
        self.feature_weights = feature_weights or {
            StructuralFeature.FUNCTION_SIGNATURE: 0.30,
            StructuralFeature.CLASS_HIERARCHY: 0.25,
            StructuralFeature.CONTROL_FLOW: 0.20,
            StructuralFeature.VARIABLE_USAGE: 0.10,
            StructuralFeature.IMPORT_PATTERN: 0.10,
            StructuralFeature.DECORATOR_PATTERN: 0.05,
        }
        self.boost_factor = boost_factor

    def rerank(
        self,
        candidates: list[dict],
        query_context: str | None = None,
        reference_code: str | None = None,
    ) -> list[CodeRerankedChunk]:
        """
        Rerank candidates based on structural similarity.

        Args:
            candidates: List of candidate chunks with scores
            query_context: Optional query context (natural language)
            reference_code: Optional reference code to compare against

        Returns:
            Reranked list with structural scores
        """
        results = []

        # Parse reference code if provided
        reference_ast = None
        if reference_code:
            try:
                reference_ast = ast.parse(reference_code)
            except SyntaxError:
                reference_ast = None

        for candidate in candidates:
            chunk_id = candidate.get("chunk_id", "unknown")
            original_score = candidate.get("score", 0.0)
            code_content = candidate.get("content", "")

            # Calculate structural similarity
            if reference_ast and code_content:
                ast_similarity = self._compute_similarity(reference_ast, code_content)
                structural_score = ast_similarity.overall_score
            else:
                # No reference code, use pattern matching on query
                ast_similarity = self._match_query_patterns(code_content, query_context or "")
                structural_score = ast_similarity.overall_score

            # Apply boost
            boost = structural_score * self.boost_factor
            final_score = min(1.0, original_score + boost)

            results.append(
                CodeRerankedChunk(
                    chunk_id=chunk_id,
                    original_score=original_score,
                    structural_score=structural_score,
                    final_score=final_score,
                    ast_similarity=ast_similarity,
                    metadata=candidate.get("metadata", {}),
                )
            )

        # Sort by final score
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results

    def _compute_similarity(self, reference_ast: ast.AST, candidate_code: str) -> ASTSimilarity:
        """Compute structural similarity between reference and candidate."""
        try:
            candidate_ast = ast.parse(candidate_code)
        except SyntaxError:
            return ASTSimilarity(overall_score=0.0)

        # Extract features from both ASTs
        ref_features = self._extract_features(reference_ast)
        cand_features = self._extract_features(candidate_ast)

        # Compare features
        feature_scores = {}
        matched_patterns = []

        for feature_type, _weight in self.feature_weights.items():
            similarity = self._compare_feature(
                ref_features.get(feature_type, set()),
                cand_features.get(feature_type, set()),
            )
            feature_scores[feature_type] = similarity

            if similarity > 0.5:
                matched_patterns.append(feature_type.value)

        # Weighted overall score
        overall_score = sum(score * self.feature_weights[feature] for feature, score in feature_scores.items())

        explanation = self._generate_explanation(feature_scores, matched_patterns)

        return ASTSimilarity(
            overall_score=overall_score,
            feature_scores=feature_scores,
            matched_patterns=matched_patterns,
            explanation=explanation,
        )

    def _extract_features(self, tree: ast.AST) -> dict[StructuralFeature, set]:
        """Extract structural features from AST."""
        features = {feature_type: set() for feature_type in StructuralFeature}

        for node in ast.walk(tree):
            # Function signatures
            if isinstance(node, ast.FunctionDef):
                sig = f"{node.name}({len(node.args.args)})"
                features[StructuralFeature.FUNCTION_SIGNATURE].add(sig)

                # Decorators
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        features[StructuralFeature.DECORATOR_PATTERN].add(dec.id)

            # Class hierarchy
            elif isinstance(node, ast.ClassDef):
                bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
                features[StructuralFeature.CLASS_HIERARCHY].add(f"{node.name}:{','.join(bases)}")

            # Control flow
            elif isinstance(node, ast.If | ast.For | ast.While | ast.Try):
                features[StructuralFeature.CONTROL_FLOW].add(node.__class__.__name__)

            # Variable usage
            elif isinstance(node, ast.Name):
                features[StructuralFeature.VARIABLE_USAGE].add(node.id)

            # Imports
            elif isinstance(node, ast.Import | ast.ImportFrom):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        features[StructuralFeature.IMPORT_PATTERN].add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    features[StructuralFeature.IMPORT_PATTERN].add(node.module)

        return features

    def _compare_feature(self, ref_set: set, cand_set: set) -> float:
        """Compare two feature sets using Jaccard similarity."""
        if not ref_set and not cand_set:
            return 1.0
        if not ref_set or not cand_set:
            return 0.0

        intersection = len(ref_set & cand_set)
        union = len(ref_set | cand_set)

        return intersection / union if union > 0 else 0.0

    def _match_query_patterns(self, code_content: str, query: str) -> ASTSimilarity:
        """
        Match patterns from query in code.

        Used when no reference code is provided.
        """
        try:
            code_ast = ast.parse(code_content)
        except SyntaxError:
            return ASTSimilarity(overall_score=0.0)

        features = self._extract_features(code_ast)
        matched_patterns = []
        feature_scores = {}

        # Simple keyword matching for patterns
        query_lower = query.lower()

        # Check for function-related queries
        if any(kw in query_lower for kw in ["function", "def", "method", "call", "invoke"]):
            if features[StructuralFeature.FUNCTION_SIGNATURE]:
                feature_scores[StructuralFeature.FUNCTION_SIGNATURE] = 0.8
                matched_patterns.append("function_signature")
            else:
                feature_scores[StructuralFeature.FUNCTION_SIGNATURE] = 0.0
        else:
            feature_scores[StructuralFeature.FUNCTION_SIGNATURE] = 0.5

        # Check for class-related queries
        if any(kw in query_lower for kw in ["class", "inherit", "extend"]):
            if features[StructuralFeature.CLASS_HIERARCHY]:
                feature_scores[StructuralFeature.CLASS_HIERARCHY] = 0.8
                matched_patterns.append("class_hierarchy")
            else:
                feature_scores[StructuralFeature.CLASS_HIERARCHY] = 0.0
        else:
            feature_scores[StructuralFeature.CLASS_HIERARCHY] = 0.5

        # Check for control flow queries
        if any(kw in query_lower for kw in ["loop", "if", "condition", "error"]):
            if features[StructuralFeature.CONTROL_FLOW]:
                feature_scores[StructuralFeature.CONTROL_FLOW] = 0.7
                matched_patterns.append("control_flow")
            else:
                feature_scores[StructuralFeature.CONTROL_FLOW] = 0.0
        else:
            feature_scores[StructuralFeature.CONTROL_FLOW] = 0.5

        # Default scores for other features
        for feature in StructuralFeature:
            if feature not in feature_scores:
                feature_scores[feature] = 0.3

        overall_score = sum(score * self.feature_weights.get(feature, 0.0) for feature, score in feature_scores.items())

        explanation = (
            f"Matched patterns: {', '.join(matched_patterns)}" if matched_patterns else "No strong pattern match"
        )

        return ASTSimilarity(
            overall_score=overall_score,
            feature_scores=feature_scores,
            matched_patterns=matched_patterns,
            explanation=explanation,
        )

    def _generate_explanation(self, feature_scores: dict, matched_patterns: list[str]) -> str:
        """Generate human-readable explanation."""
        if not matched_patterns:
            return "No significant structural similarity"

        top_features = sorted(feature_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        feature_names = [f"{feat.value} ({score:.2f})" for feat, score in top_features]

        return f"Similar in: {', '.join(feature_names)}"
