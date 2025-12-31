"""
Factory Classes for Dependency Injection

Provides factory classes that avoid circular references and support caching.
"""

from collections.abc import Callable
from typing import Generic, TypeVar
from weakref import ReferenceType, ref

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class WeakRefFactory(Generic[T]):
    """
    Factory that uses weak reference to avoid circular dependencies.

    Instead of:
        lambda: self.resource  # ❌ Strong reference to self

    Use:
        WeakRefFactory(container, lambda c: c.resource)  # ✅ Weak reference

    Example:
        container = Container()
        factory = WeakRefFactory(container, lambda c: c.graph_store)

        # Later...
        graph_store = factory()  # Calls container.graph_store

        # Container can be garbage collected when no strong references remain
        del container
        gc.collect()  # Container is freed!
    """

    def __init__(self, obj: object, accessor: Callable[[object], T]):
        """
        Initialize factory with weak reference.

        Args:
            obj: Object to weakly reference (e.g., Container)
            accessor: Function that accesses resource from object
        """
        self._ref: ReferenceType = ref(obj)
        self._accessor = accessor
        self._name = f"{type(obj).__name__}.{accessor.__name__ if hasattr(accessor, '__name__') else 'lambda'}"

    def __call__(self) -> T | None:
        """
        Call factory to get resource.

        Returns:
            Resource from accessor, or None if object was garbage collected
        """
        obj = self._ref()
        if obj is None:
            logger.warning(f"WeakRefFactory: Object was garbage collected ({self._name})")
            return None

        try:
            return self._accessor(obj)
        except Exception as e:
            logger.error(f"WeakRefFactory: Accessor failed ({self._name}): {e}", exc_info=True)
            return None

    def __repr__(self) -> str:
        obj = self._ref()
        status = "alive" if obj is not None else "dead"
        return f"WeakRefFactory({self._name}, {status})"


class CachedFactory(Generic[T]):
    """
    Factory that caches the result of first call.

    Prevents multiple calls to expensive factory functions.

    Example:
        expensive_factory = lambda: expensive_computation()
        cached = CachedFactory(expensive_factory)

        result1 = cached()  # Calls expensive_computation()
        result2 = cached()  # Returns cached result (no call)

        assert result1 is result2  # Same instance
    """

    def __init__(self, factory: Callable[[], T], name: str = "factory"):
        """
        Initialize cached factory.

        Args:
            factory: Underlying factory function
            name: Name for logging
        """
        self._factory = factory
        self._name = name
        self._cached: T | None = None
        self._called = False

    def __call__(self) -> T | None:
        """
        Call factory (or return cached result).

        Returns:
            Resource from factory (cached after first call)
        """
        if not self._called:
            try:
                logger.debug(f"CachedFactory: First call to {self._name}")
                self._cached = self._factory()
                self._called = True
            except Exception as e:
                logger.error(f"CachedFactory: Factory failed ({self._name}): {e}", exc_info=True)
                self._called = True  # Mark as called to avoid retry
                self._cached = None
        else:
            logger.debug(f"CachedFactory: Returning cached result for {self._name}")

        return self._cached

    def clear_cache(self) -> None:
        """Clear cached value."""
        self._cached = None
        self._called = False
        logger.debug(f"CachedFactory: Cache cleared for {self._name}")

    def is_cached(self) -> bool:
        """Check if value is cached."""
        return self._called

    def __repr__(self) -> str:
        status = "cached" if self._called else "uncached"
        return f"CachedFactory({self._name}, {status})"


class WeakCachedFactory(Generic[T]):
    """
    Factory that combines weak reference and caching.

    Best of both worlds:
    - Avoids circular references (weak reference)
    - Prevents multiple calls (caching)

    Example:
        container = Container()
        factory = WeakCachedFactory(
            container,
            lambda c: c.expensive_resource,
            name="expensive_resource"
        )

        # First call
        res1 = factory()  # Computes

        # Second call
        res2 = factory()  # Returns cached (same instance)

        # Container can be freed when no strong references
        del container
        gc.collect()
    """

    def __init__(
        self,
        obj: object,
        accessor: Callable[[object], T],
        name: str = "resource",
    ):
        """
        Initialize weak cached factory.

        Args:
            obj: Object to weakly reference
            accessor: Function to access resource from object
            name: Name for logging
        """
        self._weak_factory = WeakRefFactory(obj, accessor)
        self._cached_factory = CachedFactory(self._weak_factory, name=name)
        self._name = name

    def __call__(self) -> T | None:
        """Call factory (weak reference + cached)."""
        return self._cached_factory()

    def clear_cache(self) -> None:
        """Clear cached value."""
        self._cached_factory.clear_cache()

    def is_cached(self) -> bool:
        """Check if value is cached."""
        return self._cached_factory.is_cached()

    def __repr__(self) -> str:
        return f"WeakCachedFactory({self._name}, {self._weak_factory}, {self._cached_factory})"


# ============================================================
# Convenience Functions
# ============================================================


def weak_factory(obj: object, accessor: Callable[[object], T]) -> Callable[[], T | None]:
    """
    Create a weak reference factory function.

    Args:
        obj: Object to weakly reference
        accessor: Function to access resource

    Returns:
        Callable factory function
    """
    factory = WeakRefFactory(obj, accessor)
    return factory


def cached_factory(factory: Callable[[], T], name: str = "factory") -> Callable[[], T | None]:
    """
    Create a cached factory function.

    Args:
        factory: Underlying factory
        name: Name for logging

    Returns:
        Callable cached factory function
    """
    cached = CachedFactory(factory, name=name)
    return cached


def weak_cached_factory(
    obj: object,
    accessor: Callable[[object], T],
    name: str = "resource",
) -> Callable[[], T | None]:
    """
    Create a weak + cached factory function.

    Args:
        obj: Object to weakly reference
        accessor: Function to access resource
        name: Name for logging

    Returns:
        Callable factory function (weak + cached)
    """
    factory = WeakCachedFactory(obj, accessor, name=name)
    return factory
