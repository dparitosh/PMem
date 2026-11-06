"""Immutable, offline IDO foundation shipped with DEPO; no implicit mappings."""
import hashlib
import json
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, URIRef

ROOT = Path(__file__).with_name('resources') / 'foundation'


def foundation():
    metadata = json.loads((ROOT / 'manifest.json').read_text())
    path = (ROOT / metadata['file']).resolve()
    if not path.is_relative_to(ROOT.resolve()): raise ValueError('Invalid foundation artifact path')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata['sha256']:
        raise ValueError('Embedded foundation digest mismatch; restore the complete release')
    graph = Graph().parse(data=content, format='turtle')
    if any(graph.triples((None, OWL.imports, None))):
        raise ValueError('Embedded foundation has unapproved imports')
    local_path = ROOT / 'depo-business-core.ttl'
    local_content = local_path.read_bytes()
    if hashlib.sha256(local_content).hexdigest() != metadata['depo_module_sha256']:
        raise ValueError('DEPO business foundation digest mismatch')
    local = Graph().parse(data=local_content,format='turtle')
    allowed = {URIRef(metadata['version_iri'])}
    if set(local.objects(None,OWL.imports)) - allowed: raise ValueError('Unapproved business foundation import')
    for triple in local:
        if triple[1] != OWL.imports: graph.add(triple)
    metadata['depo_module_version'] = '1.0.0'
    metadata['depo_module_sha256'] = hashlib.sha256(local_content).hexdigest()
    metadata['bundle_sha256'] = hashlib.sha256(content+local_content).hexdigest()
    return metadata, graph


def foundation_summary(query='', limit=12):
    meta, graph = foundation()
    classes = sorted(str(s) for s in graph.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef))
    predicates = (RDFS.label, RDFS.comment, URIRef('http://www.w3.org/2004/02/skos/core#definition'),
                  URIRef('http://www.w3.org/2004/02/skos/core#prefLabel'))
    terms = []
    for subject in sorted(set(graph.subjects(RDF.type, None)), key=lambda s: (not str(s).startswith('urn:depo:business:'), str(s))):
        if not isinstance(subject, URIRef): continue
        descriptions = [str(value)[:1600] for predicate in predicates for value in graph.objects(subject, predicate)]
        if query and query.casefold() not in (' '.join([str(subject), *descriptions])).casefold(): continue
        terms.append({'iri': str(subject), 'labels': [str(v)[:250] for v in graph.objects(subject, RDFS.label)][:3],
                      'definitions': descriptions[:4], 'types': sorted(map(str, graph.objects(subject, RDF.type))),
                      'parents': sorted(str(v) for v in graph.objects(subject, RDFS.subClassOf) if isinstance(v, URIRef))[:8]})
    return {**meta, 'embedded':True, 'class_count':len(classes), 'classes':classes,
            'terms': terms[:max(1, min(int(limit), 30))], 'terms_truncated': len(terms) > limit,
            'alignment_approved':False, 'consistency_status':'not_checked',
            'message':'Embedded reference vocabulary. Domain alignment requires reviewed axioms; embedding is not conformance.'}


def alignment_coverage(graph, base):
    """Describe explicit subclass reachability, never semantic equivalence."""
    roots = set(base.subjects(RDF.type, OWL.Class))
    classes = set(graph.subjects(RDF.type, OWL.Class)) - roots
    children = {}
    for child, parent in graph.subject_objects(RDFS.subClassOf): children.setdefault(parent,set()).add(child)
    aligned, pending = set(roots), list(roots)
    while pending:
        for child in children.get(pending.pop(),set()) - aligned:
            aligned.add(child); pending.append(child)
    missing = sorted(map(str,classes-aligned))
    return {'scope':'explicit_subclass_paths_only','domain_classes':len(classes),
            'classes_with_foundation_path':len(classes & aligned),
            'unmapped_class_count':len(missing),'unmapped_classes':missing[:100],
            'alignment_approved':False,'iso_conformance_established':False}


if __name__ == '__main__':
    import sys
    try:
        meta, _ = foundation()
        from .owl_dl import capabilities, inspect_graph
        engine = capabilities()
        result = inspect_graph(Graph(),artifact_sha256=meta['bundle_sha256']) if engine['available'] else None
        valid = result is None or (result['status']=='consistent' and result.get('modeling_coherent') is True)
        print(json.dumps({'status':'ready' if result and valid else 'degraded' if valid else 'failed',
            'foundation':'IDO 4.2 + DEPO business core 1.0.0','bundle_sha256':meta['bundle_sha256'],
            'owl_dl':engine,'foundation_consistency':result['status'] if result else 'not_checked',
            'iso_conformance_established':False}))
        if not valid: sys.exit(1)
    except (OSError,ValueError,KeyError):
        print(json.dumps({'status':'failed','action':'Restore the complete embedded foundation and verified reasoner release files'}))
        sys.exit(1)
