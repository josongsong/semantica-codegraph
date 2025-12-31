"""
Semantic IR Cache Utilities

Provides dynamic cache sizing based on project scale.
"""


def get_optimal_ast_cache_size(file_count: int) -> int:
    """
    Calculate optimal AST cache size based on project size.

    Args:
        file_count: Number of files in the project

    Returns:
        Optimal cache size (number of AST trees)

    Memory estimates (per AST: ~5-15MB):
    - Tiny projects (<30 files): file_count (cache all, ~150-450MB)
    - Small projects (30-100): min(file_count, 100) (avoid evictions)
    - Medium projects (100-500): 100 ASTs (~500MB-1.5GB)
    - Large projects (500-1000): 200 ASTs (~1-3GB)
    - Very large projects (1000+): 500 ASTs (~2.5-7.5GB)
    """
    if file_count < 30:
        # Tiny projects: Cache everything to avoid evictions
        return file_count
    elif file_count < 100:
        # Small projects: Cache all files (avoid evictions)
        return min(file_count, 100)
    elif file_count < 500:
        # Medium projects: Moderate caching
        return 100
    elif file_count < 1000:
        # Large projects: Aggressive caching
        return 200
    else:
        # Very large projects: Maximum caching
        # For 10K+ files, consider increasing if memory allows
        return min(500, file_count // 2)  # Cache up to 50% of files


def get_optimal_expression_cache_size(file_count: int) -> int:
    """
    Calculate optimal expression cache size based on project size.

    Expression builder cache is generally smaller than BFG cache
    since expressions are extracted per-block.

    Args:
        file_count: Number of files in the project

    Returns:
        Optimal cache size
    """
    # Expression cache is typically 1.5-2x larger than BFG cache
    bfg_size = get_optimal_ast_cache_size(file_count)
    return min(int(bfg_size * 1.7), 1000)  # Cap at 1000 ASTs
