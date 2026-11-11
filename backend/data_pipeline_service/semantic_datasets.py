"""Versioned RDF analytics records. Prefixes never serve as database identities."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rdflib import Graph, URIRef, BNode, Literal
from rdflib.namespace import RDF, RDFS, OWL, SKOS, XSD, split_uri
from psycopg.types.json import Jsonb
from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.execution_guard import ensure_execution_allowed

VERSION = 'rdf-records-v1'
MAX_BYTES = 25 * 1024 * 1024
MAX_TRIPLES = 250000
FORMATS = {'.ttl':'turtle', '.nt':'nt', '.rdf':'xml', '.owl':'xml', '.jsonld':'json-ld'}
NUMERIC = {XSD.integer,XSD.decimal,XSD.double,XSD.float,XSD.int,XSD.long,XSD.short,
           XSD.nonNegativeInteger,XSD.positiveInteger,XSD.nonPositiveInteger,XSD.negativeInteger,
           XSD.unsignedInt,XSD.unsignedLong,XSD.unsignedShort,XSD.byte,XSD.unsignedByte}
META = {str(RDF),str(RDFS),str(OWL),str(SKOS)}


def namespace(iri):
    try:
        return str(split_uri(URIRef(iri))[0])
    except ValueError:
        return iri.rsplit(':',1)[0]+':' if ':' in iri else ''


def label(graph, term):
    values = [str(value) for predicate in (SKOS.prefLabel,RDFS.label) for value in graph.objects(term,predicate) if isinstance(value,Literal)]
    return min(values) if values else str(term).removeprefix(namespace(str(term))) or str(term)


def resolve_source(source_id, artifact_id):
    """Only accept artifacts owned by a catalog version or registered metadata asset."""
    if source_id.startswith('catalog:'):
        record = PostgresRegistry('catalog_products').get(source_id[len('catalog:'):])
        allowed = [item.get('artifact_id') if isinstance(item,dict) else item for item in (record or {}).get('artifacts',[])]
    elif source_id.startswith('metadata:'):
        identity = source_id[len('metadata:'):]
        from .metadata_sources import read_metadata
        record = read_metadata(identity)
        allowed = [(record or {}).get('implementation_ref')]
    else:
        raise ValueError('Choose a versioned catalog source or registered metadata asset')
    if not record or artifact_id not in allowed:
        raise ValueError('The selected RDF artifact does not belong to this registered source')
    if record.get('lifecycle_status',record.get('lifecycle_state')) in {'retired','deprecated','revoked'}:
        raise ValueError('Retired, deprecated or revoked sources cannot supply a new analytics snapshot')
    return {key:record.get(key) for key in ('name','product_id','version','asset_id','revision','updated_at','namespace_uri','namespace_prefix','owner','steward','domain')}


def parse_records(content, rdf_format):
    from backend.ontology_service.catalog import validate_rdf_input
    if len(content)>MAX_BYTES:
        raise ValueError('RDF snapshot exceeds 25 MiB; supply a bounded source partition')
    validate_rdf_input(content,rdf_format)
    class BoundedGraph(Graph):
        def add(self,triple):
            if len(self)>=MAX_TRIPLES:
                raise ValueError('RDF snapshot exceeds 250000 triples; supply a bounded source partition')
            return super().add(triple)
    graph=BoundedGraph().parse(data=content,format=rdf_format)
    if any(isinstance(term,URIRef) and len(str(term).encode('utf-8'))>800 for triple in graph for term in triple):raise ValueError('RDF identity exceeds the indexed 800-byte limit; supply a reviewed identifier mapping')
    terms=[]
    for subject in set(graph.subjects()):
        types=sorted(str(value) for value in graph.objects(subject,RDF.type))
        kind='resource'
        if any(value in {str(OWL.Class),str(RDFS.Class)} for value in types):kind='class'
        elif any(value in {str(RDF.Property),str(OWL.ObjectProperty),str(OWL.DatatypeProperty),str(OWL.AnnotationProperty)} for value in types):kind='property'
        elif str(OWL.NamedIndividual) in types or any(not any(value.startswith(ns) for ns in META) for value in types):kind='individual'
        if isinstance(subject,BNode):kind='blank'
        terms.append((str(subject),namespace(str(subject)),label(graph,subject)[:1000],
                      next((str(value) for value in graph.objects(subject,RDFS.comment) if isinstance(value,Literal)), '')[:4000],kind,types))
    facts=[]
    for index,(subject,predicate,value) in enumerate(graph):
        if index%1000==0:ensure_execution_allowed()
        numeric=None
        if isinstance(value,Literal) and value.datatype in NUMERIC:
            try:
                number=Decimal(str(value))
                if number.is_finite() and len(number.as_tuple().digits)<=1000 and abs(number.adjusted())<=1000:numeric=number
            except InvalidOperation:pass
        facts.append((hashlib.sha256((' '.join(item.n3() for item in (subject,predicate,value))).encode()).hexdigest(),
                      str(subject),str(predicate),'literal' if isinstance(value,Literal) else 'blank' if isinstance(value,BNode) else 'iri',
                      str(value),str(value.datatype or '') if isinstance(value,Literal) else '',value.language or '' if isinstance(value,Literal) else '',numeric))
    return graph,terms,facts


def validate_semantics(graph,payload, *, frozen=False):
    identifier=payload.get('shape_artifact_id')
    if not identifier:return {'status':'not_assessed','reason':'No registered SHACL rules were selected'}
    if not frozen:resolve_source(payload.get('shape_source_id') or payload['source_id'],identifier)
    metadata,path=ArtifactStore().resolve(identifier)
    if path.stat().st_size>1024*1024:raise ValueError('SHACL rules exceed 1 MiB')
    content=path.read_bytes()
    if 'sha256:'+hashlib.sha256(content).hexdigest()!=identifier:raise ValueError('SHACL artifact changed after retention')
    shapes=Graph().parse(data=content,format='turtle')
    if len(shapes)>10000:raise ValueError('SHACL rule graph exceeds 10000 triples')
    sh='http://www.w3.org/ns/shacl#'
    forbidden={'sparql','js','rule','select','ask','construct','function','sparqlconstraint','sparqlfunction','jsconstraint','jsfunction'}
    if any(isinstance(term,URIRef) and ((str(term).startswith(sh) and str(term)[len(sh):].lower() in forbidden) or term==OWL.imports) for triple in shapes for term in triple):
        raise ValueError('Only registered SHACL core constraints are allowed; executable rules/imports are blocked')
    if not any(shapes.subjects(RDF.type,URIRef(sh+'NodeShape'))):raise ValueError('Selected rules contain no SHACL node shapes')
    try:
        from semantica.ontology import OntologyEngine
    except ImportError as exc:
        raise ValueError('Selected SHACL rules require the Semantica capability in this worker runtime; no conformance was established') from exc
    report=OntologyEngine().validate_graph(graph,shacl=shapes.serialize(format='turtle'),explain=False)
    if not report.conforms:raise ValueError('Registered Semantica SHACL checks failed; review the source and rules before preparing data')
    return {'status':'conforms','provider':'Semantica','shape_artifact_id':identifier,
            'scope':'Selected SHACL core shapes only; target coverage and full OWL-DL consistency are not established'}


def materialize(payload,correlation_id):
    artifact_id,source_id=payload.get('artifact_id',''),payload.get('source_id','')
    from .semantic_configuration import preparation_configuration
    baseline,selection,shape=preparation_configuration(payload)
    source=selection['source_version']
    if shape:payload={**payload,'shape_source_id':shape['source_id'],'shape_artifact_id':shape['artifact_id']}
    metadata,path=ArtifactStore().resolve(artifact_id)
    rdf_format=FORMATS.get(Path(metadata.get('filename','')).suffix.lower())
    if not rdf_format:raise ValueError('Choose retained Turtle, N-Triples, RDF/XML or inline-context JSON-LD data')
    if path.stat().st_size>MAX_BYTES:raise ValueError('RDF snapshot exceeds 25 MiB; supply a bounded partition')
    dataset=hashlib.sha256(json.dumps([VERSION,baseline['configuration_id'],source_id,artifact_id,source,payload.get('shape_artifact_id'),payload.get('shape_source_id')],sort_keys=True).encode()).hexdigest()
    registry=PostgresRegistry('semantic_dataset_projection')
    with registry._connect() as db,db.transaction(),db.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('semantic-dataset:'+dataset,))
        cursor.execute('SELECT metadata FROM depo_semantic_datasets WHERE dataset_id=%s',(dataset,))
        previous=cursor.fetchone()
        if previous:return previous[0]
        with path.open('rb') as stream:content=stream.read(MAX_BYTES+1)
        if 'sha256:'+hashlib.sha256(content).hexdigest()!=artifact_id:raise ValueError('RDF source changed after retention; restore its exact content')
        graph,terms,facts=parse_records(content,rdf_format)
        semantic_validation=validate_semantics(graph,payload,frozen=True)
        receipt={'dataset_id':dataset,'name':source.get('name') or metadata.get('filename'),'status':'completed',
                 'configuration_id':baseline['configuration_id'],'configuration_context':baseline['configuration_context'],
                 'source_id':source_id,'artifact_id':artifact_id,'source_version':source,'projection_version':VERSION,
                 'counts':{'entities':sum(term[4]=='individual' for term in terms),'vocabulary_terms':sum(term[4] in {'class','property'} for term in terms),'triples':len(facts)},
                 'semantic_validation':semantic_validation,'shape_source_id':payload.get('shape_source_id'),
                 'execution_actor':payload.get('execution_actor'),'correlation_id':correlation_id,'quality_scope':'RDF syntax and typed projection; no semantic equivalence, unit conversion or OWL-DL claim',
                 'tables':['depo_semantic_terms','depo_semantic_values','depo_semantic_namespaces']}
        ensure_execution_allowed()
        cursor.execute('INSERT INTO depo_semantic_datasets(dataset_id,source_id,artifact_id,projection_version,metadata) VALUES (%s,%s,%s,%s,%s)',(dataset,source_id,artifact_id,VERSION,Jsonb(receipt)))
        with cursor.copy('COPY depo_semantic_terms(dataset_id,iri,namespace_uri,label,description,term_kind,types) FROM STDIN') as copy:
            for index,row in enumerate(terms):
                if index%1000==0:ensure_execution_allowed()
                copy.write_row((dataset,*row))
        aliases={(str(uri),str(prefix or '')) for prefix,uri in graph.namespaces()}
        aliases.update((term[1],'') for term in terms)
        if source.get('namespace_uri'):aliases.add((source['namespace_uri'],source.get('namespace_prefix') or ''))
        if any(len(uri.encode('utf-8'))>800 or len(prefix.encode('utf-8'))>800 for uri,prefix in aliases):raise ValueError('Namespace alias exceeds the indexed 800-byte limit')
        cursor.executemany('INSERT INTO depo_semantic_namespaces(dataset_id,namespace_uri,prefix) VALUES (%s,%s,%s)',[(dataset,*row) for row in sorted(aliases)])
        with cursor.copy('COPY depo_semantic_values(dataset_id,fact_id,subject_iri,property_iri,value_kind,lexical_value,datatype_iri,language,numeric_value) FROM STDIN') as copy:
            for index,row in enumerate(facts):
                if index%1000==0:ensure_execution_allowed()
                copy.write_row((dataset,*row))
        ensure_execution_allowed()
    return receipt


def execute_materialization(runner,payload,*,correlation_id):
    receipt=materialize(payload,correlation_id)
    # The generic run evidence layer retains this result. Failure there is
    # retryable: dataset identity and database transaction prevent duplicate loads.
    return {**receipt,'semantic_dataset':receipt,'job_type':'rdf-semantic-materialize',
            'data_product_draft':{'contract':'semantic-records-product-v1','name':receipt['name'],
              'configuration_id':receipt['configuration_id'],'configuration_context':receipt['configuration_context'],
              'product_kind':'pipeline-evidence','domain':receipt['source_version'].get('domain') or 'semantic-engineering',
              'analytics_readiness':'typed-records-available' if receipt['counts']['entities'] else 'vocabulary-only; business instances required',
              'quality_status':'requires_review','sources':[{'artifact_id':receipt['artifact_id'],'dataset_id':receipt['dataset_id'],'source_id':receipt['source_id'],'configuration_id':receipt['configuration_id']}],
              'artifacts':[{'artifact_id':receipt['artifact_id'],'kind':'rdf-source'}],
              'publication_requirements':['Approved semantic release','Data-product steward approval']}}
