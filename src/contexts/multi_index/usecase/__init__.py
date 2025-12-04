"""Multi Index UseCases"""

from .delete_from_indexes import DeleteFromIndexesUseCase
from .upsert_to_index import UpsertToIndexUseCase

__all__ = [
    "DeleteFromIndexesUseCase",
    "UpsertToIndexUseCase",
]
