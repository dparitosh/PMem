"""Deterministic engineering comparisons; absence never establishes compatibility."""
import json
import math
import re
from difflib import SequenceMatcher


def local(value):
    return re.sub(r'[^a-z0-9]', '', re.split(r'[/#]', str(value))[-1].lower())


ALIASES = {
    'material': {'material', 'materialname', 'materialgrade'},
    'diameter': {'diameter', 'nominaldiameter', 'outerdiameter'},
    'length': {'length', 'nominallength'},
    'width': {'width'}, 'height': {'height'},
    'mass': {'mass', 'weight'},
    'tolerance': {'tolerance', 'dimensionaltolerance'},
    'specification': {'specification', 'specificationid', 'standard'},
    'revision': {'revision', 'revisionid'},
    'configuration': {'configuration', 'configurationid', 'variant'},
    'effectivity': {'effectivity', 'effectivitydate'},
}
NUMERIC = {'diameter', 'length', 'width', 'height', 'mass', 'tolerance'}
UNITS = {'mm': ('length', .001), 'cm': ('length', .01), 'm': ('length', 1),
         'in': ('length', .0254), 'inch': ('length', .0254), 'inches': ('length', .0254),
         'um': ('length', .000001), 'µm': ('length', .000001),
         'kg': ('mass', 1), 'g': ('mass', .001), 'lb': ('mass', .45359237), 'lbs': ('mass', .45359237)}


def values(properties):
    """Read exact vocabulary local names, retaining conflicts instead of picking one."""
    properties = properties if isinstance(properties, dict) else {}
    combined = dict(properties)
    raw = properties.get('rdf_properties', {})
    if isinstance(raw, str) and len(raw) <= 262144:
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    if isinstance(raw, dict):
        combined.update(raw)
    output = {}
    for field, aliases in ALIASES.items():
        found = []
        for key, data in combined.items():
            if local(key) not in aliases:
                continue
            for item in data if isinstance(data, list) else [data]:
                value = item.get('value') if isinstance(item, dict) else item
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    continue
                text = str(value).strip()
                if text and len(text) <= 500 and '<' not in text and '{' not in text:
                    unit = item.get('unit') if isinstance(item, dict) else None
                    if not unit:
                        unit = combined.get(str(key) + '_unit') or combined.get(field + '_unit')
                    text += ' ' + unit if isinstance(unit, str) and unit.strip() else ''
                    if text not in found:
                        found.append(text)
        if found:
            output[field] = found
    return output


def declared_relation(properties):
    raw = properties.get('rdf_properties', {})
    if isinstance(raw, str) and len(raw) <= 262144:
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    merged = {**properties, **(raw if isinstance(raw, dict) else {})}
    types = set()
    for key, data in merged.items():
        if local(key) not in {'subtype', 'relationtype', 'relationshiptype'}:
            continue
        for item in data if isinstance(data, list) else [data]:
            types.add(local(item.get('value', '') if isinstance(item, dict) else item))
    return types


def quantity(text, field):
    match = re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Zµ]+)\s*', text)
    if not match:
        return None  # A unitless source value is intentionally not guessed.
    unit = UNITS.get(match[2].lower())
    expected = 'mass' if field == 'mass' else 'length'
    if not unit or unit[0] != expected:
        return None
    number = float(match[1]) * unit[1]
    return number if math.isfinite(number) and number >= 0 else None


def compare(source, candidate):
    a, b = values(source), values(candidate)
    comparisons = []
    for field in ALIASES:
        left, right = a.get(field, []), b.get(field, [])
        state, reason = 'unassessed', 'Missing value on one or both records'
        if len(left) > 1 or len(right) > 1:
            reason = 'Multiple values require a scoped engineering review'
        elif left and right:
            if field in NUMERIC:
                x, y = quantity(left[0], field), quantity(right[0], field)
                if x is None or y is None:
                    reason = 'Explicit compatible units are required'
                else:
                    state = 'match' if math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-12) else 'conflict'
                    reason = 'Compared after conversion to SI units'
            else:
                state = 'match' if left[0].casefold() == right[0].casefold() else 'conflict'
                reason = 'Exact declared value comparison; equivalence is not inferred'
        comparisons.append({'property': field, 'source': left, 'candidate': right, 'status': state, 'reason': reason})
    return comparisons


def name_score(a, b):
    def terms(text):
        return set(re.findall(r'[a-z0-9]+', str(text).casefold()))
    left, right = terms(a), terms(b)
    token = len(left & right) / max(1, len(left | right))
    def grams(text):
        text = re.sub(r'\s+', ' ', str(text).casefold()).strip()
        return {text[i:i+3] for i in range(max(0, len(text)-2))}
    x, y = grams(a), grams(b)
    ngram = len(x & y) / max(1, len(x | y))
    return {'token_jaccard': token, 'character_trigram_jaccard': ngram,
            'sequence_similarity': SequenceMatcher(None, str(a).casefold(), str(b).casefold()).ratio()}


def kind(record):
    """Only declared types/roles classify a business object; names are not types."""
    props = record.get('properties') or {}
    def declared_values(value):
        return value if isinstance(value, (list, tuple, set)) else [value] if isinstance(value, str) else []
    types = [*declared_values(record.get('labels')), *declared_values(props.get('rdf_types')), *declared_values(record.get('mapped_types')),
             props.get('element_type', ''), props.get('semantic_role', '')]
    names = {local(value).removesuffix('type') for value in types}
    groups = [('requirement', {'requirement', 'requirementspecification'}),
              ('process', {'process', 'operation', 'processinstance', 'manufacturingprocess', 'workplan'}),
              ('change', {'change', 'changerequest', 'changenotice', 'engineeringchange'}),
              ('document', {'document', 'specification', 'documentspecification'}),
              ('test', {'test', 'testcase', 'testresult'}),
              ('measurement', {'measurement', 'qualitymeasurement'}),
              ('assembly', {'assembly', 'productassembly'}),
              ('part', {'part', 'product', 'productrevision', 'productinstance', 'component', 'item', 'itemrevision'}),
              ('carrier', {'generalrelation', 'relationshipcarrier'})]
    return next((group for group, members in groups if names & members), 'unclassified')
