"""Run expensive RDF work in a process that can be terminated at its deadline."""
import pickle
import time
import subprocess
import sys
from pathlib import Path
from backend.depo_platform.network import bounded_timeout_seconds


def prepare_publication_turtle(content, rdf_format):
    """Avoid reserializing retained Turtle; the graph publisher validates it.

    Other RDF syntaxes still require conversion. Do not apply this shortcut
    to canonical graph preparation, which assigns stable blank-node identities.
    """
    if rdf_format == 'turtle':
        return content
    return prepare_rdf(content, rdf_format)


def prepare_rdf(content, rdf_format, *, canonical=False):
    started = time.monotonic()
    timeout = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180, maximum=3600)
    try:
        result = subprocess.run([sys.executable, '-m', 'backend.depo_platform.rdf_preparation'],
            input=pickle.dumps((content, rdf_format, canonical)), capture_output=True,
            timeout=timeout, cwd=str(Path(__file__).resolve().parents[2]))
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError('RDF preparation exceeded the publication deadline; its worker was terminated.') from exc
    if result.returncode != 0:
        raise ValueError('RDF preparation failed; check the retained artifact format.')
    # Only the trusted child program emits this payload, never an uploaded pickle.
    def check_deadline():
        if time.monotonic() - started >= timeout:
            raise TimeoutError('RDF preparation exceeded its deadline during result reconstruction.')
    check_deadline()
    value = pickle.loads(result.stdout)
    check_deadline()
    if canonical == 'projection':
        return value
    if canonical:
        from rdflib import Graph
        graph = Graph()
        for index, triple in enumerate(value):
            if index % 512 == 0: check_deadline()
            graph.add(triple)
        check_deadline()
        return graph
    return value


def main():
    from rdflib import Graph, BNode
    from rdflib.compare import to_canonical_graph
    content, rdf_format, canonical = pickle.loads(sys.stdin.buffer.read())
    graph = Graph().parse(data=content, format=rdf_format)
    # URI/literal-only graphs already have stable resource identities. Avoid
    # canonicalization overhead unless blank nodes actually need stable IDs.
    if canonical:
        has_blank_nodes = any(isinstance(value, BNode) for triple in graph for value in triple)
        if canonical == 'projection' and has_blank_nodes:
            from backend.depo_platform.projection_canonicalization import canonicalize_projection_graph
            canonical_graph = canonicalize_projection_graph(graph)
        else:
            canonical_graph = to_canonical_graph(graph) if has_blank_nodes else graph
        if canonical == 'projection':
            from backend.depo_platform.projection_preparation import build_projection
            value = build_projection(canonical_graph)
        else:
            value = list(canonical_graph)
    else:
        value = graph.serialize(format='turtle').encode('utf-8')
    sys.stdout.buffer.write(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))


if __name__ == '__main__':
    main()
