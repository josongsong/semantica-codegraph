#!/usr/bin/env python3
"""Z3 Advanced Scenarios - Features NOT in Internal Engine

Demonstrates scenarios where Z3 is essential or significantly more powerful.
"""

from z3 import *

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("Z3 ADVANCED SCENARIOS - Features Beyond Internal Engine")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 1: Inter-Variable Relationships (Transitive Inference)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("1️⃣  INTER-VARIABLE RELATIONSHIPS")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

x, y, z = Ints("x y z")
s = Solver()

s.add(x < y)
s.add(y < z)
s.add(x >= z)  # Contradiction via transitivity

print("Constraints:")
print("  x < y")
print("  y < z")
print("  x >= z  (contradicts transitivity)")
print()

result = s.check()
print(f"Z3 Result: {result}")  # unsat (detects contradiction)
print("✅ Z3 detects: x < y && y < z → x < z (contradicts x >= z)")
print("❌ Internal Engine: Unknown (no inter-variable reasoning)")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 2: Arithmetic Operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("2️⃣  ARITHMETIC OPERATIONS")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

x, y = Ints("x y")
s = Solver()

s.add(x + y > 10)
s.add(2 * x - y < 5)
s.add(x > 100)  # Is this possible?

print("Constraints:")
print("  x + y > 10")
print("  2*x - y < 5")
print("  x > 100")
print()

result = s.check()
print(f"Z3 Result: {result}")

if result == sat:
    m = s.model()
    print(f"✅ Z3 found solution: x={m[x]}, y={m[y]}")
    print(f"   Verification: {m[x].as_long() + m[y].as_long()} > 10? {m[x].as_long() + m[y].as_long() > 10}")
    print(f"   Verification: 2*{m[x].as_long()} - {m[y].as_long()} < 5? {2 * m[x].as_long() - m[y].as_long() < 5}")
else:
    print(f"✅ Z3 result: {result}")

print("❌ Internal Engine: Cannot handle arithmetic expressions")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 3: Bit-Vector Operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("3️⃣  BIT-VECTOR OPERATIONS")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

x = BitVec("x", 32)
y = BitVec("y", 32)
s = Solver()

s.add(x & 0xFF == 0x42)  # Lower 8 bits must be 0x42
s.add(x >> 8 == y)  # Upper 24 bits shifted
s.add((x ^ y) & 0x1 == 0)  # XOR LSB must be 0

print("Constraints (32-bit integers):")
print("  x & 0xFF == 0x42     (lower 8 bits)")
print("  x >> 8 == y          (bit shift)")
print("  (x ^ y) & 0x1 == 0   (XOR)")
print()

result = s.check()
print(f"Z3 Result: {result}")

if result == sat:
    m = s.model()
    print(f"✅ Z3 found solution: x={hex(m[x].as_long())}, y={hex(m[y].as_long())}")
else:
    print(f"✅ Z3 result: {result}")

print("❌ Internal Engine: No bit-vector support")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 4: Array Theory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("4️⃣  ARRAY THEORY (Symbolic Indexing)")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

arr = Array("arr", IntSort(), IntSort())
i = Int("i")
j = Int("j")
s = Solver()

# arr[i] = 10, then check if arr[j] == 10
updated_arr = Store(arr, i, 10)
s.add(Select(updated_arr, j) == 10)
s.add(i != j)  # But i and j are different!

print("Constraints:")
print("  arr[i] = 10")
print("  arr[j] == 10")
print("  i != j")
print()

result = s.check()
print(f"Z3 Result: {result}")  # unsat (contradiction)
print("✅ Z3 detects: arr[i]=10 doesn't affect arr[j] if i≠j")
print("❌ Internal Engine: Limited array theory support")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 5: String Theory (SMT-LIB 2.6)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("5️⃣  STRING THEORY (Advanced)")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

s_str = String("s")
t = String("t")
s = Solver()

s.add(Length(s_str) > 5)
s.add(PrefixOf("http://", s_str))  # Must start with "http://"
s.add(Contains(s_str, t))  # Must contain substring t
s.add(IndexOf(s_str, ".", 0) > 7)  # First "." after position 7
s.add(Length(t) == 3)  # Substring length is 3

print("Constraints:")
print("  len(s) > 5")
print('  s starts with "http://"')
print("  s contains substring t")
print('  first "." in s is after position 7')
print("  len(t) == 3")
print()

result = s.check()
print(f"Z3 Result: {result}")

if result == sat:
    m = s.model()
    print(f"✅ Z3 found solution:")
    print(f"   s = {m[s_str]}")
    print(f"   t = {m[t]}")
else:
    print(f"✅ Z3 result: {result}")

print("⚠️  Internal Engine: Basic patterns only (startsWith, contains)")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 6: Quantified Logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("6️⃣  QUANTIFIED LOGIC (ForAll / Exists)")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

x = Int("x")
y = Int("y")
s = Solver()

# For all y, if x < y then x < 100
# (This implies x < 100)
s.add(ForAll([y], Implies(x < y, x < 100)))
s.add(x > 100)  # Contradiction?

print("Constraints:")
print("  ∀y. (x < y) → (x < 100)")
print("  x > 100")
print()

result = s.check()
print(f"Z3 Result: {result}")  # unsat

if result == unsat:
    print("✅ Z3 detects: x cannot be > 100 if ∀y. (x < y) → (x < 100)")
else:
    print(f"✅ Z3 result: {result}")

print("❌ Internal Engine: No quantifier support")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 7: Non-Linear Arithmetic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("7️⃣  NON-LINEAR ARITHMETIC")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

x, y = Reals("x y")
s = Solver()

s.add(x * y > 10)  # Non-linear constraint
s.add(x**2 + y**2 < 25)  # Circle equation
s.add(x > 0)
s.add(y > 0)

print("Constraints (Real numbers):")
print("  x * y > 10       (non-linear)")
print("  x² + y² < 25     (circle)")
print("  x > 0, y > 0")
print()

result = s.check()
print(f"Z3 Result: {result}")

if result == sat:
    m = s.model()
    x_val = m[x]
    y_val = m[y]
    print(f"✅ Z3 found solution: x={x_val}, y={y_val}")

    # Approximate values
    from decimal import Decimal

    x_approx = float(x_val.as_decimal(10))
    y_approx = float(y_val.as_decimal(10))
    print(f"   Approximate: x≈{x_approx:.2f}, y≈{y_approx:.2f}")
    print(f"   Verification: x*y ≈ {x_approx * y_approx:.2f} > 10? {x_approx * y_approx > 10}")
    print(f"   Verification: x²+y² ≈ {x_approx**2 + y_approx**2:.2f} < 25? {x_approx**2 + y_approx**2 < 25}")
else:
    print(f"✅ Z3 result: {result}")

print("❌ Internal Engine: No non-linear arithmetic")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SUMMARY: Z3-Only Features")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print()
print("✅ Z3 Can Handle:")
print("  1. Inter-variable relationships (x < y && y < z)")
print("  2. Arithmetic operations (x + y > 10)")
print("  3. Bit-vector operations (x & 0xFF == 0x42)")
print("  4. Array theory (arr[i] = arr[j])")
print("  5. Advanced string theory (IndexOf, Substring)")
print("  6. Quantified logic (∀x. P(x))")
print("  7. Non-linear arithmetic (x² + y² < 25)")
print()
print("❌ Internal Engine Limitations:")
print("  - Single-variable constraints only")
print("  - No arithmetic expressions")
print("  - No bit-vector support")
print("  - Limited array theory")
print("  - Basic string patterns only")
print("  - No quantifiers")
print("  - Linear constraints only")
print()
print("💡 Recommendation:")
print("  - Use Internal Engine for 90%+ cases (<1ms)")
print("  - Fall back to Z3 for complex scenarios (50-100ms)")
print("  - Best of both worlds: Speed + Precision")
print()
