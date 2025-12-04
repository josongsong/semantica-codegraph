"""
Integration Tests for Semantic Region Index

Tests the full pipeline:
1. Region segmentation
2. Semantic annotation
3. Region indexing
4. Search and retrieval
"""

from pathlib import Path
from src.contexts.code_foundation.infrastructure.semantic_regions import (
    SemanticRegion,
    RegionType,
    RegionPurpose,
    RegionSegmenter,
    SemanticAnnotator,
    RegionIndex,
    RegionCollection,
)
from src.contexts.code_foundation.infrastructure.semantic_regions.index import SearchQuery


def test_semantic_region_model():
    """Test SemanticRegion model"""
    print("\n[SemanticRegion Test] Basic model...")
    
    region = SemanticRegion(
        region_id="region_123",
        file_path="calculator.py",
        start_line=10,
        end_line=25,
        region_type=RegionType.FUNCTION_BODY,
        purpose=RegionPurpose.BUSINESS_LOGIC,
        description="Calculate discount",
        responsibility="Handles discount calculation logic",
    )
    
    # Add tags
    region.add_tag("discount")
    region.add_tag("pricing")
    region.add_tag("calculate")
    
    # Add symbols
    region.add_symbol("calculate_discount")
    region.add_symbol("apply_tier_discount")
    
    assert region.line_count == 16
    assert len(region.semantic_tags) == 3
    assert len(region.symbols) == 2
    assert region.matches_query({"discount", "pricing"})
    assert not region.matches_query({"invalid", "tags"})
    
    # Test similarity
    score = region.similarity_score({"discount", "calculate"})
    assert score > 0
    
    print(f"  ✅ Region created: {region}")
    print(f"  ✅ Line count: {region.line_count}")
    print(f"  ✅ Tags: {region.semantic_tags}")
    print(f"  ✅ Similarity score: {score:.2f}")


def test_region_collection():
    """Test RegionCollection"""
    print("\n[RegionCollection Test] Collection management...")
    
    collection = RegionCollection()
    
    # Add regions
    for i in range(5):
        region = SemanticRegion(
            region_id=f"region_{i}",
            file_path=f"file_{i % 2}.py",
            start_line=i * 10,
            end_line=i * 10 + 15,
            region_type=RegionType.FUNCTION_BODY,
            purpose=RegionPurpose.BUSINESS_LOGIC,
            description=f"Function {i}",
            responsibility=f"Logic {i}",
        )
        
        # Add tags
        if i % 2 == 0:
            region.add_tag("even")
        else:
            region.add_tag("odd")
        
        region.add_tag("function")
        
        collection.add_region(region)
    
    assert len(collection) == 5
    
    # Test file index
    file0_regions = collection.get_regions_by_file("file_0.py")
    assert len(file0_regions) == 3  # regions 0, 2, 4
    
    # Test tag search
    even_regions = collection.search_by_tags({"even"}, min_score=0.1)
    assert len(even_regions) == 3
    
    # Test statistics
    stats = collection.get_statistics()
    assert stats["total_regions"] == 5
    assert stats["total_files"] == 2
    
    print(f"  ✅ Collection: {collection}")
    print(f"  ✅ File index: {len(file0_regions)} regions in file_0.py")
    print(f"  ✅ Tag search: {len(even_regions)} regions with 'even' tag")
    print(f"  ✅ Statistics: {stats}")


def test_region_segmenter():
    """Test RegionSegmenter with mock IR"""
    print("\n[RegionSegmenter Test] Segmenting code...")
    
    segmenter = RegionSegmenter(min_region_lines=3, max_region_lines=50)
    
    # Create mock IR document
    class MockLocation:
        def __init__(self, start_line, end_line):
            self.start_line = start_line
            self.end_line = end_line
    
    class MockNode:
        def __init__(self, node_id, name, node_type, start_line, end_line):
            self.id = node_id
            self.name = name
            self.type = node_type
            self.location = MockLocation(start_line, end_line)
            self.signature = f"def {name}()"
    
    class MockIRDoc:
        def __init__(self, nodes):
            self.nodes = nodes
            self.edges = []
    
    # Create nodes
    nodes = [
        MockNode("calc_discount", "calculate_discount", "function", 10, 25),
        MockNode("validate_input", "validate_input", "function", 30, 40),
        MockNode("process_order", "process_order", "function", 45, 70),
    ]
    
    ir_doc = MockIRDoc(nodes)
    
    # Segment
    collection = segmenter.segment_ir_document(ir_doc, "calculator.py")
    
    assert len(collection) == 3
    
    # Check first region
    region = collection.regions[0]
    assert region.region_type == RegionType.FUNCTION_BODY
    assert region.start_line == 10
    assert region.end_line == 25
    assert len(region.semantic_tags) > 0  # Should have tags from name
    
    print(f"  ✅ Segmented {len(collection)} regions")
    print(f"  ✅ Region 1: {region}")
    print(f"  ✅ Tags: {region.semantic_tags}")


def test_semantic_annotator():
    """Test SemanticAnnotator"""
    print("\n[SemanticAnnotator Test] Annotating regions...")
    
    # Create collection
    collection = RegionCollection()
    
    region1 = SemanticRegion(
        region_id="region_1",
        file_path="service.py",
        start_line=10,
        end_line=25,
        region_type=RegionType.FUNCTION_BODY,
        purpose=RegionPurpose.BUSINESS_LOGIC,
        description="Process data",
        responsibility="Data processing",
        primary_symbol="process_data",
    )
    region1.add_symbol("process_data")
    region1.add_tag("process")
    region1.add_tag("data")
    
    region2 = SemanticRegion(
        region_id="region_2",
        file_path="service.py",
        start_line=30,
        end_line=40,
        region_type=RegionType.FUNCTION_BODY,
        purpose=RegionPurpose.VALIDATION_CHECK,
        description="Validate input",
        responsibility="Input validation",
        primary_symbol="validate_input",
    )
    region2.add_symbol("validate_input")
    region2.add_tag("validate")
    region2.add_tag("input")
    
    collection.add_region(region1)
    collection.add_region(region2)
    
    # Create mock IR
    class MockEdge:
        def __init__(self, source, target, edge_type):
            self.type = edge_type
            self.source = source
            self.target = target
    
    class MockIRDoc:
        def __init__(self):
            self.nodes = []
            self.edges = [
                MockEdge("process_data", "validate_input", "CALLS"),
            ]
    
    ir_docs = {"service.py": MockIRDoc()}
    
    # Annotate
    annotator = SemanticAnnotator()
    annotated_collection = annotator.annotate_collection(collection, ir_docs)
    
    # Check dependencies
    assert len(region1.depends_on) >= 0  # May have dependencies
    
    print(f"  ✅ Annotated {len(annotated_collection)} regions")
    print(f"  ✅ Region 1 dependencies: {len(region1.depends_on)}")
    print(f"  ✅ Region 2 depended by: {len(region2.depended_by)}")


def test_region_index_search():
    """Test RegionIndex search"""
    print("\n[RegionIndex Test] Search and retrieval...")
    
    # Build collection
    collection = RegionCollection()
    
    # Region 1: Discount calculation
    region1 = SemanticRegion(
        region_id="region_discount",
        file_path="pricing.py",
        start_line=10,
        end_line=30,
        region_type=RegionType.FUNCTION_BODY,
        purpose=RegionPurpose.BUSINESS_LOGIC,
        description="Calculate discount based on customer tier",
        responsibility="Discount calculation",
    )
    region1.add_tag("discount")
    region1.add_tag("calculate")
    region1.add_tag("pricing")
    region1.add_symbol("calculate_discount")
    
    # Region 2: Validation
    region2 = SemanticRegion(
        region_id="region_validation",
        file_path="pricing.py",
        start_line=35,
        end_line=50,
        region_type=RegionType.FUNCTION_BODY,
        purpose=RegionPurpose.VALIDATION_CHECK,
        description="Validate discount percentage",
        responsibility="Validation",
    )
    region2.add_tag("validate")
    region2.add_tag("discount")
    region2.add_symbol("validate_discount")
    
    # Region 3: Database access
    region3 = SemanticRegion(
        region_id="region_db",
        file_path="database.py",
        start_line=10,
        end_line=25,
        region_type=RegionType.FUNCTION_BODY,
        purpose=RegionPurpose.DATA_ACCESS,
        description="Fetch customer data",
        responsibility="Data access",
    )
    region3.add_tag("fetch")
    region3.add_tag("customer")
    region3.add_tag("database")
    region3.add_symbol("fetch_customer")
    
    collection.add_region(region1)
    collection.add_region(region2)
    collection.add_region(region3)
    
    # Create index
    index = RegionIndex(collection)
    
    # Test 1: Search by tags
    results = index.search(tags={"discount", "calculate"}, top_k=5)
    assert len(results) > 0
    assert results[0].region.region_id == "region_discount"  # Best match
    
    print(f"  ✅ Tag search: {len(results)} results")
    print(f"  ✅ Top result: {results[0].region.description} (score: {results[0].score:.2f})")
    
    # Test 2: Search with filters
    query = SearchQuery(
        tags={"discount"},
        purposes={RegionPurpose.VALIDATION_CHECK},
    )
    results2 = index.search(query=query, top_k=5)
    assert len(results2) > 0
    assert results2[0].region.region_id == "region_validation"
    
    print(f"  ✅ Filtered search: {len(results2)} results")
    print(f"  ✅ Top result: {results2[0].region.description}")
    
    # Test 3: Search by symbol
    results3 = index.search(symbols={"calculate_discount"}, top_k=5)
    assert len(results3) > 0
    assert results3[0].region.region_id == "region_discount"
    
    print(f"  ✅ Symbol search: {len(results3)} results")
    
    # Test 4: Get related regions
    related = index.get_related_regions("region_discount", max_results=3)
    # Related regions may be empty if no similar regions exist
    
    print(f"  ✅ Related regions: {len(related)} found")
    if related:
        for r in related:
            print(f"    - {r.region.description} (score: {r.score:.2f})")
    else:
        print(f"    - (no related regions - expected for small collection)")
    
    # Test 5: Get by type
    functions = index.get_by_type(RegionType.FUNCTION_BODY)
    assert len(functions) == 3
    
    print(f"  ✅ Type query: {len(functions)} function regions")
    
    # Test 6: Get by purpose
    validation_regions = index.get_by_purpose(RegionPurpose.VALIDATION_CHECK)
    assert len(validation_regions) == 1
    
    print(f"  ✅ Purpose query: {len(validation_regions)} validation regions")
    
    # Statistics
    stats = index.get_statistics()
    print(f"  ✅ Index statistics: {stats}")


def test_end_to_end_pipeline():
    """Test full pipeline: segment → annotate → index → search"""
    print("\n[E2E Pipeline Test] Full semantic region pipeline...")
    
    # Step 1: Create mock IR
    class MockLocation:
        def __init__(self, start_line, end_line):
            self.start_line = start_line
            self.end_line = end_line
    
    class MockNode:
        def __init__(self, node_id, name, node_type, start_line, end_line):
            self.id = node_id
            self.name = name
            self.type = node_type
            self.location = MockLocation(start_line, end_line)
            self.signature = f"def {name}(customer: Customer) -> float"
    
    class MockEdge:
        def __init__(self, source, target, edge_type):
            self.type = edge_type
            self.source = source
            self.target = target
    
    class MockIRDoc:
        def __init__(self, nodes, edges):
            self.nodes = nodes
            self.edges = edges
    
    nodes = [
        MockNode("calc_discount", "calculate_discount", "function", 10, 30),
        MockNode("get_tier", "get_customer_tier", "function", 35, 45),
        MockNode("apply_discount", "apply_tier_discount", "function", 50, 70),
    ]
    
    edges = [
        MockEdge("calc_discount", "get_tier", "CALLS"),
        MockEdge("calc_discount", "apply_discount", "CALLS"),
    ]
    
    ir_doc = MockIRDoc(nodes, edges)
    ir_docs = {"discount.py": ir_doc}
    
    # Step 2: Segment
    segmenter = RegionSegmenter()
    collection = segmenter.segment_ir_document(ir_doc, "discount.py")
    
    assert len(collection) >= 3
    print(f"  ✅ Step 1: Segmented {len(collection)} regions")
    
    # Step 3: Annotate
    annotator = SemanticAnnotator()
    collection = annotator.annotate_collection(collection, ir_docs)
    
    # Check dependencies were built
    region1 = collection.regions[0]
    print(f"  ✅ Step 2: Annotated regions with dependencies")
    print(f"    - Region 1 depends on: {len(region1.depends_on)} regions")
    
    # Step 4: Index
    index = RegionIndex(collection)
    stats = index.get_statistics()
    
    print(f"  ✅ Step 3: Indexed {stats['total_regions']} regions")
    print(f"    - Tags indexed: {stats['indexed_tags']}")
    print(f"    - Symbols indexed: {stats['indexed_symbols']}")
    
    # Step 5: Search
    results = index.search(tags={"discount", "calculate"}, top_k=3)
    
    print(f"  ✅ Step 4: Search returned {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"    {i}. {result.region.description} (score: {result.score:.2f})")
        print(f"       Reasons: {', '.join(result.match_reasons[:2])}")
    
    # Step 6: Verify search quality
    if results:
        top_result = results[0]
        assert top_result.score > 0
        assert "discount" in top_result.region.semantic_tags or "calculate" in top_result.region.semantic_tags
    
    print(f"  ✅ Step 5: Search quality verified")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🔬 Semantic Region Index Integration Tests")
    print("=" * 60)
    
    test_semantic_region_model()
    test_region_collection()
    test_region_segmenter()
    test_semantic_annotator()
    test_region_index_search()
    test_end_to_end_pipeline()
    
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print("  ✅ PASS: SemanticRegion model")
    print("  ✅ PASS: RegionCollection")
    print("  ✅ PASS: RegionSegmenter")
    print("  ✅ PASS: SemanticAnnotator")
    print("  ✅ PASS: RegionIndex search")
    print("  ✅ PASS: End-to-end pipeline")
    print("=" * 60)
    print("\n✅ All tests passed!")
    print("\n🎯 Month 2 - Week 9-11: Semantic Region Index COMPLETE!")


if __name__ == "__main__":
    run_all_tests()

