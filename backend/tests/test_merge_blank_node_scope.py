import ast
from pathlib import Path
import unittest

class Blank(str):
    counter=0
    def __new__(cls, value=None):
        if value is None:
            cls.counter+=1; value='generated-'+str(cls.counter)
        return super().__new__(cls,value)

class MergeScopeTests(unittest.TestCase):
    def test_source_local_nodes_stay_connected_but_do_not_join_other_sources(self):
        tree=ast.parse(Path('backend/ontology_service/merge_service.py').read_text())
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef))
        fn=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='_scoped_triples')
        fn.decorator_list=[]
        scope={'BNode':Blank}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<merge>','exec'),scope)
        source=[(Blank('shared'),'predicate','value'),('subject','predicate',Blank('shared'))]
        first=list(scope['_scoped_triples'](source)); second=list(scope['_scoped_triples'](source))
        self.assertEqual(first[0][0],first[1][2])
        self.assertNotEqual(first[0][0],second[0][0])
        self.assertEqual(first[0][1:],('predicate','value'))

if __name__=='__main__':unittest.main()
