"""Explicit mapping checks over retained RDF evidence, without inferred approval."""
from collections import Counter


def check_mapping(source, term, summary, duplicates):
    details = source if isinstance(source, dict) else {}
    checks = {}
    checks['class_existence_check'] = 'passed' if term['kind'] == 'Class' else 'not_applicable'
    checks['property_type_check'] = 'passed' if term['kind'] in {'Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty'} else 'failed'
    scope = summary.get('ontology_iris') or []
    expected_scope = details.get('ontology_iri')
    checks['scope_check'] = ('passed' if expected_scope in scope else 'failed') if expected_scope else 'not_supplied'
    checks['duplicate_check'] = 'failed' if duplicates else 'passed'
    datatype = details.get('datatype_iri')
    checks['datatype_compatibility'] = 'not_applicable' if term['kind'] != 'DatatypeProperty' else (
        ('passed' if datatype in term.get('ranges', []) else 'failed') if datatype else 'not_supplied')
    if term['kind'] in {'ObjectProperty', 'DatatypeProperty'}:
        expected = [(details.get('domain_iri'), term.get('domains', [])),
                    (details.get('range_iri'), term.get('ranges', []))]
        supplied = [(value, retained) for value, retained in expected if value]
        if any(value not in retained for value, retained in supplied):
            checks['domain_range_compatibility'] = 'failed'
        elif len(supplied) < len(expected):
            checks['domain_range_compatibility'] = 'not_supplied'
        elif any(len(retained) != 1 for _, retained in expected):
            checks['domain_range_compatibility'] = 'reasoning_required'
        else:
            checks['domain_range_compatibility'] = 'passed'
    else:
        checks['domain_range_compatibility'] = 'not_applicable'
    checks['human_approval'] = 'required'
    return checks


def source_duplicates(metadata):
    def name(value):
        return str(value.get('name') or value.get('label') or value.get('source') or '') if isinstance(value, dict) else str(value)
    return {field: Counter(name(value).strip().casefold() for value in values)
            for field, values in metadata.items() if isinstance(values, list)}
