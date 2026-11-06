"""Durable package storage shares the operator-configured artifact volume."""
import os
from pathlib import Path


def product_storage_root():
    explicit = os.getenv('DATA_PRODUCT_STORAGE', '').strip()
    if explicit:
        return Path(explicit)
    artifacts = os.getenv('ARTIFACT_STORAGE', '').strip()
    if artifacts:
        return Path(artifacts) / 'products'
    return Path(__file__).resolve().parents[2] / 'data' / 'products'
