"""Validate exported syntax, blank-node-safe equivalence and merge triple count."""
import argparse
import json
from pathlib import Path

from rdflib import Graph
from rdflib.compare import isomorphic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ttl', required=True)
    parser.add_argument('--owl', required=True)
    parser.add_argument('--expected-triples', type=int, required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    result = {'status': 'failed'}
    try:
        # Reject external XML entity declarations before RDF/XML parsing.
        xml = Path(args.owl).read_bytes()
        if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
            raise ValueError('XML entity declarations are unsupported')
        ttl = Graph().parse(args.ttl, format='turtle')
        owl = Graph().parse(data=xml, format='xml')
        result.update(ttl_triples=len(ttl), owl_triples=len(owl),
                      expected_triples=args.expected_triples, isomorphic=isomorphic(ttl, owl))
        if args.expected_triples > 0 and len(ttl) == args.expected_triples and result['isomorphic']:
            result['status'] = 'passed'
    except Exception:
        result['error'] = 'RDF parse or semantic validation failed'
    Path(args.report).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
