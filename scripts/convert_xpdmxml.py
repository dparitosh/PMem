#!/usr/bin/env python3
"""Convert 3dexperience XPDMXML files into a simple RDF/Turtle ontology.

Creates classes for element types and individuals for each discovered element,
extracting common metadata (ID, Name, UniqueID External, Owner, TimeCreated).
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, URIRef, Literal
except Exception:
    print('Missing dependency: rdflib')
    raise

NS_XP = 'http://www.3ds.com/xsd/XPDMXML'


def sanitize_identifier(s: str) -> str:
    s = str(s or '')
    s = s.strip()
    s = re.sub(r"[^0-9A-Za-z_]+", '_', s)
    s = re.sub(r'_+', '_', s)
    s = re.sub(r'^([^A-Za-z_])', r'_\1', s)
    return s or 'unnamed'


def local_name(tag: str) -> str:
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def extract_text(el, name):
    child = el.find(f'{{{NS_XP}}}{name}')
    if child is None:
        return None
    return (child.text or '').strip()


def process_file(path: Path, g: Graph, ns: Namespace, known_classes: set):
    try:
        tree = ET.parse(str(path))
    except Exception as e:
        print('Failed to parse', path, e)
        return 0

    root = tree.getroot()
    count = 0

    # iterate over interesting elements directly under root structures
    for elem in root.findall('.//'):
        tag_local = local_name(elem.tag)
        # skip generic containers
        if tag_local in ('InfoHeader', 'ProductTransformationStructure', 'ResourceStructure', 'ProcessPlanningStructure'):
            continue
        # Only process elements from XP namespace
        if not elem.tag.startswith('{'+NS_XP+'}'):
            continue

        cls_name = sanitize_identifier(tag_local)
        cls_uri = ns[cls_name]
        if cls_name not in known_classes:
            g.add((cls_uri, RDF.type, OWL.Class))
            g.add((cls_uri, RDFS.label, Literal(tag_local)))
            known_classes.add(cls_name)

        # Build an identifier for this instance
        unique_ext = None
        unique_el = elem.find(f"{{{NS_XP}}}UniqueID")
        if unique_el is not None:
            unique_ext = unique_el.get('External') or unique_el.get('XID')
        inst_id = extract_text(elem, 'ID') or unique_ext or f"{path.stem}_{count}"
        inst_ident = sanitize_identifier(inst_id)
        inst_uri = ns[inst_ident]

        # declare individual and its class
        g.add((inst_uri, RDF.type, OWL.NamedIndividual))
        g.add((inst_uri, RDF.type, cls_uri))
        g.add((inst_uri, RDFS.label, Literal(extract_text(elem, 'Name') or inst_id)))

        # common metadata fields to capture
        for fld in ('ID', 'Name', 'Description', 'RevisionName', 'RevisionIndex', 'Owner', 'Organization', 'Project', 'TimeCreated', 'TimeModified'):
            val = extract_text(elem, fld)
            if val:
                p = ns[f"{cls_name}_{sanitize_identifier(fld)}"]
                g.add((p, RDFS.domain, cls_uri))
                # choose XSD type for time fields
                if fld in ('TimeCreated', 'TimeModified'):
                    try:
                        g.add((p, RDF.type, OWL.DatatypeProperty))
                        g.add((inst_uri, p, Literal(val, datatype=XSD.dateTime)))
                    except Exception:
                        g.add((p, RDF.type, OWL.DatatypeProperty))
                        g.add((inst_uri, p, Literal(val)))
                else:
                    g.add((p, RDF.type, OWL.DatatypeProperty))
                    g.add((inst_uri, p, Literal(val)))

        # capture UniqueID attributes if present
        if unique_el is not None:
            for attr in ('External', 'XID', 'locationOfControl'):
                v = unique_el.get(attr)
                if v:
                    p = ns[f"{cls_name}_unique_{sanitize_identifier(attr)}"]
                    g.add((p, RDFS.domain, cls_uri))
                    g.add((p, RDF.type, OWL.DatatypeProperty))
                    g.add((inst_uri, p, Literal(v)))

        count += 1

    return count


def process_folder(src: Path, out: Path, prefix: str, base_iri: str):
    g = Graph()
    ns = Namespace(base_iri)
    g.bind(prefix, ns)
    g.bind('rdf', RDF)
    g.bind('rdfs', RDFS)
    g.bind('owl', OWL)
    g.bind('xsd', XSD)

    known_classes = set()
    total = 0
    files = list(src.glob('**/*_XPDMXML.xml')) + list(src.glob('**/*.3dxml'))
    if not files:
        print('No XPDMXML or 3dxml files found in', src)
        return False

    for f in files:
        print('Processing', f)
        c = process_file(f, g, ns, known_classes)
        print('  instances:', c)
        total += c

    if total == 0:
        print('No instances extracted. Nothing written.')
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(out), format='turtle')
    print('Wrote', out, 'with', total, 'instances')
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--src', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--prefix', default='dx3')
    p.add_argument('--base', default='http://example.org/3dx#')
    args = p.parse_args()

    ok = process_folder(Path(args.src), Path(args.out), args.prefix, args.base)
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
