import requests, json, os
from dotenv import load_dotenv
from backend.core.db_config import get_config, Neo4jConnection

load_dotenv('backend/.env')
base = 'http://localhost:8000'

# ── Backend health ────────────────────────────────────────────────────────────
print('=== BACKEND HEALTH ===')
try:
    h = requests.get(f'{base}/health', timeout=5)
    print(f'  HTTP {h.status_code}  {h.json().get("status","?")}')
except Exception as e:
    print(f'  ERROR: {e}')

# ── Neo4j ─────────────────────────────────────────────────────────────────────
print('\n=== NEO4J ===')
try:
    cfg = get_config()
    with Neo4jConnection(database=cfg.database) as s:
        nodes = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
        rels  = s.run('MATCH ()-[r]->() RETURN count(r) AS c').single()['c']
        idxs  = s.run('SHOW INDEXES').data()
        labels = s.run('CALL db.labels() YIELD label RETURN collect(label) AS l').single()['l']
    print(f'  Nodes         : {nodes}')
    print(f'  Relationships : {rels}')
    print(f'  Indexes       : {len(idxs)}')
    print(f'  Labels        : {labels or ["(none)"]}')
except Exception as e:
    print(f'  ERROR: {e}')

# ── Ontology uploads ──────────────────────────────────────────────────────────
print('\n=== ONTOLOGY UPLOADS ===')
try:
    r = requests.get(f'{base}/api/v1/ontology/registered', timeout=5)
    d = r.json()
    count = d.get('count', 0)
    print(f'  Registered: {count}')
    for o in d.get('ontologies', []):
        latest = o.get('is_latest', '(unset)')
        print(f'  - [{o["file_type"]:4}] {o["ontology_id"]:30} "{o["ontology_name"]}"  is_latest={latest}')
    if count == 0:
        print('  (empty — ready for fresh import)')
except Exception as e:
    print(f'  ERROR: {e}')

# ── Key API routes ────────────────────────────────────────────────────────────
print('\n=== KEY ROUTES ===')
routes = [
    ('GET',  '/api/v1/ontology/registered'),
    ('GET',  '/api/v1/import/pre-commit/test-id'),
    ('POST', '/api/v1/ontology/merge'),
    ('GET',  '/api/v1/ontology/ap239/data-dictionary'),
]
for method, path in routes:
    try:
        fn = requests.post if method == 'POST' else requests.get
        rx = fn(f'{base}{path}', json={}, timeout=5)
        print(f'  {method:4} {path}: HTTP {rx.status_code}')
    except Exception as e:
        print(f'  {method:4} {path}: ERROR {e}')

# ── Frontend build ────────────────────────────────────────────────────────────
print('\n=== FRONTEND ===')
try:
    fx = requests.get('http://localhost:3000', timeout=5)
    print(f'  Dev server: HTTP {fx.status_code}')
except Exception as e:
    print(f'  Dev server: {e}')

from pathlib import Path
build = Path('frontend/build/static/js')
if build.exists():
    bundles = sorted(build.glob('*.js'), key=lambda f: f.stat().st_mtime, reverse=True)
    if bundles:
        import datetime
        mtime = datetime.datetime.fromtimestamp(bundles[0].stat().st_mtime)
        print(f'  Build bundle: {bundles[0].name}  (built {mtime.strftime("%H:%M:%S")})')
else:
    print('  No build found')

print('\n=== SUMMARY ===')
print('  Neo4j    : CLEAN' if nodes == 0 else f'  Neo4j    : {nodes} nodes, {rels} rels')
print(f'  Uploads  : {"CLEAN (0 ontologies)" if count == 0 else str(count) + " ontologies registered"}')
