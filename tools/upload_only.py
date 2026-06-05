import requests
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / 'data' / 'business_object_models' / 'managed_model_based_3d_engineering' / 'bom.xsd'
BASE = 'http://127.0.0.1:8000'

def main():
    p = DEFAULT
    if not p.exists():
        print('File missing:', p)
        return 2
    url = f"{BASE}/api/v1/import/upload"
    with open(p, 'rb') as fh:
        files = {'file': (p.name, fh, 'application/xml')}
        data = {'ontology_mapping': 'AP242'}
        r = requests.post(url, files=files, data=data, timeout=120)
    print('STATUS', r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
