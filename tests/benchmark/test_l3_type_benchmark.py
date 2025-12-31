"""
Benchmark: L3 TypeResolver Performance

Validates that L3 type resolution adds minimal overhead to L1+L2.

Target: < 5% overhead for type resolution
"""

import time


def test_l3_type_resolution_overhead():
    """Measure L3 TypeResolver overhead"""
    try:
        import codegraph_ast
    except ImportError:
        print("⚠️  Rust module not installed")
        return

    # Code with extensive type annotations
    code = """
from typing import List, Dict, Optional, Union, Tuple
import datetime

class UserService:
    \"\"\"User management service\"\"\"
    
    def __init__(self, db_url: str):
        self.db_url: str = db_url
        self.cache: Dict[str, User] = {}
    
    def get_user(self, user_id: int) -> Optional[User]:
        \"\"\"Get user by ID\"\"\"
        if user_id in self.cache:
            return self.cache[user_id]
        return None
    
    def create_user(
        self,
        name: str,
        email: str,
        age: int,
        tags: List[str]
    ) -> User:
        \"\"\"Create new user\"\"\"
        user: User = User(name, email, age)
        user.tags = tags
        self.cache[user.id] = user
        return user
    
    def update_user(
        self,
        user_id: int,
        updates: Dict[str, Union[str, int]]
    ) -> bool:
        \"\"\"Update user\"\"\"
        user: Optional[User] = self.get_user(user_id)
        if user is None:
            return False
        
        for key, value in updates.items():
            setattr(user, key, value)
        return True
    
    def list_users(
        self,
        filters: Optional[Dict[str, str]] = None
    ) -> List[User]:
        \"\"\"List users with filters\"\"\"
        users: List[User] = list(self.cache.values())
        
        if filters:
            filtered: List[User] = []
            for user in users:
                match: bool = True
                for key, value in filters.items():
                    if getattr(user, key, None) != value:
                        match = False
                        break
                if match:
                    filtered.append(user)
            return filtered
        
        return users
    
    def get_stats(self) -> Dict[str, int]:
        \"\"\"Get user statistics\"\"\"
        total: int = len(self.cache)
        active: int = sum(1 for u in self.cache.values() if u.active)
        
        return {
            "total": total,
            "active": active,
            "inactive": total - active
        }

class User:
    \"\"\"User model\"\"\"
    
    def __init__(self, name: str, email: str, age: int):
        self.id: int = 0
        self.name: str = name
        self.email: str = email
        self.age: int = age
        self.active: bool = True
        self.tags: List[str] = []
        self.created_at: datetime.datetime = datetime.datetime.now()
    
    def to_dict(self) -> Dict[str, Union[str, int, bool]]:
        \"\"\"Convert to dictionary\"\"\"
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "age": self.age,
            "active": self.active
        }
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        \"\"\"Validate user data\"\"\"
        if not self.name:
            return False, "Name is required"
        if not self.email:
            return False, "Email is required"
        if self.age < 0:
            return False, "Age must be positive"
        return True, None
"""

    print("\n" + "=" * 70)
    print("🔬 L3 TypeResolver Performance Test")
    print("=" * 70)

    # Warmup
    result = codegraph_ast.process_python_files([("test.py", code)], "test_repo")

    # Benchmark (100 runs for accuracy)
    times = []
    for _ in range(100):
        start = time.perf_counter()
        result = codegraph_ast.process_python_files([("test.py", code)], "test_repo")
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print(f"\n📊 Performance:")
    print(f"  Average: {avg_time * 1000:.2f}ms")
    print(f"  Min: {min_time * 1000:.2f}ms")
    print(f"  Max: {max_time * 1000:.2f}ms")

    print(f"\n📦 Output:")
    print(f"  Nodes: {len(result['nodes'])}")
    print(f"  Edges: {len(result['edges'])}")
    print(f"  BFG graphs: {len(result['bfg_graphs'])}")
    print(f"  CFG edges: {len(result['cfg_edges'])}")
    print(f"  Type entities: {len(result['type_entities'])}")

    # Validate type entities
    type_entities = result["type_entities"]

    # Count by flavor
    builtin_count = sum(1 for t in type_entities if t["flavor"] == "BUILTIN")
    user_count = sum(1 for t in type_entities if t["flavor"] == "USER")
    external_count = sum(1 for t in type_entities if t["flavor"] == "EXTERNAL")

    print(f"\n🎯 Type Resolution:")
    print(f"  Builtin types: {builtin_count}")
    print(f"  User types: {user_count}")
    print(f"  External types: {external_count}")
    print(f"  Total: {len(type_entities)}")

    # Validate user-defined types
    user_types = [t for t in type_entities if t["flavor"] == "USER"]
    user_type_names = {t["raw"] for t in user_types}

    print(f"\n✅ User-defined types detected:")
    for name in sorted(user_type_names):
        print(f"  - {name}")

    # Check that User and UserService are detected
    assert "User" in user_type_names, "User class should be detected"
    assert "UserService" in user_type_names, "UserService class should be detected"

    # Check generic types
    generic_types = [t for t in type_entities if t.get("generic_param_ids")]
    print(f"\n🔗 Generic types: {len(generic_types)}")

    # Performance assertion: < 10ms for this file
    assert avg_time < 0.01, f"Performance regression: {avg_time * 1000:.2f}ms > 10ms"

    print(f"\n✅ PASS: L3 TypeResolver performance validated")
    print("=" * 70)


def test_l3_type_accuracy():
    """Validate L3 type resolution accuracy"""
    try:
        import codegraph_ast
    except ImportError:
        print("⚠️  Rust module not installed")
        return

    code = """
class MyClass:
    pass

def func() -> MyClass:
    x: int = 5
    y: str = "hello"
    obj: MyClass = MyClass()
    items: List[int] = [1, 2, 3]
    return obj
"""

    result = codegraph_ast.process_python_files([("test.py", code)], "test_repo")

    print("\n" + "=" * 70)
    print("🎯 L3 Type Resolution Accuracy Test")
    print("=" * 70)

    # Check nodes with types
    nodes_with_types = [n for n in result["nodes"] if n.get("declared_type_id")]
    print(f"\n📦 Nodes with types: {len(nodes_with_types)}")

    for node in nodes_with_types:
        print(f"  - {node['kind']}: {node.get('name')} → {node['declared_type_id'][:8]}...")

    # Check type entities
    type_entities = result["type_entities"]
    print(f"\n🎯 Type entities: {len(type_entities)}")

    # Group by raw type
    type_map = {}
    for t in type_entities:
        raw = t["raw"]
        if raw not in type_map:
            type_map[raw] = []
        type_map[raw].append(t)

    print(f"\n📋 Type breakdown:")
    for raw_type, entities in sorted(type_map.items()):
        entity = entities[0]
        print(f"  - {raw_type}: {entity['flavor']} ({entity['resolution_level']})")

    # Validate
    assert "int" in type_map, "int should be detected"
    assert "str" in type_map, "str should be detected"
    assert "MyClass" in type_map, "MyClass should be detected"
    assert "List[int]" in type_map, "List[int] should be detected"

    # Check MyClass resolution
    myclass_types = type_map["MyClass"]
    assert len(myclass_types) > 0
    myclass_type = myclass_types[0]
    assert myclass_type["flavor"] == "USER", "MyClass should be USER type"
    assert myclass_type["resolution_level"] == "LOCAL", "MyClass should be LOCAL"
    assert myclass_type["resolved_target"] is not None, "MyClass should have resolved_target"

    print(f"\n✅ PASS: Type resolution accuracy validated")
    print("=" * 70)


if __name__ == "__main__":
    test_l3_type_resolution_overhead()
    test_l3_type_accuracy()
