"""Bounded retained labels for recorded predicates; no inferred equivalence."""


def read_vocabulary(publisher, predicates, *, ontology_id='', ontology_prefix=''):
    predicates = sorted({value for value in predicates if isinstance(value, str) and value})[:60]
    if not predicates:
        return []
    rows = publisher._session_rows(
        'MATCH (term:OntologyResource) WHERE term.iri IN $predicates '
        'AND NOT term:StagedOntologyResource AND NOT term:RetainedOntologyIdentity '
        "AND ($scope='' OR term.ontology_id=$scope OR term.source_ontology=$scope) "
        "AND ($prefix='' OR term.prefix=$prefix OR term.ontology_prefix=$prefix) "
        'RETURN term.iri AS iri,term.label AS label,term.definition AS description '
        'ORDER BY iri,label LIMIT 100', predicates=predicates, scope=ontology_id, prefix=ontology_prefix)
    return [{key: row.get(key) for key in ('iri','label','description')} for row in rows
            if isinstance(row, dict) and row.get('iri') in predicates and isinstance(row.get('label'), str)]


def unique_label(vocabulary, predicate):
    labels = {row['label'] for row in vocabulary if row.get('iri') == predicate and row.get('label')}
    return next(iter(labels)) if len(labels) == 1 else None
