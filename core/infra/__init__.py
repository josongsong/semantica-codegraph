"""
Infrastructure Layer (Adapters)

This package contains concrete implementations of the port interfaces.
Each adapter translates between the core domain and external systems.

Following Hexagonal Architecture:
- Adapters implement port interfaces from core
- Adapters depend on core (not vice versa)
- Adapters handle all external I/O and serialization
"""
