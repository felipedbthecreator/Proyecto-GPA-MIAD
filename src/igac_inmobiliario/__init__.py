"""Reusable ingestion and cleaning helpers for the IGAC Socrata dataset."""

from .api import DATASET_ID, SocrataClient
from .cleaning import clean_transactions, profile_transactions
from .scope import TARGET_DEPARTMENTS, build_scope_where

__all__ = [
    "DATASET_ID",
    "SocrataClient",
    "TARGET_DEPARTMENTS",
    "build_scope_where",
    "clean_transactions",
    "profile_transactions",
]
