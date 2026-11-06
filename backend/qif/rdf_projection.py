"""Deterministic schema projection; XSD remains authoritative for lexical facets."""
from collections import Counter
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DC, OWL, XSD


def project_schema_ontology(inspection, prefix):
    if inspection.get('errors'):
        raise ValueError('Cannot generate ontology from an invalid schema inspection')
    terms = inspection['terms']
    owners = Counter(term.namespace for term in terms if term.namespace)
    namespace = owners.most_common(1)[0][0] if owners else f'https://depo.local/ontology/{quote(prefix)}'
    def space(value):
        return Namespace(value if value.endswith(('#', '/')) else value + '#')
    primary = space(namespace)
    # Keep schema identities separate from application-specific annotations.
    annotation = Namespace('https://depo.local/schema-projection#')
    graph = Graph()
    graph.bind(prefix, primary)
    graph.bind('projection', annotation)
    graph.bind('dc', DC)
    ontology = URIRef(namespace)
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, RDFS.label, Literal(f'{prefix} schema ontology')))
    graph.add((ontology, RDFS.comment, Literal('Ontology projected from the supplied XSD schema set. Source XSD validation remains authoritative for lexical and compositor constraints.')))
    graph.add((ontology, OWL.versionInfo, Literal('source-schema-set projection v2')))
    graph.add((ontology, DC.creator, Literal('PMem XSD declaration converter')))
    for source in inspection['source_files']:
        graph.add((ontology, DC.source, Literal(source)))

    declarations = [term for term in terms if term.kind in {'complex_type', 'simple_type', 'element'}]
    declarations_by_name = {term.name: term for term in declarations}
    # Source QName qualification has already made internal names unambiguous.
    # An element and a type of the same QName have separate schema identities.
    type_names = {(t.namespace, t.source_name or t.name) for t in declarations if t.kind != 'element'}
    identities = {}
    for term in declarations:
        local = term.source_name or term.name
        if term.kind == 'element' and (term.namespace, local) in type_names:
            local = 'element/' + local
        identities[term.name] = space(term.namespace or namespace)[quote(local, safe='/')]
    complexes = {term.name for term in declarations if term.kind == 'complex_type'}
    simple = {term.name: term for term in declarations if term.kind == 'simple_type'}
    lexical_lists = set()

    def datatype(name):
        seen = set()
        while name in simple:
            if name in seen:
                raise ValueError(f'Cyclic XSD datatype: {name}')
            seen.add(name)
            term = simple[name]
            if term.variety == 'list':
                lexical_lists.add(term.name)
                # XML list lexical representations are strings, not scalar
                # item values. Never equate a vector/list to xs:double.
                return XSD.string
            if term.variety == 'union':
                raise ValueError(f'XSD union needs explicit datatype mapping: {name}')
            name = term.base
        if name and name in XSD:
            return XSD[name]
        raise ValueError(f'Unresolved XSD property datatype: {name or "missing type"}')

    def metadata(uri, term, description):
        graph.add((uri, RDFS.label, Literal(term.source_name or term.name)))
        graph.add((uri, RDFS.comment, Literal(term.documentation or description)))
        graph.add((uri, DC.source, Literal(term.source)))
        graph.add((uri, annotation.sourceFile, Literal(term.source)))
        if term.namespace:
            graph.add((uri, annotation.schemaNamespace, Literal(term.namespace)))

    for term in declarations:
        uri = identities[term.name]
        # Simple type declarations describe lexical datatypes, not classes of
        # domain objects. The projected property's range is its known base.
        graph.add((uri, RDF.type, RDFS.Datatype if term.kind == 'simple_type' else OWL.Class))
        metadata(uri, term, f"XSD {term.kind.replace('_', ' ')} declaration '{term.source_name or term.name}' in {term.source}.")
        if term.kind != 'simple_type':
            parent = term.base or (term.value_type if term.kind == 'element' else '')
            if parent in complexes and parent != term.name:
                graph.add((uri, RDFS.subClassOf, identities[parent]))

    for term in (term for term in terms if term.kind == 'property'):
        if term.base not in complexes:
            raise ValueError(f'Unresolved XSD property owner: {term.base}')
        owner = identities[term.base]
        owner_term = declarations_by_name[term.base]
        uri = space(owner_term.namespace or namespace)[f'property/{quote(owner_term.source_name or term.base, safe="")}/{quote(term.name, safe="")}']
        metadata(uri, term, f"XSD property '{term.name}' declared by '{owner_term.source_name or term.base}' in {term.source}.")
        graph.add((uri, RDFS.domain, owner))
        if term.value_type in complexes:
            graph.add((uri, RDF.type, OWL.ObjectProperty))
            graph.add((uri, RDFS.range, identities[term.value_type]))
        else:
            graph.add((uri, RDF.type, OWL.DatatypeProperty))
            graph.add((uri, RDFS.range, datatype(term.value_type)))
        graph.add((uri, annotation.sourceType, Literal(term.value_type)))
        graph.add((uri, annotation.minOccurs, Literal(term.min_occurs or '1')))
        graph.add((uri, annotation.maxOccurs, Literal(term.max_occurs or '1')))

    limitations = ['XSD facets, identity constraints and compositor constraints require source XSD validation; no semantic equivalence is inferred.']
    if lexical_lists:
        limitations.append('List-valued simple types preserve their XML lexical representation as xsd:string; item types, order and list facets require source XSD validation.')
    for limitation in limitations:
        graph.add((ontology, annotation.limitation, Literal(limitation)))
    return graph.serialize(format='turtle').encode(), {
        'engine': 'XSD declaration projection', 'projection_version': 2,
        'files_processed': len(inspection['source_files']), 'terms_created': len(terms),
        'classes_created': len(set(graph.subjects(RDF.type, OWL.Class))),
        'properties_created': sum(t.kind == 'property' for t in terms),
        'references_found': len(inspection['references']), 'parse_errors': [],
        'semantic_completeness': 'partial', 'limitations': limitations,
        'lexical_list_types': sorted(lexical_lists),
        'validation_scope': 'Declared types and property ranges resolved; source XSD validation remains required.',
    }
