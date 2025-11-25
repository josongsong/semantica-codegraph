"""
Pyright LSP API Example

Demonstrates:
1. textDocument/definition - "어디서 정의?"
2. textDocument/references - "어디서 사용?"
"""


# ============================================================
# Example Code
# ============================================================

print("=" * 70)
print("  Pyright LSP API 활용: Definition & References")
print("=" * 70)

print("""
예제 코드:

  # file: src/models/user.py
  class User:                      # ← DEFINITION (line 2)
      def __init__(self, name):
          self.name = name

  # file: src/main.py
  from models.user import User     # ← REFERENCE 1 (line 2)

  def create_user(name):
      return User(name)            # ← REFERENCE 2 (line 5)

  def main():
      user = create_user("Alice")  # ← REFERENCE 3 (line 8)
      print(user.name)
""")

print("=" * 70)

# ============================================================
# 1. textDocument/definition
# ============================================================

print("\n📍 1. textDocument/definition (Go-to-Definition)")
print("-" * 70)

print("""
Question: "line 5의 User는 어디서 정의되었나?"

API Call:
  pyright.get_definition(
      file_path="src/main.py",
      line=5,
      column=11
  )

Response:
  Location(
      file_path="src/models/user.py",
      line=2,
      column=6
  )

✅ Result: "src/models/user.py:2 에서 정의됨!"
""")

print("\n💡 활용:")
print("  • Go-to-Definition 기능")
print("  • Import 자동 추적")
print("  • Cross-file Name Resolution")
print("  • NameBinding 구축 (name → definition_node_id)")

# ============================================================
# 2. textDocument/references
# ============================================================

print("\n" + "=" * 70)
print("\n🔍 2. textDocument/references (Find-All-References)")
print("-" * 70)

print("""
Question: "User 클래스가 어디서 사용되나?"

API Call:
  pyright.get_references(
      file_path="src/models/user.py",
      line=2,
      column=6
  )

Response:
  [
      Location(file_path="src/main.py", line=2, column=27),  # import
      Location(file_path="src/main.py", line=5, column=11),  # User(name)
      Location(file_path="src/api.py", line=10, column=15),  # 다른 파일
      ...
  ]

✅ Result: "3개 파일에서 총 5번 사용됨!"
""")

print("\n💡 활용:")
print("  • Find-All-References 기능")
print("  • Impact Analysis (이 함수 바꾸면 어디 영향?)")
print("  • Call Graph 구축")
print("  • Dead Code Detection (사용 안 되는 코드?)")

# ============================================================
# Data Flow
# ============================================================

print("\n" + "=" * 70)
print("\n🔄 Data Flow in Name Resolution Graph")
print("=" * 70)

print("""
1. get_definition() 활용:

   Source Location (src/main.py:5:11, "User")
        │
        ├─► Pyright: get_definition()
        │
        ▼
   Definition Location (src/models/user.py:2:6)
        │
        ▼
   Find IR Node (file_path + line 매칭)
        │
        ▼
   Create NameBinding:
     - name: "User"
     - scope_node_id: "function:create_user"
     - definition_node_id: "class:User"  ← 연결 완료!


2. get_references() 활용:

   Definition Node (class:User)
        │
        ├─► Pyright: get_references()
        │
        ▼
   Reference Locations [
     (src/main.py, line=2),
     (src/main.py, line=5),
     (src/api.py, line=10)
   ]
        │
        ▼
   Create ReferenceSite[] for each location
        │
        ▼
   Build Call Graph / Usage Graph
""")

# ============================================================
# Implementation Strategy
# ============================================================

print("\n" + "=" * 70)
print("\n🏗️  구현 전략")
print("=" * 70)

print("""
Phase 1: Protocol 정의 ✅ (완료)
  • ExternalAnalyzer.get_definition()
  • ExternalAnalyzer.get_references()
  • Location dataclass

Phase 2: Stub 구현 ✅ (완료)
  • PyrightAdapter.get_definition() - TypeInfo 기반 placeholder
  • PyrightAdapter.get_references() - 빈 리스트 반환

Phase 3: LSP Integration (TODO)
  • pyright-langserver 시작
  • LSP client 구현
  • textDocument/definition 요청
  • textDocument/references 요청

Phase 4: Name Resolution Graph (TODO)
  • DefinitionSite, ReferenceSite 모델
  • NameBinding 구축
  • get_definition()으로 cross-file 추적
  • get_references()로 usage 추적
""")

# ============================================================
# Code Example
# ============================================================

print("\n" + "=" * 70)
print("\n💻 사용 예제 (향후)")
print("=" * 70)

print("""
```python
from src.foundation.ir.external_analyzers import PyrightAdapter
from pathlib import Path

# Initialize
pyright = PyrightAdapter(Path("/project/root"))

# 1. Find definition
location = pyright.get_definition(
    Path("src/main.py"),
    line=5,
    column=11
)
print(f"Defined at: {location.file_path}:{location.line}")
# → "Defined at: src/models/user.py:2"

# 2. Find all usages
references = pyright.get_references(
    Path("src/models/user.py"),
    line=2,
    column=6
)
for ref in references:
    print(f"Used at: {ref.file_path}:{ref.line}")
# → "Used at: src/main.py:2"
# → "Used at: src/main.py:5"
# → "Used at: src/api.py:10"

pyright.shutdown()
```
""")

print("\n" + "=" * 70)
print("\n✨ Summary")
print("=" * 70)

print("""
Pyright LSP API 두 가지:

1. ✅ textDocument/definition
   - Input: 심볼 위치 (file, line, col)
   - Output: 정의 위치 (Location)
   - 용도: Go-to-Definition, Name Resolution

2. ✅ textDocument/references
   - Input: 정의 위치 (file, line, col)
   - Output: 사용 위치들 (Location[])
   - 용도: Find-All-References, Call Graph, Impact Analysis

현재 상태:
  ✅ Protocol 정의 완료
  ✅ Stub 구현 완료
  📋 LSP Integration 대기 (pyright-langserver)

다음 단계:
  1. LSP client 구현
  2. Name Resolution Graph 구축
  3. Definition/Reference 활용
""")
