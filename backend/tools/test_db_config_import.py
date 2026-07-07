from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

import backend.core.db_config as db_config

print('imported', db_config.__file__)