"""Prepare a local XSD closure for a plain-filename root upload; never fetch URLs."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from lxml import etree


def prepare(source, schema_root, output):
    source, boundary, output = Path(source).resolve(), Path(schema_root).resolve(), Path(output).resolve()
    if not source.is_relative_to(boundary):
        raise ValueError('Source must remain within --schema-root')
    if output.exists():
        raise ValueError('Output must be a new directory; existing files are never overwritten')
    pending, documents, total = [source], {}, 0
    while pending:
        path = pending.pop()
        if path in documents:
            continue
        if not path.is_relative_to(boundary) or path.suffix.lower() != '.xsd':
            raise ValueError('Dependency escapes --schema-root or is not an XSD')
        data = path.read_bytes()
        total += len(data)
        if len(documents) >= 64 or total > 25 * 1024 * 1024:
            raise ValueError('Upload closure exceeds 64 files or 25 MiB')
        if b'<!DOCTYPE' in data.replace(b'\x00', b'').upper() or b'<!ENTITY' in data.replace(b'\x00', b'').upper():
            raise ValueError('DTD/entities are not permitted')
        document = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
        if document.tag != '{http://www.w3.org/2001/XMLSchema}schema':
            raise ValueError(f'{path.name}: expected XML Schema root')
        references = []
        for node in document:
            if node.tag not in {'{http://www.w3.org/2001/XMLSchema}'+kind for kind in ('include', 'import', 'redefine')}:
                continue
            location = node.get('schemaLocation')
            if not location:
                continue
            uri = urlsplit(location)
            if uri.scheme or uri.netloc or uri.query or uri.fragment or '%' in location or '\\' in location:
                raise ValueError(f'{path.name}: requires a literal local schemaLocation')
            dependency = (path.parent / location).resolve()
            if not dependency.is_relative_to(boundary):
                raise ValueError(f'{path.name}: dependency escapes --schema-root')
            references.append((node, dependency))
            pending.append(dependency)
        documents[path] = (document, references, data)
    destinations = {path: Path(source.name) if path == source else path.relative_to(boundary) for path in documents}
    if len({str(path).casefold() for path in destinations.values()}) != len(destinations):
        raise ValueError('Upload filenames collide')
    prepared = {}
    for path, (document, references, data) in documents.items():
        changed = False
        for node, dependency in references:
            relative = os.path.relpath(destinations[dependency], destinations[path].parent).replace('\\', '/')
            if relative != node.get('schemaLocation'):
                node.set('schemaLocation', relative)
                changed = True
        prepared[destinations[path].as_posix()] = etree.tostring(document, xml_declaration=True, encoding='UTF-8') if changed else data
    output.mkdir(parents=True)
    for name, data in prepared.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    paths = sorted(name for name in prepared if name != source.name)
    (output / 'dependency-paths.txt').write_text('\n'.join(paths), encoding='utf-8')
    print(json.dumps({'root': str(output/source.name), 'companion_paths': paths, 'files': len(prepared)}))
    return prepared


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--schema-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    prepare(args.source, args.schema_root, args.output)
