# ========== Format Detection & Parsers ==========


# ========== Format Detection & Parsers ==========

# (Moved below FileType definition)

"""
Unified Data Import Service
Consolidates CSV, Excel, PLMXML, STEP, and XML imports with auto-detection,
validation, transformation, and Neo4j ingestion capabilities.
"""

import os
import re
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
import time
from typing import Dict, Any, Optional, List, Tuple

from .workflow_artifact_service import WorkflowArtifactService


def _derive_prefix_from_namespace(namespace: str) -> str:
    """Derive a short lowercase ontology prefix from an XML namespace URI.

    Examples:
      http://www.plmxml.org/Schemas/PLMXMLSchema  -> plmxml
      http://www.omg.org/XMI                     -> xmi
      http://www.w3.org/2001/XMLSchema            -> xsd
    """
    if not namespace:
        return 'unknown'
    _KNOWN = {
        'plmxml.org': 'plmxml',
        'omg.org/XMI': 'xmi',
        'omg.org/spec/XMI': 'xmi',
        'XMLSchema': 'xsd',
        '22-rdf-syntax-ns': 'rdf',
        '/owl#': 'owl',
        '/owl/': 'owl',
        'mbse': 'mbse',
        'step-': 'step',
        'AP239': 'ap239',
        'AP242': 'ap242',
    }
    for pattern, prefix in _KNOWN.items():
        if pattern in namespace:
            return prefix
    # Extract from URI path: last non-empty segment, strip non-alnum
    path_parts = [p for p in namespace.rstrip('/').split('/') if p]
    for part in reversed(path_parts):
        cleaned = re.sub(r'[^a-z0-9]', '', part.lower())
        if len(cleaned) >= 2:
            return cleaned[:20]
    # Fallback: second-level domain (e.g. 'plmxml' from 'www.plmxml.org')
    try:
        host = namespace.split('/')[2]  # 'www.plmxml.org'
        domain_parts = host.split('.')
        sld = domain_parts[-2] if len(domain_parts) >= 2 else domain_parts[0]
        cleaned = re.sub(r'[^a-z0-9]', '', sld.lower())
        if cleaned:
            return cleaned[:20]
    except Exception:
        pass
    return 'unknown'


_PLMXML_METADATA_KEYS = {
    'id',
    'uid',
    'name',
    'label',
    'description',
    'sub_type',
    'sub_class',
    'type',
    'value',
    'text',
    'title',
    'namespace',
    'ontology_prefix',
    'source_ontology',
    'import_id',
}


_PLMXML_STRUCTURAL_TAGS = {
    'AccessIntent',
    'AssociatedAttachment',
    'ApplicationRef',
    'Description',
    'PlainText',
    'Form',
    'UserValue',
}


def _plmxml_row_has_payload(row: Dict[str, Any], tag: str = '') -> bool:
    meaningful = 0
    for key, value in row.items():
        if key in {'element_type', 'id', 'name', 'label', 'description', 'sub_type', 'sub_class', 'ontology_prefix', 'source_ontology', 'semantic_role'}:
            continue
        if value in (None, '', [], {}):
            continue
        key_norm = str(key).strip().lower()
        if key_norm in _PLMXML_METADATA_KEYS:
            continue
        if key_norm.endswith('ref') or key_norm.endswith('refs'):
            continue
        meaningful += 1
    if meaningful:
        return True
    return bool(tag and tag not in _PLMXML_STRUCTURAL_TAGS and any(str(v).strip() for v in row.values()))


def _detect_xml_family(file_content: bytes) -> str:
    """Detect specialized XML families before falling back to generic XML."""
    try:
        from .archimate_service import looks_like_archimate_xml
        if looks_like_archimate_xml(file_content):
            return 'archimate'
    except Exception:
        pass
    head = (file_content or b'')[:8192].lower()
    if (
        b'3ds.com/xsd/3dxml' in head
        or b'vpmrepreference' in head
        or b'vpmrepinstance' in head
        or b'3dxml' in head and b'plmxml' not in head
    ):
        return '3dxml'
    if (
        b'<plmxml' in head
        or b'plmxmlschema' in head
        or b'plmxml.org' in head
    ):
        return 'plmxml'
    return 'xml'

from enum import Enum

logger = logging.getLogger(__name__)

# Keep write transactions moderate to reduce AuraDB timeout risk.
# Relationship-heavy imports usually benefit from smaller batches than node writes.
IMPORT_WRITE_BATCH_SIZE = int(os.getenv('IMPORT_WRITE_BATCH_SIZE', '250'))
IMPORT_LINK_BATCH_SIZE = int(os.getenv('IMPORT_LINK_BATCH_SIZE', '150'))
IMPORT_COMMIT_QUERY_TIMEOUT = int(os.getenv('IMPORT_COMMIT_QUERY_TIMEOUT', os.getenv('NEO4J_IMPORT_QUERY_TIMEOUT', '600')))

class FileType(Enum):
    CSV = 'csv'
    EXCEL = 'excel'
    JSON = 'json'
    PLMXML = 'plmxml'
    STEP = 'step'
    EXPRESS = 'express'
    XML = 'xml'
    XMI = 'xmi'
    XSD = 'xsd'
    THREEDXML = '3dxml'
    ARCHIMATE = 'archimate'
    ONTOLOGY = 'ontology'


class ImportStatus(Enum):
    """Status of import task"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ImportStage(Enum):
    """Stages of import pipeline"""
    UPLOAD = 'upload'
    DETECT = 'detect'
    PARSE = 'parse'
    VALIDATE = 'validate'
    TRANSFORM = 'transform'
    PREVIEW = 'preview'
    INGEST = 'ingest'
    LOAD = 'load'
    VERIFY = 'verify'


class FileFormatDetector:
    """Detects file format and provides format utilities"""
    
    # Mapping of file extensions to FileType
    _EXTENSION_MAP = {
        '.csv': FileType.CSV,
        '.xlsx': FileType.EXCEL,
        '.xls': FileType.EXCEL,
        '.json': FileType.JSON,
        '.plmxml': FileType.PLMXML,
        '.step': FileType.STEP,
        '.stp': FileType.STEP,
        '.stpx': FileType.STEP,
        '.exp': FileType.EXPRESS,
        '.xml': FileType.XML,
        '.xmi': FileType.XMI,
        '.mdxml': FileType.XMI,
        '.xsd': FileType.XSD,
        '.3dxml': FileType.THREEDXML,
        '.archimate': FileType.ARCHIMATE,
        '.owl': FileType.ONTOLOGY,
        '.rdf': FileType.ONTOLOGY,
        '.ttl': FileType.ONTOLOGY,
    }
    
    @classmethod
    def detect(cls, filename: str) -> Optional[FileType]:
        """Detect file type from filename"""
        if not filename:
            return None
        
        # Get file extension
        _, ext = os.path.splitext(filename.lower())
        return cls._EXTENSION_MAP.get(ext)
    
    @classmethod
    def get_supported_formats(cls) -> list:
        """Get list of supported file formats"""
        return [f for f in cls._EXTENSION_MAP.keys() if f]



    @staticmethod
    def parse_xmi(file_content: bytes) -> tuple[list[dict], dict]:
        """Parse XMI/MDXML file using independent XMIParser."""
        from pathlib import Path
        # Import from local Services module
        from .xmi_parser import XMIParser
        from .ap239_parser import AP239XMIParser, classify_ap239_concept, AP239_NAMESPACE

        # Write content to a temp file for parser compatibility
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xmi') as tmp:
            tmp.write(file_content)
            tmp_path = Path(tmp.name)

        ap239_stats: Dict[str, Any] = {}
        try:
            parser = XMIParser()
            parsed = parser.parse(tmp_path)

            # AP239-aware enrichment: if the XMI is an AP239 domain model,
            # run the AP239 XMI parser to get concept-type counts.
            xmi_snippet = file_content[:4096].decode('utf-8', errors='ignore')
            if AP239_NAMESPACE in xmi_snippet or 'AP239' in xmi_snippet.upper():
                _ap239_parser = AP239XMIParser()
                _model = _ap239_parser.parse_xmi_file(tmp_path)
                ap239_stats = {
                    'is_ap239': True,
                    'ap239_parts': len(_model.parts),
                    'ap239_activities': len(_model.activities),
                    'ap239_requirements': len(_model.requirements),
                    'ap239_interfaces': len(_model.interface_connectors),
                    'ap239_documents': len(_model.documents),
                }
        except Exception as xmi_err:
            logging.error(f"XMI parse error: {xmi_err}")
            return [], {'error': str(xmi_err), 'file_format': 'XMI'}
        finally:
            tmp_path.unlink(missing_ok=True)

        nodes = parsed.get("nodes", [])
        relationships = parsed.get("relationships", [])
        provenance = parsed.get("provenance", {})

        # For preview: flatten nodes to rows, extract common columns
        preview_rows = []
        columns = set()
        for node in nodes:
            row = {"label": node.get("label", "Element")}
            props = node.get("properties", {})
            row.update(props)
            preview_rows.append(row)
            columns.update(row.keys())

        # Enrich node labels from AP239 concept classification when detected.
        if ap239_stats.get('is_ap239'):
            for row in preview_rows:
                if row.get('label') in ('Element', 'Class') and row.get('name'):
                    row['ap239_concept'] = classify_ap239_concept(row['name'])

        rel_stats = {
            "relationship_count": len(relationships),
            "relationship_types": list({r.get("type") for r in relationships}),
        }

        # Extract namespace and derive prefix from XMI root element
        _ns_uri = provenance.get('xmi_namespace', '')
        if not _ns_uri:
            _ns_map = provenance.get('namespaces', {}) if isinstance(provenance, dict) else {}
            if isinstance(_ns_map, dict):
                _ns_uri = _ns_map.get('xmi', '') or _ns_map.get('default', '')
        if not _ns_uri:
            try:
                import defusedxml.ElementTree as _ET
                _xmi_root = _ET.fromstring(file_content[:8192])
                _ns_uri = _xmi_root.tag[1:_xmi_root.tag.index('}')] if _xmi_root.tag.startswith('{') else ''
                if not _ns_uri:
                    for _attr, _val in _xmi_root.attrib.items():
                        if 'xmlns' in _attr.lower() and _val.startswith('http'):
                            _ns_uri = _val
                            break
            except Exception:
                pass
        _ns_prefix = _derive_prefix_from_namespace(_ns_uri) if _ns_uri else (
            'ap239' if ap239_stats.get('is_ap239') else 'xmi'
        )

        stats = {
            "row_count": len(preview_rows),
            "column_count": len(columns),
            "columns": list(columns),
            "relationships": rel_stats,
            "provenance": provenance,
            "namespace": _ns_uri,
            "ontology_prefix": _ns_prefix,
            "ontology_name": _ns_uri.rstrip('/').split('/')[-1] or _ns_prefix,
            "_xmi_relationships": relationships,
            **ap239_stats,
        }
        return preview_rows, stats

    @staticmethod
    def parse_express(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse EXPRESS schema file and generate OWL"""
        try:
            from .owl_generation_service import OWLGenerationService
            
            # Generate both schema metadata AND OWL/Turtle
            owl_ttl, schema_metadata = OWLGenerationService.generate_owl_from_express(
                file_content, 
                "schema.exp"
            )
            
            # Add OWL data to metadata for storage
            schema_metadata['owl_ttl'] = owl_ttl
            
            # Convert to rows for preview
            rows = [
                {'type': 'Schema', 'name': schema_metadata.get('schema_name', 'Unknown'), 'entities': schema_metadata.get('entity_count', 0)},
                {'type': 'DERIVE', 'count': schema_metadata.get('derived_attributes', 0)},
                {'type': 'INVERSE', 'count': schema_metadata.get('inverse_attributes', 0)},
                {'type': 'UNIQUE', 'count': schema_metadata.get('unique_constraints', 0)},
                {'type': 'OWL Generated', 'triples': schema_metadata.get('owl_triple_count', 0)},
            ]
            
            for entity_name in schema_metadata.get('entities', [])[:10]:  # Preview first 10
                rows.append({
                    'label': 'ExpressEntity',
                    'entity': entity_name,
                })
            
            return rows, schema_metadata

        except Exception as e:
            logging.error(f"EXPRESS parser error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def parse_xsd(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse XSD schema file for AP239 SHACL ontology generation"""
        try:
            import tempfile
            from lxml import etree
            from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
            from rdflib.namespace import OWL

            # Write to temp file for parser compatibility
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xsd') as tmp:
                tmp.write(file_content)
                tmp_path = Path(tmp.name)

            try:
                # ✅ SECURITY: disable external entities and network to prevent XXE
                _safe_xsd = etree.XMLParser(
                    resolve_entities=False,
                    no_network=True,
                    load_dtd=False,
                    huge_tree=False,
                )
                tree = etree.parse(str(tmp_path), _safe_xsd)
                root = tree.getroot()

                # Namespaces / provenance
                nsmap = {k if k else 'default': v for k, v in (root.nsmap or {}).items()}
                target_ns = root.get('targetNamespace') or ''

                # Intermediate model
                model: Dict[str, Any] = {
                    'types': {},
                    'elements': {},
                    'attributes': {},
                    'groups': {},
                    'attributeGroups': {},
                    'imports': [],
                    'includes': [],
                    'redefines': [],
                    'substitutionGroups': {},
                    'keys': [],
                    'unique': [],
                    'keyrefs': [],
                    'enumerations': {},
                    'unions': {},
                    'lists': {},
                    'any': [],
                    'anyAttribute': [],
                    'provenance': {
                        'namespaces': nsmap,
                        'targetNamespace': target_ns,
                        'root_tag': root.tag,
                    }
                }

                XSD_NS = '{http://www.w3.org/2001/XMLSchema}'

                def safe_tag(elem):
                    return elem.tag.split('}')[-1] if isinstance(elem.tag, str) and '}' in elem.tag else (elem.tag or '')

                # Helper to serialize element XML for traceability
                def xml_snippet(elem):
                    try:
                        return etree.tostring(elem, pretty_print=False).decode('utf-8')
                    except Exception:
                        return ''

                # Gather types
                for ct in tree.findall('.//' + XSD_NS + 'complexType'):
                    name = ct.get('name') or str(uuid.uuid4())
                    model['types'][name] = {
                        'kind': 'complex',
                        'name': name,
                        'xml': xml_snippet(ct),
                        'elements': [],
                        'attributes': [],
                    }
                    # Check for extension/restriction
                    ext = ct.find('.//' + XSD_NS + 'extension')
                    if ext is not None:
                        model['types'][name]['extension_base'] = ext.get('base')
                    restr = ct.find('.//' + XSD_NS + 'restriction')
                    if restr is not None:
                        model['types'][name]['restriction_base'] = restr.get('base')

                for st in tree.findall('.//' + XSD_NS + 'simpleType'):
                    name = st.get('name') or str(uuid.uuid4())
                    model['types'][name] = {
                        'kind': 'simple',
                        'name': name,
                        'xml': xml_snippet(st),
                    }
                    # enumeration / union / list
                    enums = st.findall('.//' + XSD_NS + 'enumeration')
                    if enums:
                        model['enumerations'][name] = [e.get('value') for e in enums if e.get('value')]
                    union = st.find('.//' + XSD_NS + 'union')
                    if union is not None:
                        model['unions'][name] = union.get('memberTypes')
                    lst = st.find('.//' + XSD_NS + 'list')
                    if lst is not None:
                        model['lists'][name] = lst.get('itemType') or ''

                # Elements and attributes
                for el in tree.findall('.//' + XSD_NS + 'element'):
                    name = el.get('name') or str(uuid.uuid4())
                    model['elements'][name] = {
                        'name': name,
                        'type': el.get('type'),
                        'minOccurs': el.get('minOccurs'),
                        'maxOccurs': el.get('maxOccurs'),
                        'substitutionGroup': el.get('substitutionGroup'),
                        'xml': xml_snippet(el),
                    }
                    if el.get('substitutionGroup'):
                        model['substitutionGroups'].setdefault(el.get('substitutionGroup'), []).append(name)

                for attr in tree.findall('.//' + XSD_NS + 'attribute'):
                    name = attr.get('name') or str(uuid.uuid4())
                    model['attributes'][name] = {
                        'name': name,
                        'type': attr.get('type'),
                        'use': attr.get('use'),
                        'xml': xml_snippet(attr),
                    }

                # Groups and attributeGroups
                for grp in tree.findall('.//' + XSD_NS + 'group'):
                    gname = grp.get('name') or str(uuid.uuid4())
                    model['groups'][gname] = {'name': gname, 'xml': xml_snippet(grp)}
                for ag in tree.findall('.//' + XSD_NS + 'attributeGroup'):
                    aname = ag.get('name') or str(uuid.uuid4())
                    model['attributeGroups'][aname] = {'name': aname, 'xml': xml_snippet(ag)}

                # Keys / unique / keyrefs
                for key in tree.findall('.//' + XSD_NS + 'key'):
                    model['keys'].append({'name': key.get('name'), 'xml': xml_snippet(key)})
                for uq in tree.findall('.//' + XSD_NS + 'unique'):
                    model['unique'].append({'name': uq.get('name'), 'xml': xml_snippet(uq)})
                for kr in tree.findall('.//' + XSD_NS + 'keyref'):
                    model['keyrefs'].append({'name': kr.get('name'), 'refer': kr.get('refer'), 'xml': xml_snippet(kr)})

                # any / anyAttribute
                for any_el in tree.findall('.//' + XSD_NS + 'any'):
                    model['any'].append({'xml': xml_snippet(any_el)})
                for any_attr in tree.findall('.//' + XSD_NS + 'anyAttribute'):
                    model['anyAttribute'].append({'xml': xml_snippet(any_attr)})

                # Imports / includes / redefines
                for imp in tree.findall('.//' + XSD_NS + 'import'):
                    model['imports'].append({'namespace': imp.get('namespace'), 'schemaLocation': imp.get('schemaLocation')})
                for inc in tree.findall('.//' + XSD_NS + 'include'):
                    model['includes'].append({'schemaLocation': inc.get('schemaLocation')})
                for red in tree.findall('.//' + XSD_NS + 'redefine'):
                    model['redefines'].append({'xml': xml_snippet(red)})

                # Build a source RDF graph for traceability (lightweight)
                SRC = Namespace('http://depo-onto.local/source#')
                src_g = Graph()
                src_g.bind('src', SRC)
                src_g.bind('owl', OWL)

                root_uri = URIRef(SRC[root.get('name') or Path(tmp_path).stem])
                src_g.add((root_uri, RDF.type, SRC.SourceSchema))
                src_g.add((root_uri, RDFS.label, Literal(Path(tmp_path).name)))

                for tname, tinfo in model['types'].items():
                    c = URIRef(SRC['type/' + tname])
                    src_g.add((c, RDF.type, OWL.Class))
                    src_g.add((c, RDFS.label, Literal(tname)))
                    src_g.add((c, SRC.sourceXml, Literal(tinfo.get('xml', ''))))
                    if tinfo.get('extension_base'):
                        src_g.add((c, RDFS.subClassOf, URIRef(SRC['type/' + tinfo['extension_base']])))
                    if tinfo.get('restriction_base'):
                        src_g.add((c, SRC.restrictionOn, Literal(tinfo['restriction_base'])))

                for ename, einfo in model['elements'].items():
                    p = URIRef(SRC['element/' + ename])
                    # heuristics: if type looks like an xs: primitive, it's a DatatypeProperty
                    typ = einfo.get('type') or ''
                    if typ.startswith('xs:') or typ.startswith('xsd:') or typ in ('string', 'int', 'integer'):
                        src_g.add((p, RDF.type, OWL.DatatypeProperty))
                    else:
                        src_g.add((p, RDF.type, OWL.ObjectProperty))
                    src_g.add((p, RDFS.label, Literal(ename)))
                    src_g.add((p, SRC.sourceXml, Literal(einfo.get('xml', ''))))

                for aname, ainfo in model['attributes'].items():
                    p = URIRef(SRC['attribute/' + aname])
                    src_g.add((p, RDF.type, OWL.DatatypeProperty))
                    src_g.add((p, RDFS.label, Literal(aname)))
                    src_g.add((p, SRC.sourceXml, Literal(ainfo.get('xml', ''))))

                # Convert graph to TTL for downstream preview/storage when reasonable
                try:
                    ttl = src_g.serialize(format='turtle')
                except Exception:
                    ttl = ''

                rows = []
                # produce preview rows: types, elements, attributes
                for tname, tinfo in model['types'].items():
                    rows.append({'kind': 'type', 'name': tname, 'kind_detail': tinfo.get('kind')})
                for ename, einfo in model['elements'].items():
                    rows.append({'kind': 'element', 'name': ename, 'type': einfo.get('type')})
                for aname, ainfo in model['attributes'].items():
                    rows.append({'kind': 'attribute', 'name': aname, 'type': ainfo.get('type')})

                stats = {
                    'type_count': len(model['types']),
                    'element_count': len(model['elements']),
                    'attribute_count': len(model['attributes']),
                    'group_count': len(model['groups']),
                    'import_count': len(model['imports']),
                    'enum_count': sum(1 for k in model['enumerations']),
                    'row_count': len(rows),
                    'format': 'XSD',
                    'file_format': 'XSD',
                    'provenance': model['provenance'],
                    'source_ttl': ttl,
                }

                return rows, stats
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as e:
            logging.error(f"XSD parser error: {e}")
            return [], {'error': str(e), 'file_format': 'XSD'}

    @staticmethod
    def parse_rdf(file_content: bytes, filename: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse OWL/RDF/Turtle ontology content into rows for preview/Neo4j push."""
        try:
            from rdflib import Graph, URIRef, BNode, Literal
            from rdflib.namespace import RDF, RDFS

            ext = Path(filename).suffix.lower()
            candidates = ['xml', 'turtle', 'n3']
            if ext == '.ttl':
                candidates = ['turtle', 'n3', 'xml']

            graph = Graph()
            parse_error = None
            for fmt in candidates:
                try:
                    graph.parse(data=file_content, format=fmt)
                    parse_error = None
                    break
                except Exception as e:
                    parse_error = e
            if parse_error:
                raise parse_error

            rows: List[Dict[str, Any]] = []
            classes_seen = set()

            def _node_id(term: Any) -> str:
                if isinstance(term, URIRef):
                    return str(term)
                if isinstance(term, BNode):
                    return f"_:{term}"
                return str(term)

            def _local_name(term: Any) -> str:
                text = str(term)
                if '#' in text:
                    return text.split('#')[-1]
                if '/' in text:
                    return text.rstrip('/').split('/')[-1]
                return text

            labels: Dict[str, str] = {}
            for s, p, o in graph.triples((None, RDFS.label, None)):
                if isinstance(o, Literal):
                    labels[_node_id(s)] = str(o)

            for s, p, o in graph.triples((None, RDF.type, None)):
                sid = _node_id(s)
                class_name = _local_name(o) or 'OntologyResource'
                if sid in classes_seen:
                    continue
                classes_seen.add(sid)
                rows.append({
                    'name': labels.get(sid) or _local_name(s) or sid,
                    'type': class_name,
                    'id': sid,
                    'namespace': str(s).split('#')[0] if '#' in str(s) else str(s).rsplit('/', 1)[0],
                })
                if len(rows) >= 2000:
                    break

            if not rows:
                for s in graph.subjects():
                    sid = _node_id(s)
                    if sid in classes_seen:
                        continue
                    classes_seen.add(sid)
                    rows.append({
                        'name': labels.get(sid) or _local_name(s) or sid,
                        'type': 'OntologyResource',
                        'id': sid,
                        'namespace': str(s).split('#')[0] if '#' in str(s) else str(s).rsplit('/', 1)[0],
                    })
                    if len(rows) >= 2000:
                        break

            stats = {
                'row_count': len(rows),
                'column_count': len(rows[0].keys()) if rows else 0,
                'columns': list(rows[0].keys()) if rows else [],
                'file_format': 'RDF',
                'format': 'RDF',
                'triple_count': len(graph),
            }
            return rows, stats
        except Exception as e:
            logging.error(f"RDF parser error: {e}")
            return [], {'error': str(e), 'file_format': 'RDF'}

    @staticmethod
    def transform_to_nodes(rows: List[Dict[str, Any]], node_label: str, 
                          merge_keys: Optional[List[str]] = None) -> Tuple[List[str], Dict[str, int]]:
        """Generate Cypher queries for node creation"""
        if not rows:
            return [], {'created': 0}
        
        merge_keys = merge_keys or [list(rows[0].keys())[0]]
        
        # Strip backticks and colons from identifiers to prevent Cypher injection
        # and label-parsing issues (e.g. 'uml:Package' → 'uml_Package').
        safe_label = str(node_label).replace('`', '').replace(':', '_')
        safe_merge_keys = [str(k).replace('`', '') for k in merge_keys]

        # Build MERGE clause using map-literal syntax: {key: row.key}
        merge_props = ", ".join([f"`{key}`: row.`{key}`" for key in safe_merge_keys])
        merge_clause = f"MERGE (n:`{safe_label}` {{{merge_props}}})"
        
        # Build SET clause for all properties — union all row keys to handle heterogeneous rows
        all_keys = [str(k).replace('`', '') for k in {k for row in rows for k in row.keys()}]
        set_props = ", ".join([f"n.`{key}` = row.`{key}`" for key in all_keys])
        
        query = f"""
        UNWIND $rows AS row
        {merge_clause}
        SET {set_props}
        """
        
        stats = {'created': len(rows)}
        return [query], stats

    @staticmethod
    def create_indexes(index_defs: List[Dict[str, Any]]) -> List[str]:
        """Generate index creation queries"""
        queries = []
        
        for idx in index_defs:
            index_type = idx.get('type', 'range')
            raw_name = idx.get('name', f"idx_{uuid.uuid4().hex[:8]}")
            raw_label = idx.get('label')
            properties = idx.get('properties', [])
            
            if not raw_label or not properties:
                continue

            # Strip backticks and colons to prevent Cypher injection / label-parsing issues
            index_name = str(raw_name).replace('`', '').replace(':', '_')
            label = str(raw_label).replace('`', '').replace(':', '_')
            safe_props = [str(p).replace('`', '') for p in properties]
            prop_list = ", ".join([f"n.`{p}`" for p in safe_props])
            
            if index_type == "range":
                query = f"CREATE INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON ({prop_list})"
            elif index_type == "text":
                query = f"CREATE TEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.`{safe_props[0]}`)"
            elif index_type == "fulltext":
                query = f"CREATE FULLTEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON EACH [{prop_list}]"
            elif index_type == "vector":
                query = f"CREATE VECTOR INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.`{safe_props[0]}`) OPTIONS {{indexConfig: {{`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}}}"
            else:
                continue
            
            queries.append(query)
        
        return queries

    @staticmethod
    def _append_index(indexes: List[Dict[str, Any]], seen: set, idx_type: str, label: str, properties: List[str], name: str) -> None:
        safe_properties = [str(prop) for prop in (properties or []) if prop]
        if not label or not safe_properties:
            return
        signature = (idx_type, str(label), tuple(safe_properties))
        if signature in seen:
            return
        seen.add(signature)
        indexes.append({
            'type': idx_type,
            'name': name,
            'label': label,
            'properties': safe_properties,
        })

    @classmethod
    def _recommended_indexes_for_label(cls, label: str, merge_key: str, properties: List[str]) -> List[Dict[str, Any]]:
        indexes: List[Dict[str, Any]] = []
        seen = set()
        props = {str(prop) for prop in (properties or []) if prop}
        safe_label = str(label).lower().replace(':', '_').replace(' ', '_')

        if 'import_row_key' in props:
            if 'import_id' in props:
                cls._append_index(
                    indexes,
                    seen,
                    'range',
                    label,
                    ['import_id', 'import_row_key'],
                    f"idx_{safe_label}_import_id_import_row_key".replace('-', '_'),
                )
            cls._append_index(
                indexes,
                seen,
                'range',
                label,
                ['import_row_key'],
                f"idx_{safe_label}_import_row_key".replace('-', '_'),
            )

        if merge_key:
            if 'import_id' in props and merge_key != 'import_id':
                cls._append_index(
                    indexes,
                    seen,
                    'range',
                    label,
                    ['import_id', merge_key],
                    f"idx_{safe_label}_import_id_{merge_key}".replace('-', '_'),
                )
            cls._append_index(
                indexes,
                seen,
                'range',
                label,
                [merge_key],
                f"idx_{safe_label}_{merge_key}".replace('-', '_'),
            )

        for text_prop in ('name', 'part_number', 'title'):
            if text_prop in props and text_prop != merge_key:
                cls._append_index(
                    indexes,
                    seen,
                    'text',
                    label,
                    [text_prop],
                    f"idx_{safe_label}_{text_prop}_text".replace('-', '_'),
                )

        for range_prop in ('ontology_prefix', 'source_ontology', 'part_ref', 'parent_ref'):
            if range_prop in props and range_prop != merge_key:
                cls._append_index(
                    indexes,
                    seen,
                    'range',
                    label,
                    [range_prop],
                    f"idx_{safe_label}_{range_prop}".replace('-', '_'),
                )

        return indexes


# ========== File Parser Router ==========

class FileParser:
    """Dispatcher for routing files to appropriate parser based on type"""
    
    @staticmethod
    def parse(
        file_content: bytes,
        file_type: FileType,
        parse_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Parse file content based on file type
        
        Args:
            file_content: Raw file bytes
            file_type: FileType enum value
        
        Returns:
            Tuple of (rows: List[Dict], stats: Dict)
        """
        parse_options = parse_options or {}
        try:
            if file_type == FileType.CSV:
                return FileParser._parse_csv(file_content)
            elif file_type == FileType.EXCEL:
                return FileParser._parse_excel(file_content)
            elif file_type == FileType.XMI:
                return FileFormatDetector.parse_xmi(file_content)
            elif file_type == FileType.XSD:
                return FileFormatDetector.parse_xsd(file_content)
            elif file_type == FileType.EXPRESS:
                return FileFormatDetector.parse_express(file_content)
            elif file_type == FileType.PLMXML:
                return FileParser._parse_plmxml(
                    file_content,
                    metadata_exclusion_tags=parse_options.get('metadata_exclusion_tags'),
                )
            elif file_type == FileType.STEP:
                return FileParser._parse_step(file_content)
            elif file_type == FileType.THREEDXML:
                return FileParser._parse_threedxml(file_content)
            elif file_type == FileType.ARCHIMATE:
                return FileParser._parse_archimate(file_content)
            elif file_type == FileType.XML:
                xml_family = _detect_xml_family(file_content)
                if xml_family == 'archimate':
                    return FileParser._parse_archimate(file_content)
                if xml_family == '3dxml':
                    return FileParser._parse_threedxml(file_content)
                if xml_family == 'plmxml':
                    return FileParser._parse_plmxml(
                        file_content,
                        metadata_exclusion_tags=parse_options.get('metadata_exclusion_tags'),
                    )
                return FileParser._parse_xml(file_content)
            elif file_type == FileType.JSON:
                return FileParser._parse_json(file_content)
            else:
                return [], {'error': f'Unsupported file type: {file_type}'}
        except Exception as e:
            logging.error(f"Error parsing {file_type.value}: {str(e)}")
            return [], {'error': str(e), 'file_type': file_type.value}
    
    @staticmethod
    def _parse_archimate(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse ArchiMate Model Exchange XML into architecture/process rows."""
        try:
            from .archimate_service import parse_archimate_model_exchange

            rows, stats = parse_archimate_model_exchange(file_content)
            logging.info(
                "[OK] ArchiMate parsed: %s elements, %s relationships, %s views",
                stats.get("element_count", len(rows)),
                stats.get("relationship_count", 0),
                stats.get("view_count", 0),
            )
            return rows, stats
        except Exception as exc:
            logging.error("ArchiMate parse error: %s", exc)
            return [], {"error": str(exc), "file_format": "ArchiMate"}

    @staticmethod
    def _coerce_value(val: Any) -> Any:
        """Coerce a string scalar to int/float/bool where unambiguous; leaves non-strings unchanged."""
        if not isinstance(val, str):
            return val
        stripped = val.strip()
        if not stripped:
            return val
        # Boolean
        if stripped.lower() == 'true':
            return True
        if stripped.lower() == 'false':
            return False
        # Integer (reject zero-padded strings to avoid mangling IDs like '007')
        digits = stripped.lstrip('-')
        if digits.isdigit() and not (len(digits) > 1 and digits[0] == '0'):
            try:
                return int(stripped)
            except ValueError:
                pass
        # Float — only coerce when str() round-trips exactly (guards against '007' → 7.0)
        try:
            f = float(stripped)
            if str(f) == stripped:
                return f
        except ValueError:
            pass
        return val

    @staticmethod
    def _parse_csv(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse CSV file — tries multiple encodings common in CAD/PLM exports."""
        import csv
        import io

        # Try encodings in order of likelihood for CAD/Windows-origin files
        decoded: Optional[str] = None
        encoding_used = 'utf-8'
        for enc in ('utf-8-sig', 'utf-8', 'windows-1252', 'latin-1'):
            try:
                decoded = file_content.decode(enc)
                encoding_used = enc
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if decoded is None:
            decoded = file_content.decode('utf-8', errors='replace')
            encoding_used = 'utf-8 (with replacement)'

        try:
            # Auto-detect delimiter (tab, comma, semicolon)
            sample = decoded[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
            except csv.Error:
                dialect = csv.excel  # default comma dialect
            reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
            # G21: sanitize empty / duplicate column headers before reading rows
            if reader.fieldnames:
                seen: Dict[str, int] = {}
                sanitized = []
                for i, name in enumerate(reader.fieldnames):
                    clean = str(name).strip() if name else ''
                    clean = clean or f'col_{i}'
                    if clean in seen:
                        seen[clean] += 1
                        clean = f'{clean}_{seen[clean]}'
                    else:
                        seen[clean] = 0
                    sanitized.append(clean)
                reader.fieldnames = sanitized
            rows = list(reader)
            # L2: coerce numeric/boolean values so Neo4j stores correct scalar types
            rows = [{k: FileParser._coerce_value(v) for k, v in row.items()} for row in rows]
            stats = {
                'format': 'CSV',
                'encoding': encoding_used,
                'delimiter': getattr(dialect, 'delimiter', ','),
                'row_count': len(rows),
                'column_count': len(rows[0]) if rows else 0,
                'columns': list(rows[0].keys()) if rows else []
            }
            return rows, stats
        except Exception as e:
            logging.error(f"CSV parse error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def _parse_json(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse JSON file - supports both array of objects and single object"""
        try:
            content = file_content.decode('utf-8')
            data = json.loads(content)
            
            # If data is a dict, wrap in list
            def _flatten(d: dict, prefix: str = '') -> dict:
                """Flatten nested dicts; preserve scalar lists and stringify complex lists."""
                out: dict = {}
                for k, v in d.items():
                    full_key = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, dict):
                        out.update(_flatten(v, full_key))
                    elif isinstance(v, list):
                        if all(isinstance(item, (str, int, float, bool)) or item is None for item in v):
                            out[full_key] = [
                                FileParser._coerce_value(item) if isinstance(item, str) else item
                                for item in v
                            ]
                        else:
                            out[full_key] = json.dumps(v)
                    else:
                        out[full_key] = FileParser._coerce_value(v) if isinstance(v, str) else v
                return out

            if isinstance(data, dict):
                rows = [_flatten(data)]
            elif isinstance(data, list):
                rows = [_flatten(r) if isinstance(r, dict) else {'value': r} for r in data]
            else:
                return [], {'error': 'JSON must be an object or array of objects'}
            
            # Extract column names from first row
            columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
            
            stats = {
                'format': 'JSON',
                'row_count': len(rows),
                'column_count': len(columns),
                'columns': columns
            }
            return rows, stats
        except json.JSONDecodeError as e:
            logging.error(f"JSON parse error: {e}")
            return [], {'error': f'Invalid JSON: {str(e)}'}
        except Exception as e:
            logging.error(f"JSON parse error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def _parse_xml(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse generic XML file into rows using element tag/attributes/text"""
        try:
            import defusedxml.ElementTree as ET  # ✅ SECURITY: prevents XXE
            root = ET.fromstring(file_content)

            rows = []
            for child in root.iter():
                if not isinstance(child.tag, str):
                    continue
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                row = {'tag': tag}
                row.update(child.attrib)
                if child.text and child.text.strip():
                    row['text'] = child.text.strip()
                rows.append(row)

            columns = list(rows[0].keys()) if rows else []
            stats = {
                'format': 'XML',
                'row_count': len(rows),
                'column_count': len(columns),
                'columns': columns,
                'root_element': root.tag.split('}')[-1] if '}' in root.tag else root.tag,
            }
            return rows, stats
        except Exception as e:
            logging.error(f"XML parse error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def _parse_excel(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse Excel file (.xlsx / .xls) using pandas"""
        import io
        try:
            import pandas as pd
            buf = io.BytesIO(file_content)
            # Detect format: openpyxl for .xlsx, xlrd for legacy .xls
            # Read first 8 bytes to check magic number
            magic = file_content[:8]
            is_legacy_xls = magic[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
            engine = 'xlrd' if is_legacy_xls else 'openpyxl'
            try:
                df = pd.read_excel(buf, engine=engine)
            except Exception:
                # Fallback: try the other engine
                buf.seek(0)
                df = pd.read_excel(buf, engine='openpyxl' if engine == 'xlrd' else 'xlrd')
            df = df.fillna('')
            rows = df.to_dict(orient='records')
            # Stringify keys and values for safety
            rows = [{str(k): str(v) if not isinstance(v, (int, float, bool)) else v
                     for k, v in r.items()} for r in rows]
            columns = list(df.columns.astype(str))
            stats = {
                'format': 'Excel',
                'row_count': len(rows),
                'column_count': len(columns),
                'columns': columns,
            }
            return rows, stats
        except ImportError:
            logging.error("openpyxl not installed; cannot parse Excel files")
            return [], {'error': 'openpyxl is required to parse Excel files. Install it with: pip install openpyxl'}
        except Exception as e:
            logging.error(f"Excel parse error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def _parse_plmxml(
        file_content: bytes,
        metadata_exclusion_tags: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse PLMXML file using the dedicated plmxml_parser module.

        Extracts semantic PLM objects: parts, BOMs, processes, requirements,
        RFLP trace links, and product instances with parent-child structure.
        Falls back to generic XML flatten if the dedicated parser fails.
        """
        import tempfile
        from pathlib import Path as _Path
        try:
            from .plmxml_parser import parse_plmxml_file, _normalize_ref

            with tempfile.NamedTemporaryFile(delete=False, suffix='.plmxml') as tmp:
                tmp.write(file_content)
                tmp_path = _Path(tmp.name)
            try:
                doc = parse_plmxml_file(tmp_path, metadata_exclusion_tags=metadata_exclusion_tags)
            finally:
                tmp_path.unlink(missing_ok=True)

            rows: List[Dict[str, Any]] = []
            rows_by_id: Dict[str, Dict[str, Any]] = {}
            raw_rels: List[Dict[str, Any]] = []
            rel_seen = set()
            row_key_counts: Dict[str, int] = {}
            metadata_only_skipped = 0
            metadata_properties_attached = 0

            def append_row(row: Dict[str, Any]) -> None:
                if row.get('id') and not row.get('name'):
                    row['name'] = row['id']
                source_id = str(row.get('id') or '').strip()
                if source_id:
                    occurrence = row_key_counts.get(source_id, 0) + 1
                    row_key_counts[source_id] = occurrence
                    row.setdefault('import_row_key', source_id if occurrence == 1 else f'{source_id}::{occurrence}')
                rows.append(row)
                if row.get('id'):
                    rows_by_id[str(row['id'])] = row

            def append_rel(from_id: str, to_id: str, rel_type: str, **props: Any) -> None:
                from_id = _normalize_ref(str(from_id or ''))
                to_id = _normalize_ref(str(to_id or ''))
                if not from_id or not to_id or from_id == to_id:
                    return
                safe_type = str(rel_type or 'RELATED_TO')
                key = (from_id, to_id, safe_type)
                if key in rel_seen:
                    return
                rel_seen.add(key)
                payload = {
                    'from_props': {'id': from_id},
                    'to_props': {'id': to_id},
                    'type': safe_type,
                }
                if props:
                    payload['properties'] = props
                raw_rels.append(payload)

            def _safe_metadata_key(prefix: str, key: str) -> str:
                slug = re.sub(r'[^0-9a-zA-Z]+', '_', str(key or '').strip()).strip('_').lower()
                if not slug:
                    slug = 'value'
                return f'{prefix}_{slug}'

            def _merge_metadata_properties(target_row: Dict[str, Any], metadata_props: Dict[str, Any]) -> bool:
                changed = False
                for key, value in metadata_props.items():
                    if value in (None, '', [], {}):
                        continue
                    if key not in target_row:
                        target_row[key] = value
                        changed = True
                return changed

            def _metadata_properties_for_id(metadata_id: str) -> Dict[str, Any]:
                metadata_id = _normalize_ref(str(metadata_id or ''))
                if not metadata_id:
                    return {}
                user_data = doc.user_data.get(metadata_id)
                if user_data:
                    props: Dict[str, Any] = {
                        'metadata_user_data_id': user_data.id,
                    }
                    if user_data.type:
                        props['metadata_user_data_type'] = user_data.type
                    if user_data.title:
                        props['metadata_user_data_title'] = user_data.title
                    for title, value in (user_data.values or {}).items():
                        if value not in (None, ''):
                            props[_safe_metadata_key('user_data', title)] = value
                    return props

                form = doc.forms.get(metadata_id)
                if form and getattr(form, 'is_structural', False):
                    props = {
                        'metadata_form_id': form.id,
                    }
                    if form.sub_type:
                        props['metadata_form_sub_type'] = form.sub_type
                    if form.sub_class:
                        props['metadata_form_sub_class'] = form.sub_class
                    if form.description:
                        props['metadata_form_description'] = form.description
                    for title, value in (form.attributes or {}).items():
                        if value not in (None, ''):
                            props[_safe_metadata_key('form', title)] = value
                    return props

                generic = doc.generic_entities.get(metadata_id)
                if generic and getattr(generic, 'is_structural', False):
                    props = {
                        'metadata_tag': generic.tag,
                    }
                    if generic.subtype:
                        props['metadata_sub_type'] = generic.subtype
                    if generic.description:
                        props['metadata_description'] = generic.description
                    return props
                return {}

            def _consume_metadata_reference(target_row: Dict[str, Any], metadata_id: str) -> bool:
                nonlocal metadata_properties_attached
                metadata_props = _metadata_properties_for_id(metadata_id)
                if not metadata_props:
                    return False
                if _merge_metadata_properties(target_row, metadata_props):
                    metadata_properties_attached += 1
                return True

            for pid, part in doc.parts.items():
                part_row = {
                    'element_type': 'Part', 'id': pid,
                    'name': part.name, 'part_number': part.part_number,
                    'revision': part.revision, 'description': part.description,
                    'part_type': part.part_type,
                    'master_ref': part.master_ref,
                }
                append_row(part_row)
                for user_data_ref in part.user_data_refs:
                    if not _consume_metadata_reference(part_row, user_data_ref):
                        append_rel(pid, user_data_ref, 'USER_DATA_REF')
                if part.master_ref and not _consume_metadata_reference(part_row, part.master_ref):
                    append_rel(pid, part.master_ref, 'MASTER_REF')

            for rid, req in doc.requirements.items():
                append_row({
                    'element_type': 'Requirement', 'id': rid,
                    'name': req.name, 'catalogue_id': req.catalogue_id,
                    'revision': req.revision,
                    'body_text': (req.body_text or '')[:500],
                    'master_ref': req.master_ref,
                    'dataset_ref': req.dataset_ref,
                })
                if req.master_ref:
                    append_rel(rid, req.master_ref, 'MASTER_REF')
                if req.dataset_ref:
                    append_rel(rid, req.dataset_ref, 'DATASET_REF')
                if req.revision_id and req.revision_id != rid:
                    append_row({
                        'element_type': 'RequirementRevision', 'id': req.revision_id,
                        'name': req.name, 'catalogue_id': req.catalogue_id,
                        'revision': req.revision,
                        'body_text': (req.body_text or '')[:500],
                        'master_ref': req.master_ref,
                        'dataset_ref': req.dataset_ref,
                        'requirement_ref': rid,
                    })
                    append_rel(req.revision_id, rid, 'REVISION_OF')
                    if req.master_ref:
                        append_rel(req.revision_id, req.master_ref, 'MASTER_REF')
                    if req.dataset_ref:
                        append_rel(req.revision_id, req.dataset_ref, 'DATASET_REF')

            for proc_id, proc in doc.processes.items():
                append_row({
                    'element_type': 'Process', 'id': proc_id,
                    'name': proc.name, 'process_type': proc.process_type,
                    'description': proc.description,
                })
                for resource_id in proc.resources:
                    append_rel(proc_id, resource_id, 'RESOURCE_REF')

            for view_id, view in doc.product_views.items():
                append_row({
                    'element_type': 'ProductView', 'id': view_id,
                    'name': view.name, 'view_type': view.view_type,
                    'structure_type': view.structure_type,
                    'product_ref': view.product_ref,
                })
                if view.product_ref:
                    append_rel(view_id, view.product_ref, 'PRODUCT_REF')
                for root_ref in view.root_refs:
                    append_rel(view_id, root_ref, 'HAS_ROOT')

            for inst in doc.product_instances:
                inst_row = {
                    'element_type': 'ProductInstance', 'id': inst.id,
                    'name': inst.name, 'part_ref': inst.part_ref,
                    'parent_ref': inst.parent_ref, 'transform_ref': inst.transform_ref,
                    'quantity': str(inst.quantity),
                }
                append_row(inst_row)
                if inst.parent_ref:
                    append_rel(inst.parent_ref, inst.id, 'HAS_CHILD_INSTANCE')
                if inst.part_ref:
                    append_rel(inst.id, inst.part_ref, 'PART_REF')
                if inst.transform_ref:
                    append_rel(inst.id, inst.transform_ref, 'TRANSFORM_REF')
                for occurrence_ref in inst.occurrence_refs:
                    append_rel(inst.id, occurrence_ref, 'OCCURRENCE_REF')
                for user_data_ref in inst.user_data_refs:
                    if not _consume_metadata_reference(inst_row, user_data_ref):
                        append_rel(inst.id, user_data_ref, 'USER_DATA_REF')
                for app_ref in inst.application_refs:
                    if not _consume_metadata_reference(inst_row, app_ref):
                        append_rel(inst.id, app_ref, 'APPLICATION_REF')

            for view_id, view in doc.process_views.items():
                append_row({
                    'element_type': 'ProcessView', 'id': view_id,
                    'name': view.name,
                })
                for root_process_ref in view.root_process_refs:
                    append_rel(view_id, root_process_ref, 'HAS_ROOT_PROCESS')
                for product_ref in view.product_refs:
                    append_rel(view_id, product_ref, 'PRODUCT_REF')

            for proc_inst in doc.process_instances:
                append_row({
                    'element_type': 'ProcessInstance', 'id': proc_inst.id,
                    'process_ref': proc_inst.process_ref,
                })
                if proc_inst.process_ref:
                    append_rel(proc_inst.id, proc_inst.process_ref, 'PROCESS_REF')
                for predecessor_ref in proc_inst.predecessor_refs:
                    append_rel(proc_inst.id, predecessor_ref, 'PREDECESSOR_REF')
                for product_instance_ref in proc_inst.product_instance_refs:
                    append_rel(proc_inst.id, product_instance_ref, 'PRODUCT_INSTANCE_REF')

            for notice_id, notice in doc.change_notices.items():
                append_row({
                    'element_type': 'ChangeNotice', 'id': notice_id,
                    'name': notice.name, 'change_type': notice.change_type,
                    'status': notice.status, 'description': notice.description,
                })
                for affected_id in notice.affected_items:
                    append_rel(notice_id, affected_id, 'AFFECTED_ITEM')

            for revision_id, revision in doc.revisions.items():
                append_row({
                    'element_type': 'Revision', 'id': revision_id,
                    'revision_id': revision.revision_id,
                    'revision_type': revision.revision_type,
                    'base_ref': revision.base_ref,
                    'description': revision.description,
                })
                if revision.base_ref:
                    append_rel(revision_id, revision.base_ref, 'BASE_REF')
                for notice_ref in revision.change_notice_refs:
                    append_rel(revision_id, notice_ref, 'CHANGE_NOTICE_REF')

            for transform_id, transform in doc.transforms.items():
                append_row({
                    'element_type': 'Transform', 'id': transform_id,
                    'matrix': ' '.join(str(v) for v in transform.matrix),
                })

            for userdata_id, userdata in doc.user_data.items():
                metadata_only_skipped += 1

            for document_id, document in doc.documents.items():
                document_row = {
                    'element_type': 'Document', 'id': document_id,
                    'name': document.name,
                    'document_type': document.document_type,
                    'revision': document.revision,
                    'description': document.description,
                }
                append_row(document_row)
                for file_ref in document.external_file_refs:
                    append_rel(document_id, file_ref, 'EXTERNAL_FILE_REF')
                for userdata_ref in document.user_data_refs:
                    if not _consume_metadata_reference(document_row, userdata_ref):
                        append_rel(document_id, userdata_ref, 'USER_DATA_REF')

            for file_id, external_file in doc.external_files.items():
                append_row({
                    'element_type': 'ExternalFile', 'id': file_id,
                    'name': external_file.name,
                    'location': external_file.location,
                    'format': external_file.format,
                    'mime_type': external_file.mime_type,
                })

            for rel in doc.general_relations:
                append_row({
                    'element_type': 'GeneralRelation', 'id': rel.id,
                    'name': rel.tc_label or rel.sub_type or rel.id,
                    'sub_type': rel.sub_type,
                    'tc_label': rel.tc_label,
                    'related_count': str(len(rel.related_refs)),
                })
                for target_id in rel.related_refs:
                    append_rel(rel.id, target_id, rel.sub_type or 'RELATED_TO', tc_label=rel.tc_label)

            for form_id, form in doc.forms.items():
                metadata_only_skipped += 1

            for generic_id, generic in doc.generic_entities.items():
                generic_row = {
                    'element_type': generic.tag, 'id': generic_id,
                    'name': generic.name,
                    'description': generic.description,
                    'sub_type': generic.subtype,
                    'semantic_role': getattr(generic, 'semantic_role', 'entity'),
                }
                if getattr(generic, 'is_structural', False) or not _plmxml_row_has_payload(generic_row, generic.tag):
                    metadata_only_skipped += 1
                    continue
                append_row(generic_row)

            for rel in doc.relationships:
                source_row = rows_by_id.get(_normalize_ref(rel.source_id))
                target_row = rows_by_id.get(_normalize_ref(rel.target_id))
                source_is_metadata = bool(_metadata_properties_for_id(rel.source_id))
                target_is_metadata = bool(_metadata_properties_for_id(rel.target_id))

                if source_row and target_is_metadata and _consume_metadata_reference(source_row, rel.target_id):
                    continue
                if target_row and source_is_metadata and _consume_metadata_reference(target_row, rel.source_id):
                    continue
                if source_is_metadata or target_is_metadata:
                    metadata_only_skipped += 1
                    continue
                append_rel(rel.source_id, rel.target_id, rel.relationship_type, **(rel.properties or {}))

            _ns_uri = str(doc.parse_stats.get('namespace') or '')
            _ns_prefix = _derive_prefix_from_namespace(_ns_uri)

            columns = list(rows[0].keys()) if rows else []
            stats = {
                'format': 'PLMXML',
                'schema_version': doc.schema_version,
                'namespace': _ns_uri,
                'ontology_prefix': _ns_prefix,
                'ontology_name': _ns_uri.rstrip('/').split('/')[-1] or _ns_prefix,
                'row_count': len(rows),
                'column_count': len(columns),
                'columns': columns,
                'parts_count': len(doc.parts),
                'requirements_count': len(doc.requirements),
                'processes_count': len(doc.processes),
                'bom_links': len(doc.product_instances),
                'elements_parsed': doc.parse_stats.get('elements_parsed', 0),
                'classes_created': doc.parse_stats.get('classes_created', 0),
                'individuals_created': len(rows),
                'relationships_created': len(raw_rels),
                'unresolved_references': doc.parse_stats.get('unresolved_references', 0),
                'duplicate_ids': doc.parse_stats.get('duplicate_ids', 0),
                'skipped_elements': doc.parse_stats.get('skipped_elements', 0),
                'malformed_elements': doc.parse_stats.get('malformed_elements', 0),
                'parse_ingestion_time': doc.parse_stats.get('ingestion_time', 0),
                'unresolved_reference_details': doc.unresolved_references[:200],
                'duplicate_id_values': doc.duplicate_ids[:200],
                'metadata_only_entities_skipped': metadata_only_skipped,
                'metadata_properties_attached': metadata_properties_attached,
                'metadata_exclusion_tags': doc.parse_stats.get('metadata_exclusion_tags', []),
                '_xmi_relationships': raw_rels,  # reused by commit_import relationship writer
            }
            return rows, stats

        except ImportError:
            logging.warning("plmxml_parser not available — falling back to generic XML flatten")
        except Exception as e:
            logging.error(f"PLMXML dedicated parser error: {e}")

        # Fallback: generic XML flatten (defusedxml — XXE-safe)
        try:
            import defusedxml.ElementTree as ET  # ✅ SECURITY: prevents XXE
            root = ET.fromstring(file_content)
            # Extract namespace from root tag: {http://...}TagName
            ns_uri = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else root.get('xmlns', '')
            ns_prefix = _derive_prefix_from_namespace(ns_uri)
            import re as _re_xml
            rows = []
            raw_rels: List[Dict[str, Any]] = []
            for elem in root.iter():
                if not isinstance(elem.tag, str):
                    continue
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                attrs = dict(elem.attrib)
                if not attrs and not elem.text:
                    continue
                row = {'element_type': tag}
                row.update(attrs)
                if elem.text and elem.text.strip():
                    row['value'] = elem.text.strip()
                rows.append(row)
                # Extract *Ref/*Refs attributes as relationships
                from_id = attrs.get('id')
                if from_id:
                    for attr_key, attr_val in attrs.items():
                        if (attr_key.endswith('Ref') or attr_key.endswith('Refs')) and attr_val:
                            rel_type = _re_xml.sub(r'([A-Z])', r'_\1', attr_key).upper().strip('_')
                            for token in str(attr_val).split():
                                to_id = token.lstrip('#')
                                if to_id and to_id != from_id:
                                    raw_rels.append({'from_props': {'id': from_id},
                                                     'to_props': {'id': to_id},
                                                     'type': rel_type})
            columns = list(rows[0].keys()) if rows else []
            stats = {
                'format': 'PLMXML',
                'namespace': ns_uri,
                'ontology_prefix': ns_prefix,
                'ontology_name': ns_uri.rstrip('/').split('/')[-1] or ns_prefix,
                'row_count': len(rows),
                'column_count': len(columns),
                'columns': columns,
                '_xmi_relationships': raw_rels,
            }
            return rows, stats
        except Exception as e:
            logging.error(f"PLMXML parse error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def _parse_threedxml(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse 3DXML content using the dedicated extractor and flatten it for import."""
        import tempfile
        from pathlib import Path as _Path

        try:
            from .threedxml_ontology_extractor import ThreeDXMLExtractor
        except Exception:
            from backend.Services.threedxml_ontology_extractor import ThreeDXMLExtractor

        try:
            with tempfile.TemporaryDirectory(prefix='threedxml_import_') as temp_dir:
                temp_path = _Path(temp_dir) / 'import.3dxml'
                temp_path.write_bytes(file_content)
                extractor = ThreeDXMLExtractor(temp_dir)
                summary = extractor.extract()

            rows: List[Dict[str, Any]] = []
            rels: List[Dict[str, Any]] = []
            columns = set()

            for entity_name, entity in (extractor.entities or {}).items():
                row: Dict[str, Any] = {
                    'element_type': getattr(entity, 'entity_type', '3DXML'),
                    'id': entity_name,
                    'import_row_key': entity_name,
                    'name': getattr(entity, 'name', entity_name),
                    'label': getattr(entity, 'name', entity_name),
                    'namespace': getattr(entity, 'namespace', ''),
                    'description': getattr(entity, 'description', ''),
                }
                metadata = getattr(entity, 'metadata', {}) or {}
                for key, value in metadata.items():
                    if value in (None, '', [], {}):
                        continue
                    row[f'metadata_{key}'] = value
                attributes = getattr(entity, 'attributes', {}) or {}
                for attr_name, attr in attributes.items():
                    attr_value = getattr(attr, 'description', None)
                    if attr_value in (None, ''):
                        attr_value = getattr(attr, 'name', None)
                    if attr_name and attr_value not in (None, ''):
                        row[str(attr_name)] = attr_value
                rows.append(row)
                columns.update(row.keys())

            for rel in getattr(extractor, 'relationships', []) or []:
                source = getattr(rel, 'source', '')
                target = getattr(rel, 'target', '')
                if not source or not target or source == target:
                    continue
                rel_payload = {
                    'from_props': {'id': source},
                    'to_props': {'id': target},
                    'type': str(getattr(rel, 'relation_type', 'RELATED_TO') or 'RELATED_TO'),
                }
                rel_metadata = {
                    'source_entity_type': getattr(rel, 'source_type', ''),
                    'target_entity_type': getattr(rel, 'target_type', ''),
                    'cardinality': getattr(rel, 'cardinality', ''),
                    'description': getattr(rel, 'description', ''),
                }
                rel_payload['properties'] = {
                    key: value for key, value in rel_metadata.items() if value not in (None, '', [], {})
                }
                rels.append(rel_payload)

            stats = {
                'format': '3DXML',
                'row_count': len(rows),
                'column_count': len(columns),
                'columns': list(columns),
                'entity_count': len(getattr(extractor, 'entities', {}) or {}),
                'relationship_count': len(getattr(extractor, 'relationships', []) or []),
                'entity_types': sorted(list(getattr(extractor, 'entity_types', set()) or [])),
                '_xmi_relationships': rels,
                'root_element': '3DXML',
            }
            if isinstance(summary, dict):
                summary_meta = summary.get('metadata') or {}
                summary_stats = summary_meta.get('stats') or {}
                if isinstance(summary_stats, dict):
                    for key in ('source_format', 'source_path'):
                        if key in summary_meta and key not in stats:
                            stats[key] = summary_meta[key]
                    for key, value in summary_stats.items():
                        if key not in stats and value not in (None, '', [], {}):
                            stats[key] = value
            return rows, stats
        except Exception as e:
            logging.error(f"3DXML parse error: {e}")
            return FileParser._parse_xml(file_content)

    @staticmethod
    def _parse_step(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse STEP/STP file using the dedicated step_parser module (ISO 10303 Part 21/28).

        Uses the robust character-level parser from step_parser.py which correctly
        handles quoted semicolons, Part28 XML, and AP242 entity normalization.
        """
        import tempfile
        from pathlib import Path as _Path
        try:
            from .step_parser import iter_part21_entities, parse_step_metadata, \
                extract_step_strings, _AP242_NAMED_ENTITIES

            # G-A: detect STPX (Part 28 XML) content to use correct temp file suffix.
            # detect_step_format() relies on the suffix, so write to .stpx when content is XML.
            _head = file_content[:128].lstrip()
            _is_xml = _head.startswith(b'<?xml') or b'iso_10303_28' in file_content[:4096].lower()
            suffix = '.stpx' if _is_xml else '.stp'

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_content)
                tmp_path = _Path(tmp.name)

            try:
                file_meta = parse_step_metadata(tmp_path)
                schema = file_meta.file_schema or 'UNKNOWN'

                rows: List[Dict[str, Any]] = []
                type_counts: Dict[str, int] = {}
                ref_map: Dict[int, List[int]] = {}  # step_id -> [ref_step_ids]

                for entity in iter_part21_entities(tmp_path):
                    args_preview = (
                        entity.raw_args[:200] + '...'
                        if len(entity.raw_args) > 200
                        else entity.raw_args
                    )
                    row: Dict[str, Any] = {
                        'id': f'#{entity.step_id}',
                        'entity_type': entity.entity_type,
                        'args': args_preview,
                        'ref_ids': list(entity.ref_ids),
                    }
                    if getattr(entity, 'compound_entity_types', None):
                        row['compound_entity_types'] = list(entity.compound_entity_types)
                    if entity.source_identifier:
                        row['source_identifier'] = entity.source_identifier
                        row['source_identifier_kind'] = entity.source_identifier_kind
                    if entity.text_value:
                        row['text_value'] = entity.text_value
                    if entity.parent_step_id is not None:
                        row['parent_step_id'] = f'#{entity.parent_step_id}'
                    if entity.unresolved_refs:
                        row['unresolved_refs'] = list(entity.unresolved_refs)
                    if entity.attributes:
                        reserved_keys = {
                            'id', 'entity_type', 'args', 'ref_ids', 'import_row_key',
                            'source_identifier', 'source_identifier_kind',
                            'text_value', 'parent_step_id', 'unresolved_refs',
                            'compound_entity_types',
                        }
                        for attr_key, attr_value in entity.attributes.items():
                            safe_key = str(attr_key).strip()
                            if not safe_key:
                                continue
                            target_key = f'xml_{safe_key}' if safe_key in reserved_keys else safe_key
                            row[target_key] = attr_value
                    # G-B: extract name/description for AP242 semantic entity types.
                    # Canonical pattern from requirements/src/engines/ap242_bom_mapper.py.
                    if entity.entity_type in _AP242_NAMED_ENTITIES:
                        strings = extract_step_strings(entity.raw_args)
                        row['external_id'] = strings[0] if strings else ''
                        row['name'] = strings[1] if len(strings) > 1 else ''
                        row['description'] = strings[2] if len(strings) > 2 else ''
                    rows.append(row)
                    type_counts[entity.entity_type] = type_counts.get(entity.entity_type, 0) + 1
                    if entity.ref_ids:
                        ref_map[entity.step_id] = entity.ref_ids

                id_seen: Dict[str, int] = {}
                source_identifier_seen: Dict[str, int] = {}
                duplicate_id_count = 0
                unresolved_reference_total = 0
                for row in rows:
                    source_id = str(row.get('id') or '')
                    id_seen[source_id] = id_seen.get(source_id, 0) + 1
                    occurrence = id_seen[source_id]
                    if occurrence > 1:
                        duplicate_id_count += 1
                    row['import_row_key'] = source_id if occurrence == 1 else f'{source_id}::{occurrence}'
                    unresolved_reference_total += len(row.get('unresolved_refs') or [])
                    source_identifier = str(row.get('source_identifier') or '')
                    if source_identifier:
                        source_identifier_seen[source_identifier] = source_identifier_seen.get(source_identifier, 0) + 1

                duplicate_source_identifier_count = sum(
                    1 for count in source_identifier_seen.values() if count > 1
                )

                all_columns = sorted({key for row in rows for key in row.keys()})
                stats = {
                    'format': 'STEP',
                    'schema': schema,
                    'namespace': file_meta.namespace,
                    'schema_location': file_meta.schema_location,
                    'schema_version': file_meta.schema_version,
                    'row_count': len(rows),
                    'column_count': len(all_columns) if rows else 4,
                    'columns': all_columns if rows else ['import_row_key', 'id', 'entity_type', 'args'],
                    'entity_types': type_counts,
                    'duplicate_source_id_count': duplicate_id_count,
                    'duplicate_source_identifier_count': duplicate_source_identifier_count,
                    'unresolved_reference_count': unresolved_reference_total,
                    'elements_parsed': len(rows),
                    '_step_ref_map': ref_map,
                }
                return rows, stats
            finally:
                tmp_path.unlink(missing_ok=True)

        except ImportError:
            logging.warning("step_parser not available — falling back to regex parser")
        except Exception as e:
            logging.error(f"STEP parse error (dedicated parser): {e}")
            return [], {'error': str(e)}

        # Fallback: legacy regex parser (handles simple files)
        import re
        try:
            content = file_content.decode('utf-8', errors='replace')
            upper = content.upper()
            data_start = upper.find('DATA;')
            data_end = upper.rfind('ENDSEC;')
            data_section = content[data_start + 5:data_end] if data_start != -1 and data_end != -1 else content

            schema_match = re.search(r"FILE_SCHEMA\(\s*\(\s*'([^']+)'", content, re.IGNORECASE)
            schema = schema_match.group(1) if schema_match else 'UNKNOWN'

            entity_pattern = re.compile(
                r'#(\d+)\s*=\s*([A-Z_][A-Z0-9_]*)\s*\(([^;]*)\)\s*;',
                re.MULTILINE | re.DOTALL,
            )
            rows = []
            type_counts: Dict[str, int] = {}
            id_seen: Dict[str, int] = {}
            duplicate_id_count = 0
            for match in entity_pattern.finditer(data_section):
                eid, etype, args = match.group(1), match.group(2), match.group(3).strip()
                args_preview = args[:200] + '...' if len(args) > 200 else args
                source_id = f'#{eid}'
                id_seen[source_id] = id_seen.get(source_id, 0) + 1
                occurrence = id_seen[source_id]
                if occurrence > 1:
                    duplicate_id_count += 1
                rows.append({
                    'import_row_key': source_id if occurrence == 1 else f'{source_id}::{occurrence}',
                    'id': source_id,
                    'entity_type': etype,
                    'args': args_preview,
                    'ref_ids': [],
                })
                type_counts[etype] = type_counts.get(etype, 0) + 1

            stats = {
                'format': 'STEP',
                'schema': schema,
                'row_count': len(rows),
                'column_count': 4,
                'columns': ['import_row_key', 'id', 'entity_type', 'args'],
                'entity_types': type_counts,
                'duplicate_source_id_count': duplicate_id_count,
            }
            return rows, stats
        except Exception as e:
            logging.error(f"STEP parse error (fallback): {e}")
            return [], {'error': str(e)}


# ========== Data Transformer ==========

class DataTransformer:
    """Schema detection and Cypher query generation for import pipeline"""

    @staticmethod
    def auto_detect_schema(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Auto-detect graph schema from parsed rows.

        Supports heterogeneous row sets (e.g. PLMXML Parts + Requirements + Processes)
        by detecting an 'element_type' discriminator column and creating one node
        definition per distinct type.  Falls back to a single-label schema otherwise.

        Returns a schema dict with 'nodes' and 'indexes' suitable for
        Neo4j ingestion via commit_import.
        """
        if not rows:
            return {'nodes': [], 'indexes': []}

        # ── Multi-label detection (PLMXML / heterogeneous rows) ───────────────
        element_types = list({
            str(row.get('element_type', '')).replace(' ', '_').replace(':', '_')
            for row in rows if row.get('element_type')
        })
        _SKIP_MERGE = frozenset({'element_type', 'type', 'value', 'ontology_prefix', 'source_ontology'})
        if len(element_types) > 1:
            nodes = []
            indexes = []
            for etype in element_types:
                type_rows = [r for r in rows
                             if str(r.get('element_type', '')).replace(' ', '_') == etype]
                if not type_rows:
                    continue
                type_cols = sorted({k for r in type_rows for k in r.keys()})
                merge_key = next(
                    (c for c in ('import_row_key', 'id', 'uuid', 'key', 'name') if c in type_cols),
                    next((c for c in type_cols if c not in _SKIP_MERGE), type_cols[0]),
                )
                nodes.append({
                    'label': etype,
                    'mergeKeys': [merge_key],
                    'properties': type_cols,
                    '_filter_key': 'element_type',
                    '_filter_val': etype,
                })
                indexes.extend(FileFormatDetector._recommended_indexes_for_label(etype, merge_key, type_cols))
            return {'nodes': nodes, 'indexes': indexes}

        # ── STEP/AP242 entity typing ─────────────────────────────────────────
        # STEP imports expose parser-normalized AP242 entity_type values such as
        # PRODUCT, PRODUCT_DEFINITION, and SHAPE_REPRESENTATION. Use those as
        # graph labels so visualizations do not collapse instance nodes into a
        # generic fallback label.
        entity_type_vals = sorted({
            str(row.get('entity_type', '')).replace(' ', '_').replace(':', '_')
            for row in rows if row.get('entity_type')
        })
        if entity_type_vals:
            nodes = []
            indexes = []
            for entity_type in entity_type_vals:
                type_rows = [
                    r for r in rows
                    if str(r.get('entity_type', '')).replace(' ', '_').replace(':', '_') == entity_type
                ]
                if not type_rows:
                    continue
                type_cols = sorted({k for r in type_rows for k in r.keys()})
                merge_key = next(
                    (c for c in ('import_row_key', 'id', 'uuid', 'key') if c in type_cols),
                    type_cols[0],
                )
                nodes.append({
                    'label': entity_type,
                    'mergeKeys': [merge_key],
                    'properties': type_cols,
                    '_filter_key': 'entity_type',
                    '_filter_val': entity_type,
                })
                indexes.extend(FileFormatDetector._recommended_indexes_for_label(entity_type, merge_key, type_cols))
            if nodes:
                return {'nodes': nodes, 'indexes': indexes}

        # ── XMI-style multi-label detection (type column as discriminator) ────
        # Triggered when 'element_type' column is absent but 'type' column holds
        # heterogeneous values like 'uml:Class', 'uml:Property', 'sysml:Block', etc.
        type_discriminator_vals = list({
            str(row.get('type', '')).replace(' ', '_').replace(':', '_')
            for row in rows if row.get('type')
        })
        if len(type_discriminator_vals) > 1:
            nodes = []
            indexes = []
            for tval in type_discriminator_vals:
                type_rows = [
                    r for r in rows
                    if str(r.get('type', '')).replace(' ', '_').replace(':', '_') == tval
                ]
                if not type_rows:
                    continue
                type_cols = sorted({k for r in type_rows for k in r.keys()})
                _skip2 = frozenset({'element_type', 'type', 'value', 'ontology_prefix', 'source_ontology'})
                merge_key = next(
                    (c for c in ('id', 'uuid', 'key', 'name') if c in type_cols),
                    next((c for c in type_cols if c not in _skip2), type_cols[0]),
                )
                nodes.append({
                    'label': tval,
                    'mergeKeys': [merge_key],
                    'properties': type_cols,
                    '_filter_key': 'type',
                    '_filter_val': tval,
                })
                indexes.extend(FileFormatDetector._recommended_indexes_for_label(tval, merge_key, type_cols))
            return {'nodes': nodes, 'indexes': indexes}

        # ── Single-label schema (original logic, column union fix applied) ────
        columns = sorted({k for row in rows for k in row.keys()})
        # Prefer unique identifier columns; 'name' is often non-unique or empty
        merge_key = next((c for c in ('import_row_key', 'id', 'uuid', 'key', 'name') if c in columns), columns[0])
        default_label = (
            element_types[0] if element_types
            else str(rows[0].get('entity_type', '')).replace(' ', '_').replace(':', '_') if rows[0].get('entity_type')
            else str(rows[0].get('type', 'ImportedRecord')).replace(' ', '_').replace(':', '_')
        )
        nodes = [{'label': default_label, 'mergeKeys': [merge_key], 'properties': columns}]
        indexes = FileFormatDetector._recommended_indexes_for_label(default_label, merge_key, columns)
        return {'nodes': nodes, 'indexes': indexes}

    @staticmethod
    def transform_to_nodes(
        rows: List[Dict[str, Any]],
        node_label: str,
        merge_keys: Optional[List[str]] = None,
    ) -> Tuple[List[str], Dict[str, Any]]:
        """Generate Cypher MERGE queries for node creation."""
        return FileFormatDetector.transform_to_nodes(rows, node_label, merge_keys)

    @staticmethod
    def create_indexes(index_defs: List[Dict[str, Any]]) -> List[str]:
        """Generate index creation queries."""
        return FileFormatDetector.create_indexes(index_defs)


# ========== Neo4j Integration ==========

class Neo4jImporter:
    """Handles Neo4j ingestion"""

    @staticmethod
    def validate_before_ingest(rows: List[Dict[str, Any]], schema: Dict[str, Any]) -> Tuple[bool, str]:
        """
        🔒 DATA LOSS PREVENTION: Validate data before Neo4j ingestion
        
        Checks:
        - Data not empty
        - Required fields present
        - No malformed entries
        - No duplicate keys in merge strategy
        
        Returns: (is_valid, error_message)
        """
        if not rows:
            return False, "No data rows to ingest"
        
        if not schema or not schema.get('nodes'):
            return False, "No schema defined for ingestion"
        
        # Validate each row has required keys
        for node_def in schema.get('nodes', []):
            merge_keys = node_def.get('mergeKeys', [])
            # For multi-label schemas, only validate the filtered subset of rows
            filter_key = node_def.get('_filter_key')
            filter_val = node_def.get('_filter_val')
            if filter_key and filter_val:
                check_rows = [r for r in rows
                              if str(r.get(filter_key, '')).replace(' ', '_').replace(':', '_') == filter_val]
            else:
                check_rows = rows

            missing_key_count = 0
            missing_key_examples = []
            for row_idx, row in enumerate(check_rows):
                if not row:
                    return False, f"Row {row_idx} is empty"

                for key in merge_keys:
                    if key not in row or row[key] is None:
                        missing_key_count += 1
                        if len(missing_key_examples) < 5:
                            missing_key_examples.append(str(row.get('id') or row.get('name') or f'row-{row_idx}'))
            # Fail only if ALL rows are missing the merge key (schema mismatch),
            # not just some — partial rows are filtered out at write time.
            if missing_key_count == len(check_rows) and check_rows:
                return False, (
                    f"All {len(check_rows)} rows missing merge key '{merge_keys[0]}'. "
                    "Schema may be incorrect."
                )
            if missing_key_count > 0:
                return False, (
                    f"{missing_key_count} rows are missing merge key '{merge_keys[0]}'. "
                    f"Examples: {', '.join(missing_key_examples)}"
                )
        
        return True, ""

    @staticmethod
    def check_duplicate_entries(rows: List[Dict[str, Any]], schema: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        🔒 DATA LOSS PREVENTION: Detect duplicate entries
        
        Returns: (duplicate_count, duplicate_ids)
        """
        duplicates = []
        
        for node_def in schema.get('nodes', []):
            merge_keys = node_def.get('mergeKeys', [])
            filter_key = node_def.get('_filter_key')
            filter_val = node_def.get('_filter_val')
            if filter_key and filter_val:
                check_rows = [
                    r for r in rows
                    if str(r.get(filter_key, '')).replace(' ', '_').replace(':', '_') == filter_val
                ]
            else:
                check_rows = rows
            seen_keys = {}
            
            for row in check_rows:
                if not merge_keys:
                    continue
                
                # Create composite key from merge keys
                key_values = tuple(row.get(k) for k in merge_keys)
                key_str = '|'.join(str(v) for v in key_values)
                
                if key_str in seen_keys:
                    duplicates.append(key_str)
                else:
                    seen_keys[key_str] = True
        
        return len(duplicates), duplicates

    @staticmethod
    def execute_cypher(
        queries: List[str],
        rows: Optional[List[Dict[str, Any]]] = None,
        batch_size: Optional[int] = None,
        batch_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute Cypher queries with error tracking"""
        try:
            from core.graph import graph as _graph  # lazy import — avoids boot-time connection errors  # noqa: F401
            from core.graph import query_with_timeout as _query_with_timeout
        except ModuleNotFoundError:
            from ..core.graph import query_with_timeout as _query_with_timeout

        stats = {
            'queries_executed': 0,
            'nodes_created': 0,
            'relationships_created': 0,
            'matched_rows': 0,
            'errors': []
        }

        for query in queries:
            if not query or not query.strip():
                continue

            try:
                if rows and 'UNWIND $rows' in query:
                    _BATCH = max(100, int(batch_size or IMPORT_WRITE_BATCH_SIZE))
                    _total_batches = max(1, (len(rows) + _BATCH - 1) // _BATCH)
                    for _i in range(0, len(rows), _BATCH):
                        _batch = rows[_i:_i + _BATCH]
                        result = _query_with_timeout(query, {'rows': _batch}, timeout=IMPORT_COMMIT_QUERY_TIMEOUT)
                        stats['queries_executed'] += 1
                        if isinstance(result, list):
                            stats['nodes_created'] += len(result)
                            for record in result:
                                if isinstance(record, dict) and record.get('matched_rows') is not None:
                                    try:
                                        stats['matched_rows'] += int(record.get('matched_rows') or 0)
                                    except (TypeError, ValueError):
                                        pass
                        if callable(batch_callback):
                            batch_callback({
                                'batch_index': (_i // _BATCH) + 1,
                                'batch_size': len(_batch),
                                'total_batches': _total_batches,
                                'rows_processed': min(_i + len(_batch), len(rows)),
                                'rows_total': len(rows),
                            })
                else:
                    result = _query_with_timeout(query, timeout=IMPORT_COMMIT_QUERY_TIMEOUT)
                    stats['queries_executed'] += 1
                    if isinstance(result, list):
                        stats['nodes_created'] += len(result)
                        for record in result:
                            if isinstance(record, dict) and record.get('matched_rows') is not None:
                                try:
                                    stats['matched_rows'] += int(record.get('matched_rows') or 0)
                                except (TypeError, ValueError):
                                    pass
            except Exception as e:
                logger.error(f"Query execution error: {str(e)}", exc_info=True)
                stats['errors'].append(str(e))

        return stats

    @staticmethod
    def validate_indexes_and_constraints(
        schema: Dict[str, Any],
        extra_indexes: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        try:
            from core.graph import query_with_timeout as _query_with_timeout
        except ModuleNotFoundError:
            from ..core.graph import query_with_timeout as _query_with_timeout

        existing_indexes = _query_with_timeout(
            "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state "
            "RETURN name, type, entityType, labelsOrTypes, properties, state"
        ) or []
        existing_constraints = _query_with_timeout(
            "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
            "RETURN name, type, entityType, labelsOrTypes, properties"
        ) or []

        existing_signatures = set()
        for record in existing_indexes:
            if str(record.get('entityType', '')).upper() != 'NODE':
                continue
            labels = tuple(sorted(record.get('labelsOrTypes') or []))
            properties = tuple(record.get('properties') or [])
            idx_type = str(record.get('type', 'RANGE')).upper()
            existing_signatures.add((idx_type, labels, properties))

        required_indexes: List[Dict[str, Any]] = list(schema.get('indexes', []))
        if extra_indexes:
            required_indexes.extend(extra_indexes)

        seen_required = set()
        deduped_required: List[Dict[str, Any]] = []
        for idx in required_indexes:
            idx_type = str(idx.get('type', 'range')).upper()
            label = str(idx.get('label', ''))
            properties = tuple(str(p) for p in (idx.get('properties') or []) if p)
            signature = (idx_type, (label,), properties)
            if not label or not properties or signature in seen_required:
                continue
            seen_required.add(signature)
            deduped_required.append(idx)

        missing_indexes = [
            idx for idx in deduped_required
            if (str(idx.get('type', 'range')).upper(), (str(idx.get('label', '')),), tuple(str(p) for p in idx.get('properties', [])))
            not in existing_signatures
        ]

        return {
            'existing_index_count': len(existing_indexes),
            'existing_constraint_count': len(existing_constraints),
            'required_index_count': len(deduped_required),
            'missing_index_count': len(missing_indexes),
            'missing_indexes': missing_indexes,
        }


# ========== Main Service ==========

# Global task tracking
# ⚠️  C6: import_tasks is an in-process dict — safe for asyncio (single-threaded) and
# single-worker uvicorn deployments only. Running uvicorn with --workers > 1 (multi-process)
# will cause 404 errors on status polls because each worker has its own independent copy.
# Mitigation: always start with --reload (enforces one worker) or explicitly --workers 1.
import_tasks: Dict[str, Dict[str, Any]] = {}


class UnifiedDataImportService:
    """Main service for unified data import"""

    UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
    TASK_STORE_DIR = UPLOAD_DIR / ".import_tasks"

    @classmethod
    def initialize(cls):
        """Initialize upload directory"""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _update_commit_state(
        cls,
        task_id: str,
        task: Dict[str, Any],
        *,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        phase: Optional[str] = None,
        batch_progress: Optional[Dict[str, Any]] = None,
        commit_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        if progress is not None:
            task['progress'] = max(0, min(100, int(progress)))
        if message is not None:
            task['message'] = message
        if phase is not None:
            task['commit_phase'] = phase
        if batch_progress is not None:
            task['batch_progress'] = batch_progress
        if commit_metrics is not None:
            task['commit_metrics'] = commit_metrics
        cls._persist_task(task_id)

    @classmethod
    def _task_snapshot_path(cls, task_id: str) -> Path:
        return cls.TASK_STORE_DIR / f"{task_id}.json"

    @classmethod
    def _refresh_artifact_manifest(cls, task_id: str, task_info: Dict[str, Any]) -> None:
        try:
            task_info['artifact_manifest'] = WorkflowArtifactService.get_manifest(task_id)
        except Exception as exc:
            logger.warning(f"Task {task_id}: artifact manifest refresh failed: {exc}")

    @classmethod
    def _write_artifact(cls, task_id: str, task_info: Dict[str, Any], method: str, *args, **kwargs) -> None:
        try:
            writer = getattr(WorkflowArtifactService, method)
            writer(task_id, *args, **kwargs)
            cls._refresh_artifact_manifest(task_id, task_info)
        except Exception as exc:
            logger.warning(f"Task {task_id}: artifact write failed ({method}): {exc}")

    @classmethod
    def _build_persistable_task(cls, task: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize task fields needed for status/preview and cross-worker commit restore."""
        persistable = dict(task)
        # Raw file bytes are not JSON-serializable and can be large; omit from snapshot.
        persistable.pop('file_content', None)
        return persistable

    @classmethod
    def _persist_task(cls, task_id: str) -> None:
        task = import_tasks.get(task_id)
        if not task:
            return
        try:
            snapshot = cls._build_persistable_task(task)
            # Add writer metadata to help diagnose race/overwrite issues
            ver = int(snapshot.get('_persist_version', 0) or 0) + 1
            snapshot['_persisted_by'] = {
                'pid': os.getpid(),
                'time': datetime.now().isoformat(),
                'version': ver,
            }
            snapshot['_persist_version'] = ver
            # Diagnostic: log which keys are being persisted and parsed_rows size
            try:
                keys = list(snapshot.keys())
                parsed_rows_info = None
                if 'parsed_rows' in snapshot:
                    try:
                        parsed_rows_info = len(snapshot.get('parsed_rows') or [])
                    except Exception:
                        parsed_rows_info = 'unlenable'
                # Surface this at INFO level so it's always visible in dev logs
                logger.info(f"Persisting snapshot for {task_id} keys={keys} parsed_rows={parsed_rows_info}")
                # Note: debug copy will be written after path is resolved below
            except Exception:
                # swallow logging diagnostics to avoid breaking persist
                pass
            path = cls._task_snapshot_path(task_id)
            # Ensure directory exists before writing
            path.parent.mkdir(parents=True, exist_ok=True)
            # Acquire a lightweight per-task lock to avoid overlapping persists
            lock_path = path.with_suffix('.lock')
            lock_acquired = False
            try:
                attempts = 0
                while attempts < 10:
                    try:
                        # Use exclusive create to acquire lock; will fail if exists
                        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        os.close(fd)
                        lock_acquired = True
                        break
                    except FileExistsError:
                        attempts += 1
                        time.sleep(0.02)
                if not lock_acquired:
                    # If we couldn't acquire lock, proceed but log a warning
                    logger.warning(f"Task {task_id}: couldn't acquire persist lock after {attempts} attempts")
                # Proceed with writing while holding the lock (if acquired)
                
                # If parsed_rows present, write them to a separate file atomically to
                # avoid large-list overwrite races and to make persistence robust.
                parsed_rows = None
                try:
                    if 'parsed_rows' in snapshot:
                        parsed_rows = snapshot.pop('parsed_rows')
                        parsed_path = path.with_name(path.name + ".parsed_rows.json")
                        parsed_tmp = parsed_path.with_suffix('.json.tmp')
                        # Write parsed rows using default=str to tolerate odd values
                        parsed_tmp.write_text(json.dumps(parsed_rows, ensure_ascii=True, default=str), encoding='utf-8')
                        try:
                            logger.info(f"Task {task_id}: about to atomically replace parsed_rows tmp -> {parsed_path.name} (pid={os.getpid()} v={ver})")
                            parsed_tmp.replace(parsed_path)
                            logger.info(f"Task {task_id}: parsed_rows replace completed -> {parsed_path.name} (size={parsed_path.stat().st_size} bytes)")
                        except Exception as e_replace:
                            logger.exception(f"Task {task_id}: failed atomic replace for parsed_rows: {e_replace}")
                        # add pointer to snapshot for restore
                        snapshot['_parsed_rows_file'] = parsed_path.name
                        # Persist pointer into the in-memory task as well so concurrent
                        # persists will include the pointer and not overwrite it.
                        try:
                            task['_parsed_rows_file'] = parsed_path.name
                        except Exception:
                            pass
                except Exception:
                    logger.exception('Failed to persist parsed_rows separately')

                # If a SHACL report is present in the snapshot (from OWL generation/validation),
                # persist it separately to avoid bloating the snapshot and to make reports
                # available for downstream inspection.
                try:
                    if 'shacl_report' in snapshot:
                        shacl_report = snapshot.pop('shacl_report')
                        shacl_path = path.with_name(path.name + ".shacl_report.json")
                        shacl_tmp = shacl_path.with_suffix('.json.tmp')
                        shacl_tmp.write_text(json.dumps(shacl_report, ensure_ascii=True, default=str), encoding='utf-8')
                        try:
                            logger.info(f"Task {task_id}: about to atomically replace shacl tmp -> {shacl_path.name} (pid={os.getpid()} v={ver})")
                            shacl_tmp.replace(shacl_path)
                            logger.info(f"Task {task_id}: shacl replace completed -> {shacl_path.name} (size={shacl_path.stat().st_size} bytes)")
                        except Exception as e_sh:
                            logger.exception(f"Task {task_id}: failed atomic replace for shacl_report: {e_sh}")
                        # add pointer to snapshot and in-memory task
                        snapshot['_shacl_file'] = shacl_path.name
                        try:
                            task['_shacl_file'] = shacl_path.name
                        except Exception:
                            pass
                except Exception:
                    logger.exception('Failed to persist shacl_report separately')
                # Ensure any shacl_report pointer present in-memory is reflected
                try:
                    if '_shacl_file' not in snapshot and task.get('_shacl_file'):
                        snapshot['_shacl_file'] = task.get('_shacl_file')
                except Exception:
                    pass

                # Ensure any parsed_rows pointer present in-memory is reflected
                # in the snapshot before writing to avoid losing the pointer when
                # another writer started earlier.
                try:
                    if '_parsed_rows_file' not in snapshot and task.get('_parsed_rows_file'):
                        snapshot['_parsed_rows_file'] = task.get('_parsed_rows_file')
                except Exception:
                    pass

                # Also write a per-write debug copy to help diagnose overwrite/race issues
                try:
                    debug_path = path.with_name(path.name + f".writer_{os.getpid()}_v{ver}.json")
                    debug_path.write_text(json.dumps(snapshot, ensure_ascii=True, default=str), encoding='utf-8')
                except Exception:
                    logger.debug("Failed to write debug snapshot copy", exc_info=True)
                tmp_path = path.with_suffix('.json.tmp')
                # Use default=str to tolerate any non-serializable values (best-effort)
                tmp_path.write_text(json.dumps(snapshot, ensure_ascii=True, default=str), encoding='utf-8')
                try:
                    logger.info(f"Task {task_id}: about to atomically replace snapshot tmp -> {path.name} (pid={os.getpid()} v={ver})")
                    tmp_path.replace(path)
                    logger.info(f"Task {task_id}: snapshot replace completed -> {path.name} (size={path.stat().st_size} bytes)")
                except Exception as e_replace:
                    logger.exception(f"Task {task_id}: failed atomic replace for snapshot: {e_replace}")
            finally:
                try:
                    if lock_acquired and lock_path.exists():
                        lock_path.unlink()
                except Exception:
                    logger.debug("Failed to remove persist lock", exc_info=True)
            
        except Exception as exc:
            logger.exception(f"Task {task_id}: failed to persist snapshot: {exc}")

    @classmethod
    def _restore_task(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Restore task snapshot when current worker does not have in-memory state."""
        if task_id in import_tasks:
            return import_tasks[task_id]

        path = cls._task_snapshot_path(task_id)
        if not path.exists():
            return None
        try:
            task = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(task, dict) and task.get('task_id') == task_id:
                # Restore into unified service in-memory store
                import_tasks[task_id] = task
                # Also attempt to synchronize into the legacy DataImportService import_tasks
                try:
                    from .data_import_service import import_tasks as legacy_tasks
                    legacy_tasks[task_id] = task
                except Exception:
                    # If the legacy module isn't available, skip silently
                    pass
                return task
        except Exception as exc:
            logger.warning(f"Task {task_id}: failed to restore snapshot: {exc}")
        return None

    @classmethod
    def _prune_tasks(cls, max_tasks: int = 300) -> None:
        """Keep in-memory task state bounded to avoid unbounded growth."""
        if len(import_tasks) <= max_tasks:
            return
        terminal = [
            (tid, t) for tid, t in import_tasks.items()
            if t.get('status') in (
                ImportStatus.COMPLETED.value,
                ImportStatus.FAILED.value,
                ImportStatus.CANCELLED.value,
            )
        ]
        terminal.sort(key=lambda x: x[1].get('completed_at') or x[1].get('started_at') or '')

        overflow = len(import_tasks) - max_tasks
        for tid, _ in terminal[:overflow]:
            import_tasks.pop(tid, None)

    @classmethod
    async def start_import(
        cls,
        file_content: bytes,
        filename: str,
        ontology_mapping: str = '',
        parse_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start an import task
        Returns task_id
        """
        parse_options = parse_options or {}

        # Validate file type
        file_type = FileFormatDetector.detect(filename)
        if not file_type:
            raise ValueError(f"Unsupported file type. Supported: {', '.join(FileFormatDetector.get_supported_formats())}")
        if file_type == FileType.XML and _detect_xml_family(file_content) == 'archimate':
            file_type = FileType.ARCHIMATE

        # Create task
        task_id = str(uuid.uuid4())
        cls._prune_tasks()
        keep_file_content = file_type in {
            FileType.PLMXML,
            FileType.STEP,
            FileType.EXPRESS,
            FileType.XMI,
            FileType.XSD,
        }
        # Normalize mapping and seed task-level ontology metadata so downstream
        # stages (preview/commit) and Neo4j writes can rely on a stable prefix/name.
        mapping_value = (ontology_mapping or '').strip()
        normalized_mapping = mapping_value if mapping_value else 'auto'
        seeded_stats = {'ontology_mapping': normalized_mapping}
        if parse_options.get('metadata_exclusion_tags'):
            seeded_stats['metadata_exclusion_tags'] = list(parse_options['metadata_exclusion_tags'])
        # If a concrete mapping was provided (not 'auto'), expose it as
        # ontology_prefix and ontology_name so later commit logic can pick it up.
        if normalized_mapping != 'auto':
            seeded_stats['ontology_prefix'] = normalized_mapping
            seeded_stats['ontology_name'] = normalized_mapping

        task_info = {
            'task_id': task_id,
            'filename': filename,
            'file_type': file_type.value,
            'current_stage': ImportStage.UPLOAD.value,
            'progress': 10,
            'message': 'File uploaded, starting processing...',
            'status': ImportStatus.PROCESSING.value,
            'error': None,
            'preview_data': None,
            'stats': seeded_stats,
            'started_at': datetime.now().isoformat(),
            'completed_at': None,
            'result': None,
            'workflow_id': (
                'ontology.create' if file_type in {FileType.EXPRESS, FileType.XSD, FileType.ONTOLOGY}
                else 'architecture.archimate' if file_type == FileType.ARCHIMATE
                else 'instance.import'
            ),
            'artifact_manifest': None,
            'parse_options': parse_options,
            # Keep raw bytes only where downstream OWL generation may need them.
            'file_content': file_content if keep_file_content else None,
        }
        cls._write_artifact(
            task_id,
            task_info,
            "ensure_task",
            workflow_id=task_info['workflow_id'],
            filename=filename,
        )
        cls._write_artifact(
            task_id,
            task_info,
            "write_bytes",
            "source",
            filename,
            file_content,
            "source_file",
            {
                "file_type": file_type.value,
                "ontology_mapping": normalized_mapping,
                "parse_options": parse_options,
            },
        )
        # Register task immediately so the frontend can start polling
        import_tasks[task_id] = task_info
        cls._persist_task(task_id)

        # Parse file in a thread pool — FileParser.parse() is CPU-bound synchronous
        # work; running it directly in an async function blocks the event loop.
        import asyncio
        asyncio.get_event_loop().run_in_executor(
            None, cls._parse_and_preview, task_id, task_info, file_content, file_type
        )

        return task_id

    @classmethod
    def _parse_and_preview(
        cls,
        task_id: str,
        task_info: dict,
        file_content: bytes,
        file_type,
    ) -> None:
        """
        Synchronous parse/validate/transform/preview body — runs in a thread pool
        so start_import returns immediately and the upload endpoint is non-blocking.
        """
        # Parse file
        try:
            task_info['current_stage'] = ImportStage.PARSE.value
            task_info['progress'] = 25
            task_info['message'] = f'Parsing {file_type.value.upper()} file...'
            cls._persist_task(task_id)

            rows, stats = FileParser.parse(file_content, file_type, task_info.get('parse_options'))
            source_filename = task_info.get('filename', '') or ''
            if source_filename:
                for row in rows:
                    if isinstance(row, dict):
                        row.setdefault('source_filename', source_filename)

            # Extract relationship objects before merging stats (not JSON-serializable in bulk)
            xmi_rels = stats.pop('_xmi_relationships', [])
            step_ref_map = stats.pop('_step_ref_map', {})
            if xmi_rels:
                task_info['_xmi_relationships'] = xmi_rels
            if step_ref_map:
                task_info['_step_ref_map'] = step_ref_map

            task_info['parsed_rows'] = rows
            # Persist parsed rows immediately to survive worker/process restarts
            try:
                cls._persist_task(task_id)
                logger.info(f"Task {task_id}: persisted parsed_rows ({len(rows)} rows)")
            except Exception:
                logger.exception(f"Task {task_id}: failed to persist parsed_rows")
            # Merge stats — preserve ontology_mapping set during init
            task_info['stats'] = {**task_info.get('stats', {}), **stats}

            # ✅ C5: Surface parser-level errors immediately instead of generic message
            if stats.get('error') and not rows:
                raise ValueError(f"Parse error: {stats['error']}")
            
            # For EXPRESS and XSD files, attempt OWL/schema metadata generation
            # during the parse phase so preview/status reflects available OWL data.
            try:
                if file_type in (FileType.EXPRESS, FileType.XSD):
                    # EXPRESS parser may already include owl_ttl in stats (handled by parse_express)
                    if file_type == FileType.EXPRESS:
                        task_info['schema_metadata'] = stats
                        if 'owl_ttl' in stats:
                            task_info['owl_ttl'] = stats.pop('owl_ttl')
                    else:
                        # For XSD, run OWLGenerationService.generate_owl_from_xsd
                        try:
                            from .owl_generation_service import OWLGenerationService
                            # Use file_content bytes and filename to generate OWL/metadata
                            start_t = time.perf_counter()
                            owl_ttl, schema_meta = OWLGenerationService.generate_owl_from_xsd(
                                task_info.get('file_content', b''), task_info.get('filename', '')
                            )
                            dur = time.perf_counter() - start_t
                            logger.info(f"Task {task_id}: in-parse XSD->OWL generation took {dur:.2f}s")
                            if schema_meta:
                                # Merge schema metadata into task stats and set schema_metadata
                                task_info['schema_metadata'] = schema_meta
                                task_info['stats'] = {**task_info.get('stats', {}), **schema_meta}
                            if owl_ttl:
                                task_info['owl_ttl'] = owl_ttl
                        except Exception as owl_exc:
                            # Non-fatal: log and continue; OWL generation will still run at commit
                            logger.debug(f"Task {task_id}: deferred OWL generation skipped during parse: {owl_exc}")
            except Exception:
                # Protect parse from any OWL-gen regressions
                logger.exception(f"Task {task_id}: unexpected error during in-parse OWL generation")
            
            # Validate
            task_info['current_stage'] = ImportStage.VALIDATE.value
            task_info['progress'] = 40
            task_info['message'] = f'Validating data ({len(rows)} records)...'
            
            if not rows:
                raise ValueError("File is empty or contains no valid data")
            
            # Transform
            task_info['current_stage'] = ImportStage.TRANSFORM.value
            task_info['progress'] = 60
            task_info['message'] = 'Preparing data structure...'
            
            schema = DataTransformer.auto_detect_schema(rows)
            task_info['auto_schema'] = schema
            
            # Generate preview
            task_info['current_stage'] = ImportStage.PREVIEW.value
            task_info['progress'] = 75
            task_info['message'] = 'Ready for review'
            
            # L3: union of all column keys — handles heterogeneous rows (e.g. PLMXML
            # produces Parts, Requirements, Processes each with different key sets)
            all_col_keys: Dict[str, None] = {}
            for row in rows:
                all_col_keys.update({k: None for k in row.keys()})
            preview = {
                'row_count': len(rows),
                'columns': list(all_col_keys),
                'sample_rows': rows[:5],
                'auto_schema': schema,
            }
            task_info['preview_data'] = preview
            cls._write_artifact(
                task_id,
                task_info,
                "write_json",
                "preview",
                "preview.json",
                preview,
                "preview_data",
                {"row_count": len(rows)},
            )
            cls._write_artifact(
                task_id,
                task_info,
                "write_json",
                "manifests",
                "auto_schema.json",
                schema,
                "auto_schema",
            )
            if task_info.get('schema_metadata'):
                cls._write_artifact(
                    task_id,
                    task_info,
                    "write_json",
                    "ontology",
                    "schema_metadata.json",
                    task_info.get('schema_metadata'),
                    "schema_metadata",
                )
            if task_info.get('owl_ttl'):
                cls._write_artifact(
                    task_id,
                    task_info,
                    "write_text",
                    "ontology",
                    f"{Path(task_info.get('filename') or 'ontology').stem}.ttl",
                    task_info.get('owl_ttl'),
                    "ontology_ttl",
                    task_info.get('schema_metadata') or {},
                )
            cls._persist_task(task_id)
            
            logger.info(f"Task {task_id} ready for preview: {len(rows)} rows")

        except Exception as e:
            task_info['status'] = ImportStatus.FAILED.value
            task_info['current_stage'] = 'error'
            task_info['progress'] = 0
            task_info['error'] = str(e)
            task_info['completed_at'] = datetime.now().isoformat()
            cls._persist_task(task_id)
            logger.error(f"Task {task_id} failed during parsing: {str(e)}")
            # Do NOT re-raise — frontend polls /status to read the real error

    @classmethod
    def get_status(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        if task_id not in import_tasks:
            restored = cls._restore_task(task_id)
            if not restored:
                return None
        
        task = import_tasks[task_id]
        artifact_manifest = task.get('artifact_manifest')
        if not artifact_manifest:
            try:
                artifact_manifest = WorkflowArtifactService.get_manifest(task_id)
            except Exception as exc:
                logger.warning(f"Task {task_id}: artifact manifest lookup failed: {exc}")

        return {
            'task_id': task['task_id'],
            'filename': task['filename'],
            'file_type': task['file_type'],
            'current_stage': task['current_stage'],
            'progress': task['progress'],
            'message': task['message'],
            'status': task['status'],
            'committing': task.get('committing', False),
            'error': task.get('error'),
            'stats': task.get('stats'),
            'commit_phase': task.get('commit_phase'),
            'batch_progress': task.get('batch_progress'),
            'commit_metrics': task.get('commit_metrics'),
            'schema_metadata': task.get('schema_metadata'),
            'owl_ttl': task.get('owl_ttl'),  # Include OWL if available
            'workflow_id': task.get('workflow_id'),
            'artifact_manifest': artifact_manifest,
            'started_at': task['started_at'],
            'completed_at': task.get('completed_at'),
        }

    @classmethod
    def get_preview(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Get preview data"""
        if task_id not in import_tasks:
            restored = cls._restore_task(task_id)
            if not restored:
                return None
        
        task = import_tasks[task_id]
        return task.get('preview_data')

    @staticmethod
    def _ontology_match_key(value: Any) -> str:
        return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())

    @classmethod
    def _collect_ontology_link_candidates(cls, row: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for key in (
            'entity_type',
            'element_type',
            'type',
            'xsi:type',
            'class',
            'category',
            'part_type',
        ):
            value = row.get(key)
            if not value:
                continue
            for variant in (str(value), str(value).split(':')[-1], str(value).split('#')[-1]):
                normalized = cls._ontology_match_key(variant)
                if normalized:
                    candidates.append(normalized)

        if not candidates:
            value = row.get('name')
            if value:
                normalized = cls._ontology_match_key(value)
                if normalized:
                    candidates.append(normalized)

        unique_candidates: List[str] = []
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            unique_candidates.append(candidate)
        return unique_candidates

    @classmethod
    def _load_ontology_class_lookup(cls, ontology_prefix: str) -> Dict[str, List[Dict[str, Any]]]:
        """Return normalized AP242/selected ontology class names keyed for STEP linking."""
        raw_prefix = str(ontology_prefix or '').strip()
        prefix = raw_prefix.lower()
        preferred_prefixes = [p for p in {raw_prefix, prefix} if p]
        if prefix in ('step', 'step_ap242_mbd3d', 'ap242_mbd3d') or 'ap242' in prefix:
            preferred_prefixes.extend(['ap242', 'step_ap242_mbd3d', 'AP242', 'STEP_AP242_MBD3D'])
        preferred_prefixes = sorted({p for p in preferred_prefixes if p})
        lower_prefixes = sorted({p.lower() for p in preferred_prefixes if p})

        query = """
        MATCH (c:OntologyClass)
        WHERE c.prefix IN $prefixes
           OR c.ontology_prefix IN $prefixes
           OR c.ontology_id IN $prefixes
           OR c.prefix IN $lower_prefixes
           OR c.ontology_prefix IN $lower_prefixes
           OR c.ontology_id IN $lower_prefixes
           OR ($ap242 = true AND (
                c.prefix IN ['ap242', 'step_ap242_mbd3d', 'AP242', 'STEP_AP242_MBD3D']
                OR c.ontology_prefix IN ['ap242', 'step_ap242_mbd3d', 'AP242', 'STEP_AP242_MBD3D']
                OR c.ontology_id IN ['ap242', 'step_ap242_mbd3d', 'AP242', 'STEP_AP242_MBD3D']
                OR c.namespace CONTAINS '10303'
           ))
        RETURN elementId(c) AS element_id,
               coalesce(c.name, c.label, c.id, c.uri) AS name,
               coalesce(c.uri, '') AS uri,
               coalesce(c.prefix, c.ontology_prefix, c.ontology_id, '') AS prefix
        """
        try:
            try:
                from core.graph import query_with_timeout as _query_with_timeout
            except ModuleNotFoundError:
                from ..core.graph import query_with_timeout as _query_with_timeout
            records = _query_with_timeout(
                query,
                {
                    'prefixes': preferred_prefixes,
                    'lower_prefixes': lower_prefixes,
                    'ap242': any('ap242' in p.lower() for p in preferred_prefixes),
                },
            ) or []
        except Exception as exc:
            logger.warning(f"Ontology class lookup skipped for prefix '{ontology_prefix}': {exc}")
            return {}

        lookup: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            name = record.get('name')
            element_id = record.get('element_id')
            if not name or not element_id:
                continue
            uri = str(record.get('uri') or '')
            aliases = [str(name)]
            if uri:
                aliases.append(uri.rsplit('#', 1)[-1].rsplit('/', 1)[-1])
            for alias in aliases:
                key = cls._ontology_match_key(alias)
                if not key:
                    continue
                lookup.setdefault(key, []).append({
                    'element_id': element_id,
                    'class_name': str(name),
                    'prefix': record.get('prefix') or ontology_prefix,
                    'normalized': key,
                    'tokens': [token for token in re.split(r'[^a-zA-Z0-9]+', str(name).lower()) if len(token) > 1],
                    'is_generic': str(name).strip().lower() in {'part', 'class', 'entity', 'item', 'object', 'resource', 'thing', 'type', 'value'},
                })
        return lookup

    @classmethod
    def _commit_sync(cls, task_id: str, task: dict, schema: dict) -> Dict[str, Any]:
        """
        Synchronous Neo4j write body — called via asyncio.to_thread so it never
        blocks the FastAPI event loop.
        """
        import re as _re
        commit_started_at = time.perf_counter()
        rows = task.get('parsed_rows', [])

        # 🔒 DATA LOSS PREVENTION: Validate data integrity before commit
        is_valid, error_msg = Neo4jImporter.validate_before_ingest(rows, schema)
        if not is_valid:
            raise ValueError(f"Data validation failed: {error_msg}")

        # 🔒 DATA LOSS PREVENTION: Check for duplicates
        dup_count, dup_ids = Neo4jImporter.check_duplicate_entries(rows, schema)
        if dup_count > 0:
            logger.warning(f"Found {dup_count} duplicate entries. These will be merged. IDs: {dup_ids[:5]}...")

        task['commit_phase'] = 'prepare'
        task['batch_progress'] = None
        task['commit_metrics'] = {
            'rows_total': len(rows),
            'node_batch_size': IMPORT_WRITE_BATCH_SIZE,
            'link_batch_size': IMPORT_LINK_BATCH_SIZE,
            'nodes_written': 0,
            'relationships_written': 0,
            'relationships_skipped': 0,
            'instance_links_created': 0,
            'ontology_classes_matched': 0,
            'phase': 'prepare',
        }
        cls._update_commit_state(
            task_id,
            task,
            progress=82,
            message='Preparing Neo4j batches...',
            phase='prepare',
            commit_metrics=task['commit_metrics'],
        )

        # Derive ontology prefix/name from parsed stats (namespace-based)
        _stats = task.get('stats', {})
        _ontology_prefix = _stats.get('ontology_prefix') or task.get('file_type', 'unknown')
        _ontology_name = _stats.get('ontology_name') or _ontology_prefix
        _namespace_uri = _stats.get('namespace', '')
        logger.info(
            f"Task {task_id}: ontology_prefix='{_ontology_prefix}', "
            f"ontology_name='{_ontology_name}', namespace='{_namespace_uri}'"
        )
        # Stamp namespace-derived metadata onto every row before writing
        for _row in rows:
            _row.setdefault('import_id', task_id)
            _row.setdefault('ontology_prefix', _ontology_prefix)
            _row.setdefault('source_ontology', _namespace_uri or _ontology_name)
            _row.setdefault('source_filename', task.get('filename') or '')

        result = {'queries_executed': 0, 'nodes_created': 0,
                  'relationships_created': 0, 'instance_links_created': 0,
                  'ontology_classes_matched': 0, 'errors': []}
        result['warnings'] = []
        result['classes_created'] = len([nd for nd in schema.get('nodes', []) if nd.get('label')])
        result['individuals_created'] = len(rows)
        result['unresolved_references'] = int((_stats.get('unresolved_references') or 0))
        result['duplicate_ids'] = int((_stats.get('duplicate_ids') or 0))
        result['relationships_skipped'] = 0
        result['skipped_node_rows'] = 0

        if task.get('file_type') == 'plmxml' and result['duplicate_ids'] > 0:
            raise ValueError(
                "PLMXML import contains duplicate source identifiers. "
                "Commit is blocked to prevent ambiguous node merges and relationship resolution."
            )

        def _sync_metrics(
            phase: str,
            progress: int,
            message: str,
            batch_progress: Optional[Dict[str, Any]] = None,
        ) -> None:
            current_progress = int(task.get('progress') or 0)
            stable_progress = max(current_progress, int(progress))
            task['commit_metrics'] = {
                **(task.get('commit_metrics') or {}),
                'phase': phase,
                'nodes_written': result['nodes_created'],
                'relationships_written': result['relationships_created'],
                'relationships_skipped': result['relationships_skipped'],
                'instance_links_created': result['instance_links_created'],
                'ontology_classes_matched': result['ontology_classes_matched'],
            }
            cls._update_commit_state(
                task_id,
                task,
                progress=stable_progress,
                message=message,
                phase=phase,
                batch_progress=batch_progress,
                commit_metrics=task['commit_metrics'],
            )

        merge_support_indexes: List[Dict[str, Any]] = []
        seen_merge_signatures = set()
        for node_def in schema.get('nodes', []):
            label = node_def.get('label')
            merge_keys = [str(k) for k in (node_def.get('mergeKeys') or []) if k]
            if not label or not merge_keys:
                continue
            signature = (str(label), tuple(merge_keys))
            if signature in seen_merge_signatures:
                continue
            seen_merge_signatures.add(signature)
            merge_support_indexes.append({
                'type': 'range',
                'name': f"idx_merge_{str(label).replace(':', '_')}_{'_'.join(merge_keys)}",
                'label': label,
                'properties': merge_keys,
            })

        _sync_metrics('prepare', 83, 'Validating Neo4j indexes and constraints...')
        schema_validation = Neo4jImporter.validate_indexes_and_constraints(schema, merge_support_indexes)
        result['schema_validation'] = schema_validation
        if schema_validation.get('missing_indexes'):
            missing_index_queries = DataTransformer.create_indexes(schema_validation['missing_indexes'])
            if missing_index_queries:
                logger.info(
                    "Task %s: creating %s missing Neo4j indexes before ingest",
                    task_id,
                    len(schema_validation['missing_indexes']),
                )
                idx_result = Neo4jImporter.execute_cypher(missing_index_queries)
                result['queries_executed'] += idx_result.get('queries_executed', 0)
                result['errors'].extend(idx_result.get('errors', []))
                result['schema_validation']['created_index_count'] = len(schema_validation['missing_indexes'])
        else:
            result['schema_validation']['created_index_count'] = 0

        # ── Node queries ────────────────────────────────────────────────────
        _sync_metrics('nodes', 84, 'Writing entity batches to Neo4j...')
        for node_def in schema.get('nodes', []):
            label = node_def.get('label', 'ImportedRecord')
            merge_keys = node_def.get('mergeKeys', [])
            filter_key = node_def.get('_filter_key')
            filter_val = node_def.get('_filter_val')
            if filter_key and filter_val:
                node_rows = [r for r in rows
                             if str(r.get(filter_key, '')).replace(' ', '_').replace(':', '_') == filter_val]
            else:
                node_rows = rows
            original_node_row_count = len(node_rows)
            # Skip rows missing any required merge key (avoids Cypher MERGE on null)
            if merge_keys:
                node_rows = [r for r in node_rows if all(r.get(k) is not None for k in merge_keys)]
            skipped_for_label = original_node_row_count - len(node_rows)
            if skipped_for_label > 0:
                result['skipped_node_rows'] += skipped_for_label
                warning = (
                    f"Skipped {skipped_for_label} '{label}' rows because required merge keys "
                    f"{merge_keys} were missing."
                )
                result['warnings'].append(warning)
                logger.warning("Task %s: %s", task_id, warning)
            if not node_rows:
                continue
            queries, _ = DataTransformer.transform_to_nodes(node_rows, label, merge_keys)
            node_batch_size = max(100, IMPORT_WRITE_BATCH_SIZE)
            node_total_batches = max(1, (len(node_rows) + node_batch_size - 1) // node_batch_size)
            node_result = Neo4jImporter.execute_cypher(
                queries,
                node_rows,
                batch_size=node_batch_size,
                batch_callback=lambda batch, _label=label, _total=node_total_batches, _rows_total=len(node_rows): _sync_metrics(
                    'nodes',
                    84 + int(8 * (batch.get('rows_processed', 0) / max(1, _rows_total))),
                    f"Writing {(_label or 'entity')} batch {batch.get('batch_index', 1)} of {_total}...",
                    {
                        'scope': _label or 'entity',
                        'batch_index': batch.get('batch_index', 1),
                        'total_batches': _total,
                        'rows_processed': batch.get('rows_processed', 0),
                        'rows_total': _rows_total,
                    },
                ),
            )
            result['queries_executed'] += node_result.get('queries_executed', 0)
            result['nodes_created'] += len(node_rows)
            result['errors'].extend(node_result.get('errors', []))

        # ── XMI relationship edges ───────────────────────────────────────────
        xmi_rels = task.get('_xmi_relationships', [])
        schema_labels = [nd.get('label', '') for nd in schema.get('nodes', []) if nd.get('label')]
        _label_hint = f":`{schema_labels[0]}`" if len(schema_labels) == 1 else ''
        row_id_set = {str(r.get('id')) for r in rows if r.get('id') is not None}
        if xmi_rels:
            rel_by_type: Dict[str, List[Dict[str, Any]]] = {}
            for rel in xmi_rels:
                from_id = str((rel.get('from_props') or {}).get('id', '') or '')
                to_id = str((rel.get('to_props') or {}).get('id', '') or '')
                raw_type = rel.get('type') or 'RELATED_TO'
                safe_type = _re.sub(r'[^A-Z0-9_]', '_', raw_type.upper()).strip('_') or 'RELATED_TO'
                if from_id and to_id:
                    if from_id in row_id_set and to_id in row_id_set:
                        rel_by_type.setdefault(safe_type, []).append({
                            'from_id': from_id,
                            'to_id': to_id,
                            'properties': rel.get('properties') or {},
                        })
                    else:
                        result['relationships_skipped'] += 1
            _sync_metrics('relationships', 92, 'Creating relationship batches...')
            for rel_type, rel_rows in rel_by_type.items():
                rel_cypher = f"""
                UNWIND $rows AS row
                MATCH (a{_label_hint} {{id: row.from_id, import_id: row.import_id}})
                MATCH (b{_label_hint} {{id: row.to_id, import_id: row.import_id}})
                MERGE (a)-[rel:`{rel_type}`]->(b)
                SET rel += coalesce(row.properties, {{}})
                RETURN count(*) AS matched_rows
                """
                try:
                    rel_rows_scoped = [{**rr, 'import_id': task_id} for rr in rel_rows]
                    rel_batch_size = max(100, IMPORT_LINK_BATCH_SIZE)
                    rel_total_batches = max(1, (len(rel_rows_scoped) + rel_batch_size - 1) // rel_batch_size)
                    rel_result = Neo4jImporter.execute_cypher(
                        [rel_cypher],
                        rel_rows_scoped,
                        batch_size=rel_batch_size,
                        batch_callback=lambda batch, _type=rel_type, _total=rel_total_batches, _rows_total=len(rel_rows_scoped): _sync_metrics(
                            'relationships',
                            92 + int(3 * (batch.get('rows_processed', 0) / max(1, _rows_total))),
                            f"Creating {_type} batch {batch.get('batch_index', 1)} of {_total}...",
                            {
                                'scope': _type,
                                'batch_index': batch.get('batch_index', 1),
                                'total_batches': _total,
                                'rows_processed': batch.get('rows_processed', 0),
                                'rows_total': _rows_total,
                            },
                        ),
                    )
                    if rel_result.get('errors'):
                        logger.warning(f"Relationship write errors for type {rel_type}: {rel_result['errors']}")
                    else:
                        matched_rows = int(rel_result.get('matched_rows') or 0)
                        skipped_rows = max(0, len(rel_rows) - matched_rows)
                        result['relationships_created'] += matched_rows
                        result['relationships_skipped'] += skipped_rows
                        if skipped_rows:
                            logger.warning(
                                "Task %s: relationship type %s resolved %s/%s rows",
                                task_id,
                                rel_type,
                                matched_rows,
                                len(rel_rows),
                            )
                except Exception as rel_err:
                    logger.warning(f"Relationship write skipped for type {rel_type}: {rel_err}")

        # ── STEP reference edges ────────────────────────────────────────────
        step_ref_map = task.get('_step_ref_map', {})
        step_ref_rows = [
            {'from_key': r.get('import_row_key'), 'to_id': f"#{tid}"}
            for r in rows
            for tid in (r.get('ref_ids') or [])
            if r.get('import_row_key') and tid is not None
        ]
        if step_ref_rows:
            step_rel_cypher = f"""
            UNWIND $rows AS row
            MATCH (a{_label_hint} {{import_row_key: row.from_key, import_id: row.import_id}})
            MATCH (b{_label_hint} {{import_row_key: row.to_id, import_id: row.import_id}})
            MERGE (a)-[:REFERENCES {{target_source_id: row.to_id}}]->(b)
            RETURN count(*) AS matched_rows
            """
            try:
                ref_rows_scoped = [{**rr, 'import_id': task_id} for rr in step_ref_rows]
                ref_batch_size = max(100, IMPORT_LINK_BATCH_SIZE)
                ref_total_batches = max(1, (len(ref_rows_scoped) + ref_batch_size - 1) // ref_batch_size)
                step_rel_result = Neo4jImporter.execute_cypher(
                    [step_rel_cypher],
                    ref_rows_scoped,
                    batch_size=ref_batch_size,
                    batch_callback=lambda batch, _total=ref_total_batches, _rows_total=len(ref_rows_scoped): _sync_metrics(
                        'relationships',
                        94,
                        f"Linking STEP references batch {batch.get('batch_index', 1)} of {_total}...",
                        {
                            'scope': 'STEP references',
                            'batch_index': batch.get('batch_index', 1),
                            'total_batches': _total,
                            'rows_processed': batch.get('rows_processed', 0),
                            'rows_total': _rows_total,
                        },
                    ),
                )
                if not step_rel_result.get('errors'):
                    matched_rows = int(step_rel_result.get('matched_rows') or 0)
                    skipped_rows = max(0, len(step_ref_rows) - matched_rows)
                    result['relationships_created'] += matched_rows
                    result['relationships_skipped'] += skipped_rows
                    logger.info(f"Task {task_id}: STEP — wrote {matched_rows} row-key REFERENCES edges")
                else:
                    logger.warning(f"Task {task_id}: STEP ref write errors: {step_rel_result['errors'][:3]}")
            except Exception as step_rel_err:
                logger.warning(f"Task {task_id}: STEP reference edges skipped: {step_rel_err}")
        elif step_ref_map:
            ref_rows = [
                {'from_id': f'#{fid}', 'to_id': f'#{tid}'}
                for fid, refs in step_ref_map.items()
                for tid in refs
            ]
            step_rel_cypher = f"""
            UNWIND $rows AS row
            MATCH (a{_label_hint} {{id: row.from_id, import_id: row.import_id}})
            MATCH (b{_label_hint} {{id: row.to_id, import_id: row.import_id}})
            MERGE (a)-[:REFERENCES]->(b)
            RETURN count(*) AS matched_rows
            """
            try:
                ref_rows_scoped = [{**rr, 'import_id': task_id} for rr in ref_rows]
                ref_batch_size = max(100, IMPORT_LINK_BATCH_SIZE)
                ref_total_batches = max(1, (len(ref_rows_scoped) + ref_batch_size - 1) // ref_batch_size)
                step_rel_result = Neo4jImporter.execute_cypher(
                    [step_rel_cypher],
                    ref_rows_scoped,
                    batch_size=ref_batch_size,
                    batch_callback=lambda batch, _total=ref_total_batches, _rows_total=len(ref_rows_scoped): _sync_metrics(
                        'relationships',
                        94,
                        f"Linking STEP references batch {batch.get('batch_index', 1)} of {_total}...",
                        {
                            'scope': 'STEP references',
                            'batch_index': batch.get('batch_index', 1),
                            'total_batches': _total,
                            'rows_processed': batch.get('rows_processed', 0),
                            'rows_total': _rows_total,
                        },
                    ),
                )
                if not step_rel_result.get('errors'):
                    matched_rows = int(step_rel_result.get('matched_rows') or 0)
                    skipped_rows = max(0, len(ref_rows) - matched_rows)
                    result['relationships_created'] += matched_rows
                    result['relationships_skipped'] += skipped_rows
                    logger.info(f"Task {task_id}: STEP — wrote {matched_rows} REFERENCES edges")
                else:
                    logger.warning(f"Task {task_id}: STEP ref write errors: {step_rel_result['errors'][:3]}")
            except Exception as step_rel_err:
                logger.warning(f"Task {task_id}: STEP reference edges skipped: {step_rel_err}")

        # ── STPX parent-child hierarchy edges ──────────────────────────────
        parent_rows = [
            {'child_id': r.get('id'), 'parent_id': r.get('parent_step_id')}
            for r in rows
            if r.get('id') and r.get('parent_step_id')
        ]
        if parent_rows:
            parent_cypher = f"""
            UNWIND $rows AS row
            MATCH (child{_label_hint} {{id: row.child_id, import_id: row.import_id}})
            MATCH (parent{_label_hint} {{id: row.parent_id, import_id: row.import_id}})
            MERGE (parent)-[:PARENT_OF]->(child)
            RETURN count(*) AS matched_rows
            """
            try:
                parent_rows_scoped = [{**rr, 'import_id': task_id} for rr in parent_rows]
                parent_batch_size = max(100, IMPORT_LINK_BATCH_SIZE)
                parent_total_batches = max(1, (len(parent_rows_scoped) + parent_batch_size - 1) // parent_batch_size)
                parent_result = Neo4jImporter.execute_cypher(
                    [parent_cypher],
                    parent_rows_scoped,
                    batch_size=parent_batch_size,
                    batch_callback=lambda batch, _total=parent_total_batches, _rows_total=len(parent_rows_scoped): _sync_metrics(
                        'relationships',
                        95,
                        f"Linking STPX parent hierarchy batch {batch.get('batch_index', 1)} of {_total}...",
                        {
                            'scope': 'STPX hierarchy',
                            'batch_index': batch.get('batch_index', 1),
                            'total_batches': _total,
                            'rows_processed': batch.get('rows_processed', 0),
                            'rows_total': _rows_total,
                        },
                    ),
                )
                if not parent_result.get('errors'):
                    matched_rows = int(parent_result.get('matched_rows') or 0)
                    skipped_rows = max(0, len(parent_rows) - matched_rows)
                    result['relationships_created'] += matched_rows
                    result['relationships_skipped'] += skipped_rows
                    logger.info(f"Task {task_id}: STPX — wrote {matched_rows} PARENT_OF edges")
                else:
                    logger.warning(f"Task {task_id}: STPX hierarchy write errors: {parent_result['errors'][:3]}")
            except Exception as parent_err:
                logger.warning(f"Task {task_id}: STPX parent hierarchy edges skipped: {parent_err}")

        # Semantic ontology linking is intentionally deferred to the
        # `instance.link` semantic bridge workflow so import remains structural,
        # faster, and easier to reason about for end users.
        _sync_metrics('verification', 96, 'Structural import complete. Semantic linking is available in Link instances to ontology.')

        # ── ownerId → OWNED_BY relationship edges (XMI ownership hierarchy) ──
        owner_rows = [
            {'child_id': r.get('id'), 'parent_id': r.get('ownerId')}
            for r in rows
            if r.get('id') and r.get('ownerId')
        ]
        if owner_rows:
            owner_cypher = """
            UNWIND $rows AS row
            MATCH (child {id: row.child_id, import_id: row.import_id})
            MATCH (parent {id: row.parent_id, import_id: row.import_id})
            MERGE (child)-[:OWNED_BY]->(parent)
            RETURN count(*) AS matched_rows
            """
            _BATCH = max(100, IMPORT_LINK_BATCH_SIZE)
            _sync_metrics('verification', 98, 'Finalizing ownership and verification links...')
            for _i in range(0, len(owner_rows), _BATCH):
                _batch = owner_rows[_i:_i + _BATCH]
                try:
                    _batch_scoped = [{**rr, 'import_id': task_id} for rr in _batch]
                    try:
                        from core.graph import query_with_timeout as _query_with_timeout
                    except ModuleNotFoundError:
                        from ..core.graph import query_with_timeout as _query_with_timeout
                    _owner_result = _query_with_timeout(owner_cypher, {'rows': _batch_scoped}, timeout=IMPORT_COMMIT_QUERY_TIMEOUT) or []
                    matched_rows = 0
                    if isinstance(_owner_result, list):
                        for _record in _owner_result:
                            if isinstance(_record, dict):
                                try:
                                    matched_rows += int(_record.get('matched_rows') or 0)
                                except (TypeError, ValueError):
                                    pass
                    result['relationships_created'] += matched_rows
                    result['relationships_skipped'] += max(0, len(_batch) - matched_rows)
                except Exception as _own_err:
                    logger.warning(f"Task {task_id}: OWNED_BY batch {_i // _BATCH}: {_own_err}")

        # ── Release parsed rows (large) — file_content kept for OWL background job ──
        task.pop('parsed_rows', None)

        task['current_stage'] = ImportStage.INGEST.value
        task['status'] = ImportStatus.COMPLETED.value
        result['ingestion_time'] = round(time.perf_counter() - commit_started_at, 6)
        task['result'] = result
        task['completed_at'] = datetime.now().isoformat()
        task['committing'] = False
        _sync_metrics('complete', 100, 'Import completed successfully', None)
        task['batch_progress'] = None
        cls._persist_task(task_id)

        logger.info(f"Task {task_id} completed: {result}")
        return result

    @classmethod
    def _generate_owl_background(cls, task_id: str, task: dict) -> None:
        """Generate OWL/TTL in a background thread — does not block the commit response."""
        try:
            from .owl_generation_service import OWLGenerationService
            owl_ttl: str = task.get('owl_ttl', '')
            owl_meta: Dict[str, Any] = task.get('owl_meta', {})
            if not owl_ttl:
                file_content_bytes: bytes = task.get('file_content', b'')
                filename: str = task.get('filename', '')
                if file_content_bytes and filename:
                    start_t = time.perf_counter()
                    owl_ttl, owl_meta = OWLGenerationService.generate_owl(file_content_bytes, filename)
                    dur = time.perf_counter() - start_t
                    logger.info(f"Task {task_id}: background OWL generation took {dur:.2f}s")
            if owl_ttl:
                OWLGenerationService.store(task_id, owl_ttl)
                cls._write_artifact(
                    task_id,
                    task,
                    "write_text",
                    "ontology",
                    f"{Path(task.get('filename') or 'ontology').stem}.ttl",
                    owl_ttl,
                    "ontology_ttl",
                    owl_meta,
                )
                task.setdefault('result', {})['owl_ttl_lines'] = owl_meta.get('ttl_lines', 0)
                task['result']['owl_format'] = owl_meta.get('format', '')
                validation = owl_meta.get('validation', {})
                task['result']['owl_validation'] = {
                    'error_count': validation.get('error_count', 0),
                    'warning_count': validation.get('warning_count', 0),
                    'is_valid': validation.get('is_valid', True),
                }
                # Run SHACL validation on the generated OWL TTL and attach report
                try:
                    try:
                        shacl_report = OWLGenerationService.validate_with_shacl(
                            owl_ttl,
                            ontology_context=owl_meta.get('owlready2'),
                        )
                    except TypeError:
                        # Preserve compatibility with older test doubles / callers
                        # that still expose the previous positional-only contract.
                        shacl_report = OWLGenerationService.validate_with_shacl(owl_ttl)
                    task['shacl_report'] = shacl_report
                    task.setdefault('result', {})['shacl_conforms'] = shacl_report.get('conforms')
                    if shacl_report.get('ontology_context'):
                        task['result']['shacl_ontology_context'] = shacl_report.get('ontology_context')
                    cls._write_artifact(
                        task_id,
                        task,
                        "write_json",
                        "validation",
                        "shacl_report.json",
                        shacl_report,
                        "shacl_report",
                    )
                    logger.info(f"Task {task_id}: SHACL validation conforms={shacl_report.get('conforms')}")
                except Exception as sh_err:
                    logger.warning(f"Task {task_id}: SHACL validation failed: {sh_err}")
                logger.info(
                    f"Task {task_id}: OWL background done — "
                    f"{task['result']['owl_ttl_lines']} lines ({task['result']['owl_format']})"
                )
        except Exception as owl_err:
            logger.warning(f"Task {task_id}: OWL background generation failed: {owl_err}")
        finally:
            task.pop('file_content', None)  # release after OWL is done
            cls._refresh_artifact_manifest(task_id, task)
            cls._persist_task(task_id)

    @classmethod
    async def commit_import(cls, task_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Commit import to Neo4j.
        Fast pre-checks run synchronously. The Neo4j write itself is queued in
        the background so the HTTP response returns before gateway/proxy
        timeouts can interrupt very large commits.
        """
        import asyncio

        if task_id not in import_tasks:
            restored = cls._restore_task(task_id)
            if not restored:
                raise ValueError(f"Task not found: {task_id}")

        task = import_tasks[task_id]

        if task['status'] != ImportStatus.PROCESSING.value:
            raise ValueError(f"Task not in processing state: {task['status']}")

        if not task.get('parsed_rows'):
            # Attempt fallback: load parsed_rows from the separate parsed_rows file
            try:
                path = cls._task_snapshot_path(task_id)
                parsed_name = task.get('_parsed_rows_file') or (path.name + '.parsed_rows.json')
                parsed_path = path.parent / parsed_name
                if parsed_path.exists():
                    try:
                        parsed_text = parsed_path.read_text(encoding='utf-8')
                        parsed_data = json.loads(parsed_text)
                        task['parsed_rows'] = parsed_data
                        logger.info(f"Task {task_id}: loaded parsed_rows from {parsed_path.name} ({len(parsed_data)} rows)")
                        cls._persist_task(task_id)
                    except Exception as pexc:
                        logger.warning(f"Task {task_id}: failed to load parsed_rows from disk fallback: {pexc}")
                else:
                    raise ValueError(
                        f"Task not ready for commit: current_stage={task.get('current_stage')}"
                    )
            except ValueError:
                # propagate explicit 'not ready' error
                raise
            except Exception as exc:
                logger.exception(f"Task {task_id}: unexpected error during parsed_rows fallback: {exc}")
                raise ValueError(
                    f"Task not ready for commit: current_stage={task.get('current_stage')}"
                )

        schema = config or task.get('auto_schema', {})
        task['current_stage'] = ImportStage.INGEST.value
        task['progress'] = 80
        task['message'] = 'Queued for Neo4j commit...'
        task['committing'] = True
        cls._persist_task(task_id)

        async def _run_commit_background() -> None:
            try:
                result = await asyncio.to_thread(cls._commit_sync, task_id, task, schema)
                # Fire OWL generation in background — does NOT block the HTTP response.
                asyncio.get_running_loop().run_in_executor(
                    None, cls._generate_owl_background, task_id, task
                )
                logger.info(f"Task {task_id}: Neo4j commit finished in background: {result}")
            except Exception as e:
                # Revert to PROCESSING/preview so the user can retry.
                task.pop('file_content', None)
                task['committing'] = False
                task['status'] = ImportStatus.PROCESSING.value
                task['current_stage'] = ImportStage.PREVIEW.value
                task['progress'] = 75
                task['commit_phase'] = 'error'
                task['batch_progress'] = None
                task['message'] = f'Commit failed — retry available. Error: {str(e)[:200]}'
                task['error'] = str(e)
                cls._persist_task(task_id)
                logger.error(f"Task {task_id} commit failed (reset to preview for retry): {str(e)}")

        asyncio.create_task(_run_commit_background())
        return {
            "queued": True,
            "task_id": task_id,
            "status": task['status'],
            "current_stage": task['current_stage'],
            "progress": task['progress'],
            "message": "Neo4j commit queued in background. Continue polling task status.",
        }

    @classmethod
    def cancel_import(cls, task_id: str) -> None:
        """Cancel import task"""
        if task_id in import_tasks:
            task = import_tasks[task_id]
            if task['status'] == ImportStatus.PROCESSING.value:
                task['status'] = ImportStatus.CANCELLED.value
                task['completed_at'] = datetime.now().isoformat()
                cls._persist_task(task_id)
                logger.info(f"Task {task_id} cancelled")

