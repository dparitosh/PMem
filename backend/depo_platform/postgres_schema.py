"""Shared PostgreSQL schema boundary for control-plane repositories."""
from __future__ import annotations

import os
import re


def configured_schema() -> str:
    schema = os.getenv("DEPO_DATABASE_SCHEMA", "semantic")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema):
        raise RuntimeError("DEPO_DATABASE_SCHEMA must be a valid PostgreSQL identifier")
    return schema


def connect_timeout_seconds() -> int:
    """Return a bounded timeout for remote PostgreSQL connection attempts."""
    raw = os.getenv("DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS", "10")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS must be an integer") from exc
    if not 1 <= value <= 60:
        raise RuntimeError("DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS must be between 1 and 60")
    return value


def select_schema(cursor) -> str:
    """Select the already-migrated application schema without runtime DDL."""
    schema = configured_schema()
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)", (schema,))
    row = cursor.fetchone()
    if not row or not bool(row[0]):
        raise RuntimeError(
            f"Configured PostgreSQL schema '{schema}' does not exist; run initialize-depo-schema.ps1 first"
        )
    cursor.execute(f'SET search_path TO "{schema}", public')
    return schema


def initialise_schema(cursor) -> str:
    """Select the DBA-provisioned schema without database-wide CREATE rights."""
    schema = configured_schema()
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)", (schema,))
    row = cursor.fetchone()
    if not row or not bool(row[0]):
        raise RuntimeError(
            f"Configured PostgreSQL schema '{schema}' does not exist. "
            "Create it as the database administrator and grant the DEPO role USAGE, CREATE before migration."
        )
    cursor.execute(f'SET search_path TO "{schema}", public')
    return schema


def statement_options(*, migration=False):
    key = 'DEPO_MIGRATION_STATEMENT_TIMEOUT_SECONDS' if migration else 'DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS'
    default, maximum = (300, 3600) if migration else (30, 300)
    try: seconds = int(os.getenv(key, str(default)))
    except ValueError as exc: raise RuntimeError(f'{key} must be an integer') from exc
    if not 1 <= seconds <= maximum: raise RuntimeError(f'{key} must be between 1 and {maximum}')
    return f'-c statement_timeout={seconds * 1000} -c lock_timeout={min(seconds, 10 if not migration else 60) * 1000}'
