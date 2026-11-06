import requests

url = 'http://127.0.0.1:8000/api/v1/import/upload'
files = {'file': ('test.txt', b'hello', 'text/plain')}
data = {'ontology_mapping': ''}
try:
    r = requests.post(url, files=files, data=data, timeout=15)
    print('STATUS', r.status_code)
    print(r.text)
except Exception as e:
    print('ERR', e)
