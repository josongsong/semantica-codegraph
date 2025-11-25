"""
Pyright Integration Example

Demonstrates how to use Pyright for enhanced type resolution in IR generation.

Usage:
    python examples/pyright_example.py
"""

from pathlib import Path

from src.foundation.generators.python_generator import PythonIRGenerator
from src.foundation.ir.external_analyzers import PyrightAdapter
from src.foundation.parsing import SourceFile


def main():
    """Demonstrate Pyright integration"""
    print("🔍 Pyright Integration Demo\n")

    # Sample code with complex types
    sample_code = '''
from typing import List, Dict, Optional

class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

def get_users() -> List[User]:
    """Get list of users"""
    return [User("Alice", 30), User("Bob", 25)]

def find_user(users: List[User], name: str) -> Optional[User]:
    """Find user by name"""
    for user in users:
        if user.name == name:
            return user
    return None

def process_data(data: Dict[str, int]) -> int:
    """Process dictionary data"""
    return sum(data.values())
'''

    print("📝 Sample Code:")
    print("=" * 60)
    print(sample_code)
    print("=" * 60)
    print()

    # Create a temporary file
    temp_file = Path("/tmp/sample.py")
    temp_file.write_text(sample_code)

    # Create SourceFile
    source = SourceFile(str(temp_file), sample_code, "python")

    print("🚀 Scenario 1: WITHOUT Pyright")
    print("-" * 60)

    # Generate IR without Pyright
    generator_basic = PythonIRGenerator("demo-repo")
    ir_basic = generator_basic.generate(source, "snapshot-1")

    print(f"✓ Nodes generated: {len(ir_basic.nodes)}")
    print(f"✓ Types collected: {len(ir_basic.types)}")
    print(f"✓ Signatures: {len(ir_basic.signatures)}")

    # Show type resolution levels
    print("\n📊 Type Resolution Levels (Basic):")
    for type_entity in ir_basic.types[:5]:  # Show first 5
        print(f"  • {type_entity.raw:20s} → {type_entity.resolution_level.value:10s} ({type_entity.flavor.value})")

    print("\n" + "=" * 60)
    print()

    print("🚀 Scenario 2: WITH Pyright")
    print("-" * 60)

    # Initialize Pyright adapter
    try:
        pyright_adapter = PyrightAdapter(Path("/tmp"))

        # Generate IR with Pyright
        generator_enhanced = PythonIRGenerator("demo-repo", external_analyzer=pyright_adapter)
        ir_enhanced = generator_enhanced.generate(source, "snapshot-2")

        print(f"✓ Nodes generated: {len(ir_enhanced.nodes)}")
        print(f"✓ Types collected: {len(ir_enhanced.types)}")
        print(f"✓ Signatures: {len(ir_enhanced.signatures)}")

        # Show enhanced type resolution
        print("\n📊 Type Resolution Levels (Enhanced):")
        for type_entity in ir_enhanced.types[:5]:  # Show first 5
            print(f"  • {type_entity.raw:20s} → {type_entity.resolution_level.value:10s} ({type_entity.flavor.value})")

        print("\n✨ Enhanced Features:")
        print("  • External type checker integration")
        print("  • FULL resolution level for complex types")
        print("  • Better inference for user-defined types")

        # Show functions with signatures
        print("\n🔧 Function Signatures:")
        for node in ir_enhanced.nodes:
            if node.signature_id:
                sig = next((s for s in ir_enhanced.signatures if s.id == node.signature_id), None)
                if sig:
                    print(f"  • {node.name}:")
                    print(f"      Parameters: {len(sig.parameter_type_ids or [])} types")
                    print(f"      Return type: {sig.return_type_id or 'None'}")

        # Cleanup
        pyright_adapter.shutdown()

    except Exception as e:
        print(f"⚠️  Pyright not available: {e}")
        print("   (This is expected if pyright is not installed)")
        print("   Install with: pip install pyright")

    print("\n" + "=" * 60)
    print()

    print("📚 Summary:")
    print("  ✓ Pyright integration adds advanced type resolution")
    print("  ✓ Works seamlessly with existing IR generation")
    print("  ✓ Gracefully degrades if Pyright is not available")
    print("  ✓ Provides FULL resolution level for better analysis")
    print()

    # Cleanup
    temp_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
