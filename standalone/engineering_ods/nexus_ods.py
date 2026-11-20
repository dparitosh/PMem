"""Standalone Engineering ODS generator and governed API loader. No DB access."""
import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import time
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef
from pyshacl import validate

ROOT = Path(__file__).resolve().parent
CEIM = Namespace('https://depo.example.org/ceim/0.1/')
ENG = Namespace('https://example.org/nexus/engineering-ods/vocabulary/v1/')
UUID_NAMESPACE = uuid.UUID('c09e822e-af15-5a64-8bda-39a23cc9cc29')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def endpoint(value):
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Service URL must be an HTTP(S) base URL without credentials, query or fragment')
    if parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use HTTPS for non-loopback services')
    return value.rstrip('/')


def configuration(path):
    path = Path(path).resolve()
    config = read_json(path)
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,60}', config['prefix']):
        raise ValueError('Prefix must contain lowercase letters, numbers or underscores and start with a letter')
    config['ontology_api'] = endpoint(config['ontology_api'])
    config['oslc_api'] = endpoint(config['oslc_api'])
    config['output'] = (path.parent / config['output']).resolve()
    if config.get('ca_bundle'):
        config['ca_bundle'] = str((path.parent / config['ca_bundle']).resolve())
    config['scenario'] = (path.parent / config.get('scenario', 'scenario.json')).resolve()
    base = config['namespace']
    parts = urlsplit(base)
    if parts.scheme not in ('http', 'https') or not parts.netloc or not base.endswith('/') or parts.query or parts.fragment:
        raise ValueError('Namespace must be an absolute HTTP(S) IRI ending in /')
    return config


def generate(config, cases=1):
    if not 1 <= cases <= 100:
        raise ValueError('Cases must be between 1 and 100')
    out = config['output']
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'load-state.json').exists():
        raise ValueError('This output has registration state. Use a new output folder/version instead of overwriting a loaded artifact')
    scenario = read_json(config['scenario'])
    if scenario.get('schema_version') != 1:
        raise ValueError('Unsupported scenario schema')
    history_date = date.fromisoformat(scenario['history_date'])
    assessment_date = date.fromisoformat(scenario['assessment_date'])
    if history_date >= assessment_date:
        raise ValueError('Historical date must precede the current assessment date')
    records = scenario['records']
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)) or not ids or any(not isinstance(k, str) or not k for k in ids):
        raise ValueError('Business IDs must be nonempty and unique')
    schema = Graph().parse(ROOT / 'assets/schema.ttl', format='turtle')
    g = Graph()
    for triple in schema:
        g.add(triple)
    g.bind('ceim', CEIM)
    g.bind('eng', ENG)
    entities, relationships = [], []
    for n in range(cases):
        case = f"{config['case_key']}-{n + 1:03d}"
        nodes = {key: URIRef(config['namespace'] + str(uuid.uuid5(UUID_NAMESPACE, case + ':' + key))) for key in ids}
        for record in records:
            subject = nodes[record['id']]
            if record['record_kind'] not in ('historical', 'current'):
                raise ValueError('record_kind must be historical or current')
            for cls in record['classes']:
                cls = URIRef(cls)
                if (cls, RDF.type, OWL.Class) not in schema:
                    raise ValueError(f'Undeclared business class: {cls}')
                g.add((subject, RDF.type, cls))
            g.add((subject, RDF.type, OWL.NamedIndividual))
            g.add((subject, CEIM.externalId, Literal(case + ':' + record['id'], datatype=XSD.string)))
            g.add((subject, RDFS.label, Literal(record['label'] + (f' [{case}]' if cases > 1 else ''), datatype=XSD.string)))
            for prop, item in record['properties'].items():
                if prop in (str(CEIM.externalId), str(RDF.type), str(RDFS.label)):
                    raise ValueError('Identity, labels and types must use their dedicated fields')
                datatype = URIRef(item['datatype']) if item.get('datatype') else None
                value = Literal(item['value'], datatype=datatype, lang=item.get('language') or None)
                if value.ill_typed:
                    raise ValueError(f"Invalid typed value for {record['id']}: {prop}")
                g.add((subject, URIRef(prop), value))
            # Scenario provenance cannot be removed by editing input values.
            g.set((subject, ENG.dataOrigin, Literal('Engineering ODS scenario', datatype=XSD.string)))
            g.set((subject, ENG.engineeringApproved, Literal(False)))
            historical = record['record_kind'] == 'historical'
            g.add((subject, ENG.recordKind, Literal(record['record_kind'], datatype=XSD.string)))
            g.add((subject, ENG.recordedAt, Literal(history_date if historical else assessment_date, datatype=XSD.date)))
            entities.append({'case': case, 'business_id': record['id'], 'golden_id': str(subject), 'label': record['label'], 'kind': record['record_kind']})
        for link in scenario['links']:
            if link['from'] not in nodes or link['to'] not in nodes or link['from'] == link['to']:
                raise ValueError('Relationship endpoint is missing or self-referential')
            predicate = URIRef(link['predicate'])
            g.add((nodes[link['from']], predicate, nodes[link['to']]))
            relationships.append({'from': str(nodes[link['from']]), 'predicate': str(predicate), 'to': str(nodes[link['to']])})
    for predicate in (ENG.recordKind, ENG.recordedAt):
        g.add((predicate, RDF.type, OWL.DatatypeProperty))
    ontology = URIRef(config['namespace'] + 'ontology')
    g.add((ontology, RDF.type, OWL.Ontology))
    g.add((ontology, RDFS.label, Literal(config['name'])))
    g.add((ontology, RDFS.comment, Literal('Authored Engineering ODS scenario; historical decisions are not customer incidents or engineering approvals.')))
    conforms, _, report = validate(g, shacl_graph=Graph().parse(ROOT / 'assets/shapes.ttl'), inference='none')
    if not conforms:
        raise ValueError('SHACL validation failed: ' + report)
    (out / 'engineering-ods.ttl').write_bytes((g.serialize(format='turtle').rstrip() + '\n').encode('utf-8'))
    save(out / 'identities.json', entities)
    save(out / 'relationships.json', relationships)
    manifest = {'schema_version': 1, 'name': config['name'], 'prefix': config['prefix'], 'version': config['version'],
                'artifact_sha256': digest(out / 'engineering-ods.ttl'), 'scenario_sha256': digest(config['scenario']),
                'schema_sha256': digest(ROOT / 'assets/schema.ttl'), 'shapes_sha256': digest(ROOT / 'assets/shapes.ttl'),
                'triples': len(g), 'cases': cases, 'records': len(entities),
                'historical_records': sum(e['kind'] == 'historical' for e in entities), 'relationships': len(relationships),
                'shacl_conforms': True, 'customer_approved': False, 'database_written': False}
    save(out / 'manifest.json', manifest)
    return manifest


class Loader:
    def __init__(self, config, transport=None):
        self.config = config
        self.out = config['output']
        self.state_path = self.out / 'load-state.json'
        trust = ssl.create_default_context(cafile=config['ca_bundle']) if config.get('ca_bundle') else True
        self.client = httpx.Client(timeout=180, follow_redirects=False, trust_env=False, transport=transport, verify=trust)

    def close(self):
        self.client.close()

    def call(self, method, url, write=False, **kwargs):
        env_name = self.config.get('write_token_env', 'ONTOLOGY_APPROVAL_TOKEN') if write else self.config.get('read_token_env', 'GRAPH_READ_TOKEN')
        token = os.environ.get(env_name, '').strip()
        if not token:
            raise ValueError(f'Set {env_name} in the operator process environment; never put it in the config JSON')
        headers = {'Authorization': 'Bearer ' + token}
        if self.config.get('subscription_key_env'):
            subscription = os.environ.get(self.config['subscription_key_env'], '').strip()
            if not subscription:
                raise ValueError('Configured API gateway subscription key is missing from the operator environment')
            headers['Ocp-Apim-Subscription-Key'] = subscription
        response = self.client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 300:
            raise ValueError(f'API request failed: HTTP {response.status_code}; request ID {response.headers.get("x-request-id", "not supplied")}. Check permissions, approval matrix and server logs. No automatic write retry was made.')
        return response.json()

    def state(self):
        state = read_json(self.state_path)
        if state['ontology_api'] != self.config['ontology_api'] or state['oslc_api'] != self.config['oslc_api']:
            raise ValueError('Registration state belongs to another environment; use a separate output folder')
        if state['artifact_sha256'] != digest(self.out / 'engineering-ods.ttl'):
            raise ValueError('Artifact changed after registration. Generate a new version in a new output folder')
        return state

    def artifact_url(self, suffix=''):
        oid = quote(self.state()['ontology_id'], safe='')
        return self.config['ontology_api'] + '/' + oid + suffix

    def register(self):
        if self.state_path.exists():
            state = self.state()
            self.call('GET', self.artifact_url())
            return {'ontology_id': state['ontology_id'], 'already_registered': True}
        manifest = read_json(self.out / 'manifest.json')
        artifact = self.out / 'engineering-ods.ttl'
        if manifest['artifact_sha256'] != digest(artifact) or manifest['prefix'] != self.config['prefix'] or manifest['version'] != self.config['version'] or manifest['name'] != self.config['name']:
            raise ValueError('Artifact/configuration mismatch; generate again before registration')
        with artifact.open('rb') as source:
            result = self.call('POST', self.config['ontology_api'] + '/register', write=True,
                files={'artifact': ('engineering-ods.ttl', source, 'text/turtle')}, data={
                    'ontology_name': self.config['name'], 'prefix': self.config['prefix'],
                    'description': 'Historical options and current engineering evaluation evidence; authored ODS scenario.',
                    'source': 'Engineering ODS scenario', 'extra_metadata': json.dumps({'generated_scenario_values': True, 'customer_approved': False, 'dataset_version': self.config['version']})})
        state = {'ontology_id': result['ontology_id'], 'ontology_api': self.config['ontology_api'],
                 'oslc_api': self.config['oslc_api'], 'artifact_sha256': manifest['artifact_sha256']}
        save(self.state_path, state)
        return {'ontology_id': result['ontology_id'], 'publication': 'Not requested; review and CR/CO authorization are separate'}

    def lifecycle(self, target, reason):
        result = self.call('POST', self.artifact_url('/transition'), write=True, json={'target': target, 'reason': reason})
        save(self.out / 'lifecycle-receipt.json', result)
        return {'ontology_id': self.state()['ontology_id'], 'requested_lifecycle': target}

    def release(self):
        result = self.call('POST', self.artifact_url('/releases'), write=True, json={
            'family_id': self.config['family_id'], 'version': self.config['version'], 'change_kind': 'initial',
            'change_notes': 'Authored Engineering ODS scenario; not a source-system engineering release.'})
        save(self.out / 'release-receipt.json', result)
        return {'ontology_id': self.state()['ontology_id'], 'declared_version': self.config['version']}

    def change(self, action='status', reason=''):
        oid = quote(self.state()['ontology_id'], safe='')
        url = self.config['oslc_api'] + '/publications/' + oid + '/request'
        view = self.call('GET', url)
        if action != 'status':
            change = view.get('change_request') or {}
            view = self.call('POST', url, write=True, json={'action': action, 'reason': reason,
                'expected_revision': change.get('revision', 0), 'expected_plan_digest': view['current_plan_digest']})
        save(self.out / 'change-control-receipt.json', view)
        change = view.get('change_request') or {}
        order = change.get('order') or {}
        return {'ontology_id': self.state()['ontology_id'], 'state': change.get('state'),
                'request_number': change.get('request_number'), 'order_number': order.get('order_number'),
                'details': str(self.out / 'change-control-receipt.json')}

    def verify(self, wait=0):
        deadline = time.monotonic() + wait
        while True:
            result = self.call('GET', self.artifact_url('/publication'))
            save(self.out / 'publication-receipt.json', result)
            receipt = result.get('receipt') or {}
            state = self.state()
            verified = (result.get('status') == 'published' and receipt.get('status') == 'published'
                        and receipt.get('current') is True and receipt.get('ontology_id') == state['ontology_id']
                        and receipt.get('publication_id') == state['artifact_sha256'])
            if verified or time.monotonic() >= deadline or result.get('status') not in ('publishing', 'queued'):
                return {'verified': verified, 'status': result.get('status'), 'ontology_id': state['ontology_id'],
                        'resources': receipt.get('resources'), 'relationships': receipt.get('relationships'),
                        'details': str(self.out / 'publication-receipt.json')}
            time.sleep(min(3, max(0, deadline - time.monotonic())))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config.example.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('generate').add_argument('--cases', type=int, default=1)
    sub.add_parser('register')
    life = sub.add_parser('lifecycle')
    life.add_argument('--target', required=True, choices=['in_review', 'approved'])
    life.add_argument('--reason', required=True)
    sub.add_parser('release')
    change = sub.add_parser('change')
    change.add_argument('--action', default='status', choices=['status', 'submit', 'accept', 'authorize', 'execute'])
    change.add_argument('--reason', default='')
    sub.add_parser('verify').add_argument('--wait', type=int, default=0)
    args = parser.parse_args(argv)
    config = configuration(args.config)
    if args.command == 'generate':
        result = generate(config, args.cases)
    else:
        if args.command == 'change' and args.action != 'status' and not args.reason.strip():
            raise ValueError('A review reason is required for each change action')
        loader = Loader(config)
        try:
            if args.command == 'register': result = loader.register()
            elif args.command == 'lifecycle': result = loader.lifecycle(args.target, args.reason)
            elif args.command == 'release': result = loader.release()
            elif args.command == 'change': result = loader.change(args.action, args.reason)
            else:
                if not 0 <= args.wait <= 1800: raise ValueError('Wait must be between 0 and 1800 seconds')
                result = loader.verify(args.wait)
        finally:
            loader.close()
    print(json.dumps(result, indent=2))
    return 2 if result.get('verified') is False else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, httpx.HTTPError) as exc:
        # Do not log transport exception text: it can contain customer URLs.
        print('ERROR: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__ + '; inspect local configuration and service readiness'), file=sys.stderr)
        sys.exit(1)
