"""Offline, bounded HermiT process and retained, artifact-bound evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import re
from functools import lru_cache
from datetime import datetime, timezone
from rdflib import Graph, OWL, URIRef, RDF
from .foundation import foundation, alignment_coverage

RESOURCE = Path(__file__).with_name('resources') / 'reasoner'
MAX_SOURCE_BYTES = 64*1024*1024
_slot = threading.BoundedSemaphore(1)
_request_slot = threading.BoundedSemaphore(1)


@lru_cache(maxsize=8)
def _java_supported(executable, modified):
    try:
        process = subprocess.run([executable,'-version'],capture_output=True,timeout=5,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        text = (process.stderr+process.stdout).decode('utf-8',errors='replace')[:4096]
        version = re.search(r'version "(?:1\.)?(\d+)',text)
        return process.returncode == 0 and bool(version) and int(version.group(1)) >= 17
    except (OSError,subprocess.TimeoutExpired): return False


def capabilities():
    java = os.getenv('DEPO_REASONER_JAVA', '').strip() or shutil.which('java')
    jar = RESOURCE / 'depo-owl-dl.jar'
    manifest = RESOURCE / 'manifest.json'
    ready = bool(java and jar.is_file() and manifest.is_file())
    if ready:
        try:
            ready = (_java_supported(java,Path(java).stat().st_mtime_ns) and
                hashlib.sha256(jar.read_bytes()).hexdigest() == json.loads(manifest.read_text(encoding='utf-8-sig'))['sha256'])
        except (OSError,ValueError,KeyError): ready = False
    return {'provider':'HermiT','version':'1.4.5.519','available':ready,
            'mode':'isolated_offline_process','scope':'selected_retained_ontology_plus_embedded_IDO',
            'reason':None if ready else 'Java 17+ runtime or verified bundled reasoner is unavailable'}


def inspect_graph(graph, *, artifact_sha256, include_foundation=True, target_iris=None):
    target_iris = validate_targets(target_iris)
    result = {'status':'unknown','consistency_verified':False,'deductive_reasoner_executed':False,
              'artifact_sha256':artifact_sha256,'checked_at':datetime.now(timezone.utc).isoformat(),
              'scope':'retained RDF assertions; does not include external graph instances',
              'graph_publication_performed':False,'iso_conformance_established':False}
    meta, base = foundation()
    result['foundation'] = {key:meta[key] for key in ('id','version','version_iri','sha256','bundle_sha256','depo_module_version','license')}
    result['foundation']['included'] = include_foundation
    result['alignment'] = alignment_coverage(graph,base)
    kinds = [set(graph.subjects(RDF.type,kind)) for kind in (OWL.ObjectProperty,OWL.DatatypeProperty,OWL.AnnotationProperty)]
    if any(kinds[i] & kinds[j] for i in range(3) for j in range(i+1,3)):
        return {**result,'status':'unsupported','reason':'ambiguous_property_declarations'}
    allowed_imports = {meta['ontology_iri'],meta['version_iri'],'urn:depo:business-core','urn:depo:business-core:1.0.0'}
    imports = {str(value) for value in graph.objects(None,OWL.imports)}
    if imports - allowed_imports or (imports and not include_foundation):
        return {**result,'reason':'unresolved_imports','unresolved_imports':sorted(imports-allowed_imports or imports)[:20]}
    if not capabilities()['available']: return {**result,'reason':'reasoner_unavailable'}
    if len(graph) > 500000: return {**result,'status':'unsupported','reason':'assertion_budget_exceeded'}
    if not _slot.acquire(blocking=False): return {**result,'reason':'reasoner_busy'}
    try:
        merged = Graph()
        for triple in graph:
            if triple[1] != OWL.imports: merged.add(triple)
        if include_foundation:
            for triple in base: merged.add(triple)
        content = merged.serialize(format='turtle',encoding='utf-8')
        if len(content) > 64*1024*1024: return {**result,'status':'unsupported','reason':'input_size_budget_exceeded'}
        timeout = min(180,max(5,int(os.getenv('DEPO_REASONER_TIMEOUT_SECONDS','60'))))
        java = os.getenv('DEPO_REASONER_JAVA','').strip() or shutil.which('java')
        with tempfile.TemporaryDirectory(prefix='depo-owl-dl-') as directory:
            source, output = Path(directory)/'input.ttl',Path(directory)/'result.json'
            source.write_bytes(content)
            command = [java,'-Xmx1024m','-jar',str(RESOURCE/'depo-owl-dl.jar'),str(source),str(output)]
            if target_iris:
                targets = Path(directory)/'targets.json'
                targets.write_text(json.dumps(target_iris), encoding='utf-8')
                command.append(str(targets))
            try:
                completed = subprocess.run(command,
                    timeout=timeout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except subprocess.TimeoutExpired: return {**result,'reason':'reasoner_timeout'}
            if completed.returncode or not output.is_file(): return {**result,'reason':'reasoner_process_failed','worker_exit_code':completed.returncode}
            if output.stat().st_size > 1024*1024: return {**result,'reason':'reasoner_output_budget_exceeded'}
            evidence = json.loads(output.read_text())
        if not isinstance(evidence,dict) or evidence.get('engine') != 'HermiT' or evidence.get('engine_version') != '1.4.5.519' or evidence.get('status') not in {'consistent','inconsistent','unknown','unsupported'}:
            return {**result,'reason':'invalid_reasoner_contract'}
        executed = evidence.get('reasoner_executed') is True
        verified = executed and evidence.get('owl2_dl_profile') is True and evidence['status'] in {'consistent','inconsistent'}
        if evidence['status'] in {'consistent','inconsistent'} and not verified:
            return {**result,'reason':'invalid_reasoner_contract'}
        if evidence['status']=='consistent' and (type(evidence.get('unsatisfiable_class_count')) is not int or evidence['unsatisfiable_class_count'] < 0):
            return {**result,'reason':'invalid_reasoner_contract'}
        return {**result,**evidence,'consistency_verified':verified,'deductive_reasoner_executed':executed,
                'modeling_coherent':(evidence['status']=='consistent' and evidence.get('unsatisfiable_class_count',0)==0) if verified else None}
    except (OSError,ValueError,TypeError): return {**result,'reason':'reasoner_execution_error'}
    finally: _slot.release()


def validate_targets(targets):
    if targets is None: return []
    if not isinstance(targets, list) or len(targets) > 32 or any(not isinstance(value, str) or len(value) > 512 or not value.startswith(('urn:', 'https://', 'http://')) for value in targets):
        raise ValueError('Select up to 32 absolute target IRIs of at most 512 characters')
    return sorted(set(targets))


def inspect_retained(ontology_id, catalog, registry, target_iris=None):
    if not _request_slot.acquire(blocking=False):
        return {'ontology_id':ontology_id,'status':'unknown','reason':'reasoner_busy',
                'consistency_verified':False,'deductive_reasoner_executed':False,'graph_publication_performed':False}
    try: return _inspect_retained(ontology_id,catalog,registry, target_iris=target_iris)
    finally: _request_slot.release()


def semantic_dependencies():
    """Revisions affecting interpretation, also pinned by resumed agent goals."""
    meta, _ = foundation()
    worker = RESOURCE / 'manifest.json'
    return {'foundation_sha256': meta['bundle_sha256'],
            'worker_sha256': hashlib.sha256(worker.read_bytes()).hexdigest() if worker.is_file() else 'unavailable',
            'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def evidence_key(digest):
    dependencies = semantic_dependencies()
    return hashlib.sha256((digest + dependencies['foundation_sha256'] + dependencies['worker_sha256'] + dependencies['adapter_sha256']).encode()).hexdigest()


def current_evidence(ontology_id, catalog, registry):
    """Read only evidence for current bytes/dependencies. Never start reasoning."""
    digest = catalog.artifact_digest(ontology_id)
    result = registry.get(evidence_key(digest))
    return {**result, 'ontology_id': ontology_id} if result else {
        'ontology_id': ontology_id, 'artifact_sha256': digest, 'status': 'not_checked',
        'consistency_verified': False, 'graph_publication_performed': False}


def _inspect_retained(ontology_id, catalog, registry, target_iris=None):
    target_iris = validate_targets(target_iris)
    metadata, content = catalog.read_artifact(ontology_id)
    if len(content) > MAX_SOURCE_BYTES:
        return {'ontology_id':ontology_id,'status':'unsupported','reason':'source_size_budget_exceeded',
                'artifact_sha256':hashlib.sha256(content).hexdigest(),'consistency_verified':False,
                'deductive_reasoner_executed':False,'graph_publication_performed':False}
    digest = hashlib.sha256(content).hexdigest()
    key = evidence_key(digest)
    previous = registry.get(key)
    if previous and (previous.get('reason') == 'unresolved_imports' or
                     (previous.get('status') in {'consistent','inconsistent','unsupported'} and capabilities()['available'] and
                      (not target_iris or set(target_iris).issubset(previous.get('target_checks') or {})))):
        return {**previous,'cached':True,'ontology_id':ontology_id}
    parsed = catalog._parse_ontology(content, metadata.get('original_filename') or 'ontology.ttl', include_graph=True)
    graph = parsed['graph']
    result = inspect_graph(graph,artifact_sha256=digest, target_iris=target_iris)
    if previous and result.get('consistency_verified') is True and previous.get('consistency_verified') is True:
        checks = {**previous.get('target_checks', {}), **result.get('target_checks', {})}
        keep = list(dict.fromkeys([*target_iris, *checks]))[:32]
        result['target_checks'] = {target: checks[target] for target in keep if target in checks}
    result.update(ontology_id=ontology_id,evidence_id=key,cached=False)
    # Deterministic import failures may be reused as unknown, never as success.
    registry.put(key,result)
    return result
