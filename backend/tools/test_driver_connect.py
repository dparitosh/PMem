from backend.core.db_config import get_config, get_driver, Neo4jConnection
import traceback

cfg = get_config()
print('Testing connection to', cfg.uri)
try:
    driver = get_driver()
    with Neo4jConnection(database=cfg.database) as s:
        r = s.run('RETURN 1 AS ok')
        print('Result:', r.single())
    print('Connection test succeeded')
except Exception:
    print('Connection test failed:')
    traceback.print_exc()