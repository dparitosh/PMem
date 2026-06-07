import requests, json, time, os


def main():
    # Find Domain_model.xmi
    xmi_path = None
    for root, dirs, files in os.walk('.'):
        for f in files:
            if f == 'Domain_model.xmi':
                xmi_path = os.path.join(root, f)
                break
        if xmi_path:
            break

    if not xmi_path:
        print('Domain_model.xmi not found - using test_upload.xsd')
        xmi_path = 'test_upload.xsd'

    print(f'File: {xmi_path}  ({os.path.getsize(xmi_path):,} bytes)')

    # 1. Upload - should return in <3s now
    t0 = time.time()
    with open(xmi_path, 'rb') as fh:
        fname = os.path.basename(xmi_path)
        r = requests.post(
            'http://localhost:8000/api/v1/import/upload',
            files={'file': (fname, fh, 'application/octet-stream')},
            data={'ontology_mapping': 'auto'},
            timeout=120
        )
    upload_time = time.time() - t0
    print(f'Upload: HTTP {r.status_code}  in {upload_time:.2f}s')

    if not r.ok:
        print('FAIL:', r.text[:400])
        return 1

    task_id = r.json()['task_id']
    print(f'Task ID: {task_id}')

    if upload_time > 10:
        print('WARNING: upload still blocking (expected <3s)')
    else:
        print('OK: upload returned quickly (non-blocking parse confirmed)')

    # 2. Poll until preview or fail (max 3 min)
    print('\nPolling status...')
    last_stage = None
    s = {}
    for i in range(90):
        time.sleep(2)
        try:
            s = requests.get(
                f'http://localhost:8000/api/v1/import/{task_id}/status',
                timeout=5
            ).json()
        except Exception as e:
            print(f'  [{i*2}s] Poll error: {e}')
            continue

        stage = s.get('current_stage', '?')
        progress = s.get('progress', 0)
        status = s.get('status', '?')
        err = s.get('error') or ''

        if stage != last_stage:
            print(f'  [{i*2}s] {stage} {progress}%  [{status}]  {err[:80]}')
            last_stage = stage

        if stage == 'preview' or status in ('completed', 'failed'):
            break

    print('\nFinal status:')
    print(json.dumps({k: s.get(k) for k in ['current_stage','progress','status','error','stats']}, indent=2, default=str))

    if s.get('current_stage') == 'preview':
        print('\nPipeline reached PREVIEW (75%) - ready for commit.')
        print('Attempting commit...')
        cr = requests.post(
            f'http://localhost:8000/api/v1/import/{task_id}/commit',
            headers={'Content-Type': 'application/json'},
            timeout=120
        )
        print(f'Commit: HTTP {cr.status_code}')
        try:
            print(json.dumps(cr.json(), indent=2, default=str))
        except Exception:
            print(cr.text[:400])


if __name__ == '__main__':
    raise SystemExit(main())
