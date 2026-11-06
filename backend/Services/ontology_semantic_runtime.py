"""Asserted RDF inspection and Semantica structural validation, without remote imports.

The ontology service owns the required Semantica dependency. Lightweight converter
services may extract asserted structure with RDFLib before canonical registration.
Neither inspection nor Semantica's structural validator proves OWL consistency.
"""
from pathlib import Path
from collections import Counter
from dataclasses import asdict, is_dataclass

from rdflib import Graph, URIRef
from rdflib.exceptions import ParserError
from rdflib.namespace import RDF, RDFS, OWL, SKOS, XSD


def _fragment(value):
    return str(value).rstrip('/').rsplit('#', 1)[-1].rsplit('/', 1)[-1]


class OntologySemanticRuntime:
    @staticmethod
    def is_available():
        return True  # Asserted inspection is always provided by required RDFLib.

    @staticmethod
    def inspect_ontology(file_path, prefix=''):
        from backend.ontology_service.catalog import OntologyCatalog, validate_rdf_input
        from backend.depo_platform.upload_limits import ontology_upload_limit
        empty = {key: [] for key in ('classes','object_properties','datatype_properties','annotation_properties','individuals','subclass_edges')}
        try:
            with Path(file_path).open('rb') as source:
                content = source.read(ontology_upload_limit() + 1)
            retained_format = {'.nt': 'nt', '.n3': 'n3'}.get(Path(file_path).suffix.lower())
            if retained_format:
                validate_rdf_input(content, retained_format)
                graph = Graph().parse(data=content, format=retained_format)
                if not graph:
                    raise ValueError('Ontology artifact contains no RDF triples')
            else:
                parsed = OntologyCatalog._parse_ontology(content, Path(file_path).name)
                graph = Graph().parse(data=content, format=parsed['rdf_format'])
        except (ValueError, OSError, SyntaxError, ParserError):
            return {**empty, 'status':'unsupported', 'engine':'rdflib', 'available':True,
                    'summary':{key:0 for key in (*empty, 'triple_count')},
                    'diagnostics':[{'severity':'error','category':'rdf_parse','message':'The retained artifact could not be read as supported RDF. Check its syntax, size and access.'}],
                    'reasoning_mode':'asserted_semantic_inspection','deductive_reasoner_executed':False,'consistency_verified':False}

        def ref(value):
            label = next((str(label) for predicate in (SKOS.prefLabel, RDFS.label) for label in graph.objects(value, predicate) if str(label).strip()), _fragment(value))
            return {'iri':str(value),'local_name':_fragment(value),'label':label,'ontology_prefix':prefix}

        def refs(subject, predicate):
            # Anonymous restrictions are not named classes or stable graph identities.
            return [ref(value) for value in sorted(set(graph.objects(subject,predicate)), key=str)
                    if isinstance(value, URIRef)]

        def definition(subject):
            return next((str(value) for predicate in (SKOS.definition,RDFS.comment) for value in graph.objects(subject,predicate) if str(value).strip()), '')

        classes = {value for kind in (OWL.Class,RDFS.Class) for value in graph.subjects(RDF.type,kind) if isinstance(value,URIRef) and value not in {OWL.Thing,OWL.Nothing}}
        # Retain named schema references even when their declaration is supplied
        # by a companion ontology. Do not load imports or add inferred triples.
        for child, parent in graph.subject_objects(RDFS.subClassOf):
            classes.update(value for value in (child, parent) if isinstance(value, URIRef))
        classes.update(value for value in graph.objects(None, RDFS.domain) if isinstance(value, URIRef))
        for prop in graph.subjects(RDF.type, OWL.ObjectProperty):
            classes.update(value for value in graph.objects(prop, RDFS.range) if isinstance(value, URIRef))
        classes = {value for value in classes if value not in {OWL.Thing, OWL.Nothing}
                   and not str(value).startswith(str(XSD)) and (value, RDF.type, RDFS.Datatype) not in graph}
        class_rows = [{**ref(value),'parents':refs(value,RDFS.subClassOf),'definition':definition(value)} for value in sorted(classes,key=str)]
        edges = [{'source':str(child),'target':str(parent),'source_label':ref(child)['label'],'target_label':ref(parent)['label'],'type':'subClassOf'}
                 for child in sorted(classes,key=str) for parent in sorted(set(graph.objects(child,RDFS.subClassOf)),key=str)
                 if isinstance(parent, URIRef)]

        def properties(kind):
            return [{**ref(value),'domain':refs(value,RDFS.domain),'range':refs(value,RDFS.range),'definition':definition(value)}
                    for value in sorted(set(graph.subjects(RDF.type,kind)),key=str) if isinstance(value,URIRef)]

        objects, datatypes, annotations = properties(OWL.ObjectProperty), properties(OWL.DatatypeProperty), properties(OWL.AnnotationProperty)
        individuals = {value for value in graph.subjects(RDF.type,OWL.NamedIndividual) if isinstance(value,URIRef)}
        individuals |= {value for kind in classes for value in graph.subjects(RDF.type,kind) if isinstance(value,URIRef)}
        individual_rows = [{**ref(value),'types':[row for row in refs(value,RDF.type) if row['iri']!=str(OWL.NamedIndividual)],'definition':definition(value)} for value in sorted(individuals,key=str)]
        connected = {edge[key] for edge in edges for key in ('source','target')}
        orphans = [row for row in class_rows if row['iri'] not in connected]
        missing = [row for row in (*objects,*datatypes) if not row['domain'] or not row['range']]
        duplicates = [label for label,count in Counter(row['label'].casefold() for row in class_rows).items() if count>1]
        diagnostics = []
        for category,items,message in [('property',missing,'Some properties are missing explicit domain or range.'),('class',orphans,'Some classes have no asserted subclass links.'),('class',duplicates,'Duplicate class labels were found.')]:
            if items: diagnostics.append({'severity':'warning','category':category,'message':message,'items':items[:50]})
        validation = {'status':'not_executed','scope':'structure_only','message':'Semantica validation is owned by the ontology service.'}
        engine = 'rdflib'
        try:
            from semantica.ontology import OntologyEngine
        except ModuleNotFoundError as exc:
            if exc.name != 'semantica':
                raise  # Report a broken installed dependency rather than disguising it.
        else:
            result = OntologyEngine(base_uri='https://depo.local/ontology/',min_occurrences=1).validate({'classes':class_rows,'properties':objects+datatypes+annotations})
            details = asdict(result) if is_dataclass(result) else result.model_dump() if hasattr(result,'model_dump') else vars(result)
            validation = {'status':'passed' if details.get('valid') is True else 'failed','scope':'structure_only',
                          'errors':[str(value) for value in details.get('errors',[])], 'warnings':[str(value) for value in details.get('warnings',[])]}
            engine = 'semantica'
        return {'status':'success','engine':engine,'available':True,'ontology_iri':next((str(value) for value in graph.subjects(RDF.type,OWL.Ontology)),''),
                'classes':class_rows,'object_properties':objects,'datatype_properties':datatypes,'annotation_properties':annotations,
                'individuals':individual_rows,'subclass_edges':edges,'diagnostics':diagnostics,'structural_validation':validation,
                'reasoning_mode':'asserted_semantic_inspection','deductive_reasoner_executed':False,'consistency_verified':False,
                'summary':{'classes':len(class_rows),'object_properties':len(objects),'datatype_properties':len(datatypes),'annotation_properties':len(annotations),
                           'individuals':len(individual_rows),'subclass_edges':len(edges),'orphan_classes':len(orphans),
                           'properties_missing_domain_or_range':len(missing),'duplicate_class_labels':len(duplicates),'triple_count':len(graph)}}

    @classmethod
    def extract_taxonomy(cls, file_path, prefix=''):
        result = cls.inspect_ontology(file_path,prefix)
        nodes, edges, identities = [], [], {}
        for kind,key in [('class','classes'),('object-property','object_properties'),('datatype-property','datatype_properties'),('annotation-property','annotation_properties')]:
            for row in result[key]:
                identity = row['iri']  # Full IRI keeps same-local-name terms distinct.
                identities[row['iri']] = identity
                nodes.append({'term_id':identity,'uri':row['iri'],'label':row['label'],'definition':row.get('definition',''),'ontology_prefix':prefix,'source':'semantic-'+kind})
        for row in result['subclass_edges']:
            edges.append({'source_term':identities.get(row['source'],row['source']),'target_term':identities.get(row['target'],row['target']),
                          'source_label':row['source_label'],'target_label':row['target_label'],'mapping_type':'subClassOf'})
        return {'source':result['engine'],'nodes':nodes,'edges':edges,'triple_count':result['summary'].get('triple_count',0),
                'status':result['status'],'structural_validation':result.get('structural_validation',{}),'summary':result['summary']}
