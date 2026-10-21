"""OWL-RL with indexed blank-node bookkeeping; upstream inference rules unchanged."""
from owlrl import DeductiveClosure, OWLRL_Semantics


class _IndexedBlankNodes(list):
    """Append-only ordered list used by OWLRL_Semantics.rules/post_process.

    OWL-RL collects blank nodes with ``node not in self.bnodes`` in its first
    pass. A hash membership index avoids repeated scans of the complete list
    for XSD ontologies with many anonymous restrictions. Iteration still uses
    the original insertion order for upstream blank-predicate cleanup.
    """
    def __init__(self):
        super().__init__()
        self._members = set()

    def __contains__(self, node):
        return node in self._members

    def append(self, node):
        self._members.add(node)
        super().append(node)


class IndexedOWLRLSemantics(OWLRL_Semantics):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if type(self.bnodes) is not list or self.bnodes:
            raise ValueError('Unsupported OWL-RL blank-node bookkeeping; repair the pinned reasoning dependencies')
        self.bnodes = _IndexedBlankNodes()


def expand_owlrl(graph):
    """Run the same closure/options used by pySHACL's owlrl pre-inference."""
    DeductiveClosure(IndexedOWLRLSemantics).expand(graph)
