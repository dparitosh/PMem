"""Normalize uploaded RDF syntax without publishing or asserting new facts."""
from pathlib import Path
from rdflib import Graph
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from backend.artifact_store import ArtifactStore
from backend.depo_platform.upload_limits import ontology_upload_limit


def convert_rdf(*, filename, content):
    if not content or len(content) > ontology_upload_limit():
        raise ValueError('RDF artifact is empty or exceeds the ontology upload limit')
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.ttl', '.rdf', '.owl'}:
        raise ValueError('Expected a Turtle or RDF/XML ontology')
    if suffix != '.ttl':
        # Inspect XML without resolving DTDs/entities before RDFLib sees it.
        # Turtle may also start with an IRI; XML syntax is selected only if valid.
        try:
            ElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        except ElementTree.ParseError:
            rdf_format = 'turtle'
        except DefusedXmlException as failure:
            raise ValueError('RDF/XML DTDs and entity declarations are forbidden') from failure
        else:
            rdf_format = 'xml'
    else:
        rdf_format = 'turtle'
    try:
        graph = Graph().parse(data=content, format=rdf_format)
    except Exception as failure:
        raise ValueError('Ontology RDF syntax is invalid') from failure
    if not graph:
        raise ValueError('Ontology contains no RDF triples')
    turtle = graph.serialize(format='turtle')
    store = ArtifactStore()
    source = store.ingest_bytes(content, filename=Path(filename).name, kind='ontology-source')
    serialized = store.ingest_bytes(turtle.encode('utf-8'), filename=Path(filename).stem + '.ttl', kind='serialized-ontology',
                                    media_type='text/turtle', provenance={'source_artifact_id': source['artifact_id']})
    return {'format': 'RDF', 'source_kind': 'schema', 'statistics': {'triples': len(graph)},
            'ontology': {'name': Path(filename).stem, 'prefix': 'ontology', 'turtle': turtle},
            'artifacts': {'source': source['artifact_id'], 'serialization': serialized['artifact_id']},
            'data_product_draft': {
                'contract': 'ontology-evidence-data-product-v1',
                'product_kind': 'ontology-evidence',
                'analytics_readiness': 'semantic_evidence_requires_review',
                'name': f'{Path(filename).stem} ontology evidence',
                'domain': 'semantic-engineering',
                'artifacts': [{'artifact_id': source['artifact_id']}, {'artifact_id': serialized['artifact_id']}],
                'quality_status': 'requires_review',
                'publication_requirements': ['approved semantic release', 'data-product steward approval', 'explicit Data Product API publish request'],
            }}
