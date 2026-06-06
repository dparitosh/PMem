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

from enum import Enum

logger = logging.getLogger(__name__)

# Keep write transactions moderate to reduce AuraDB timeout risk.
IMPORT_WRITE_BATCH_SIZE = int(os.getenv('IMPORT_WRITE_BATCH_SIZE', '200'))

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
                    'label': 'DataNode',
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


# ========== File Parser Router ==========

class FileParser:
    """Dispatcher for routing files to appropriate parser based on type"""
    
    @staticmethod
    def parse(file_content: bytes, file_type: FileType) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Parse file content based on file type
        
        Args:
            file_content: Raw file bytes
            file_type: FileType enum value
        
        Returns:
            Tuple of (rows: List[Dict], stats: Dict)
        """
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
                return FileParser._parse_plmxml(file_content)
            elif file_type == FileType.STEP:
                return FileParser._parse_step(file_content)
            elif file_type == FileType.XML:
                # Content-sniff: if the root element is PLMXML (namespace or tag),
                # treat it as PLMXML so we get namespace extraction + structured parsing.
                _head = file_content[:4096]
                _is_plmxml = (
                    b'<PLMXML' in _head
                    or b'PLMXMLSchema' in _head
                    or b'plmxml.org' in _head
                )
                if _is_plmxml:
                    return FileParser._parse_plmxml(file_content)
                return FileParser._parse_xml(file_content)
            elif file_type == FileType.JSON:
                return FileParser._parse_json(file_content)
            else:
                return [], {'error': f'Unsupported file type: {file_type}'}
        except Exception as e:
            logging.error(f"Error parsing {file_type.value}: {str(e)}")
            return [], {'error': str(e), 'file_type': file_type.value}
    
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
    def _parse_plmxml(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse PLMXML file using the dedicated plmxml_parser module.

        Extracts semantic PLM objects: parts, BOMs, processes, requirements,
        RFLP trace links, and product instances with parent-child structure.
        Falls back to generic XML flatten if the dedicated parser fails.
        """
        import tempfile
        from pathlib import Path as _Path
        try:
            from .plmxml_parser import parse_plmxml_file

            with tempfile.NamedTemporaryFile(delete=False, suffix='.plmxml') as tmp:
                tmp.write(file_content)
                tmp_path = _Path(tmp.name)
            try:
                doc = parse_plmxml_file(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)

            rows: List[Dict[str, Any]] = []
            raw_rels: List[Dict[str, Any]] = []

            for pid, part in doc.parts.items():
                rows.append({
                    'element_type': 'Part', 'id': pid,
                    'name': part.name, 'part_number': part.part_number,
                    'revision': part.revision, 'description': part.description,
                    'part_type': part.part_type,
                })

            for rid, req in doc.requirements.items():
                rows.append({
                    'element_type': 'Requirement', 'id': rid,
                    'name': req.name, 'catalogue_id': req.catalogue_id,
                    'revision': req.revision,
                    'body_text': (req.body_text or '')[:500],
                })

            for proc_id, proc in doc.processes.items():
                rows.append({
                    'element_type': 'Process', 'id': proc_id,
                    'name': proc.name, 'process_type': proc.process_type,
                    'description': proc.description,
                })

            for inst in doc.product_instances:
                rows.append({
                    'element_type': 'ProductInstance', 'id': inst.id,
                    'name': inst.name, 'part_ref': inst.part_ref,
                    'parent_ref': inst.parent_ref, 'quantity': str(inst.quantity),
                })
                if inst.parent_ref and inst.part_ref:
                    raw_rels.append({'from_props': {'id': inst.parent_ref},
                                     'to_props': {'id': inst.part_ref}, 'type': 'CONTAINS'})

            for rel in doc.general_relations:
                for target_id in rel.related_refs:
                    raw_rels.append({'from_props': {'id': rel.id},
                                     'to_props': {'id': target_id},
                                     'type': rel.sub_type or 'RELATED_TO'})

            # Extract namespace from file content (first 512 bytes is enough)
            import defusedxml.ElementTree as _ET2
            _root2 = _ET2.fromstring(file_content[:8192])
            _ns_uri = _root2.tag[1:_root2.tag.index('}')] if _root2.tag.startswith('{') else _root2.get('xmlns', '')
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
                    }
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

                stats = {
                    'format': 'STEP',
                    'schema': schema,
                    'row_count': len(rows),
                    'column_count': len(rows[0]) if rows else 3,
                    'columns': list(rows[0].keys()) if rows else ['id', 'entity_type', 'args'],
                    'entity_types': type_counts,
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
            for match in entity_pattern.finditer(data_section):
                eid, etype, args = match.group(1), match.group(2), match.group(3).strip()
                args_preview = args[:200] + '...' if len(args) > 200 else args
                rows.append({'id': f'#{eid}', 'entity_type': etype, 'args': args_preview})
                type_counts[etype] = type_counts.get(etype, 0) + 1

            stats = {
                'format': 'STEP',
                'schema': schema,
                'row_count': len(rows),
                'column_count': 3,
                'columns': ['id', 'entity_type', 'args'],
                'entity_types': type_counts,
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
                    (c for c in ('id', 'uuid', 'key', 'name') if c in type_cols),
                    next((c for c in type_cols if c not in _SKIP_MERGE), type_cols[0]),
                )
                nodes.append({
                    'label': etype,
                    'mergeKeys': [merge_key],
                    'properties': type_cols,
                    '_filter_key': 'element_type',
                    '_filter_val': etype,
                })
                indexes.append({
                    'type': 'range',
                    'name': f"idx_{etype.lower()}_{merge_key}",
                    'label': etype,
                    'properties': [merge_key],
                })
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
                indexes.append({
                    'type': 'range',
                    'name': f"idx_{tval.lower()}_{merge_key}",
                    'label': tval,
                    'properties': [merge_key],
                })
            return {'nodes': nodes, 'indexes': indexes}

        # ── Single-label schema (original logic, column union fix applied) ────
        columns = sorted({k for row in rows for k in row.keys()})
        # Prefer unique identifier columns; 'name' is often non-unique or empty
        merge_key = next((c for c in ('id', 'uuid', 'key', 'name') if c in columns), columns[0])
        default_label = (
            element_types[0] if element_types
            else str(rows[0].get('type', 'DataNode')).replace(' ', '_').replace(':', '_')
        )
        nodes = [{'label': default_label, 'mergeKeys': [merge_key], 'properties': columns}]
        indexes = [{
            'type': 'range',
            'name': f"idx_{default_label.lower()}_{merge_key}",
            'label': default_label,
            'properties': [merge_key],
        }]
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
            for row_idx, row in enumerate(check_rows):
                if not row:
                    return False, f"Row {row_idx} is empty"

                for key in merge_keys:
                    if key not in row or row[key] is None:
                        missing_key_count += 1
            # Fail only if ALL rows are missing the merge key (schema mismatch),
            # not just some — partial rows are filtered out at write time.
            if missing_key_count == len(check_rows) and check_rows:
                return False, (
                    f"All {len(check_rows)} rows missing merge key '{merge_keys[0]}'. "
                    "Schema may be incorrect."
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
    def execute_cypher(queries: List[str], rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
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
            'errors': []
        }

        for query in queries:
            if not query or not query.strip():
                continue

            try:
                if rows and 'UNWIND $rows' in query:
                    _BATCH = max(50, IMPORT_WRITE_BATCH_SIZE)
                    for _i in range(0, len(rows), _BATCH):
                        _batch = rows[_i:_i + _BATCH]
                        result = _query_with_timeout(query, {'rows': _batch})
                        stats['queries_executed'] += 1
                        if isinstance(result, list):
                            stats['nodes_created'] += len(result)
                else:
                    result = _query_with_timeout(query)
                    stats['queries_executed'] += 1
                    if isinstance(result, list):
                        stats['nodes_created'] += len(result)
            except Exception as e:
                logger.error(f"Query execution error: {str(e)}", exc_info=True)
                stats['errors'].append(str(e))

        return stats


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
    def _task_snapshot_path(cls, task_id: str) -> Path:
        return cls.TASK_STORE_DIR / f"{task_id}.json"

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
    async def start_import(cls, file_content: bytes, filename: str, ontology_mapping: str = '') -> str:
        """
        Start an import task
        Returns task_id
        """
        # Validate file type
        file_type = FileFormatDetector.detect(filename)
        if not file_type:
            raise ValueError(f"Unsupported file type. Supported: {', '.join(FileFormatDetector.get_supported_formats())}")

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
            # Keep raw bytes only where downstream OWL generation may need them.
            'file_content': file_content if keep_file_content else None,
        }
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

            rows, stats = FileParser.parse(file_content, file_type)

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
        return {
            'task_id': task['task_id'],
            'filename': task['filename'],
            'file_type': task['file_type'],
            'current_stage': task['current_stage'],
            'progress': task['progress'],
            'message': task['message'],
            'status': task['status'],
            'error': task.get('error'),
            'stats': task.get('stats'),
            'schema_metadata': task.get('schema_metadata'),
            'owl_ttl': task.get('owl_ttl'),  # Include OWL if available
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

    @classmethod
    def _commit_sync(cls, task_id: str, task: dict, schema: dict) -> Dict[str, Any]:
        """
        Synchronous Neo4j write body — called via asyncio.to_thread so it never
        blocks the FastAPI event loop.
        """
        import re as _re
        rows = task.get('parsed_rows', [])

        # 🔒 DATA LOSS PREVENTION: Validate data integrity before commit
        is_valid, error_msg = Neo4jImporter.validate_before_ingest(rows, schema)
        if not is_valid:
            raise ValueError(f"Data validation failed: {error_msg}")

        # 🔒 DATA LOSS PREVENTION: Check for duplicates
        dup_count, dup_ids = Neo4jImporter.check_duplicate_entries(rows, schema)
        if dup_count > 0:
            logger.warning(f"Found {dup_count} duplicate entries. These will be merged. IDs: {dup_ids[:5]}...")

        task['message'] = 'Writing to Neo4j...'
        task['progress'] = 85

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

        result = {'queries_executed': 0, 'nodes_created': 0,
                  'relationships_created': 0, 'errors': []}

        # ── Node queries ────────────────────────────────────────────────────
        for node_def in schema.get('nodes', []):
            label = node_def.get('label', 'DataNode')
            merge_keys = node_def.get('mergeKeys', [])
            filter_key = node_def.get('_filter_key')
            filter_val = node_def.get('_filter_val')
            if filter_key and filter_val:
                node_rows = [r for r in rows
                             if str(r.get(filter_key, '')).replace(' ', '_').replace(':', '_') == filter_val]
            else:
                node_rows = rows
            # Skip rows missing any required merge key (avoids Cypher MERGE on null)
            if merge_keys:
                node_rows = [r for r in node_rows if all(r.get(k) is not None for k in merge_keys)]
            if not node_rows:
                continue
            queries, _ = DataTransformer.transform_to_nodes(node_rows, label, merge_keys)
            node_result = Neo4jImporter.execute_cypher(queries, node_rows)
            result['queries_executed'] += node_result.get('queries_executed', 0)
            result['errors'].extend(node_result.get('errors', []))

        # ── Index queries ────────────────────────────────────────────────────
        index_queries = DataTransformer.create_indexes(schema.get('indexes', []))
        if index_queries:
            idx_result = Neo4jImporter.execute_cypher(index_queries)
            result['queries_executed'] += idx_result.get('queries_executed', 0)
            result['errors'].extend(idx_result.get('errors', []))

        # ── XMI relationship edges ───────────────────────────────────────────
        xmi_rels = task.get('_xmi_relationships', [])
        schema_labels = [nd.get('label', '') for nd in schema.get('nodes', []) if nd.get('label')]
        _label_hint = f":`{schema_labels[0]}`" if len(schema_labels) == 1 else ''
        if xmi_rels:
            rel_by_type: Dict[str, List[Dict[str, str]]] = {}
            for rel in xmi_rels:
                from_id = (rel.get('from_props') or {}).get('id', '')
                to_id = (rel.get('to_props') or {}).get('id', '')
                raw_type = rel.get('type') or 'RELATED_TO'
                safe_type = _re.sub(r'[^A-Z0-9_]', '_', raw_type.upper()).strip('_') or 'RELATED_TO'
                if from_id and to_id:
                    rel_by_type.setdefault(safe_type, []).append({'from_id': from_id, 'to_id': to_id})
            for rel_type, rel_rows in rel_by_type.items():
                rel_cypher = f"""
                UNWIND $rows AS row
                MATCH (a{_label_hint} {{id: row.from_id, import_id: row.import_id}})
                MATCH (b{_label_hint} {{id: row.to_id, import_id: row.import_id}})
                MERGE (a)-[:`{rel_type}`]->(b)
                """
                try:
                    rel_rows_scoped = [{**rr, 'import_id': task_id} for rr in rel_rows]
                    rel_result = Neo4jImporter.execute_cypher([rel_cypher], rel_rows_scoped)
                    if rel_result.get('errors'):
                        logger.warning(f"Relationship write errors for type {rel_type}: {rel_result['errors']}")
                    else:
                        result['relationships_created'] += len(rel_rows)
                except Exception as rel_err:
                    logger.warning(f"Relationship write skipped for type {rel_type}: {rel_err}")

        # ── STEP reference edges ────────────────────────────────────────────
        step_ref_map = task.get('_step_ref_map', {})
        if step_ref_map:
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
            """
            try:
                ref_rows_scoped = [{**rr, 'import_id': task_id} for rr in ref_rows]
                step_rel_result = Neo4jImporter.execute_cypher([step_rel_cypher], ref_rows_scoped)
                if not step_rel_result.get('errors'):
                    result['relationships_created'] += len(ref_rows)
                    logger.info(f"Task {task_id}: STEP — wrote {len(ref_rows)} REFERENCES edges")
                else:
                    logger.warning(f"Task {task_id}: STEP ref write errors: {step_rel_result['errors'][:3]}")
            except Exception as step_rel_err:
                logger.warning(f"Task {task_id}: STEP reference edges skipped: {step_rel_err}")

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
            """
            _BATCH = max(50, IMPORT_WRITE_BATCH_SIZE)
            for _i in range(0, len(owner_rows), _BATCH):
                _batch = owner_rows[_i:_i + _BATCH]
                try:
                    _batch_scoped = [{**rr, 'import_id': task_id} for rr in _batch]
                    try:
                        from core.graph import graph as _g
                    except ModuleNotFoundError:
                        from ..core.graph import graph as _g
                    _g.query(owner_cypher, {'rows': _batch_scoped})
                    result['relationships_created'] += len(_batch)
                except Exception as _own_err:
                    logger.warning(f"Task {task_id}: OWNED_BY batch {_i // _BATCH}: {_own_err}")

        # ── Release parsed rows (large) — file_content kept for OWL background job ──
        task.pop('parsed_rows', None)

        task['current_stage'] = ImportStage.INGEST.value
        task['progress'] = 100
        task['message'] = 'Import completed successfully'
        task['status'] = ImportStatus.COMPLETED.value
        task['result'] = result
        task['completed_at'] = datetime.now().isoformat()
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
                    shacl_report = OWLGenerationService.validate_with_shacl(owl_ttl)
                    task['shacl_report'] = shacl_report
                    task.setdefault('result', {})['shacl_conforms'] = shacl_report.get('conforms')
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
            cls._persist_task(task_id)

    @classmethod
    async def commit_import(cls, task_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Commit import to Neo4j.
        Fast pre-checks run synchronously; blocking Neo4j writes run in a thread
        pool via asyncio.to_thread so the event loop is never blocked.
        OWL generation is fired in a separate background thread so the HTTP
        response returns as soon as Neo4j writes are complete.
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
        task['message'] = 'Validating data before Neo4j commit...'
        cls._persist_task(task_id)

        try:
            result = await asyncio.to_thread(cls._commit_sync, task_id, task, schema)
            # Fire OWL generation in background — does NOT block the HTTP response.
            asyncio.get_event_loop().run_in_executor(
                None, cls._generate_owl_background, task_id, task
            )
            return result
        except Exception as e:
            # Revert to PROCESSING/preview so the user can retry.
            task.pop('file_content', None)  # release on failure too
            task['status'] = ImportStatus.PROCESSING.value
            task['current_stage'] = ImportStage.PREVIEW.value
            task['progress'] = 75
            task['message'] = f'Commit failed — retry available. Error: {str(e)[:200]}'
            task['error'] = str(e)
            cls._persist_task(task_id)
            logger.error(f"Task {task_id} commit failed (reset to preview for retry): {str(e)}")
            raise

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
