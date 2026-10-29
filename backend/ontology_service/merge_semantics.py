"""SHACL and OWL-RL checks over the exact proposed graph; never claim OWL-DL proof."""
def validation_fingerprint(source_metadata):
    """Bind retained evidence to current validation code, dependencies and shapes."""
    import hashlib
    from pathlib import Path
    from importlib.metadata import version
    from backend.Services.shacl_service import ShaclValidationService
    from backend.depo_platform.upload_limits import ontology_upload_limit
    digest = hashlib.sha256()
    from .owl_dl import semantic_dependencies
    import json
    digest.update(json.dumps(semantic_dependencies(), sort_keys=True).encode())
    for filename in ('merge_semantics.py', 'merge_validation.py', 'merge_service.py', 'merge_reasoning.py', 'merge_reporting.py'):
        digest.update(Path(__file__).with_name(filename).read_bytes())
    for dependency in ('pyshacl', 'owlrl', 'rdflib'): digest.update(version(dependency).encode())
    digest.update(ShaclValidationService().create_default_shapes().encode())
    for metadata in source_metadata:
        path = metadata.get('shacl_file_path')
        identifier = (metadata.get('engineering_artifacts') or {}).get('shacl')
        if identifier:
            from backend.artifact_store import ArtifactStore
            artifact, path = ArtifactStore().resolve(identifier)
            digest.update(str((identifier, artifact.get('filename'), artifact.get('media_type'))).encode())
        if path:
            with Path(path).open('rb') as stream: content = stream.read(ontology_upload_limit() + 1)
            if len(content) > ontology_upload_limit(): raise ValueError('Merge SHACL source exceeds upload limit')
            digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()

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
    from rdflib import Graph, RDF, URIRef, RDFS, OWL
    from rdflib.namespace import SH
    try:
        from .merge_reporting import validate_shacl
    except ImportError as exc:
        raise ValueError('Merge validation requires the installed SHACL/OWL-RL dependencies. Repair the backend installation before approval') from exc
    from backend.Services.shacl_service import ShaclValidationService
    from backend.ontology_service.catalog import OntologyCatalog
    from backend.ontology_service.merge_validation import explicit_conflicts
    from backend.depo_platform.upload_limits import ontology_upload_limit

    checked = Graph()
    for triple in graph: checked.add(triple)
    shapes = Graph()
    editorial_shapes = Graph()
    shape_sources = []
    shape_digests = []
    default_shapes = ShaclValidationService().create_default_shapes()
    def scope_editorial_targets(rule_graph):
        # Generated editorial rules describe submitted declarations, not the
        # unannotated vocabulary introduced by OWL-RL (e.g. owl:Thing).
        for shape, kind in list(rule_graph.subject_objects(SH.targetClass)):
            rule_graph.remove((shape, SH.targetClass, kind))
            for subject in graph.subjects(RDF.type, kind):
                rule_graph.add((shape, SH.targetNode, subject))
        for target, method in ((SH.targetSubjectsOf, lambda predicate: graph.subjects(predicate, None)),
                               (SH.targetObjectsOf, lambda predicate: graph.objects(None, predicate))):
            for shape, predicate in list(rule_graph.subject_objects(target)):
                rule_graph.remove((shape, target, predicate))
                for subject in method(predicate): rule_graph.add((shape, SH.targetNode, subject))
    replacements = {URIRef(item['source_iri']): URIRef(item['target_iri']) for item in (entity_mappings or [])}
    if any(graph.subjects(RDF.type, SH.NodeShape)) or any(graph.subjects(RDF.type, SH.PropertyShape)):
        for triple in graph: shapes.add(triple)
        shape_sources.append('embedded')
    for metadata in source_metadata:
        path = metadata.get('shacl_file_path')
        shape_filename = Path(path).name if path else None
        identifier = (metadata.get('engineering_artifacts') or {}).get('shacl')
        if identifier:
            from backend.artifact_store import ArtifactStore
            artifact, path = ArtifactStore().resolve(identifier)
            # Content-addressed storage deliberately names every payload
            # "content". Its physical suffix is not the RDF serialization.
            shape_filename = artifact.get('filename')
            if not shape_filename or Path(shape_filename).suffix.lower() not in {'.ttl', '.rdf', '.xml', '.owl', '.jsonld', '.json'}:
                media_type = str(artifact.get('media_type') or '').split(';', 1)[0].strip().lower()
                shape_filename = {'text/turtle': 'shapes.ttl', 'application/rdf+xml': 'shapes.rdf',
                                  'application/ld+json': 'shapes.jsonld'}.get(media_type)
            if not shape_filename:
                raise ValueError('Retained merge SHACL artifact has no supported RDF format metadata')
        if not path: continue
        with Path(path).open('rb') as stream: content = stream.read(ontology_upload_limit() + 1)
        if len(content) > ontology_upload_limit(): raise ValueError('Merge SHACL source exceeds upload limit')
        parsed = OntologyCatalog._parse_ontology(content, shape_filename)
        shape_digests.append(hashlib.sha256(content).hexdigest())
        temporary = Graph().parse(data=content, format=parsed['rdf_format'])
        normalized_text = content.decode('utf-8-sig', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
        is_editorial = normalized_text.strip() == default_shapes.strip()
        if is_editorial:
            scope_editorial_targets(temporary)
        # Each shape document has its own blank-node scope.
        from backend.ontology_service.merge_service import GovernedMergeService
        destination = editorial_shapes if is_editorial else shapes
        for triple in GovernedMergeService._scoped_triples(temporary): destination.add(tuple(replacements.get(term, term) for term in triple))
        shape_sources.append(str(identifier or Path(path).name))
    # Embedded instance constraints supplement authored-ontology metadata
    # checks; they must not silently disable the standard metadata profile.
    if not len(editorial_shapes):
        editorial_shapes.parse(data=default_shapes, format='turtle')
        # Default editorial rules describe submitted declarations. OWL-RL adds
        # built-in vocabulary without labels; it must not become an editorial
        # target. Custom/embedded SHACL targets retain their original semantics.
        scope_editorial_targets(editorial_shapes)
        shape_digests.append(hashlib.sha256(default_shapes.encode('utf-8')).hexdigest())
        shape_sources.append('default ontology checks')
    from .merge_reasoning import expand_owlrl
    expand_owlrl(checked)
    # The complete OWL-RL closure was computed above. Avoid running it twice.
    parts = []
    if len(shapes):
        conforms, _, report, summary = validate_shacl(checked, shacl_graph=shapes)
        parts.append(('custom_inferred', conforms, report, summary))
    if len(editorial_shapes):
        # Editorial completeness checks describe authored metadata. OWL-RL can
        # derive extra domain/range restrictions and datatype disjointness;
        # those are not additional metadata declarations needing annotations.
        editorial_graph = Graph()
        for triple in graph: editorial_graph.add(triple)
        for triple in checked:
            if triple[1] in {RDF.type, RDFS.subClassOf}: editorial_graph.add(triple)
        # Standard class-expression typing context for the editorial sh:class
        # checks. This does not alter the proposed graph or custom rule input.
        editorial_graph.add((OWL.Restriction, RDFS.subClassOf, OWL.Class))
        editorial_graph.add((RDFS.Class, RDFS.subClassOf, OWL.Class))
        conforms, _, report, summary = validate_shacl(editorial_graph, shacl_graph=editorial_shapes)
        parts.append(('editorial_asserted', conforms, report, summary))
    from .merge_reporting import combine_summaries, REPORT_PROFILE_LABELS
    if not parts or any(type(item[1]) is not bool for item in parts):
        raise ValueError('Merge SHACL validation did not return conformance')
    conforms = all(item[1] is True for item in parts)
    report_summary = combine_summaries(parts)
    report = (parts[0][2] if len(parts) == 1 else '\n'.join(f'{REPORT_PROFILE_LABELS.get(name,name)}:\n{text}' for name, _, text, _ in parts))[:20000]
    if type(conforms) is not bool: raise ValueError('Merge SHACL validation did not return conformance')
    from .merge_service import GovernedMergeService
    conflicts = explicit_conflicts(checked) + GovernedMergeService._literal_conflicts(checked)
    return {'shacl_conforms':conforms, 'shape_sources':shape_sources, 'shape_digests':shape_digests, 'report':str(report)[:20000],
        'report_summary': report_summary,
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
