import json, os, sys
p = os.path.join(os.path.dirname(__file__), '..', 'uploads', '.import_tasks', sys.argv[1])
try:
    stat = os.stat(p)
    print('path:', p)
    print('size:', stat.st_size)
    print('mtime:', stat.st_mtime)
    with open(p, 'r', encoding='utf-8') as f:
        txt = f.read()
    print('preview of file (first 1000 chars):')
    print(txt[:1000])
    data = json.loads(txt)
    print('keys:', list(data.keys()))
    print('parsed_rows present?:', 'parsed_rows' in data)
    if 'parsed_rows' in data:
        v = data['parsed_rows']
        print('parsed_rows type:', type(v), 'len:' , (len(v) if hasattr(v,'__len__') else 'N/A'))
except Exception as e:
    print('error reading', p, e)
