"""Validate and export a complete, versioned contract bundle for all services."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.depo_platform.openapi_contract import contract_errors


def collect(services, load):
    documents = {}
    failures = []
    for service in services:
        try:
            document = load(service)
            errors = contract_errors(document)
            if errors:
                failures.append({'service':service['id'],'errors':errors})
            else:
                documents[service['id']] = document
        except Exception as exc:
            failures.append({'service':service['id'],'error_type':type(exc).__name__})
    if failures:
        raise ValueError(json.dumps({'status':'failed','services':failures}))
    return documents


def export(output, services, documents):
    if set(documents) != {service['id'] for service in services}:
        raise ValueError('Contract bundle is incomplete')
    directory = Path(output) / ('bundle-' + uuid4().hex)
    directory.mkdir(parents=True)
    manifest = {'status':'complete','services':[]}
    try:
        manifest['git_commit'] = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        manifest['working_tree_dirty'] = bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    except (OSError,subprocess.CalledProcessError):
        manifest['git_commit'] = None
    for service in services:
        name = service['id'] + '.openapi.json'
        data = json.dumps(documents[service['id']],ensure_ascii=False,indent=2).encode()
        (directory / name).write_bytes(data)
        manifest['services'].append({'id':service['id'],'apim_path':service['apim_path'],
            'file':name,'sha256':hashlib.sha256(data).hexdigest(),'paths':len(documents[service['id']]['paths'])})
    # A bundle is consumable only when its completion manifest exists.
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'logs'/'openapi-release'))
    parser.add_argument('--live-template',help='Optional running service URL template, e.g. http://127.0.0.1:{port} or https://gateway/depo/{apim_path}')
    args = parser.parse_args()
    services = json.loads((ROOT/'infra/deployment/services.json').read_text())['services']
    def load(service):
        if args.live_template:
            import httpx
            from backend.depo_platform.network import gateway_subscription_headers
            endpoint = args.live_template.format(**service).rstrip('/') + '/openapi.json'
            with httpx.Client(timeout=15,trust_env=False) as client:
                with client.stream('GET',endpoint,headers=gateway_subscription_headers(endpoint)) as response:
                    response.raise_for_status()
                    content=bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content)>8*1024*1024: raise ValueError('Contract exceeds byte limit')
            return json.loads(content)
        module, name = service['module'].split(':',1)
        return getattr(importlib.import_module(module),name).openapi()
    try:
        directory = export(args.output,services,collect(services,load))
    except ValueError as exc:
        print(str(exc))
        return 1
    print(json.dumps({'status':'complete','services':len(services),'bundle':str(directory)}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
