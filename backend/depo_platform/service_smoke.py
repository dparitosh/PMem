"""Import one deployment-owned service/worker in its own dependency runtime."""
import argparse
import importlib
import json
from pathlib import Path


def check(service_id):
    manifest = json.loads((Path(__file__).resolve().parents[2] / 'infra/deployment/services.json').read_text())
    entries = manifest['services'] + manifest['workers']
    item = next((entry for entry in entries if entry['id'] == service_id), None)
    if item is None:
        raise ValueError('Unknown deployment service')
    module, separator, attribute = item['module'].partition(':')
    imported = importlib.import_module(module)
    if separator:
        contract = getattr(imported, attribute).openapi()
        if not contract.get('paths'):
            raise RuntimeError('Service generated an empty OpenAPI contract')
        from .openapi_contract import contract_errors
        errors = contract_errors(contract)
        if errors:
            raise RuntimeError('Service OpenAPI validation failed: ' + '; '.join(errors))
        return {'status': 'ok', 'service': service_id, 'paths': len(contract['paths'])}
    return {'status': 'ok', 'service': service_id, 'check': 'worker import'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.service)))
