"""Compatibility wrapper for Neo4j cleanup.

This file used to contain hardcoded local Neo4j credentials and deleted all
nodes immediately. Keep it importable for old commands, but delegate the actual
work to the guarded admin tool.
"""

from __future__ import annotations

from tools.admin.cleanup_neo4j import main


if __name__ == "__main__":
    raise SystemExit(main())
