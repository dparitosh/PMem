import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

class TaxonomyScopeTests(unittest.TestCase):
    def test_retained_version_cannot_fall_back_to_shared_prefix(self):
        tree=ast.parse(Path('backend/ingestion_service/api/ontology_browser.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='taxonomy');fn.decorator_list=[]
        class HTTPException(Exception):
            def __init__(self,status_code,detail):self.status_code=status_code
        def unavailable(*args):raise ValueError('No artifact')
        calls=[]
        scope={'_resolve_ontology_id':lambda value:value,'OntologyTaxonomyService':SimpleNamespace(get_taxonomy=unavailable),
               '_taxonomy_from_dictionary':lambda value:{'nodes':[]},'OntologyUploadManager':SimpleNamespace(get_ontology=lambda value:{'metadata':{'prefix':'shared'}}),
               '_taxonomy_from_graph':lambda value:calls.append(value) or {},'HTTPException':HTTPException}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<taxonomy>','exec'),scope)
        with self.assertRaises(HTTPException) as failure:scope['taxonomy']('retained-version')
        self.assertEqual(failure.exception.status_code,409);self.assertEqual(calls,[])
        result=scope['taxonomy']('shared');self.assertEqual(result['scope'],'shared-prefix-projection')

if __name__=='__main__':unittest.main()
