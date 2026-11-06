import unittest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from backend.depo_platform.projection_canonicalization import canonicalize_projection_graph


class ProjectionCanonicalizationTests(unittest.TestCase):
    def test_preserves_graph_and_anonymous_node_multiplicity(self):
        graph = Graph().parse(data='''@prefix : <urn:test:> .
            :a :restriction [ :value "same" ], [ :value "same" ] .
            :b :restriction [ :next [ :value "nested" ] ] .
            :c :next :d .''', format='turtle')
        result = canonicalize_projection_graph(graph)
        self.assertTrue(isomorphic(graph, result))
        self.assertEqual(len(graph), len(result))
        self.assertEqual(len({n for t in graph for n in t if isinstance(n, BNode)}),
                         len({n for t in result for n in t if isinstance(n, BNode)}))

    def test_identity_is_independent_of_order_and_blank_labels(self):
        graphs = [Graph().parse(data=text, format='turtle') for text in (
            '<urn:a> <urn:p> _:a, _:b . _:a <urn:q> _:c . _:c <urn:r> "x" . _:b <urn:r> "x" .',
            '_:z <urn:r> "x" . _:y <urn:r> "x" . _:x <urn:q> _:z . <urn:a> <urn:p> _:y, _:x .')]
        self.assertEqual(set(canonicalize_projection_graph(graphs[0])),
                         set(canonicalize_projection_graph(graphs[1])))

    def test_repeated_isomorphic_components_are_stable(self):
        def make(reverse=False):
            graph = Graph()
            for i in (reversed(range(200)) if reverse else range(200)):
                blank = BNode()
                graph.add((URIRef('urn:a'), URIRef('urn:p'), blank))
                graph.add((blank, URIRef('urn:q'), Literal('same')))
            return graph
        self.assertEqual(set(canonicalize_projection_graph(make())),
                         set(canonicalize_projection_graph(make(True))))

    def test_cyclic_connected_component_and_named_anchor_difference(self):
        graph = Graph().parse(data='''_:a <urn:p> _:b . _:b <urn:p> _:a .
            <urn:one> <urn:q> _:a . <urn:two> <urn:q> [ <urn:value> "v" ] .''', format='turtle')
        result = canonicalize_projection_graph(graph)
        self.assertTrue(isomorphic(graph, result))
        self.assertEqual(set(result), set(canonicalize_projection_graph(result)))


if __name__ == '__main__':
    unittest.main()
