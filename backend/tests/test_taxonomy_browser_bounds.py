import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

class BrowserBoundsTests(unittest.TestCase):
 def test_reason_endpoint_uses_catalog_aware_taxonomy_resolver(self):
    tree=ast.parse(Path('backend/ingestion_service/api/ontology_browser.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='reasoning')
    fn.decorator_list=[]
    service=SimpleNamespace(get_reasoning=Mock(return_value={'ontology_id':'native-catalog-id'}))
    scope={'OntologyTaxonomyService':service}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<reason-route>','exec'),scope)
    assert scope['reasoning']('native-catalog-id')['ontology_id']=='native-catalog-id'
    service.get_reasoning.assert_called_once_with('native-catalog-id')

 def test_browser_slice_prioritizes_classes_preserves_totals_and_does_not_mutate_inventory(self):
    tree=ast.parse(Path('backend/ingestion_service/api/ontology_browser.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='bounded_taxonomy')
    scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<bounds>','exec'),scope)
    nodes=[{'term_id':'literal','kind':'literal'},{'term_id':'class','kind':'class'},{'term_id':'prop','kind':'property'}]
    payload={'nodes':nodes,'edges':[{'source_term':'class','target_term':'prop'},{'source_term':'class','target_term':'literal'}],'summary':{'triple_count':10}}
    result=scope['bounded_taxonomy'](payload,2,10)
    assert [n['term_id'] for n in result['nodes']]==['class','prop']
    assert result['summary']['total_terms']==3 and result['summary']['truncated']
    assert len(result['edges'])==1 and len(payload['nodes'])==3 and len(payload['edges'])==2
    assert 'truncated' not in payload['summary']
