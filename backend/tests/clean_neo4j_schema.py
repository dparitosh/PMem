"""Compatibility wrapper for Neo4j cleanup.

This file used to contain hardcoded local Neo4j credentials and deleted all
nodes immediately. Keep it importable for old commands, but delegate the actual
work to the guarded admin tool.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from tools.admin.cleanup_neo4j import main


if __name__ == "__main__":
    raise SystemExit(main())
