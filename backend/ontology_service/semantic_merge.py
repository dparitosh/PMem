"""Check the exact proposed union, never infer merge safety from its sources alone."""
import hashlib


def check(turtle):
    from rdflib import Graph
    from .owl_dl import inspect_graph
    from backend.depo_platform.semantic_support import assessment
    evidence = inspect_graph(Graph().parse(data=turtle, format='turtle'),
                             artifact_sha256=hashlib.sha256(turtle.encode('utf-8')).hexdigest())
    return {'evidence': evidence, 'assessment': assessment(evidence)}


if __name__ == '__main__':
    import pickle
    import sys
    result = check(pickle.load(sys.stdin.buffer))
    pickle.dump(result, sys.stdout.buffer)
