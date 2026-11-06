"""Grounding rules for review-only ontology questions."""
from .input_contracts import validate

REVIEW_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['questions', 'limitations'], 'properties': {
    'questions': {'type': 'array', 'maxItems': 3, 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['question', 'evidence_iris'], 'properties': {'question': {'type': 'string', 'minLength': 1, 'maxLength': 600},
        'evidence_iris': {'type': 'array', 'minItems': 1, 'maxItems': 5, 'items': {'type': 'string'}}}}},
    'limitations': {'type': 'string', 'minLength': 1, 'maxLength': 1200}}}


def validate_review(review, evidence):
    validate(review, REVIEW_SCHEMA, REVIEW_SCHEMA)
    iris = {term['iri'] for term in evidence.get('terms', [])}
    for question in review['questions']:
        if any(iri not in iris for iri in question['evidence_iris']):
            raise ValueError('Ontology review cited a term outside the supplied evidence')
    return review
