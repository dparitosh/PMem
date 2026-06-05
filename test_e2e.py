import requests, json, time, os, sys


def main():
    XMI = r'.\data\domain_models\product_life_cycle_support\Domain_model_4439_XMI\STEPlib\Application_protocols\AP239\Domain_model\Domain_model.xmi'
    BASE = 'http://localhost:8000'

    if not os.path.exists(XMI):
        print('XMI file not found; skipping interactive upload script.')
        return

    print(f'Uploading {os.path.getsize(XMI):,} bytes...')
    t0 = time.time()
    with open(XMI, 'rb') as fh:
        r = requests.post(f'{BASE}/api/v1/import/upload',
            files={'file': ('Domain_model.xmi', fh, 'application/octet-stream')},
            data={'ontology_mapping': 'auto'}, timeout=120)
    elapsed = time.time() - t0
    print(f'Upload: HTTP {r.status_code} in {elapsed:.2f}s')
    if not r.ok:
        print(r.text[:400])
        sys.exit(1)

    task_id = r.json()['task_id']
    print(f'Task ID: {task_id}')

    print('Polling status (up to 4 min)...')
    last_stage = None
    for i in range(120):
        time.sleep(2)
        try:
            s = requests.get(f'{BASE}/api/v1/import/status/{task_id}', timeout=5).json()
        except Exception as e:
            print(f'  [{i*2}s] poll error: {e}')
            continue
        stage = s.get('current_stage')
        prog = s.get('progress')
        status = s.get('status')
        err = (s.get('error') or '')[:60]
        if stage != last_stage:
            print(f'  [{i*2}s] stage={stage} progress={prog}% status={status} error={err}')
            last_stage = stage
        if stage == 'preview' or status in ('completed', 'failed'):
            break

    print(f'Final: stage={stage} progress={prog}% status={status}')
    if stage != 'preview':
        print('ERROR:', s.get('error'))
        sys.exit(1)

    print('Committing to Neo4j...')
    cr = requests.post(f'{BASE}/api/v1/import/commit/{task_id}',
        headers={'Content-Type': 'application/json'}, timeout=300)
    print(f'Commit: HTTP {cr.status_code}')
    try:
        print(json.dumps(cr.json(), indent=2, default=str))
    except Exception:
        print(cr.text[:600])


if __name__ == '__main__':
    main()
