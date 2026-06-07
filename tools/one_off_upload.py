import requests
import sys

path = 'Depo_onto/data/business_object_models/managed_model_based_3d_engineering/bom.xsd'
if len(sys.argv) > 1:
    path = sys.argv[1]

url = 'http://127.0.0.1:8000/api/v1/import/upload'
files = {'file': open(path, 'rb')}
data = {'ontology_mapping': 'AP242'}
try:
    r = requests.post(url, files=files, data=data, timeout=300)
    print('STATUS', r.status_code)
    print(r.text)
except Exception as e:
    print('ERR', e)
finally:
    files['file'].close()
