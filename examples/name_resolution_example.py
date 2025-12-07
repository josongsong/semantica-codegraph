"""
Name Resolution Example

Shows the difference between:
1. Self-implementation (Tree-sitter + IR)
2. Pyright enhancement (LSP API)
"""

# ============================================================
# Example Code
# ============================================================

EXAMPLE_CODE = """
# file: src/models/user.py
class User:
    def __init__(self, name: str):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}"

# file: src/main.py
from models.user import User

def create_user(name: str):
    user = User(name)  # ← Q1: User는 어디서 정의?
    return user

def main():
    user = create_user("Alice")  # ← Q2: create_user는 어디서 정의?
    print(user.greet())          # ← Q3: greet는 어디서 정의?
"""


# ============================================================
# Resolution Methods
# ============================================================


def demo_self_resolution():
    """
    자체 구현 (Tree-sitter + IR)
    """
    print("=" * 60)
    print("1️⃣  Self-Implementation (Tree-sitter + IR)")
    print("=" * 60)

    print("\n📊 Available Information:")
    print("  ✅ IMPORTS Edge: from models.user import User")
    print("  ✅ CONTAINS Edge: User is in src/models/user.py")
    print("  ✅ Node.fqn: models.user.User")
    print("  ✅ DFG: user variable → User() call")

    print("\n🔍 Resolution Process:")
    print("  Q1: User는 어디서 정의?")
    print("      → Step 1: IMPORTS Edge → 'models.user' 모듈")
    print("      → Step 2: IR nodes → file_path='src/models/user.py'")
    print("      → Step 3: Find node where name='User' and kind='class'")
    print("      ✅ Result: src/models/user.py:2 (class User)")

    print("\n  Q2: create_user는 어디서 정의?")
    print("      → Step 1: Same file resolution")
    print("      → Step 2: Find node where name='create_user' and kind='function'")
    print("      ✅ Result: src/main.py:4 (def create_user)")

    print("\n  Q3: greet는 어디서 정의?")
    print("      → Step 1: user.greet → user는 User 타입")
    print("      → Step 2: TypeResolver → User 클래스 찾기")
    print("      → Step 3: User의 children 중 name='greet' 찾기")
    print("      ✅ Result: src/models/user.py:6 (def greet)")

    print("\n✨ Capabilities:")
    print("  ✅ Local scope (same file)")
    print("  ✅ Direct imports (from X import Y)")
    print("  ✅ Class methods (basic)")
    print("  ❌ Alias imports (import pandas as pd)")
    print("  ❌ Inheritance chain (B(A).foo → A.foo)")
    print("  ❌ Dynamic imports")
    print()


def demo_pyright_resolution():
    """
    Pyright 강화
    """
    print("=" * 60)
    print("2️⃣  Pyright Enhancement (LSP API)")
    print("=" * 60)

    print("\n📊 Additional Information from Pyright:")
    print("  ✅ textDocument/definition → Exact definition location")
    print("  ✅ textDocument/references → All usage sites")
    print("  ✅ textDocument/hover → Type + documentation")
    print("  ✅ Auto alias resolution")
    print("  ✅ Auto inheritance resolution (MRO)")

    print("\n🔍 Enhanced Resolution Process:")
    print("  Q1: User는 어디서 정의?")
    print("      → pyright.get_definition('src/main.py', line=4, col=10)")
    print("      ✅ Result: {")
    print("           file: 'src/models/user.py',")
    print("           line: 2,")
    print("           col: 6,")
    print("           symbol: 'User',")
    print("           kind: 'class'")
    print("         }")

    print("\n  Q2: create_user는 어디서 정의?")
    print("      → pyright.get_definition('src/main.py', line=8, col=11)")
    print("      ✅ Result: {")
    print("           file: 'src/main.py',")
    print("           line: 4,")
    print("           col: 4,")
    print("           symbol: 'create_user'")
    print("         }")

    print("\n  Q3: greet는 어디서 정의?")
    print("      → pyright.get_definition('src/main.py', line=9, col=15)")
    print("      ✅ Result: {")
    print("           file: 'src/models/user.py',")
    print("           line: 6,")
    print("           symbol: 'greet'")
    print("         }")

    print("\n✨ Enhanced Capabilities:")
    print("  ✅ All from self-implementation")
    print("  ✅ Alias imports (pd.DataFrame → pandas.core.frame.DataFrame)")
    print("  ✅ Inheritance chain (B(A).foo → A.foo via MRO)")
    print("  ✅ Dynamic imports (importlib)")
    print("  ✅ Type inference (x = foo(); x.bar → bar's definition)")
    print("  ✅ Cross-package resolution")
    print()


def demo_hybrid_approach():
    """
    Hybrid: 자체 + Pyright
    """
    print("=" * 60)
    print("3️⃣  Hybrid Approach (Best of Both)")
    print("=" * 60)

    print("\n🎯 Strategy:")
    print("  1. Always try self-implementation first (fast)")
    print("  2. If ambiguous → query Pyright (accurate)")
    print("  3. Cache Pyright results (performance)")

    print("\n📊 Performance:")
    print("  Self-implementation: ~1-5ms per lookup")
    print("  Pyright query: ~50-200ms per lookup (first time)")
    print("  Pyright cached: ~1ms per lookup")

    print("\n🔧 Implementation:")
    print("  ```python")
    print("  class NameResolver:")
    print("      def resolve(self, name, location):")
    print("          # 1. Try local/module scope (fast)")
    print("          result = self._resolve_local(name, location)")
    print("          if result:")
    print("              return result")
    print("          ")
    print("          # 2. Try IR-based resolution")
    print("          result = self._resolve_from_ir(name, location)")
    print("          if result and result.confidence > 0.8:")
    print("              return result")
    print("          ")
    print("          # 3. Query Pyright (accurate but slower)")
    print("          if self.external_analyzer:")
    print("              result = self.external_analyzer.get_definition(...)")
    print("              return result")
    print("          ")
    print("          return None  # Cannot resolve")
    print("  ```")

    print("\n✨ Benefits:")
    print("  ✅ Fast for 90% of cases (local/module scope)")
    print("  ✅ Accurate for complex cases (cross-file, alias)")
    print("  ✅ Works without Pyright (graceful degradation)")
    print("  ✅ Pyright enhances but doesn't replace")
    print()


# ============================================================
# Pyright Data Flow
# ============================================================


def show_pyright_data_flow():
    """
    Pyright 데이터 활용 흐름
    """
    print("=" * 60)
    print("📊 Pyright Data Flow in Our Architecture")
    print("=" * 60)

    print(
        """
    ┌─────────────────┐
    │   Source Code   │
    └────────┬────────┘
             │
             ├───────────────────────────────┐
             │                               │
    ┌────────▼────────┐            ┌────────▼────────┐
    │  Tree-sitter    │            │    Pyright      │
    │  (AST Parser)   │            │  (Type Checker) │
    └────────┬────────┘            └────────┬────────┘
             │                               │
             │                               │
    ┌────────▼────────┐            ┌────────▼────────┐
    │   IR Generator  │◄───────────│  TypeInfo       │
    │  (Basic IR)     │            │  - inferred_type│
    └────────┬────────┘            │  - def_path     │
             │                     │  - def_line     │
             │                     └─────────────────┘
             │
    ┌────────▼────────┐
    │   IR Document   │
    │  - nodes        │
    │  - edges        │
    │  - types ◄──────┼─── Pyright enriched types
    │  - signatures   │
    └────────┬────────┘
             │
    ┌────────▼──────────────┐
    │ Name Resolution Graph │
    │  - bindings           │
    │  - definitions ◄──────┼─── Pyright definition locations
    │  - references ◄───────┼─── Pyright reference sites
    └───────────────────────┘

    Pyright 기여:
    1. Type Resolution (이미 구현 ✅)
       TypeInfo.inferred_type → TypeEntity

    2. Definition Location (Name Resolution용)
       TypeInfo.definition_path → DefinitionSite
       TypeInfo.definition_line → NameBinding

    3. References (향후)
       textDocument/references → ReferenceSite[]
    """
    )


# ============================================================
# Main
# ============================================================


def main():
    print("\n" + "🔍 Name Resolution: Pyright 활용 전략".center(60))
    print()

    print("📝 Example Code:")
    print(EXAMPLE_CODE)
    print()

    # 1. Self-implementation
    demo_self_resolution()

    # 2. Pyright enhancement
    demo_pyright_resolution()

    # 3. Hybrid approach
    demo_hybrid_approach()

    # 4. Data flow
    show_pyright_data_flow()

    print("=" * 60)
    print("🎯 Summary")
    print("=" * 60)
    print(
        """
    Pyright에서 활용할 정보:

    1. ✅ Type Information (이미 활용 중)
       - TypeInfo.inferred_type
       - TypeInfo.declared_type
       → TypeEntity.resolution_level = FULL

    2. 🚀 Definition Location (Name Resolution용)
       - TypeInfo.definition_path
       - TypeInfo.definition_line
       → DefinitionSite, NameBinding

    3. 📋 References (향후)
       - textDocument/references API
       → ReferenceSite[], Call Graph

    구현 전략:
    - Phase 1: 자체 구현 (70% 완료, IMPORTS/CONTAINS Edge 활용)
    - Phase 2: Pyright 통합 (definition_path/line 활용)
    - Phase 3: Full LSP (references, hover, rename)

    Pyright는 "선택적 강화제"!
    - 없으면: 기본 resolution (빠름)
    - 있으면: 정확도 향상 (cross-file, alias, MRO)
    """
    )


if __name__ == "__main__":
    main()
