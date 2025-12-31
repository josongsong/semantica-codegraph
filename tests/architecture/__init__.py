"""Architecture Tests - RFC-021 Phase 0

Tests to enforce architectural constraints:
1. No cyclic dependencies between contexts
2. shared_kernel only depends on stdlib
3. Dependency graph is acyclic
"""
