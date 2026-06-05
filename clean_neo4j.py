import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('backend/.env')
import os
from backend.core.db_config import get_config, Neo4jConnection

cfg = get_config()

with Neo4jConnection(database=cfg.database) as s:
    before = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
    print(f'Before: {before} nodes')

    # Delete all nodes+rels in batches (avoids heap overflow on large graphs)
    while True:
        deleted = s.run(
            'MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(*) AS d'
        ).single()['d']
        print(f'  Deleted batch: {deleted}')
        if deleted == 0:
            break

    # Drop all user-created indexes
    for row in s.run('SHOW INDEXES YIELD name, type WHERE type <> "LOOKUP"').data():
        name = row['name']
        try:
            s.run(f'DROP INDEX `{name}`')
            print(f'  Dropped index: {name}')
        except Exception as e:
            print(f'  Index {name} skip: {e}')

    # Drop all constraints
    for row in s.run('SHOW CONSTRAINTS YIELD name').data():
        name = row['name']
        try:
            s.run(f'DROP CONSTRAINT `{name}`')
            print(f'  Dropped constraint: {name}')
        except Exception as e:
            print(f'  Constraint {name} skip: {e}')

    after = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
    print(f'After:  {after} nodes — schema clean')

# Neo4jConnection context manager closes the session
