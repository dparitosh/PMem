"""Complete SHACL checks with bounded text and core RDF validation evidence.

The standard reporter recursively copies the data surrounding anonymous focus
nodes. Ontology closure graphs contain cycles and large RDF lists; copying that
context is unnecessary for PMem's retained validation decision. Keep every
validation-result triple, but do not copy unrelated data/shape neighborhoods.
"""
from collections import Counter
from rdflib import Graph, BNode, Literal, RDF
from rdflib.namespace import SH
from pyshacl.validator import Validator

REPORT_TEXT_LIMIT = 20000
REPORT_PROFILE_LABELS = {'custom_inferred': 'Custom semantic constraints',
                         'editorial_asserted': 'Authored ontology metadata'}


def combine_summaries(parts):
    severities, components = Counter(), Counter()
    samples, profiles = [], []
    total, truncated = 0, False
    for name, conforms, text, summary in parts:
        total += summary.get('total_results', 0)
        severities.update(summary.get('by_severity', {}))
        components.update(summary.get('by_component', {}))
        truncated = truncated or summary.get('text_truncated', False)
        profiles.append({'profile': name, 'label': REPORT_PROFILE_LABELS.get(name, name), 'conforms': conforms,
                         'total_results': summary.get('total_results', 0)})
        samples.extend({**sample, 'profile': name} for sample in summary.get('results_sample', [])[:100-len(samples)])
    combined_length = sum(len(item[2]) for item in parts)
    if len(parts)>1: combined_length += sum(len(REPORT_PROFILE_LABELS.get(item[0],item[0]))+2 for item in parts)+len(parts)-1
    return {'total_results': total, 'by_severity': dict(severities.most_common(100)),
            'by_component': dict(components.most_common(100)), 'profiles': profiles,
            'results_sample': samples, 'results_sample_limit': 100, 'context_graph_copied': False,
            'text_truncated': bool(truncated or combined_length > REPORT_TEXT_LIMIT),
            'validation_failure': any(item[3].get('validation_failure', False) for item in parts),
            'categories_truncated': len(severities)>100 or len(components)>100 or any(item[3].get('categories_truncated', False) for item in parts)}


class MergeReportValidator(Validator):
    def create_validation_report(self, sg, conforms, results):
        if not conforms and not results:
            raise RuntimeError('A nonconformant SHACL report must have results')
        header = f'Validation Report\nConforms: {conforms}\n'
        if results: header += f'Results ({len(results)}):\n'
        chunks = [header]
        remaining = REPORT_TEXT_LIMIT - len(header)
        ordered = sorted(results, key=lambda result: result[0])
        for description, _, _ in ordered:
            if remaining <= 0: break
            chunks.append(description[:remaining]); remaining -= len(chunks[-1])
        report = Graph()
        for prefix, namespace in sg.graph.namespaces(): report.bind(prefix, namespace)
        root = BNode()
        report.add((root, RDF.type, SH.ValidationReport))
        report.add((root, SH.conforms, Literal(conforms)))
        severities, components = Counter(), Counter()
        samples = []
        for _, node, triples in results:
            report.add((root, SH.result, node))
            sample = {}
            for subject, predicate, value in triples:
                if isinstance(value, tuple): value = value[1]
                report.add((subject, predicate, value))
                if subject != node: continue
                text = str(value)[:500]
                if predicate == SH.resultSeverity:
                    severities[text] += 1; sample['severity'] = text
                elif predicate == SH.sourceConstraintComponent:
                    components[text] += 1; sample['component'] = text
                elif predicate == SH.focusNode: sample['focus'] = text
                elif predicate == SH.resultPath: sample['path'] = text
                elif predicate == SH.resultMessage: sample['message'] = text
            if len(samples) < 100: samples.append(sample)
        self.report_summary = {
            'total_results': len(results), 'by_severity': dict(severities.most_common(100)),
            'by_component': dict(components.most_common(100)),
            'categories_truncated': len(severities) > 100 or len(components) > 100,
            'text_truncated': len(header) + sum(len(item[0]) for item in results) > REPORT_TEXT_LIMIT,
            'context_graph_copied': False, 'results_sample': samples,
            'results_sample_limit': 100,
        }
        return report, ''.join(chunks)


def validate_shacl(data_graph, *, shacl_graph):
    from pyshacl.graph_abstraction import DataGraph
    from pyshacl.monkey import apply_patches
    from pyshacl.validator import assign_baked_in
    from pyshacl.errors import ValidationFailure
    # Match validate() entrypoint initialization for already-parsed local graphs.
    apply_patches()
    assign_baked_in()
    validator = MergeReportValidator(DataGraph.from_rdflib(data_graph), shacl_graph=shacl_graph,
        options={'inference': 'none', 'inplace': True, 'allow_infos': False, 'allow_warnings': False,
                 'advanced': False, 'abort_on_first': False, 'use_js': False, 'sparql_mode': False})
    try:
        conforms, report, text = validator.run()
    except ValidationFailure as exc:
        return False, Graph(), f'Validation Failure - {exc.message}'[:REPORT_TEXT_LIMIT], {'validation_failure': True}
    return conforms, report, text, validator.report_summary
