import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

class BrowserBoundsTests(unittest.TestCase):
 def test_paging_search_and_endpoint_integrity(self):
    tree=ast.parse(Path('backend/ingestion_service/api/ontology_browser.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='bounded_taxonomy')
    scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<bounds>','exec'),scope)
    payload={'nodes':[{'term_id':str(i),'label':f'Part {i}','kind':'class'} for i in range(12)],
             'edges':[{'source_term':'0','target_term':'1'},{'source_term':'0','target_term':'9'}]}
    first=scope['bounded_taxonomy'](payload,5)
    second=scope['bounded_taxonomy'](payload,5,offset=5)
    assert first['page']['next_offset']==5 and second['page']['next_offset']==10
    assert not ({n['term_id'] for n in first['nodes']} & {n['term_id'] for n in second['nodes']})
    found=scope['bounded_taxonomy'](payload,5,query='PART 9')
    assert [n['term_id'] for n in found['nodes']]==['9'] and found['page']['matching_terms']==1
    assert found['edges']==[]
    assert scope['bounded_taxonomy'](payload,5,offset=100)['page']['next_offset'] is None
    payload['nodes'].append({'term_id':'prop','kind':'property'})
    properties=scope['bounded_taxonomy'](payload,5,kind='property')
    assert [n['term_id'] for n in properties['nodes']]==['prop']
    payload['edges'].append({'source_term':'prop','target_term':'0','target_label':'Business Part','mapping_type':'domain'})
    properties=scope['bounded_taxonomy'](payload,5,kind='property')
    assert properties['nodes'][0]['browse_declarations']['domain']==[{'term_id':'0','label':'Business Part'}]
    assert properties['edges']==[]  # Boundary declarations do not fabricate graph edges within the slice.

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
