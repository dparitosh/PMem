"""Evidence coverage checks, independent of model availability or confidence."""
import re


def assess(question, evidence):
    """Retrieval is not a calculation or proof of a business association."""
    # Definitions do not execute an operation. An explicit calculation clause
    # still wins over a descriptive first clause.
    explicit = re.search(r'\b(calculate|compute|sum up|add up)\b', question, re.I)
    definition = re.search(r'\b(define|definition|means?|meaning)\b', question, re.I) or re.match(
        r'\s*(explain|describe)\b', question, re.I)
    quantitative = re.search(r'\b(how many|how much|percentage|percent|average|count of|sum of|total (?:mass|weight|cost|number)|ratio|median)\b', question, re.I)
    if explicit or (quantitative and not definition):
        return {'status': 'unsupported_calculation', 'answerable': False,
                'response': 'I cannot verify that calculation through this Companion retrieval. '
                'Choose an approved analysis with an agreed formula, units and product or revision scope. '
                'A sample of matching records cannot establish a total or KPI. No calculation was executed.'}
    items = [item for item in evidence if item.get('evidence_type') == 'business_answer']
    if items and not any(item.get('rows') for item in items):
        return {'status': 'insufficient_evidence', 'answerable': False, 'response': ''}
    judgment_definition = re.search(r'\b(definition|means?|meaning)\b', question, re.I) or re.match(r'\s*define\b', question, re.I)
    if not judgment_definition and re.search(r'\b(satisfied|satisfies|compliant|complies|interchangeable|safe|manufacturing ready)\b', question, re.I):
        return {'status': 'unsupported_judgment', 'answerable': False,
                'response': 'The retrieved context does not establish requirement satisfaction, compliance or engineering suitability. '
                'An authorized review needs explicit verification evidence for the selected product and revision. Recorded connections alone are insufficient.'}
    for item in items:
        if item.get('intent') != 'parts_with_pmi':
            continue
        rows = item.get('rows') or []
        if any(row.get('association_status') != 'recorded_association' for row in rows):
            return {'status': 'unverified_association', 'answerable': False, 'response': ''}
    return {'status': 'bounded_evidence', 'answerable': True, 'response': ''}
