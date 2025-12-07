"""Injection Queries"""

from .sql_injection import DjangoSQLInjectionQuery, SQLInjectionQuery

__all__ = ["SQLInjectionQuery", "DjangoSQLInjectionQuery"]
