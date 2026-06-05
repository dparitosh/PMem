import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('backend/.env')
import os
from backend.core.db_config import get_config, Neo4jConnection

cfg = get_config()

with Neo4jConnection(database=cfg.database) as s:
    total = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
    print(f'Total nodes: {total}')

    labels = s.run('MATCH (n) RETURN labels(n)[0] AS lbl, count(*) AS c ORDER BY c DESC LIMIT 10').data()
    for row in labels:
        print(f'  {row["lbl"]}: {row["c"]}')

    print('Sample nodes:')
    for i, r in enumerate(s.run('MATCH (n) RETURN n LIMIT 3').data()):
        props = dict(r['n'])
        items = list(props.items())[:4]
        print(f'  [{i+1}] {items}')

# Neo4jConnection context manager closes the session
