from importlib import import_module
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

m = import_module('backend.Services.tests.test_shacl_integration')
print('module loaded:', m)
try:
    m.test_shacl_integration()
except AssertionError as e:
    print('Assertion failed:', e)
except Exception as e:
    import traceback
    traceback.print_exc()
