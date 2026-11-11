"""Canonical blank-node identities without comparing disconnected components.

URI resources anchor identity. Only blank-to-blank links couple anonymous
components; canonicalizing unrelated restrictions together creates needless
symmetry work on large engineering ontologies. The retained RDF is unchanged.
"""
from collections import defaultdict
import hashlib
from rdflib import BNode, Graph
from rdflib.compare import to_canonical_graph


def canonicalize_projection_graph(graph):
    parents = {}

    def root(node):
        parents.setdefault(node, node)
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    blank_triples = []
    result = Graph()
    for triple in graph:
        blanks = [node for node in triple if isinstance(node, BNode)]
        if not blanks:
            result.add(triple)
            continue
        first = root(blanks[0])
        for node in blanks[1:]:
            parents[root(node)] = first
        blank_triples.append((blanks[0], triple))

    components = defaultdict(list)
    for node, triple in blank_triples:
        components[root(node)].append(triple)
    occurrences = defaultdict(int)
    for triples in components.values():
        component = Graph()
        for triple in triples:
            component.add(triple)
        canonical = list(to_canonical_graph(component))
        signature = '\n'.join(sorted(' '.join(node.n3() for node in triple) for triple in canonical))
        digest = hashlib.sha256(signature.encode('utf-8')).hexdigest()
        ordinal = occurrences[digest]
        occurrences[digest] += 1
        # Identical disconnected components need distinct nodes. Their ordinal
        # assignment cannot change the resulting graph: their triples are equal.
        mapping = {node: BNode(f'pc{digest}_{ordinal}_{node}')
                   for triple in canonical for node in triple if isinstance(node, BNode)}
        for triple in canonical:
            result.add(tuple(mapping.get(node, node) for node in triple))
    return result
