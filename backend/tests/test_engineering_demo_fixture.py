"""Synthetic fixture reproducibility and KPI integrity."""
import importlib.util
import json
from pathlib import Path
from rdflib import Graph, Namespace, RDF

def test_engineering_fixture_kpis_are_computed_from_generated_graph(tmp_path):
    path=Path(__file__).parents[2]/'scripts'/'generate_engineering_demo.py'
    spec=importlib.util.spec_from_file_location('demo_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.generate(tmp_path)
    graph=Graph().parse(tmp_path/'synthetic-engineering-demo.ttl',format='turtle')
    c=Namespace('https://depo.example.org/ceim/0.1/'); d=Namespace('https://example.org/nexus/synthetic-demo/')
    receipt=json.loads((tmp_path/'synthetic-receipt.json').read_text())
    assert receipt['synthetic'] is True and receipt['customer_approved'] is False
    assert receipt['triples']==len(graph)
    assert receipt['kpis'][0]['value']==len(set(graph.subjects(RDF.type,c.Part)))==3
    assert receipt['kpis'][1]['value']==len(set(graph.subjects(c.hasPMI,None)))==1
    assert (d.housing,c.hasRequirement,d.req) in graph
    assert (d.housing,c.hasPMI,d.pmi) in graph
    assert (d.assembly,c.hasPart,d.housing) in graph
    assert not list(graph.triples((None,c.satisfies,None)))
