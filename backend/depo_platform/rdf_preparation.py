"""Run expensive RDF work in a process that can be terminated at its deadline."""
import pickle
import time
import subprocess
import sys
from pathlib import Path
from backend.depo_platform.network import bounded_timeout_seconds


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
    from rdflib import Graph
    from rdflib.compare import to_canonical_graph
    content, rdf_format, canonical = pickle.loads(sys.stdin.buffer.read())
    graph = Graph().parse(data=content, format=rdf_format)
    value = list(to_canonical_graph(graph)) if canonical else graph.serialize(format='turtle').encode('utf-8')
    sys.stdout.buffer.write(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))


if __name__ == '__main__':
    main()
