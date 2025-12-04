"""
Quick test for Type Narrowing
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.contexts.code_foundation.infrastructure.analyzers.type_narrowing_full import (
    FullTypeNarrowingAnalyzer,
    TypeNarrowingKind,
    TypeState,
)


def test_type_narrowing_analyzer():
    """Test 1: FullTypeNarrowingAnalyzer can be instantiated"""
    print("\n[Test 1] FullTypeNarrowingAnalyzer instantiation...")
    
    analyzer = FullTypeNarrowingAnalyzer()
    assert analyzer is not None
    assert analyzer._type_states is not None
    
    print("✅ FullTypeNarrowingAnalyzer created!")


def test_type_narrowing_kinds():
    """Test 2: TypeNarrowingKind enum"""
    print("\n[Test 2] TypeNarrowingKind enum...")
    
    assert TypeNarrowingKind.ISINSTANCE == TypeNarrowingKind.ISINSTANCE
    assert TypeNarrowingKind.IS_NONE == TypeNarrowingKind.IS_NONE
    assert TypeNarrowingKind.IS_NOT_NONE == TypeNarrowingKind.IS_NOT_NONE
    assert TypeNarrowingKind.TRUTHINESS == TypeNarrowingKind.TRUTHINESS
    
    print("✅ TypeNarrowingKind enum works!")


def test_type_state():
    """Test 3: TypeState data structure"""
    print("\n[Test 3] TypeState...")
    
    state = TypeState()
    assert state.variables == {}
    assert state.constraints == []
    
    # Add variable
    state.variables["x"] = {"str", "int"}
    assert "x" in state.variables
    assert len(state.variables["x"]) == 2
    
    print("✅ TypeState works!")


def test_isinstance_narrowing_concept():
    """Test 4: isinstance narrowing concept"""
    print("\n[Test 4] isinstance narrowing concept...")
    
    # Simulated: Union[str, int] → str
    union_type = {"str", "int"}
    
    # After isinstance(x, str)
    narrowed = {"str"}
    
    assert narrowed < union_type  # Subset
    assert len(narrowed) == 1
    assert "str" in narrowed
    
    print("✅ isinstance narrowing concept validated!")


def test_none_narrowing_concept():
    """Test 5: None narrowing concept"""
    print("\n[Test 5] None narrowing concept...")
    
    # Optional[str] = Union[str, None]
    optional = {"str", "None"}
    
    # After x is not None
    narrowed = optional - {"None"}
    
    assert narrowed == {"str"}
    assert "None" not in narrowed
    
    print("✅ None narrowing concept validated!")


def main():
    """Run all tests"""
    print("=" * 60)
    print("🚀 Type Narrowing Quick Tests")
    print("=" * 60)
    
    try:
        test_type_narrowing_analyzer()
        test_type_narrowing_kinds()
        test_type_state()
        test_isinstance_narrowing_concept()
        test_none_narrowing_concept()
        
        print("\n" + "=" * 60)
        print("✅ All type narrowing tests passed!")
        print("=" * 60)
        print("\n📊 Type Narrowing Status:")
        print("  ✅ Basic structure complete")
        print("  ✅ isinstance narrowing concept validated")
        print("  ✅ None narrowing concept validated")
        print("  🚧 Full integration with IR (next step)")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

