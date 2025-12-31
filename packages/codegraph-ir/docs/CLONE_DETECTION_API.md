# Clone Detection API Documentation

## Overview

The Clone Detection API provides SOTA (State-of-the-Art) code clone detection using 4-tier classification (Bellon et al. 2007). It's implemented in Rust for maximum performance and exposed to Python via PyO3 bindings.

## Features

- **Type-1**: Exact clones (whitespace/comments differ)
- **Type-2**: Renamed clones (identifiers/types/literals differ)
- **Type-3**: Gapped clones (statements added/removed/modified)
- **Type-4**: Semantic clones (different syntax, same behavior)

## Performance

| Clone Type | Throughput | Algorithm |
|------------|------------|-----------|
| Type-1 | ~2M LOC/s | String hashing (MD5/FNV-1a) |
| Type-2 | ~500K LOC/s | AST normalization |
| Type-3 | ~50K LOC/s | PDG + edit distance |
| Type-4 | ~5K LOC/s | Graph isomorphism |

## Python API

### Installation

```bash
# Build and install
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

### Basic Usage

```python
import codegraph_ir

# Prepare code fragments
fragments = [
    {
        "file_path": "src/module1.py",
        "start_line": 10,
        "start_col": 0,  # Optional, defaults to 0
        "end_line": 20,
        "end_col": 0,    # Optional, defaults to 0
        "content": "def calculate_total(items):\n    return sum(items)",
        "token_count": 50,
        "loc": 10
    },
    {
        "file_path": "src/module2.py",
        "start_line": 50,
        "end_line": 60,
        "content": "def compute_sum(values):\n    return sum(values)",
        "token_count": 48,
        "loc": 10
    },
]

# Detect all clone types at once
all_clones = codegraph_ir.detect_clones_all(fragments)

for clone in all_clones:
    print(f"{clone['clone_type']}: {clone['source_file']}:{clone['source_start_line']}")
    print(f"  -> {clone['target_file']}:{clone['target_start_line']}")
    print(f"  Similarity: {clone['similarity']:.2%}")
```

### Detecting Specific Clone Types

#### Type-1: Exact Clones

```python
# Detect exact clones (only whitespace/comments differ)
type1_clones = codegraph_ir.detect_clones_type1(
    fragments,
    min_tokens=50,  # Minimum token count threshold
    min_loc=6       # Minimum lines of code threshold
)

# Type-1 clones have similarity = 1.0
for clone in type1_clones:
    assert clone['similarity'] == 1.0
    print(f"Exact clone: {clone['source_file']} == {clone['target_file']}")
```

#### Type-2: Renamed Clones

```python
# Detect renamed clones (identifiers/types/literals differ)
type2_clones = codegraph_ir.detect_clones_type2(
    fragments,
    min_tokens=50,
    min_loc=6,
    min_similarity=0.95  # Similarity threshold after normalization
)

# Type-2 includes Type-1 clones
for clone in type2_clones:
    print(f"Renamed clone (sim={clone['similarity']:.2%})")
    print(f"  {clone['source_file']} ~ {clone['target_file']}")
```

#### Type-3: Gapped Clones

```python
# Detect gapped clones (statements added/removed/modified)
type3_clones = codegraph_ir.detect_clones_type3(
    fragments,
    min_tokens=30,        # Lower threshold for gapped clones
    min_loc=4,
    min_similarity=0.7,   # Lower similarity threshold
    max_gap_ratio=0.3     # Maximum gap ratio (30% different lines allowed)
)

# Type-3 may have gaps
for clone in type3_clones:
    if clone.get('gap_count'):
        print(f"Gapped clone: {clone['gap_count']} gaps, {clone['gap_size']} lines")
    if clone.get('edit_distance'):
        print(f"  Edit distance: {clone['edit_distance']}")
```

#### Type-4: Semantic Clones

```python
# Detect semantic clones (different syntax, same behavior)
type4_clones = codegraph_ir.detect_clones_type4(
    fragments,
    min_tokens=20,
    min_loc=3,
    min_similarity=0.6,
    node_weight=0.4,      # Weight for node similarity
    edge_weight=0.3,      # Weight for edge similarity
    pattern_weight=0.3    # Weight for pattern similarity
)

# Type-4 uses graph isomorphism
for clone in type4_clones:
    if clone.get('semantic_similarity'):
        print(f"Semantic clone (semantic_sim={clone['semantic_similarity']:.2%})")
```

### File-Specific Detection

```python
# Detect clones within a specific file
file_clones = codegraph_ir.detect_clones_in_file(
    fragments,
    file_path="src/module1.py",
    clone_type="all"  # or "type1", "type2", "type3", "type4"
)

# Useful for finding duplicated code within the same file
for clone in file_clones:
    print(f"Self-clone in {clone['source_file']}")
    print(f"  Lines {clone['source_start_line']}-{clone['source_end_line']}")
    print(f"  vs Lines {clone['target_start_line']}-{clone['target_end_line']}")
```

## Result Format

Each clone pair is returned as a dictionary with the following fields:

```python
{
    # Clone classification
    "clone_type": "Type-1" | "Type-2" | "Type-3" | "Type-4",

    # Source fragment location
    "source_file": str,
    "source_start_line": int,
    "source_end_line": int,

    # Target fragment location
    "target_file": str,
    "target_start_line": int,
    "target_end_line": int,

    # Similarity metrics
    "similarity": float,          # Overall similarity (0.0 - 1.0)
    "token_count": int,           # Number of tokens in clone
    "loc": int,                   # Lines of code in clone

    # Detection metadata
    "detection_method": str,      # Algorithm used
    "confidence": float | None,   # Detection confidence (optional)
    "detection_time_ms": int | None,  # Detection time (optional)

    # Type-3 specific metrics (optional)
    "edit_distance": int | None,
    "normalized_edit_distance": float | None,
    "gap_count": int | None,
    "gap_size": int | None,

    # Type-4 specific metrics (optional)
    "semantic_similarity": float | None,
}
```

## Integration with Rust Pipeline

Clone detection is integrated into the end-to-end Rust pipeline at Layer 8:

```python
from codegraph_ir import E2EPipelineOrchestrator

# Create orchestrator
orchestrator = E2EPipelineOrchestrator(config={
    "repo_info": {"repo_name": "my-project", "root_path": "/path/to/repo"},
    "stages": {
        "enable_clone_detection": True,  # Enable clone detection
        # ... other stages
    }
})

# Run pipeline
result = orchestrator.execute(files=[...])

# Access clone detection results
clone_pairs = result.clone_pairs  # Vec<ClonePairSummary>

for pair in clone_pairs:
    print(f"Found {pair.clone_type} clone:")
    print(f"  {pair.source_file}:{pair.source_start_line}-{pair.source_end_line}")
    print(f"  {pair.target_file}:{pair.target_start_line}-{pair.target_end_line}")
    print(f"  Similarity: {pair.similarity:.2%}")
```

## Advanced Usage

### Custom Thresholds

```python
# Aggressive detection (more clones, may include false positives)
aggressive_clones = codegraph_ir.detect_clones_type3(
    fragments,
    min_tokens=20,       # Lower token threshold
    min_loc=3,           # Lower LOC threshold
    min_similarity=0.5,  # Lower similarity threshold
    max_gap_ratio=0.5    # Allow more gaps
)

# Conservative detection (fewer clones, higher precision)
conservative_clones = codegraph_ir.detect_clones_type2(
    fragments,
    min_tokens=100,      # Higher token threshold
    min_loc=10,          # Higher LOC threshold
    min_similarity=0.98  # Very high similarity
)
```

### Filtering Results

```python
# Filter by minimum clone size
large_clones = [
    clone for clone in all_clones
    if clone['loc'] >= 20  # At least 20 lines
]

# Filter by similarity
high_similarity_clones = [
    clone for clone in all_clones
    if clone['similarity'] >= 0.9  # At least 90% similar
]

# Filter cross-file clones only
cross_file_clones = [
    clone for clone in all_clones
    if clone['source_file'] != clone['target_file']
]
```

### Clone Statistics

```python
from collections import Counter

# Count clones by type
clone_types = Counter(clone['clone_type'] for clone in all_clones)
print("Clone distribution:", clone_types)

# Average similarity by type
for clone_type in ['Type-1', 'Type-2', 'Type-3', 'Type-4']:
    clones_of_type = [c for c in all_clones if c['clone_type'] == clone_type]
    if clones_of_type:
        avg_sim = sum(c['similarity'] for c in clones_of_type) / len(clones_of_type)
        print(f"{clone_type}: {len(clones_of_type)} clones, avg similarity {avg_sim:.2%}")

# Find most duplicated files
file_clone_counts = Counter()
for clone in all_clones:
    file_clone_counts[clone['source_file']] += 1
    file_clone_counts[clone['target_file']] += 1

print("Top 10 most duplicated files:")
for file_path, count in file_clone_counts.most_common(10):
    print(f"  {file_path}: {count} clones")
```

## Performance Tips

1. **Batch Processing**: Process files in batches to minimize overhead
2. **Appropriate Thresholds**: Use higher thresholds for large codebases to reduce false positives
3. **Type Selection**: Use Type-1/Type-2 for fast detection, Type-3/Type-4 only when needed
4. **Parallel Execution**: The Rust implementation automatically uses multi-threading via Rayon

## Error Handling

```python
try:
    clones = codegraph_ir.detect_clones_all(fragments)
except ValueError as e:
    print(f"Invalid fragment format: {e}")
except Exception as e:
    print(f"Clone detection failed: {e}")
```

## References

- Bellon et al. (2007): "Comparison and Evaluation of Clone Detection Tools"
- Roy & Cordy (2007): "A Survey on Software Clone Detection Research"
- Koschke (2007): "Survey of Research on Software Clones"

## License

MIT License - see LICENSE file for details
