"""SHACL and OWL-RL checks over the exact proposed graph; never claim OWL-DL proof."""
def validate_merge(graph, source_metadata, entity_mappings=None, *, declarations_only=False):
    import pickle
    import subprocess
    import sys
    import time
    from pathlib import Path
    from backend.depo_platform.network import bounded_timeout_seconds
    timeout = bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
    from backend.depo_platform.operations import current_operation
    operation = current_operation()
    if operation: timeout = operation.timeout(timeout)
    started = time.monotonic()
    payload = pickle.dumps((graph if isinstance(graph, str) else list(graph), source_metadata, entity_mappings, declarations_only), protocol=pickle.HIGHEST_PROTOCOL)
    remaining = timeout - (time.monotonic() - started)
    if remaining <= 0: raise ValueError('Merge validation preparation exceeded its deadline')
    try:
        result = subprocess.run([sys.executable, '-m', 'backend.ontology_service.merge_semantics'],
            input=payload, capture_output=True, timeout=remaining, cwd=str(Path(__file__).resolve().parents[2]))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Merge validation timed out; its worker was terminated. Narrow the merge or adjust MERGE_VALIDATION_TIMEOUT_SECONDS') from exc
    if result.returncode != 0:
        raise ValueError('Merge semantic validation failed. Check retained shapes and installed SHACL/OWL-RL dependencies')
    if len(result.stdout) > 8 * 1024 * 1024: raise ValueError('Merge validation evidence exceeds its result limit')
    # Trusted local child output only; uploaded bytes are never unpickled.
    evidence = pickle.loads(result.stdout)
    if time.monotonic() - started > timeout: raise ValueError('Merge validation result exceeded its deadline')
    return evidence


def _validate_merge(graph, source_metadata, entity_mappings=None):
    from pathlib import Path
    import hashlib
    from rdflib import Graph, RDF, URIRef
    from rdflib.namespace import SH
    try:
        from pyshacl import validate
    except ImportError as exc:
        raise ValueError('Merge validation requires the installed SHACL/OWL-RL dependencies. Repair the backend installation before approval') from exc
    from backend.Services.shacl_service import ShaclValidationService
    from backend.ontology_service.catalog import OntologyCatalog
    from backend.ontology_service.merge_validation import explicit_conflicts
    from backend.depo_platform.upload_limits import ontology_upload_limit

    checked = Graph()
    for triple in graph: checked.add(triple)
    shapes = Graph()
    shape_sources = []
    shape_digests = []
    replacements = {URIRef(item['source_iri']): URIRef(item['target_iri']) for item in (entity_mappings or [])}
    if any(graph.subjects(RDF.type, SH.NodeShape)) or any(graph.subjects(RDF.type, SH.PropertyShape)):
        for triple in graph: shapes.add(triple)
        shape_sources.append('embedded')
    for metadata in source_metadata:
        path = metadata.get('shacl_file_path')
        identifier = (metadata.get('engineering_artifacts') or {}).get('shacl')
        if identifier:
            from backend.artifact_store import ArtifactStore
            _, path = ArtifactStore().resolve(identifier)
        if not path: continue
        with Path(path).open('rb') as stream: content = stream.read(ontology_upload_limit() + 1)
        if len(content) > ontology_upload_limit(): raise ValueError('Merge SHACL source exceeds upload limit')
        parsed = OntologyCatalog._parse_ontology(content, Path(path).name)
        shape_digests.append(hashlib.sha256(content).hexdigest())
        temporary = Graph().parse(data=content, format=parsed['rdf_format'])
        # Each shape document has its own blank-node scope.
        from backend.ontology_service.merge_service import GovernedMergeService
        for triple in GovernedMergeService._scoped_triples(temporary): shapes.add(tuple(replacements.get(term, term) for term in triple))
        shape_sources.append(str(identifier or Path(path).name))
    if not shape_sources:
        default_shapes = ShaclValidationService().create_default_shapes()
        shapes.parse(data=default_shapes, format='turtle')
        # Default editorial rules describe submitted declarations. OWL-RL adds
        # built-in vocabulary without labels; it must not become an editorial
        # target. Custom/embedded SHACL targets retain their original semantics.
        for shape, kind in list(shapes.subject_objects(SH.targetClass)):
            shapes.remove((shape, SH.targetClass, kind))
            for subject in graph.subjects(RDF.type, kind):
                shapes.add((shape, SH.targetNode, subject))
        shape_digests.append(hashlib.sha256(default_shapes.encode('utf-8')).hexdigest())
        shape_sources.append('default ontology checks')
    conforms, _, report = validate(checked, shacl_graph=shapes, inference='owlrl', inplace=True,
        allow_infos=False, allow_warnings=False, advanced=False, do_owl_imports=False)
    if type(conforms) is not bool: raise ValueError('Merge SHACL validation did not return conformance')
    from .merge_service import GovernedMergeService
    conflicts = explicit_conflicts(checked) + GovernedMergeService._literal_conflicts(checked)
    return {'shacl_conforms':conforms, 'shape_sources':shape_sources, 'shape_digests':shape_digests, 'report':str(report)[:20000],
        'inferred_conflicts':conflicts, 'owl_rl_performed':True, 'full_owl_dl_consistency_established':False}


if __name__ == '__main__':
    import pickle
    import sys
    from rdflib import Graph
    from contextlib import redirect_stdout
    triples, metadata, mappings, declarations_only = pickle.loads(sys.stdin.buffer.read())
    graph = Graph()
    with redirect_stdout(sys.stderr):
        if isinstance(triples, str): graph.parse(data=triples, format='turtle')
        else:
            for triple in triples: graph.add(triple)
        if declarations_only:
            from .merge_service import GovernedMergeService
            from .merge_validation import explicit_conflicts
            evidence = {'inferred_conflicts': explicit_conflicts(graph) + GovernedMergeService._literal_conflicts(graph)}
        else: evidence = _validate_merge(graph, metadata, mappings)
    sys.stdout.buffer.write(pickle.dumps(evidence, protocol=pickle.HIGHEST_PROTOCOL))
