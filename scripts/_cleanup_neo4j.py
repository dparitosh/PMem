"""
Legacy safety wrapper.

This script used to contain hardcoded Neo4j credentials and a fixed database
name. Destructive cleanup must use the centralized .env-driven cleanup tool
so the UI, API, and scripts all target the same configured database.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.admin.cleanup_neo4j import main


if __name__ == "__main__":
    raise SystemExit(main())
