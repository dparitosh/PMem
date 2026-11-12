"""Checksum-pinned import closure. Never dereferences an ontology URL."""
import hashlib
import json
from pathlib import Path
from rdflib import Graph, OWL

ROOT=Path(__file__).with_name('resources')/'imports'
MAX_BYTES=2*1024*1024

def catalog():
    content=(ROOT/'manifest.json').read_bytes()
    if len(content)>1024*1024:raise ValueError('Offline import manifest exceeds limit')
    manifest=json.loads(content);documents=manifest.get('documents',[])
    if manifest.get('version')!=1 or not isinstance(documents,list) or len(documents)>32:raise ValueError('Invalid offline import catalog')
    by_iri={};digest=hashlib.sha256(content)
    for item in documents:
        original=ROOT/item['file']
        if original.is_symlink():raise ValueError('Offline import symlink is forbidden')
        path=original.resolve()
        if not path.is_relative_to(ROOT.resolve()) or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Invalid offline import artifact')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Offline import digest mismatch')
        if item['format'] not in {'xml','turtle','nt'}:raise ValueError('Unsupported offline import format')
        digest.update(data)
        for iri in item['iris']:
            if not isinstance(iri,str) or iri in by_iri:raise ValueError('Invalid or duplicate offline import IRI')
            by_iri[iri]=(item,data)
    return by_iri,digest.hexdigest()

def dependency_digest():
    return catalog()[1]

def resolve(graph,allowed=()):
    indexed,digest=catalog();closure=Graph();pending=list(map(str,graph.objects(None,OWL.imports)));seen=set();resolved=[];missing=set()
    while pending:
        iri=pending.pop()
        if iri in seen or iri in allowed:continue
        seen.add(iri)
        if len(seen)>64:raise ValueError('Offline import closure exceeds limit')
        if iri not in indexed:missing.add(iri);continue
        item,data=indexed[iri]
        try:
            imported=Graph().parse(data=data,format=item['format'],publicID=item['source_url'])
        except Exception as exc:
            raise ValueError('Invalid pinned offline vocabulary') from exc
        pending.extend(map(str,imported.objects(None,OWL.imports)))
        for triple in imported:
            if triple[1]!=OWL.imports:closure.add(triple)
        if len(closure)>100000:raise ValueError('Offline import assertions exceed limit')
        resolved.append({'iri':iri,'sha256':item['sha256'],'source_url':item['source_url']})
    return closure,sorted(missing),resolved,digest
