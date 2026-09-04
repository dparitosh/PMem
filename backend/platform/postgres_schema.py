"""Shared PostgreSQL schema boundary for control-plane repositories."""
from __future__ import annotations

import os
import re


def configured_schema() -> str:
    schema = os.getenv("DEPO_DATABASE_SCHEMA", "semantic")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema):
        raise RuntimeError("DEPO_DATABASE_SCHEMA must be a valid PostgreSQL identifier")
    return schema


def initialise_schema(cursor) -> str:
    """Create and select the configured tenant/control-plane schema safely."""
    schema = configured_schema()
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    cursor.execute(f'SET search_path TO "{schema}", public')
    return schema
