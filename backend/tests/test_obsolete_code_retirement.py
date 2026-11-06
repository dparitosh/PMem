"""Executable retirement checks: old entry points must not touch databases."""
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.mark.parametrize('path',[
    'backend/Services/step_0_generate_ontology.py',
    'backend/qif/worker.py',
])
def test_retired_cli_exits_with_migration_guidance(path):
    result=subprocess.run([sys.executable,path],capture_output=True,text=True,timeout=10)
    assert result.returncode!=0
    assert 'retired' in result.stderr.lower()
    assert 'INSTALLATION.md' in result.stderr
    assert 'Traceback' not in result.stderr


def test_retired_python_callers_fail_before_database_access():
    path=Path('backend/Services/step_0_generate_ontology.py')
    spec=importlib.util.spec_from_file_location('retired_ontology_cli',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with pytest.raises(RuntimeError,match='retired'):
        module.create_ontology_in_neo4j({'Class':{'property'}})
    with pytest.raises(RuntimeError,match='retired'):
        module.step_0_generate_ontology('does-not-exist.xml')


def test_document_retirement_handlers_have_no_unreachable_processing():
    tree=ast.parse(Path('backend/Services/documents_api.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.AsyncFunctionDef) and node.name in {'upload_documents','upload_single_document'}:
            assert len(node.body)==2  # Retirement explanation and HTTP 410 only.
            assert isinstance(node.body[-1],ast.Raise)


def test_legacy_mapping_handlers_keep_distinct_routes_and_names():
    tree=ast.parse(Path('backend/main.py').read_text(encoding='utf-8'))
    routes={}
    for node in tree.body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
        for decorator in node.decorator_list:
            if isinstance(decorator,ast.Call) and decorator.args and isinstance(decorator.args[0],ast.Constant):
                routes[decorator.args[0].value]=node.name
    assert routes['/ontology-mapper/{mapping_type}/mappings']=='get_ontology_mapper_mappings'
    assert routes['/ontology-mappings']=='list_legacy_ontology_mappings'


@pytest.mark.parametrize('stage,args', [
    ('OntologyEnrichmentService', ('enrich', '', {})),
    ('Neo4jLoadService', ('load_to_neo4j', '', {'entity_count': 100}, 'task')),
    ('HealthCheckService', ('verify', 'task', None, {})),
    ('UnifiedStage4to7Service', ('process_stages', '', {}, 'task')),
])
def test_simulated_pipeline_never_claims_enrichment_or_graph_success(stage,args):
    from backend.Services import pipeline_stages_4_7 as retired
    service=getattr(retired,stage)()
    method,*values=args
    with pytest.raises(RuntimeError,match='retired'):
        getattr(service,method)(*values)
