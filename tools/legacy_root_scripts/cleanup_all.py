"""
Cleanup script:
  1. Wipe all Neo4j nodes / relationships / indexes
  2. Remove all XSD ontology upload folders
  3. Remove all superseded / orphan XMI folders
  4. Keep only ap239_1779774056 (AP239PLCS v5, is_latest=True)
"""
import sys, json, shutil
from pathlib import Path

sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('backend/.env')
import os
from backend.core.db_config import get_config, Neo4jConnection

UPLOAD_DIR = Path('ontology_uploads')

# ── 1. Neo4j full wipe ──────────────────────────────────────────────────────
print('=== 1. Cleaning Neo4j ===')
cfg = get_config()
with Neo4jConnection(database=cfg.database) as s:
    before = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
    print(f'  Nodes before: {before}')
    batch = 1
    while True:
        result = s.run('MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c').single()['c']
        print(f'  Deleted batch {batch}: {result} nodes')
        batch += 1
        if result == 0:
            break

    # Drop all indexes and constraints
    for row in s.run('SHOW INDEXES').data():
        name = row.get('name')
        if name and name not in ('__org_neo4j_schema_index_label_scan_store_converted_to_token_index',):
            try:
                s.run(f'DROP INDEX `{name}` IF EXISTS')
                print(f'  Dropped index: {name}')
            except Exception:
                pass
    for row in s.run('SHOW CONSTRAINTS').data():
        name = row.get('name')
        if name:
            try:
                s.run(f'DROP CONSTRAINT `{name}` IF EXISTS')
                print(f'  Dropped constraint: {name}')
            except Exception:
                pass

    after = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
    print(f'  Nodes after : {after}')

# Neo4jConnection context manager closes the session

# ── 2. Identify folders to remove ──────────────────────────────────────────
print('\n=== 2. Scanning ontology_uploads/ ===')
KEEP = {'ap239_1779774056'}   # only the latest AP239PLCS XMI (v5)

to_delete = []
to_keep   = []
for d in sorted(UPLOAD_DIR.iterdir()):
    if not d.is_dir():
        continue
    meta_path = d / 'metadata.json'
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf-8-sig'))
        ftype   = meta.get('file_type', '?')
        name    = meta.get('ontology_name', d.name)
        latest  = meta.get('is_latest', None)
        version = meta.get('version', 1)
    else:
        ftype, name, latest, version = '?', d.name, None, 1

    if d.name in KEEP:
        to_keep.append((d.name, ftype, name))
    else:
        to_delete.append((d, ftype, name, latest, version))

print(f'  Keep  ({len(to_keep)}):')
for n, ft, nm in to_keep:
    print(f'    KEEP  {n}  [{ft}]  "{nm}"')
print(f'  Delete ({len(to_delete)}):')
for d, ft, nm, latest, ver in to_delete:
    print(f'    DEL   {d.name}  [{ft}]  "{nm}"  is_latest={latest} v{ver}')

# ── 3. Perform deletion ─────────────────────────────────────────────────────
print('\n=== 3. Deleting ===')
deleted = 0
for d, ft, nm, *_ in to_delete:
    try:
        shutil.rmtree(d)
        print(f'  Removed {d.name}  [{ft}]  "{nm}"')
        deleted += 1
    except Exception as e:
        print(f'  ERROR removing {d.name}: {e}')

print(f'\nDone. Removed {deleted} folder(s). Kept {len(to_keep)}.')
print('Remaining:')
for d in sorted(UPLOAD_DIR.iterdir()):
    print(f'  {d.name}')
