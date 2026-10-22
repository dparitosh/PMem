"""Bounded, deterministic alignment evidence. Scores never authorize consolidation."""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from rdflib import URIRef, RDF, RDFS, OWL
from rdflib.namespace import SKOS

POLICY = 'lexical-context-v2'
MIN_SCORE = 0.55
MAX_COMPARISONS = 100000
MAX_CANDIDATES = 200


def tokens(value):
    value = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(value))
    return set(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value).casefold()))


def grams(value):
    text = ' '.join(sorted(tokens(value)))
    return {text[i:i + 3] for i in range(max(0, len(text) - 2))}


def dice(left, right):
    return 2 * len(left & right) / (len(left) + len(right)) if left and right else 0.0


def inventory(graph):
    kinds = {OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty}
    declared = defaultdict(set)
    for subject, kind in graph.subject_objects(RDF.type):
        if isinstance(subject, URIRef) and kind in kinds:
            declared[subject].add(OWL.Class if kind == RDFS.Class else kind)
    result = []
    for subject in sorted(declared, key=str):
        labels = sorted({str(value)[:512] for predicate in (RDFS.label, SKOS.prefLabel, SKOS.altLabel) for value in graph.objects(subject, predicate)})
        local = str(subject).rsplit('#', 1)[-1].rsplit('/', 1)[-1].rsplit(':', 1)[-1]
        labels = labels[:8] or [local[:512]]
        def refs(predicate):
            return sorted(str(value) for value in graph.objects(subject, predicate) if isinstance(value, URIRef))[:20]
        domains, ranges = refs(RDFS.domain), refs(RDFS.range)
        properties = sorted(str(value) for value in graph.subjects(RDFS.domain, subject) if isinstance(value, URIRef))[:40]
        definitions = sorted({str(value)[:2048] for predicate in (RDFS.comment, SKOS.definition) for value in graph.objects(subject, predicate)})[:5]
        def context_terms(values):
            return set().union(*(tokens(value.rsplit('#', 1)[-1].rsplit('/', 1)[-1].rsplit(':', 1)[-1]) for value in values))
        context = [context_terms(values) for values in (domains, ranges, properties)]
        result.append(dict(iri=str(subject), kinds=frozenset(declared[subject]), labels=labels,
            tokens=set().union(*(tokens(label) for label in labels)),
            grams=set().union(*(grams(label) for label in labels)),
            definitions=definitions, context=context, domains=domains, ranges=ranges, properties=properties))
    return result


def match_entities(source_graph, target_graph):
    source, target = inventory(source_graph), inventory(target_graph)
    index = defaultdict(list)
    for i, term in enumerate(target):
        for key in term['tokens'] | {f'~{value}' for value in term['grams']}:
            index[(term['kinds'], key)].append(i)
    proposals, comparisons, truncated = [], 0, False
    for left in source:
        votes = defaultdict(int)
        for key in sorted(left['tokens'] | {f'~{value}' for value in left['grams']}):
            bucket = index.get((left['kinds'], key), [])
            # Broad grams are not discriminating; shared tokens still admit candidates.
            if len(bucket) > 200:
                truncated = True
                continue
            for i in bucket: votes[i] += 1
        ranked = sorted(votes, key=lambda i: (-votes[i], target[i]['iri']))
        if len(ranked) > 100: truncated = True
        for i in ranked[:100]:
            if comparisons >= MAX_COMPARISONS:
                truncated = True
                break
            comparisons += 1
            right = target[i]
            if left['iri'] == right['iri']: continue
            label = max(max(dice(tokens(a), tokens(b)), SequenceMatcher(None,
                ' '.join(sorted(tokens(a))), ' '.join(sorted(tokens(b))), autojunk=False).ratio())
                for a in left['labels'] for b in right['labels'])
            ngram = max(dice(grams(a), grams(b)) for a in left['labels'] for b in right['labels'])
            definition = dice(tokens(' '.join(left['definitions'])), tokens(' '.join(right['definitions'])))
            role_pairs = [(a, b) for a, b in zip(left['context'], right['context']) if a or b]
            context = sum(dice(a, b) for a, b in role_pairs) / len(role_pairs) if role_pairs else 0
            score = .5 * label + .3 * ngram + .1 * definition + .1 * context
            if max(label, ngram) < .45 or score < MIN_SCORE: continue
            evidence = lambda term: {key: term[key] for key in ('definitions', 'domains', 'ranges', 'properties')}
            proposals.append(dict(source_iri=left['iri'], target_iri=right['iri'],
                source_label=left['labels'][0], target_label=right['labels'][0],
                kind=', '.join(sorted(str(kind).rsplit('#', 1)[-1] for kind in left['kinds'])),
                confidence_score=round(score, 4), score_policy=POLICY,
                score_components={'label_similarity': round(label, 4), 'character_trigrams': round(ngram, 4),
                    'definitions': round(definition, 4), 'property_context': round(context, 4)},
                source_evidence=evidence(left), target_evidence=evidence(right),
                reason='Weighted lexical and structural similarity; heuristic score, not a probability. Semantic equivalence requires review.',
                requires_review=True, proposed_relation='unverified'))
        if comparisons >= MAX_COMPARISONS: break
    proposals.sort(key=lambda row: (-row['confidence_score'], row['source_iri'], row['target_iri']))
    by_source, by_target = defaultdict(list), defaultdict(list)
    for row in proposals:
        by_source[row['source_iri']].append(row['confidence_score'])
        by_target[row['target_iri']].append(row['confidence_score'])
    for row in proposals:
        row['ambiguous'] = any(len(scores) > 1 and abs(sorted(scores, reverse=True)[0] - sorted(scores, reverse=True)[1]) < .05
            for scores in (by_source[row['source_iri']], by_target[row['target_iri']]))
    return proposals[:MAX_CANDIDATES], {'policy': POLICY, 'minimum_score': MIN_SCORE,
        'weights': {'label_similarity': .5, 'character_trigrams': .3, 'definitions': .1, 'property_context': .1},
        'comparisons': comparisons, 'returned': min(len(proposals), MAX_CANDIDATES),
        'truncated': truncated or len(proposals) > MAX_CANDIDATES,
        'limitations': ['Heuristic similarity is not semantic equivalence or calibrated probability.',
            'Missing annotations contribute zero; language and business context require review.',
            'Candidate blocking and output limits can omit matches; no automatic consolidation.']}
