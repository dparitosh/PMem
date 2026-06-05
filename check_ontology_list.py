import requests, json
r = requests.get('http://localhost:8000/api/v1/ontology/registered', timeout=10)
data = r.json()
print('Total returned:', data.get('count'))
for o in data.get('ontologies', []):
    latest = o.get('is_latest', '(unset)')
    ver = o.get('version', 1)
    name = repr(o.get('ontology_name', ''))
    oid = o.get('ontology_id', '')
    has_prev = 'previous_versions' in o
    print(f'  {oid:35} name={name:22} is_latest={latest} version={ver} has_prev_versions={has_prev}')
