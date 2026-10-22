"""Deterministic evidence for the existing Governor / Steward workflow.

Policies never rewrite source IRIs, downgrade predicates or manufacture facts.
The model explains this evidence; publication enforces it independently.
"""
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, URIRef, RDF, RDFS, OWL, Namespace
from rdflib.namespace import SKOS, DCTERMS, XSD

VERSION = 'steward-governance-v1'
PROV = Namespace('http://www.w3.org/ns/prov#')
KINDS = {OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.NamedIndividual}
EDITORIAL = {RDFS.label, RDFS.comment, SKOS.definition, SKOS.altLabel, DCTERMS.description}


def policy():
    profile = os.getenv('ONTOLOGY_GOVERNANCE_PROFILE', 'imported_standard').strip()
    if profile not in {'imported_standard', 'enterprise_curated'}:
        raise ValueError('Choose imported_standard or enterprise_curated governance profile')
    rules = {'profile': profile, 'require_definitions': profile == 'enterprise_curated',
             'upper_class_iris': [], 'approved_identity_pairs': [], 'identity_context_predicates': [],
             'require_batch_provenance': True}
    filename = os.getenv('ONTOLOGY_GOVERNANCE_POLICY_FILE', '').strip()
    if filename:
        with Path(filename).open('rb') as handle: content = handle.read(65537)
        if len(content) > 65536: raise ValueError('Governance policy exceeds 64 KiB')
        extra = json.loads(content)
        if not isinstance(extra, dict) or set(extra) - (set(rules) - {'profile'}):
            raise ValueError('Governance policy has unsupported fields')
        rules.update(extra)
    for field in ('require_definitions', 'require_batch_provenance'):
        if type(rules[field]) is not bool: raise ValueError('Governance policy flags must be booleans')
    for field in ('upper_class_iris', 'identity_context_predicates'):
        if not isinstance(rules[field], list) or len(rules[field]) > 100 or any(not isinstance(x, str) or not x.startswith(('http://', 'https://', 'urn:')) for x in rules[field]):
            raise ValueError('Governance policy requires bounded absolute IRI lists')
    pairs = rules['approved_identity_pairs']
    if not isinstance(pairs, list) or len(pairs) > 1000 or any(not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(x, str) or not x.startswith(('http://', 'https://', 'urn:')) for x in pair) for pair in pairs):
        raise ValueError('Approved identities require pairs of absolute IRIs')
    rules['version'] = VERSION
    rules['evaluator_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rules['sha256'] = hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()
    return rules


def change_impact(added, removed):
    if not added and not removed: return 'NONE'
    if all(predicate in EDITORIAL for _, predicate, _ in added | removed): return 'PATCH'
    restrictive = {OWL.disjointWith, OWL.equivalentClass, OWL.equivalentProperty, OWL.sameAs,
                   OWL.minCardinality, OWL.maxCardinality, OWL.cardinality, RDFS.domain, RDFS.range}
    new_classes = {subject for subject, predicate, kind in added if predicate == RDF.type and kind in {OWL.Class, RDFS.Class}}
    if removed or any(predicate in restrictive or (predicate == RDFS.subClassOf and subject not in new_classes) for subject, predicate, _ in added): return 'MAJOR'
    return 'MINOR'


def _identity_findings(left, right, rules, emit, *, subject=None):
    if left == right: return
    approved = {tuple(sorted(pair)) for pair in rules['approved_identity_pairs']}
    if tuple(sorted((str(left), str(right)))) not in approved:
        emit(subject or left, 'IDENTITY_CONFLATION', 'BLOCKER',
             'Identity requires domain review. Retain the original predicate and propose an evidenced relation; no automatic SKOS downgrade.', related=[str(right)])


def audit_ontology(record):
    rules = policy()
    turtle = record['turtle']
    graph = Graph().parse(data=turtle, format='turtle')
    subjects = {subject for subject, kind in graph.subject_objects(RDF.type) if kind in KINDS and isinstance(subject, URIRef)}
    findings, categories, blocked = [], Counter(), set()
    total_findings = 0
    def emit(subject, category, severity, diagnosis, related=None):
        nonlocal total_findings
        total_findings += 1; categories[category] += 1
        if severity == 'BLOCKER': blocked.add(str(subject))
        if len(findings) < 200:
            actions = {'IDENTITY_CONFLATION':'Keep these resources separate until a domain reviewer establishes identity; remove the consolidation or revise the proposal.',
                       'FOUNDATIONAL_ALIGNMENT':'Review the configured foundation and supply an approved subclass bridge in a new draft.',
                       'MISSING_METADATA':'Use source documentation to prepare a reviewed label or definition; do not invent one.',
                       'POLICY_CHANGED':'Generate a new plan under the current policy.',
                       'SHACL_OR_OWL_VIOLATION':'Open the validation report, correct the draft and regenerate the plan.',
                       'MISSING_PROVENANCE':'Restore the retained source artifacts and their hashes before retrying.'}
            findings.append({'subject_uri': str(subject), 'issue_category': category, 'severity': severity,
                             'diagnosis': diagnosis, 'action_taken': 'QUARANTINED' if severity == 'BLOCKER' else 'REVIEW_REQUIRED',
                             'related_iris': related or [], 'proposed_fix_turtle': None, 'recommended_action': actions.get(category, 'Inspect the cited source evidence with the domain steward; retain the current identifiers until reviewed.')})
    complete = len(subjects) <= 100000 and len(graph) <= 1000000
    if not complete:
        emit('urn:pmem:governance:coverage', 'VALIDATION_COVERAGE', 'BLOCKER', 'Graph exceeds the bounded governance audit budget. Partition the review.')
    parents = defaultdict(set)
    for child, parent in graph.subject_objects(RDFS.subClassOf):
        if isinstance(child, URIRef) and isinstance(parent, URIRef): parents[child].add(parent)
    roots = {URIRef(value) for value in rules['upper_class_iris']}
    # Reverse reachability checks configured foundation alignment in linear time.
    descendants = defaultdict(set)
    for child, values in parents.items():
        for parent in values: descendants[parent].add(child)
    aligned, pending = set(roots), list(roots)
    while pending:
        for child in descendants[pending.pop()]:
            if child not in aligned: aligned.add(child); pending.append(child)
    # OWL permits cycles; surface them as review findings rather than inventing inconsistency.
    color = {}
    for start in list(parents):
        if color.get(start): continue
        color[start] = 1
        stack = [(start, iter(parents[start]))]
        while stack:
            node, edges = stack[-1]
            try: parent = next(edges)
            except StopIteration:
                color[node] = 2; stack.pop(); continue
            if color.get(parent) == 1 and node != parent:
                emit(node, 'TAXONOMY_REVIEW', 'WARNING', 'Subclass cycle detected; review whether the intended meaning is class equivalence.', related=[str(parent)])
            elif not color.get(parent):
                color[parent] = 1; stack.append((parent, iter(parents[parent])))
    duplicate_properties = defaultdict(list)
    for subject in sorted(subjects, key=str)[:100000]:
        kinds = set(graph.objects(subject, RDF.type))
        if not any(graph.objects(subject, RDFS.label)):
            emit(subject, 'MISSING_METADATA', 'BLOCKER' if rules['require_definitions'] else 'WARNING', 'A human-readable rdfs:label is missing; preserve the source IRI.')
        if not any(graph.objects(subject, SKOS.definition)):
            emit(subject, 'MISSING_METADATA', 'BLOCKER' if rules['require_definitions'] else 'WARNING', 'A reviewed skos:definition is missing. Class definitions need genus/differentia; property definitions need relationship semantics.')
        if kinds & {OWL.Class, RDFS.Class}:
            if roots and subject not in aligned:
                emit(subject, 'FOUNDATIONAL_ALIGNMENT', 'BLOCKER', 'No subclass path to a configured approved foundation category was found.')
            if OWL.NamedIndividual in kinds:
                emit(subject, 'MODELING_REVIEW', 'WARNING', 'Class/individual punning requires domain review; it is not automatically an OWL error.')
            if subject in parents[subject]:
                emit(subject, 'TAXONOMY_REVIEW', 'WARNING', 'Self-subclass declaration detected. Cycles and multiple inheritance need contextual review, not automatic rejection.')
        if kinds & {OWL.ObjectProperty, OWL.DatatypeProperty}:
            key = (tuple(sorted(str(x) for x in kinds)), tuple(sorted(str(x).casefold() for x in graph.objects(subject, RDFS.label))),
                   tuple(sorted(str(x) for x in graph.objects(subject, RDFS.domain))), tuple(sorted(str(x) for x in graph.objects(subject, RDFS.range))))
            if key[1]: duplicate_properties[key].append(subject)
        if any(str(value).lower() in {'true', '1'} for value in graph.objects(subject, OWL.deprecated)) and not any(graph.objects(subject, DCTERMS.isReplacedBy)):
            emit(subject, 'DEPRECATION_REVIEW', 'WARNING', 'Deprecated term has no replacement link. Review whether replacement or retirement without replacement is intended.')
    for group in duplicate_properties.values():
        if len(group) > 1: emit(group[0], 'PROPERTY_REUSE_REVIEW', 'WARNING', 'Properties share labels and declared domains/ranges; review reuse without assuming equivalence.', related=[str(x) for x in group[1:20]])
    for left, right in graph.subject_objects(OWL.sameAs):
        _identity_findings(left, right, rules, emit)
        if left != right:
            for predicate in rules['identity_context_predicates']:
                first = {value.n3() for value in graph.objects(left, URIRef(predicate))}
                second = {value.n3() for value in graph.objects(right, URIRef(predicate))}
                if not first or not second:
                    emit(left, 'MISSING_IDENTITY_CONTEXT', 'BLOCKER', 'An authored identity assertion lacks configured lifecycle/viewpoint evidence.', related=[str(right), predicate])
                elif first != second:
                    emit(left, 'IDENTITY_CONFLATION', 'BLOCKER', 'An authored identity assertion crosses a configured lifecycle/viewpoint partition; an allowlist cannot override it.', related=[str(right), predicate])
    for item in record.get('mapping_evidence', []):
        if item.get('individual'):
            _identity_findings(item['source_iri'], item['target_iri'], rules, emit)
        for predicate in rules['identity_context_predicates']:
            left, right = item.get('source_context', {}).get(predicate), item.get('target_context', {}).get(predicate)
            if not left or not right:
                emit(item['source_iri'], 'MISSING_IDENTITY_CONTEXT', 'BLOCKER', 'Configured lifecycle/viewpoint evidence is missing for a selected mapping.', related=[item['target_iri'], predicate])
            elif left != right:
                emit(item['source_iri'], 'IDENTITY_CONFLATION', 'BLOCKER', 'Selected consolidation crosses a configured lifecycle/viewpoint partition.', related=[item['target_iri'], predicate])
    if rules['require_batch_provenance'] and (not record.get('source_ontology_ids') or not record.get('sources') or {source.get('ontology_id') for source in record.get('sources', [])} != set(record.get('source_ontology_ids', [])) or any(not isinstance(source.get('artifact_sha256'), str) or len(source['artifact_sha256']) != 64 for source in record.get('sources', []))):
        emit('urn:pmem:governance:provenance', 'MISSING_PROVENANCE', 'BLOCKER', 'Retained source IDs and content hashes are required.')
    for subject in record.get('removed_active_iris', []):
        emit(subject, 'ACTIVE_IDENTITY_REMOVAL', 'BLOCKER', 'An active target term would lose its declaration. Use a reviewed deprecation and replacement plan.')
    from .merge_validation import explicit_conflicts
    declared_conflicts = explicit_conflicts(graph)
    if record.get('governance_policy_sha256') and record['governance_policy_sha256'] != rules['sha256']:
        emit('urn:pmem:governance:policy', 'POLICY_CHANGED', 'BLOCKER', 'Governance rules changed after plan preparation. Regenerate and review the plan.')
    reviewed_pairs = [(item.get('source_iri'), item.get('target_iri')) for item in record.get('changes', {}).get('entity_mappings', [])]
    evidence_pairs = [(item.get('source_iri'), item.get('target_iri')) for item in record.get('mapping_evidence', [])]
    if Counter(reviewed_pairs) != Counter(evidence_pairs):
        emit('urn:pmem:governance:identity', 'VALIDATION_COVERAGE', 'BLOCKER', 'Retained identity evidence does not cover every selected mapping. Regenerate the plan.')
    checks = record.get('semantic_checks') or {}
    if checks.get('shacl_conforms') is False or checks.get('inferred_conflicts') or record.get('conflicts') or declared_conflicts:
        emit('urn:pmem:governance:validation', 'SHACL_OR_OWL_VIOLATION', 'BLOCKER', 'Retained semantic validation has blocking findings; inspect its report.')
    validation_pending = checks.get('shacl_conforms') is not True or checks.get('owl_rl_performed') is not True
    graph_hash = hashlib.sha256(turtle.encode()).hexdigest()
    audit_id = hashlib.sha256(json.dumps([graph_hash, rules['sha256'], record.get('sources'), record.get('mapping_evidence'), checks], sort_keys=True, default=str).encode()).hexdigest()
    report = {'audit_id': audit_id, 'evaluator': 'deterministic-steward-policy', 'policy_version': VERSION,
              'policy_sha256': rules['sha256'], 'profile': rules['profile'], 'artifact_sha256': graph_hash,
              'source_ontology_ids': record.get('source_ontology_ids', []), 'sources': record.get('sources', []),
              'overall_verdict': 'REJECTED' if blocked else 'PENDING_VALIDATION' if validation_pending else 'APPROVED',
              'recommended_version_bump': record.get('recommended_version_bump', 'NONE'),
              'metrics': {'total_triples_evaluated': len(graph) if complete else None, 'total_triples_in_graph': len(graph), 'entities_evaluated': min(len(subjects), 100000),
                          'findings': total_findings, 'quarantined_subjects': len(blocked), 'auto_remediated_count': 0},
              'coverage': {'complete': complete, 'shacl': 'pending' if validation_pending else 'retained-result',
                           'shape_digests': checks.get('shape_digests', []), 'owl_rl_performed': checks.get('owl_rl_performed', False),
                           'full_owl_dl_consistency_established': False, 'foundation_alignment': 'configured' if roots else 'not_configured',
                           'linguistic_and_role_modeling': 'human_review', 'partial_graph_commit': 'disabled'},
              'findings_by_category': dict(categories), 'violations_and_remediations': findings,
              'findings_truncated': total_findings > len(findings), 'automatic_changes_applied': False}
    provenance = Graph()
    entity, activity = URIRef('urn:pmem:audit:' + audit_id), URIRef('urn:pmem:steward-evaluation:' + audit_id)
    provenance.add((entity, RDF.type, PROV.Entity)); provenance.add((activity, RDF.type, PROV.Activity))
    provenance.add((entity, PROV.wasGeneratedBy, activity))
    artifact = URIRef('urn:pmem:merge-preview:' + str(record.get('preview_id') or graph_hash))
    provenance.add((entity, PROV.wasDerivedFrom, artifact))
    if record.get('created_at'):
        provenance.add((artifact, PROV.generatedAtTime, Literal(record['created_at'], datatype=XSD.dateTime)))
    for source in record.get('source_ontology_ids', []): provenance.add((entity, PROV.wasDerivedFrom, URIRef('urn:pmem:ontology:' + quote(source, safe=''))))
    report['provenance_turtle'] = provenance.serialize(format='turtle')
    return report


def bridge_findings(row):
    """Only declared identity predicates trigger identity adjudication.

    Instance classification is not identity. Never fabricate ABox SHACL coverage
    from a classification candidate or its heuristic similarity score.
    """
    predicate = row.get('predicate') or row.get('mapping_predicate') or row.get('mapping_type')
    if predicate in {str(OWL.sameAs), 'owl:sameAs', 'sameAs'}:
        return ['identity_requires_domain_review']
    return []


def audit_ontology_bounded(record):
    """Keep parsing and graph traversal outside the long-lived service process."""
    import subprocess
    import sys
    from backend.depo_platform.network import bounded_timeout_seconds
    from backend.depo_platform.operations import current_operation
    budget = bounded_timeout_seconds('GOVERNANCE_AUDIT_TIMEOUT_SECONDS', default=60, maximum=300)
    operation = current_operation()
    if operation: budget = operation.timeout(budget)
    keys = ('turtle','source_ontology_ids','sources','mapping_evidence','changes','semantic_checks','conflicts',
            'governance_policy_sha256','removed_active_iris','recommended_version_bump','preview_id','created_at')
    payload = json.dumps({key: record[key] for key in keys if key in record}).encode()
    try:
        result = subprocess.run([sys.executable, '-m', 'backend.ontology_service.governance'], input=payload,
                                capture_output=True, timeout=budget, cwd=str(Path(__file__).resolve().parents[2]))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Steward audit timed out; its worker was terminated. Narrow the graph or adjust GOVERNANCE_AUDIT_TIMEOUT_SECONDS.') from exc
    if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
        raise ValueError('Steward audit failed or exceeded its evidence budget. Check retained RDF, governance policy and service logs.')
    try: return json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Steward worker returned invalid evidence; approval remains blocked.') from exc


if __name__ == '__main__':
    import sys
    try:
        report = audit_ontology(json.loads(sys.stdin.buffer.read()))
        content = json.dumps(report).encode()
        if len(content) > 8 * 1024 * 1024: raise ValueError('Evidence budget exceeded')
        sys.stdout.buffer.write(content)
    except Exception:
        # Uploaded RDF and policy text must not leak through child tracebacks.
        sys.stderr.write('Steward governance worker failed; inspect source RDF and policy configuration.\n')
        sys.exit(1)
