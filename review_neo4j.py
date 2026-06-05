import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('backend/.env')
import os
from backend.core.db_config import get_config, Neo4jConnection
from collections import Counter

cfg = get_config()

with Neo4jConnection(database=cfg.database) as s:
    print('=== NODE COUNTS BY LABEL ===')
    for r in s.run('MATCH (n) RETURN labels(n) AS lbls, count(*) AS c ORDER BY c DESC').data():
        print(f'  {r["lbls"]}: {r["c"]}')

    print('\n=== UNIQUE type VALUES (first 20) ===')
    for r in s.run('MATCH (n) WHERE n.type IS NOT NULL RETURN n.type AS t, count(*) AS c ORDER BY c DESC LIMIT 20').data():
        print(f'  {r["t"]}: {r["c"]}')

    print('\n=== RELATIONSHIP COUNTS ===')
    rel_count = s.run('MATCH ()-[r]->() RETURN count(r) AS c').single()['c']
    print(f'  Total relationships: {rel_count}')

    print('\n=== NODES WITH ownerId SET ===')
    owner_count = s.run('MATCH (n) WHERE n.ownerId IS NOT NULL AND n.ownerId <> "" RETURN count(n) AS c').single()['c']
    print(f'  Nodes with ownerId: {owner_count}')

    print('\n=== SAMPLE ownerId VALUES ===')
    for r in s.run('MATCH (n) WHERE n.ownerId IS NOT NULL AND n.ownerId <> "" RETURN n.id AS id, n.ownerId AS owner, n.type AS t LIMIT 5').data():
        print(f'  {r}')

    print('\n=== PROPERTY KEYS ===')
    for r in s.run('MATCH (n) UNWIND keys(n) AS k RETURN k, count(*) AS c ORDER BY c DESC LIMIT 10').data():
        print(f'  {r["k"]}: {r["c"]}')

# Neo4jConnection context manager closes the session
