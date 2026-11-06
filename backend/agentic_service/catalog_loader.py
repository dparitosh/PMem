"""One validated source for agent discovery and execution."""
import json
import os
from pathlib import Path
from .catalog_contract import validate_catalog
from .dt_bindings import extend_catalog


def load_catalog(path=None):
    selected = Path(path or os.getenv('AGENTIC_CATALOG_PATH') or Path(__file__).with_name('catalog.json'))
    data = validate_catalog(json.loads(selected.read_text(encoding='utf-8')))
    return validate_catalog(extend_catalog(data))
